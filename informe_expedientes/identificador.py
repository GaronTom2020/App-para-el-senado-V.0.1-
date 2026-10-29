"""Lectura del número de expediente en los formatos habituales.

Acepta, entre otros:
    S-1234/24 · S 1234/2024 · C.D.-14/24 · CD-14/24-PL · PE 107/24 PL
    1370-S-2020 · Expte. S-1234/24 · enlaces a la ficha (verExp/14.24/CD/PL)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from functools import lru_cache

from . import config
from .util import anio_cuatro_digitos


class ErrorIdentificador(ValueError):
    """El texto no se puede interpretar como número de expediente."""


RE_URL_FICHA = re.compile(
    r"verExp/(?P<num>\d{1,5})\.(?P<anio>\d{2,4})/(?P<origen>[A-Za-z]{1,4})/(?P<tipo>[A-Za-z0-9]{2})",
    re.I,
)
RE_URL_PARLA = re.compile(
    r"verExp/parla/(?P<origen>[A-Za-z]{1,4})-(?P<num>\d{1,5})\.(?P<anio>\d{2,4})-(?P<tipo>[A-Za-z0-9]{2})",
    re.I,
)
_PREFIJO = re.compile(r"^(?:EXPEDIENTE|EXPTE|EXP)\s*\.?\s*(?:N[°º]|NRO\.?|NUM\.?)?\s*")
_ORIGEN_PRIMERO = re.compile(
    r"^(?P<origen>[A-Z]{1,4})\s*-?\s*(?:N[°º]\s*)?(?P<num>\d{1,5})\s*[/-]\s*(?P<anio>\d{4}|\d{2})"
    r"(?:\s*[-/ ]\s*(?P<tipo>[A-Z][A-Z0-9]))?$"
)
_NUMERO_PRIMERO = re.compile(
    r"^(?P<num>\d{1,5})\s*-\s*(?P<origen>[A-Z]{1,4})\s*-\s*(?P<anio>\d{4}|\d{2})"
    r"(?:\s*[-/ ]\s*(?P<tipo>[A-Z][A-Z0-9]))?$"
)
_SIN_ORIGEN = re.compile(r"^(?P<num>\d{1,5})\s*/\s*(?P<anio>\d{4}|\d{2})$")
_ALIAS_ORIGEN = {"PEN": "PE", "SEN": "S", "HCD": "CD", "HCDN": "CD", "JG": "JGM"}


@dataclass(frozen=True)
class IdExpediente:
    numero: int
    anio: int          # cuatro dígitos
    origen: str        # S, CD, PE, JGM, OV, OVD, P, DCD
    tipo: str | None = None   # PL, PD, PR, PC, …

    @property
    def anio2(self) -> int:
        return self.anio % 100

    @property
    def corto(self) -> str:
        """Forma usada por el Senado: S-1234/24."""
        return f"{self.origen}-{self.numero}/{self.anio2:02d}"

    @property
    def para_archivo(self) -> str:
        return f"{self.origen}-{self.numero}-{self.anio2:02d}"

    def con_tipo(self, tipo: str) -> "IdExpediente":
        return replace(self, tipo=tipo)

    def url_ficha(self, tipo: str | None = None) -> str:
        t = tipo or self.tipo
        if not t:
            raise ValueError("Falta el tipo del expediente para armar la dirección de la ficha.")
        return config.URL_FICHA.format(numero=self.numero, anio2=self.anio2, origen=self.origen, tipo=t)

    def coincide_url(self, href: str) -> bool:
        """¿El enlace apunta a la ficha de este expediente (cualquier tipo)?"""
        m = RE_URL_FICHA.search(href or "") or RE_URL_PARLA.search(href or "")
        if not m:
            return False
        try:
            return (
                int(m.group("num")) == self.numero
                and anio_cuatro_digitos(m.group("anio")) == self.anio
                and m.group("origen").upper() == self.origen
            )
        except ValueError:
            return False

    def patron_texto(self) -> re.Pattern:
        """Expresión que reconoce el expediente escrito en un texto libre."""
        return _patron(self.origen, self.numero, self.anio2)


@lru_cache(maxsize=512)
def _patron(origen: str, numero: int, anio2: int) -> re.Pattern:
    letras = r"\.?\s?".join(re.escape(c) for c in origen)
    yy = f"{anio2:02d}"
    anio = rf"(?:(?:19|20){yy}|{yy})(?!\d)"
    estilo_senado = rf"(?<![A-Z0-9]){letras}\.?\s*[-–—]?\s*(?:N[°º.]?\s*)?0*{numero}\s*/\s*{anio}"
    estilo_numero = rf"(?<![\d/]){'0*'}{numero}\s*-\s*{letras}\.?\s*-\s*{anio}"
    return re.compile(f"(?:{estilo_senado})|(?:{estilo_numero})", re.IGNORECASE)


def parsear(texto: str, tipo: str | None = None) -> IdExpediente:
    """Interpreta lo que escribió el usuario. `tipo` se usa si el texto no lo trae."""
    original = (texto or "").strip()
    if not original:
        raise ErrorIdentificador("Escribí un número de expediente.")

    m = RE_URL_FICHA.search(original) or RE_URL_PARLA.search(original)
    if m:
        return _construir(m.group("origen"), m.group("num"), m.group("anio"), m.group("tipo"), original)

    t = original.upper().replace("–", "-").replace("—", "-")
    t = _PREFIJO.sub("", t.strip())
    t = re.sub(r"(?<=[A-Z])\.", "", t)          # C.D. → CD · P.E.N. → PEN
    t = re.sub(r"\s+", " ", t).strip(" .,;")

    m = _ORIGEN_PRIMERO.match(t) or _NUMERO_PRIMERO.match(t)
    if m:
        return _construir(m.group("origen"), m.group("num"), m.group("anio"), m.group("tipo") or tipo, original)
    if _SIN_ORIGEN.match(t):
        raise ErrorIdentificador(
            f"«{original}»: falta el origen. Escribilo como S-1234/24, CD-14/24 o PE-107/24."
        )
    raise ErrorIdentificador(
        f"No reconozco «{original}» como número de expediente. "
        "Ejemplos válidos: S-1234/24, CD-14/24, PE-107/24 o el enlace a la ficha del Senado."
    )


def _construir(origen: str, numero: str, anio: str, tipo: str | None, original: str) -> IdExpediente:
    origen = _ALIAS_ORIGEN.get(origen.upper(), origen.upper())
    if origen == "D":
        raise ErrorIdentificador(
            f"«{original}» usa la numeración de la Cámara de Diputados. En el Senado ese proyecto "
            "ingresa como CD-número/año: buscalo con ese número."
        )
    if origen not in config.ORIGENES:
        raise ErrorIdentificador(
            f"«{original}»: el origen «{origen}» no existe. Orígenes válidos: {', '.join(config.ORIGENES)}."
        )
    n = int(numero)
    if n <= 0:
        raise ErrorIdentificador(f"«{original}»: el número de expediente tiene que ser mayor que cero.")
    a = anio_cuatro_digitos(anio)
    if not 1983 <= a <= date.today().year + 1:
        raise ErrorIdentificador(f"«{original}»: el año {a} está fuera de rango.")
    t = (tipo or "").upper() or None
    if t and t not in config.TIPOS:
        raise ErrorIdentificador(f"«{original}»: el tipo «{t}» no existe. Tipos válidos: {', '.join(config.TIPOS)}.")
    return IdExpediente(n, a, origen, t)


def separar_lote(texto: str) -> list[str]:
    """Un expediente por línea (también se aceptan comas y punto y coma)."""
    partes = re.split(r"[\n;,]+", texto or "")
    return [p.strip() for p in partes if p.strip()]
