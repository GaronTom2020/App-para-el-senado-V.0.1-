"""Interfaz gráfica del programa (Tkinter, incluida en Python)."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

from . import __version__, config
from .cliente import Cancelado, Cliente, ErrorRed
from .contenido import (
    comisiones_texto, datos_diputados, datos_diputados_hcdn, datos_generales, descripcion, sesiones_votadas,
    filas_relacionados, integrantes_od, texto_od, texto_resumen, titulo_etapa_diputados,
)
from .ficha import ExpedienteNoEncontrado
from .orden_dia import OrdenDelDiaVacia, parsear_od
from .identificador import ErrorIdentificador, parsear, separar_lote
from .busqueda import OTROS, Consulta, separar_palabras
from .ejes import Eje, buscar_eje, cargar_ejes, guardar_ejes
from . import asuntos_entrados, plan_labor, senadores
from .seguimiento import (
    Lista, OpcionesSeguimiento, ResultadoSeguimiento, markdown, revisar, situacion_breve, ultimo_movimiento,
)
from .sesion import OpcionesSesion, ResultadoSesion, etiqueta_referencias, generar_sesion
from .sesion import resumen as resumen_sesion
from .seguimiento import resumen as resumen_seguimiento
from .servicio import Opciones, generar
from .tematico import ETAPA, OpcionesTematicas, ResultadoTematico, generar_tematico, resumen, resumen_tipos
from .tematico import texto_resumen_tematico
from .util import fmt_fecha, nombre_comision

P = {
    "cupula": "#1A64AB", "cupula_oscura": "#114E9A", "cupula_tenue": "#E6EEF9", "piedra": "#D8E4F7",
    "papel": "#FFFFFF", "tinta": "#292F3D", "suave": "#5A6478", "linea": "#B9C8DE", "lacre": "#8C2F2F",
    "ambar": "#8A5A10", "apagado": "#9BB3D4", "subtitulo": "#D6E4F5", "boton": "#114E9A", "boton_activo": "#0B3D7C",
}
ICONO = Path(__file__).resolve().parent / "recursos" / "icono.ico"
LOGO = Path(__file__).resolve().parent / "recursos" / "logo_senado.png"     # isologotipo del sitio del Senado
TITULO = "Sistema de Información Parlamentaria"
PAD_FILA = 4            # separación entre renglones de los paneles
ANCHO_PANEL = 380       # ancho inicial de las explicaciones (después siguen el ancho del panel)
ENLACES = [
    ("Buscador de proyectos del Senado", config.URL_BUSCADOR),
    ("Buscador de proyectos de Diputados", "https://www.hcdn.gob.ar/proyectos/"),
    None,
    ("Constitución Nacional (Infoleg)",
     "https://servicios.infoleg.gob.ar/infolegInternet/anexos/0-4999/804/norma.htm"),
    ("Reglamento del Senado (PDF)", "https://www.senado.gob.ar/bundles/senadoportal/pdf/Reglamento_HSN.pdf"),
    ("Reglamento de Diputados", "https://www.hcdn.gob.ar/institucional/reglamento.html"),
    None,
    ("Versiones taquigráficas de las sesiones", "https://www.senado.gob.ar/parlamentario/sesiones/busquedaTac"),
    ("Votaciones nominales del Senado", "https://www.senado.gob.ar/votaciones/actas"),
    ("Planes de labor (Plenario de Labor)", "https://www.senado.gob.ar/parlamentario/parlamentaria/actas"),
]
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
TODOS_LOS_SEGUIDOS = "Todos los expedientes"
MARCA_SI, MARCA_NO = "☑", "☐"
MARCA_GRUPO = "◆"            # delante del nombre: el expediente está en algún grupo
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


def barra_automatica(contenedor, widget) -> ttk.Scrollbar:
    """Barra vertical que aparece solo cuando el contenido no entra (el widget va con pack)."""
    barra = ttk.Scrollbar(contenedor, orient="vertical", command=widget.yview)
    visible = False
    cambios: list[float] = []

    def fijar(primero, ultimo):
        nonlocal visible
        sobra = float(primero) <= 0.0 and float(ultimo) >= 1.0
        if sobra and visible:
            # Si el contenido queda justo en el límite, ocultar la barra lo reacomoda y la vuelve a pedir:
            # después de varios vaivenes seguidos, la barra se queda.
            ahora = time.monotonic()
            cambios[:] = [x for x in cambios if ahora - x < 1.0] + [ahora]
            if len(cambios) > 3:
                barra.set(primero, ultimo)
                return
            barra.pack_forget()
            visible = False
        elif not sobra and not visible:
            barra.pack(side="right", fill="y", before=widget)
            visible = True
        barra.set(primero, ultimo)

    widget.configure(yscrollcommand=fijar)
    return barra


def barra_horizontal_automatica(contenedor, widget) -> ttk.Scrollbar:
    """Barra horizontal que aparece solo cuando las columnas no entran (el widget va con pack)."""
    barra = ttk.Scrollbar(contenedor, orient="horizontal", command=widget.xview)
    visible = False
    cambios: list[float] = []

    def fijar(primero, ultimo):
        nonlocal visible
        sobra = float(primero) <= 0.0 and float(ultimo) >= 1.0
        if sobra and visible:
            # Si el contenido queda justo en el límite, ocultar la barra lo reacomoda y la vuelve a pedir:
            # después de varios vaivenes seguidos, la barra se queda.
            ahora = time.monotonic()
            cambios[:] = [x for x in cambios if ahora - x < 1.0] + [ahora]
            if len(cambios) > 3:
                barra.set(primero, ultimo)
                return
            barra.pack_forget()
            visible = False
        elif not sobra and not visible:
            barra.pack(side="bottom", fill="x", before=widget)
            visible = True
        barra.set(primero, ultimo)

    widget.configure(xscrollcommand=fijar)
    return barra


def mensaje_de_error(error: Exception) -> str:
    if isinstance(error, (ErrorIdentificador, ExpedienteNoEncontrado, OrdenDelDiaVacia)):
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
        self.title(TITULO)                 # es lo que muestra la barra de tareas al pasar el mouse
        self._icono()
        self.configure(bg=P["piedra"])
        self.minsize(940, 600)
        self.cfg = cargar_config()
        ancho = min(1400, self.winfo_screenwidth() - 40)
        alto = min(920, self.winfo_screenheight() - 70)
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
    def _icono(self) -> None:
        """Logo del Senado en la ventana y la barra de tareas (en el .exe viaja con --add-data)."""
        if ICONO.exists():
            try:
                self.iconbitmap(default=str(ICONO))
            except tk.TclError:
                pass                                   # fuera de Windows Tk puede no aceptar .ico

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
        self.f_titulo = tkfont.Font(family=serif, size=26)
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
        e.configure("Rotulo.TLabel", background=P["papel"], foreground=P["suave"])
        e.configure("Revision.TLabel", background=P["papel"], foreground=P["cupula_oscura"], font=self.f_normal)
        e.configure("Chico.TMenubutton", background=P["boton"], foreground="#FFFFFF", arrowcolor="#FFFFFF",
                    bordercolor=P["boton"], lightcolor=P["boton"], darkcolor=P["boton"], padding=(8, 2),
                    font=self.f_chica)
        e.map("Chico.TMenubutton", background=[("active", P["boton_activo"]), ("pressed", P["boton_activo"])])
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
        e.configure("TButton", padding=(12, 6), background=P["boton"], foreground="#FFFFFF", bordercolor=P["boton"],
                    lightcolor=P["boton"], darkcolor=P["boton"])
        e.map("TButton",
              background=[("disabled", P["apagado"]), ("pressed", P["boton_activo"]), ("active", P["boton_activo"])],
              foreground=[("disabled", "#F2F6FC")],
              lightcolor=[("active", P["boton_activo"])], darkcolor=[("active", P["boton_activo"])])
        e.configure("Chico.TButton", padding=(8, 2), font=self.f_chica, width=0)
        e.configure("Barra.TButton", padding=(10, 6), width=0)
        e.configure("Acento.TButton", padding=(18, 8), font=self.f_negrita)
        e.configure("Vertical.TScrollbar", background=P["linea"], troughcolor=P["papel"], bordercolor=P["papel"],
                    arrowcolor=P["suave"], lightcolor=P["linea"], darkcolor=P["linea"], gripcount=0, arrowsize=11)
        e.map("Vertical.TScrollbar", background=[("active", P["apagado"])])
        e.configure("Horizontal.TScrollbar", background=P["linea"], troughcolor=P["papel"], bordercolor=P["papel"],
                    arrowcolor=P["suave"], lightcolor=P["linea"], darkcolor=P["linea"], gripcount=0, arrowsize=11)
        e.map("Horizontal.TScrollbar", background=[("active", P["apagado"])])
        e.configure("TEntry", fieldbackground=P["papel"], padding=5)
        e.configure("TCombobox", fieldbackground=P["papel"], padding=4)
        e.map("TCombobox", fieldbackground=[("readonly", P["papel"])])
        e.configure("Horizontal.TProgressbar", troughcolor=P["linea"], background=P["cupula"],
                    lightcolor=P["cupula"], darkcolor=P["cupula"], bordercolor=P["linea"], thickness=6)
        e.configure("TNotebook", background=P["piedra"], borderwidth=0, tabmargins=(0, 4, 0, 0))
        e.configure("TNotebook.Tab", padding=(16, 7), background=P["piedra"], foreground=P["suave"])
        e.map("TNotebook.Tab", background=[("selected", P["papel"])], foreground=[("selected", P["tinta"])])
        e.configure("Treeview", rowheight=26, background=P["papel"], fieldbackground=P["papel"], borderwidth=0)
        e.configure("Treeview.Heading", background=P["piedra"], foreground=P["suave"], font=self.f_negrita,
                    relief="flat", padding=(6, 6))
        e.map("Treeview", background=[("selected", "#BCD2F0")], foreground=[("selected", P["tinta"])])

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
        self.var_seg_alias = tk.StringVar()
        self.registro_ae = asuntos_entrados.Registro.cargar()
        desde = date.fromisoformat(self.registro_ae.desde) if self.registro_ae.desde else date.today() - timedelta(days=7)
        self.var_ae_desde = tk.StringVar(value=f"{desde:%d/%m/%Y}")
        self.vars_ae_tipos = {t: tk.BooleanVar(value=True) for t, _ in TIPOS_TEMA}
        self.var_ae_origen = tk.StringVar(value=TODOS_ORIGENES)
        self.var_ae_texto = tk.StringVar()
        self.var_ae_ayuda = tk.StringVar()
        self.var_ae_info = tk.StringVar()
        self.var_ae_informe = tk.BooleanVar(value=c.get("asuntos_informe", False))
        self._ae_lista: list = []
        self.var_seg_info = tk.StringVar()
        self.var_seg_ultima = tk.StringVar()
        self.var_seg_archivo = tk.BooleanVar(value=c.get("seguimiento_archivo", True))
        self._ancla_seguimiento = None
        self._marcados: set[str] = set()
        self._mensaje_fin = ""
        self.var_notas = tk.StringVar()
        self.var_seg_grupo = tk.StringVar(value=TODOS_LOS_SEGUIDOS)
        self.var_seg_reuniones = tk.BooleanVar(value=c.get("seguimiento_reuniones", True))
        self.var_ses_fuente = tk.StringVar(value="Abrí un archivo, buscá el plan en el sitio o pegá el texto.")
        self.var_ses_plan = tk.StringVar()
        self.var_ses_reuniones = tk.BooleanVar(value=False)
        self.var_ses_taquigrafica = tk.BooleanVar(value=c.get("sesion_taquigrafica", True))
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
        archivo.add_command(label="Cambiar carpeta de informes…", command=self._elegir_carpeta)
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
        enlaces = tk.Menu(barra, tearoff=False)
        for enlace in ENLACES:
            if enlace is None:
                enlaces.add_separator()
            else:
                enlaces.add_command(label=enlace[0], command=lambda u=enlace[1]: webbrowser.open(u))
        barra.add_cascade(label="Enlaces útiles", menu=enlaces)
        ayuda = tk.Menu(barra, tearoff=False)
        ayuda.add_command(label="Cómo funciona", command=self._ayuda)
        ayuda.add_command(label="Acerca del programa", command=self._acerca)
        barra.add_cascade(label="Ayuda", menu=ayuda)
        self.config(menu=barra)

    # ------------------------------------------------------------- armado
    def _construir(self) -> None:
        banda = tk.Frame(self, bg=P["cupula"])
        banda.pack(fill="x")
        try:
            self.logo = tk.PhotoImage(file=str(LOGO))          # 110 × 82, en su tamaño original: se ve nítido
            tk.Label(banda, image=self.logo, bg=P["cupula"]).pack(side="right", padx=(0, 24), pady=8)
        except tk.TclError:
            pass                                       # sin el logo, la banda queda solo con el título
        tk.Label(banda, text=TITULO, bg=P["cupula"], fg="#FFFFFF", font=self.f_titulo).pack(
            side="left", anchor="w", padx=22, pady=10)

        cuerpo = ttk.Frame(self, padding=(14, 12, 14, 12))
        cuerpo.pack(fill="both", expand=True)
        cuerpo.columnconfigure(1, weight=1)
        cuerpo.rowconfigure(0, weight=1)
        self.modos = ttk.Notebook(cuerpo)
        self.modos.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        exterior, interior = self._desplazable(self.modos)
        self._panel_opciones(interior).pack(fill="both", expand=True)
        self.modos.add(exterior, text="Expedientes")
        exterior, interior = self._desplazable(self.modos)
        self._panel_tema(interior).pack(fill="both", expand=True)
        self.modos.add(exterior, text="Por tema")
        exterior, interior = self._desplazable(self.modos)
        self._panel_seguimiento(interior).pack(fill="both", expand=True)
        self.modos.add(exterior, text="Seguimiento")
        exterior, interior = self._desplazable(self.modos)
        self._panel_sesion(interior).pack(fill="both", expand=True)
        self.modos.add(exterior, text="Sesión")
        exterior, interior = self._desplazable(self.modos)
        self._panel_asuntos(interior).pack(fill="both", expand=True)
        self.modos.add(exterior, text="Asuntos entrados")
        self._panel_resultados(cuerpo).grid(row=0, column=1, sticky="nsew")

    def _desplazable(self, padre):
        """Marco con barra de desplazamiento vertical (para pantallas bajas)."""
        exterior = ttk.Frame(padre, style="Tarjeta.TFrame")
        lienzo = tk.Canvas(exterior, bg=P["papel"], highlightthickness=0, borderwidth=0)
        interior = ttk.Frame(lienzo, style="Tarjeta.TFrame")
        ventana = lienzo.create_window((0, 0), window=interior, anchor="nw")

        def ajustar(_e=None):
            # El ancho solo crece: si se achicara al aparecer la barra, el texto se reacomodaría y la barra
            # volvería a ocultarse, en un vaivén sin fin.
            ancho = max(lienzo.winfo_reqwidth() if lienzo.winfo_ismapped() else 0, interior.winfo_reqwidth())
            lienzo.configure(scrollregion=lienzo.bbox("all"), width=ancho)

        interior.bind("<Configure>", ajustar)
        lienzo.bind("<Configure>", lambda e: lienzo.itemconfigure(ventana, width=e.width))
        lienzo.pack(side="left", fill="both", expand=True)
        barra_automatica(exterior, lienzo)

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

    # ----------------------------------------------------- piezas de los paneles
    # Cada panel es una grilla de cuatro columnas: la primera lleva el rótulo del campo y las otras tres el
    # campo o varias opciones en el mismo renglón. Así entra en la pantalla sin barra de desplazamiento.
    def _rotulo(self, marco, texto: str, fila: int) -> None:
        ttk.Label(marco, text=texto, style="Rotulo.TLabel").grid(row=fila, column=0, sticky="nw", padx=(0, 10),
                                                                pady=(PAD_FILA + 3, 0))

    def _seccion(self, marco, texto: str, fila: int, arriba: int = 10) -> None:
        ttk.Label(marco, text=texto, style="Seccion.TLabel").grid(row=fila, column=0, columnspan=4, sticky="w",
                                                                 pady=(arriba, 2))

    def _explicacion(self, marco, texto: str, fila: int, columna: int = 0) -> ttk.Label:
        """Explicación a lo ancho del panel, debajo del campo (se reacomoda si cambia el ancho)."""
        etiqueta = ttk.Label(marco, text=texto, style="Ayuda.TLabel", justify="left", wraplength=ANCHO_PANEL)
        etiqueta.grid(row=fila, column=columna, columnspan=4 - columna, sticky="ew", pady=(2, 0))
        etiqueta.bind("<Configure>", lambda e: e.widget.configure(wraplength=max(160, e.width - 2)))
        return etiqueta

    def _texto(self, marco, alto: int, ajuste: str = "word", fuente=None) -> tk.Text:
        return tk.Text(marco, height=alto, width=30, wrap=ajuste, font=fuente or self.f_normal, relief="flat",
                       bg=P["papel"], fg=P["tinta"], insertbackground=P["tinta"], highlightthickness=1,
                       highlightbackground=P["linea"], highlightcolor=P["cupula"], padx=8, pady=5, undo=True)

    def _casillas(self, marco, fila: int, opciones, columna: int = 1) -> ttk.Frame:
        """Varias casillas en un renglón: [(texto, variable), …]."""
        caja = ttk.Frame(marco, style="Tarjeta.TFrame")
        caja.grid(row=fila, column=columna, columnspan=4 - columna, sticky="w", pady=(PAD_FILA, 0))
        for texto, variable in opciones:
            ttk.Checkbutton(caja, text=texto, variable=variable, style="Tarjeta.TCheckbutton").pack(
                side="left", padx=(0, 12))
        return caja

    def _botones_generar(self, marco, fila: int, texto: str, comando):
        botones = ttk.Frame(marco, style="Tarjeta.TFrame")
        botones.grid(row=fila, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        botones.columnconfigure(0, weight=1)
        generar = ttk.Button(botones, text=texto, style="Acento.TButton", command=comando)
        generar.grid(row=0, column=0, sticky="ew")
        cancelar = ttk.Button(botones, text="Cancelar", command=self._cancelar, state="disabled")
        cancelar.grid(row=0, column=1, padx=(8, 0))
        return generar, cancelar

    def _marco_panel(self, padre) -> ttk.Frame:
        marco = ttk.Frame(padre, style="Tarjeta.TFrame", padding=(16, 10, 16, 12))
        marco.columnconfigure(1, weight=1)
        marco.columnconfigure(2, weight=1)
        marco.columnconfigure(3, weight=1)
        return marco

    # ------------------------------------------------------------ paneles
    def _panel_opciones(self, padre) -> ttk.Frame:
        marco = self._marco_panel(padre)
        self._seccion(marco, "Expedientes u órdenes del día", 0, arriba=0)
        self.txt_expedientes = self._texto(marco, 3, ajuste="none")
        self.txt_expedientes.grid(row=1, column=0, columnspan=4, sticky="ew")
        self.txt_expedientes.bind("<Return>", self._enter_en_expedientes)
        self._explicacion(marco, "Uno por línea: S-1234/24, CD-14/24, PE-107/24, el enlace de la ficha o una orden del "
                           "día, OD 413/26 (sus expedientes forman un único despacho).", 2)

        self._rotulo(marco, "Tipo", 3)
        ttk.Combobox(marco, textvariable=self.var_tipo, values=OPCIONES_TIPO, state="readonly").grid(
            row=3, column=1, columnspan=3, sticky="ew", pady=(PAD_FILA, 0))
        self._rotulo(marco, "Buscar", 4)
        caja = self._casillas(marco, 4, [])
        ttk.Checkbutton(caja, text="Reuniones de comisión", variable=self.var_reuniones, style="Tarjeta.TCheckbutton",
                        command=self._sincronizar).pack(side="left", padx=(0, 12))
        self.chk_asesores = ttk.Checkbutton(caja, text="incluir las de asesores", variable=self.var_asesores,
                                            style="Tarjeta.TCheckbutton")
        self.chk_asesores.pack(side="left")
        self._casillas(marco, 5, [("Reuniones ya convocadas (agenda)", self.var_agenda)])
        self._rotulo(marco, "Formato", 6)
        self._casillas(marco, 6, [("Word", self.var_docx), ("HTML", self.var_html)])

        self._rotulo(marco, "Comentario", 7)
        ttk.Entry(marco, textvariable=self.var_notas).grid(row=7, column=1, columnspan=3, sticky="ew",
                                                           pady=(PAD_FILA, 0))
        self._explicacion(marco, "Opcional: un texto tuyo que se agrega al final del informe, en la sección «Notas» "
                           "(por ejemplo, una aclaración para quien lo recibe).", 8, columna=1)
        self.btn_generar, self.btn_cancelar = self._botones_generar(marco, 9, "Generar informe", self._generar)
        self._sincronizar()
        return marco

    def _panel_tema(self, padre) -> ttk.Frame:
        marco = self._marco_panel(padre)
        self._rotulo(marco, "Eje", 0)
        self.combo_eje = ttk.Combobox(marco, textvariable=self.var_eje, state="readonly", width=20)
        self.combo_eje.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(PAD_FILA, 0))
        self.combo_eje.bind("<<ComboboxSelected>>", self._eje_elegido)
        self._actualizar_combo_ejes()
        botones_eje = ttk.Frame(marco, style="Tarjeta.TFrame")
        botones_eje.grid(row=0, column=3, sticky="e", pady=(PAD_FILA, 0))
        ttk.Button(botones_eje, text="Guardar…", style="Chico.TButton", command=self._guardar_eje).pack(
            side="left", padx=(6, 0))
        ttk.Button(botones_eje, text="Borrar", style="Chico.TButton", command=self._borrar_eje).pack(
            side="left", padx=(4, 0))

        self._rotulo(marco, "Palabras", 1)
        ttk.Entry(marco, textvariable=self.var_palabras).grid(row=1, column=1, columnspan=3, sticky="ew",
                                                              pady=(PAD_FILA, 0))
        modos = ttk.Frame(marco, style="Tarjeta.TFrame")
        modos.grid(row=2, column=1, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Radiobutton(modos, text="Que tenga alguna", value="alguna", variable=self.var_modo,
                        style="Tarjeta.TRadiobutton").pack(side="left")
        ttk.Radiobutton(modos, text="Que tenga todas", value="todas", variable=self.var_modo,
                        style="Tarjeta.TRadiobutton").pack(side="left", padx=(14, 0))
        self._explicacion(marco, "Separadas por coma. Se busca en el extracto el comienzo de cada palabra, sin importar "
                           "tildes.", 3, columna=1)
        self._rotulo(marco, "Excluir", 4)
        ttk.Entry(marco, textvariable=self.var_excluir).grid(row=4, column=1, columnspan=3, sticky="ew",
                                                             pady=(PAD_FILA, 0))

        self._rotulo(marco, "Años", 5)
        anios = ttk.Frame(marco, style="Tarjeta.TFrame")
        anios.grid(row=5, column=1, columnspan=3, sticky="ew", pady=(PAD_FILA, 0))
        hoy = datetime.now().year
        ttk.Spinbox(anios, from_=1983, to=hoy, textvariable=self.var_desde, width=6).pack(side="left")
        ttk.Label(anios, text="a", style="Tarjeta.TLabel").pack(side="left", padx=6)
        ttk.Spinbox(anios, from_=1983, to=hoy, textvariable=self.var_hasta, width=6).pack(side="left")
        ttk.Label(anios, text="Origen", style="Rotulo.TLabel").pack(side="left", padx=(14, 6))
        ttk.Combobox(anios, textvariable=self.var_origen, values=OPCIONES_ORIGEN, state="readonly", width=12).pack(
            side="left", fill="x", expand=True)
        self._rotulo(marco, "Comisión", 6)
        ttk.Combobox(marco, textvariable=self.var_comision, state="readonly",
                     values=[CUALQUIER_COMISION] + list(self.comisiones_por_nombre)).grid(
            row=6, column=1, columnspan=3, sticky="ew", pady=(PAD_FILA, 0))
        self._rotulo(marco, "Autor / bloque", 7)
        firmas = ttk.Frame(marco, style="Tarjeta.TFrame")
        firmas.grid(row=7, column=1, columnspan=3, sticky="ew", pady=(PAD_FILA, 0))
        firmas.columnconfigure(0, weight=3)
        firmas.columnconfigure(1, weight=2)
        self.combo_autor = ttk.Combobox(firmas, textvariable=self.var_autor, values=[CUALQUIER_AUTOR], width=14,
                                        postcommand=self._cargar_senadores)
        self.combo_autor.grid(row=0, column=0, sticky="ew")
        self.combo_bloque = ttk.Combobox(firmas, textvariable=self.var_bloque, values=[CUALQUIER_BLOQUE], width=10,
                                         state="readonly", postcommand=self._cargar_senadores)
        self.combo_bloque.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._explicacion(marco, "Proyectos con su firma (autor o coautor). El bloque toma a sus integrantes actuales "
                                 "y tiene prioridad sobre el senador.", 9, columna=1)

        self._rotulo(marco, "Tipos", 10)
        tipos = ttk.Frame(marco, style="Tarjeta.TFrame")
        tipos.grid(row=10, column=1, columnspan=3, sticky="w", pady=(PAD_FILA, 0))
        for k, (codigo, nombre) in enumerate(TIPOS_TEMA):
            ttk.Checkbutton(tipos, text=nombre, variable=self.vars_tipos[codigo], style="Tarjeta.TCheckbutton").grid(
                row=k // 3, column=k % 3, sticky="w", padx=(0, 10))
        self._rotulo(marco, "De cada uno", 11)
        self._casillas(marco, 11, [("Ficha", self.var_detallar), ("Reuniones (lento)", self.var_reuniones_tema),
                                   ("Informe completo", self.var_individuales)])
        self._rotulo(marco, "Formato", 13)
        self._casillas(marco, 13, [("Word", self.var_t_docx), ("HTML", self.var_t_html), ("Excel", self.var_t_xlsx)])
        self.btn_generar_tema, self.btn_cancelar_tema = self._botones_generar(
            marco, 14, "Generar informe temático", self._generar_tematico)
        return marco

    def _panel_seguimiento(self, padre) -> ttk.Frame:
        marco = self._marco_panel(padre)
        self._rotulo(marco, "Grupo", 0)
        self.combo_grupo = ttk.Combobox(marco, textvariable=self.var_seg_grupo, state="readonly", width=16)
        self.combo_grupo.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(PAD_FILA, 0))
        self.combo_grupo.bind("<<ComboboxSelected>>", lambda _e: self._llenar_seguimiento())
        grupos = ttk.Frame(marco, style="Tarjeta.TFrame")
        grupos.grid(row=0, column=3, sticky="e", pady=(PAD_FILA, 0))
        for texto, comando in (("Nuevo", self._nuevo_grupo), ("Renombrar", self._renombrar_grupo),
                               ("Borrar", self._borrar_grupo)):
            ttk.Button(grupos, text=texto, style="Chico.TButton", command=comando).pack(side="left", padx=(4, 0))

        contenedor = ttk.Frame(marco, style="Tarjeta.TFrame")
        contenedor.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=(8, 0))
        a = self.arbol_seguimiento = ttk.Treeview(contenedor, columns=("marca", "exp", "situacion", "desde"),
                                                  show="headings", selectmode="browse", height=5)
        # Anchos mínimos: si el nombre o la situación no entran, aparece la barra horizontal.
        for clave, titulo, ancho in (("marca", MARCA_NO, 30), ("exp", "Expediente", 200),
                                     ("situacion", "Situación", 170), ("desde", "Desde", 92)):
            a.heading(clave, text=titulo, anchor="center" if clave == "marca" else "w")
            a.column(clave, width=ancho, minwidth=ancho, stretch=clave in ("exp", "situacion"),
                     anchor="center" if clave == "marca" else "w")
        a.heading("marca", command=self._elegir_todos)
        a.tag_configure("secundario", foreground=P["suave"])
        barra_horizontal_automatica(contenedor, a)
        a.pack(side="left", fill="both", expand=True)
        barra_automatica(contenedor, a)
        # El recuadro tiene alto fijo y toma el ancho del panel: si las columnas no entran, la tabla se desplaza
        # adentro (barra horizontal) en vez de ensanchar el panel.
        contenedor.configure(width=320, height=a.winfo_reqheight() + 18)
        contenedor.pack_propagate(False)
        a.bind("<Button-1>", self._clic_seguimiento)
        a.bind("<<TreeviewSelect>>", lambda _e: self._resumen_seguido())
        a.bind("<Control-a>", lambda _e: self._elegir_todos(True) or "break")
        a.bind("<space>", lambda _e: self._alternar_marca(a.focus()) or "break")
        a.bind("<Delete>", lambda _e: self._quitar_seguimiento())
        a.bind("<Double-1>", lambda _e: self._ficha_seguimiento())
        a.bind("<Button-3>", self._menu_seguimiento)

        acciones = ttk.Frame(marco, style="Tarjeta.TFrame")
        acciones.grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        for texto, comando in (("Nombre…", self._nombrar_seguido), ("Agrupar…", self._agrupar_elegidos),
                               ("Ficha", self._ficha_seguimiento), ("Quitar", self._quitar_seguimiento)):
            ttk.Button(acciones, text=texto, style="Chico.TButton", command=comando).pack(side="left", padx=(0, 4))
        self.btn_sacar_grupo = ttk.Button(acciones, text="Sacar del grupo", style="Chico.TButton",
                                          command=self._sacar_del_grupo)
        self._explicacion(marco, "", 3).configure(textvariable=self.var_seg_info)

        self._seccion(marco, "Agregar expedientes u órdenes del día", 4)
        self.menu_traer = tk.Menu(self, tearoff=False, postcommand=self._armar_menu_traer)
        ttk.Menubutton(marco, text="Traer de un tema", menu=self.menu_traer, style="Chico.TMenubutton").grid(
            row=4, column=3, sticky="e", pady=(10, 2))
        self.txt_seg_nuevos = self._texto(marco, 2)
        self.txt_seg_nuevos.grid(row=5, column=0, columnspan=4, sticky="ew")
        self._rotulo(marco, "Nombre", 6)
        ttk.Entry(marco, textvariable=self.var_seg_alias).grid(row=6, column=1, columnspan=2, sticky="ew",
                                                               pady=(PAD_FILA, 0))
        ttk.Button(marco, text="Agregar", command=self._agregar_seguimiento).grid(row=6, column=3, sticky="e",
                                                                                padx=(6, 0), pady=(PAD_FILA, 0))
        self._explicacion(marco, "Por línea o con comas (también OD 413/26). El nombre vale si agregás uno solo.", 7)

        self._rotulo(marco, "Al revisar", 8)
        self._casillas(marco, 8, [("Reuniones (lento)", self.var_seg_reuniones),
                                  ("Guardar resumen en archivo", self.var_seg_archivo)])
        self.btn_revisar, self.btn_cancelar_seg = self._botones_generar(marco, 10, "Revisar novedades",
                                                                        self._revisar_seguimiento)
        ttk.Label(marco, textvariable=self.var_seg_ultima, style="Revision.TLabel").grid(
            row=11, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.menu_seguido = tk.Menu(self, tearoff=False)
        self._llenar_seguimiento()
        return marco

    def _panel_asuntos(self, padre) -> ttk.Frame:
        marco = self._marco_panel(padre)
        self._rotulo(marco, "Desde", 0)
        ttk.Entry(marco, textvariable=self.var_ae_desde, width=12).grid(row=0, column=1, sticky="w", pady=(PAD_FILA, 0))
        self._explicacion(marco, "", 1, columna=1).configure(textvariable=self.var_ae_ayuda)
        self._seccion(marco, "Filtrar lo que se muestra", 2)
        self._rotulo(marco, "Tipos", 3)
        tipos = ttk.Frame(marco, style="Tarjeta.TFrame")
        tipos.grid(row=3, column=1, columnspan=3, sticky="w", pady=(PAD_FILA, 0))
        for k, (codigo, nombre) in enumerate(TIPOS_TEMA):
            ttk.Checkbutton(tipos, text=nombre, variable=self.vars_ae_tipos[codigo],
                            style="Tarjeta.TCheckbutton").grid(row=k // 3, column=k % 3, sticky="w", padx=(0, 10))
        self._rotulo(marco, "Origen", 4)
        ttk.Combobox(marco, textvariable=self.var_ae_origen, values=OPCIONES_ORIGEN, state="readonly").grid(
            row=4, column=1, columnspan=3, sticky="ew", pady=(PAD_FILA, 0))
        self._rotulo(marco, "Palabras", 5)
        ttk.Entry(marco, textvariable=self.var_ae_texto).grid(row=5, column=1, columnspan=3, sticky="ew",
                                                              pady=(PAD_FILA, 0))
        self._explicacion(marco, "Busca en el extracto y en las comisiones del giro. Los filtros cambian la lista al "
                                 "instante, sin volver a consultar el sitio.", 6, columna=1)
        acciones = ttk.Frame(marco, style="Tarjeta.TFrame")
        acciones.grid(row=7, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(acciones, text="Sumar los elegidos al seguimiento", style="Chico.TButton",
                   command=lambda: self._accion_expediente("seguir")).pack(side="left")
        ttk.Button(acciones, text="Ver la última revisión", style="Chico.TButton",
                   command=self._ver_ultimos_asuntos).pack(side="left", padx=(6, 0))
        self._casillas(marco, 8, [("Generar un informe de los asuntos (Word y HTML)", self.var_ae_informe)], columna=0)
        self.btn_asuntos, self.btn_cancelar_ae = self._botones_generar(marco, 9, "Buscar asuntos nuevos",
                                                                       self._buscar_asuntos)
        ttk.Label(marco, textvariable=self.var_ae_info, style="Revision.TLabel").grid(
            row=10, column=0, columnspan=4, sticky="w", pady=(6, 0))
        for variable in [self.var_ae_origen, self.var_ae_texto, *self.vars_ae_tipos.values()]:
            variable.trace_add("write", lambda *_: self._refiltrar_asuntos())
        self._estado_asuntos()
        return marco

    def _panel_sesion(self, padre) -> ttk.Frame:
        marco = self._marco_panel(padre)
        self._seccion(marco, "Plan de labor", 0, arriba=0)
        botones = ttk.Frame(marco, style="Tarjeta.TFrame")
        botones.grid(row=1, column=0, columnspan=4, sticky="w")
        ttk.Button(botones, text="Abrir archivo…", style="Chico.TButton", command=self._abrir_plan).pack(side="left")
        ttk.Button(botones, text="Buscar en el sitio", style="Chico.TButton",
                   command=self._buscar_planes).pack(side="left", padx=(6, 0))
        ttk.Button(botones, text="Ver los asuntos", style="Chico.TButton",
                   command=self._vista_previa_sesion).pack(side="left", padx=(6, 0))
        self.combo_planes = ttk.Combobox(marco, textvariable=self.var_ses_plan, state="disabled")
        self.combo_planes.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        self.combo_planes.bind("<<ComboboxSelected>>", self._elegir_plan_publicado)
        self._explicacion(marco, "O pegá el texto del plan (podés corregirlo antes de generar):", 3)
        self.txt_plan = self._texto(marco, 6, fuente=self.f_chica)
        self.txt_plan.grid(row=4, column=0, columnspan=4, sticky="ew")
        self._explicacion(marco, "", 5).configure(textvariable=self.var_ses_fuente)

        self._rotulo(marco, "Buscar", 6)
        self._casillas(marco, 6, [("Reuniones de comisión (lento)", self.var_ses_reuniones)])
        self._casillas(marco, 7, [("Versión taquigráfica (si la sesión ya se hizo)", self.var_ses_taquigrafica)])
        self._rotulo(marco, "Formato", 8)
        self._casillas(marco, 8, [("Word", self.vars_ses_formatos["docx"]), ("HTML", self.vars_ses_formatos["html"]),
                                  ("Excel", self.vars_ses_formatos["xlsx"]),
                                  ("CSV (Power BI)", self.vars_ses_formatos["csv"])])
        self.btn_generar_ses, self.btn_cancelar_ses = self._botones_generar(marco, 9, "Generar informe de sesión",
                                                                            self._generar_sesion)
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
            self.pestanias, [("exp", "Expediente", 120), ("tipo", "Tipo", 56), ("etapa", "Situación", 210),
                             ("extracto", "Extracto", 300)],
            ayuda="Doble clic: abre la ficha. Clic derecho: informe completo o seguimiento (Ctrl + clic elige varios).",
            seleccion="extended")
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
        menu_exp.add_command(label="Agregar los elegidos a la lista de seguimiento",
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
        texto.configure(state="disabled")
        texto.pack(side="left", fill="both", expand=True)
        barra_automatica(contenedor, texto)
        return texto

    def _arbol(self, padre, columnas, con_arbol=False, ayuda: str = "", seleccion: str = "browse") -> ttk.Treeview:
        contenedor = ttk.Frame(padre, style="Tarjeta.TFrame")
        if ayuda:
            ttk.Label(contenedor, text=ayuda, style="Ayuda.TLabel", padding=(10, 6)).pack(side="bottom", anchor="w")
        arbol = ttk.Treeview(contenedor, columns=[c[0] for c in columnas],
                             show="tree headings" if con_arbol else "headings", selectmode=seleccion)
        if con_arbol:
            arbol.column("#0", width=24, stretch=False)
        for clave, titulo, ancho in columnas:
            arbol.heading(clave, text=titulo, anchor="w")
            arbol.column(clave, width=ancho, minwidth=44, anchor="w",
                         stretch=clave in ("reunion", "detalle", "extracto"))
        arbol.tag_configure("grupo", font=self.f_negrita)
        arbol.tag_configure("secundario", foreground=P["suave"])
        arbol.pack(side="left", fill="both", expand=True)
        barra_automatica(contenedor, arbol)
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
            notas_usuario=self.var_notas.get().strip(),
        )

    def _generar(self) -> None:
        if self.hilo and self.hilo.is_alive():
            return
        textos = separar_lote(self.txt_expedientes.get("1.0", "end"))
        if not textos:
            messagebox.showinfo("Falta el expediente", "Escribí al menos un número de expediente o de orden del día, "
                                                       "por ejemplo S-1234/24 u OD 413/26.")
            self.txt_expedientes.focus_set()
            return
        opciones = self._opciones()
        errores = []
        for t in textos:
            if parsear_od(t):
                continue
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
        for b in (self.btn_generar, self.btn_generar_tema, self.btn_revisar, self.btn_generar_ses, self.btn_asuntos):
            b.state(["disabled"] if si else ["!disabled"])
        for b in (self.btn_cancelar, self.btn_cancelar_tema, self.btn_cancelar_seg, self.btn_cancelar_ses,
                  self.btn_cancelar_ae):
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
        for b in (self.btn_cancelar, self.btn_cancelar_tema, self.btn_cancelar_seg, self.btn_cancelar_ses,
                  self.btn_cancelar_ae):
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
        elif evento == "traer":
            idents = datos["idents"]
            if idents:
                nuevos = self._sumar_a_seguimiento([x.corto for x in idents], {x.corto: x.tipo for x in idents},
                                                   grupo=datos["grupo"])
                self.var_seg_grupo.set(datos["grupo"])
                self._llenar_seguimiento()
                self._mensaje_fin = (f"Eje «{datos['eje']}»: {len(idents)} proyectos encontrados, {nuevos} nuevos en "
                                     f"el grupo «{datos['grupo']}».")
            else:
                self._mensaje_fin = f"El eje «{datos['eje']}» no encontró proyectos en esos años."
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
            if isinstance(resultado, asuntos_entrados.ResultadoAsuntos) and self.var_ae_informe.get():
                self._informe_asuntos(resultado)
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
                if self.resultados and isinstance(self.resultados[-1], asuntos_entrados.ResultadoAsuntos):
                    self.var_estado.set("Listo: " + asuntos_entrados.resumen(self.resultados[-1]))
                if self.resultados and isinstance(self.resultados[-1], ResultadoSeguimiento):
                    self.var_estado.set(f"Listo: {resumen_seguimiento(self.resultados[-1])}")
                    self._llenar_seguimiento()
            else:
                self.var_estado.set("No se pudo generar el informe. Mirá el detalle en «Registro».")
            self._registro(f"Pedidos al sitio: {datos['pedidos']} · desde caché: {datos['cache']}")
            if self._mensaje_fin:
                self.var_estado.set(self._mensaje_fin)
                self._mensaje_fin = ""
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
        if isinstance(r, asuntos_entrados.ResultadoAsuntos):
            self._mostrar_asuntos(r)
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
        self.arbol_expedientes.heading("etapa", text="Situación")
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
            return f"Seguimiento: {r.grupo}" if r.grupo else "Seguimiento"
        if isinstance(r, ResultadoSesion):
            return f"Sesión {r.fecha:%d/%m}" if r.fecha else "Sesión"
        if isinstance(r, asuntos_entrados.ResultadoAsuntos):
            return "Asuntos entrados"
        return r.titulo

    def _mostrar_seguimiento(self, r: ResultadoSeguimiento) -> None:
        self._pestanias_visibles(True)
        self.pestanias.tab(self.arbol_expedientes.master, state="hidden")
        t = self.txt_resumen
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._enlaces.clear()
        t.insert("end", f"Revisión del {r.generado:%d/%m/%Y, %H:%M} h\n", "suave")
        t.insert("end", (f"Seguimiento: {r.grupo}" if r.grupo else "Seguimiento de expedientes") + "\n", "numero")
        t.insert("end", resumen_seguimiento(r) + "\n", "extracto")
        for rev in r.con_novedades:
            self._enlace(rev.seguido.nombre, rev.url, "rotulo")
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
                t.insert("end", f"{rev.seguido.nombre}: ", ("vineta", "etiqueta"))
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
                                  buscar_taquigrafica=self.var_ses_taquigrafica.get(),
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
            if tema.debate is not None:
                d = tema.debate
                partes = [d.desenlace or f"{len(d.votaciones)} votaciones"]
                if d.modificaciones:
                    partes.append(f"{len(d.modificaciones)} modificaciones aprobadas en el recinto")
                t.insert("end", "      Recinto: " + ". ".join(p.rstrip(".") for p in partes) + ".\n", ("vineta", "suave"))
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
    def _grupo_elegido(self) -> str | None:
        grupo = self.var_seg_grupo.get()
        return grupo if grupo in self.lista_seguimiento.grupos else None

    def _llenar_seguimiento(self) -> None:
        lista = self.lista_seguimiento
        self.combo_grupo.configure(values=[TODOS_LOS_SEGUIDOS] + lista.grupos)
        if self.var_seg_grupo.get() not in lista.grupos:
            self.var_seg_grupo.set(TODOS_LOS_SEGUIDOS)
        grupo = self._grupo_elegido()
        a = self.arbol_seguimiento
        a.delete(*a.get_children())
        elegidos = lista.del_grupo(grupo)
        self._marcados &= {s.expediente for s in elegidos}
        for s in elegidos:
            nombre = (f"{MARCA_GRUPO} " if any(g != grupo for g in s.grupos) else "") + s.nombre
            foto = s.foto or {}
            situacion = situacion_breve(foto["situacion"]) if foto.get("situacion") else "sin revisar todavía"
            fecha, _que = ultimo_movimiento(foto)
            a.insert("", "end", iid=s.expediente, values=(MARCA_NO, nombre, situacion, fmt_fecha(fecha, "")),
                     tags=() if s.foto else ("secundario",))
        # Cada columna toma el ancho de su texto más largo: si no entra en el recuadro, aparece la barra horizontal.
        for columna in ("exp", "situacion", "desde"):
            textos = [str(a.heading(columna, "text"))] + [str(a.set(i, columna)) for i in a.get_children()]
            ancho = max(self.f_normal.measure(x) for x in textos) + 20
            a.column(columna, width=ancho, minwidth=ancho)
        self.btn_revisar.configure(text=f"Revisar novedades ({len(elegidos)})" if grupo else "Revisar novedades")
        if grupo:
            self.btn_sacar_grupo.pack(side="left", padx=(0, 4))
        else:
            self.btn_sacar_grupo.pack_forget()
        revisados = [s.revisado for s in elegidos if s.revisado]
        if revisados:
            ultima = datetime.fromisoformat(max(revisados))
            pendientes = len(elegidos) - len(revisados)
            self.var_seg_ultima.set(f"⟳  Última revisión: {ultima:%d/%m/%Y, %H:%M} h"
                                    + (f" · {pendientes} sin revisar todavía" if pendientes else ""))
        else:
            self.var_seg_ultima.set("⟳  Todavía no se revisó." if elegidos else "")
        self._marcar_elegidos()

    def _seguidos_elegidos(self) -> list:
        """Los marcados con la casilla o, si no hay ninguno, la fila que se está mirando."""
        claves = self._marcados or set(self.arbol_seguimiento.selection())
        return [s for s in self.lista_seguimiento.seguidos if s.expediente in claves]

    def _marcar_elegidos(self) -> None:
        """Casillas de las filas y explicación según lo marcado."""
        a = self.arbol_seguimiento
        filas = a.get_children()
        for iid in filas:
            a.set(iid, "marca", MARCA_SI if iid in self._marcados else MARCA_NO)
        a.heading("marca", text=MARCA_SI if filas and len(self._marcados) == len(filas) else MARCA_NO)
        n = len(self._marcados)
        con_grupo = any(MARCA_GRUPO in str(a.set(i, "exp")) for i in filas)
        if not filas:
            texto = "La lista está vacía: agregá expedientes abajo."
        elif n and self._grupo_elegido():
            texto = (f"{n} marcado{'s' if n != 1 else ''}. «Sacar del grupo» los saca de «{self._grupo_elegido()}» "
                     "pero siguen en la lista.")
        elif n:
            texto = f"{n} marcado{'s' if n != 1 else ''}. Los botones y el clic derecho actúan sobre ellos."
        else:
            texto = "Clic en una fila: su resumen a la derecha. ☐ marca varios; el ☐ del encabezado, todos."
        if con_grupo and not n:
            texto += f" {MARCA_GRUPO} = está en un grupo."
        self.var_seg_info.set(texto)

    def _alternar_marca(self, fila: str) -> None:
        if fila:
            self._marcados ^= {fila}
            self._marcar_elegidos()

    def _clic_seguimiento(self, evento):
        """Clic en la casilla: marca o desmarca. En el resto de la fila: la elige y muestra su resumen."""
        a = self.arbol_seguimiento
        if a.identify_region(evento.x, evento.y) != "cell" or a.identify_column(evento.x) != "#1":
            return None
        fila = a.identify_row(evento.y)
        filas = list(a.get_children())
        if evento.state & 0x1 and self._ancla_seguimiento in filas and fila:   # Mayús: un tramo
            i, j = sorted((filas.index(self._ancla_seguimiento), filas.index(fila)))
            self._marcados |= set(filas[i:j + 1])
            self._marcar_elegidos()
        else:
            self._alternar_marca(fila)
            self._ancla_seguimiento = fila
        return "break"

    def _resumen_seguido(self) -> None:
        """Resumen del expediente elegido en la pestaña «Resumen» de la derecha."""
        sel = self.arbol_seguimiento.selection()
        s = next((x for x in self.lista_seguimiento.seguidos if sel and x.expediente == sel[0]), None)
        if s is None:
            return
        foto = s.foto or {}
        self.actual = None
        self._pestanias_visibles(True)
        self.pestanias.tab(self.arbol_expedientes.master, state="hidden")
        t = self.txt_resumen
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._enlaces.clear()
        t.insert("end", "Seguimiento\n", "suave")
        t.insert("end", (s.alias or s.expediente) + "\n", "numero")
        if s.alias:
            t.insert("end", s.expediente + "\n", "suave")
        if foto.get("extracto"):
            t.insert("end", foto["extracto"] + "\n", "extracto")
        if foto.get("situacion"):
            t.insert("end", "Situación\n", "rotulo")
            t.insert("end", foto["situacion"] + "\n", "situacion")
            fecha, que = ultimo_movimiento(foto)
            if fecha:
                t.insert("end", f"Desde el {fmt_fecha(fecha)}: {que}.\n", "vineta")
            if foto.get("caducidad"):
                t.insert("end", f"Caducidad estimada: {fmt_fecha(datetime.fromisoformat(foto['caducidad']).date())}.\n",
                         ("vineta", "suave"))
        else:
            t.insert("end", "Todavía no se revisó: presioná «Revisar novedades» para traer su situación.\n",
                     ("vineta", "suave"))
        t.insert("end", "Datos del seguimiento\n", "rotulo")
        t.insert("end", "Grupos: ", ("vineta", "etiqueta"))
        t.insert("end", (", ".join(s.grupos) or "ninguno") + "\n")
        t.insert("end", "Agregado: ", ("vineta", "etiqueta"))
        t.insert("end", (fmt_fecha(datetime.fromisoformat(s.agregado).date()) if s.agregado else "") + "\n")
        t.insert("end", "Última revisión: ", ("vineta", "etiqueta"))
        t.insert("end", (f"{datetime.fromisoformat(s.revisado):%d/%m/%Y, %H:%M} h" if s.revisado else "nunca") + "\n")
        if foto.get("url"):
            t.insert("end", "\n")
            self._enlace("Ver la ficha en el sitio del Senado", foto["url"], "vineta")
            t.insert("end", "\n")
        t.configure(state="disabled")
        for boton in (self.btn_word, self.btn_html, self.btn_excel, self.btn_ficha):
            boton.state(["disabled"])
        self.btn_copiar.state(["disabled"])
        self.pestanias.select(0)

    def _elegir_todos(self, todos: bool | None = None) -> None:
        filas = set(self.arbol_seguimiento.get_children())
        if todos is None:
            todos = self._marcados != filas
        self._marcados = filas if todos else set()
        self._marcar_elegidos()

    def _vaciar_seguimiento(self) -> None:
        lista = self.lista_seguimiento
        if not lista.seguidos:
            return
        if not messagebox.askyesno("Vaciar la lista", f"¿Quitar los {len(lista.seguidos)} expedientes de la lista de "
                                                      "seguimiento? Los grupos quedan creados, vacíos."):
            return
        lista.seguidos.clear()
        self._guardar_seguimiento()

    def _armar_menu_traer(self) -> None:
        """Menú «Traer de un tema»: los ejes temáticos guardados y la última búsqueda por tema."""
        m = self.menu_traer
        m.delete(0, "end")
        for eje in self.ejes:
            m.add_command(label=f"Eje «{eje.nombre}»", command=lambda e=eje: self._traer_de_eje(e))
        if not self.ejes:
            m.add_command(label="(no hay ejes guardados: crealos en «Por tema»)", state="disabled")
        m.add_separator()
        m.add_command(label="Resultados de la última búsqueda por tema", command=self._traer_de_tema)

    def _traer_de_eje(self, eje) -> None:
        if self.hilo and self.hilo.is_alive():
            messagebox.showinfo("Consulta en curso", "Esperá a que termine la consulta actual.")
            return
        try:
            desde, hasta = int(self.var_desde.get()), int(self.var_hasta.get())
        except ValueError:
            desde = hasta = datetime.now().year
        grupo = self._grupo_elegido() or eje.nombre
        if not messagebox.askyesno("Traer de un tema", f"Se buscan los proyectos del eje «{eje.nombre}» "
                                                       f"({desde} a {hasta}) y se suman al seguimiento, en el grupo "
                                                       f"«{grupo}». ¿Continuar?"):
            return
        consulta = Consulta(palabras=list(eje.palabras), modo=eje.modo, excluir=list(eje.excluir), anio_desde=desde,
                            anio_hasta=hasta, comision_id=eje.comision_id, eje=eje.nombre)
        opciones = OpcionesTematicas(detallar=False, formatos=(), carpeta_salida=Path(self.var_carpeta.get()))
        self.cancelar.clear()
        self._registro(f"— Traer al seguimiento el eje «{eje.nombre}»")
        self._ocupado(True)

        def trabajo():
            cliente = self._nuevo_cliente()
            hechos, fallidos = 0, []
            try:
                res = generar_tematico(consulta, opciones, cliente, lambda ev, msg="", **d: self.cola.put((ev, msg, d)),
                                       escribir=False)
                idents = [it.hallazgo.ident for it in res.items]
                self.cola.put(("traer", "", {"idents": idents, "grupo": grupo, "eje": eje.nombre}))
                hechos = 1
            except Cancelado:
                self.cola.put(("log", "Consulta cancelada.", {}))
            except Exception as e:  # noqa: BLE001
                fallidos.append(mensaje_de_error(e))
                self.cola.put(("log", traceback.format_exc(), {}))
            self.cola.put(("fin", "", {"hechos": hechos, "fallidos": fallidos, "carpeta": str(opciones.carpeta_salida),
                                       "pedidos": cliente.pedidos_red, "cache": cliente.pedidos_cache}))

        self.hilo = threading.Thread(target=trabajo, daemon=True)
        self.hilo.start()

    def _guardar_seguimiento(self) -> bool:
        try:
            self.lista_seguimiento.guardar()
        except OSError as e:
            messagebox.showerror("No se pudo guardar la lista", str(e))
            return False
        self._llenar_seguimiento()
        return True

    def _sumar_a_seguimiento(self, textos: list[str], tipos: dict | None = None, alias: str = "",
                             grupo: str | None = None) -> int:
        """Suma los expedientes a la lista (y al grupo elegido). Devuelve cuántos eran nuevos."""
        grupo = grupo or self._grupo_elegido()
        nuevos, errores = 0, []
        for texto in textos:
            try:
                _s, nuevo = self.lista_seguimiento.agregar(texto, (tipos or {}).get(texto),
                                                           alias=alias if len(textos) == 1 else "", grupo=grupo)
                nuevos += nuevo
            except ErrorIdentificador as e:
                errores.append(str(e))
        if errores:
            messagebox.showwarning("Revisá los números", "\n\n".join(errores))
        if not self._guardar_seguimiento():
            return 0
        repetidos = len(textos) - len(errores) - nuevos
        partes = [f"{nuevos} agregado{'s' if nuevos != 1 else ''}"]
        if repetidos:
            partes.append(f"{repetidos} ya estaba{'n' if repetidos != 1 else ''}")
        self.var_estado.set("Seguimiento: " + ", ".join(partes) + (f" (grupo «{grupo}»)." if grupo else "."))
        return nuevos

    def _agregar_seguimiento(self) -> None:
        textos = separar_lote(self.txt_seg_nuevos.get("1.0", "end").replace(",", "\n").replace(";", "\n"))
        if not textos:
            messagebox.showinfo("Falta el expediente", "Escribí uno o más expedientes, por ejemplo S-1234/24, o una "
                                                       "orden del día, por ejemplo OD 413/26.")
            return
        self._sumar_a_seguimiento(textos, alias=self.var_seg_alias.get().strip())
        self.txt_seg_nuevos.delete("1.0", "end")
        self.var_seg_alias.set("")

    def _traer_de_tema(self) -> None:
        """Suma los expedientes elegidos (o todos) del último informe temático."""
        tematico = self.actual if isinstance(self.actual, ResultadoTematico) else next(
            (r for r in reversed(self.resultados) if isinstance(r, ResultadoTematico)), None)
        if tematico is None or not tematico.items:
            messagebox.showinfo("Sin búsqueda por tema", "Primero hacé una búsqueda en la pestaña «Por tema». Después "
                                                         "podés traer acá todos sus expedientes o solo los que elijas "
                                                         "en la lista de resultados.")
            return
        sel = self.arbol_expedientes.selection() if tematico is self.actual else ()
        items = [tematico.items[int(i)] for i in sel] or tematico.items
        que = f"los {len(items)} expedientes elegidos" if sel else f"los {len(items)} expedientes de la búsqueda"
        if len(items) > 1 and not messagebox.askyesno("Traer de «Por tema»", f"¿Sumar al seguimiento {que} "
                                                                             f"«{tematico.consulta.titulo()}»?"):
            return
        idents = [it.hallazgo.ident for it in items]
        self._sumar_a_seguimiento([x.corto for x in idents], {x.corto: x.tipo for x in idents})

    def _quitar_seguimiento(self) -> None:
        elegidos = self._seguidos_elegidos()
        if not elegidos:
            return
        que = elegidos[0].nombre if len(elegidos) == 1 else f"los {len(elegidos)} expedientes elegidos"
        if not messagebox.askyesno("Quitar del seguimiento", f"¿Quitar {que} de la lista de seguimiento?"):
            return
        for s in elegidos:
            self.lista_seguimiento.seguidos.remove(s)
        self._guardar_seguimiento()

    def _nombrar_seguido(self) -> None:
        elegidos = self._seguidos_elegidos()
        if len(elegidos) != 1:
            messagebox.showinfo("Ponerle nombre", "Elegí un expediente de la lista.")
            return
        s = elegidos[0]
        nombre = simpledialog.askstring("Nombre del expediente", f"Nombre o tema con que conocen {s.expediente} "
                                        "(dejalo vacío para quitarlo):", initialvalue=s.alias, parent=self)
        if nombre is None:
            return
        s.alias = " ".join(nombre.split())
        self._guardar_seguimiento()

    def _agrupar_elegidos(self, grupo: str | None = None) -> None:
        elegidos = self._seguidos_elegidos()
        if not elegidos:
            messagebox.showinfo("Agrupar", "Elegí uno o más expedientes de la lista.")
            return
        if grupo is None:
            existentes = ", ".join(self.lista_seguimiento.grupos)
            grupo = simpledialog.askstring("Agrupar", "Grupo al que se suman (uno existente o uno nuevo):"
                                           + (f"\n\nGrupos: {existentes}" if existentes else ""), parent=self)
        if not grupo or not grupo.strip():
            return
        for s in elegidos:
            self.lista_seguimiento.sumar_a_grupo(s, grupo)
        self._guardar_seguimiento()

    def _sacar_del_grupo(self) -> None:
        grupo = self._grupo_elegido()
        if not grupo:
            return
        for s in self._seguidos_elegidos():
            self.lista_seguimiento.sacar_de_grupo(s, grupo)
        self._guardar_seguimiento()

    def _menu_seguimiento(self, evento) -> None:
        fila = self.arbol_seguimiento.identify_row(evento.y)
        m = self.menu_seguido
        m.delete(0, "end")
        if not fila:
            m.add_command(label="Marcar todos", command=lambda: self._elegir_todos(True))
            m.add_separator()
            m.add_command(label="Vaciar la lista de seguimiento…", command=self._vaciar_seguimiento)
            m.tk_popup(evento.x_root, evento.y_root)
            return
        if fila not in self._marcados:
            self._marcados = set()
            self.arbol_seguimiento.selection_set(fila)
            self._marcar_elegidos()
        m.add_command(label="Ponerle nombre…", command=self._nombrar_seguido)
        sub = tk.Menu(m, tearoff=False)
        for g in self.lista_seguimiento.grupos:
            sub.add_command(label=g, command=lambda g=g: self._agrupar_elegidos(g))
        if self.lista_seguimiento.grupos:
            sub.add_separator()
        sub.add_command(label="Grupo nuevo…", command=self._agrupar_elegidos)
        m.add_cascade(label="Agregar al grupo", menu=sub)
        if self._grupo_elegido():
            m.add_command(label=f"Sacar del grupo «{self._grupo_elegido()}»", command=self._sacar_del_grupo)
        m.add_separator()
        m.add_command(label="Ver la ficha", command=self._ficha_seguimiento)
        m.add_command(label="Generar el informe completo", command=self._informe_seguido)
        m.add_command(label="Quitar de la lista", command=self._quitar_seguimiento)
        m.add_separator()
        m.add_command(label="Marcar todos", command=lambda: self._elegir_todos(True))
        m.add_command(label="Vaciar la lista de seguimiento…", command=self._vaciar_seguimiento)
        m.tk_popup(evento.x_root, evento.y_root)

    def _informe_seguido(self) -> None:
        elegidos = self._seguidos_elegidos()
        if not elegidos or (self.hilo and self.hilo.is_alive()):
            return
        self.modos.select(0)
        self.txt_expedientes.delete("1.0", "end")
        self.txt_expedientes.insert("1.0", "\n".join(s.expediente for s in elegidos))
        self.var_tipo.set(TIPO_AUTOMATICO)
        self._generar()

    def _nuevo_grupo(self) -> None:
        nombre = simpledialog.askstring("Grupo nuevo", "Nombre del grupo (p. ej. «Universidades»):", parent=self)
        if not nombre or not nombre.strip():
            return
        self.var_seg_grupo.set(self.lista_seguimiento.crear_grupo(nombre))
        self._guardar_seguimiento()

    def _renombrar_grupo(self) -> None:
        grupo = self._grupo_elegido()
        if not grupo:
            messagebox.showinfo("Renombrar grupo", "Elegí arriba el grupo que querés renombrar.")
            return
        nuevo = simpledialog.askstring("Renombrar grupo", "Nombre nuevo:", initialvalue=grupo, parent=self)
        if not nuevo or nuevo.strip() == grupo:
            return
        try:
            self.var_seg_grupo.set(self.lista_seguimiento.renombrar_grupo(grupo, nuevo))
        except ValueError as e:
            messagebox.showwarning("Renombrar grupo", str(e))
            return
        self._guardar_seguimiento()

    def _borrar_grupo(self) -> None:
        grupo = self._grupo_elegido()
        if not grupo:
            messagebox.showinfo("Borrar grupo", "Elegí arriba el grupo que querés borrar.")
            return
        if messagebox.askyesno("Borrar grupo", f"¿Borrar el grupo «{grupo}»? Sus expedientes siguen en la lista."):
            self.lista_seguimiento.borrar_grupo(grupo)
            self.var_seg_grupo.set(TODOS_LOS_SEGUIDOS)
            self._guardar_seguimiento()

    def _ficha_seguimiento(self) -> None:
        elegidos = self._seguidos_elegidos()
        s = elegidos[0] if elegidos else None
        if s and s.foto and s.foto.get("url"):
            webbrowser.open(s.foto["url"])
        elif s:
            messagebox.showinfo("Sin revisar", "Todavía no se revisó este expediente: presioná «Revisar novedades».")

    def _revisar_seguimiento(self) -> None:
        if self.hilo and self.hilo.is_alive():
            return
        grupo = self._grupo_elegido()
        elegidos = self.lista_seguimiento.del_grupo(grupo)
        if not elegidos:
            messagebox.showinfo("Lista vacía", f"El grupo «{grupo}» no tiene expedientes." if grupo else
                                "Agregá al menos un expediente a la lista de seguimiento.")
            return
        opciones = OpcionesSeguimiento(buscar_reuniones=self.var_seg_reuniones.get(),
                                       incluir_asesores=self.var_asesores.get(),
                                       formatos=("html", "md") if self.var_seg_archivo.get() else (),
                                       carpeta_salida=Path(self.var_carpeta.get()).expanduser())
        self._guardar_preferencias()
        self.cancelar.clear()
        self._registro(f"— Revisión de seguimiento ({len(elegidos)} expedientes"
                       + (f", grupo «{grupo}»)" if grupo else ")"))
        self._ocupado(True)
        self.hilo = threading.Thread(target=self._trabajo_seguimiento, args=(opciones, grupo), daemon=True)
        self.hilo.start()

    def _trabajo_seguimiento(self, opciones: OpcionesSeguimiento, grupo: str | None = None) -> None:
        cliente = self._nuevo_cliente()
        hechos, fallidos = 0, []

        def avisar(evento, mensaje="", **datos):
            self.cola.put((evento, mensaje, datos))

        try:
            res = revisar(self.lista_seguimiento, cliente, opciones, avisar, grupo=grupo)
            self.cola.put(("resultado", "", {"resultado": res}))
            hechos = 1
        except Cancelado:
            self.cola.put(("log", "Revisión cancelada.", {}))
        except Exception as e:  # noqa: BLE001
            fallidos.append(mensaje_de_error(e))
            self.cola.put(("log", traceback.format_exc(), {}))
        self.cola.put(("fin", "", {"hechos": hechos, "fallidos": fallidos, "carpeta": str(opciones.carpeta_salida),
                                   "pedidos": cliente.pedidos_red, "cache": cliente.pedidos_cache}))

    def _filas_elegidas(self) -> list[tuple]:
        """(ident, enlace a la ficha) de las filas elegidas en «Expedientes» (búsqueda por tema o asuntos entrados)."""
        sel = [int(i) for i in self.arbol_expedientes.selection()]
        if isinstance(self.actual, ResultadoTematico):
            return [(self.actual.items[i].hallazgo.ident, self.actual.items[i].url) for i in sel]
        if isinstance(self.actual, asuntos_entrados.ResultadoAsuntos):
            return [(self._ae_lista[i].ident, self._ae_lista[i].url_ficha) for i in sel if i < len(self._ae_lista)]
        return []

    def _menu_expedientes(self, evento) -> None:
        fila = self.arbol_expedientes.identify_row(evento.y)
        if fila:
            if fila not in self.arbol_expedientes.selection():
                self.arbol_expedientes.selection_set(fila)
            self.menu_expediente.tk_popup(evento.x_root, evento.y_root)

    def _accion_expediente(self, que: str) -> None:
        filas = self._filas_elegidas()
        if not filas:
            if que == "seguir":
                messagebox.showinfo("Elegí expedientes", "Elegí uno o más expedientes en la lista «Expedientes» de la "
                                                         "derecha (Ctrl + clic para varios).")
            return
        ident, url = filas[0]
        if que == "ficha":
            webbrowser.open(url)
        elif que == "copiar":
            self.clipboard_clear()
            self.clipboard_append("\n".join(x.corto for x, _u in filas))
        elif que == "seguir":
            idents = [x for x, _u in filas]
            self._sumar_a_seguimiento([x.corto for x in idents], {x.corto: x.tipo for x in idents})
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

    # ---------------------------------------------------- asuntos entrados
    def _estado_asuntos(self) -> None:
        r = self.registro_ae
        if r.iniciado:
            self.var_ae_ayuda.set(f"Se buscan los DAE posteriores al {r.ultimo_dae[0]}/{r.ultimo_dae[1]}. Si cambiás la "
                                  "fecha, la búsqueda empieza de nuevo desde ella.")
            cuando = f"{datetime.fromisoformat(r.revisado):%d/%m/%Y, %H:%M} h" if r.revisado else ""
            self.var_ae_info.set(f"⟳  Última revisión: {cuando} · DAE {r.ultimo_dae[0]}/{r.ultimo_dae[1]}")
        else:
            self.var_ae_ayuda.set("Primera vez: fecha de Mesa de Entradas desde la que buscar (dd/mm/aaaa). Después "
                                  "solo se traen los asuntos nuevos.")
            self.var_ae_info.set("")

    def _buscar_asuntos(self) -> None:
        if self.hilo and self.hilo.is_alive():
            return
        from .util import parsear_fecha
        desde = parsear_fecha(self.var_ae_desde.get().strip())
        if desde is None:
            messagebox.showinfo("Fecha", "Escribí la fecha de partida como dd/mm/aaaa, por ejemplo 01/10/2026.")
            return
        r = self.registro_ae
        if r.iniciado and r.desde and desde.isoformat() != r.desde:
            if not messagebox.askyesno("Empezar de nuevo", f"La revisión venía desde el {fmt_fecha(date.fromisoformat(r.desde))}. "
                                                           f"¿Empezar de nuevo desde el {fmt_fecha(desde)}?"):
                return
            r.ultimo_dae, r.desde = None, None
        self.cancelar.clear()
        self._registro("— Asuntos entrados")
        self._ocupado(True)

        def trabajo():
            cliente = self._nuevo_cliente()
            hechos, fallidos = 0, []
            try:
                res = asuntos_entrados.revisar(cliente, r, None if r.iniciado else desde,
                                               lambda ev, msg="", **d: self.cola.put((ev, msg, d)))
                self.cola.put(("resultado", "", {"resultado": res}))
                hechos = 1
            except Cancelado:
                self.cola.put(("log", "Consulta cancelada.", {}))
            except Exception as e:  # noqa: BLE001
                fallidos.append(mensaje_de_error(e))
                self.cola.put(("log", traceback.format_exc(), {}))
            self.cola.put(("fin", "", {"hechos": hechos, "fallidos": fallidos, "carpeta": self.var_carpeta.get(),
                                       "pedidos": cliente.pedidos_red, "cache": cliente.pedidos_cache}))

        self.hilo = threading.Thread(target=trabajo, daemon=True)
        self.hilo.start()

    def _ver_ultimos_asuntos(self) -> None:
        r = self.registro_ae
        if not r.iniciado:
            messagebox.showinfo("Sin revisiones", "Todavía no se buscaron asuntos entrados.")
            return
        daes = [f"{r.ultimo_dae[0]}/{r.ultimo_dae[1]}"]
        self._mostrar(asuntos_entrados.ResultadoAsuntos(list(r.ultimos_asuntos), daes, r.desde))

    def _filtro_asuntos(self, asuntos: list | None = None) -> list:
        tipos = {codigo for codigo, var in self.vars_ae_tipos.items() if var.get()}
        origen = self.var_ae_origen.get()
        return asuntos_entrados.filtrar(self.actual.asuntos if asuntos is None else asuntos,
                                        None if len(tipos) == len(TIPOS_TEMA) else tipos,
                                        None if origen == TODOS_ORIGENES else origen.split(" ")[0],
                                        self.var_ae_texto.get())

    def _texto_filtros_asuntos(self) -> str:
        partes = []
        tipos = [nombre for codigo, nombre in TIPOS_TEMA if self.vars_ae_tipos[codigo].get()]
        if len(tipos) != len(TIPOS_TEMA):
            partes.append("tipos: " + ", ".join(tipos).lower())
        if self.var_ae_origen.get() != TODOS_ORIGENES:
            partes.append("origen: " + self.var_ae_origen.get())
        if self.var_ae_texto.get().strip():
            partes.append(f"palabras: {self.var_ae_texto.get().strip()}")
        return "; ".join(partes)

    def _informe_asuntos(self, res) -> None:
        """Con la casilla marcada, guarda el informe de lo que muestran los filtros (Word y HTML)."""
        from . import informe_asuntos
        try:
            informe_asuntos.escribir(res, self._filtro_asuntos(res.asuntos), Path(self.var_carpeta.get()).expanduser(),
                                     filtros=self._texto_filtros_asuntos())
            self._registro("Informe de asuntos entrados: " + ", ".join(str(p) for p in res.archivos.values()))
        except OSError as e:
            messagebox.showwarning("No se pudo guardar el informe", str(e))

    def _refiltrar_asuntos(self) -> None:
        if isinstance(self.actual, asuntos_entrados.ResultadoAsuntos):
            self._mostrar_asuntos(self.actual)

    def _mostrar_asuntos(self, r) -> None:
        self._estado_asuntos()
        self._pestanias_visibles(True)
        lista = self._ae_lista = self._filtro_asuntos()
        t = self.txt_resumen
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._enlaces.clear()
        t.insert("end", "Asuntos entrados\n", "suave")
        t.insert("end", (f"Desde el {fmt_fecha(date.fromisoformat(r.desde))}" if r.desde else "Asuntos nuevos") + "\n",
                 "numero")
        t.insert("end", asuntos_entrados.resumen(r, len(lista)) + "\n", "extracto")
        if lista:
            t.insert("end", "Por tipo\n", "rotulo")
            conteo: dict[str, int] = {}
            for a in lista:
                nombre = asuntos_entrados.TIPOS.get(a.tipo, "Otros")
                conteo[nombre] = conteo.get(nombre, 0) + 1
            for nombre, k in sorted(conteo.items(), key=lambda x: -x[1]):
                t.insert("end", f"• {nombre}: {k}\n", "vineta")
            t.insert("end", "\nLa lista está en la pestaña «Expedientes»: elegí los que quieras y sumalos al "
                            "seguimiento.\n", ("vineta", "suave"))
        for aviso in r.advertencias:
            t.insert("end", f"• {aviso}\n", ("vineta", "suave"))
        t.configure(state="disabled")
        a = self.arbol_expedientes
        a.heading("etapa", text="Entrada y giro")
        a.delete(*a.get_children())
        for i, x in enumerate(lista):
            entrada = fmt_fecha(x.fecha_d) + (f" · {', '.join(x.giros)}" if x.giros else "")
            a.insert("", "end", iid=str(i), values=(x.expediente, x.tipo, entrada, x.extracto))
        for formato, boton in (("docx", self.btn_word), ("html", self.btn_html), ("xlsx", self.btn_excel)):
            boton.state(["!disabled"] if formato in r.archivos else ["disabled"])
        self.btn_ficha.state(["disabled"])
        self.btn_copiar.state(["!disabled"])
        self.pestanias.select(self.arbol_expedientes.master if lista else 0)

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
        if r.od:
            t.insert("end", f"Orden del Día N° {r.od}\n", "numero")
            t.insert("end", "Integrada por ", "suave")
            for fragmento in integrantes_od(r):
                self._enlace(fragmento.texto, fragmento.url)
            t.insert("end", "\n" + texto_od(r) + "\n", "suave")
            t.insert("end", f.id.corto + "\n", "situacion")
        else:
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
            elif isinstance(self.actual, asuntos_entrados.ResultadoAsuntos):
                texto = asuntos_entrados.resumen(self.actual, len(self._ae_lista)) + "\n\n" + "\n".join(
                    f"{x.expediente} ({x.tipo}, {fmt_fecha(x.fecha_d)}): {x.extracto}" for x in self._ae_lista)
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
            "Orden del día: si escribís «OD 413/26», el informe es el del despacho completo; sus expedientes "
            "dejan de tramitar por separado y la ficha que se muestra es la del expediente cabecera.\n\n"
            "Seguimiento: guarda una lista de expedientes (u órdenes del día), con el nombre con que los conocen y "
            "agrupados como quieras; al revisar un grupo, avisa qué cambió desde la revisión anterior (giros, "
            "dictámenes, votaciones, sanción, convocatorias y caducidad cercana).\n\n"
            "Asuntos entrados: lee el Diario de Asuntos Entrados (DAE) del Senado y muestra lo que ingresó desde la "
            "última revisión (la primera vez, desde la fecha que indiques); podés filtrarlo y sumarlo al "
            "seguimiento.\n\n"
            "Sesión: si la sesión ya se hizo, lee la versión taquigráfica y suma a cada asunto las votaciones y la "
            "versión revisada del proyecto, con las modificaciones aprobadas en el recinto en negrita.\n\n"
            "Por tema: busca en el Senado los expedientes cuyo extracto menciona las palabras del eje, filtra por "
            "años, origen, tipo y comisión, y arma un informe con la etapa de cada uno, en Word, HTML y Excel.\n\n"
            "4. Deduce la situación actual y estima la caducidad (Ley 13.640). Es orientativa: si importa, "
            "verificala en la fuente.\n\n"
            "Si algo no se lee bien, activá «Herramientas → Guardar las páginas descargadas» y enviá esa carpeta "
            "a quien mantiene el programa."))

    def _acerca(self) -> None:
        messagebox.showinfo("Acerca del programa", (
            f"{TITULO} (SIP – HSN), versión {__version__}\n\n"
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
            "seguimiento_archivo": self.var_seg_archivo.get(),
            "asuntos_informe": self.var_ae_informe.get(),
            "sesion_formatos": [f for f, v in self.vars_ses_formatos.items() if v.get()],
            "sesion_taquigrafica": self.var_ses_taquigrafica.get(),
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
        try:
            # Identidad propia en la barra de tareas: sin esto, con «python app.py» aparece el ícono de Python.
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HSenado.InformeExpedientes")
        except Exception:
            pass
    app = Aplicacion()
    app.mainloop()
