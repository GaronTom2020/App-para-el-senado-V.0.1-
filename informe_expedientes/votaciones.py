"""Votaciones nominales del recinto (www.senado.gob.ar/votaciones).

Dónde está cada dato (relevado en docs/relevamiento-fase0.md):
- El listado del año (`votaciones/actas`; otros años, con POST del formulario) trae
  una fila por votación con fecha, título, expedientes y órdenes del día enlazados,
  tipo, resultado y mayoría. Alcanza para saber qué actas tocan a un expediente.
- El detalle (`detalleActa/{id}`) trae los totales. En las sesiones recientes se
  publica vacío y se completa días después.
- El PDF (`verActaVotacion/{id}`) sale enseguida con la lista nominal, el quórum y,
  en el título, los artículos votados («ART. 1 AL 22»).

Solo interesan las votaciones sobre el contenido del expediente: en general, en
particular y las insistencias (arts. 81 y 83 de la Constitución). Las mociones,
preferencias y habilitaciones sobre tablas quedan afuera. De la votación en particular
importan los artículos rechazados; los aprobados se informan «sin observaciones».

Lo ya leído se guarda en un índice (JSON en la carpeta de caché) para no volver a
recorrer los listados ni las actas completas en cada consulta.
"""

from __future__ import annotations

import io
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import date
from pathlib import Path

from . import config
from .cliente import Cliente, ErrorRed
from .identificador import RE_URL_FICHA, IdExpediente
from .modelos import Ficha, Votacion
from .paginas import sopa, texto
from .util import anio_cuatro_digitos, limpiar, normalizar, parsear_fecha

URL_ACTAS = config.BASE + "/votaciones/actas"
URL_DETALLE = config.BASE + "/votaciones/detalleActa/{id}"
URL_PDF = config.BASE + "/votaciones/verActaVotacion/{id}"

TTL_ANIO_EN_CURSO = 3 * 3600
TTL_ANIO_CERRADO = 30 * 86400
MAX_ACTAS_POR_EXPEDIENTE = 40
VERSION_INDICE = 3

_RE_ID = re.compile(r"(?:verActaVotacion|detalleActa)/(\d+)|mostrar\((\d+)\)")
_RE_OD = re.compile(r"ordenDelDiaResultadoLink/(\d{4})/(\d+)")
_RE_ARTICULO = re.compile(r"\bArt\.\s*[\w ]+?(?=\s*(?:,|$))")
_VOTOS = {"SI": "AFIRMATIVO", "NO": "NEGATIVO", "ABSTENCION": "ABSTENCION", "AUSENTE": "AUSENTE"}


class ErrorVotaciones(Exception):
    """No se pudo leer una página de votaciones."""


# ================================================================== listado

def _resultado(valor: str) -> str:
    n = normalizar(valor)
    if "AFIRMATIV" in n:
        return "AFIRMATIVO"
    if "NEGATIV" in n:
        return "NEGATIVO"
    return limpiar(valor)


def _corto(href: str) -> str | None:
    m = RE_URL_FICHA.search(href or "")
    if not m:
        return None
    try:
        return IdExpediente(int(m.group("num")), anio_cuatro_digitos(m.group("anio")), m.group("origen").upper()).corto
    except ValueError:
        return None


def parsear_listado(html: str) -> list[Votacion]:
    """Filas del listado anual de votaciones (tabla `actasTable`)."""
    s = sopa(html)
    tabla = s.find("table", id="actasTable") or s.find("table", attrs={"summary": re.compile("Votaciones", re.I)})
    if tabla is None:
        raise ErrorVotaciones("El listado de votaciones cambió: no se encontró la tabla de actas.")
    cuerpo = tabla.find("tbody") or tabla
    filas: list[Votacion] = []
    for tr in cuerpo.find_all("tr", recursive=False) or cuerpo.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 7:
            continue
        ids = [int(a or b) for a, b in _RE_ID.findall(str(tr))]
        if not ids:
            continue
        vid = ids[0]
        fecha = parsear_fecha(texto(tds[0]))
        celda = tds[2]
        expedientes = list(dict.fromkeys(c for c in (_corto(a["href"]) for a in celda.find_all("a", href=True)) if c))
        ordenes = [f"{int(n)}/{int(a) % 100:02d}" for a, n in _RE_OD.findall(str(celda))]
        oculto = celda.find("div")
        titulo_partes = []
        for nodo in celda.children:
            if nodo is oculto:
                break
            if getattr(nodo, "name", None) == "a" and not nodo.get("href"):
                continue            # «Ver Expedientes»
            if getattr(nodo, "name", None) == "a" and "ordenDelDia" in nodo.get("href", ""):
                continue
            parte = limpiar(nodo.get_text(" ") if hasattr(nodo, "get_text") else str(nodo))
            if parte and parte != ",":
                titulo_partes.append(parte)
        titulo = limpiar(" ".join(titulo_partes)).strip(" ,(")
        articulos = ", ".join(limpiar(x) for x in _RE_ARTICULO.findall(texto(celda)))
        resultado_celda = tds[4].find("div") or tds[4]
        enlaces = {a["href"] for a in tr.find_all("a", href=True)}
        video = next((h for h in enlaces if "youtube" in h or "youtu.be" in h), None)
        filas.append(Votacion(
            id=vid,
            fecha=fecha,
            numero_en_sesion=texto(tds[1]),
            titulo=titulo,
            tipo=texto(tds[3]),
            resultado=_resultado(texto(resultado_celda)),
            mayoria=texto(tds[6]),
            articulos=articulos,
            expedientes=expedientes,
            ordenes_del_dia=ordenes,
            url_detalle=URL_DETALLE.format(id=vid) if any("detalleActa" in h for h in enlaces) else None,
            url_pdf=URL_PDF.format(id=vid) if any("verActaVotacion" in h for h in enlaces) else None,
            video=video,
        ))
    return filas


# =================================================================== detalle

def parsear_detalle(html: str, vid: int) -> Votacion | None:
    """Detalle de un acta. None si el ID no existe (el sitio devuelve la plantilla vacía)."""
    s = sopa(html)
    texto_pagina = texto(s)
    m = re.search(r"Acta Nro:\s*(\d+)(?![\d/])", texto_pagina)
    if not m:
        return None
    v = Votacion(id=vid, fecha=None, numero_en_sesion=m.group(1), fuente="detalle",
                 url_detalle=URL_DETALLE.format(id=vid), url_pdf=URL_PDF.format(id=vid))
    cabecera = next((p for p in s.find_all("p") if re.search(r"Acta Nro:", p.get_text())), None)
    zona = (cabecera.find_parent("div", class_="row") if cabecera else None) or s
    titulo_p = cabecera.find_next("p") if cabecera else None
    if titulo_p is not None:
        v.expedientes = list(dict.fromkeys(c for c in (_corto(a["href"]) for a in titulo_p.find_all("a", href=True)) if c))
        v.ordenes_del_dia = [f"{int(n)}/{int(a) % 100:02d}" for a, n in _RE_OD.findall(str(titulo_p))]
        v.articulos = ", ".join(limpiar(x) for x in _RE_ARTICULO.findall(texto(titulo_p)))
        partes = []
        for nodo in titulo_p.children:
            if getattr(nodo, "name", None) == "a":
                break
            partes.append(limpiar(nodo.get_text(" ") if hasattr(nodo, "get_text") else str(nodo)))
        v.titulo = limpiar(" ".join(partes)).strip(" ,")
    for span in zona.find_all("span"):
        t = texto(span)
        fecha = re.match(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{1,2}:\d{2})?", t)
        if fecha and v.fecha is None:
            v.fecha = parsear_fecha(fecha.group(1))
            v.hora = fecha.group(2) or ""
        elif v.fecha is not None and t and not v.mayoria and not re.search(r"\d{2}/\d{2}/\d{4}", t):
            v.mayoria = t
    for p in zona.find_all("p"):
        t = normalizar(p.get_text(" "))
        if t in ("AFIRMATIVO", "NEGATIVO") and not v.resultado:
            v.resultado = t
        elif t.startswith("EN GENERAL") or t.startswith("EN PARTICULAR"):
            v.tipo = v.tipo or limpiar(p.get_text(" "))
    totales = {}
    for h4 in zona.find_all("h4"):
        etiqueta = normalizar(h4.get_text())
        h3 = h4.find_previous_sibling("h3")
        if h3 and etiqueta in ("AFIRMATIVOS", "NEGATIVOS", "ABSTENCIONES", "AUSENTES"):
            try:
                totales[etiqueta] = int(texto(h3))
            except ValueError:
                pass
    v.afirmativos = totales.get("AFIRMATIVOS")
    v.negativos = totales.get("NEGATIVOS")
    v.abstenciones = totales.get("ABSTENCIONES")
    v.ausentes = totales.get("AUSENTES")
    return v


# ======================================================================= PDF

def texto_pdf(contenido: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise ErrorVotaciones("Falta la biblioteca pypdf para leer los PDF del Senado.") from e
    try:
        lector = PdfReader(io.BytesIO(contenido))
        return limpiar(" ".join(p.extract_text() or "" for p in lector.pages))
    except Exception as e:  # noqa: BLE001 - PDF dañado o con otro formato
        raise ErrorVotaciones(f"No se pudo leer el PDF ({type(e).__name__}).") from e


_RE_VOTO_PDF = re.compile(r"\s(SI|NO|AUSENTE|ABSTENCI[OÓ]N)(?=\s|$)")


def parsear_pdf(texto_acta: str, vid: int) -> Votacion:
    """Acta en PDF: encabezado (título, fecha), lista nominal y pie con quórum y mayoría."""
    t = limpiar(texto_acta)
    v = Votacion(id=vid, fecha=None, fuente="pdf", url_pdf=URL_PDF.format(id=vid))
    m = re.search(r"(\d{2}/\d{2}/\d{4})\s+(\d{1,2}:\d{2})(?::\d{2})?", t)
    if m:
        v.titulo = limpiar(t[:m.start()])
        v.fecha = parsear_fecha(m.group(1))
        v.hora = m.group(2)
    lista = t[m.end():] if m else t
    pie_inicio = lista.find("Proyecto:")
    pie = lista[pie_inicio:] if pie_inicio >= 0 else ""
    lista = lista[:pie_inicio] if pie_inicio >= 0 else lista
    lista = " " + lista.replace("Nombre Completo Voto", " ")
    partes = _RE_VOTO_PDF.split(lista)
    votos = [_VOTOS[normalizar(voto)] for nombre, voto in zip(partes[0::2], partes[1::2]) if "," in nombre]
    if votos:
        v.afirmativos, v.negativos = votos.count("AFIRMATIVO"), votos.count("NEGATIVO")
        v.abstenciones, v.ausentes = votos.count("ABSTENCION"), votos.count("AUSENTE")

    def campo(patron):
        x = re.search(patron, pie)
        return limpiar(x.group(1)) if x else ""

    v.quorum = campo(r"Tipo Quorum:\s*(.+?)\s+Mayor[ií]a:")
    v.mayoria = campo(r"Mayor[ií]a:\s*(.+?)\s+Miembros del cuerpo")
    v.presidente = campo(r"Presidente:\s*(.+?)\s+Acta\s*:")
    v.numero_en_sesion = campo(r"Acta\s*:\s*(\d+)")
    presentes = campo(r"Presentes:\s*(\d+)")
    v.presentes = int(presentes) if presentes else None
    resultado = campo(r"Resultado:\s*(\w+)")
    v.resultado = _resultado(resultado) if resultado else ""
    return v


# ===================================================================== índice

def _a_dict(v: Votacion) -> dict:
    d = asdict(v)
    d["fecha"] = v.fecha.isoformat() if v.fecha else None
    return d


def _de_dict(d: dict) -> Votacion:
    nombres = {f.name for f in fields(Votacion)}
    datos = {k: val for k, val in d.items() if k in nombres}
    datos["fecha"] = date.fromisoformat(d["fecha"]) if d.get("fecha") else None
    return Votacion(**datos)


class Indice:
    """Listados anuales y actas ya leídas, guardados entre consultas."""

    def __init__(self, archivo: Path | None = None):
        self.archivo = Path(archivo) if archivo else None
        self.datos = {"version": VERSION_INDICE, "anios": {}, "actas": {}}
        if self.archivo and self.archivo.exists():
            try:
                cargado = json.loads(self.archivo.read_text(encoding="utf-8"))
                if cargado.get("version") == VERSION_INDICE:
                    self.datos.update(cargado)
            except (OSError, ValueError):
                pass

    @classmethod
    def para(cls, cliente) -> "Indice":
        carpeta = getattr(cliente, "carpeta_cache", None)
        if carpeta and getattr(cliente, "usar_cache", False):
            return cls(Path(carpeta) / "indice_votaciones.json")
        return cls(None)

    def guardar(self) -> None:
        if not self.archivo:
            return
        try:
            self.archivo.parent.mkdir(parents=True, exist_ok=True)
            temporal = self.archivo.with_suffix(".tmp")
            temporal.write_text(json.dumps(self.datos, ensure_ascii=False), encoding="utf-8")
            os.replace(temporal, self.archivo)
        except OSError:
            pass

    # ---- listados por año
    def filas(self, cliente: Cliente, anio: int, hoy: date) -> list[Votacion]:
        guardado = self.datos["anios"].get(str(anio))
        ttl = TTL_ANIO_EN_CURSO if anio >= hoy.year else TTL_ANIO_CERRADO
        if guardado and time.time() - guardado["guardado"] < ttl:
            return [_de_dict(d) for d in guardado["filas"]]
        if anio >= hoy.year:
            html = cliente.get(URL_ACTAS).texto
        else:
            html = cliente.post(URL_ACTAS, {"busqueda_actas[anio]": str(anio), "busqueda_actas[titulo]": ""}).texto
        filas = parsear_listado(html)
        self.datos["anios"][str(anio)] = {"guardado": time.time(), "filas": [_a_dict(f) for f in filas]}
        return filas

    # ---- acta completa
    def completar(self, cliente: Cliente, fila: Votacion, avisar=None) -> Votacion:
        """Totales de una fila del listado: del detalle si ya está publicado, si no del PDF."""
        avisar = avisar or (lambda *a, **k: None)
        guardada = self.datos["actas"].get(str(fila.id))
        if guardada and guardada.get("fuente") == "detalle":
            return _mezclar(fila, _de_dict(guardada))
        if guardada and guardada.get("fuente") == "pdf" and not fila.url_detalle:
            return _mezclar(fila, _de_dict(guardada))
        leida = None
        if fila.url_detalle:
            try:
                leida = parsear_detalle(cliente.get(fila.url_detalle).texto, fila.id)
            except ErrorRed as e:
                avisar("log", f"No se pudo abrir el detalle del acta {fila.id}: {e}")
            if leida is not None and not leida.con_totales:
                leida = None            # todavía no se cargó: se usa el PDF
        pdf = _de_dict(guardada) if guardada and guardada.get("fuente") == "pdf" else None
        if leida is None and fila.url_pdf:
            if pdf is not None:
                return _mezclar(fila, pdf)
            r = cliente.get(fila.url_pdf, binario=True)
            leida = parsear_pdf(texto_pdf(r.contenido or b""), fila.id)
        elif leida is not None and fila.url_pdf and (fila.en_general or fila.insistencia):
            # Las dos fuentes oficiales a veces no coinciden: se contrastan en las votaciones que deciden.
            try:
                pdf = pdf or parsear_pdf(texto_pdf(cliente.get(fila.url_pdf, binario=True).contenido or b""), fila.id)
                leida.discrepancia = discrepancia(leida, pdf)
            except (ErrorRed, ErrorVotaciones) as e:
                avisar("log", f"No se pudo contrastar el acta {fila.id} con su PDF: {e}")
        if leida is None:
            return fila
        if leida.con_totales:
            self.datos["actas"][str(fila.id)] = _a_dict(leida)
        return _mezclar(fila, leida)


def discrepancia(detalle: Votacion, pdf: Votacion) -> str:
    """Texto de aviso si el detalle publicado y el PDF del acta dan totales distintos."""
    if not (detalle.con_totales and pdf.con_totales):
        return ""
    a = (detalle.afirmativos, detalle.negativos, detalle.abstenciones, detalle.ausentes)
    b = (pdf.afirmativos, pdf.negativos, pdf.abstenciones, pdf.ausentes)
    if a == b:
        return ""
    return (f"el detalle del acta registra {a[0]} a {a[1]} ({a[3]} ausentes) y su PDF, {b[0]} a {b[1]} "
            f"({b[3]} ausentes): verificar con la Secretaría Parlamentaria")


def _mezclar(fila: Votacion, leida: Votacion) -> Votacion:
    """El acta leída, completada con lo que trae el listado (título, expedientes, enlaces)."""
    v = Votacion(**{f.name: getattr(leida, f.name) for f in fields(Votacion)})
    v.titulo = fila.titulo or leida.titulo
    v.tipo = fila.tipo or leida.tipo
    for campo in ("resultado", "mayoria", "articulos", "numero_en_sesion", "video"):
        setattr(v, campo, getattr(leida, campo) or getattr(fila, campo))
    v.fecha = fila.fecha or leida.fecha
    v.expedientes = list(dict.fromkeys(fila.expedientes + leida.expedientes))
    v.ordenes_del_dia = list(dict.fromkeys(fila.ordenes_del_dia + leida.ordenes_del_dia))
    v.url_detalle = fila.url_detalle or (leida.url_detalle if leida.fuente == "detalle" else None)
    v.url_pdf = fila.url_pdf or leida.url_pdf
    return v


# ================================================================== búsqueda

def _od_clave(numero: str) -> tuple[int, int] | None:
    m = re.match(r"\s*0*(\d+)\s*/\s*(\d{2,4})", numero or "")
    return (int(m.group(1)), int(m.group(2)) % 100) if m else None


def corresponde(fila: Votacion, ficha: Ficha) -> bool:
    """¿La votación trata este expediente? Por enlace, por orden del día o por el número en el título."""
    if ficha.id.corto in fila.expedientes:
        return True
    ods = {_od_clave(od.numero) for od in ficha.ordenes_del_dia} - {None}
    if ods & {_od_clave(od) for od in fila.ordenes_del_dia}:
        return True
    return bool(fila.titulo and ficha.id.patron_texto().search(fila.titulo))


def relevante(v: Votacion) -> bool:
    """Votaciones sobre el contenido del proyecto: en general, en particular e insistencias."""
    return v.en_general or v.en_particular or v.insistencia


def hace_falta_el_acta(v: Votacion) -> bool:
    """Totales para las votaciones que deciden; artículos, si el listado no los trae."""
    return v.en_general or v.insistencia or (v.en_particular and not articulos(v) and not v.titulo)


def anios_a_revisar(ficha: Ficha, hoy: date) -> list[int]:
    inicio = ficha.fecha_mesa_entradas.year if ficha.fecha_mesa_entradas else ficha.id.anio
    inicio = min(inicio, ficha.id.anio)
    return list(range(max(inicio, 1983), hoy.year + 1))


def buscar(cliente: Cliente, ficha: Ficha, hoy: date | None = None, avisar=None,
           indice: Indice | None = None) -> list[Votacion]:
    """Votaciones nominales del expediente (o de su orden del día), de la más vieja a la más nueva."""
    hoy = hoy or date.today()
    avisar = avisar or (lambda *a, **k: None)
    indice = indice or Indice.para(cliente)
    encontradas: list[Votacion] = []
    try:
        for anio in anios_a_revisar(ficha, hoy):
            cliente.verificar_cancelacion()
            try:
                filas = indice.filas(cliente, anio, hoy)
            except ErrorVotaciones as e:
                avisar("advertencia", f"No se pudo leer el listado de votaciones de {anio}: {e}")
                continue
            encontradas += [f for f in filas if relevante(f) and corresponde(f, ficha)]
        encontradas.sort(key=lambda v: (v.fecha or date.min, v.id))
        completas, fallidas = [], []
        pedidas = 0
        for fila in encontradas:
            cliente.verificar_cancelacion()
            if hace_falta_el_acta(fila) and pedidas < MAX_ACTAS_POR_EXPEDIENTE:
                pedidas += 1
                try:
                    fila = indice.completar(cliente, fila, avisar)
                except (ErrorRed, ErrorVotaciones) as e:
                    fallidas.append(fila.id)
                    avisar("log", f"No se pudo leer el acta de votación {fila.id}: {e}")
            completas.append(fila)
        if fallidas:
            cuales = ", ".join(str(x) for x in fallidas[:5]) + ("…" if len(fallidas) > 5 else "")
            avisar("advertencia", f"No se pudieron leer los totales de {len(fallidas)} "
                                  f"{'acta' if len(fallidas) == 1 else 'actas'} de votación ({cuales}); "
                                  "figuran solo con su resultado.")
        return completas
    finally:
        indice.guardar()


def ultima_votacion_general(votaciones: list[Votacion]) -> Votacion | None:
    generales = [v for v in votaciones if v.en_general and (v.aprobada or v.rechazada)]
    return max(generales, key=lambda v: (v.fecha or date.min, v.id)) if generales else None


# ================================================================ artículos

_RE_ARTS = re.compile(
    r"\bART(?:ICULO)?S?\.?\s*((?:\d+\s*(?:BIS|TER)?\s*(?:,|Y|AL|A|-)?\s*)+)", re.I)


def articulos(v: Votacion) -> list[str]:
    """Artículos votados, de los enlaces del listado o del título: ['1', '2', '6 bis', …]."""
    fuente = v.articulos if v.articulos else v.titulo
    salida: list[str] = []
    for m in _RE_ARTS.finditer(normalizar(fuente)):
        lista = m.group(1)
        for a, b in re.findall(r"(\d+)\s*(?:AL|A|-)\s*(\d+)", lista):
            if int(b) >= int(a):
                salida += [str(i) for i in range(int(a), int(b) + 1)]
        lista = re.sub(r"(\d+)\s*(?:AL|A|-)\s*(\d+)", " ", lista)
        salida += [f"{x} {y.lower()}".strip() for x, y in re.findall(r"(\d+)\s*(BIS|TER)?", lista)]
    return list(dict.fromkeys(salida))


def _orden(articulo: str) -> tuple[int, str]:
    numero, _, sufijo = articulo.partition(" ")
    return int(numero), sufijo


def rango(lista: list[str]) -> str:
    """['1', '2', '3', '5', '6 bis'] → '1-3, 5 y 6 bis' (los «bis» y «ter» van aparte)."""
    enteros = sorted({int(a) for a in lista if a.isdigit()})
    tramos, inicio = [], None
    for i, n in enumerate(enteros):
        if inicio is None:
            inicio = n
        if i + 1 == len(enteros) or enteros[i + 1] != n + 1:
            tramos.append(str(inicio) if inicio == n else f"{inicio}-{n}")
            inicio = None
    tramos += sorted({a for a in lista if not a.isdigit()}, key=_orden)
    if len(tramos) <= 1:
        return "".join(tramos)
    return ", ".join(tramos[:-1]) + " y " + tramos[-1]


def describir_articulos(lista: list[str]) -> str:
    """«el art. 7» · «los arts. 2-6»."""
    if len(lista) == 1:
        return f"el art. {lista[0]}"
    return f"los arts. {rango(lista)}"


_RE_PARTE = re.compile(r"\b(T[ÍI]TULO|CAP[ÍI]TULO|SECCI[ÓO]N)\s+[IVXLC\d]+\b[^.]*", re.I)


def parte_votada(v: Votacion) -> str:
    """Lo que se votó en particular, si no son artículos: «Título V: Impuesto a las Ganancias»."""
    m = _RE_PARTE.search(v.titulo or "")
    return limpiar(m.group(0)) if m else limpiar(v.titulo)


# ================================================================== sesiones

@dataclass
class Sesion:
    """Las votaciones de un expediente en una misma sesión."""
    fecha: date | None
    general: list[Votacion] = field(default_factory=list)
    particular: list[Votacion] = field(default_factory=list)
    insistencias: list[Votacion] = field(default_factory=list)

    @property
    def rechazos(self) -> list[Votacion]:
        return [v for v in self.particular if v.rechazada]

    @property
    def articulos_rechazados(self) -> list[str]:
        return [a for v in self.rechazos for a in articulos(v)]

    @property
    def partes_rechazadas(self) -> list[str]:
        return [parte_votada(v) for v in self.rechazos if not articulos(v)]

    @property
    def acta(self) -> Votacion | None:
        return (self.general or self.insistencias or self.particular or [None])[0]


def sesiones(votaciones: list[Votacion]) -> list[Sesion]:
    por_fecha: dict[date | None, Sesion] = {}
    for v in sorted(votaciones, key=lambda x: (x.fecha or date.min, x.id)):
        s = por_fecha.setdefault(v.fecha, Sesion(v.fecha))
        if v.insistencia:
            s.insistencias.append(v)
        elif v.en_general:
            s.general.append(v)
        elif v.en_particular:
            s.particular.append(v)
    return list(por_fecha.values())


__all__ = [
    "Indice", "ErrorVotaciones", "Sesion", "buscar", "corresponde", "relevante", "parsear_listado", "parsear_detalle",
    "parsear_pdf", "texto_pdf", "ultima_votacion_general", "articulos", "rango", "describir_articulos", "sesiones",
]
