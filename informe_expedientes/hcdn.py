"""El expediente en el sitio de la Cámara de Diputados (www.hcdn.gob.ar/proyectos).

El buscador de Diputados encuentra un proyecto por su número del Senado y trae, en
una sola página, el número que le asignó Diputados (NNNN-S-AAAA para los que vienen
del Senado), los giros y dictámenes de las dos cámaras y el trámite completo:
media sanción, pase a la otra cámara, sanción, veto e insistencia, con los artículos
aprobados con modificaciones o rechazados en particular (al menos en Diputados).

Sirve para contrastar la ficha del Senado, que a veces registra tarde lo que pasó.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from . import config
from .cliente import Cliente
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
    return (f"{config.URL_HCDN_BUSQUEDA}?{PARAMETROS}&strNumExp={ident.numero}"
            f"&strNumExpOrig={ident.origen}&strNumExpAnio={ident.anio}")


def buscar(cliente: Cliente, ident: IdExpediente) -> ProyectoHCDN | None:
    """El proyecto cuyo «Expediente Senado» es este (la búsqueda puede traer otros con el mismo número)."""
    url = url_busqueda(ident)
    buscado = numero_hcdn(ident)
    for p in parsear_resultado(cliente.get(url, ttl=TTL_HCDN).texto, url):
        if p.expediente_senado == buscado:
            return p
    return None


__all__ = ["Movimiento", "Dictamen", "ProyectoHCDN", "parsear_resultado", "buscar", "numero_hcdn",
           "articulos_en_texto", "url_busqueda"]
