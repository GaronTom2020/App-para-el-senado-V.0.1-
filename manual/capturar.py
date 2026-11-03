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

from PIL import Image, ImageGrab  # noqa: E402

from conftest import ClienteFalso  # noqa: E402
from informe_expedientes import gui  # noqa: E402
from informe_expedientes.servicio import Opciones, generar  # noqa: E402

HOY = date(2026, 10, 30)


def _por_pantalla(_widget, x, y, ancho, alto):
    return ImageGrab.grab(bbox=(x, y, x + ancho, y + alto), all_screens=True)


def _por_ventana(widget, x, y, ancho, alto):
    """PrintWindow de Win32: dibuja la ventana en memoria, sin depender de que esté a la vista (sirve en los
    runners de GitHub, donde el escritorio puede no estar disponible para ImageGrab)."""
    import ctypes
    from ctypes import wintypes
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    ventana = widget.winfo_toplevel()
    hwnd = ventana.winfo_id()
    ancho_v, alto_v = ventana.winfo_width(), ventana.winfo_height()
    hdc = user32.GetDC(hwnd)
    memoria = gdi32.CreateCompatibleDC(hdc)
    mapa = gdi32.CreateCompatibleBitmap(hdc, ancho_v, alto_v)
    gdi32.SelectObject(memoria, mapa)
    try:
        if not user32.PrintWindow(hwnd, memoria, 2):           # PW_RENDERFULLCONTENT
            raise OSError("PrintWindow no pudo dibujar la ventana")

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                        ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
        cabecera = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), ancho_v, -alto_v, 1, 32, 0, 0, 0, 0, 0, 0)
        datos = ctypes.create_string_buffer(ancho_v * alto_v * 4)
        gdi32.GetDIBits(memoria, mapa, 0, alto_v, datos, ctypes.byref(cabecera), 0)
    finally:
        gdi32.DeleteObject(mapa)
        gdi32.DeleteDC(memoria)
        user32.ReleaseDC(hwnd, hdc)
    imagen = Image.frombuffer("RGB", (ancho_v, alto_v), datos, "raw", "BGRX", 0, 1)
    dx, dy = x - ventana.winfo_rootx(), y - ventana.winfo_rooty()
    return imagen.crop((dx, dy, dx + ancho, dy + alto))


def _vacia(imagen) -> bool:
    """Negra o de un solo color: el escritorio no estaba disponible."""
    return imagen.convert("L").getextrema()[0] == imagen.convert("L").getextrema()[1]


def capturar(app, nombre: str, widget=None) -> None:
    """Guarda la ventana entera o, con ``widget``, solo ese recuadro. Si ningún método da una imagen
    válida, deja la captura anterior del repositorio y avisa."""
    app.update()
    app.after(350)
    app.update()
    w = widget or app
    caja = (w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height())
    errores = []
    for metodo in (_por_pantalla, _por_ventana):
        try:
            imagen = metodo(w, *caja)
        except Exception as error:                              # noqa: BLE001 - se prueba el siguiente método
            errores.append(f"{metodo.__name__}: {error!r}")
            continue
        if _vacia(imagen):
            errores.append(f"{metodo.__name__}: imagen vacía")
            continue
        imagen.save(SALIDA / f"{nombre}.png")
        print("captura", nombre, f"({metodo.__name__})")
        return
    raise RuntimeError(f"No se pudo capturar «{nombre}»: " + "; ".join(errores))


def principal() -> None:
    if sys.platform.startswith("win"):
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    SALIDA.mkdir(exist_ok=True)
    # Las capturas se toman siempre a escala 100 % (96 ppp), aunque la PC tenga Windows al 125 % o 150 %: si no,
    # las letras salen más grandes, no entran en la ventana de 1280 × 800 y las columnas quedan cortadas.
    iniciar = gui.tk.Tk.__init__

    def a_escala_100(ventana, *args, **kwargs):
        iniciar(ventana, *args, **kwargs)
        ventana.tk.call("tk", "scaling", 96 / 72)

    gui.tk.Tk.__init__ = a_escala_100
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

    # La ventana del resumen diario por correo, con dos grupos de ejemplo.
    app.lista_seguimiento.crear_grupo("Presupuesto")
    app.lista_seguimiento.crear_grupo("Salud")
    app._config_correo()
    ventana = next(w for w in app.winfo_children() if isinstance(w, gui.tk.Toplevel))
    ventana.attributes("-topmost", True)
    capturar(app, "09_correo", ventana)
    ventana.destroy()

    html = r.archivos.get("html")
    if html:
        (SALIDA / "informe_ejemplo.html").write_bytes(Path(html).read_bytes())
    app.destroy()


if __name__ == "__main__":
    principal()
