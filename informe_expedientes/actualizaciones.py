"""Versiones nuevas del programa y manual de usuario, publicados en GitHub Releases.

Cada compilación del .exe se publica como una versión «v1.1.4» con el archivo InformeExpediente.exe; el
manual, en la versión «manual». Al abrir, el programa consulta la lista de versiones (una vez por día) y,
si hay una más nueva, ofrece instalarla con la lista de cambios: descarga el .exe nuevo y lo reemplaza al
cerrar. El anterior queda guardado como «InformeExpediente.anterior.exe», para volver a él si hace falta.
"""

from __future__ import annotations

import hashlib
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
    sha256: str = ""             # huella del .exe según GitHub («digest» del archivo; vacío si no la informa)


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
                                 int(archivo.get("size") or 0),
                                 (archivo.get("digest") or "").removeprefix("sha256:").lower()))
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
    incompleta o no coincide con la huella SHA-256 que publica GitHub: en ese caso se borra lo descargado y
    el .exe actual no se toca."""
    if not version.exe:
        raise OSError("Esta versión no trae el archivo .exe.")
    actual = Path(sys.executable)
    nuevo = actual.with_name(actual.stem + ".nuevo.exe")
    avisar("Descargando la versión nueva…")
    bajado = 0
    huella = hashlib.sha256()
    try:
        with requests.get(version.exe, stream=True, timeout=60, headers={"User-Agent": config.USER_AGENT}) as r:
            r.raise_for_status()
            with open(nuevo, "wb") as f:
                for parte in r.iter_content(1 << 16):
                    f.write(parte)
                    bajado += len(parte)
                    huella.update(parte)
    except requests.RequestException as e:
        nuevo.unlink(missing_ok=True)
        raise OSError(f"Se cortó la descarga ({e}). Probá de nuevo más tarde.") from e
    if not bajado or (version.tamano and bajado != version.tamano):
        nuevo.unlink(missing_ok=True)
        raise OSError(f"La descarga quedó incompleta ({bajado:,} de {version.tamano:,} bytes). "
                      "Probá de nuevo más tarde.".replace(",", "."))
    if version.sha256 and huella.hexdigest() != version.sha256:
        nuevo.unlink(missing_ok=True)
        raise OSError("El archivo descargado no coincide con el publicado en GitHub. No se instaló; "
                      "avisá a quien mantiene el programa.")
    # El .exe actual queda como «.anterior.exe», por si la versión nueva anda mal (Ayuda → Volver a la versión
    # anterior).
    return _bat_reemplazo(nuevo, actual, f"copy /y \"{actual}\" \"{archivo_anterior()}\" >nul\r\n")


def archivo_anterior() -> Path:
    actual = Path(sys.executable)
    return actual.with_name(actual.stem + ".anterior.exe")


def hay_anterior() -> bool:
    """True si quedó guardada la versión anterior a la última actualización."""
    return es_ejecutable() and archivo_anterior().exists()


def volver_a_anterior() -> Path:
    """Deja preparado volver a la versión anterior al cerrar el programa; devuelve el .bat como instalar()."""
    if not hay_anterior():
        raise OSError("No quedó guardada ninguna versión anterior.")
    return _bat_reemplazo(archivo_anterior(), Path(sys.executable))


def _bat_reemplazo(nuevo: Path, actual: Path, antes: str = "") -> Path:
    """.bat que espera a que se cierre el programa, pone `nuevo` en lugar de `actual` y lo vuelve a abrir.

    El .exe de un solo archivo corre en dos procesos: el lanzador sigue unos segundos después de que termina el
    programa (borra sus archivos temporales) y mientras tanto Windows no deja reemplazar el .exe. Por eso el
    reemplazo se reintenta hasta 30 veces, una por segundo, en vez de probar una sola vez.

    Para esperar un segundo se usa ping y no timeout: el .bat corre sin ventana y timeout, sin consola, falla
    en el acto («Input redirection is not supported»), con lo que los reintentos se agotaban enseguida."""
    pausa = "ping -n 2 127.0.0.1 >nul\r\n"
    bat = Path(tempfile.gettempdir()) / "actualizar_informe_expediente.bat"
    bat.write_text(
        "@echo off\r\n"
        f":espera\r\ntasklist /FI \"PID eq {os.getpid()}\" | find \"{os.getpid()}\" >nul || goto cerrado\r\n"
        + pausa +
        "goto espera\r\n"
        ":cerrado\r\n"
        + antes +
        "set intentos=0\r\n"
        ":mover\r\n"
        f"move /y \"{nuevo}\" \"{actual}\" >nul 2>&1 && goto listo\r\n"
        "set /a intentos+=1\r\n"
        "if %intentos% geq 30 goto listo\r\n"
        + pausa +
        "goto mover\r\n"
        ":listo\r\n"
        f"start \"\" \"{actual}\"\r\n"
        "del \"%~f0\"\r\n", encoding="mbcs" if os.name == "nt" else "utf-8")
    return bat


def limpiar_restos() -> None:
    """Borra un «.nuevo.exe» que quedó de una actualización que no llegó a reemplazar el .exe (las versiones
    anteriores probaban una sola vez). Se llama al abrir el programa."""
    if not es_ejecutable():
        return
    actual = Path(sys.executable)
    try:
        actual.with_name(actual.stem + ".nuevo.exe").unlink(missing_ok=True)
    except OSError:
        pass


def cambios(notas: str, maximo: int = 8) -> list[str]:
    """Los títulos de la lista de cambios que arma GitHub en las notas de la versión.

    «* Actualizaciones más seguras by @usuario in https://github.com/…/pull/16» → «Actualizaciones más seguras».
    """
    titulos = []
    for renglon in notas.splitlines():
        m = re.match(r"\s*[*-]\s+(.+?)(?:\s+by\s+@\S+)?(?:\s+in\s+https?://\S+)?\s*$", renglon)
        if m:
            titulos.append(m.group(1))
    if len(titulos) > maximo:
        titulos = titulos[:maximo] + [f"y {len(titulos) - maximo} cambios más"]
    return titulos


def lanzar_reemplazo(bat: Path) -> None:
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                     close_fds=True)


def manual() -> str:
    """El manual incluido en el .exe si está; si no, la dirección del PDF en Releases."""
    return str(MANUAL_LOCAL) if MANUAL_LOCAL.exists() else URL_MANUAL


__all__ = ["Version", "ultima", "hay_nueva", "instalar", "lanzar_reemplazo", "manual", "es_ejecutable", "clave",
           "cambios", "hay_anterior", "volver_a_anterior", "archivo_anterior",
           "limpiar_restos"]
