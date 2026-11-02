"""Capturas de pantalla del programa para el manual de usuario.

Abre la ventana con una carpeta de configuración vacía y con las páginas de prueba de ``tests/fixtures``
(no hace falta conexión), recorre las pestañas y guarda una imagen de cada una en ``manual/capturas``.
Solo funciona en Windows (usa ImageGrab sobre el escritorio).

    python manual/capturar.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = Path(__file__).resolve().parent / "capturas"
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="manual_")      # no toca la configuración real

from PIL import ImageGrab  # noqa: E402

from conftest import ClienteFalso  # noqa: E402
from informe_expedientes import gui  # noqa: E402
from informe_expedientes.servicio import Opciones, generar  # noqa: E402

HOY = date(2026, 10, 30)


def capturar(app, nombre: str, widget=None) -> None:
    """Guarda la ventana entera o, con ``widget``, solo ese recuadro."""
    app.update()
    app.after(350)
    app.update()
    w = widget or app
    x, y = w.winfo_rootx(), w.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + w.winfo_width(), y + w.winfo_height()), all_screens=True).save(
        SALIDA / f"{nombre}.png")
    print("captura", nombre)


def principal() -> None:
    if sys.platform.startswith("win"):
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    SALIDA.mkdir(exist_ok=True)
    app = gui.Aplicacion()
    app.geometry("1280x800+0+0")
    app.attributes("-topmost", True)
    app.lift()
    capturar(app, "01_inicio")

    # Un informe real armado con las páginas de prueba.
    carpeta = Path(tempfile.mkdtemp(prefix="informes_"))
    app.txt_expedientes.delete("1.0", "end")
    app.txt_expedientes.insert("1.0", "S-351/25")
    r = generar("S-351/25", Opciones(carpeta_salida=carpeta, formatos=("html",), buscar_reuniones=False,
                                      buscar_agenda=False), ClienteFalso(), hoy=HOY)
    app.resultados = [r]
    app._mostrar(r)
    capturar(app, "02_resultado")
    app.pestanias.select(app.arbol_tramite.master)
    capturar(app, "03_tramite")
    app.pestanias.select(0)

    for i, nombre in enumerate(["por_tema", "seguimiento", "sesion", "asuntos"], start=1):
        app.modos.select(i)
        capturar(app, f"{i + 3:02d}_{nombre}", app.modos)

    html = r.archivos.get("html")
    if html:
        (SALIDA / "informe_ejemplo.html").write_bytes(Path(html).read_bytes())
    app.destroy()


if __name__ == "__main__":
    principal()
