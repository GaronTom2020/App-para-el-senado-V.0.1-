"""Ayudas comunes para leer las páginas del sitio."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from .util import limpiar, normalizar


def sopa(html: str) -> BeautifulSoup:
    try:
        s = BeautifulSoup(html or "", "lxml")
    except Exception:  # lxml no disponible
        s = BeautifulSoup(html or "", "html.parser")
    for t in s(["script", "style", "noscript"]):
        t.decompose()
    return s


def texto(elemento) -> str:
    return limpiar(elemento.get_text(" ")) if elemento is not None else ""


def tablas_hoja(s: BeautifulSoup) -> list[Tag]:
    """Tablas que no contienen otras tablas (evita las de maquetación)."""
    return [t for t in s.find_all("table") if not t.find("table")]


def encabezado(tabla: Tag) -> list[str]:
    ths = tabla.find_all("th")
    if ths:
        return [normalizar(th.get_text(" ")) for th in ths]
    primera = tabla.find("tr")
    if not primera:
        return []
    return [normalizar(c.get_text(" ")) for c in primera.find_all(["td", "th"])]


def filas_datos(tabla: Tag) -> list[Tag]:
    """Filas con al menos una celda <td>."""
    return [tr for tr in tabla.find_all("tr") if tr.find("td")]


def celdas(fila: Tag) -> list[str]:
    return [texto(c) for c in fila.find_all(["td", "th"])]


def meta(s: BeautifulSoup, clave: str) -> str:
    for atributo in ("property", "name"):
        etiqueta = s.find("meta", attrs={atributo: re.compile(rf"^{re.escape(clave)}$", re.I)})
        if etiqueta and etiqueta.get("content"):
            return etiqueta["content"]
    return ""
