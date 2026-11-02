"""Informes en PDF: se imprime el HTML con Microsoft Edge (o Chrome) sin ventana.

Edge viene con Windows 10 y 11, así que no hace falta instalar nada. Si no se encuentra ningún navegador,
`ErrorPDF` lo explica y el resto de los formatos se guarda igual.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ESPERA = 120          # segundos como máximo por documento


class ErrorPDF(RuntimeError):
    pass


def navegador() -> str | None:
    """Ruta de Edge o Chrome (o de la variable INFORME_NAVEGADOR_PDF, si está definida)."""
    propio = os.environ.get("INFORME_NAVEGADOR_PDF")
    if propio and Path(propio).exists():
        return propio
    raices = [os.environ.get(v) for v in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
    for raiz in filter(None, raices):
        for relativa in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
            if (Path(raiz) / relativa).exists():
                return str(Path(raiz) / relativa)
    for nombre in ("msedge", "microsoft-edge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    return None


def html_a_pdf(origen: Path, destino: Path) -> Path:
    """Imprime el archivo HTML `origen` en `destino` (PDF)."""
    exe = navegador()
    if not exe:
        raise ErrorPDF("Para guardar en PDF hace falta Microsoft Edge o Google Chrome, y no se encontró ninguno.")
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="informe_pdf_") as perfil:
        orden = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer",
                 f"--user-data-dir={perfil}", f"--print-to-pdf={destino}", Path(origen).resolve().as_uri()]
        try:
            subprocess.run(orden, capture_output=True, timeout=ESPERA,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ErrorPDF(f"No se pudo generar el PDF: {e}") from e
    if not destino.exists() or destino.stat().st_size == 0:
        raise ErrorPDF("El navegador no generó el PDF.")
    return destino


def texto_a_pdf(html: str, destino: Path) -> Path:
    """Igual que `html_a_pdf`, a partir del texto HTML."""
    with tempfile.TemporaryDirectory(prefix="informe_pdf_") as carpeta:
        origen = Path(carpeta) / "informe.html"
        origen.write_text(html, encoding="utf-8")
        return html_a_pdf(origen, destino)


def desde_html(escribir_html):
    """Convierte un escritor HTML `(resultado, destino)` en uno que deja el PDF."""
    def escribir(resultado, destino):
        with tempfile.TemporaryDirectory(prefix="informe_pdf_") as carpeta:
            origen = Path(carpeta) / "informe.html"
            escribir_html(resultado, origen)
            return html_a_pdf(origen, destino)
    return escribir


__all__ = ["ErrorPDF", "navegador", "html_a_pdf", "texto_a_pdf", "desde_html"]
