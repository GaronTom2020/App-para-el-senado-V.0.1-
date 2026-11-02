"""Versiones nuevas del programa y manual de usuario, publicados en GitHub Releases.

Cada compilación del .exe se publica como una versión «v0.4.0» con el archivo InformeExpediente.exe; el
manual, en la versión «manual». Al abrir, el programa consulta la lista de versiones (una vez por día) y,
si hay una más nueva, ofrece instalarla: descarga el .exe nuevo y lo reemplaza al cerrar.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import requests

from . import __version__, config

REPOSITORIO = "GaronTom2020/App-para-el-senado-V.0.1-"
URL_VERSIONES = f"https://api.github.com/repos/{REPOSITORIO}/releases?per_page=30"
URL_PAGINA = f"https://github.com/{REPOSITORIO}/releases"
URL_MANUAL = f"{URL_PAGINA}/download/manual/Manual-de-usuario.pdf"
MANUAL_LOCAL = Path(__file__).resolve().parent / "recursos" / "Manual-de-usuario.pdf"
NOMBRE_EXE = "InformeExpediente.exe"


@dataclass
class Version:
    numero: str
    pagina: str
    exe: str | None              # dirección de descarga del .exe, si la versión lo trae
    notas: str = ""
    tamano: int = 0              # bytes del .exe según GitHub (0 si no lo informa)


def clave(numero: str) -> tuple[int, ...]:
    """«v0.10.1» → (0, 10, 1), para comparar versiones."""
    return tuple(int(x) for x in re.findall(r"\d+", numero)[:4])


def ultima(espera: float = 8) -> Version | None:
    """La versión publicada más nueva (sin borradores ni prepublicaciones), o None si no se pudo consultar."""
    try:
        r = requests.get(URL_VERSIONES, timeout=espera, headers={"Accept": "application/vnd.github+json",
                                                                 "User-Agent": config.USER_AGENT})
        r.raise_for_status()
        datos = r.json()
    except (requests.RequestException, ValueError):
        return None
    versiones = []
    for v in datos:
        etiqueta = v.get("tag_name") or ""
        if v.get("draft") or v.get("prerelease") or not re.fullmatch(r"v?\d+(\.\d+)*", etiqueta):
            continue
        archivo = next((a for a in v.get("assets", []) if a.get("name", "").lower() == NOMBRE_EXE.lower()), {})
        versiones.append(Version(etiqueta.lstrip("v"), v.get("html_url") or URL_PAGINA,
                                 archivo.get("browser_download_url"), v.get("body") or "",
                                 int(archivo.get("size") or 0)))
    return max(versiones, key=lambda v: clave(v.numero), default=None)


def hay_nueva(espera: float = 8) -> Version | None:
    v = ultima(espera)
    return v if v and clave(v.numero) > clave(__version__) else None


def es_ejecutable() -> bool:
    """True si corre como .exe compilado (y no desde el código con Python)."""
    return bool(getattr(sys, "frozen", False))


def instalar(version: Version, avisar=lambda *_: None) -> Path:
    """Descarga el .exe nuevo y deja preparado el reemplazo, que ocurre cuando se cierra el programa.

    Devuelve el archivo .bat que hay que ejecutar antes de salir. Lanza OSError si no se puede escribir
    junto al .exe actual (por ejemplo, en una carpeta de red de solo lectura) o si la descarga quedó
    incompleta: en ese caso se borra lo descargado y el .exe actual no se toca."""
    if not version.exe:
        raise OSError("Esta versión no trae el archivo .exe.")
    actual = Path(sys.executable)
    nuevo = actual.with_name(actual.stem + ".nuevo.exe")
    avisar("Descargando la versión nueva…")
    bajado = 0
    try:
        with requests.get(version.exe, stream=True, timeout=60, headers={"User-Agent": config.USER_AGENT}) as r:
            r.raise_for_status()
            with open(nuevo, "wb") as f:
                for parte in r.iter_content(1 << 16):
                    f.write(parte)
                    bajado += len(parte)
    except requests.RequestException as e:
        nuevo.unlink(missing_ok=True)
        raise OSError(f"Se cortó la descarga ({e}). Probá de nuevo más tarde.") from e
    if not bajado or (version.tamano and bajado != version.tamano):
        nuevo.unlink(missing_ok=True)
        raise OSError(f"La descarga quedó incompleta ({bajado:,} de {version.tamano:,} bytes). "
                      "Probá de nuevo más tarde.".replace(",", "."))
    bat = Path(tempfile.gettempdir()) / "actualizar_informe_expediente.bat"
    bat.write_text(
        "@echo off\r\n"
        f":espera\r\ntasklist /FI \"PID eq {os.getpid()}\" | find \"{os.getpid()}\" >nul && "
        "(timeout /t 1 /nobreak >nul & goto espera)\r\n"
        f"move /y \"{nuevo}\" \"{actual}\" >nul\r\n"
        f"start \"\" \"{actual}\"\r\n"
        "del \"%~f0\"\r\n", encoding="mbcs" if os.name == "nt" else "utf-8")
    return bat


def lanzar_reemplazo(bat: Path) -> None:
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                     close_fds=True)


def manual() -> str:
    """El manual incluido en el .exe si está; si no, la dirección del PDF en Releases."""
    return str(MANUAL_LOCAL) if MANUAL_LOCAL.exists() else URL_MANUAL


__all__ = ["Version", "ultima", "hay_nueva", "instalar", "lanzar_reemplazo", "manual", "es_ejecutable", "clave"]
