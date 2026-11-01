"""Búsqueda por orden del día (OD).

Cuando varios expedientes se dictaminan en una única orden del día, dejan de tramitar por
separado: forman parte del mismo despacho (como un dictamen unificado en Diputados). Por eso
se puede pedir el informe o seguir el trámite por el número de OD: se leen sus expedientes en
la página de la OD y el primero (la cabecera) lleva la ficha; los demás figuran como parte
integrante del despacho.
"""

from __future__ import annotations

import re

from . import config, plan_labor
from .cliente import Cliente
from .identificador import IdExpediente
from .util import anio_cuatro_digitos

# «OD 413/26» · «O.D. N° 413/2026» · «Orden del Día 413/26» · «OD-413-26»
_RE_OD = re.compile(
    r"^\s*(?:O\s*\.?\s*D\s*\.?|ORDEN\s+DEL\s+D[IÍ]A)\s*(?:N\s*[°º.]?\s*|NRO\.?\s*)?-?\s*"
    r"(?P<num>\d{1,4})\s*[/-]\s*(?P<anio>\d{4}|\d{2})\s*$",
    re.I,
)


class OrdenDelDiaVacia(ValueError):
    """La página de la orden del día no lista expedientes."""


def parsear_od(texto: str) -> str | None:
    """«OD 413/26» → «413/26»; None si el texto no es una orden del día."""
    m = _RE_OD.match(texto or "")
    if not m:
        return None
    return f"{int(m.group('num'))}/{anio_cuatro_digitos(m.group('anio')) % 100:02d}"


def etiqueta(od: str) -> str:
    return f"OD {od}"


def url(od: str) -> str:
    return plan_labor.url_od(od)


def expedientes(cliente: Cliente, od: str) -> list[IdExpediente]:
    """Expedientes que integran la orden del día, en el orden del sitio (el primero es la cabecera)."""
    html = cliente.get(url(od), ttl=config.TTL_ORDEN_DIA).texto
    idents = plan_labor.expedientes_de_od(html)
    if not idents:
        raise OrdenDelDiaVacia(f"La Orden del Día N° {od} no lista expedientes en el sitio del Senado "
                               "(revisá el número o si ya fue publicada).")
    return idents


__all__ = ["parsear_od", "etiqueta", "url", "expedientes", "OrdenDelDiaVacia"]
