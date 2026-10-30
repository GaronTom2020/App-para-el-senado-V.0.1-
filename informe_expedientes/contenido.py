"""Contenido común a los informes Word y HTML y al resumen de la interfaz."""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import config
from .modelos import Ficha, Resultado, Votacion
from .numeros import cantidad, en_letras
from .util import fmt_fecha, nombre_comision, normalizar, parsear_fecha, titulo_es


@dataclass
class Fragmento:
    texto: str
    url: str | None = None


Linea = list[Fragmento]


def _unir(fragmentos: list[Fragmento], separador: str = ", ") -> Linea:
    salida: Linea = []
    for i, f in enumerate(fragmentos):
        if i:
            salida.append(Fragmento(separador))
        salida.append(f)
    return salida


def nombre_tipo(ficha: Ficha) -> str:
    return config.TIPOS.get(ficha.id.tipo or "", "") or titulo_es(ficha.tipo_texto) or "Expediente"


def descripcion(ficha: Ficha) -> str:
    tipo = nombre_tipo(ficha)
    origen = ficha.id.origen
    if origen == "CD":
        return f"{tipo} venido en revisión de la Cámara de Diputados" if tipo.startswith("Proyecto") \
            else f"{tipo}, de la Cámara de Diputados"
    if origen == "S":
        return f"{tipo} presentado en el Senado"
    if origen == "PE":
        return f"{tipo}, remitido por el Poder Ejecutivo Nacional"
    if origen == "JGM":
        return f"{tipo}, remitido por la Jefatura de Gabinete de Ministros"
    if origen == "P":
        return f"{tipo}, presentado por particulares"
    return f"{tipo}, origen: {config.ORIGENES.get(origen, origen).lower()}"


def datos_generales(ficha: Ficha) -> list[tuple[str, Linea]]:
    filas: list[tuple[str, Linea]] = [
        ("Expediente", [Fragmento(f"{ficha.id.corto} ({ficha.id.tipo})", ficha.url)]),
        ("Tipo", [Fragmento(nombre_tipo(ficha))]),
        ("Origen", [Fragmento(config.ORIGENES.get(ficha.id.origen, ficha.origen_texto))]),
    ]
    if ficha.autores:
        filas.append(("Autores" if len(ficha.autores) > 1 else "Autor",
                      _unir([Fragmento(a.nombre, a.url) for a in ficha.autores], "; ")))
    elif ficha.etapa_diputados and ficha.etapa_diputados.autor:
        filas.append(("Autor en Diputados", [Fragmento(titulo_es(ficha.etapa_diputados.autor))]))
    filas.append(("Ingreso por mesa de entradas", [Fragmento(fmt_fecha(ficha.fecha_mesa_entradas))]))
    if ficha.fecha_dado_cuenta:
        filas.append(("Dado cuenta en sesión", [Fragmento(fmt_fecha(ficha.fecha_dado_cuenta))]))
    if ficha.dae:
        filas.append(("Diario de Asuntos Entrados",
                      [Fragmento(f"N° {ficha.dae}" + (f" ({ficha.dae_tipo.lower()})" if ficha.dae_tipo else ""))]))
    textos: list[Fragmento] = []
    if ficha.texto_original:
        textos.append(Fragmento("Texto original (PDF)", ficha.texto_original.url))
    for d in ficha.textos_definitivos:
        textos.append(Fragmento(d.etiqueta, d.url))
    if ficha.texto_definitivo_pendiente and not ficha.textos_definitivos:
        textos.append(Fragmento("texto definitivo en proceso de carga"))
    if textos:
        filas.append(("Textos", _unir(textos, "; ")))
    return filas


def datos_diputados(ficha: Ficha) -> list[tuple[str, Linea]]:
    etapa = ficha.etapa_diputados
    if not etapa:
        return []
    filas: list[tuple[str, Linea]] = []
    if etapa.expedientes:
        filas.append(("Expedientes en Diputados", _unir(
            [Fragmento(e, config.url_hcdn(e)) for e in etapa.expedientes])))
    elif etapa.texto_expedientes:
        filas.append(("Expedientes en Diputados", [Fragmento(etapa.texto_expedientes)]))
    if etapa.orden_del_dia:
        filas.append(("Orden del Día de Diputados (dictamen)", [Fragmento(f"N° {etapa.orden_del_dia}")]))
    if etapa.tramite_parlamentario:
        filas.append(("Trámite Parlamentario", [Fragmento(f"N° {etapa.tramite_parlamentario}")]))
    if etapa.fecha_sancion:
        filas.append(("Sanción de Diputados", [Fragmento(fmt_fecha(etapa.fecha_sancion))]))
    return filas


_ETIQUETAS = {
    "SENADO": "Senado",
    "SANCION DE LEY": "Sanción de ley",
    "PODER EJECUTIVO DE LA NACION": "Poder Ejecutivo de la Nación",
    "CAMARA DE DIPUTADOS": "Cámara de Diputados",
    "FECHA DE SANCION": "Fecha de sanción",
    "SANCION": "Sanción",
    "NOTA": "Nota",
    "COMENTARIO": "Comentario",
    "NUMERO DE LEY": "Número de ley",
    "RESOLUCION": "Resolución",
    "FECHA": "Fecha",
    "DECRETO NUMERO": "Decreto N°",
    "FECHA DEL DECRETO": "Fecha del decreto",
    "BOLETIN OFICIAL NUMERO": "Boletín Oficial N°",
    "FECHA DEL BOLETIN OFICIAL": "Fecha del Boletín Oficial",
}
_VALORES = {"APROBO": "Aprobó", "RECHAZO": "Rechazó", "LEY": "Ley", "MEDIA SANCION": "Media sanción"}


def _etiqueta(texto: str) -> str:
    return _ETIQUETAS.get(normalizar(texto), titulo_es(texto))


def _valor(texto: str) -> str:
    fecha = parsear_fecha(texto) if re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", texto.strip()) else None
    if fecha:
        return fmt_fecha(fecha)
    return _VALORES.get(normalizar(texto), texto)


def bloques_resolucion(ficha: Ficha) -> list[tuple[str, list[tuple[str, str]]]]:
    salida = []
    for b in ficha.resoluciones:
        campos = [(_etiqueta(k), _valor(v)) for k, v in b.campos if v]
        if campos:
            salida.append((_etiqueta(b.titulo), campos))
    return salida


def comisiones_texto(nombres: list[str]) -> str:
    legibles = [nombre_comision(n) for n in nombres]
    if len(legibles) <= 1:
        return "".join(legibles)
    return ", ".join(legibles[:-1]) + " y " + legibles[-1]


def alcance_busqueda(resultado: Resultado) -> str:
    b = resultado.busqueda
    if not b.realizada:
        return b.motivo or "No se buscaron reuniones de comisión."
    if not b.comisiones:
        return b.motivo or "El expediente no tiene giros a comisiones con página en el sitio."
    reuniones = "reunión publicada" if b.notas_revisadas == 1 else "reuniones publicadas"
    texto = (f"Se revisaron {b.notas_revisadas} {reuniones} por "
             f"{'la comisión' if len(b.comisiones) == 1 else 'las comisiones'} de "
             f"{comisiones_texto(b.comisiones)}, entre el {fmt_fecha(b.desde)} y el {fmt_fecha(b.hasta)}")
    texto += ", incluidas las reuniones de asesores." if b.incluye_asesores else ", sin las reuniones de asesores."
    if b.comisiones_sin_pagina:
        texto += f" No se pudo revisar: {comisiones_texto(b.comisiones_sin_pagina)}."
    return texto


# ================================================================ votaciones

def tipo_votacion(v: Votacion) -> str:
    return (v.tipo or "votación").capitalize()


def resultado_votacion(v: Votacion) -> str:
    return v.resultado.capitalize() if v.resultado else "—"


def descripcion_votacion(v: Votacion) -> str:
    titulo = normalizar(v.titulo)
    partes = [v.titulo or "Votación sin título publicado"]
    ods = [od for od in v.ordenes_del_dia if od not in v.titulo]
    if ods:
        partes.append("OD " + ", ".join(ods))
    articulos = [a.strip() for a in v.articulos.split(",") if a.strip()]
    if articulos and "ART" not in titulo:
        partes.append(", ".join(articulos) if len(articulos) <= 3 else f"{articulos[0]} a {articulos[-1]}")
    return " · ".join(partes)


def enlaces_votacion(v: Votacion) -> list[Fragmento]:
    enlaces = []
    if v.url_detalle:
        enlaces.append(Fragmento("Acta", v.url_detalle))
    if v.url_pdf:
        enlaces.append(Fragmento("PDF", v.url_pdf))
    if v.video:
        enlaces.append(Fragmento("Video", v.video))
    return enlaces


def totales_votacion(v: Votacion) -> list[str]:
    if not v.con_totales:
        return ["—"] * 4
    return [str(x if x is not None else "—") for x in (v.afirmativos, v.negativos, v.abstenciones, v.ausentes)]


def texto_votaciones(resultado: Resultado) -> str:
    """Párrafo de la sección, con las cantidades en forma normativa."""
    vs = resultado.votaciones
    if not vs:
        return ("No se encontraron votaciones nominales del recinto sobre este expediente ni sobre sus "
                "órdenes del día.")
    generales = sum(1 for v in vs if v.en_general)
    texto = f"Se registran {cantidad(len(vs), 'votación nominal', 'votaciones nominales', femenino=True)} en el recinto"
    if generales and generales < len(vs):
        otras = len(vs) - generales
        texto += (f": {en_letras(generales, True)} ({generales}) en general y {en_letras(otras, True)} ({otras}) "
                  "en particular o sobre mociones")
    elif generales:
        texto += " en general" if generales == 1 else ", todas en general"
    return texto + "."


def nota_votacion(v: Votacion) -> str:
    """Fuente y datos de quórum de una votación, para el pie de su tabla por bloque."""
    partes = []
    if v.mayoria:
        partes.append(f"Mayoría requerida: {v.mayoria.lower()}")
    if v.quorum:
        partes.append(f"quórum: {v.quorum}")
    if v.presentes:
        partes.append(f"presentes: {v.presentes}")
    if v.presidente:
        partes.append(f"presidencia: {titulo_es(v.presidente)}")
    texto = "; ".join(partes) + "." if partes else ""
    if v.fuente == "pdf":
        texto += (" El detalle oficial del acta todavía no se publicó: los votos salen del PDF del acta"
                  + (" y el bloque de cada senador, del listado de bloques actual." if v.bloques_actuales else "."))
    return texto.strip()


def votaciones_con_bloques(resultado: Resultado) -> list[Votacion]:
    return [v for v in resultado.votaciones if v.en_general and v.votos]


def texto_resumen(resultado: Resultado) -> str:
    """Resumen en texto plano (vista previa y «Copiar resumen»)."""
    f, s = resultado.ficha, resultado.situacion
    lineas = [
        f"Expediente {f.id.corto} ({f.id.tipo})",
        descripcion(f),
        f.extracto,
        "",
        f"Situación: {s.titulo}",
    ]
    lineas += [f"  {d}" for d in s.detalle]
    if s.caducidad:
        etiqueta = "Caducidad registrada" if s.caducidad.registrada else "Caducidad estimada"
        lineas.append(f"  {etiqueta}: {fmt_fecha(s.caducidad.fecha)}")
    lineas += ["", "Datos del expediente"]
    for etiqueta, linea in datos_generales(f) + datos_diputados(f):
        lineas.append(f"  {etiqueta}: " + "".join(fr.texto for fr in linea))
    if f.giros:
        lineas += ["", "Giros a comisiones"]
        for g in f.giros:
            lineas.append(f"  {nombre_comision(g.comision)} (orden {g.orden or '—'}): "
                          f"ingreso {fmt_fecha(g.ingreso)}, egreso {fmt_fecha(g.egreso)}")
    lineas += ["", f"Reuniones de comisión en que se trató: {len(resultado.reuniones)}"]
    for r in resultado.reuniones:
        lineas.append(f"  {fmt_fecha(r.fecha)}  {r.titulo}  [{r.tipo}]")
        lineas.append(f"      {r.url}")
    if resultado.convocadas:
        lineas += ["", "Próximas reuniones convocadas"]
        for c in resultado.convocadas:
            lineas.append(f"  {fmt_fecha(c.fecha)} {c.hora}  {c.comision}  {c.lugar}")
    if resultado.votaciones:
        lineas += ["", "Votaciones en el recinto"]
        for v in resultado.votaciones:
            totales = "-".join(totales_votacion(v)) if v.con_totales else "sin totales publicados"
            lineas.append(f"  {fmt_fecha(v.fecha)}  {tipo_votacion(v)}: {resultado_votacion(v)} ({totales})")
            lineas.append(f"      {descripcion_votacion(v)}  {v.url or ''}")
    if f.ordenes_del_dia:
        lineas += ["", "Órdenes del Día del Senado"]
        for od in f.ordenes_del_dia:
            lineas.append(f"  N° {od.numero} ({fmt_fecha(od.fecha)}): {od.estado}")
    lineas += ["", f"Fuente: {f.url}"]
    return "\n".join(lineas)
