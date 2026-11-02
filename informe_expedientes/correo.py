"""Resumen diario por correo: novedades de la lista de seguimiento y asuntos entrados nuevos.

Es opcional y lo configura cada usuario en su PC (Herramientas → Resumen diario por correo…): a qué
direcciones, qué grupos del seguimiento, si suma los asuntos entrados (con filtros de tipo y palabras),
a qué hora y cómo se envía. Una tarea programada de Windows corre todos los días
`InformeExpediente.exe --resumen-diario`, que arma el resumen y lo manda.

Se envía con el Outlook de la PC (no hace falta contraseña: usa la cuenta ya abierta) o por SMTP. La
contraseña de SMTP se guarda cifrada con la cuenta de Windows del usuario (DPAPI).

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
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from html import escape
from pathlib import Path

from . import __version__, asuntos_entrados, config, seguimiento
from .cliente import Cliente

TAREA = "Informe de Expedientes - resumen diario"
METODOS = {"outlook": "Outlook de esta PC", "smtp": "Servidor SMTP"}


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
    metodo: str = "outlook"
    smtp_servidor: str = ""
    smtp_puerto: int = 587
    smtp_tls: bool = True
    smtp_usuario: str = ""
    smtp_clave: str = ""                                      # cifrada (DPAPI), en base64
    remitente: str = ""

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
                  "recibís: Herramientas → Resumen diario por correo.</p></div>")
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


def enviar(cfg: ConfigCorreo, asunto: str, cuerpo_html: str, cuerpo_texto: str) -> None:
    if not cfg.destinatarios:
        raise ErrorCorreo("No hay ninguna dirección de correo configurada.")
    if cfg.metodo == "outlook":
        _por_outlook(cfg.destinatarios, asunto, cuerpo_html)
    else:
        _por_smtp(cfg, asunto, cuerpo_html, cuerpo_texto)


def _por_outlook(destinatarios: list[str], asunto: str, cuerpo_html: str) -> None:
    """Con el Outlook de la PC, por PowerShell (COM): usa la cuenta ya configurada, sin contraseña."""
    with tempfile.TemporaryDirectory(prefix="correo_") as carpeta:
        cuerpo = Path(carpeta) / "cuerpo.html"
        cuerpo.write_text(cuerpo_html, encoding="utf-8")
        script = Path(carpeta) / "enviar.ps1"
        script.write_text(
            "$ErrorActionPreference = 'Stop'\n"
            "$o = New-Object -ComObject Outlook.Application\n"
            "$m = $o.CreateItem(0)\n"
            f"$m.To = '{'; '.join(destinatarios).replace(chr(39), '')}'\n"
            f"$m.Subject = '{asunto.replace(chr(39), chr(39) * 2)}'\n"
            f"$m.HTMLBody = Get-Content -Raw -Encoding UTF8 '{cuerpo}'\n"
            "$m.Send()\n", encoding="utf-8-sig")
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-File", str(script)], capture_output=True, text=True, timeout=120,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise ErrorCorreo("Outlook no pudo enviar el correo. ¿Está instalado y con una cuenta configurada?\n"
                          + (r.stderr or r.stdout).strip()[-400:])


def _por_smtp(cfg: ConfigCorreo, asunto: str, cuerpo_html: str, cuerpo_texto: str) -> None:
    if not cfg.smtp_servidor:
        raise ErrorCorreo("Falta el servidor SMTP.")
    m = EmailMessage()
    m["Subject"], m["To"] = asunto, ", ".join(cfg.destinatarios)
    m["From"] = cfg.remitente or cfg.smtp_usuario or cfg.destinatarios[0]
    m.set_content(cuerpo_texto)
    m.add_alternative(cuerpo_html, subtype="html")
    try:
        with smtplib.SMTP(cfg.smtp_servidor, int(cfg.smtp_puerto), timeout=60) as s:
            if cfg.smtp_tls:
                s.starttls()
            if cfg.smtp_usuario:
                s.login(cfg.smtp_usuario, descifrar_clave(cfg.smtp_clave))
            s.send_message(m)
    except (OSError, smtplib.SMTPException) as e:
        raise ErrorCorreo(f"El servidor SMTP no aceptó el correo: {e}") from e


def enviar_resumen(cfg: ConfigCorreo, cliente: Cliente, avisar=lambda *a, **k: None, forzar: bool = False) -> Resumen:
    """Arma el resumen y lo envía (salvo un día sin novedades, si así se configuró). Devuelve el resumen."""
    res = armar(cfg, cliente, avisar)
    if res.vacio and not (cfg.enviar_vacio or forzar):
        avisar("log", "Sin novedades: no se envía el correo.")
        return res
    enviar(cfg, asunto_correo(res), html(res), texto_plano(res))
    avisar("log", f"Resumen enviado a {', '.join(cfg.destinatarios)}.")
    return res


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


__all__ = ["ConfigCorreo", "Resumen", "armar", "enviar", "enviar_resumen", "programar", "ErrorCorreo",
           "cifrar_clave", "descifrar_clave", "METODOS", "TAREA"]
