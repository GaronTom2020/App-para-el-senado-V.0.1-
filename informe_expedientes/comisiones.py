"""Reuniones de comisión en que se trató un expediente.

Cómo se buscan:
1. Se toman las comisiones a las que fue girado el expediente.
2. Se recorre la lista de reuniones de cada comisión (comisiones/info/{id},
   paginada con ?Reuniones=N), de la más nueva a la más vieja, hasta pasar la
   fecha de ingreso del expediente.
3. Se abre cada nota de reunión de ese período y se busca el expediente en el
   temario: primero por el enlace a su ficha (verExp/...), después por el texto
   (S-1234/24, CD 14/24, 1234-S-2024…).
4. De cada nota se toman la versión taquigráfica, el video y otros archivos.

La agenda (comisiones/agenda/{id}) se revisa igual para encontrar reuniones
ya convocadas.
"""

from __future__ import annotations

import difflib
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import urljoin

from bs4 import NavigableString

from . import config
from .cliente import Cancelado, Cliente, ErrorRed
from .identificador import IdExpediente
from .modelos import BusquedaReuniones, Documento, Ficha, Reunion, ReunionConvocada
from .paginas import encabezado, filas_datos, meta, sopa, texto
from .util import (
    MESES, desescapar, fmt_fecha, limpiar, nombre_comision, normalizar, parsear_fecha,
    parsear_fecha_larga, sin_acentos,
)

RE_NOTA = re.compile(r"/(?:micrositios/nota|prensa)/(\d+)/noticias")
RE_YOUTUBE = re.compile(
    r"(?:youtube(?:-nocookie)?\.com/(?:embed/|live/|shorts/|v/|watch\?(?:[^\"'\s<>]*?&(?:amp;)?)?v=)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)
RE_FECHA_LISTADO = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")
SECCIONES_REUNION = {"REUNIONES", "REUNIONES VARIAS", "REUNIONES DE COMISION"}
_MARCA = re.compile(r"(⟦[^⟧]*⟧)")

# ===================================================================== comisiones

_mapa: dict[int, str] = dict(config.COMISIONES)
_bloqueo_mapa = threading.Lock()


def actualizar_mapa_comisiones(html: str) -> int:
    """Lee el selector de comisiones del buscador y actualiza los números internos."""
    s = sopa(html)
    selector = s.find("select", attrs={"name": "busqueda_proyectos[comision]"})
    if not selector:
        return 0
    nuevas = {}
    for opcion in selector.find_all("option"):
        valor = (opcion.get("value") or "").strip()
        nombre = texto(opcion)
        if valor.isdigit() and nombre:
            nuevas[int(valor)] = nombre
    with _bloqueo_mapa:
        _mapa.update(nuevas)
    return len(nuevas)


def _clave_comision(nombre: str) -> str:
    n = normalizar(nombre)
    n = re.sub(r"^(COMISION\s+)?(UNICAMERAL\s+)?", "", n)
    n = re.sub(r"^(PERMANENTE\s+)?DE\s+", "", n)
    return limpiar(re.sub(r"[^A-Z0-9 ]", " ", n))


def id_comision(nombre: str) -> int | None:
    clave = _clave_comision(nombre)
    if not clave:
        return None
    with _bloqueo_mapa:
        candidatos = list(_mapa.items())
    for cid, n in candidatos:
        if _clave_comision(n) == clave:
            return cid
    mejor, puntaje = None, 0.0
    for cid, n in candidatos:
        p = difflib.SequenceMatcher(None, clave, _clave_comision(n)).ratio()
        if p > puntaje:
            mejor, puntaje = cid, p
    return mejor if puntaje >= 0.88 else None


# ======================================================== listado de reuniones

@dataclass
class EntradaListado:
    nota_id: str
    url: str
    titulo: str
    fecha: date | None
    seccion: str | None
    comisiones: set = field(default_factory=set)


def parsear_listado(html: str, url_base: str, comision_id: int) -> tuple[list[EntradaListado], dict[str, int]]:
    """Entradas (nota, título, fecha, sección) y páginas disponibles por parámetro."""
    s = sopa(html)

    paginas: dict[str, int] = {}
    for a in s.find_all("a", href=True):
        href = a["href"]
        if f"/info/{comision_id}" not in href and not href.startswith("?"):
            continue
        for parametro, numero in re.findall(r"[?&]([A-Za-z]+)=(\d+)", href):
            paginas[parametro] = max(paginas.get(parametro, 0), int(numero))

    for h in s.find_all(re.compile(r"^h[1-6]$")):
        if any(RE_NOTA.search(a["href"]) for a in h.find_all("a", href=True)):
            continue
        nombre = normalizar(h.get_text(" "))
        if nombre and len(nombre) < 60:
            h.replace_with(NavigableString(f"\n⟦SEC|{nombre}⟧\n"))

    for a in s.find_all("a", href=True):
        m = RE_NOTA.search(a["href"])
        if not m:
            continue
        titulo = texto(a)
        if not titulo:
            a.decompose()          # miniatura de la foto, enlaza a la misma nota
            continue
        url = urljoin(url_base, a["href"])
        titulo = titulo.replace("|", "/").replace("⟧", ")")
        a.replace_with(NavigableString(f"\n⟦NOTA|{m.group(1)}|{url}|{titulo}⟧\n"))

    entradas: dict[str, EntradaListado] = {}
    seccion = None
    actual = None
    for parte in _MARCA.split(s.get_text("\n")):
        if parte.startswith("⟦SEC|"):
            seccion = parte[5:-1]
            actual = None
        elif parte.startswith("⟦NOTA|"):
            _, nota_id, url, titulo = parte[1:-1].split("|", 3)
            if nota_id in entradas:
                actual = entradas[nota_id]
            else:
                actual = EntradaListado(nota_id, url, limpiar(titulo), None, seccion)
                entradas[nota_id] = actual
        elif actual is not None and actual.fecha is None:
            m = RE_FECHA_LISTADO.search(parte)
            if m:
                actual.fecha = parsear_fecha(m.group(0))
    lista = list(entradas.values())
    # Si no se reconoció ninguna sección de reuniones, no se descarta nada por sección.
    if lista and not any(e.seccion in SECCIONES_REUNION for e in lista):
        for e in lista:
            e.seccion = None
    return lista, paginas


def _seccion_de_parametro(parametro: str) -> str:
    return normalizar(re.sub(r"(?<!^)(?=[A-Z])", " ", parametro))


def listar_reuniones(cliente: Cliente, comision_id: int, desde: date, avisar=None) -> list[EntradaListado]:
    """Recorre las páginas de reuniones de una comisión hasta pasar la fecha `desde`."""
    avisar = avisar or (lambda *a, **k: None)
    url = config.URL_COMISION.format(id=comision_id)
    r = cliente.get(url, ttl=config.TTL_LISTADO)
    entradas, paginas = parsear_listado(r.texto, url, comision_id)
    todas = {e.nota_id: e for e in entradas}
    for parametro, ultima in list(paginas.items()):
        if not parametro.lower().startswith("reuniones"):
            continue
        seccion = _seccion_de_parametro(parametro)
        de_la_seccion = [e for e in entradas if e.seccion == seccion] or entradas
        n = 2
        while n <= min(ultima, config.MAX_PAGINAS_POR_LISTADO):
            fechas = [e.fecha for e in de_la_seccion if e.fecha]
            if fechas and min(fechas) < desde:
                break
            cliente.verificar_cancelacion()
            url_pagina = f"{url}?{parametro}={n}"
            try:
                rp = cliente.get(url_pagina, ttl=config.TTL_LISTADO)
            except ErrorRed as e:
                avisar("advertencia", f"No se pudo leer la página {n} de reuniones de la comisión {comision_id}: {e}")
                break
            nuevas, paginas_n = parsear_listado(rp.texto, url, comision_id)
            ultima = max(ultima, paginas_n.get(parametro, 0))
            de_la_seccion = [e for e in nuevas if e.seccion == seccion] or nuevas
            agregadas = 0
            for e in nuevas:
                if e.nota_id not in todas:
                    todas[e.nota_id] = e
                    agregadas += 1
            if not agregadas:
                break
            n += 1
    return list(todas.values())


# ================================================================ notas

def analizar_nota(html: str, ident: IdExpediente) -> dict | None:
    """Si la nota menciona el expediente, devuelve sus datos; si no, None."""
    s = sopa(html)
    menciona = any(ident.coincide_url(a["href"]) for a in s.find_all("a", href=True))
    contenido = s.get_text(" ")
    if not menciona and not ident.patron_texto().search(contenido):
        return None

    titulo = limpiar(meta(s, "og:title"))
    if not titulo:
        h2 = s.find("h2")
        titulo = texto(h2) if h2 else (texto(s.title) if s.title else "")
    resumen = desescapar(meta(s, "og:description") or meta(s, "description"))
    if len(resumen) > 600:
        resumen = resumen[:597].rsplit(" ", 1)[0] + "…"

    videos = []
    for vid in RE_YOUTUBE.findall(html):
        url = f"https://www.youtube.com/watch?v={vid}"
        if url not in videos:
            videos.append(url)

    versiones, otros = _archivos(s)
    return {
        "titulo": titulo,
        "resumen": resumen,
        "fecha": parsear_fecha_larga(limpiar(contenido)),
        "videos": videos,
        "versiones": versiones,
        "otros": otros,
    }


def _es_version_taquigrafica(descripcion: str) -> bool:
    n = normalizar(descripcion)
    return "TAQUIGR" in n or bool(re.search(r"\bV\.?\s?T\b", n))


def _archivos(s) -> tuple[list[Documento], list[Documento]]:
    versiones: list[Documento] = []
    otros: list[Documento] = []
    vistos: set[str] = set()

    def agregar(descripcion: str, href: str) -> None:
        url = urljoin(config.BASE, href)
        if url in vistos:
            return
        vistos.add(url)
        doc = Documento(descripcion or "Archivo", url)
        (versiones if _es_version_taquigrafica(descripcion) else otros).append(doc)

    for tabla in s.find_all("table"):
        if "ARCHIVO" not in " ".join(encabezado(tabla)):
            continue
        for tr in filas_datos(tabla):
            anclas = tr.find_all("a", href=True)
            if not anclas:
                continue
            tds = tr.find_all("td")
            descripcion = texto(tds[-1]) if tds else ""
            agregar(descripcion or texto(anclas[-1]), anclas[-1]["href"])
    if not vistos:
        for a in s.find_all("a", href=re.compile(r"/upload/archivo/\d+")):
            descripcion = texto(a)
            if descripcion:
                agregar(descripcion, a["href"])
    return versiones, otros


def _tipo_reunion(titulo: str, seccion: str | None, comisiones: set) -> str:
    n = normalizar(titulo)
    if "ASESOR" in n:
        return "Asesores"
    if len(comisiones) > 1 or "PLENARI" in n or "CONJUNTA" in n:
        return "Plenario"
    return "Comisión"


def _revisar_nota(cliente: Cliente, e: EntradaListado, ident: IdExpediente, hoy: date, avisar) -> Reunion | None:
    antigua = e.fecha is not None and (hoy - e.fecha).days > 60
    ttl = config.TTL_NOTA_ANTIGUA if antigua else config.TTL_NOTA_RECIENTE
    try:
        r = cliente.get(e.url, ttl=ttl)
    except ErrorRed as err:
        avisar("advertencia", f"No se pudo abrir la nota «{e.titulo}»: {err}")
        return None
    datos = analizar_nota(r.texto, ident)
    if not datos:
        return None
    titulo = datos["titulo"] or e.titulo
    return Reunion(
        url=e.url,
        nota_id=e.nota_id,
        titulo=titulo,
        fecha=e.fecha or datos["fecha"],
        comisiones=sorted(e.comisiones),
        tipo=_tipo_reunion(titulo, e.seccion, e.comisiones),
        resumen=datos["resumen"],
        videos=datos["videos"],
        versiones=datos["versiones"],
        otros_archivos=datos["otros"],
    )


def periodo_busqueda(ficha: Ficha, hoy: date) -> tuple[date, date]:
    inicios = [g.ingreso for g in ficha.giros if g.ingreso]
    if ficha.fecha_mesa_entradas:
        inicios.append(ficha.fecha_mesa_entradas)
    desde = (min(inicios) - timedelta(days=1)) if inicios else date(ficha.id.anio, 1, 1)
    egresos = [g.egreso for g in ficha.giros if g.egreso]
    if any(g.abierto for g in ficha.giros) or not egresos:
        hasta = hoy
    else:
        hasta = min(hoy, max(egresos) + timedelta(days=7))
    return desde, hasta


def buscar_reuniones(
    cliente: Cliente,
    ficha: Ficha,
    incluir_asesores: bool = True,
    max_hilos: int = config.HILOS_POR_DEFECTO,
    avisar=None,
    hoy: date | None = None,
) -> tuple[list[Reunion], BusquedaReuniones]:
    avisar = avisar or (lambda *a, **k: None)
    hoy = hoy or date.today()
    busqueda = BusquedaReuniones(realizada=True, incluye_asesores=incluir_asesores)

    comisiones: dict[int, str] = {}
    for g in ficha.giros:
        g.comision_id = g.comision_id or id_comision(g.comision)
        if g.comision_id:
            comisiones.setdefault(g.comision_id, g.comision)
        elif g.comision not in busqueda.comisiones_sin_pagina:
            busqueda.comisiones_sin_pagina.append(g.comision)
    busqueda.comisiones = [nombre_comision(n) for n in comisiones.values()]
    if not comisiones:
        busqueda.motivo = "El expediente no tiene giros a comisiones con página en el sitio."
        return [], busqueda

    desde, hasta = periodo_busqueda(ficha, hoy)
    busqueda.desde, busqueda.hasta = desde, hasta

    entradas: dict[str, EntradaListado] = {}
    for cid, nombre in comisiones.items():
        avisar("etapa", f"Revisando el listado de reuniones de {nombre_comision(nombre)}…")
        try:
            lista = listar_reuniones(cliente, cid, desde, avisar)
        except ErrorRed as e:
            avisar("advertencia", f"No se pudo leer la página de la comisión {nombre_comision(nombre)}: {e}")
            busqueda.comisiones_sin_pagina.append(nombre)
            continue
        for e in lista:
            previa = entradas.get(e.nota_id)
            if previa:
                previa.comisiones.add(nombre)
            else:
                e.comisiones = {nombre}
                entradas[e.nota_id] = e

    def es_candidata(e: EntradaListado) -> bool:
        if e.seccion and e.seccion not in SECCIONES_REUNION:
            return False
        if not incluir_asesores and ("ASESOR" in normalizar(e.titulo) or e.seccion == "REUNIONES VARIAS"):
            return False
        if e.fecha and not (desde <= e.fecha <= hasta):
            return False
        return True

    candidatas = [e for e in entradas.values() if es_candidata(e)]
    busqueda.notas_revisadas = len(candidatas)
    avisar("etapa", f"Revisando el temario de {len(candidatas)} reuniones "
                    f"({fmt_fecha(desde)} a {fmt_fecha(hasta)})…")
    avisar("progreso", actual=0, total=max(1, len(candidatas)))

    reuniones: list[Reunion] = []
    if candidatas:
        with ThreadPoolExecutor(max_workers=max(1, max_hilos)) as ejecutor:
            futuros = [ejecutor.submit(_revisar_nota, cliente, e, ficha.id, hoy, avisar) for e in candidatas]
            try:
                for hechos, futuro in enumerate(as_completed(futuros), 1):
                    reunion = futuro.result()
                    avisar("progreso", actual=hechos, total=len(candidatas))
                    if reunion:
                        reuniones.append(reunion)
                        avisar("log", f"Encontrado en: {fmt_fecha(reunion.fecha)} {reunion.titulo}")
            except Cancelado:
                for f in futuros:
                    f.cancel()
                raise
    reuniones.sort(key=lambda r: (r.fecha or date.min, r.titulo))
    return reuniones, busqueda


# ===================================================================== agenda

_DIAS = "LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO"
_RE_DIA = re.compile(rf"\b(?:{_DIAS})\s+(\d{{1,2}})\s+DE\s+([A-Z]+)(?:\s+DE\s+(\d{{4}}))?")
_RE_HORA = re.compile(r"^(?:HORA\s*:\s*)?(\d{1,2})[:.](\d{2})\s*(?:H|HS|HORAS)?\.?$")


def _fecha_agenda(dia: str, mes: str, anio: str | None, hoy: date) -> date | None:
    numero_mes = MESES.get(mes)
    if not numero_mes:
        return None
    try:
        if anio:
            return date(int(anio), numero_mes, int(dia))
        candidata = date(hoy.year, numero_mes, int(dia))
        if candidata < hoy - timedelta(days=60):   # agenda de enero vista en diciembre
            candidata = date(hoy.year + 1, numero_mes, int(dia))
        return candidata
    except ValueError:
        return None


def parsear_agenda(html: str, url: str, ident: IdExpediente, comision: str, hoy: date) -> list[ReunionConvocada]:
    s = sopa(html)
    marcado = False
    for a in s.find_all("a", href=True):
        if ident.coincide_url(a["href"]):
            a.replace_with(NavigableString(" ⟦EXP⟧ "))
            marcado = True
    contenido = s.get_text("\n")
    if not marcado:
        contenido = ident.patron_texto().sub(" ⟦EXP⟧ ", contenido)
    lineas = [limpiar(l) for l in contenido.split("\n")]
    lineas = [l for l in lineas if l]
    normal = [normalizar(sin_acentos(l)) for l in lineas]

    convocadas: list[ReunionConvocada] = []
    vistas = set()
    for i, linea in enumerate(lineas):
        if "⟦EXP⟧" not in linea:
            continue
        fecha = None
        fecha_texto = hora = lugar = nombre = ""
        for j in range(i - 1, max(-1, i - 600), -1):
            m = _RE_DIA.search(normal[j])
            if m and not normal[j].startswith("FECHA"):
                fecha = _fecha_agenda(m.group(1), m.group(2), m.group(3), hoy)
                fecha_texto = lineas[j]
                bloque = lineas[j + 1:i]
                if bloque and not _RE_HORA.match(normalizar(bloque[0])):
                    nombre = bloque[0]
                for k, valor in enumerate(bloque):
                    if _RE_HORA.match(normalizar(valor)):
                        hora = re.sub(r"\s*(H|HS|HORAS)\.?$", "", valor, flags=re.I)
                        siguiente = bloque[k + 1] if k + 1 < len(bloque) else ""
                        if siguiente and "TEMARIO" not in normalizar(siguiente):
                            lugar = siguiente
                        break
                break
        titulo = ""
        for k in range(i + 1, min(len(lineas), i + 400)):
            n = normal[k]
            if _RE_DIA.search(n) and not n.startswith("FECHA"):
                break
            if n.startswith("REUNION") and not titulo:
                titulo = lineas[k]
            if n.startswith("UBICACION") and not lugar:
                lugar = limpiar(lineas[k].split(":", 1)[-1])
            if n.startswith("HORA") and not hora:
                hora = limpiar(lineas[k].split(":", 1)[-1])
        clave = (fecha, hora, normalizar(nombre or comision))
        if clave in vistas:
            continue
        vistas.add(clave)
        convocadas.append(ReunionConvocada(
            fecha=fecha, fecha_texto=fecha_texto, hora=hora, lugar=lugar,
            titulo=titulo or "Reunión convocada",
            comision=nombre_comision(nombre) if nombre else comision, url=url,
        ))
    return convocadas


def buscar_convocatorias(cliente: Cliente, ficha: Ficha, avisar=None, hoy: date | None = None) -> list[ReunionConvocada]:
    avisar = avisar or (lambda *a, **k: None)
    hoy = hoy or date.today()
    giros = [g for g in ficha.giros if g.abierto] or ficha.giros
    comisiones: dict[int, str] = {}
    for g in giros:
        g.comision_id = g.comision_id or id_comision(g.comision)
        if g.comision_id:
            comisiones.setdefault(g.comision_id, g.comision)
    resultado: list[ReunionConvocada] = []
    for cid, nombre in comisiones.items():
        url = config.URL_AGENDA.format(id=cid)
        try:
            r = cliente.get(url, ttl=config.TTL_AGENDA)
        except ErrorRed as e:
            avisar("advertencia", f"No se pudo leer la agenda de {nombre_comision(nombre)}: {e}")
            continue
        for c in parsear_agenda(r.texto, url, ficha.id, nombre_comision(nombre), hoy):
            if c.fecha is None or c.fecha >= hoy - timedelta(days=1):
                resultado.append(c)
    resultado.sort(key=lambda c: (c.fecha or date.max, c.hora))
    return resultado
