"""Expedientes relacionados: los tratados en conjunto y los que se tuvieron a la vista.

Fuentes, de la relación más fuerte a la más débil:
- la orden del día: sus otros expedientes se dictaminaron en conjunto;
- el texto del dictamen (PDF de la orden del día): «han considerado los proyectos …»
  (en conjunto) y «teniendo a la vista el proyecto … S-285/24 …»;
- la ficha: «aprobado conjuntamente con el P.E. 186/25», «teniendo a la vista los
  exptes. S. 285-637-638/24» y otros expedientes citados en las observaciones;
- el sitio de Diputados, del lado del Senado: «la comisión ha tenido a la vista los
  expedientes 0285-S-2024, …» y «aprobación en conjunto del expediente 0186-PE-25»;
- el temario de las reuniones de comisión en que se trató, si es breve: los demás
  expedientes de esa reunión.

De cada relacionado se lee su ficha para mostrar la situación resumida.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date

from . import config, ficha as ficha_mod, situacion as situacion_mod
from .cliente import Cancelado, Cliente, ErrorRed
from .identificador import IdExpediente, encontrar
from .modelos import Ficha, Reunion
from .paginas import sopa, texto
from .util import fmt_fecha, limpiar, normalizar

MAX_RELACIONADOS = 15          # con situación; los demás figuran solo con su relación
MAX_TEMARIO = 8                # un temario más largo es una reunión de muchos asuntos, no un tratamiento conjunto
PAGINAS_DICTAMEN = 3           # el «considerado» y el «a la vista» están en la primera página

# Orden de las relaciones (la primera que se encuentra es la que se muestra primero).
CONJUNTO_OD, CONJUNTO_DICTAMEN, CONJUNTO_SANCION, A_LA_VISTA, CITADO, REUNION = range(6)


@dataclass
class Relacionado:
    ident: IdExpediente
    relaciones: dict[int, str] = field(default_factory=dict)   # clase → texto
    url: str | None = None
    situacion: str = ""
    extracto: str = ""
    error: str = ""

    @property
    def prioridad(self) -> int:
        return min(self.relaciones)

    def texto_relacion(self) -> str:
        """Las relaciones, sin repetir; «citado» y «misma reunión» solo si no hay una más fuerte."""
        clases = sorted(self.relaciones)
        conjunto = [k for k in clases if k < A_LA_VISTA]
        elegidas = conjunto[:1] + [k for k in clases if k == A_LA_VISTA]     # una frase por tipo de relación
        if not elegidas:
            elegidas = clases[:1]
        textos = list(dict.fromkeys(self.relaciones[k] for k in elegidas))
        texto_ = "; ".join(textos)
        return texto_[:1].upper() + texto_[1:]


# ================================================================== textos

_RE_VISTA = re.compile(r"(?:TENIENDO|HA TENIDO|HABIENDO TENIDO|TENIDO) A LA VISTA")
_RE_FIN = re.compile(r"Y POR LAS RAZONES|ACONSEJAN?\b|;\s*CON \d+ DICTAMEN|DICTAMENES DE MINORIA|SALA DE LAS COMISIONES"
                     r"|\.\s*-")        # «.-» separa las anotaciones de la ficha
_RE_CONSIDERADO = re.compile(r"HAN CONSIDERADO|HA CONSIDERADO")


def _corte(t: str, inicio: int) -> str:
    n = normalizar(t)
    fin = _RE_FIN.search(n, inicio)
    return t[inicio:fin.start() if fin else min(len(t), inicio + 3000)]


def a_la_vista(texto_libre: str) -> list[IdExpediente]:
    """Expedientes del tramo «teniendo a la vista …» de un dictamen o una observación."""
    t = limpiar(texto_libre)
    salida: list[IdExpediente] = []
    for m in _RE_VISTA.finditer(normalizar(t)):
        salida += [i for _p, i in encontrar(_corte(t, m.end())) if all(i.corto != x.corto for x in salida)]
    return salida


def considerados(texto_libre: str) -> list[IdExpediente]:
    """Expedientes del tramo «han considerado …» (antes del «a la vista»): dictaminados en conjunto."""
    t = limpiar(texto_libre)
    n = normalizar(t)
    m = _RE_CONSIDERADO.search(n)
    if not m:
        return []
    vista = _RE_VISTA.search(n, m.end())
    fin = _RE_FIN.search(n, m.end())
    hasta = min(x.start() for x in (vista, fin) if x) if (vista or fin) else min(len(t), m.end() + 3000)
    return [i for _p, i in encontrar(t[m.end():hasta])]


def temario(html: str) -> list[IdExpediente]:
    """Expedientes del temario de la nota de una reunión («Temario:» o «Tratamiento de los expedientes:»)."""
    t = texto(sopa(html).find("body") or sopa(html))
    n = normalizar(t)
    m = re.search(r"\bTEMARIO\b|TRATAMIENTO DE LOS EXPEDIENTES", n)
    if not m:
        return []
    fin = re.search(r"LA VERSION TAQUIGRAFICA|\bARCHIVOS\b|\bANTERIOR\b|INSTITUCIONAL PRESIDENCIA", n[m.end():])
    tramo = t[m.end():m.end() + fin.start()] if fin else t[m.end():m.end() + 4000]
    return [i for _p, i in encontrar(tramo)]


def texto_dictamen(contenido: bytes) -> str:
    """Primeras páginas del PDF de una orden del día."""
    from pypdf import PdfReader
    lector = PdfReader(io.BytesIO(contenido))
    return " ".join(p.extract_text() or "" for p in lector.pages[:PAGINAS_DICTAMEN])


# ================================================================ detección

class _Juntar:
    def __init__(self, propio: IdExpediente):
        self.propio = propio
        self.por_clave: dict[str, Relacionado] = {}

    def sumar(self, ident: IdExpediente, clase: int, texto_rel: str) -> None:
        if ident.corto == self.propio.corto:
            return
        r = self.por_clave.setdefault(ident.corto, Relacionado(ident))
        r.relaciones.setdefault(clase, texto_rel)
        if ident.tipo and not r.ident.tipo:
            r.ident = ident

    def lista(self) -> list[Relacionado]:
        return sorted(self.por_clave.values(), key=lambda r: (r.prioridad, -r.ident.anio, r.ident.origen,
                                                               r.ident.numero))


def detectar(f: Ficha, ods: dict[str, list[IdExpediente]] | None = None, dictamenes: dict[str, str] | None = None,
             diputados=None, reuniones: list[tuple[Reunion, list[IdExpediente]]] | None = None) -> list[Relacionado]:
    """Relacionados a partir de lo ya leído: expedientes de cada OD, texto de cada dictamen, Diputados y temarios."""
    j = _Juntar(f.id)
    for od, idents in (ods or {}).items():
        for i in idents:
            j.sumar(i, CONJUNTO_OD, f"dictaminado en conjunto (Orden del Día N° {od})")
    for od, txt in (dictamenes or {}).items():
        for i in considerados(txt):
            j.sumar(i, CONJUNTO_DICTAMEN, f"dictaminado en conjunto (Orden del Día N° {od})")
        for i in a_la_vista(txt):
            j.sumar(i, A_LA_VISTA, f"tenido a la vista en el dictamen (Orden del Día N° {od})")
    notas = f.observaciones + f.anotaciones + f.hitos
    for b in f.resoluciones:
        notas += [v for k, v in b.campos if normalizar(k) in ("NOTA", "COMENTARIO") and v]
    for nota in notas:
        n = normalizar(nota)
        vista = {i.corto for i in a_la_vista(nota)}
        for i in a_la_vista(nota):
            j.sumar(i, A_LA_VISTA, "tenido a la vista (observaciones de la ficha)")
        for _p, i in encontrar(nota):
            if i.corto in vista:
                continue
            if "CONJUNTA" in n or "EN CONJUNTO" in n or re.search(r"\bCONJ\b", n):
                que = "dictaminado" if re.search(r"\bDICT", n) else "tratado"
                j.sumar(i, CONJUNTO_SANCION, f"{que} en conjunto (ficha del Senado)")
            else:
                j.sumar(i, CITADO, "citado en las observaciones de la ficha")
    if diputados is not None:
        for d in diputados.dictamenes:
            if normalizar(d.camara).startswith("SENAD"):
                for i in a_la_vista(d.texto):
                    j.sumar(i, A_LA_VISTA, f"tenido a la vista en el dictamen (Orden del Día N° "
                                           f"{_od(d.orden_del_dia)}, según Diputados)")
        for m in diputados.tramite:
            if normalizar(m.camara).startswith("SENAD") and "EN CONJUNTO" in normalizar(m.movimiento):
                for _p, i in encontrar(m.movimiento):
                    j.sumar(i, CONJUNTO_SANCION, f"aprobado en conjunto el {fmt_fecha(m.fecha)} (según Diputados)")
    for reunion, idents in reuniones or []:
        if 2 <= len(idents) <= MAX_TEMARIO:
            for i in idents:
                j.sumar(i, REUNION, f"tratado en la misma reunión de comisión ({fmt_fecha(reunion.fecha)})")
    return j.lista()


def _od(numero: str) -> str:
    n, _, a = numero.partition("/")
    return f"{int(n)}/{a[-2:]}" if n.isdigit() else numero


# ================================================================== consulta

def _nada(*_a, **_k):
    return None


def buscar(cliente: Cliente, f: Ficha, diputados=None, reuniones: list[Reunion] | None = None, avisar=_nada,
           hoy: date | None = None) -> list[Relacionado]:
    """Lee las órdenes del día, sus dictámenes y los temarios, y arma la lista de relacionados con su situación."""
    from .plan_labor import expedientes_de_od

    ods: dict[str, list[IdExpediente]] = {}
    dictamenes: dict[str, str] = {}
    for od in f.ordenes_del_dia:
        cliente.verificar_cancelacion()
        if od.url:
            try:
                ods[od.numero] = expedientes_de_od(cliente.get(od.url, ttl=config.TTL_ORDEN_DIA).texto)
            except ErrorRed as e:
                avisar("log", f"No se pudo abrir la Orden del Día N° {od.numero}: {e}")
        if od.url_pdf:
            try:
                dictamenes[od.numero] = texto_dictamen(cliente.get(od.url_pdf, binario=True).contenido or b"")
            except ErrorRed as e:
                avisar("log", f"No se pudo bajar el dictamen de la Orden del Día N° {od.numero}: {e}")
            except Exception as e:  # noqa: BLE001 - PDF ilegible o sin pypdf
                avisar("log", f"No se pudo leer el dictamen de la Orden del Día N° {od.numero} ({type(e).__name__}).")
    temarios = []
    for r in reuniones or []:
        try:
            temarios.append((r, temario(cliente.get(r.url, ttl=config.TTL_NOTA_ANTIGUA).texto)))
        except ErrorRed:
            continue
    lista = detectar(f, ods, dictamenes, diputados, temarios)
    completar(cliente, lista, hoy, avisar)
    return lista


def completar(cliente: Cliente, lista: list[Relacionado], hoy: date | None = None, avisar=_nada) -> None:
    """Situación resumida de los primeros relacionados (una ficha por expediente)."""
    hoy = hoy or date.today()
    for r in lista[:MAX_RELACIONADOS]:
        cliente.verificar_cancelacion()
        try:
            tipo = ficha_mod.resolver_tipo(cliente, r.ident)
            ident = r.ident.con_tipo(tipo)
            f = ficha_mod.descargar_ficha(cliente, ident)
            r.ident, r.url, r.extracto = ident, f.url, f.extracto
            r.situacion = situacion_mod.calcular(f, hoy).titulo
        except Cancelado:
            raise
        except Exception as e:  # noqa: BLE001 - un relacionado que falla no corta el informe
            r.error = str(e)
            avisar("log", f"No se pudo leer el expediente relacionado {r.ident.corto}: {e}")


__all__ = ["Relacionado", "detectar", "buscar", "completar", "a_la_vista", "considerados", "temario",
           "texto_dictamen"]
