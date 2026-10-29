"""Utilidades de texto y fechas."""

from __future__ import annotations

import html as _html
import re
import unicodedata
from datetime import date, timedelta

_ESPACIOS = re.compile(r"\s+")
_ETIQUETAS = re.compile(r"<[^>]+>")


def limpiar(texto) -> str:
    """Colapsa espacios (incluido el espacio duro) y recorta."""
    if texto is None:
        return ""
    return _ESPACIOS.sub(" ", str(texto).replace("\xa0", " ")).strip()


def sin_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto) -> str:
    """Mayúsculas, sin acentos y con espacios colapsados: para comparar."""
    return limpiar(sin_acentos(limpiar(texto))).upper()


def desescapar(texto) -> str:
    """Las meta descripciones del sitio vienen con entidades dobles (&amp;nbsp;)."""
    t = texto or ""
    for _ in range(3):
        nuevo = _html.unescape(t)
        if nuevo == t:
            break
        t = nuevo
    return limpiar(_ETIQUETAS.sub(" ", t))


def anio_cuatro_digitos(valor) -> int:
    n = int(valor)
    if n >= 100:
        return n
    return 1900 + n if n >= 83 else 2000 + n


_RE_FECHA = re.compile(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?!\d)")


def parsear_fecha(texto) -> date | None:
    """Acepta dd-mm-aaaa, dd/mm/aaaa y dd-mm-aa."""
    if not texto:
        return None
    m = _RE_FECHA.search(str(texto))
    if not m:
        return None
    try:
        return date(anio_cuatro_digitos(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
_NOMBRES_MES = "|".join(MESES)
_RE_FECHA_LARGA = re.compile(rf"(?<!\d)(\d{{1,2}})\s+DE\s+({_NOMBRES_MES})\s+DE\s+(\d{{4}})")


def parsear_fecha_larga(texto) -> date | None:
    """«01 de octubre de 2025» → date."""
    m = _RE_FECHA_LARGA.search(normalizar(texto))
    if not m:
        return None
    try:
        return date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
    except ValueError:
        return None


def fmt_fecha(d: date | None, vacio: str = "—") -> str:
    return d.strftime("%d/%m/%Y") if d else vacio


def fmt_numero_ley(numero: str) -> str:
    digitos = re.sub(r"\D", "", numero or "")
    if not digitos:
        return limpiar(numero)
    return f"{int(digitos):,}".replace(",", ".")


def anio_parlamentario(d: date) -> int:
    """El año parlamentario va del 1 de marzo al último día de febrero."""
    return d.year if d.month >= 3 else d.year - 1


def fin_anio_parlamentario(anio: int) -> date:
    """Último día del año parlamentario que empieza en marzo de `anio`."""
    return date(anio + 1, 3, 1) - timedelta(days=1)


_PALABRAS_MENORES = {
    "de", "del", "la", "las", "los", "el", "y", "e", "o", "u", "a", "al",
    "en", "por", "para", "con", "entre", "sus", "su",
}
_SIGLAS = {"DNU", "AGN", "ONG", "CABA", "II", "III", "IV"}


def _capitalizar(palabra: str) -> str:
    for i, c in enumerate(palabra):
        if c.isalpha():
            return palabra[:i] + c.upper() + palabra[i + 1:].lower()
    return palabra


def titulo_es(texto: str) -> str:
    """«DE EDUCACIÓN Y CULTURA» → «De Educación y Cultura» (respeta siglas)."""
    palabras = limpiar(texto).split(" ")
    salida = []
    for i, p in enumerate(palabras):
        nucleo = p.strip("(),.;:")
        if nucleo.upper() in _SIGLAS:
            salida.append(p.upper())
        elif i > 0 and nucleo.lower() in _PALABRAS_MENORES:
            salida.append(p.lower())
        else:
            salida.append(_capitalizar(p))
    return " ".join(salida)


def nombre_comision(nombre: str) -> str:
    """Nombre legible de una comisión: «DE SALUD» → «Salud»."""
    n = limpiar(nombre)
    n = re.sub(r"^(COMISI[OÓ]N\s+)?(UNICAMERAL\s+)?(PERMANENTE\s+)?DE\s+", "", n, flags=re.I)
    return titulo_es(n) if n.isupper() else n


def nombre_archivo_seguro(texto: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "-", texto).strip(" .")
