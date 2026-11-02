"""Resumen diario: novedades de la lista de seguimiento y asuntos entrados nuevos, por correo y en un aviso.

Es opcional y lo configura cada usuario en su PC (Herramientas → Resumen diario (correo y aviso)…): a qué
direcciones, qué grupos del seguimiento, si suma los asuntos entrados (con filtros de tipo y palabras),
a qué hora y cómo se envía. Una tarea programada de Windows corre todos los días
`InformeExpediente.exe --resumen-diario`, que arma el resumen y lo manda.

Se envía desde la cuenta de Gmail de la oficina, creada solo para esto: el usuario solo indica a qué
dirección quiere recibirlo. La cuenta y su contraseña de aplicación se leen, en este orden, de:

1. `cuenta_envio.txt` junto al .exe (o junto a app.py): sirve para cambiar la contraseña editando un archivo
   en la carpeta compartida, sin recompilar;
2. la variable de entorno INFORME_CUENTA_ENVIO, con el mismo contenido;
3. `recursos/cuenta_envio.txt`, que el workflow del .exe arma con los secretos del repositorio.

El archivo tiene dos renglones: la dirección y la contraseña de aplicación (los renglones que empiezan con
# se ignoran).

El correo lleva su propio registro de lo ya avisado (`correo_seguimiento.json` y
`correo_asuntos_entrados.json`), así no se pierden las novedades que el usuario revisa a mano en la ventana.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import smtplib
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from pathlib import Path

from . import __version__, asuntos_entrados, config, seguimiento
from .cliente import Cliente

TAREA = "Informe de Expedientes - resumen diario"
GMAIL = ("smtp.gmail.com", 587)
NOMBRE_REMITENTE = "Resumen parlamentario"
ARCHIVO_CUENTA = "cuenta_envio.txt"


def archivo_config() -> Path:
    return config.carpeta_app() / "correo.json"


@dataclass
class ConfigCorreo:
    activo: bool = False
    destinatarios: list[str] = field(default_factory=list)
    hora: str = "07:30"
    seguimiento: bool = True
    grupos: list[str] = field(default_factory=list)          # vacío: toda la lista
    asuntos: bool = True
    asuntos_tipos: list[str] = field(default_factory=lambda: ["PL", "PR", "PC", "PD", "OTROS"])
    asuntos_palabras: str = ""
    enviar_vacio: bool = False                                # también los días sin novedades
    por_correo: bool = True                                   # mandar el resumen por correo
    aviso: bool = True                                        # mostrar un aviso en pantalla con las novedades
    ultimo: str = ""                                          # fecha (ISO) del último resumen armado

    @classmethod
    def cargar(cls) -> "ConfigCorreo":
        try:
            datos = json.loads(archivo_config().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        conocidos = {k: v for k, v in datos.items() if k in cls.__dataclass_fields__}
        return cls(**conocidos)

    def guardar(self) -> None:
        archivo_config().parent.mkdir(parents=True, exist_ok=True)
        archivo_config().write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================ contraseña (DPAPI)

def _dpapi(datos: bytes, cifrar: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    entrada = BLOB(len(datos), ctypes.cast(ctypes.create_string_buffer(datos, len(datos)), ctypes.POINTER(ctypes.c_char)))
    salida = BLOB()
    funcion = ctypes.windll.crypt32.CryptProtectData if cifrar else ctypes.windll.crypt32.CryptUnprotectData
    if not funcion(ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(salida)):
        raise OSError("No se pudo cifrar o descifrar la contraseña con la cuenta de Windows.")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(salida.pbData)


def cifrar_clave(clave: str) -> str:
    if not clave:
        return ""
    return base64.b64encode(_dpapi(clave.encode("utf-8"), True)).decode()


def descifrar_clave(guardada: str) -> str:
    if not guardada:
        return ""
    return _dpapi(base64.b64decode(guardada), False).decode("utf-8")


# ================================================================ armar resumen

@dataclass
class Resumen:
    seguimiento: seguimiento.ResultadoSeguimiento | None = None
    asuntos: list[asuntos_entrados.Asunto] = field(default_factory=list)
    daes: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    generado: datetime = field(default_factory=datetime.now)

    @property
    def revisiones(self) -> list[seguimiento.Revision]:
        """Las que tienen novedades de verdad (no solo la «Primera revisión»)."""
        if not self.seguimiento:
            return []
        return [r for r in self.seguimiento.revisiones if any(n.clase != "alta" for n in r.novedades)]

    @property
    def vacio(self) -> bool:
        return not (self.revisiones or self.asuntos or self.errores)


def _lista_propia(principal: seguimiento.Lista) -> seguimiento.Lista:
    """La lista del usuario (expedientes, nombres y grupos) con las «fotos» propias del correo."""
    propia = seguimiento.Lista(config.carpeta_app() / "correo_seguimiento.json")
    fotos = {s.expediente: (s.foto, s.revisado) for s in propia.seguidos}
    propia.seguidos = []
    for s in principal.seguidos:
        copia = copy.deepcopy(s)
        copia.foto, copia.revisado = fotos.get(s.expediente, (None, None))
        propia.seguidos.append(copia)
    propia.grupos = list(principal.grupos)
    return propia


def armar(cfg: ConfigCorreo, cliente: Cliente, avisar=lambda *a, **k: None, hoy: date | None = None) -> Resumen:
    res = Resumen()
    if cfg.seguimiento:
        lista = _lista_propia(seguimiento.Lista())
        if cfg.grupos:
            elegidos = {s.expediente for s in lista.seguidos if set(s.grupos) & set(cfg.grupos)}
            lista.seguidos = [s for s in lista.seguidos if s.expediente in elegidos]
        try:
            res.seguimiento = seguimiento.revisar(lista, cliente, seguimiento.OpcionesSeguimiento(
                buscar_reuniones=False, formatos=()), avisar, hoy=hoy)
        except Exception as e:  # noqa: BLE001 - el resumen sale igual con lo demás
            res.errores.append(f"No se pudo revisar la lista de seguimiento: {e}")
    if cfg.asuntos:
        registro = asuntos_entrados.Registro.cargar(config.carpeta_app() / "correo_asuntos_entrados.json")
        desde = None if registro.iniciado else (hoy or date.today()) - timedelta(days=1)
        try:
            r = asuntos_entrados.revisar(cliente, registro, desde, avisar, hoy=hoy)
            res.daes = r.daes
            res.asuntos = asuntos_entrados.filtrar(r.asuntos, set(cfg.asuntos_tipos) or None,
                                                   texto=cfg.asuntos_palabras)
        except Exception as e:  # noqa: BLE001
            res.errores.append(f"No se pudieron leer los asuntos entrados: {e}")
    return res


def asunto_correo(res: Resumen) -> str:
    partes = []
    if res.revisiones:
        partes.append(f"{len(res.revisiones)} con novedades")
    if res.asuntos:
        partes.append(f"{len(res.asuntos)} asuntos entrados")
    return f"Resumen parlamentario del {res.generado:%d/%m/%Y}: " + (", ".join(partes) or "sin novedades")


def html(res: Resumen) -> str:
    def e(t) -> str:
        return escape(str(t or ""), quote=True)

    def enlace(texto, url) -> str:
        return f'<a href="{e(url)}" style="color:#1A64AB">{e(texto)}</a>' if url else e(texto)

    azul, gris = "#114E9A", "#5A6478"
    partes = [f'<div style="font-family:Calibri,Arial,sans-serif;font-size:14px;color:#292F3D;max-width:760px">',
              f'<div style="background:#1A64AB;color:#fff;padding:14px 18px;font-family:Georgia,serif;font-size:20px">'
              f"Resumen parlamentario — {res.generado:%d/%m/%Y}</div>"]
    if res.errores:
        partes.append('<div style="background:#FFF4DE;border-left:4px solid #E0A030;padding:8px 12px;margin:12px 0">'
                      + "<br>".join(e(x) for x in res.errores) + "</div>")
    if res.seguimiento is not None:
        partes.append(f'<h2 style="color:{azul};font-size:17px;margin:18px 0 6px">Lista de seguimiento</h2>')
        if not res.revisiones:
            partes.append(f'<p style="color:{gris}">Sin novedades en los expedientes seguidos.</p>')
        for r in res.revisiones:
            items = "".join(f"<li>{e(n.texto)}" + (f" {enlace('Ver', n.url)}" if n.url else "") + "</li>"
                            for n in r.novedades if n.clase != "alta")
            partes.append(f'<p style="margin:10px 0 2px"><b>{enlace(r.seguido.nombre, r.url)}</b>'
                          f' <span style="color:{gris}">— {e(r.situacion)}</span></p><ul style="margin:2px 0">{items}</ul>')
    if res.daes or res.asuntos:
        daes = (res.daes[-1] + (f" a {res.daes[0]}" if len(res.daes) > 1 else "")) if res.daes else ""
        partes.append(f'<h2 style="color:{azul};font-size:17px;margin:18px 0 6px">Asuntos entrados'
                      + (f" (DAE {e(daes)})" if daes else "") + "</h2>")
        if not res.asuntos:
            partes.append(f'<p style="color:{gris}">Sin asuntos nuevos con los filtros elegidos.</p>')
        else:
            filas = "".join(
                f'<tr><td style="padding:4px 8px;border-bottom:1px solid #B9C8DE;white-space:nowrap">'
                f"{enlace(a.expediente, a.url_ficha)}</td>"
                f'<td style="padding:4px 8px;border-bottom:1px solid #B9C8DE">{e(asuntos_entrados.TIPOS.get(a.tipo, a.tipo))}</td>'
                f'<td style="padding:4px 8px;border-bottom:1px solid #B9C8DE">{e(a.extracto)}</td></tr>' for a in res.asuntos)
            partes.append('<table style="border-collapse:collapse;font-size:13px"><tr style="background:#1A64AB;color:#fff">'
                          '<th style="padding:4px 8px;text-align:left">Expediente</th><th style="padding:4px 8px;'
                          'text-align:left">Tipo</th><th style="padding:4px 8px;text-align:left">Extracto</th></tr>'
                          f"{filas}</table>")
    partes.append(f'<p style="color:{gris};font-size:12px;margin-top:20px">Enviado automáticamente por el Sistema de '
                  f"Información Parlamentaria {e(__version__)}, con datos públicos de senado.gob.ar. Para cambiar qué "
                  "recibís: Herramientas → Resumen diario (correo y aviso).</p></div>")
    return "".join(partes)


def texto_plano(res: Resumen) -> str:
    lineas = [asunto_correo(res), ""]
    lineas += res.errores
    for r in res.revisiones:
        lineas.append(f"{r.seguido.nombre} — {r.situacion}")
        lineas += [f"  - {n.texto}" for n in r.novedades if n.clase != "alta"]
    for a in res.asuntos:
        lineas.append(f"{a.expediente}: {a.extracto}")
    return "\n".join(lineas)


# ===================================================================== envío

class ErrorCorreo(RuntimeError):
    pass


def _carpeta_programa() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _leer_cuenta(texto: str) -> tuple[str, str] | None:
    renglones = [x.strip() for x in texto.splitlines() if x.strip() and not x.strip().startswith("#")]
    if len(renglones) < 2 or "@" not in renglones[0]:
        return None
    # Google muestra la contraseña de aplicación en grupos de cuatro («abcd efgh ijkl mnop»): los espacios no van.
    return renglones[0], renglones[1].replace(" ", "")


def cuenta_envio() -> tuple[str, str] | None:
    """(dirección, contraseña de aplicación) de la cuenta de la oficina, o None si no está configurada."""
    fuentes = [_carpeta_programa() / ARCHIVO_CUENTA, None, Path(__file__).resolve().parent / "recursos" / ARCHIVO_CUENTA]
    for fuente in fuentes:
        if fuente is None:
            texto = os.environ.get("INFORME_CUENTA_ENVIO", "")
        else:
            try:
                texto = fuente.read_text(encoding="utf-8-sig")
            except OSError:
                continue
        cuenta = _leer_cuenta(texto)
        if cuenta:
            return cuenta
    return None


def enviar(cfg: ConfigCorreo, asunto: str, cuerpo_html: str, cuerpo_texto: str) -> None:
    """Envía por Gmail desde la cuenta de la oficina."""
    if not cfg.destinatarios:
        raise ErrorCorreo("No hay ninguna dirección de correo configurada.")
    cuenta = cuenta_envio()
    if cuenta is None:
        raise ErrorCorreo("El programa no tiene configurada la cuenta de envío de la oficina. Avisá a quien lo "
                          "mantiene.")
    usuario, clave = cuenta
    m = EmailMessage()
    m["Subject"], m["To"] = asunto, ", ".join(cfg.destinatarios)
    m["From"] = formataddr((NOMBRE_REMITENTE, usuario))
    m.set_content(cuerpo_texto)
    m.add_alternative(cuerpo_html, subtype="html")
    try:
        with smtplib.SMTP(*GMAIL, timeout=60) as s:
            s.starttls()
            s.login(usuario, clave)
            s.send_message(m)
    except smtplib.SMTPAuthenticationError as e:
        raise ErrorCorreo("La cuenta de envío de la oficina no aceptó la contraseña (puede haber cambiado). "
                          "Avisá a quien mantiene el programa.") from e
    except (OSError, smtplib.SMTPException) as e:
        raise ErrorCorreo(f"No se pudo enviar el correo: {e}") from e


def enviar_resumen(cfg: ConfigCorreo, cliente: Cliente, avisar=lambda *a, **k: None, forzar: bool = False) -> Resumen:
    """Arma el resumen y lo envía (salvo un día sin novedades, si así se configuró). Devuelve el resumen."""
    res = armar(cfg, cliente, avisar)
    if res.vacio and not (cfg.enviar_vacio or forzar):
        avisar("log", "Sin novedades: no se envía el correo.")
        return res
    enviar(cfg, asunto_correo(res), html(res), texto_plano(res))
    avisar("log", f"Resumen enviado a {', '.join(cfg.destinatarios)}.")
    return res


def archivo_ultimo_resumen() -> Path:
    return config.carpeta_app() / "ultimo_resumen.html"


def ejecutar_diario(cfg: ConfigCorreo, cliente: Cliente, avisar=lambda *a, **k: None, hoy: date | None = None,
                    forzar: bool = False, mostrar=None) -> Resumen | None:
    """Lo que corre la tarea programada: una vez por día arma el resumen, lo manda por correo y muestra el aviso.

    Si ese día ya se armó (por ejemplo, la tarea corrió a la hora y otra vez al iniciar sesión), no hace nada.
    Devuelve el resumen, o None si ya estaba hecho."""
    hoy = hoy or date.today()
    if cfg.ultimo == hoy.isoformat() and not forzar:
        avisar("log", "El resumen de hoy ya se armó.")
        return None
    res = armar(cfg, cliente, avisar, hoy)
    try:
        archivo_ultimo_resumen().write_text("<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
                                            f"<title>{escape(asunto_correo(res))}</title></head><body>"
                                            f"{html(res)}</body></html>", encoding="utf-8")
    except OSError:
        pass
    if cfg.por_correo and cfg.destinatarios and (not res.vacio or cfg.enviar_vacio):
        try:
            enviar(cfg, asunto_correo(res), html(res), texto_plano(res))
            avisar("log", f"Resumen enviado a {', '.join(cfg.destinatarios)}.")
        except ErrorCorreo as e:
            res.errores.append(f"No se pudo enviar el correo: {e}")
            avisar("log", f"Error: {e}")
    elif cfg.por_correo:
        avisar("log", "Sin novedades: no se envía el correo.")
    cfg.ultimo = hoy.isoformat()
    cfg.guardar()
    if cfg.aviso and not res.vacio:
        (mostrar or mostrar_aviso)(res)
    return res


# ============================================================ aviso en pantalla

def lineas_aviso(res: Resumen, maximo: int = 6) -> list[str]:
    """Las líneas del aviso: un renglón por expediente con novedades y la cuenta de asuntos entrados."""
    lineas = []
    for r in res.revisiones[:maximo]:
        primera = next(n.texto for n in r.novedades if n.clase != "alta")
        otras = sum(1 for n in r.novedades if n.clase != "alta") - 1
        lineas.append(f"{r.seguido.nombre}: {primera}" + (f" (y {otras} más)" if otras > 0 else ""))
    if len(res.revisiones) > maximo:
        lineas.append(f"… y {len(res.revisiones) - maximo} expedientes más con novedades.")
    if res.asuntos:
        lineas.append(f"{len(res.asuntos)} asunto{'s' if len(res.asuntos) != 1 else ''} "
                      f"entrado{'s' if len(res.asuntos) != 1 else ''} nuevo{'s' if len(res.asuntos) != 1 else ''}.")
    lineas += res.errores
    return lineas


def abrir_programa() -> None:
    if getattr(sys, "frozen", False):
        orden = [sys.executable]
    else:
        python = Path(sys.executable)
        sin_ventana = python.with_name("pythonw.exe")
        orden = [str(sin_ventana if sin_ventana.exists() else python), str(Path(__file__).resolve().parent.parent / "app.py")]
    subprocess.Popen(orden, close_fds=True)


def mostrar_aviso(res: Resumen) -> None:
    """Ventanita en la esquina inferior derecha, por encima de las demás, con el resumen de novedades."""
    import tkinter as tk
    from tkinter import font as tkfont

    azul, papel, tinta, suave = "#1A64AB", "#FFFFFF", "#292F3D", "#5A6478"
    v = tk.Tk()
    v.title("Novedades parlamentarias")
    v.configure(bg=papel)
    v.attributes("-topmost", True)
    v.resizable(False, False)
    icono = Path(__file__).resolve().parent / "recursos" / "icono.ico"
    try:
        v.iconbitmap(default=str(icono))
    except tk.TclError:
        pass
    familias = set(tkfont.families(v))
    sans = next((f for f in ("Segoe UI", "Calibri", "Arial") if f in familias), "TkDefaultFont")
    tk.Label(v, text=f"Novedades parlamentarias — {res.generado:%d/%m/%Y}", bg=azul, fg="#FFFFFF",
             font=(sans, 12, "bold"), anchor="w", padx=14, pady=8).pack(fill="x")
    cuerpo = tk.Frame(v, bg=papel, padx=14, pady=10)
    cuerpo.pack(fill="both")
    for linea in lineas_aviso(res):
        tk.Label(cuerpo, text="• " + linea, bg=papel, fg=tinta, font=(sans, 10), justify="left", anchor="w",
                 wraplength=400).pack(fill="x", pady=1)
    botones = tk.Frame(v, bg=papel, padx=14, pady=10)
    botones.pack(fill="x")

    def boton(texto, comando, principal=False):
        tk.Button(botones, text=texto, command=comando, relief="flat", padx=10, pady=3, cursor="hand2",
                  bg=azul if principal else "#E6EEF9", fg="#FFFFFF" if principal else tinta,
                  activebackground="#0B3D7C" if principal else "#D8E4F7", font=(sans, 9)).pack(side="right", padx=(6, 0))

    def ver():
        try:
            os.startfile(archivo_ultimo_resumen())                       # noqa: S606 - solo en Windows
        except (AttributeError, OSError):
            import webbrowser
            webbrowser.open(archivo_ultimo_resumen().as_uri())
        v.destroy()

    def programa():
        abrir_programa()
        v.destroy()

    boton("Cerrar", v.destroy)
    boton("Abrir el programa", programa)
    boton("Ver el resumen", ver, principal=True)
    tk.Label(botones, text="Resumen diario", bg=papel, fg=suave, font=(sans, 8)).pack(side="left")
    v.update_idletasks()
    x = v.winfo_screenwidth() - v.winfo_reqwidth() - 24
    y = v.winfo_screenheight() - v.winfo_reqheight() - 72                # por encima de la barra de tareas
    v.geometry(f"+{x}+{y}")
    v.bell()
    v.mainloop()


# ========================================================== tarea programada

def orden_programa() -> str:
    """La línea que corre la tarea: el .exe o, desde el código, pythonw con app.py."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --resumen-diario'
    python = Path(sys.executable)
    sin_ventana = python.with_name("pythonw.exe")
    app = Path(__file__).resolve().parent.parent / "app.py"
    return f'"{sin_ventana if sin_ventana.exists() else python}" "{app}" --resumen-diario'


def programar(cfg: ConfigCorreo) -> None:
    """Crea (o borra, si está desactivado) la tarea diaria de Windows. Corre con la sesión del usuario."""
    if os.name != "nt":
        raise ErrorCorreo("La tarea programada solo está disponible en Windows.")
    if not cfg.activo:
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", TAREA], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return
    r = subprocess.run(["schtasks", "/Create", "/F", "/SC", "DAILY", "/TN", TAREA, "/TR", orden_programa(),
                        "/ST", cfg.hora], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise ErrorCorreo("No se pudo crear la tarea programada de Windows: " + (r.stderr or r.stdout).strip())
    # «Ejecutar la tarea lo antes posible si se omitió un inicio programado»: si a esa hora la PC estaba
    # apagada o sin la sesión iniciada, corre apenas el usuario entra. schtasks no tiene esa opción; PowerShell sí.
    ajuste = (f"$t = Get-ScheduledTask -TaskName '{TAREA}'; "
              "$t.Settings.StartWhenAvailable = $true; "
              "$t.Settings.DisallowStartIfOnBatteries = $false; $t.Settings.StopIfGoingOnBatteries = $false; "
              "$t.Settings.ExecutionTimeLimit = 'PT1H'; "
              "Set-ScheduledTask -InputObject $t | Out-Null")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ajuste], capture_output=True,
                       text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise ErrorCorreo("Se creó la tarea, pero no se pudo activar que corra al iniciar sesión si se perdió la "
                          "hora: " + (r.stderr or r.stdout).strip()[-300:])


__all__ = ["ConfigCorreo", "Resumen", "armar", "enviar", "enviar_resumen", "ejecutar_diario", "mostrar_aviso",
           "lineas_aviso", "programar", "ErrorCorreo",
           "cifrar_clave", "descifrar_clave", "cuenta_envio", "TAREA"]
