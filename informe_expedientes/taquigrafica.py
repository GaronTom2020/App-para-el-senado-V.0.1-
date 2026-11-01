"""Versión taquigráfica de una sesión: qué se votó y qué modificaciones se aprobaron en el recinto.

La Dirección General de Taquígrafos publica cada versión en PDF, en la página «busquedaTac»
(una fila por sesión, con el enlace «…/sesiones/29-10-2026/12/downloadTac»). El PDF trae un
índice numerado («15. Régimen de Incentivo para Inversiones Relevantes (RIIR).») y el cuerpo
repite esos títulos. De cada punto se toma:

- la orden del día y los expedientes que enuncia el Secretario («Orden del Día Nº 413/26 …
  (S. 702/26.)»);
- las votaciones («Resultado: afirmativos 60, negativos 2, abstenciones cero. … Acta Nº 2»);
- los textos leídos entre comillas que modifican el dictamen: los que lee el Secretario y los
  que propone un senador y el miembro informante acepta. Las propuestas no aceptadas se
  listan aparte, sin su texto;
- el desenlace («Resulta aprobado en general y en particular el Orden del Día … Se comunicará
  a la Honorable Cámara de Diputados»).

Es una lectura automática del texto: el informe la presenta como «versión revisada» con las
modificaciones en negrita y remite al dictamen para el resto del articulado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from . import config, plan_labor
from .cliente import Cliente
from .paginas import sopa
from .util import limpiar, normalizar

URL_LISTA = config.BASE + "/parlamentario/sesiones/busquedaTac"

_RE_ENCABEZADO = re.compile(r"^\s*\d{1,2}(?:/\d{1,2})? de \w+ de \d{4}\s+Sesi[oó]n .*P[aá]g\.\s*\d+\s*$", re.I | re.M)
_RE_DIRECCION = re.compile(r"^\s*Direcci[oó]n General de Taqu[ií]grafos\s*$", re.I | re.M)
_RE_ITEM = re.compile(r"^\s*(\d{1,2})\s*\.\s*(\S.*)$")
_RE_OD = re.compile(r"Orden\s+del\s+D[ií]a\s*N\s*[º°o]?\s*(\d{1,4})\s*/\s*(\d{2,4})", re.I)
_RE_ORADOR = re.compile(r"(?m)^\s*(Sra?\.\s+[^\n]{2,60}?)\s?\.\s?-")
_RE_ACTA = re.compile(r"surge\s+del\s+Acta\s*N\s*[º°o]?\s*(\d+)", re.I)
_CERO = r"(\d+|cero|ninguna)"
_RE_AFIRMATIVOS = re.compile(r"(\d+)\s*af\s*irmativos|af\s*irmativos\s*(\d+)", re.I)
_RE_NEGATIVOS = re.compile(_CERO + r"\s*negativos|negativos\s*" + _CERO, re.I)
_RE_ABSTENCIONES = re.compile(_CERO + r"\s*abs\s*tenc\s*iones|abs\s*tenc\s*iones\s*" + _CERO, re.I)
_RE_CITA = re.compile(r"“([^”]{80,})”", re.S)
_RE_RECHAZO = re.compile(r"\bno\s+(?:se\s+|ser[ií]a\s+|resulta\s+|ha\s+sido\s+|vamos\s+a\s+|podemos\s+)?acept", re.I)
_RE_ACEPTA = re.compile(r"\bse\s+acepta\b|\baceptamos\b|\bacept(?:a|o)\s+la\b|\bresulta\s+aceptad", re.I)
_RE_ARTICULO = re.compile(r"art[íi]culos?\s+(\d{1,3})\s*[°º]?\s*(bis|ter)?", re.I)
_RE_DESENLACE = re.compile(
    r"(?:Result(?:a|ando)|Queda)\s+(?:apro\s*bad|sancionad|rechazad)[oa]s?,?\s+en\s+general\s+y\s+en\s+particular[^.]*\."
    r"(?:\s*(?:Se\s+comunicar[aá]|Se\s+gira|Pasa)[^.]*\.)?", re.I | re.S)


@dataclass
class Votacion:
    que: str                      # «en general», «artículo 3°», «en general y en particular»
    afirmativos: int
    negativos: int
    abstenciones: str
    acta: str = ""                # número de acta dentro de la sesión
    resultado: str = ""           # «Resulta aprobado.»


@dataclass
class Modificacion:
    articulo: str                 # «Artículo 3°» (puede quedar vacío si el texto no lo dice)
    texto: str
    quien: str                    # «Secretario (Giustinian)» o el senador que la propuso


@dataclass
class Debate:
    numero: int
    titulo: str
    texto: str
    ordenes_del_dia: list[str] = field(default_factory=list)      # «413/26»
    votaciones: list[Votacion] = field(default_factory=list)
    modificaciones: list[Modificacion] = field(default_factory=list)
    rechazadas: list[Modificacion] = field(default_factory=list)  # propuestas que no se aceptaron (sin texto)
    desenlace: str = ""


@dataclass
class VersionTaquigrafica:
    url: str
    debates: list[Debate] = field(default_factory=list)

    def debate_de(self, ordenes_del_dia: list[str], titulo: str = "") -> Debate | None:
        """El punto que trata alguna de esas órdenes del día o, si no, el de título más parecido."""
        for d in self.debates:
            if set(ordenes_del_dia) & set(d.ordenes_del_dia):
                return d
        if not titulo:
            return None
        palabras = _palabras(titulo)
        mejor, puntaje = None, 0.0
        for d in self.debates:
            comunes = len(palabras & _palabras(d.titulo))
            p = comunes / max(1, min(len(palabras), len(_palabras(d.titulo))))
            if comunes >= 2 and p > puntaje:
                mejor, puntaje = d, p
        return mejor if puntaje >= 0.6 else None


def _palabras(texto: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{4,}", normalizar(texto).lower())}


def _compacto(texto: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalizar(texto).lower())


# ================================================================== búsqueda

def url_de_sesion(html: str, fecha: date) -> str | None:
    """Enlace de descarga de la versión taquigráfica de la sesión de esa fecha (None si no está publicada)."""
    clave = f"/{fecha:%d-%m-%Y}/"
    for a in sopa(html).find_all("a", href=True):
        if "downloadTac" in a["href"] and clave in a["href"]:
            href = a["href"]
            return href if href.startswith("http") else config.BASE + href
    return None


def buscar(cliente: Cliente, fecha: date) -> VersionTaquigrafica | None:
    """Baja y lee la versión taquigráfica de la sesión; None si todavía no se publicó."""
    url = url_de_sesion(cliente.get(URL_LISTA, ttl=config.TTL_ORDEN_DIA).texto, fecha)
    if not url:
        return None
    return leer(_texto_pdf(cliente.get(url, binario=True).contenido or b""), url)


def _texto_pdf(contenido: bytes) -> str:
    return plan_labor.texto_de_pdf(contenido)


# ==================================================================== lectura

def _limpiar(texto: str) -> str:
    texto = _RE_ENCABEZADO.sub("", texto.replace("\r", ""))
    texto = _RE_DIRECCION.sub("", texto)
    return re.sub(r"\n\s*\n+", "\n", texto)


def _indice(lineas: list[str]) -> tuple[list[tuple[int, str]], int]:
    """Los puntos del índice y la línea donde termina."""
    try:
        inicio = next(i for i, x in enumerate(lineas) if normalizar(x).strip() == "INDICE")
    except StopIteration:
        return [], 0
    puntos: list[tuple[int, str]] = []
    fin = inicio
    for i in range(inicio + 1, min(len(lineas), inicio + 400)):
        linea = lineas[i].strip()
        m = _RE_ITEM.match(linea)
        if m and int(m.group(1)) == len(puntos) + 1:
            puntos.append((int(m.group(1)), m.group(2).strip()))
            fin = i
            if normalizar(m.group(2)).startswith("APENDICE"):
                break
        elif puntos and linea and not re.match(r"^[IVX]+\.\s", linea):
            n, t = puntos[-1]
            puntos[-1] = (n, f"{t} {linea}")              # el título sigue en el renglón siguiente
            fin = i
    return [(n, limpiar(t).rstrip(". ")) for n, t in puntos], fin


def leer(texto: str, url: str = "") -> VersionTaquigrafica:
    lineas = _limpiar(texto).split("\n")
    puntos, fin_indice = _indice(lineas)
    vt = VersionTaquigrafica(url)
    if not puntos:
        return vt
    # Comienzo de cada punto en el cuerpo: el número y las primeras letras del título.
    comienzos: list[tuple[int, int, str]] = []
    pos = fin_indice + 1
    for numero, titulo in puntos:
        clave = _compacto(titulo)[:14]
        for i in range(pos, len(lineas)):
            m = _RE_ITEM.match(lineas[i])
            if m and int(m.group(1)) == numero:
                siguiente = lineas[i + 1] if i + 1 < len(lineas) else ""
                if _compacto(m.group(2) + siguiente).startswith(clave):
                    comienzos.append((numero, i, titulo))
                    pos = i + 1
                    break
    for k, (numero, i, titulo) in enumerate(comienzos):
        hasta = comienzos[k + 1][1] if k + 1 < len(comienzos) else len(lineas)
        cuerpo = "\n".join(lineas[i + 1:hasta])
        base = re.sub(r"\s*\(continuaci[oó]n\)\s*$", "", titulo, flags=re.I)
        previo = next((d for d in vt.debates if _compacto(d.titulo) == _compacto(base)), None)
        if previo is not None:                       # «(Continuación)»: se suma al punto ya abierto
            previo.texto += "\n" + cuerpo
        else:
            vt.debates.append(Debate(numero, base, cuerpo))
    for d in vt.debates:
        _analizar(d)
    vt.debates = [d for d in vt.debates if d.ordenes_del_dia or d.votaciones]
    return vt


def _parrafos(texto: str) -> str:
    """Une los renglones del PDF y deja un salto donde termina un párrafo (renglón que cierra en . : ;)."""
    parrafos, actual = [], []
    for renglon in texto.split("\n"):
        renglon = limpiar(renglon)
        if not renglon:
            continue
        actual.append(renglon)
        if renglon[-1] in ".:;":
            parrafos.append(" ".join(actual))
            actual = []
    if actual:
        parrafos.append(" ".join(actual))
    return "\n".join(parrafos)


def _orador(texto: str, hasta: int) -> str:
    oradores = list(_RE_ORADOR.finditer(texto, 0, hasta))
    if not oradores:
        return ""
    return re.sub(r"^Sra?\.\s+", "", limpiar(oradores[-1].group(1)))


def _articulo(cita: str, antes: str) -> str:
    """«Artículo 6° bis» · «Artículo 3°, inciso l)» · «Artículo 10, inciso f)»."""
    m = _RE_ARTICULO.match(cita.strip())
    if not m:
        previos = list(_RE_ARTICULO.finditer(antes[-600:]))
        m = previos[-1] if previos else None
    if not m:
        return ""
    numero = int(m.group(1))
    bis = (m.group(2) or "").lower()
    inciso = re.match(r"\s*Inciso\s+(\w)\)", cita, re.I) or re.search(r"inciso\s+(\w)\)\W{0,4}$", antes, re.I)
    return (f"Artículo {numero}{'°' if numero < 10 else ''}" + (f" {bis}" if bis else "")
            + (f", inciso {inciso.group(1)})" if inciso else ""))


def _que_se_vota(antes: str) -> str:
    """Lo último que se anunció antes de votar: «en general», «artículos 25 al 34», …"""
    t = limpiar(antes[-700:])
    candidatos = [(m.start(), "en general y en particular")
                  for m in re.finditer(r"en\s+general,?\s+y\s+en\s+particular", t, re.I)]
    candidatos += [(m.start(), "en general") for m in re.finditer(r"en\s+general(?!,?\s+y\s+en)", t, re.I)]
    candidatos += [(m.start(), "en particular") for m in re.finditer(r"(?<!general y )(?<!general, y )en\s+particular",
                                                                     t, re.I)]
    for m in re.finditer(r"art[íi]culos?\s+\d{1,3}\s*[°º]?(?:\s*(?:bis|ter))?"
                         r"(?:\s*(?:,|y|al|a)\s*\d{1,3}\s*[°º]?(?:\s*(?:bis|ter))?)*", t, re.I):
        candidatos.append((m.start(), re.sub(r"\s+", " ", m.group(0).lower()).replace("º", "°")))
    return max(candidatos)[1] if candidatos else "votación"


def _numero(m: re.Match | None) -> int:
    valor = next((g for g in (m.groups() if m else ()) if g), "0")
    return int(valor) if valor.isdigit() else 0


def _analizar(d: Debate) -> None:
    t = d.texto
    d.ordenes_del_dia = list(dict.fromkeys(f"{int(n)}/{int(a) % 100:02d}" for n, a in _RE_OD.findall(t[:1500])))

    previo = 0
    for m in _RE_ACTA.finditer(t):
        # El resultado lo lee el Secretario justo antes: «Resultado: afirmativos 60, negativos 2, abstenciones
        # cero» o «Afirmativos 53, negativos cero y abstenciones cero».
        inicio = max(previo, m.start() - 260)
        ventana = t[inicio:m.start()]
        previo = m.end()
        afirmativos = _RE_AFIRMATIVOS.search(ventana)
        if not afirmativos:
            continue
        negativos, abstenciones = _RE_NEGATIVOS.search(ventana), _RE_ABSTENCIONES.search(ventana)
        despues = t[m.end():m.end() + 400]
        resultado = re.search(r"(?:Result(?:a|an|ando)|Queda)\s+[^.\n]{0,160}\.", despues)
        d.votaciones.append(Votacion(
            _que_se_vota(t[:inicio + afirmativos.start()]), _numero(afirmativos), _numero(negativos),
            str(_numero(abstenciones)) if abstenciones else "—", m.group(1),
            limpiar(resultado.group(0)) if resultado else ""))

    citas = list(_RE_CITA.finditer(t))
    for k, m in enumerate(citas):
        antes = t[max(0, m.start() - 700):m.start()]
        if re.search(r"\bdice\s*:?\s*$", antes, re.I):
            continue                                   # el texto que se reemplaza, no el nuevo
        fin_ventana = min(len(t), m.end() + 900, citas[k + 1].start() if k + 1 < len(citas) else len(t))
        despues = t[m.end():fin_ventana]
        voto = _RE_ACTA.search(despues)
        if voto:
            despues = despues[:voto.start()]
        quien = _orador(t, m.start())
        texto = _parrafos(m.group(1))
        mod = Modificacion(_articulo(texto, antes), texto, quien)
        if _RE_RECHAZO.search(despues):
            d.rechazadas.append(Modificacion(mod.articulo, "", quien))
        elif "Secretario" in quien or _RE_ACEPTA.search(despues):
            d.modificaciones.append(mod)

    desenlaces = list(_RE_DESENLACE.finditer(t))
    if desenlaces:
        d.desenlace = limpiar(desenlaces[-1].group(0))


__all__ = ["VersionTaquigrafica", "Debate", "Votacion", "Modificacion", "buscar", "leer", "url_de_sesion",
           "URL_LISTA"]
