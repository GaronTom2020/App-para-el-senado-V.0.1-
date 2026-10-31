"""Interfaz gráfica del programa (Tkinter, incluida en Python)."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

from . import __version__, config
from .cliente import Cancelado, Cliente, ErrorRed
from .contenido import (
    comisiones_texto, datos_diputados, datos_diputados_hcdn, datos_generales, descripcion, sesiones_votadas,
    filas_relacionados, texto_resumen, titulo_etapa_diputados,
)
from .ficha import ExpedienteNoEncontrado
from .identificador import ErrorIdentificador, parsear, separar_lote
from .busqueda import OTROS, Consulta, separar_palabras
from .ejes import Eje, buscar_eje, cargar_ejes, guardar_ejes
from . import plan_labor, senadores
from .seguimiento import Lista, OpcionesSeguimiento, ResultadoSeguimiento, markdown, revisar
from .sesion import OpcionesSesion, ResultadoSesion, etiqueta_referencias, generar_sesion
from .sesion import resumen as resumen_sesion
from .seguimiento import resumen as resumen_seguimiento
from .servicio import Opciones, generar
from .tematico import ETAPA, OpcionesTematicas, ResultadoTematico, generar_tematico, resumen, resumen_tipos
from .tematico import texto_resumen_tematico
from .util import fmt_fecha, nombre_comision

P = {
    "cupula": "#2E6B5F", "cupula_oscura": "#1F4E45", "cupula_tenue": "#E4EFEB", "piedra": "#EEF2F0",
    "papel": "#FFFFFF", "tinta": "#1F2B28", "suave": "#55645F", "linea": "#CBD5D1", "lacre": "#8C2F2F",
    "ambar": "#8A5A10", "apagado": "#9DB7B0", "subtitulo": "#D3E6E0",
}
TIPO_AUTOMATICO = "Detectar automáticamente"
OPCIONES_TIPO = [TIPO_AUTOMATICO] + [f"{codigo} — {nombre}" for codigo, nombre in config.TIPOS.items()]
COLOR_NIVEL = {"con_dictamen": "ambar", "vetado": "lacre", "caducado": "lacre", "rechazado": "lacre",
               "archivado": "lacre"}
MARCA_PASO = {"hecho": "✓", "actual": "●", "detenido": "×", "pendiente": "○"}
SIN_EJE = "(ninguno: escribir palabras)"
TODOS_ORIGENES = "Todos"
CUALQUIER_COMISION = "Cualquiera"
CUALQUIER_AUTOR = "Cualquier senador"
CUALQUIER_BLOQUE = "Cualquier bloque"
CARGANDO = "Cargando la lista del sitio…"
OPCIONES_ORIGEN = [TODOS_ORIGENES] + [f"{c} — {n}" for c, n in config.ORIGENES.items()]
TIPOS_TEMA = [("PL", "Ley"), ("PR", "Resolución"), ("PC", "Comunicación"), ("PD", "Declaración"), (OTROS, "Otros")]


# ============================================================== configuración

def _archivo_config() -> Path:
    return config.carpeta_app() / "config.json"


def cargar_config() -> dict:
    try:
        return json.loads(_archivo_config().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def guardar_config(datos: dict) -> None:
    try:
        _archivo_config().parent.mkdir(parents=True, exist_ok=True)
        _archivo_config().write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def abrir_en_sistema(ruta: Path | str) -> None:
    ruta = str(ruta)
    if sys.platform.startswith("win"):
        os.startfile(ruta)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", ruta])
    else:
        subprocess.Popen(["xdg-open", ruta])


def mensaje_de_error(error: Exception) -> str:
    if isinstance(error, (ErrorIdentificador, ExpedienteNoEncontrado)):
        return str(error)
    if isinstance(error, ErrorRed):
        return ("No se pudo conectar con el sitio del Senado. Revisá la conexión a internet "
                f"o probá de nuevo en unos minutos.\nDetalle: {error}")
    if isinstance(error, PermissionError):
        return f"No se pudo guardar el archivo: {error}. Cerralo si está abierto en Word y probá de nuevo."
    return f"Error inesperado: {type(error).__name__}: {error}"


# ================================================================== ventana

class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Informe de expedientes — H. Senado de la Nación")
        self.configure(bg=P["piedra"])
        self.minsize(940, 600)
        self.cfg = cargar_config()
        ancho = min(1200, self.winfo_screenwidth() - 40)
        alto = min(780, self.winfo_screenheight() - 90)
        self.geometry(f"{ancho}x{alto}+20+10")

        self.cola: queue.Queue = queue.Queue()
        self.cancelar = threading.Event()
        self.hilo: threading.Thread | None = None
        self.resultados: list = []
        self.actual = None
        self._enlaces: dict[str, str] = {}
        self._contando = False

        self._fuentes()
        self._estilos()
        self._variables()
        self._menu()
        self._construir()
        self.bind_all("<Control-Return>", lambda _e: self._generar())
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.after(120, self._procesar_cola)
        self.txt_expedientes.focus_set()

    # --------------------------------------------------------------- estilo
    def _fuentes(self) -> None:
        familias = set(tkfont.families(self))

        def elegir(*opciones):
            return next((f for f in opciones if f in familias), "TkDefaultFont")

        sans = elegir("Segoe UI", "Helvetica Neue", "Helvetica", "DejaVu Sans", "Arial")
        serif = elegir("Georgia", "Cambria", "DejaVu Serif", "Times New Roman")
        for nombre in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(nombre).configure(family=sans, size=10)
        self.f_normal = tkfont.Font(family=sans, size=10)
        self.f_chica = tkfont.Font(family=sans, size=9)
        self.f_negrita = tkfont.Font(family=sans, size=10, weight="bold")
        self.f_titulo = tkfont.Font(family=serif, size=18)
        self.f_numero = tkfont.Font(family=serif, size=22)
        self.f_situacion = tkfont.Font(family=serif, size=14)
        self.f_extracto = tkfont.Font(family=serif, size=11)
        self.option_add("*TCombobox*Listbox.font", self.f_normal)

    def _estilos(self) -> None:
        e = ttk.Style(self)
        e.theme_use("clam")
        e.configure(".", background=P["piedra"], foreground=P["tinta"], font=self.f_normal,
                    bordercolor=P["linea"], focuscolor=P["cupula_tenue"])
        e.configure("Tarjeta.TFrame", background=P["papel"])
        e.configure("TLabel", background=P["piedra"])
        e.configure("Tarjeta.TLabel", background=P["papel"])
        e.configure("Seccion.TLabel", background=P["papel"], font=self.f_negrita)
        e.configure("Ayuda.TLabel", background=P["papel"], foreground=P["suave"], font=self.f_chica)
        e.configure("Estado.TLabel", background=P["piedra"], foreground=P["tinta"])
        e.configure("Tarjeta.TCheckbutton", background=P["papel"], indicatorbackground=P["papel"],
                    indicatorforeground=P["cupula_oscura"], indicatormargin=(0, 0, 6, 0))
        e.map("Tarjeta.TCheckbutton", background=[("active", P["papel"])],
              indicatorbackground=[("disabled", P["piedra"])],
              indicatorforeground=[("disabled", P["apagado"])])
        e.configure("Tarjeta.TRadiobutton", background=P["papel"], indicatorbackground=P["papel"],
                    indicatorforeground=P["cupula_oscura"])
        e.map("Tarjeta.TRadiobutton", background=[("active", P["papel"])])
        e.configure("TSpinbox", fieldbackground=P["papel"], padding=4, arrowsize=12)
        e.configure("Chico.TButton", padding=(8, 3), font=self.f_chica)
        e.configure("Barra.TButton", padding=(10, 6), width=0)
        e.configure("TButton", padding=(12, 6), background=P["papel"])
        e.map("TButton", background=[("active", P["cupula_tenue"]), ("disabled", P["piedra"])])
        e.configure("Acento.TButton", background=P["cupula"], foreground="#FFFFFF", bordercolor=P["cupula"],
                    padding=(18, 8), font=self.f_negrita)
        e.map("Acento.TButton",
              background=[("disabled", P["apagado"]), ("pressed", P["cupula_oscura"]), ("active", P["cupula_oscura"])],
              foreground=[("disabled", "#F4F8F6")])
        e.configure("TEntry", fieldbackground=P["papel"], padding=5)
        e.configure("TCombobox", fieldbackground=P["papel"], padding=4)
        e.map("TCombobox", fieldbackground=[("readonly", P["papel"])])
        e.configure("Horizontal.TProgressbar", troughcolor=P["linea"], background=P["cupula"],
                    lightcolor=P["cupula"], darkcolor=P["cupula"], bordercolor=P["linea"], thickness=6)
        e.configure("TNotebook", background=P["piedra"], borderwidth=0, tabmargins=(0, 4, 0, 0))
        e.configure("TNotebook.Tab", padding=(16, 7), background=P["piedra"], foreground=P["suave"])
        e.map("TNotebook.Tab", background=[("selected", P["papel"])], foreground=[("selected", P["tinta"])])
        e.configure("Treeview", rowheight=28, background=P["papel"], fieldbackground=P["papel"], borderwidth=0)
        e.configure("Treeview.Heading", background=P["piedra"], foreground=P["suave"], font=self.f_negrita,
                    relief="flat", padding=(6, 6))
        e.map("Treeview", background=[("selected", P["cupula_tenue"])], foreground=[("selected", P["tinta"])])

    def _variables(self) -> None:
        c = self.cfg
        self.var_tipo = tk.StringVar(value=TIPO_AUTOMATICO)
        self.var_reuniones = tk.BooleanVar(value=c.get("reuniones", True))
        self.var_asesores = tk.BooleanVar(value=c.get("asesores", True))
        self.var_agenda = tk.BooleanVar(value=c.get("agenda", True))
        self.var_docx = tk.BooleanVar(value=c.get("docx", True))
        self.var_html = tk.BooleanVar(value=c.get("html", True))
        self.var_carpeta = tk.StringVar(value=c.get("carpeta", str(config.carpeta_informes_por_defecto())))
        self.var_cache = tk.BooleanVar(value=c.get("usar_cache", True))
        self.var_diagnostico = tk.BooleanVar(value=c.get("diagnostico", False))
        anio = datetime.now().year
        self.ejes: list[Eje] = cargar_ejes()
        self.var_eje = tk.StringVar(value=SIN_EJE)
        self.var_palabras = tk.StringVar()
        self.var_modo = tk.StringVar(value="alguna")
        self.var_excluir = tk.StringVar()
        self.var_desde = tk.StringVar(value=str(anio - 1))
        self.var_hasta = tk.StringVar(value=str(anio))
        self.var_origen = tk.StringVar(value=TODOS_ORIGENES)
        self.var_comision = tk.StringVar(value=CUALQUIER_COMISION)
        self.var_autor = tk.StringVar(value=CUALQUIER_AUTOR)
        self.var_bloque = tk.StringVar(value=CUALQUIER_BLOQUE)
        self.lista_autores: list = []
        self.lista_bloques: dict = {}
        self._cargando_senadores = False
        tipos_guardados = c.get("tema_tipos", ["PL", "PR", "PC"])
        self.vars_tipos = {t: tk.BooleanVar(value=t in tipos_guardados) for t, _ in TIPOS_TEMA}
        self.var_detallar = tk.BooleanVar(value=c.get("tema_detallar", True))
        self.var_reuniones_tema = tk.BooleanVar(value=False)
        self.var_individuales = tk.BooleanVar(value=False)
        self.var_t_docx = tk.BooleanVar(value=c.get("tema_docx", True))
        self.var_t_html = tk.BooleanVar(value=c.get("tema_html", True))
        self.var_t_xlsx = tk.BooleanVar(value=c.get("tema_xlsx", True))
        self.lista_seguimiento = Lista()
        self.var_seg_nuevo = tk.StringVar()
        self.var_seg_reuniones = tk.BooleanVar(value=c.get("seguimiento_reuniones", True))
        self.var_ses_fuente = tk.StringVar(value="Abrí un archivo, buscá el plan en el sitio o pegá el texto.")
        self.var_ses_plan = tk.StringVar()
        self.var_ses_reuniones = tk.BooleanVar(value=False)
        self.vars_ses_formatos = {f: tk.BooleanVar(value=f in c.get("sesion_formatos", ["docx", "html", "xlsx", "csv"]))
                                  for f in ("docx", "html", "xlsx", "csv")}
        self.planes_publicados: list = []
        self.plan_publicado = None
        self.ses_fuente = ""
        self.comisiones_por_nombre = {nombre_comision(n): i for i, n in sorted(config.COMISIONES.items(),
                                                                              key=lambda kv: nombre_comision(kv[1]))}
        self.var_estado = tk.StringVar(value="Escribí uno o más expedientes y presioná «Generar informe».")
        self.var_resultado = tk.StringVar()

    # ---------------------------------------------------------------- menú
    def _menu(self) -> None:
        barra = tk.Menu(self)
        archivo = tk.Menu(barra, tearoff=False)
        archivo.add_command(label="Generar informe", accelerator="Ctrl+Enter", command=self._generar)
        archivo.add_command(label="Abrir carpeta de informes", command=self._abrir_carpeta)
        archivo.add_separator()
        archivo.add_command(label="Salir", command=self._cerrar)
        barra.add_cascade(label="Archivo", menu=archivo)
        herramientas = tk.Menu(barra, tearoff=False)
        herramientas.add_checkbutton(label="Usar caché (consultas repetidas más rápidas)", variable=self.var_cache)
        herramientas.add_checkbutton(label="Guardar las páginas descargadas (diagnóstico)",
                                     variable=self.var_diagnostico)
        herramientas.add_command(label="Abrir carpeta de diagnóstico", command=self._abrir_diagnostico)
        herramientas.add_separator()
        herramientas.add_command(label="Vaciar caché", command=self._vaciar_cache)
        barra.add_cascade(label="Herramientas", menu=herramientas)
        ayuda = tk.Menu(barra, tearoff=False)
        ayuda.add_command(label="Cómo funciona", command=self._ayuda)
        ayuda.add_command(label="Acerca del programa", command=self._acerca)
        barra.add_cascade(label="Ayuda", menu=ayuda)
        self.config(menu=barra)

    # ------------------------------------------------------------- armado
    def _construir(self) -> None:
        banda = tk.Frame(self, bg=P["cupula"])
        banda.pack(fill="x")
        tk.Label(banda, text="Informe de expedientes", bg=P["cupula"], fg="#FFFFFF",
                 font=self.f_titulo).pack(anchor="w", padx=22, pady=(10, 0))
        tk.Label(banda, text="Por expediente o por tema: situación en el trámite, reuniones de comisión y "
                             "enlaces a cada fuente, en Word, HTML y Excel.", bg=P["cupula"], fg=P["subtitulo"],
                 font=self.f_normal).pack(anchor="w", padx=22, pady=(0, 10))

        cuerpo = ttk.Frame(self, padding=(14, 12, 14, 12))
        cuerpo.pack(fill="both", expand=True)
        cuerpo.columnconfigure(1, weight=1)
        cuerpo.rowconfigure(0, weight=1)
        self.modos = ttk.Notebook(cuerpo)
        self.modos.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        exterior, interior = self._desplazable(self.modos)
        self._panel_opciones(interior).pack(fill="both", expand=True)
        self.modos.add(exterior, text="Un expediente")
        exterior, interior = self._desplazable(self.modos)
        self._panel_tema(interior).pack(fill="both", expand=True)
        self.modos.add(exterior, text="Por tema")
        exterior, interior = self._desplazable(self.modos)
        self._panel_seguimiento(interior).pack(fill="both", expand=True)
        self.modos.add(exterior, text="Seguimiento")
        exterior, interior = self._desplazable(self.modos)
        self._panel_sesion(interior).pack(fill="both", expand=True)
        self.modos.add(exterior, text="Sesión")
        self._panel_resultados(cuerpo).grid(row=0, column=1, sticky="nsew")

    def _desplazable(self, padre):
        """Marco con barra de desplazamiento vertical (para pantallas bajas)."""
        exterior = ttk.Frame(padre, style="Tarjeta.TFrame")
        lienzo = tk.Canvas(exterior, bg=P["papel"], highlightthickness=0, borderwidth=0)
        barra = ttk.Scrollbar(exterior, orient="vertical", command=lienzo.yview)
        interior = ttk.Frame(lienzo, style="Tarjeta.TFrame")
        ventana = lienzo.create_window((0, 0), window=interior, anchor="nw")

        def ajustar(_e=None):
            lienzo.configure(scrollregion=lienzo.bbox("all"), width=interior.winfo_reqwidth())

        interior.bind("<Configure>", ajustar)
        lienzo.bind("<Configure>", lambda e: lienzo.itemconfigure(ventana, width=e.width))
        lienzo.configure(yscrollcommand=barra.set)
        lienzo.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

        def rueda(evento):
            if interior.winfo_reqheight() <= lienzo.winfo_height():
                return
            arriba = getattr(evento, "num", 0) == 4 or getattr(evento, "delta", 0) > 0
            lienzo.yview_scroll(-1 if arriba else 1, "units")

        def activar(_e):
            for secuencia in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                lienzo.bind_all(secuencia, rueda)

        def desactivar(_e):
            for secuencia in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                lienzo.unbind_all(secuencia)

        exterior.bind("<Enter>", activar)
        exterior.bind("<Leave>", desactivar)
        return exterior, interior

    def _panel_tema(self, padre) -> ttk.Frame:
        marco = ttk.Frame(padre, style="Tarjeta.TFrame", padding=(16, 12, 16, 14))
        fila = 0

        def etiqueta(texto, arriba=9):
            nonlocal fila
            ttk.Label(marco, text=texto, style="Seccion.TLabel").grid(row=fila, column=0, columnspan=3, sticky="w",
                                                                     pady=(arriba, 4))
            fila += 1

        def ayuda(texto):
            nonlocal fila
            ttk.Label(marco, text=texto, style="Ayuda.TLabel", wraplength=300, justify="left").grid(
                row=fila, column=0, columnspan=3, sticky="w", pady=(3, 0))
            fila += 1

        etiqueta("Eje temático", arriba=0)
        self.combo_eje = ttk.Combobox(marco, textvariable=self.var_eje, state="readonly", width=36)
        self.combo_eje.grid(row=fila, column=0, columnspan=3, sticky="ew")
        self.combo_eje.bind("<<ComboboxSelected>>", self._eje_elegido)
        self._actualizar_combo_ejes()
        fila += 1
        botones_eje = ttk.Frame(marco, style="Tarjeta.TFrame")
        botones_eje.grid(row=fila, column=0, columnspan=3, sticky="w", pady=(5, 0))
        ttk.Button(botones_eje, text="Guardar como eje…", style="Chico.TButton", command=self._guardar_eje).pack(side="left")
        ttk.Button(botones_eje, text="Borrar eje", style="Chico.TButton", command=self._borrar_eje).pack(
            side="left", padx=(6, 0))
        fila += 1

        etiqueta("Palabras clave")
        ttk.Entry(marco, textvariable=self.var_palabras).grid(row=fila, column=0, columnspan=3, sticky="ew")
        fila += 1
        ayuda("Separadas por coma. Se busca en el extracto el comienzo de cada palabra, sin importar tildes.")
        modos = ttk.Frame(marco, style="Tarjeta.TFrame")
        modos.grid(row=fila, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Radiobutton(modos, text="Que tenga alguna", value="alguna", variable=self.var_modo,
                        style="Tarjeta.TRadiobutton").pack(side="left")
        ttk.Radiobutton(modos, text="Que tenga todas", value="todas", variable=self.var_modo,
                        style="Tarjeta.TRadiobutton").pack(side="left", padx=(14, 0))
        fila += 1

        etiqueta("Excluir si menciona (opcional)")
        ttk.Entry(marco, textvariable=self.var_excluir).grid(row=fila, column=0, columnspan=3, sticky="ew")
        fila += 1

        etiqueta("Años de los expedientes")
        anios = ttk.Frame(marco, style="Tarjeta.TFrame")
        anios.grid(row=fila, column=0, columnspan=3, sticky="w")
        hoy = datetime.now().year
        ttk.Spinbox(anios, from_=1983, to=hoy, textvariable=self.var_desde, width=7).pack(side="left")
        ttk.Label(anios, text="a", style="Tarjeta.TLabel").pack(side="left", padx=8)
        ttk.Spinbox(anios, from_=1983, to=hoy, textvariable=self.var_hasta, width=7).pack(side="left")
        fila += 1

        etiqueta("Origen")
        ttk.Combobox(marco, textvariable=self.var_origen, values=OPCIONES_ORIGEN, state="readonly").grid(
            row=fila, column=0, columnspan=3, sticky="ew")
        fila += 1
        etiqueta("Comisión del giro")
        ttk.Combobox(marco, textvariable=self.var_comision, state="readonly",
                     values=[CUALQUIER_COMISION] + list(self.comisiones_por_nombre)).grid(
            row=fila, column=0, columnspan=3, sticky="ew")
        fila += 1

        etiqueta("Autor o bloque (opcional)")
        self.combo_autor = ttk.Combobox(marco, textvariable=self.var_autor, values=[CUALQUIER_AUTOR],
                                        postcommand=self._cargar_senadores)
        self.combo_autor.grid(row=fila, column=0, columnspan=3, sticky="ew")
        fila += 1
        self.combo_bloque = ttk.Combobox(marco, textvariable=self.var_bloque, values=[CUALQUIER_BLOQUE],
                                         state="readonly", postcommand=self._cargar_senadores)
        self.combo_bloque.grid(row=fila, column=0, columnspan=3, sticky="ew", pady=(5, 0))
        fila += 1
        ayuda("Escribí el apellido del senador y elegilo de la lista, o elegí un bloque (si elegís los dos, se usa "
              "el bloque). Se toman los proyectos con su firma, como autor o coautor; el bloque usa sus "
              "integrantes actuales.")

        etiqueta("Tipos de proyecto")
        for k, (codigo, nombre) in enumerate(TIPOS_TEMA):
            ttk.Checkbutton(marco, text=nombre, variable=self.vars_tipos[codigo], style="Tarjeta.TCheckbutton").grid(
                row=fila + k // 3, column=k % 3, sticky="w")
        fila += 2

        etiqueta("De cada expediente encontrado")
        for texto, variable in (("Consultar su ficha (etapa y comisión)", self.var_detallar),
                                ("Buscar sus reuniones de comisión (lento)", self.var_reuniones_tema),
                                ("Generar además su informe completo", self.var_individuales)):
            ttk.Checkbutton(marco, text=texto, variable=variable, style="Tarjeta.TCheckbutton").grid(
                row=fila, column=0, columnspan=3, sticky="w")
            fila += 1

        etiqueta("Formato")
        for k, (texto, variable) in enumerate((("Word", self.var_t_docx), ("HTML", self.var_t_html),
                                               ("Excel", self.var_t_xlsx))):
            ttk.Checkbutton(marco, text=texto, variable=variable, style="Tarjeta.TCheckbutton").grid(
                row=fila, column=k, sticky="w")
        fila += 1
        ayuda("Se guarda en la misma carpeta elegida en «Un expediente».")

        botones = ttk.Frame(marco, style="Tarjeta.TFrame")
        botones.grid(row=fila, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        botones.columnconfigure(0, weight=1)
        self.btn_generar_tema = ttk.Button(botones, text="Generar informe temático", style="Acento.TButton",
                                           command=self._generar_tematico)
        self.btn_generar_tema.grid(row=0, column=0, sticky="ew")
        self.btn_cancelar_tema = ttk.Button(botones, text="Cancelar", command=self._cancelar, state="disabled")
        self.btn_cancelar_tema.grid(row=0, column=1, padx=(8, 0))
        for col in range(3):
            marco.columnconfigure(col, weight=1)
        return marco

    def _panel_seguimiento(self, padre) -> ttk.Frame:
        marco = ttk.Frame(padre, style="Tarjeta.TFrame", padding=(16, 12, 16, 14))
        ttk.Label(marco, text="Expedientes en seguimiento", style="Seccion.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        contenedor = ttk.Frame(marco, style="Tarjeta.TFrame")
        contenedor.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.arbol_seguimiento = ttk.Treeview(contenedor, columns=("exp", "situacion"), show="headings",
                                              selectmode="extended", height=7)
        self.arbol_seguimiento.heading("exp", text="Expediente", anchor="w")
        self.arbol_seguimiento.heading("situacion", text="Última situación conocida", anchor="w")
        self.arbol_seguimiento.column("exp", width=124, stretch=False)
        self.arbol_seguimiento.column("situacion", width=200, stretch=True)
        barra = ttk.Scrollbar(contenedor, orient="vertical", command=self.arbol_seguimiento.yview)
        self.arbol_seguimiento.configure(yscrollcommand=barra.set)
        self.arbol_seguimiento.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.arbol_seguimiento.bind("<Delete>", lambda _e: self._quitar_seguimiento())
        self.arbol_seguimiento.bind("<Double-1>", lambda _e: self._ficha_seguimiento())

        ttk.Label(marco, text="Agregar expediente", style="Seccion.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(10, 4))
        entrada = ttk.Entry(marco, textvariable=self.var_seg_nuevo)
        entrada.grid(row=3, column=0, sticky="ew", padx=(0, 6))
        entrada.bind("<Return>", lambda _e: self._agregar_seguimiento())
        ttk.Button(marco, text="Agregar", command=self._agregar_seguimiento).grid(row=3, column=1, sticky="ew")
        acciones = ttk.Frame(marco, style="Tarjeta.TFrame")
        acciones.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(acciones, text="Quitar los elegidos", style="Chico.TButton",
                   command=self._quitar_seguimiento).pack(side="left")
        ttk.Button(acciones, text="Ver ficha", style="Chico.TButton",
                   command=self._ficha_seguimiento).pack(side="left", padx=(6, 0))
        ttk.Label(marco, text="También podés sumar expedientes desde la lista del modo «Por tema», con clic derecho.",
                  style="Ayuda.TLabel", wraplength=300, justify="left").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        ttk.Label(marco, text="Al revisar", style="Seccion.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(10, 4))
        ttk.Checkbutton(marco, text="Buscar también reuniones de comisión (lento)", variable=self.var_seg_reuniones,
                        style="Tarjeta.TCheckbutton").grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Label(marco, text="Se compara cada expediente con la revisión anterior: giros, egresos, dictámenes, "
                              "votaciones, sanción, reuniones convocadas y caducidad cercana (menos de 60 días). "
                              "El resumen se guarda en HTML y Markdown en la carpeta de informes.",
                  style="Ayuda.TLabel", wraplength=300, justify="left").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(4, 0))

        botones = ttk.Frame(marco, style="Tarjeta.TFrame")
        botones.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        botones.columnconfigure(0, weight=1)
        self.btn_revisar = ttk.Button(botones, text="Revisar novedades", style="Acento.TButton",
                                      command=self._revisar_seguimiento)
        self.btn_revisar.grid(row=0, column=0, sticky="ew")
        self.btn_cancelar_seg = ttk.Button(botones, text="Cancelar", command=self._cancelar, state="disabled")
        self.btn_cancelar_seg.grid(row=0, column=1, padx=(8, 0))
        marco.columnconfigure(0, weight=1)
        self._llenar_seguimiento()
        return marco

    def _panel_sesion(self, padre) -> ttk.Frame:
        marco = ttk.Frame(padre, style="Tarjeta.TFrame", padding=(16, 12, 16, 14))
        ttk.Label(marco, text="Plan de labor", style="Seccion.TLabel").grid(row=0, column=0, columnspan=2, sticky="w",
                                                                         pady=(0, 4))
        botones = ttk.Frame(marco, style="Tarjeta.TFrame")
        botones.grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Button(botones, text="Abrir archivo…", style="Chico.TButton", command=self._abrir_plan).pack(side="left")
        ttk.Button(botones, text="Buscar en el sitio", style="Chico.TButton",
                   command=self._buscar_planes).pack(side="left", padx=(6, 0))
        self.combo_planes = ttk.Combobox(marco, textvariable=self.var_ses_plan, state="disabled", width=36)
        self.combo_planes.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.combo_planes.bind("<<ComboboxSelected>>", self._elegir_plan_publicado)
        ttk.Label(marco, text="O pegá el texto del plan (podés corregirlo antes de generar):", style="Ayuda.TLabel",
                  wraplength=300, justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 2))
        self.txt_plan = tk.Text(marco, height=7, width=34, wrap="word", font=self.f_chica, relief="flat",
                                bg=P["papel"], fg=P["tinta"], insertbackground=P["tinta"], highlightthickness=1,
                                highlightbackground=P["linea"], highlightcolor=P["cupula"], padx=8, pady=6, undo=True)
        self.txt_plan.grid(row=4, column=0, columnspan=2, sticky="ew")
        ttk.Label(marco, textvariable=self.var_ses_fuente, style="Ayuda.TLabel", wraplength=300,
                  justify="left").grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(marco, text="Ver los asuntos", style="Chico.TButton",
                   command=self._vista_previa_sesion).grid(row=6, column=0, sticky="w", pady=(6, 0))

        ttk.Label(marco, text="De cada expediente", style="Seccion.TLabel").grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(10, 4))
        ttk.Checkbutton(marco, text="Buscar también reuniones de comisión (lento)", variable=self.var_ses_reuniones,
                        style="Tarjeta.TCheckbutton").grid(row=8, column=0, columnspan=2, sticky="w")
        ttk.Label(marco, text="Formato", style="Seccion.TLabel").grid(row=9, column=0, columnspan=2, sticky="w",
                                                                    pady=(10, 4))
        formatos = ttk.Frame(marco, style="Tarjeta.TFrame")
        formatos.grid(row=10, column=0, columnspan=2, sticky="w")
        for texto_f, clave in (("Word", "docx"), ("HTML", "html"), ("Excel", "xlsx"), ("CSV (Power BI)", "csv")):
            ttk.Checkbutton(formatos, text=texto_f, variable=self.vars_ses_formatos[clave],
                            style="Tarjeta.TCheckbutton").pack(side="left", padx=(0, 8))

        acciones = ttk.Frame(marco, style="Tarjeta.TFrame")
        acciones.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        acciones.columnconfigure(0, weight=1)
        self.btn_generar_ses = ttk.Button(acciones, text="Generar informe de sesión", style="Acento.TButton",
                                          command=self._generar_sesion)
        self.btn_generar_ses.grid(row=0, column=0, sticky="ew")
        self.btn_cancelar_ses = ttk.Button(acciones, text="Cancelar", command=self._cancelar, state="disabled")
        self.btn_cancelar_ses.grid(row=0, column=1, padx=(8, 0))
        marco.columnconfigure(0, weight=1)
        return marco

    def _panel_opciones(self, padre) -> ttk.Frame:
        marco = ttk.Frame(padre, style="Tarjeta.TFrame", padding=(16, 12, 16, 14))
        fila = 0

        def etiqueta(texto, estilo="Seccion.TLabel", arriba=9):
            nonlocal fila
            ttk.Label(marco, text=texto, style=estilo).grid(row=fila, column=0, columnspan=2, sticky="w",
                                                           pady=(arriba, 4))
            fila += 1

        etiqueta("Expedientes", arriba=0)
        self.txt_expedientes = tk.Text(marco, height=3, width=34, wrap="none", font=self.f_normal, relief="flat",
                                       bg=P["papel"], fg=P["tinta"], insertbackground=P["tinta"],
                                       highlightthickness=1, highlightbackground=P["linea"],
                                       highlightcolor=P["cupula"], padx=8, pady=6, undo=True)
        self.txt_expedientes.grid(row=fila, column=0, columnspan=2, sticky="ew")
        self.txt_expedientes.bind("<Return>", self._enter_en_expedientes)
        fila += 1
        ttk.Label(marco, text="Uno por línea. Ejemplos: S-1234/24, CD-14/24, PE-107/24, o el enlace de la ficha "
                              "del Senado.", style="Ayuda.TLabel", wraplength=300, justify="left").grid(
            row=fila, column=0, columnspan=2, sticky="w", pady=(4, 0))
        fila += 1

        etiqueta("Tipo")
        combo = ttk.Combobox(marco, textvariable=self.var_tipo, values=OPCIONES_TIPO, state="readonly", width=36)
        combo.grid(row=fila, column=0, columnspan=2, sticky="ew")
        fila += 1

        etiqueta("Qué buscar")
        ttk.Checkbutton(marco, text="Reuniones de comisión en que se trató", variable=self.var_reuniones,
                        style="Tarjeta.TCheckbutton", command=self._sincronizar).grid(
            row=fila, column=0, columnspan=2, sticky="w")
        fila += 1
        self.chk_asesores = ttk.Checkbutton(marco, text="Incluir reuniones de asesores", variable=self.var_asesores,
                                            style="Tarjeta.TCheckbutton")
        self.chk_asesores.grid(row=fila, column=0, columnspan=2, sticky="w", padx=(22, 0))
        fila += 1
        ttk.Checkbutton(marco, text="Reuniones ya convocadas (agenda)", variable=self.var_agenda,
                        style="Tarjeta.TCheckbutton").grid(row=fila, column=0, columnspan=2, sticky="w")
        fila += 1

        etiqueta("Formato")
        ttk.Checkbutton(marco, text="Word (.docx)", variable=self.var_docx, style="Tarjeta.TCheckbutton").grid(
            row=fila, column=0, sticky="w")
        ttk.Checkbutton(marco, text="HTML (navegador)", variable=self.var_html, style="Tarjeta.TCheckbutton").grid(
            row=fila, column=1, sticky="w")
        fila += 1

        etiqueta("Guardar en")
        ttk.Entry(marco, textvariable=self.var_carpeta, width=26).grid(row=fila, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(marco, text="Elegir…", command=self._elegir_carpeta).grid(row=fila, column=1, sticky="ew")
        fila += 1

        etiqueta("Notas para el informe (opcional)")
        self.txt_notas = tk.Text(marco, height=2, width=34, wrap="word", font=self.f_normal, relief="flat",
                                 bg=P["papel"], fg=P["tinta"], insertbackground=P["tinta"], highlightthickness=1,
                                 highlightbackground=P["linea"], highlightcolor=P["cupula"], padx=8, pady=6)
        self.txt_notas.grid(row=fila, column=0, columnspan=2, sticky="ew")
        fila += 1

        botones = ttk.Frame(marco, style="Tarjeta.TFrame")
        botones.grid(row=fila, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        botones.columnconfigure(0, weight=1)
        self.btn_generar = ttk.Button(botones, text="Generar informe", style="Acento.TButton", command=self._generar)
        self.btn_generar.grid(row=0, column=0, sticky="ew")
        self.btn_cancelar = ttk.Button(botones, text="Cancelar", command=self._cancelar, state="disabled")
        self.btn_cancelar.grid(row=0, column=1, padx=(8, 0))
        marco.columnconfigure(0, weight=1)
        self._sincronizar()
        return marco

    def _panel_resultados(self, padre) -> ttk.Frame:
        marco = ttk.Frame(padre)
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(2, weight=1)

        estado = ttk.Frame(marco)
        estado.grid(row=0, column=0, sticky="ew")
        estado.columnconfigure(0, weight=1)
        ttk.Label(estado, textvariable=self.var_estado, style="Estado.TLabel").grid(row=0, column=0, sticky="w")
        self.combo_resultado = ttk.Combobox(estado, textvariable=self.var_resultado, state="disabled", width=26)
        self.combo_resultado.grid(row=0, column=1, sticky="e")
        self.combo_resultado.bind("<<ComboboxSelected>>", self._elegir_resultado)
        self.barra = ttk.Progressbar(marco, mode="determinate", style="Horizontal.TProgressbar")
        self.barra.grid(row=1, column=0, sticky="ew", pady=(8, 10))

        self.pestanias = ttk.Notebook(marco)
        self.pestanias.grid(row=2, column=0, sticky="nsew")
        self.txt_resumen = self._texto_solo_lectura(self.pestanias)
        self.pestanias.add(self.txt_resumen.master, text="Resumen")
        self.arbol_expedientes = self._arbol(
            self.pestanias, [("exp", "Expediente", 104), ("tipo", "Tipo", 50), ("etapa", "Situación", 210),
                             ("extracto", "Extracto", 300)],
            ayuda="Doble clic: abre la ficha. Clic derecho: informe completo o agregar a la lista de seguimiento.")
        self.pestanias.add(self.arbol_expedientes.master, text="Expedientes", state="hidden")
        self.arbol_reuniones = self._arbol(
            self.pestanias, [("fecha", "Fecha", 92), ("reunion", "Reunión", 300), ("tipo", "Tipo", 84),
                             ("docs", "Documentos", 120)],
            ayuda="Doble clic: abre la nota de la reunión. Clic derecho: versión taquigráfica, video o copiar enlace.")
        self.pestanias.add(self.arbol_reuniones.master, text="Reuniones")
        self.arbol_tramite = self._arbol(
            self.pestanias, [("detalle", "Detalle", 300), ("fecha", "Fecha", 100), ("estado", "Estado / egreso", 200)],
            con_arbol=True, ayuda="Doble clic en una orden del día, votación o convocatoria: la abre en el navegador.")
        self.pestanias.add(self.arbol_tramite.master, text="Trámite")
        self.txt_registro = self._texto_solo_lectura(self.pestanias, fuente=self.f_chica)
        self.pestanias.add(self.txt_registro.master, text="Registro")
        self._preparar_resumen()
        self._mostrar_bienvenida()

        acciones = ttk.Frame(marco)
        acciones.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(acciones, text="Abrir:").grid(row=0, column=0, padx=(0, 8))
        self.btn_word = ttk.Button(acciones, text="Word", command=lambda: self._abrir("docx"), state="disabled",
                                   style="Barra.TButton")
        self.btn_html = ttk.Button(acciones, text="HTML", command=lambda: self._abrir("html"), state="disabled",
                                   style="Barra.TButton")
        self.btn_excel = ttk.Button(acciones, text="Excel", command=lambda: self._abrir("xlsx"), state="disabled",
                                    style="Barra.TButton")
        self.btn_ficha = ttk.Button(acciones, text="Ver ficha", command=self._ver_ficha, state="disabled",
                                    style="Barra.TButton")
        self.btn_copiar = ttk.Button(acciones, text="Copiar resumen", command=self._copiar, state="disabled",
                                     style="Barra.TButton")
        for i, b in enumerate((self.btn_word, self.btn_html, self.btn_excel, self.btn_ficha, self.btn_copiar), 1):
            b.grid(row=0, column=i, padx=(0, 6))
        ttk.Button(acciones, text="Carpeta", command=self._abrir_carpeta, style="Barra.TButton").grid(row=0, column=7, sticky="e")
        acciones.columnconfigure(6, weight=1)

        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Abrir la nota de la reunión", command=lambda: self._abrir_reunion("nota"))
        menu.add_command(label="Abrir versión taquigráfica", command=lambda: self._abrir_reunion("vt"))
        menu.add_command(label="Abrir video", command=lambda: self._abrir_reunion("video"))
        menu.add_separator()
        menu.add_command(label="Copiar enlace de la nota", command=lambda: self._abrir_reunion("copiar"))
        self.menu_reunion = menu
        self.arbol_reuniones.bind("<Double-1>", lambda _e: self._abrir_reunion("nota"))
        self.arbol_reuniones.bind("<Button-3>", self._menu_contextual)
        self.arbol_tramite.bind("<Double-1>", self._abrir_tramite)
        menu_exp = tk.Menu(self, tearoff=False)
        menu_exp.add_command(label="Ver la ficha en el sitio", command=lambda: self._accion_expediente("ficha"))
        menu_exp.add_command(label="Generar el informe completo de este expediente",
                             command=lambda: self._accion_expediente("informe"))
        menu_exp.add_command(label="Agregar a la lista de seguimiento",
                             command=lambda: self._accion_expediente("seguir"))
        menu_exp.add_separator()
        menu_exp.add_command(label="Copiar el número", command=lambda: self._accion_expediente("copiar"))
        self.menu_expediente = menu_exp
        self.arbol_expedientes.bind("<Double-1>", lambda _e: self._accion_expediente("ficha"))
        self.arbol_expedientes.bind("<Button-3>", self._menu_expedientes)
        return marco

    def _texto_solo_lectura(self, padre, fuente=None) -> tk.Text:
        contenedor = ttk.Frame(padre, style="Tarjeta.TFrame")
        texto = tk.Text(contenedor, wrap="word", relief="flat", bg=P["papel"], fg=P["tinta"],
                        font=fuente or self.f_normal, padx=18, pady=14, cursor="arrow", highlightthickness=0,
                        spacing1=1, spacing3=2)
        barra = ttk.Scrollbar(contenedor, orient="vertical", command=texto.yview)
        texto.configure(yscrollcommand=barra.set, state="disabled")
        texto.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        return texto

    def _arbol(self, padre, columnas, con_arbol=False, ayuda: str = "") -> ttk.Treeview:
        contenedor = ttk.Frame(padre, style="Tarjeta.TFrame")
        if ayuda:
            ttk.Label(contenedor, text=ayuda, style="Ayuda.TLabel", padding=(10, 6)).pack(side="bottom", anchor="w")
        arbol = ttk.Treeview(contenedor, columns=[c[0] for c in columnas],
                             show="tree headings" if con_arbol else "headings", selectmode="browse")
        if con_arbol:
            arbol.column("#0", width=24, stretch=False)
        for clave, titulo, ancho in columnas:
            arbol.heading(clave, text=titulo, anchor="w")
            arbol.column(clave, width=ancho, minwidth=44, anchor="w",
                         stretch=clave in ("reunion", "detalle", "extracto"))
        barra = ttk.Scrollbar(contenedor, orient="vertical", command=arbol.yview)
        arbol.configure(yscrollcommand=barra.set)
        arbol.tag_configure("grupo", font=self.f_negrita)
        arbol.tag_configure("secundario", foreground=P["suave"])
        arbol.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        return arbol

    def _preparar_resumen(self) -> None:
        t = self.txt_resumen
        t.tag_configure("numero", font=self.f_numero, spacing3=2)
        t.tag_configure("suave", foreground=P["suave"])
        t.tag_configure("extracto", font=self.f_extracto, spacing3=8, lmargin1=0)
        t.tag_configure("rotulo", font=self.f_negrita, spacing1=12, spacing3=4)
        t.tag_configure("situacion", font=self.f_situacion, foreground=P["cupula_oscura"], spacing3=4)
        t.tag_configure("situacion_ambar", font=self.f_situacion, foreground=P["ambar"], spacing3=4)
        t.tag_configure("situacion_lacre", font=self.f_situacion, foreground=P["lacre"], spacing3=4)
        t.tag_configure("vineta", lmargin1=12, lmargin2=26)
        t.tag_configure("etiqueta", foreground=P["suave"])
        t.tag_configure("enlace", foreground=P["cupula_oscura"], underline=True)
        t.tag_bind("enlace", "<Enter>", lambda _e: t.configure(cursor="hand2"))
        t.tag_bind("enlace", "<Leave>", lambda _e: t.configure(cursor="arrow"))

    def _mostrar_bienvenida(self) -> None:
        t = self.txt_resumen
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", "Cómo usarlo\n", "rotulo")
        pasos = [
            "Escribí el número de expediente a la izquierda (uno por línea si son varios).",
            "Elegí qué buscar y en qué formato guardar el informe.",
            "Presioná «Generar informe». La búsqueda de reuniones puede tardar un minuto: "
            "el programa abre cada reunión publicada por las comisiones del giro.",
            "Cuando termine, el resumen aparece aquí y podés abrir el Word o el HTML.",
        ]
        for i, p in enumerate(pasos, 1):
            t.insert("end", f"{i}. {p}\n", "vineta")
        t.configure(state="disabled")

    # ----------------------------------------------------------- acciones
    def _sincronizar(self) -> None:
        self.chk_asesores.state(["!disabled"] if self.var_reuniones.get() else ["disabled"])

    def _enter_en_expedientes(self, evento):
        if evento.state & 0x4:      # Ctrl+Enter genera
            self._generar()
            return "break"
        return None

    def _elegir_carpeta(self) -> None:
        carpeta = filedialog.askdirectory(initialdir=self.var_carpeta.get() or str(Path.home()),
                                          title="Carpeta donde guardar los informes")
        if carpeta:
            self.var_carpeta.set(carpeta)

    def _opciones(self) -> Opciones:
        tipo = self.var_tipo.get()
        formatos = tuple(f for f, v in (("docx", self.var_docx), ("html", self.var_html)) if v.get())
        return Opciones(
            tipo=None if tipo == TIPO_AUTOMATICO else tipo.split(" ")[0],
            buscar_reuniones=self.var_reuniones.get(),
            incluir_asesores=self.var_asesores.get(),
            buscar_agenda=self.var_agenda.get(),
            formatos=formatos,
            carpeta_salida=Path(self.var_carpeta.get()).expanduser(),
            notas_usuario=self.txt_notas.get("1.0", "end").strip(),
        )

    def _generar(self) -> None:
        if self.hilo and self.hilo.is_alive():
            return
        textos = separar_lote(self.txt_expedientes.get("1.0", "end"))
        if not textos:
            messagebox.showinfo("Falta el expediente", "Escribí al menos un número de expediente, por ejemplo S-1234/24.")
            self.txt_expedientes.focus_set()
            return
        opciones = self._opciones()
        errores = []
        for t in textos:
            try:
                parsear(t, opciones.tipo)
            except ErrorIdentificador as e:
                errores.append(str(e))
        if errores:
            messagebox.showwarning("Revisá los números", "\n\n".join(errores))
            return
        if not opciones.formatos:
            messagebox.showinfo("Elegí un formato", "Marcá Word, HTML o ambos para guardar el informe.")
            return
        self._guardar_preferencias()
        self.cancelar.clear()
        self._registro(f"— Nueva consulta: {', '.join(textos)}")
        self._ocupado(True)
        self.hilo = threading.Thread(target=self._trabajo, args=(textos, opciones), daemon=True)
        self.hilo.start()

    def _nuevo_cliente(self) -> Cliente:
        diagnostico = None
        if self.var_diagnostico.get():
            diagnostico = config.carpeta_app() / "diagnostico" / datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return Cliente(carpeta_cache=config.carpeta_app() / "cache", usar_cache=self.var_cache.get(),
                       cancelar=self.cancelar, carpeta_diagnostico=diagnostico)

    def _ocupado(self, si: bool) -> None:
        for b in (self.btn_generar, self.btn_generar_tema, self.btn_revisar, self.btn_generar_ses):
            b.state(["disabled"] if si else ["!disabled"])
        for b in (self.btn_cancelar, self.btn_cancelar_tema, self.btn_cancelar_seg, self.btn_cancelar_ses):
            b.state(["!disabled"] if si else ["disabled"])

    def _trabajo(self, textos: list[str], opciones: Opciones) -> None:
        cliente = self._nuevo_cliente()
        hechos, fallidos = 0, []
        for i, texto in enumerate(textos, 1):
            prefijo = f"({i}/{len(textos)}) " if len(textos) > 1 else ""

            def avisar(evento, mensaje="", **datos):
                if evento == "etapa":
                    mensaje = prefijo + mensaje
                self.cola.put((evento, mensaje, datos))

            try:
                resultado = generar(texto, opciones, cliente, avisar)
                self.cola.put(("resultado", "", {"resultado": resultado}))
                hechos += 1
            except Cancelado:
                self.cola.put(("log", "Consulta cancelada.", {}))
                break
            except Exception as e:  # noqa: BLE001 - se muestra al usuario
                fallidos.append(f"{texto}: {mensaje_de_error(e)}")
                self.cola.put(("log", f"Error con {texto}: {mensaje_de_error(e)}", {}))
                self.cola.put(("log", traceback.format_exc(), {}))
        self.cola.put(("fin", "", {"hechos": hechos, "fallidos": fallidos, "carpeta": str(opciones.carpeta_salida),
                                   "pedidos": cliente.pedidos_red, "cache": cliente.pedidos_cache}))

    def _cancelar(self) -> None:
        self.cancelar.set()
        self.var_estado.set("Cancelando…")
        for b in (self.btn_cancelar, self.btn_cancelar_tema, self.btn_cancelar_seg, self.btn_cancelar_ses):
            b.state(["disabled"])

    def _procesar_cola(self) -> None:
        try:
            for _ in range(200):
                evento, mensaje, datos = self.cola.get_nowait()
                self._atender(evento, mensaje, datos)
        except queue.Empty:
            pass
        self.after(120, self._procesar_cola)

    def _atender(self, evento: str, mensaje: str, datos: dict) -> None:
        if evento == "etapa":
            self.var_estado.set(mensaje)
            self._registro(mensaje)
            if not self._contando:
                self.barra.configure(mode="indeterminate")
                self.barra.start(14)
        elif evento == "progreso":
            self._contando = True
            self.barra.stop()
            self.barra.configure(mode="determinate", maximum=max(1, datos.get("total", 1)),
                                 value=datos.get("actual", 0))
            if datos.get("actual", 0) >= datos.get("total", 1):
                self._contando = False
        elif evento in ("log", "advertencia"):
            self._registro(("Aviso: " if evento == "advertencia" else "") + mensaje)
        elif evento == "senadores":
            self._cargando_senadores = False
            self.lista_autores, self.lista_bloques = datos["autores"], datos["bloques"]
            self.combo_autor.configure(values=[CUALQUIER_AUTOR] + [f"{s.legible} ({s.id})" for s in self.lista_autores])
            self.combo_bloque.configure(values=[CUALQUIER_BLOQUE] + list(self.lista_bloques))
        elif evento == "planes":
            self.planes_publicados = datos["planes"]
            self.combo_planes.configure(values=[x.etiqueta for x in self.planes_publicados[:60]],
                                        state="readonly" if self.planes_publicados else "disabled")
            self.var_ses_fuente.set(f"Elegí un plan de la lista ({len(self.planes_publicados)} publicados)."
                                    if self.planes_publicados else "El sitio no devolvió planes de labor.")
        elif evento == "plan_texto":
            self.txt_plan.delete("1.0", "end")
            self.txt_plan.insert("1.0", datos["texto"])
            self.ses_fuente = datos["fuente"]
            self.var_ses_fuente.set(datos["etiqueta"])
        elif evento == "resultado":
            resultado = datos["resultado"]
            self.resultados.append(resultado)
            nombres = [self._nombre_resultado(r) + f" ({r.generado:%H:%M})" for r in self.resultados]
            self.combo_resultado.configure(values=nombres, state="readonly" if len(nombres) > 1 else "disabled")
            self.var_resultado.set(nombres[-1])
            self._mostrar(resultado)
        elif evento == "fin":
            self._contando = False
            self.barra.stop()
            self.barra.configure(mode="determinate", value=0)
            self._ocupado(False)
            hechos, fallidos = datos["hechos"], datos["fallidos"]
            if self.cancelar.is_set():
                self.var_estado.set("Consulta cancelada.")
            elif hechos:
                self.var_estado.set(f"Listo: {hechos} informe{'s' if hechos != 1 else ''} en {datos['carpeta']}")
                if self.resultados and isinstance(self.resultados[-1], ResultadoTematico):
                    self.var_estado.set(f"Listo: informe temático en {datos['carpeta']}")
                if self.resultados and isinstance(self.resultados[-1], ResultadoSesion):
                    self.var_estado.set(f"Listo: informe de sesión en {datos['carpeta']}")
                if self.resultados and isinstance(self.resultados[-1], ResultadoSeguimiento):
                    self.var_estado.set(f"Listo: {resumen_seguimiento(self.resultados[-1])}")
                    self._llenar_seguimiento()
            else:
                self.var_estado.set("No se pudo generar el informe. Mirá el detalle en «Registro».")
            self._registro(f"Pedidos al sitio: {datos['pedidos']} · desde caché: {datos['cache']}")
            if fallidos:
                messagebox.showwarning("Algunos informes no se generaron", "\n\n".join(fallidos))

    # ---------------------------------------------------- mostrar resultado
    def _elegir_resultado(self, _evento=None) -> None:
        i = self.combo_resultado.current()
        if 0 <= i < len(self.resultados):
            self._mostrar(self.resultados[i])

    def _pestanias_visibles(self, tematico: bool) -> None:
        self.pestanias.tab(self.arbol_expedientes.master, state="normal" if tematico else "hidden")
        for widget in (self.arbol_reuniones.master, self.arbol_tramite.master):
            self.pestanias.tab(widget, state="hidden" if tematico else "normal")

    def _mostrar(self, r) -> None:
        self.actual = r
        if isinstance(r, ResultadoTematico):
            self._mostrar_tematico(r)
            return
        if isinstance(r, ResultadoSeguimiento):
            self._mostrar_seguimiento(r)
            return
        if isinstance(r, ResultadoSesion):
            self._mostrar_sesion(r)
            return
        self._pestanias_visibles(False)
        self.btn_excel.state(["disabled"])
        self._escribir_resumen(r)
        self._llenar_reuniones(r)
        self._llenar_tramite(r)
        self.btn_word.state(["!disabled"] if "docx" in r.archivos else ["disabled"])
        self.btn_html.state(["!disabled"] if "html" in r.archivos else ["disabled"])
        self.btn_ficha.state(["!disabled"])
        self.btn_copiar.state(["!disabled"])
        self.pestanias.select(0)

    def _mostrar_tematico(self, r: ResultadoTematico) -> None:
        self._pestanias_visibles(True)
        t = self.txt_resumen
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._enlaces.clear()
        t.insert("end", "Informe temático\n", "suave")
        t.insert("end", r.consulta.titulo() + "\n", "numero")
        t.insert("end", resumen(r) + "\n", "extracto")
        if r.items:
            t.insert("end", resumen_tipos(r) + "\n", "suave")
        if r.detallados:
            t.insert("end", "Por etapa\n", "rotulo")
            for nivel, k in r.conteo_etapas():
                t.insert("end", f"• {ETAPA[nivel]}: {k}\n", "vineta")
        t.insert("end", "Criterios de búsqueda\n", "rotulo")
        for clave, valor in r.consulta.criterios():
            t.insert("end", f"{clave}: ", ("vineta", "etiqueta"))
            t.insert("end", valor + "\n")
        if r.items:
            t.insert("end", "\nLa lista completa está en la pestaña «Expedientes».\n", ("vineta", "suave"))
        if r.advertencias:
            t.insert("end", "Avisos\n", "rotulo")
            for a in r.advertencias:
                t.insert("end", f"• {a}\n", ("vineta", "suave"))
        t.configure(state="disabled")
        a = self.arbol_expedientes
        a.delete(*a.get_children())
        for i, it in enumerate(r.items):
            ident = it.hallazgo.ident
            situacion = it.situacion.titulo if it.situacion else ETAPA[it.nivel]
            a.insert("", "end", iid=str(i), values=(ident.corto, ident.tipo or "—", situacion, it.hallazgo.extracto))
        for formato, boton in (("docx", self.btn_word), ("html", self.btn_html), ("xlsx", self.btn_excel)):
            boton.state(["!disabled"] if formato in r.archivos else ["disabled"])
        self.btn_ficha.state(["disabled"])
        self.btn_copiar.state(["!disabled"])
        self.pestanias.select(self.arbol_expedientes.master if r.items else 0)

    @staticmethod
    def _nombre_resultado(r) -> str:
        if isinstance(r, ResultadoTematico):
            return f"Tema: {r.consulta.titulo()[:24]}"
        if isinstance(r, ResultadoSeguimiento):
            return "Seguimiento"
        if isinstance(r, ResultadoSesion):
            return f"Sesión {r.fecha:%d/%m}" if r.fecha else "Sesión"
        return r.ficha.id.corto

    def _mostrar_seguimiento(self, r: ResultadoSeguimiento) -> None:
        self._pestanias_visibles(True)
        self.pestanias.tab(self.arbol_expedientes.master, state="hidden")
        t = self.txt_resumen
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._enlaces.clear()
        t.insert("end", f"Revisión del {r.generado:%d/%m/%Y, %H:%M} h\n", "suave")
        t.insert("end", "Seguimiento de expedientes\n", "numero")
        t.insert("end", resumen_seguimiento(r) + "\n", "extracto")
        for rev in r.con_novedades:
            self._enlace(rev.seguido.expediente, rev.url, "rotulo")
            t.insert("end", "\n", "rotulo")
            if rev.situacion:
                t.insert("end", rev.situacion + "\n", "suave")
            for n in rev.novedades:
                t.insert("end", "• " + n.texto, "vineta")
                if n.url:
                    t.insert("end", "  ")
                    self._enlace("ver", n.url)
                t.insert("end", "\n")
        sin = [rev for rev in r.revisiones if not rev.novedades]
        if sin:
            t.insert("end", "Sin novedades\n", "rotulo")
            for rev in sin:
                t.insert("end", f"{rev.seguido.expediente}: ", ("vineta", "etiqueta"))
                t.insert("end", rev.situacion + "\n")
        t.configure(state="disabled")
        for formato, boton in (("docx", self.btn_word), ("html", self.btn_html), ("xlsx", self.btn_excel)):
            boton.state(["!disabled"] if formato in r.archivos else ["disabled"])
        self.btn_ficha.state(["disabled"])
        self.btn_copiar.state(["!disabled"])
        self.pestanias.select(0)

    # ------------------------------------------------------------ sesión
    def _abrir_plan(self) -> None:
        ruta = filedialog.askopenfilename(title="Plan de labor", filetypes=[
            ("Plan de labor", "*.docx *.pdf *.txt"), ("Word", "*.docx"), ("PDF", "*.pdf"), ("Texto", "*.txt"),
            ("Todos los archivos", "*.*")])
        if not ruta:
            return
        try:
            texto = plan_labor.texto_de_archivo(Path(ruta))
            if ruta.lower().endswith(".pdf"):
                texto = plan_labor.texto_legible(texto)
        except (plan_labor.ErrorPlan, OSError) as e:
            messagebox.showwarning("No se pudo leer el plan", str(e))
            return
        self.plan_publicado = None
        self._atender("plan_texto", "", {"texto": texto, "fuente": ruta, "etiqueta": f"Archivo: {Path(ruta).name}"})

    def _buscar_planes(self) -> None:
        if self.hilo and self.hilo.is_alive():
            return
        self.var_ses_fuente.set("Buscando los planes publicados en el sitio del Senado…")

        def trabajo():
            try:
                self.cola.put(("planes", "", {"planes": plan_labor.planes_publicados(self._nuevo_cliente())}))
            except Exception as e:  # noqa: BLE001
                self.cola.put(("log", f"No se pudo leer el Plenario de Labor: {mensaje_de_error(e)}", {}))
                self.cola.put(("planes", "", {"planes": []}))

        self.hilo = threading.Thread(target=trabajo, daemon=True)
        self.hilo.start()

    def _elegir_plan_publicado(self, _evento=None) -> None:
        i = self.combo_planes.current()
        if not 0 <= i < len(self.planes_publicados) or (self.hilo and self.hilo.is_alive()):
            return
        elegido = self.planes_publicados[i]
        self.var_ses_fuente.set("Descargando el plan de labor…")

        def trabajo():
            try:
                r = self._nuevo_cliente().get(elegido.url, binario=True)
                texto = plan_labor.texto_legible(plan_labor.texto_de_pdf(r.contenido or b""))
                self.plan_publicado = elegido
                self.cola.put(("plan_texto", "", {"texto": texto, "fuente": elegido.url,
                                                  "etiqueta": f"Del sitio: {elegido.etiqueta}"}))
            except Exception as e:  # noqa: BLE001
                self.cola.put(("log", f"No se pudo bajar el plan: {mensaje_de_error(e)}", {}))
                self.var_ses_fuente.set("No se pudo bajar el plan: mirá el detalle en «Registro».")

        self.hilo = threading.Thread(target=trabajo, daemon=True)
        self.hilo.start()

    def _plan_actual(self):
        texto = self.txt_plan.get("1.0", "end").strip()
        if not texto:
            messagebox.showinfo("Falta el plan", "Abrí el plan de labor, buscalo en el sitio o pegá su texto.")
            return None
        plan = plan_labor.leer(texto, self.ses_fuente)
        if self.plan_publicado is not None and self.ses_fuente == self.plan_publicado.url:
            plan.fecha_reunion = plan.fecha_reunion or self.plan_publicado.fecha_reunion
            plan.fecha_sesion = plan.fecha_sesion or self.plan_publicado.fecha_sesion
        if not plan.asuntos:
            messagebox.showinfo("Sin asuntos", "No se encontraron asuntos en el texto del plan.")
            return None
        return plan

    def _vista_previa_sesion(self) -> None:
        plan = self._plan_actual()
        if plan is None:
            return
        self._pestanias_visibles(True)
        self.pestanias.tab(self.arbol_expedientes.master, state="hidden")
        t = self.txt_resumen
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._enlaces.clear()
        t.insert("end", "Vista previa del plan de labor\n", "suave")
        fecha = plan.fecha_sesion or plan.fecha_reunion
        t.insert("end", (f"Sesión del {fecha:%d/%m/%Y}" if fecha else "Sesión") + "\n", "numero")
        t.insert("end", f"{len(plan.asuntos)} asuntos, en el orden de tratamiento:\n", "extracto")
        for a in plan.asuntos:
            refs = ", ".join(r.clave for r in a.referencias[:8]) + (" …" if len(a.referencias) > 8 else "")
            t.insert("end", f"{a.orden}. ", ("vineta", "etiqueta"))
            t.insert("end", (a.titulo or "(sin título en el plan)") + (f"  —  {refs}" if refs else ""), "vineta")
            if a.seccion != "Temas acordados":
                t.insert("end", f"  ({a.seccion.lower()})", ("vineta", "suave"))
            t.insert("end", "\n")
        t.insert("end", "\nSi falta o sobra algo, corregí el texto del plan y volvé a mirar.\n", ("vineta", "suave"))
        t.configure(state="disabled")
        self.pestanias.select(0)

    def _generar_sesion(self) -> None:
        if self.hilo and self.hilo.is_alive():
            return
        plan = self._plan_actual()
        if plan is None:
            return
        formatos = tuple(f for f, v in self.vars_ses_formatos.items() if v.get())
        if not formatos:
            messagebox.showinfo("Formato", "Marcá al menos un formato.")
            return
        opciones = OpcionesSesion(buscar_reuniones=self.var_ses_reuniones.get(), incluir_asesores=self.var_asesores.get(),
                                  formatos=formatos, carpeta_salida=Path(self.var_carpeta.get()).expanduser())
        self._guardar_preferencias()
        self.cancelar.clear()
        self._registro(f"— Informe de sesión: {len(plan.asuntos)} asuntos")
        self._ocupado(True)
        self.hilo = threading.Thread(target=self._trabajo_sesion, args=(plan, opciones), daemon=True)
        self.hilo.start()

    def _trabajo_sesion(self, plan, opciones: OpcionesSesion) -> None:
        cliente = self._nuevo_cliente()
        hechos, fallidos = 0, []

        def avisar(evento, mensaje="", **datos):
            self.cola.put((evento, mensaje, datos))

        try:
            res = generar_sesion(plan, opciones, cliente, avisar)
            self.cola.put(("resultado", "", {"resultado": res}))
            hechos = 1
        except Cancelado:
            self.cola.put(("log", "Informe de sesión cancelado.", {}))
        except Exception as e:  # noqa: BLE001
            fallidos.append(mensaje_de_error(e))
            self.cola.put(("log", traceback.format_exc(), {}))
        self.cola.put(("fin", "", {"hechos": hechos, "fallidos": fallidos, "carpeta": str(opciones.carpeta_salida),
                                   "pedidos": cliente.pedidos_red, "cache": cliente.pedidos_cache}))

    def _mostrar_sesion(self, r: ResultadoSesion) -> None:
        self._pestanias_visibles(True)
        self.pestanias.tab(self.arbol_expedientes.master, state="hidden")
        t = self.txt_resumen
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._enlaces.clear()
        t.insert("end", "Informe de sesión\n", "suave")
        t.insert("end", (f"{r.fecha:%d/%m/%Y}" if r.fecha else "Sesión") + "\n", "numero")
        t.insert("end", resumen_sesion(r) + "\n", "extracto")
        t.insert("end", "Asuntos en el orden de tratamiento\n", "rotulo")
        for tema in r.temas:
            t.insert("end", f"{tema.asunto.orden}. ", ("vineta", "etiqueta"))
            t.insert("end", tema.titulo, "vineta")
            if etiqueta_referencias(tema):
                t.insert("end", f"  ({etiqueta_referencias(tema)})", ("vineta", "suave"))
            t.insert("end", "\n")
            for res in tema.resultados:
                t.insert("end", "      ")
                self._enlace(res.ficha.id.corto, res.ficha.url)
                t.insert("end", f": {res.situacion.titulo}\n", "vineta")
            for error in tema.errores:
                t.insert("end", f"      {error}\n", ("vineta", "suave"))
        if r.advertencias:
            t.insert("end", "Avisos\n", "rotulo")
            for a in r.advertencias:
                t.insert("end", f"• {a}\n", ("vineta", "suave"))
        t.configure(state="disabled")
        for formato, boton in (("docx", self.btn_word), ("html", self.btn_html), ("xlsx", self.btn_excel)):
            boton.state(["!disabled"] if formato in r.archivos else ["disabled"])
        self.btn_ficha.state(["disabled"])
        self.btn_copiar.state(["!disabled"])
        self.pestanias.select(0)

    # ------------------------------------------------------- seguimiento
    def _llenar_seguimiento(self) -> None:
        a = self.arbol_seguimiento
        a.delete(*a.get_children())
        for s in self.lista_seguimiento.seguidos:
            a.insert("", "end", iid=s.expediente,
                     values=(s.expediente, (s.foto or {}).get("situacion", "sin revisar todavía")))

    def _sumar_a_seguimiento(self, texto: str, tipo: str | None = None) -> bool:
        try:
            s, nuevo = self.lista_seguimiento.agregar(texto, tipo)
            self.lista_seguimiento.guardar()
        except ErrorIdentificador as e:
            messagebox.showwarning("Revisá el número", str(e))
            return False
        except OSError as e:
            messagebox.showerror("No se pudo guardar la lista", str(e))
            return False
        self._llenar_seguimiento()
        self.var_estado.set(f"{s.expediente} {'se agregó a' if nuevo else 'ya estaba en'} la lista de seguimiento.")
        return True

    def _agregar_seguimiento(self) -> None:
        textos = separar_lote(self.var_seg_nuevo.get().replace(",", "\n"))
        if textos and all(self._sumar_a_seguimiento(x) for x in textos):
            self.var_seg_nuevo.set("")

    def _quitar_seguimiento(self) -> None:
        elegidos = self.arbol_seguimiento.selection()
        if not elegidos:
            return
        for corto in elegidos:
            self.lista_seguimiento.quitar(corto)
        self.lista_seguimiento.guardar()
        self._llenar_seguimiento()

    def _ficha_seguimiento(self) -> None:
        elegidos = self.arbol_seguimiento.selection()
        s = next((x for x in self.lista_seguimiento.seguidos if elegidos and x.expediente == elegidos[0]), None)
        if s and s.foto and s.foto.get("url"):
            webbrowser.open(s.foto["url"])
        elif s:
            messagebox.showinfo("Sin revisar", "Todavía no se revisó este expediente: presioná «Revisar novedades».")

    def _revisar_seguimiento(self) -> None:
        if self.hilo and self.hilo.is_alive():
            return
        if not self.lista_seguimiento.seguidos:
            messagebox.showinfo("Lista vacía", "Agregá al menos un expediente a la lista de seguimiento.")
            return
        opciones = OpcionesSeguimiento(buscar_reuniones=self.var_seg_reuniones.get(),
                                       incluir_asesores=self.var_asesores.get(),
                                       carpeta_salida=Path(self.var_carpeta.get()).expanduser())
        self._guardar_preferencias()
        self.cancelar.clear()
        self._registro(f"— Revisión de la lista de seguimiento ({len(self.lista_seguimiento.seguidos)} expedientes)")
        self._ocupado(True)
        self.hilo = threading.Thread(target=self._trabajo_seguimiento, args=(opciones,), daemon=True)
        self.hilo.start()

    def _trabajo_seguimiento(self, opciones: OpcionesSeguimiento) -> None:
        cliente = self._nuevo_cliente()
        hechos, fallidos = 0, []

        def avisar(evento, mensaje="", **datos):
            self.cola.put((evento, mensaje, datos))

        try:
            res = revisar(self.lista_seguimiento, cliente, opciones, avisar)
            self.cola.put(("resultado", "", {"resultado": res}))
            hechos = 1
        except Cancelado:
            self.cola.put(("log", "Revisión cancelada.", {}))
        except Exception as e:  # noqa: BLE001
            fallidos.append(mensaje_de_error(e))
            self.cola.put(("log", traceback.format_exc(), {}))
        self.cola.put(("fin", "", {"hechos": hechos, "fallidos": fallidos, "carpeta": str(opciones.carpeta_salida),
                                   "pedidos": cliente.pedidos_red, "cache": cliente.pedidos_cache}))

    def _expediente_elegido(self):
        if not isinstance(self.actual, ResultadoTematico):
            return None
        sel = self.arbol_expedientes.selection()
        return self.actual.items[int(sel[0])] if sel else None

    def _menu_expedientes(self, evento) -> None:
        fila = self.arbol_expedientes.identify_row(evento.y)
        if fila:
            self.arbol_expedientes.selection_set(fila)
            self.menu_expediente.tk_popup(evento.x_root, evento.y_root)

    def _accion_expediente(self, que: str) -> None:
        it = self._expediente_elegido()
        if not it:
            return
        ident = it.hallazgo.ident
        if que == "ficha":
            webbrowser.open(it.url)
        elif que == "copiar":
            self.clipboard_clear()
            self.clipboard_append(ident.corto)
        elif que == "seguir":
            self._sumar_a_seguimiento(ident.corto, ident.tipo)
        elif que == "informe":
            if self.hilo and self.hilo.is_alive():
                messagebox.showinfo("Consulta en curso", "Esperá a que termine la consulta actual.")
                return
            self.modos.select(0)
            self.txt_expedientes.delete("1.0", "end")
            self.txt_expedientes.insert("1.0", ident.corto)
            opcion = next((o for o in OPCIONES_TIPO if ident.tipo and o.startswith(ident.tipo + " ")), TIPO_AUTOMATICO)
            self.var_tipo.set(opcion)
            self._generar()

    # ------------------------------------------------------- modo temático
    def _actualizar_combo_ejes(self) -> None:
        self.combo_eje.configure(values=[SIN_EJE] + [e.nombre for e in self.ejes])

    def _eje_elegido(self, _evento=None) -> None:
        eje = buscar_eje(self.var_eje.get(), self.ejes)
        if not eje:
            return
        self.var_palabras.set(", ".join(eje.palabras))
        self.var_excluir.set(", ".join(eje.excluir))
        self.var_modo.set(eje.modo)
        nombre = nombre_comision(config.COMISIONES.get(eje.comision_id, "")) if eje.comision_id else ""
        self.var_comision.set(nombre if nombre in self.comisiones_por_nombre else CUALQUIER_COMISION)

    def _guardar_eje(self) -> None:
        palabras = separar_palabras(self.var_palabras.get())
        if not palabras:
            messagebox.showinfo("Sin palabras", "Escribí las palabras clave del eje antes de guardarlo.")
            return
        actual = self.var_eje.get()
        nombre = simpledialog.askstring("Guardar eje temático", "Nombre del eje:", parent=self,
                                        initialvalue="" if actual == SIN_EJE else actual)
        if not nombre or not nombre.strip():
            return
        nombre = nombre.strip()
        nuevo = Eje(nombre, palabras, self.var_modo.get(), separar_palabras(self.var_excluir.get()),
                    self.comisiones_por_nombre.get(self.var_comision.get()))
        existente = buscar_eje(nombre, self.ejes)
        if existente and not messagebox.askyesno("Reemplazar eje", f"Ya existe el eje «{nombre}». ¿Reemplazarlo?"):
            return
        self.ejes = [e for e in self.ejes if e is not existente] + [nuevo]
        guardar_ejes(self.ejes)
        self._actualizar_combo_ejes()
        self.var_eje.set(nombre)

    def _borrar_eje(self) -> None:
        eje = buscar_eje(self.var_eje.get(), self.ejes)
        if not eje:
            return
        if messagebox.askyesno("Borrar eje", f"¿Borrar el eje «{eje.nombre}»?"):
            self.ejes = [e for e in self.ejes if e is not eje]
            guardar_ejes(self.ejes)
            self._actualizar_combo_ejes()
            self.var_eje.set(SIN_EJE)

    def _cargar_senadores(self) -> None:
        """Al abrir la lista de autores o de bloques, la trae del sitio (una vez por sesión)."""
        if self.lista_autores or self._cargando_senadores:
            return
        self._cargando_senadores = True
        self.combo_autor.configure(values=[CARGANDO])
        self.combo_bloque.configure(values=[CARGANDO])

        def trabajo():
            try:
                cliente = self._nuevo_cliente()
                todos = senadores.bloques(cliente)
                self.cola.put(("senadores", "", {"autores": senadores.con_integrantes(senadores.autores(cliente), todos),
                                                 "bloques": todos}))
            except Exception as e:  # noqa: BLE001
                self.cola.put(("log", f"No se pudo traer la lista de senadores: {mensaje_de_error(e)}", {}))
                self.cola.put(("senadores", "", {"autores": [], "bloques": {}}))

        threading.Thread(target=trabajo, daemon=True).start()

    def _autores_elegidos(self):
        """(autores, bloque) elegidos; (None, None) si lo escrito no se puede resolver."""
        bloque = self.var_bloque.get()
        if bloque and bloque not in (CUALQUIER_BLOQUE, CARGANDO) and bloque in self.lista_bloques:
            return list(self.lista_bloques[bloque]), bloque
        texto = self.var_autor.get().strip()
        if not texto or texto in (CUALQUIER_AUTOR, CARGANDO):
            return [], None
        if not self.lista_autores:
            messagebox.showinfo("Autor", "Abrí la lista de autores para traerla del sitio y elegí el senador.")
            return None, None
        elegido = next((s for s in self.lista_autores if f"{s.legible} ({s.id})" == texto), None)
        hallados = [elegido] if elegido else senadores.buscar_senador(texto, self.lista_autores)
        if len(hallados) != 1:
            opciones = "\n".join(f"{s.legible} ({s.id})" for s in hallados[:12])
            messagebox.showinfo("Autor", f"«{texto}» coincide con {len(hallados)} senadores."
                                         + (f"\n\n{opciones}\n\nElegí uno de la lista." if hallados else
                                            " Revisá el apellido."))
            return None, None
        return hallados, None

    def _generar_tematico(self) -> None:
        if self.hilo and self.hilo.is_alive():
            return
        palabras = separar_palabras(self.var_palabras.get())
        comision_id = self.comisiones_por_nombre.get(self.var_comision.get())
        autores, bloque = self._autores_elegidos()
        if autores is None:
            return
        if not palabras and not comision_id and not autores:
            messagebox.showinfo("Falta el tema", "Elegí un eje, escribí al menos una palabra clave, o elegí una "
                                                 "comisión, un senador o un bloque.")
            return
        try:
            desde, hasta = int(self.var_desde.get()), int(self.var_hasta.get())
        except ValueError:
            messagebox.showwarning("Años", "Los años tienen que ser números, por ejemplo 2025 y 2026.")
            return
        hoy = datetime.now().year
        if not 1983 <= desde <= hasta <= hoy:
            messagebox.showwarning("Años", f"Revisá los años: entre 1983 y {hoy}, y el primero no mayor que el segundo.")
            return
        tipos = {codigo for codigo, var in self.vars_tipos.items() if var.get()}
        if not tipos:
            messagebox.showinfo("Tipos", "Marcá al menos un tipo de proyecto.")
            return
        formatos = tuple(f for f, v in (("docx", self.var_t_docx), ("html", self.var_t_html),
                                        ("xlsx", self.var_t_xlsx)) if v.get())
        if not formatos:
            messagebox.showinfo("Formato", "Marcá Word, HTML o Excel.")
            return
        consultas = (hasta - desde + 1) * max(1, len(palabras) if self.var_modo.get() == "alguna" else 1)
        if consultas > 24 and not messagebox.askyesno(
                "Búsqueda amplia", f"La búsqueda hace unas {consultas} consultas al sitio y puede tardar varios "
                                   "minutos. ¿Continuar?"):
            return
        origen = self.var_origen.get()
        eje = self.var_eje.get()
        consulta = Consulta(
            palabras=palabras, modo=self.var_modo.get(), excluir=separar_palabras(self.var_excluir.get()),
            anio_desde=desde, anio_hasta=hasta, origen=None if origen == TODOS_ORIGENES else origen.split(" ")[0],
            tipos=None if tipos == {c for c, _ in TIPOS_TEMA} else tipos, comision_id=comision_id,
            eje=None if eje == SIN_EJE or not buscar_eje(eje, self.ejes) else eje,
            autores=autores, bloque=bloque,
        )
        opciones = OpcionesTematicas(
            detallar=self.var_detallar.get() or self.var_reuniones_tema.get() or self.var_individuales.get(),
            buscar_reuniones=self.var_reuniones_tema.get(), informes_individuales=self.var_individuales.get(),
            formatos=formatos, carpeta_salida=Path(self.var_carpeta.get()).expanduser(),
        )
        self._guardar_preferencias()
        self.cancelar.clear()
        self._registro(f"— Nueva búsqueda temática: {consulta.titulo()}")
        self._ocupado(True)
        self.hilo = threading.Thread(target=self._trabajo_tematico, args=(consulta, opciones), daemon=True)
        self.hilo.start()

    def _trabajo_tematico(self, consulta: Consulta, opciones: OpcionesTematicas) -> None:
        cliente = self._nuevo_cliente()
        hechos, fallidos = 0, []

        def avisar(evento, mensaje="", **datos):
            self.cola.put((evento, mensaje, datos))

        try:
            res = generar_tematico(consulta, opciones, cliente, avisar)
            self.cola.put(("resultado", "", {"resultado": res}))
            hechos = 1
        except Cancelado:
            self.cola.put(("log", "Consulta cancelada.", {}))
        except Exception as e:  # noqa: BLE001
            fallidos.append(mensaje_de_error(e))
            self.cola.put(("log", traceback.format_exc(), {}))
        self.cola.put(("fin", "", {"hechos": hechos, "fallidos": fallidos, "carpeta": str(opciones.carpeta_salida),
                                   "pedidos": cliente.pedidos_red, "cache": cliente.pedidos_cache}))

    def _enlace(self, texto: str, url: str | None, estilo: str | None = None) -> None:
        t = self.txt_resumen
        if not url:
            t.insert("end", texto, estilo or ())
            return
        etiqueta = f"enlace{len(self._enlaces)}"
        self._enlaces[etiqueta] = url
        t.insert("end", texto, ((estilo,) if estilo else ()) + ("enlace", etiqueta))
        t.tag_bind(etiqueta, "<Button-1>", lambda _e, u=url: webbrowser.open(u))

    def _escribir_resumen(self, r) -> None:
        f, s = r.ficha, r.situacion
        t = self.txt_resumen
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._enlaces.clear()
        t.insert("end", f.id.corto + "\n", "numero")
        t.insert("end", descripcion(f) + "\n", "suave")
        if f.extracto:
            t.insert("end", f.extracto + "\n", "extracto")
        t.insert("end", "Situación actual\n", "rotulo")
        color = COLOR_NIVEL.get(s.nivel)
        t.insert("end", s.titulo + "\n", f"situacion_{color}" if color else "situacion")
        for d in s.detalle:
            t.insert("end", f"• {d}\n", "vineta")
        for d in s.contraste:
            t.insert("end", f"• {d}\n", ("vineta", "suave"))
        if s.pasos:
            linea = "   ".join(f"{MARCA_PASO[p.estado]} {p.nombre}" for p in s.pasos)
            t.insert("end", linea + "\n", ("vineta", "suave"))
        if s.caducidad:
            etiqueta = "Caducidad registrada" if s.caducidad.registrada else "Caducidad estimada"
            t.insert("end", f"{etiqueta}: {fmt_fecha(s.caducidad.fecha)}. ", "vineta")
            t.insert("end", s.caducidad.fundamento + "\n", ("vineta", "suave"))

        t.insert("end", "Datos del expediente\n", "rotulo")
        for etiqueta, linea in datos_generales(f):
            t.insert("end", f"{etiqueta}: ", ("vineta", "etiqueta"))
            for fragmento in linea:
                self._enlace(fragmento.texto, fragmento.url)
            t.insert("end", "\n")
        dip = datos_diputados(f) + datos_diputados_hcdn(r)
        if dip:
            t.insert("end", titulo_etapa_diputados(r) + "\n", "rotulo")
            for etiqueta, linea in dip:
                t.insert("end", f"{etiqueta}: ", ("vineta", "etiqueta"))
                for fragmento in linea:
                    self._enlace(fragmento.texto, fragmento.url)
                t.insert("end", "\n")

        t.insert("end", f"Reuniones de comisión en que se trató ({len(r.reuniones)})\n", "rotulo")
        if not r.reuniones:
            t.insert("end", "No se encontraron reuniones publicadas.\n" if r.busqueda.realizada
                     else "No se buscaron reuniones.\n", ("vineta", "suave"))
        for reunion in r.reuniones:
            t.insert("end", f"{fmt_fecha(reunion.fecha)}  ", "vineta")
            self._enlace(reunion.titulo, reunion.url)
            t.insert("end", f"  ({reunion.tipo})")
            for d in reunion.versiones:
                t.insert("end", "  ")
                self._enlace("VT", d.url)
            for v in reunion.videos:
                t.insert("end", "  ")
                self._enlace("Video", v)
            t.insert("end", "\n")
        if r.relacionados:
            t.insert("end", f"Expedientes relacionados ({len(r.relacionados)})\n", "rotulo")
            for e, rel, sit in filas_relacionados(r):
                t.insert("end", "", "vineta")
                self._enlace(e.texto, e.url)
                t.insert("end", f"  {rel}. {sit}\n", "vineta")
        sesiones = sesiones_votadas(r)
        if sesiones:
            t.insert("end", "Votaciones en el recinto\n", "rotulo")
            for sv in sesiones:
                t.insert("end", f"{sv.fecha}  ", ("vineta", "etiqueta"))
                t.insert("end", " ".join(sv.lineas), "vineta")
                for fr in sv.enlaces:
                    t.insert("end", "  ")
                    self._enlace(fr.texto, fr.url)
                t.insert("end", "\n")
        if r.convocadas:
            t.insert("end", "Próximas reuniones convocadas\n", "rotulo")
            for c in r.convocadas:
                t.insert("end", f"{fmt_fecha(c.fecha, c.fecha_texto)} {c.hora}  ", "vineta")
                self._enlace(f"{c.titulo} ({c.comision})", c.url)
                t.insert("end", "\n")
        if r.advertencias:
            t.insert("end", "Avisos\n", "rotulo")
            for a in r.advertencias:
                t.insert("end", f"• {a}\n", ("vineta", "suave"))
        t.configure(state="disabled")

    def _llenar_reuniones(self, r) -> None:
        a = self.arbol_reuniones
        a.delete(*a.get_children())
        for i, reunion in enumerate(r.reuniones):
            docs = []
            if reunion.versiones:
                docs.append("VT")
            if reunion.videos:
                docs.append("video")
            if reunion.otros_archivos:
                docs.append(f"{len(reunion.otros_archivos)} archivo(s)")
            titulo = reunion.titulo + (f"  ·  {comisiones_texto(reunion.comisiones)}" if reunion.comisiones else "")
            a.insert("", "end", iid=str(i), values=(fmt_fecha(reunion.fecha), titulo, reunion.tipo,
                                                     ", ".join(docs) or "—"))

    def _llenar_tramite(self, r) -> None:
        a = self.arbol_tramite
        a.delete(*a.get_children())
        self._urls_tramite: dict[str, str] = {}
        f = r.ficha
        if f.giros:
            g_id = a.insert("", "end", text="", values=("Giros a comisiones", "", ""), open=True, tags=("grupo",))
            for g in f.giros:
                a.insert(g_id, "end", values=(f"{nombre_comision(g.comision)} (orden {g.orden or '—'})",
                                              fmt_fecha(g.ingreso), fmt_fecha(g.egreso, "en curso")))
        if f.ordenes_del_dia:
            o_id = a.insert("", "end", values=("Órdenes del Día del Senado", "", ""), open=True, tags=("grupo",))
            for od in f.ordenes_del_dia:
                iid = a.insert(o_id, "end", values=(f"N° {od.numero}", fmt_fecha(od.fecha), od.estado.capitalize()))
                if od.url_pdf or od.url:
                    self._urls_tramite[iid] = od.url_pdf or od.url
        sesiones = sesiones_votadas(r)
        if sesiones:
            v_id = a.insert("", "end", values=("Votaciones en el recinto", "", ""), open=True, tags=("grupo",))
            for sv in sesiones:
                iid = a.insert(v_id, "end", values=(" ".join(sv.lineas), sv.fecha, ""))
                if sv.enlaces:
                    self._urls_tramite[iid] = sv.enlaces[0].url
        if r.diputados is not None and r.diputados.tramite:
            d_id = a.insert("", "end", values=("Trámite según el sitio de Diputados", "", ""), open=False,
                            tags=("grupo",))
            for m in r.diputados.tramite:
                iid = a.insert(d_id, "end", values=(f"{m.camara}: {m.movimiento.rstrip(' -')}", fmt_fecha(m.fecha, ""),
                                                    m.resultado.capitalize()))
                self._urls_tramite[iid] = r.diputados.url
        if r.convocadas:
            c_id = a.insert("", "end", values=("Reuniones convocadas", "", ""), open=True, tags=("grupo",))
            for c in r.convocadas:
                iid = a.insert(c_id, "end", values=(f"{c.titulo} ({c.comision})",
                                                    f"{fmt_fecha(c.fecha, c.fecha_texto)} {c.hora}", c.lugar))
                self._urls_tramite[iid] = c.url
        for h in f.hitos + f.observaciones + f.anotaciones:
            if not a.exists("obs"):
                a.insert("", "end", iid="obs", values=("Hitos y observaciones de la ficha", "", ""), open=True,
                         tags=("grupo",))
            a.insert("obs", "end", values=(h, "", ""), tags=("secundario",))

    def _reunion_elegida(self):
        if not self.actual:
            return None
        sel = self.arbol_reuniones.selection()
        if not sel:
            return None
        return self.actual.reuniones[int(sel[0])]

    def _abrir_reunion(self, que: str) -> None:
        reunion = self._reunion_elegida()
        if not reunion:
            return
        if que == "nota":
            webbrowser.open(reunion.url)
        elif que == "vt":
            if reunion.versiones:
                webbrowser.open(reunion.versiones[0].url)
            else:
                messagebox.showinfo("Sin versión taquigráfica", "Esta reunión no tiene versión taquigráfica publicada.")
        elif que == "video":
            if reunion.videos:
                webbrowser.open(reunion.videos[0])
            else:
                messagebox.showinfo("Sin video", "Esta reunión no tiene video enlazado en su nota.")
        elif que == "copiar":
            self.clipboard_clear()
            self.clipboard_append(reunion.url)

    def _menu_contextual(self, evento) -> None:
        fila = self.arbol_reuniones.identify_row(evento.y)
        if fila:
            self.arbol_reuniones.selection_set(fila)
            self.menu_reunion.tk_popup(evento.x_root, evento.y_root)

    def _abrir_tramite(self, _evento=None) -> None:
        sel = self.arbol_tramite.selection()
        if sel and sel[0] in getattr(self, "_urls_tramite", {}):
            webbrowser.open(self._urls_tramite[sel[0]])

    def _abrir(self, formato: str) -> None:
        if self.actual and formato in self.actual.archivos:
            try:
                abrir_en_sistema(self.actual.archivos[formato])
            except OSError as e:
                messagebox.showerror("No se pudo abrir", str(e))

    def _ver_ficha(self) -> None:
        if self.actual:
            webbrowser.open(self.actual.ficha.url)

    def _copiar(self) -> None:
        if self.actual:
            self.clipboard_clear()
            if isinstance(self.actual, ResultadoTematico):
                texto = texto_resumen_tematico(self.actual)
            elif isinstance(self.actual, ResultadoSeguimiento):
                texto = markdown(self.actual)
            elif isinstance(self.actual, ResultadoSesion):
                texto = resumen_sesion(self.actual) + "\n\n" + "\n".join(
                    f"{x.asunto.orden}. {x.titulo} ({etiqueta_referencias(x) or 'sin número'}): "
                    + ("; ".join(f"{y.ficha.id.corto}: {y.situacion.titulo}" for y in x.resultados) or "—")
                    for x in self.actual.temas)
            else:
                texto = texto_resumen(self.actual)
            self.clipboard_append(texto)
            self.var_estado.set("Resumen copiado al portapapeles.")

    def _abrir_carpeta(self) -> None:
        carpeta = Path(self.var_carpeta.get()).expanduser()
        carpeta.mkdir(parents=True, exist_ok=True)
        abrir_en_sistema(carpeta)

    def _abrir_diagnostico(self) -> None:
        carpeta = config.carpeta_app() / "diagnostico"
        carpeta.mkdir(parents=True, exist_ok=True)
        abrir_en_sistema(carpeta)

    def _vaciar_cache(self) -> None:
        borrados = Cliente(carpeta_cache=config.carpeta_app() / "cache").vaciar_cache()
        messagebox.showinfo("Caché", f"Se borraron {borrados} páginas guardadas.")

    def _registro(self, mensaje: str) -> None:
        t = self.txt_registro
        t.configure(state="normal")
        t.insert("end", f"{datetime.now():%H:%M:%S}  {mensaje}\n")
        t.see("end")
        t.configure(state="disabled")

    def _ayuda(self) -> None:
        messagebox.showinfo("Cómo funciona", (
            "1. Lee la ficha pública del expediente en senado.gob.ar: origen, autores, giros, órdenes del día, "
            "sanción y textos.\n\n"
            "2. Para las reuniones, recorre las reuniones publicadas por cada comisión del giro desde el ingreso "
            "del expediente y abre cada nota para ver si figura en el temario. De cada una toma la versión "
            "taquigráfica y el video.\n\n"
            "3. Revisa la agenda de esas comisiones para avisar si ya hay una reunión convocada, y busca las "
            "votaciones nominales del recinto sobre el expediente o su orden del día.\n\n"
            "Seguimiento: guarda una lista de expedientes y, al revisarla, avisa qué cambió desde la revisión "
            "anterior (giros, dictámenes, votaciones, sanción, convocatorias y caducidad cercana).\n\n"
            "Por tema: busca en el Senado los expedientes cuyo extracto menciona las palabras del eje, filtra por "
            "años, origen, tipo y comisión, y arma un informe con la etapa de cada uno, en Word, HTML y Excel.\n\n"
            "4. Deduce la situación actual y estima la caducidad (Ley 13.640). Es orientativa: si importa, "
            "verificala en la fuente.\n\n"
            "Si algo no se lee bien, activá «Herramientas → Guardar las páginas descargadas» y enviá esa carpeta "
            "a quien mantiene el programa."))

    def _acerca(self) -> None:
        messagebox.showinfo("Acerca del programa", (
            f"Informe de Expedientes, versión {__version__}\n\n"
            "Usa solamente información pública del sitio del H. Senado de la Nación "
            "(www.senado.gob.ar) y de la H. Cámara de Diputados.\n\n"
            f"Configuración y caché: {config.carpeta_app()}"))

    def _guardar_preferencias(self) -> None:
        self.cfg.update({
            "reuniones": self.var_reuniones.get(), "asesores": self.var_asesores.get(),
            "agenda": self.var_agenda.get(), "docx": self.var_docx.get(), "html": self.var_html.get(),
            "carpeta": self.var_carpeta.get(), "usar_cache": self.var_cache.get(),
            "diagnostico": self.var_diagnostico.get(),
            "tema_tipos": [c for c, v in self.vars_tipos.items() if v.get()], "tema_detallar": self.var_detallar.get(),
            "tema_docx": self.var_t_docx.get(), "tema_html": self.var_t_html.get(), "tema_xlsx": self.var_t_xlsx.get(),
            "seguimiento_reuniones": self.var_seg_reuniones.get(),
            "sesion_formatos": [f for f, v in self.vars_ses_formatos.items() if v.get()],
        })
        guardar_config(self.cfg)

    def _cerrar(self) -> None:
        if self.hilo and self.hilo.is_alive():
            if not messagebox.askyesno("Consulta en curso", "Hay una consulta en curso. ¿Cancelarla y salir?"):
                return
            self.cancelar.set()
        self._guardar_preferencias()
        self.destroy()


def ejecutar() -> None:
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # texto nítido en pantallas con escala
        except Exception:
            pass
    app = Aplicacion()
    app.mainloop()
