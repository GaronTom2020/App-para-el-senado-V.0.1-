"""Contenido común a los informes Word y HTML y al resumen de la interfaz."""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import config
from . import hcdn as hcdn_mod, relacionados as relacionados_mod, votaciones as votaciones_mod
from .modelos import Ficha, Resultado, Votacion
from .numeros import cantidad
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


def texto_od(resultado: Resultado) -> str:
    """«Despacho único de la Orden del Día N° 366/26, integrado por tres (3) expedientes; cabecera: S-718/26.»"""
    n = len(resultado.od_expedientes)
    if n <= 1:
        return f"Despacho de la Orden del Día N° {resultado.od} sobre el expediente {resultado.ficha.id.corto}."
    return (f"Despacho único de la Orden del Día N° {resultado.od}, integrado por "
            f"{cantidad(n, 'expediente', 'expedientes')}: desde el dictamen tramitan juntos, como parte del mismo "
            f"despacho. La ficha que sigue es la del expediente cabecera, {resultado.ficha.id.corto}.")


def integrantes_od(resultado: Resultado) -> Linea:
    """Los expedientes de la OD, con enlace a cada ficha (cabecera primero)."""
    return _unir([Fragmento(x.corto, x.url_ficha() if x.tipo else None) for x in resultado.od_expedientes])


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

@dataclass
class SesionVotada:
    fecha: str
    lineas: list[str]
    enlaces: list[Fragmento]


def _cuenta(v: Votacion) -> str:
    return f" ({v.afirmativos} a {v.negativos})" if v.con_totales else ""


def _resultado(v: Votacion) -> str:
    return "aprobado" if v.aprobada else ("rechazado" if v.rechazada else (v.resultado or "sin resultado").lower())


def _modificaciones_del_senado(resultado: Resultado, fecha) -> tuple[bool, list[str]]:
    """¿El Senado aprobó con modificaciones ese día? Y, si Diputados los nombra, qué artículos."""
    dip = resultado.diputados
    modif, articulos = False, []
    if dip is not None:
        for m in dip.tramite:
            if normalizar(m.camara).startswith("SENAD") and m.fecha == fecha and "MODIFICACION" in normalizar(m.movimiento):
                modif = True
        articulos = dip.articulos_en_particular("Senado")[0] if modif else []
    b = resultado.ficha.bloque("SENADO", exacto=True)
    if b and parsear_fecha(b.valor("FECHA DE SANCION")) in (fecha, None) and \
            "MODIFICACION" in normalizar(b.valor("COMENTARIO") or ""):
        modif = True
    return modif, articulos


def _texto_aprobado(resultado: Resultado, fecha) -> Fragmento | None:
    """El texto que aprobó el Senado ese día, según los enlaces del sitio de Diputados."""
    dip = resultado.diputados
    if dip is None:
        return None
    definitiva = any(normalizar(m.camara).startswith("SENAD") and m.fecha == fecha
                     and normalizar(m.resultado) == "SANCIONADO" for m in dip.tramite)
    buscado = "SANCION SENADO" if definitiva else "MEDIA SANCION SENADO"
    for etiqueta, url in dip.textos:
        if normalizar(etiqueta) == buscado:
            return Fragmento("Texto sancionado" if definitiva else "Texto de la media sanción", url)
    return None


def sesiones_votadas(resultado: Resultado) -> list[SesionVotada]:
    """Cada sesión en que se votó el expediente, en pocas líneas (arts. 81 y 83 de la Constitución)."""
    salida = []
    for s in votaciones_mod.sesiones(resultado.votaciones):
        lineas: list[str] = []
        enlaces: list[Fragmento] = []
        for v in s.general:
            una_sola = normalizar(v.tipo) == "EN GENERAL Y EN PARTICULAR"
            lineas.append(("En general y en particular, en una sola votación: " if una_sola else "En general: ")
                          + _resultado(v) + _cuenta(v) + ".")
            if v.discrepancia:
                lineas.append(f"Atención: {v.discrepancia}.")
        modif, modificados = _modificaciones_del_senado(resultado, s.fecha)
        if s.particular or (modif and s.general):
            observaciones = []
            if s.articulos_rechazados:
                observaciones.append(("se rechazó " if len(s.articulos_rechazados) == 1 else "se rechazaron ")
                                     + votaciones_mod.describir_articulos(s.articulos_rechazados))
            for parte in s.partes_rechazadas:
                observaciones.append(f"se rechazó {parte}")
            if modificados:
                observaciones.append(("se modificó " if len(modificados) == 1 else "se modificaron ")
                                     + votaciones_mod.describir_articulos(modificados))
            elif modif:
                observaciones.append("se aprobó con modificaciones respecto del dictamen (las actas no indican qué "
                                     "artículos: ver el texto aprobado)")
            if observaciones:
                lineas.append("En particular: " + "; ".join(observaciones) + ".")
            elif s.particular:
                lineas.append("En particular: aprobado sin observaciones.")
        for v in s.insistencias:
            tercios = {True: ", con los dos tercios de los presentes", False: ", sin los dos tercios de los presentes",
                       None: ""}[v.dos_tercios]
            lineas.append(f"Insistencia (art. 83 CN): {_resultado(v)}{_cuenta(v)}{tercios}.")
        acta = s.acta
        if acta is not None and acta.url:
            enlaces.append(Fragmento("Acta", acta.url))
        texto_aprobado = _texto_aprobado(resultado, s.fecha) if modif else None
        if texto_aprobado:
            enlaces.append(texto_aprobado)
        salida.append(SesionVotada(fmt_fecha(s.fecha), lineas, enlaces))
    return salida


def texto_votaciones(resultado: Resultado) -> str:
    sesiones = sesiones_votadas(resultado)
    if not sesiones:
        return "No se encontraron votaciones del recinto sobre este expediente ni sobre sus órdenes del día."
    return f"Se votó en {cantidad(len(sesiones), 'sesión', 'sesiones', femenino=True)}."


# ============================================================== relacionados

def texto_relacionados(resultado: Resultado) -> str:
    n = len(resultado.relacionados)
    if not n:
        return ("No se encontraron expedientes tratados en conjunto ni tenidos a la vista en la orden del día, el "
                "dictamen, la ficha ni el temario de las reuniones.")
    texto = f"Se encontraron {cantidad(n, 'expediente relacionado', 'expedientes relacionados')}"
    sin = n - min(n, relacionados_mod.MAX_RELACIONADOS)
    if sin:
        texto += f"; se muestra la situación de los primeros {relacionados_mod.MAX_RELACIONADOS}"
    return texto + "."


def filas_relacionados(resultado: Resultado) -> list[tuple[Fragmento, str, str]]:
    """(expediente con enlace, relación, situación resumida)."""
    filas = []
    for r in resultado.relacionados:
        url = r.url or (r.ident.url_ficha() if r.ident.tipo else None)
        situacion = r.situacion or ("no se pudo leer la ficha" if r.error else "—")
        filas.append((Fragmento(r.ident.corto, url), r.texto_relacion(), situacion))
    return filas


# ================================================================ Diputados

def _numero_hcdn(numero: str) -> str:
    """«0065-S-2025» → «65-S-2025»."""
    partes = numero.split("-", 1)
    return f"{int(partes[0])}-{partes[1]}" if len(partes) == 2 and partes[0].isdigit() else numero


def titulo_etapa_diputados(resultado: Resultado) -> str:
    """«Etapa en la Cámara de Diputados (revisión)» si el proyecto viene del Senado; «(origen)» si viene de allí."""
    if resultado.ficha.id.origen == "CD":
        return "Etapa en la Cámara de Diputados (origen)"
    return "Etapa en la Cámara de Diputados (revisión)"


def _recortar(texto: str, largo: int = 110) -> str:
    texto = re.split(r"\s+CONJUNTAMENTE\b", texto)[0].rstrip(" -")
    return texto if len(texto) <= largo else texto[:largo].rsplit(" ", 1)[0] + "…"


def datos_diputados_hcdn(resultado: Resultado) -> list[tuple[str, Linea]]:
    """Lo que registra el sitio de Diputados sobre el paso del proyecto por esa Cámara."""
    p = resultado.diputados
    if p is None:
        return []
    origen = "Diputados" if resultado.ficha.id.origen == "CD" else "Senado"
    filas: list[tuple[str, Linea]] = []
    if p.expediente_diputados:
        filas.append(("Expediente en Diputados", [Fragmento(_numero_hcdn(p.expediente_diputados),
                                                            config.url_hcdn(p.expediente_diputados))]))
    elif any(normalizar(m.movimiento).startswith("PASA A DIPUTADOS") for m in p.tramite):
        filas.append(("Expediente en Diputados", [Fragmento("pasó a Diputados; todavía sin número propio", p.url)]))
    else:
        return []
    estado = p.estado("Diputados", origen)
    if estado is not None:
        filas.append(("Estado en Diputados", [Fragmento(estado.texto[0].upper() + estado.texto[1:] + ".")]))
    if p.giros_diputados:
        filas.append(("Giro en Diputados", [Fragmento(comisiones_texto([titulo_es(g) for g in p.giros_diputados]))]))
    for d in p.dictamenes_de("Diputados"):
        que = hcdn_mod.mayoria(d.texto)
        filas.append(("Dictamen en Diputados", [Fragmento(
            f"Orden del Día N° {hcdn_mod._od(d.orden_del_dia)}" + (f" ({fmt_fecha(d.fecha)})" if d.fecha else "")
            + (f": {que}" if que else ""))]))
    for m in p.sanciones() + p.rechazos():
        if normalizar(m.camara).startswith("DIPUT"):
            if normalizar(m.resultado) == "RECHAZADO":
                texto = f"Rechazado el {fmt_fecha(m.fecha)}"
            elif normalizar(m.resultado) == "SANCIONADO":
                texto = f"Sanción definitiva el {fmt_fecha(m.fecha)}"
            elif origen == "Diputados":
                texto = f"Media sanción el {fmt_fecha(m.fecha)}"
            elif estado is not None and estado.clave == "modificado":
                texto = f"Aprobado con modificaciones el {fmt_fecha(m.fecha)}: vuelve al Senado"
            else:
                texto = f"Aprobado el {fmt_fecha(m.fecha)}"
            filas.append(("Votación en Diputados", [Fragmento(texto)]))
    modificados, rechazados = p.articulos_en_particular("Diputados")
    observaciones = []
    if modificados:
        observaciones.append("modificó " + votaciones_mod.describir_articulos(modificados))
    if rechazados:
        observaciones.append("rechazó " + votaciones_mod.describir_articulos(rechazados))
    if observaciones:
        filas.append(("En particular", [Fragmento("; ".join(observaciones).capitalize() + ".")]))
    ultimo = next((m for m in reversed(p.tramite) if normalizar(m.camara).startswith("DIPUT")), None)
    if ultimo:
        filas.append(("Último movimiento en Diputados", [Fragmento(
            _recortar(ultimo.movimiento).capitalize() + (f" ({fmt_fecha(ultimo.fecha)})" if ultimo.fecha else ""))]))
    filas.append(("Fuente", [Fragmento("sitio de la Cámara de Diputados", p.url)]))
    return filas


def texto_resumen(resultado: Resultado) -> str:
    """Resumen en texto plano (vista previa y «Copiar resumen»)."""
    f, s = resultado.ficha, resultado.situacion
    lineas = [f"Orden del Día N° {resultado.od}: " + "".join(x.texto for x in integrantes_od(resultado)),
              texto_od(resultado), ""] if resultado.od else []
    lineas += [
        f"Expediente {f.id.corto} ({f.id.tipo})",
        descripcion(f),
        f.extracto,
        "",
        f"Situación: {s.titulo}",
    ]
    lineas += [f"  {d}" for d in s.detalle]
    lineas += [f"  {d}" for d in s.contraste]
    if s.caducidad:
        etiqueta = "Caducidad registrada" if s.caducidad.registrada else "Caducidad estimada"
        lineas.append(f"  {etiqueta}: {fmt_fecha(s.caducidad.fecha)}")
    lineas += ["", "Datos del expediente"]
    for etiqueta, linea in datos_generales(f):
        lineas.append(f"  {etiqueta}: " + "".join(fr.texto for fr in linea))
    dip = datos_diputados(f) + datos_diputados_hcdn(resultado)
    if dip:
        lineas += ["", titulo_etapa_diputados(resultado)]
        lineas += [f"  {etiqueta}: " + "".join(fr.texto for fr in linea) for etiqueta, linea in dip]
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
    if resultado.relacionados:
        lineas += ["", "Expedientes relacionados"]
        lineas += [f"  {e.texto}: {rel} — {sit}" for e, rel, sit in filas_relacionados(resultado)]
    sesiones = sesiones_votadas(resultado)
    if sesiones:
        lineas += ["", "Votaciones en el recinto"]
        for sv in sesiones:
            lineas.append(f"  Sesión del {sv.fecha}")
            lineas += [f"    {x}" for x in sv.lineas]
            lineas += [f"    {e.texto}: {e.url}" for e in sv.enlaces]
    if f.ordenes_del_dia:
        lineas += ["", "Órdenes del Día del Senado"]
        for od in f.ordenes_del_dia:
            lineas.append(f"  N° {od.numero} ({fmt_fecha(od.fecha)}): {od.estado}")
    lineas += ["", f"Fuente: {f.url}"]
    return "\n".join(lineas)
