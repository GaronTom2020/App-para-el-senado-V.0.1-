"""El expediente en el sitio de la Cámara de Diputados (www.hcdn.gob.ar/proyectos).

El buscador de Diputados encuentra un proyecto por su número del Senado y trae, en
una sola página, el número que le asignó Diputados (NNNN-S-AAAA para los que vienen
del Senado), los giros y dictámenes de las dos cámaras y el trámite completo:
media sanción, pase a la otra cámara, sanción, veto e insistencia, con los artículos
aprobados con modificaciones o rechazados en particular (al menos en Diputados).

Sirve para contrastar la ficha del Senado, que a veces registra tarde lo que pasó.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import quote, urlencode

from . import config
from .cliente import Cliente, ErrorRed
from .identificador import IdExpediente
from .paginas import sopa, texto
from .util import limpiar, normalizar, parsear_fecha

TTL_HCDN = 6 * 3600
PARAMETROS = ("zezion=true&strTipo=todos&strCantPagina=20&strMostrarTramites=on&strMostrarDictamenes=on"
              "&strMostrarFirmantes=on&strMostrarComisiones=on")


@dataclass
class Movimiento:
    camara: str            # Senado · Diputados
    movimiento: str
    fecha: date | None
    resultado: str = ""    # MEDIA SANCION · SANCIONADO · …


@dataclass
class Dictamen:
    camara: str
    orden_del_dia: str     # «0006/2025»
    texto: str
    fecha: date | None


@dataclass
class Estado:
    """En qué está el proyecto en una cámara: rechazado · sancionado · modificado · aprobado · con_dictamen ·
    en_comision · ingresado."""
    clave: str
    texto: str
    fecha: date | None = None
    comisiones: list[str] = field(default_factory=list)


def _f(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


_MAYORIAS = [
    (r"\bCON MODIFICACIONES\b", "con modificaciones"),
    (r"\bSIN MODIFICACIONES\b", "sin modificaciones"),
    (r"\bACONSEJA (?:SU|LA) SANCION\b", "aconseja su sanción"),
    (r"\bACONSEJA (?:SU|EL) RECHAZO\b", "aconseja su rechazo"),
    (r"\bACONSEJA (?:APROBAR|LA APROBACION)\b", "aconseja aprobarlo"),
    (r"\bACONSEJA ACEPTAR LAS MODIFICACIONES\b", "aconseja aceptar las modificaciones"),
]


def mayoria(texto: str) -> str:
    """Qué aconseja el dictamen de mayoría, en pocas palabras («con modificaciones», «aconseja su sanción»)."""
    n = normalizar(texto)
    m = re.search(r"DICTAMEN DE MAYORIA:\s*([^;]+)", n)
    clausula = m.group(1) if m else n
    return next((texto_ for patron, texto_ in _MAYORIAS if re.search(patron, clausula)), "")


def _od(numero: str) -> str:
    """«0448/2026» → «448/2026»."""
    n, _, a = numero.partition("/")
    return f"{int(n)}/{a}" if n.isdigit() else numero


@dataclass
class ProyectoHCDN:
    titulo: str
    iniciado_en: str = ""
    expediente_diputados: str | None = None     # 0065-S-2025
    expediente_senado: str | None = None        # 0159-PE-2025
    publicado_en: str = ""
    fecha: date | None = None
    ley: str | None = None
    extracto: str = ""
    giros_diputados: list[str] = field(default_factory=list)
    giros_senado: list[str] = field(default_factory=list)
    dictamenes: list[Dictamen] = field(default_factory=list)
    tramite: list[Movimiento] = field(default_factory=list)
    textos: list[tuple[str, str]] = field(default_factory=list)   # (etiqueta, url)
    url: str = ""

    # ---- lecturas del trámite
    def _de(self, camara: str) -> list[Movimiento]:
        return [m for m in self.tramite if normalizar(m.camara).startswith(normalizar(camara)[:5])]

    def sanciones(self) -> list[Movimiento]:
        """Media sanción o sanción de cada cámara, en orden."""
        return [m for m in self.tramite if normalizar(m.resultado) in ("MEDIA SANCION", "SANCIONADO")]

    def ultima_sancion(self, camara: str) -> Movimiento | None:
        propias = [m for m in self.sanciones() if m in self._de(camara)]
        return propias[-1] if propias else None

    def veto(self) -> Movimiento | None:
        return next((m for m in self.tramite if re.search(r"\bVETO\b|OBSERVA (TOTAL|PARCIAL)", normalizar(m.movimiento))),
                    None)

    def insistencia(self) -> list[Movimiento]:
        return [m for m in self.tramite if "INSISTENCIA" in normalizar(m.movimiento) and m.fecha]

    def pases(self) -> list[Movimiento]:
        return [m for m in self.tramite if re.match(r"(PASA|VUELVE) A ", normalizar(m.movimiento))]

    def rechazos(self) -> list[Movimiento]:
        """Rechazo total del proyecto en una cámara (el sitio lo marca con el resultado «RECHAZADO»)."""
        return [m for m in self.tramite if normalizar(m.resultado) == "RECHAZADO"]

    def dictamenes_de(self, camara: str) -> list[Dictamen]:
        return [d for d in self.dictamenes if normalizar(d.camara).startswith(normalizar(camara)[:5])]

    def estado(self, camara: str = "Diputados", origen: str = "Senado") -> "Estado | None":
        """En qué está el proyecto en esa cámara, según su trámite (del último hecho al primero)."""
        propios = self._de(camara)
        rechazo = next((m for m in reversed(self.rechazos()) if m in propios), None)
        if rechazo:
            return Estado("rechazado", f"rechazado el {_f(rechazo.fecha)}", rechazo.fecha)
        sancion = self.ultima_sancion(camara)
        if sancion:
            if normalizar(sancion.resultado) == "SANCIONADO":
                return Estado("sancionado", f"sanción definitiva el {_f(sancion.fecha)}", sancion.fecha)
            vuelve = any(normalizar(m.movimiento).startswith(f"VUELVE A {normalizar(origen)}")
                         for m in self.tramite[self.tramite.index(sancion):])
            if vuelve and normalizar(camara) != normalizar(origen):
                return Estado("modificado", f"aprobado con modificaciones el {_f(sancion.fecha)}: vuelve "
                                            f"{'al Senado' if normalizar(origen).startswith('SENAD') else 'a Diputados'}",
                              sancion.fecha)
            texto = "media sanción" if normalizar(camara) == normalizar(origen) else "aprobado"
            return Estado("aprobado", f"{texto} el {_f(sancion.fecha)}", sancion.fecha)
        dictamenes = self.dictamenes_de(camara)
        if dictamenes:
            d = dictamenes[-1]
            extra = f", {mayoria(d.texto)}" if mayoria(d.texto) else ""
            return Estado("con_dictamen", f"con dictamen de comisión: Orden del Día N° {_od(d.orden_del_dia)} "
                                          f"({_f(d.fecha)}){extra}", d.fecha)
        giros = self.giros_diputados if normalizar(camara).startswith("DIPUT") else self.giros_senado
        if giros:
            return Estado("en_comision", "en comisión", None, giros)
        if any(normalizar(m.movimiento).startswith(f"PASA A {normalizar(camara)}") for m in self.tramite):
            return Estado("ingresado", "ingresó, todavía sin giro a comisión", None)
        return None

    def articulos_en_particular(self, camara: str) -> tuple[list[str], list[str]]:
        """(modificados, rechazados) en las votaciones en particular de la cámara, si el trámite los nombra."""
        modificados, rechazados = [], []
        for m in self._de(camara):
            n = normalizar(m.movimiento)
            if "EN PARTICULAR" not in n:
                continue
            numeros = articulos_en_texto(n)
            if not numeros:
                continue
            if "RECHAZO" in n:
                rechazados += numeros
            elif "MODIFICACION" in n:
                modificados += numeros
        return modificados, rechazados


def articulos_en_texto(texto_normalizado: str) -> list[str]:
    """«… DE LOS ARTICULOS 2, 3, 4, 5 Y 6 (…)» → ['2', '3', '4', '5', '6']; «ARTICULO PROPUESTO COMO 7» → ['7']."""
    m = re.search(r"ARTICULOS?\s+(?:PROPUESTO\s+COMO\s+)?((?:\d+\s*(?:BIS|TER)?\s*(?:,|Y|AL|A)?\s*)+)", texto_normalizado)
    if not m:
        return []
    lista = m.group(1)
    salida: list[str] = []
    for a, b in re.findall(r"(\d+)\s*(?:AL|A)\s*(\d+)", lista):
        salida += [str(i) for i in range(int(a), int(b) + 1)]
    lista = re.sub(r"(\d+)\s*(?:AL|A)\s*(\d+)", " ", lista)
    salida += [f"{x} {y.lower()}".strip() for x, y in re.findall(r"(\d+)\s*(BIS|TER)?", lista)]
    return salida


# ===================================================================== lectura

def _tabla(contenedor, titulo: str):
    for h5 in contenedor.find_all("h5"):
        if normalizar(h5.get_text()).startswith(normalizar(titulo)):
            return h5.find_next("table")
    return None


def _filas(tabla) -> list[list[str]]:
    if tabla is None:
        return []
    return [[texto(td) for td in tr.find_all("td")] for tr in tabla.find_all("tr") if tr.find("td")]


def parsear_resultado(html: str, url: str = "") -> list[ProyectoHCDN]:
    s = sopa(html)
    proyectos = []
    for caja in s.find_all("div", class_="resultado_wrapper"):
        h4 = caja.find("h4")
        p = ProyectoHCDN(titulo=texto(h4), url=url)
        for span in caja.select(".dp-metadata span"):
            etiqueta = normalizar(span.get_text(" ").split(":")[0])
            valor = texto(span.find("strong")) if span.find("strong") else ""
            if etiqueta.startswith("INICIADO"):
                p.iniciado_en = valor
            elif etiqueta == "EXPEDIENTE DIPUTADOS":
                p.expediente_diputados = valor
            elif etiqueta == "EXPEDIENTE SENADO":
                p.expediente_senado = valor
            elif etiqueta.startswith("PUBLICADO"):
                p.publicado_en = valor
            elif etiqueta == "FECHA":
                p.fecha = parsear_fecha(valor)
            elif etiqueta.startswith("LEY"):
                p.ley = valor or re.sub(r"\D", "", span.get_text())
        p.extracto = texto(caja.find("div", class_="dp-texto"))
        p.giros_diputados = [f[0] for f in _filas(_tabla(caja, "GIRO A COMISIONES EN DIPUTADOS")) if f]
        p.giros_senado = [f[0] for f in _filas(_tabla(caja, "GIRO A COMISIONES EN SENADO")) if f]
        for f in _filas(_tabla(caja, "DICTAMENES")):
            if len(f) >= 4:
                od = re.search(r"(\d+/\d{4})", f[1])
                p.dictamenes.append(Dictamen(f[0], od.group(1) if od else f[1], f[2], parsear_fecha(f[3])))
        for f in _filas(_tabla(caja, "TRAMITE")):
            if len(f) >= 3:
                p.tramite.append(Movimiento(f[0], limpiar(f[1]), parsear_fecha(f[2]),
                                            limpiar(f[3]) if len(f) > 3 and f[3] != "-" else ""))
        botones = caja.find("div", class_="btnDoc_wrapper")
        if botones:
            p.textos = [(texto(a), a["href"]) for a in botones.find_all("a", href=True)]
        proyectos.append(p)
    return proyectos


def numero_hcdn(ident: IdExpediente) -> str:
    """S-1234/24 → «1234-S-2024», como el sitio de Diputados escribe el número del Senado."""
    return f"{ident.numero:04d}-{ident.origen}-{ident.anio}"


def url_busqueda(ident: IdExpediente) -> str:
    """La búsqueda vieja (resultado.html); Diputados la dio de baja en noviembre de 2026."""
    return (f"{config.URL_HCDN_BUSQUEDA}?{PARAMETROS}&strNumExp={ident.numero}"
            f"&strNumExpOrig={ident.origen}&strNumExpAnio={ident.anio}")


class BuscadorFueraDeServicio(ErrorRed):
    """El buscador de proyectos de Diputados no está disponible (página dada de baja o «en construcción»).
    No es lo mismo que «el proyecto no figura»: no se sabe nada del trámite en Diputados."""


AVISO_FUERA_DE_SERVICIO = ("El buscador de proyectos de Diputados está fuera de servicio (el sitio lo muestra "
                           "«en construcción»); no se pudo contrastar el trámite en Diputados.")


def en_construccion(html: str) -> bool:
    """La página provisoria que Diputados muestra en lugar de un buscador dado de baja."""
    return bool(re.search(r"secci[oó]n en construcci[oó]n", html[:5000], re.I))


# ============================================================ buscador nuevo (API)
#
# Desde noviembre de 2026 Diputados publica los proyectos en https://www.hcdn.gob.ar/proyectos/buscador/, que
# lee una API JSON. Trae los mismos datos que la página vieja salvo dos: cada movimiento del trámite viene sin la
# cámara y sin la columna «resultado» (MEDIA SANCION, SANCIONADO…). No se adivinan: los movimientos quedan con
# cámara y resultado vacíos, y todo lo que depende de la cámara sale de lo que la API sí publica por cámara
# (giros, dictámenes, número de ley).

def _fecha_iso(valor) -> date | None:
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def parsear_api(dato: dict) -> ProyectoHCDN:
    """Un proyecto de la API (el detalle trae firmantes y giros; la búsqueda, no) → ProyectoHCDN."""
    p = ProyectoHCDN(titulo=limpiar(dato.get("titulo") or ""))
    p.iniciado_en = dato.get("camara_origen") or ""
    p.expediente_diputados = dato.get("expediente")
    if dato.get("publicacion_tipo") and dato.get("publicacion_numero"):
        p.publicado_en = f"{dato['publicacion_tipo']} N° {dato['publicacion_numero']}"
    p.fecha = _fecha_iso(dato.get("fecha_presentacion"))
    p.ley = str(dato["ley_nro"]) if dato.get("ley_nro") else None
    p.extracto = limpiar(dato.get("sumario") or "")
    for g in dato.get("giros") or []:
        destino = p.giros_senado if normalizar(g.get("camara") or "").startswith("SENAD") else p.giros_diputados
        if normalizar(g.get("camara") or "")[:5] in ("SENAD", "DIPUT"):
            destino.append(g.get("comision") or "")
    for d in dato.get("dictamenes") or []:
        od = f"{d['od_nro']:04d}/{d['od_anio']}" if d.get("od_nro") and d.get("od_anio") else ""
        p.dictamenes.append(Dictamen(d.get("camara") or "", od, limpiar(d.get("detalle") or ""),
                                     _fecha_iso(d.get("fecha"))))
    for m in dato.get("movimientos") or []:
        p.tramite.append(Movimiento("", limpiar(m.get("texto") or ""), _fecha_iso(m.get("fecha"))))
    if dato.get("clave"):
        p.url = config.URL_HCDN_DETALLE.format(clave=dato["clave"])
    return p


def _get_json(cliente: Cliente, url: str, *, detalle: bool = False):
    """La respuesta JSON de la API. Un 404 del detalle es «no existe» (None); un 404 de la búsqueda, o la página
    «en construcción», es que el buscador está fuera de servicio."""
    try:
        r = cliente.get(url, ttl=TTL_HCDN)
    except ErrorRed as e:
        if "código 404" in str(e):
            if detalle:
                return None
            raise BuscadorFueraDeServicio(AVISO_FUERA_DE_SERVICIO) from e
        raise
    if en_construccion(r.texto):
        raise BuscadorFueraDeServicio(AVISO_FUERA_DE_SERVICIO)
    try:
        return json.loads(r.texto)
    except ValueError as e:
        raise BuscadorFueraDeServicio(AVISO_FUERA_DE_SERVICIO) from e


class SinCorroborar(Exception):
    """Diputados tiene un proyecto con ese número, o ninguno, pero nada oficial confirma que sea el del Senado."""


AVISO_SIN_CORROBORAR = ("No se encontró en el buscador de Diputados un proyecto que coincida con la ficha del Senado "
                        "en un dato oficial (Orden del Día del Senado o número de ley); no se contrasta con Diputados.")


def _od_clave(texto: str) -> tuple[int, int] | None:
    """«699/25», «0699/2025» → (699, 2025)."""
    m = re.match(r"\s*0*(\d+)\s*/\s*(\d{2,4})\s*$", texto or "")
    if not m:
        return None
    anio = int(m.group(2))
    return int(m.group(1)), anio + 2000 if anio < 100 else anio


def _ods_senado_ficha(ficha) -> set[tuple[int, int]]:
    return {k for k in (_od_clave(o.numero) for o in ficha.ordenes_del_dia) if k}


def _ods_senado_api(dato: dict) -> set[tuple[int, int]]:
    return {(int(d["od_nro"]), int(d["od_anio"])) for d in dato.get("dictamenes") or []
            if normalizar(d.get("camara") or "").startswith("SENAD") and d.get("od_nro") and d.get("od_anio")}


def ley_de_la_ficha(ficha) -> str | None:
    for b in ficha.resoluciones:
        if normalizar(b.titulo).startswith("SANCION DE LEY"):
            ley = re.sub(r"\D", "", b.valor("NUMERO DE LEY") or "")
            if ley:
                return ley
    return None


def corrobora(dato: dict, ficha) -> bool:
    """¿El proyecto de Diputados es el de esta ficha? Solo con datos oficiales que estén en las dos páginas:
    alguna Orden del Día del Senado en común, o el mismo número de ley."""
    if _ods_senado_api(dato) & _ods_senado_ficha(ficha):
        return True
    ley = ley_de_la_ficha(ficha)
    return bool(ley and re.sub(r"\D", "", str(dato.get("ley_nro") or "")) == ley)


def _items(cliente: Cliente, parametros: dict, *, tolerante: bool = False) -> list[dict]:
    url = config.URL_HCDN_API + "?" + urlencode({"pagina": 1, **parametros, "incluir_movimientos": "true",
                                                 "incluir_dictamenes": "true"})
    try:
        return (_get_json(cliente, url) or {}).get("items") or []
    except BuscadorFueraDeServicio:
        raise
    except ErrorRed:
        if tolerante:      # una búsqueda auxiliar que el buscador no acepta no impide las demás
            return []
        raise


def _completo(cliente: Cliente, item: dict, senado: str) -> ProyectoHCDN:
    """El detalle trae firmantes y giros por cámara; la búsqueda, no."""
    detalle = _get_json(cliente, config.URL_HCDN_API + "/" + quote(item["clave"], safe=""),
                        detalle=True) if item.get("clave") else None
    p = parsear_api(detalle or item)
    p.expediente_senado = senado
    return p


def buscar(cliente: Cliente, ficha) -> ProyectoHCDN | None:
    """El proyecto de esta ficha en el buscador de Diputados.

    - Venidos de Diputados (CD): con el número de Diputados que da la ficha del Senado (CD-14/24 → 0422-D-2024).
      Si la ficha no lo da, None.
    - Del Senado o del Ejecutivo (S, PE…): Diputados les pone su propio número al recibirlos (PE-159/25 → 0065-S-2025)
      y ninguna de las dos páginas publica la equivalencia. Se busca por el número del Senado, por cada Orden del Día
      del Senado y por el número de ley, y solo se acepta un proyecto que coincida con la ficha en un dato oficial
      (corrobora). Si no hay ninguno, SinCorroborar: no se puede afirmar ni que figure ni que no.

    Si el buscador está fuera de servicio, BuscadorFueraDeServicio."""
    ident = ficha.id
    senado = numero_hcdn(ident)
    if ident.origen == "CD":
        numeros = ficha.etapa_diputados.expedientes if ficha.etapa_diputados else []
        for numero in numeros:
            item = next((i for i in _items(cliente, {"exp": numero})
                         if _mismo_numero(i.get("expediente") or "", numero)), None)
            if item is not None:
                return _completo(cliente, item, senado)
        return None
    consultas = [({"exp": senado}, False)]
    consultas += [({"od_nro": n, "od_anio": a}, True) for n, a in sorted(_ods_senado_ficha(ficha))]
    if ley_de_la_ficha(ficha):
        consultas.append(({"ley": ley_de_la_ficha(ficha)}, True))
    for parametros, tolerante in consultas:
        getattr(cliente, "verificar_cancelacion", lambda: None)()
        for item in _items(cliente, parametros, tolerante=tolerante):
            if corrobora(item, ficha):
                return _completo(cliente, item, senado)
    raise SinCorroborar(AVISO_SIN_CORROBORAR)


def _mismo_numero(a: str, b: str) -> bool:
    def partes(x):
        m = re.match(r"0*(\d+)-([A-Z]+)-(\d{4})$", x.strip().upper())
        return m.groups() if m else None
    return partes(a) is not None and partes(a) == partes(b)


__all__ = ["Movimiento", "Dictamen", "ProyectoHCDN", "parsear_resultado", "buscar", "numero_hcdn",
           "articulos_en_texto", "url_busqueda", "BuscadorFueraDeServicio", "en_construccion", "parsear_api",
           "SinCorroborar", "corrobora"]
