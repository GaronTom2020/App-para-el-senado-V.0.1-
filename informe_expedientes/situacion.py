"""Situación del expediente en el trámite parlamentario.

Se deduce de los datos de la ficha, en este orden de prioridad:
sanción como ley → aprobación o rechazo del Senado → votación en el recinto que
la ficha todavía no registra → caducidad o archivo → en comisión → con dictamen → otros.

La caducidad es una estimación orientativa:
- Proyectos de ley (Ley 13.640, texto según Ley 23.821): caducan si no obtienen
  sanción en una de las cámaras durante el año parlamentario de ingreso o el
  siguiente. Con sanción de una cámara la vigencia es de tres años
  parlamentarios. Exceptúa códigos y tratados internacionales (art. 2).
- Proyectos de declaración, resolución, comunicación y decreto (Resolución del
  H. Senado del 13/06/1991): caducan si no obtienen sanción durante el año
  parlamentario en que se dio cuenta o el siguiente.
Si la ficha del Senado registra la caducidad, se usa ese dato.
"""

from __future__ import annotations

import re
from datetime import date

from . import config
from .modelos import Caducidad, Ficha, Paso, Situacion, Votacion
from .util import (
    anio_parlamentario, fin_anio_parlamentario, fmt_fecha, fmt_numero_ley, nombre_comision,
    normalizar, parsear_fecha,
)

NIVELES_FINALES = {"sancionado", "vetado", "aprobado", "rechazado", "caducado", "archivado"}


def _lista(nombres: list[str]) -> str:
    if len(nombres) <= 1:
        return "".join(nombres)
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _descripcion_mocion(para: str | None) -> str:
    n = normalizar(para or "")
    if n.startswith("C/") or "CON DESPACHO" in n:
        return "con despacho de comisión"
    if n.startswith("S/") or "SIN DESPACHO" in n:
        return "sin despacho de comisión"
    return para or ""


def votacion_sin_registrar(ficha: Ficha, votaciones: list[Votacion] | None) -> Votacion | None:
    """Última votación en general del recinto que la ficha todavía no refleja."""
    generales = [v for v in votaciones or [] if v.en_general and (v.aprobada or v.rechazada) and v.fecha]
    if not generales:
        return None
    ultima = max(generales, key=lambda v: (v.fecha, v.id))
    registradas = []
    for titulo in ("SENADO", "SANCION DE LEY"):
        b = ficha.bloque(titulo, exacto=True) if titulo == "SENADO" else ficha.bloque(titulo)
        if b and (b.valor("SANCION") or b.valor("NUMERO DE LEY")):
            registradas.append(parsear_fecha(b.valor("FECHA DE SANCION")) or date.min)
    if any(f >= ultima.fecha for f in registradas):
        return None
    return ultima


def _resultado_votacion(v: Votacion) -> str:
    if v.con_totales:
        return f" ({v.afirmativos} a {v.negativos})"
    return ""


def calcular(ficha: Ficha, hoy: date | None = None, votaciones: list[Votacion] | None = None) -> Situacion:
    hoy = hoy or date.today()
    tipo, origen = ficha.id.tipo, ficha.id.origen

    b_senado = ficha.bloque("SENADO", exacto=True)
    b_ley = ficha.bloque("SANCION DE LEY")
    b_pe = ficha.bloque("PODER EJECUTIVO")
    b_dip = next((b for b in ficha.resoluciones if "DIPUTADOS" in normalizar(b.titulo)), None)

    numero_ley = b_ley.valor("NUMERO DE LEY") if b_ley else None
    fecha_ley = parsear_fecha(b_ley.valor("FECHA DE SANCION")) if b_ley else None
    sancion = normalizar(b_senado.valor("SANCION") or "") if b_senado else ""
    fecha_senado = parsear_fecha(b_senado.valor("FECHA DE SANCION")) if b_senado else None
    nota_senado = " ".join(filter(None, [
        b_senado.valor("NOTA") if b_senado else None,
        b_senado.valor("COMENTARIO") if b_senado else None,
    ]))

    abiertos = sorted((g for g in ficha.giros if g.abierto), key=lambda g: (g.orden or 99))
    ods_vigentes = [od for od in ficha.ordenes_del_dia if od.situacion == "vigente"]
    ods_aprobadas = [od for od in ficha.ordenes_del_dia if od.situacion == "aprobada"]
    ods_caducas = [od for od in ficha.ordenes_del_dia if od.situacion == "caduca"]

    detalle: list[str] = []
    votada = None if (numero_ley or "APROB" in sancion or "RECHAZ" in sancion) else         votacion_sin_registrar(ficha, votaciones)

    if numero_ley:
        titulo = f"Sancionado: Ley N° {fmt_numero_ley(numero_ley)}"
        nivel = "sancionado"
        if fecha_ley:
            detalle.append(f"Sanción definitiva el {fmt_fecha(fecha_ley)}.")
        if b_pe:
            resolucion = b_pe.valor("RESOLUCION") or ""
            decreto = b_pe.valor("DECRETO NUMERO")
            fecha_dec = parsear_fecha(b_pe.valor("FECHA DEL DECRETO") or b_pe.valor("FECHA"))
            bo = b_pe.valor("BOLETIN OFICIAL NUMERO")
            fecha_bo = parsear_fecha(b_pe.valor("FECHA DEL BOLETIN OFICIAL"))
            partes = [f"Poder Ejecutivo: {resolucion or 'sin resolución cargada'}"]
            if decreto:
                partes.append(f"Decreto {decreto}" + (f" del {fmt_fecha(fecha_dec)}" if fecha_dec else ""))
            if bo:
                partes.append(f"Boletín Oficial N° {bo}" + (f" ({fmt_fecha(fecha_bo)})" if fecha_bo else ""))
            detalle.append(". ".join(partes) + ".")
            if "VETO" in normalizar(resolucion):
                nivel = "vetado"
                titulo += f" (vetada: {resolucion.lower()})"
    elif "APROB" in sancion:
        nivel = "aprobado"
        cuando = f" el {fmt_fecha(fecha_senado)}" if fecha_senado else ""
        if tipo == "PL" and origen == "CD":
            if "MODIFIC" in normalizar(nota_senado):
                titulo = "Aprobado por el Senado con modificaciones"
                detalle.append(f"El Senado, como cámara revisora, lo aprobó con modificaciones{cuando}: vuelve a Diputados.")
            else:
                titulo = "Aprobado por el Senado como cámara revisora"
                detalle.append(f"Aprobado{cuando}.")
        elif tipo == "PL":
            titulo = "Media sanción del Senado"
            detalle.append(f"Aprobado{cuando}; pasa a la Cámara de Diputados para su revisión.")
            if b_dip:
                detalle.append("Diputados: " + "; ".join(f"{k.lower()} {v}" for k, v in b_dip.campos if v) + ".")
        elif tipo in config.INSTRUMENTO:
            titulo = f"Aprobado por el Senado ({config.INSTRUMENTO[tipo]})"
            detalle.append(f"Aprobado{cuando}.")
        else:
            titulo = "Aprobado por el Senado"
            detalle.append(f"Aprobado{cuando}.")
        if nota_senado.strip():
            detalle.append(f"Nota de la ficha: {nota_senado.strip()}.")
    elif "RECHAZ" in sancion:
        nivel = "rechazado"
        titulo = "Rechazado por el Senado"
        if fecha_senado:
            detalle.append(f"Rechazado el {fmt_fecha(fecha_senado)}.")
    elif votada and votada.aprobada:
        nivel = "aprobado"
        fecha_senado, sancion = votada.fecha, "APROBO"
        if tipo == "PL" and origen != "CD":
            titulo = "Media sanción del Senado (votada en el recinto)"
        elif tipo == "PL":
            titulo = "Aprobado por el Senado como cámara revisora (votado en el recinto)"
        else:
            titulo = "Aprobado en el recinto"
        detalle.append(f"Votado en el recinto el {fmt_fecha(votada.fecha)}{_resultado_votacion(votada)}; "
                       "la ficha oficial todavía no registra la sanción.")
        if tipo == "PL" and origen != "CD":
            detalle.append("Pasa a la Cámara de Diputados para su revisión.")
    elif votada and votada.rechazada:
        nivel = "rechazado"
        fecha_senado, sancion = votada.fecha, "RECHAZO"
        titulo = "Rechazado en el recinto"
        detalle.append(f"Votado en el recinto el {fmt_fecha(votada.fecha)}{_resultado_votacion(votada)}, con "
                       "resultado negativo; la ficha oficial todavía no registra el rechazo.")
    elif ficha.fecha_caducidad_registrada:
        nivel = "caducado"
        titulo = f"Caducó el {fmt_fecha(ficha.fecha_caducidad_registrada)}"
    elif ficha.fecha_archivo:
        nivel = "archivado"
        titulo = f"Enviado al archivo el {fmt_fecha(ficha.fecha_archivo)}"
    elif abiertos:
        nivel = "en_comision"
        nombres = [nombre_comision(g.comision) for g in abiertos]
        nombres = list(dict.fromkeys(nombres))
        titulo = f"En comisión: {_lista(nombres)}"
        desde = max(g.ingreso for g in abiertos)
        detalle.append(f"Ingresó a comisión el {fmt_fecha(desde)}.")
        if len(nombres) > 1:
            detalle.append(f"Comisión cabecera: {nombres[0]}.")
        if ods_caducas and not ods_vigentes:
            od = ods_caducas[-1]
            detalle.append(
                f"Tuvo dictamen (Orden del Día N° {od.numero}), que caducó por la renovación bienal "
                "del cuerpo; el expediente volvió a comisión."
            )
        if ods_vigentes:
            detalle.append(f"Tiene la Orden del Día N° {ods_vigentes[-1].numero} sin tratar.")
    elif ods_vigentes:
        nivel = "con_dictamen"
        od = ods_vigentes[-1]
        titulo = f"Con dictamen de comisión: Orden del Día N° {od.numero}"
        detalle.append(
            (f"Dictamen publicado el {fmt_fecha(od.fecha)}; " if od.fecha else "")
            + "pendiente de tratamiento en el recinto."
        )
    elif ods_aprobadas:
        nivel = "en_tramite"
        titulo = f"Orden del Día N° {ods_aprobadas[-1].numero} aprobada"
        detalle.append("La ficha no registra todavía la sanción correspondiente.")
    elif ficha.giros:
        nivel = "en_tramite"
        titulo = "Giros a comisión cumplidos, sin dictamen publicado"
    elif ficha.fecha_mesa_entradas:
        nivel = "en_tramite"
        titulo = "Ingresado, sin giro a comisión registrado"
    else:
        nivel = "desconocido"
        titulo = "No se pudo determinar la situación con los datos de la ficha"

    if ficha.fecha_archivo and nivel != "archivado":
        detalle.append(f"Enviado al archivo el {fmt_fecha(ficha.fecha_archivo)}.")
    if ficha.mocion_preferencia:
        texto = f"Moción de preferencia del {fmt_fecha(ficha.mocion_preferencia)}"
        descripcion = _descripcion_mocion(ficha.mocion_para)
        detalle.append(texto + (f", {descripcion}." if descripcion else "."))

    situacion = Situacion(titulo=titulo, nivel=nivel, detalle=detalle)
    situacion.pasos = _pasos(ficha, situacion, numero_ley, fecha_ley, fecha_senado, sancion, b_pe, b_dip,
                             votada is not None)
    situacion.caducidad = estimar_caducidad(ficha, situacion, hoy, fecha_senado, nota_senado)
    return situacion


# ======================================================================= pasos

def _pasos(ficha, situacion, numero_ley, fecha_ley, fecha_senado, sancion, b_pe, b_dip,
           por_votacion: bool = False) -> list[Paso]:
    tipo, origen = ficha.id.tipo, ficha.id.origen
    pasos: list[Paso] = []
    etapa = ficha.etapa_diputados

    if origen == "CD":
        pasos.append(Paso(
            "Sanción de Diputados",
            "hecho" if (etapa and (etapa.fecha_sancion or etapa.expedientes)) else "pendiente",
            etapa.fecha_sancion if etapa else None,
            f"OD {etapa.orden_del_dia}" if etapa and etapa.orden_del_dia else "",
        ))
    pasos.append(Paso(
        "Ingreso al Senado",
        "hecho" if ficha.fecha_mesa_entradas else "pendiente",
        ficha.fecha_mesa_entradas,
        f"DAE {ficha.dae}" if ficha.dae else "",
    ))
    abiertos = [g for g in ficha.giros if g.abierto]
    referencia = abiertos or ficha.giros
    ingresos = [g.ingreso for g in referencia if g.ingreso]
    comisiones = list(dict.fromkeys(nombre_comision(g.comision) for g in referencia))
    pasos.append(Paso(
        "Comisión",
        "hecho" if ficha.giros else "pendiente",
        (max(ingresos) if abiertos else min(ingresos)) if ingresos else None,
        _lista(comisiones),
    ))
    ods_validas = [od for od in ficha.ordenes_del_dia if od.situacion in ("vigente", "aprobada")]
    if tipo in ("PL", "PD", "PR", "PC", "DE") or ficha.ordenes_del_dia:
        od = ods_validas[-1] if ods_validas else None
        pasos.append(Paso(
            "Dictamen",
            "hecho" if od else "pendiente",
            od.fecha if od else None,
            f"OD {od.numero}" if od else "",
        ))
    senado_hecho = bool(sancion) or bool(numero_ley and origen == "CD")
    pasos.append(Paso(
        "Sanción del Senado",
        "hecho" if senado_hecho else "pendiente",
        fecha_senado,
        ("aprobado" if "APROB" in sancion else ("rechazado" if "RECHAZ" in sancion else ""))
        + (" en el recinto; sin registro en la ficha" if por_votacion else ""),
    ))
    if tipo == "PL":
        if origen != "CD":
            pasos.append(Paso(
                "Cámara de Diputados",
                "hecho" if (numero_ley or b_dip) else "pendiente",
                fecha_ley if numero_ley else None,
                "sancionó" if numero_ley else "",
            ))
        detalle_ley = f"Ley {fmt_numero_ley(numero_ley)}" if numero_ley else ""
        if b_pe and b_pe.valor("RESOLUCION"):
            detalle_ley += f"; {b_pe.valor('RESOLUCION').lower()}"
        pasos.append(Paso(
            "Ley y Poder Ejecutivo",
            "hecho" if numero_ley else "pendiente",
            fecha_ley,
            detalle_ley,
        ))

    # Marca dónde está (o dónde se detuvo) el expediente.
    if situacion.nivel in ("caducado", "archivado", "rechazado"):
        for p in pasos:
            if p.estado == "pendiente":
                p.estado = "detenido"
                break
    elif situacion.nivel not in NIVELES_FINALES:
        for p in pasos:
            if p.estado == "pendiente":
                p.estado = "actual"
                break
    if situacion.nivel == "en_comision":
        # Volvió a comisión: el dictamen anterior ya no cuenta.
        for p in pasos:
            if p.nombre == "Comisión":
                p.estado = "actual"
            elif p.nombre != "Ingreso al Senado" and p.nombre != "Sanción de Diputados" and p.estado == "actual":
                p.estado = "pendiente"
    if situacion.nivel == "aprobado" and tipo == "PL" and origen != "CD":
        for p in pasos:
            if p.nombre == "Cámara de Diputados" and p.estado == "pendiente":
                p.estado = "actual"
    if situacion.nivel == "vetado":
        pasos[-1].estado = "detenido"
    return pasos


# ================================================================== caducidad

_EXCEPCIONES = re.compile(r"\bCODIGO\b|\bTRATADO\b|\bCONVENIO\b|\bACUERDO\s+(?:CON|ENTRE|SOBRE|DE)\b|\bCONVENCION\b|\bPROTOCOLO\b")


def estimar_caducidad(ficha: Ficha, situacion: Situacion, hoy: date, fecha_senado, nota_senado: str) -> Caducidad | None:
    if ficha.fecha_caducidad_registrada:
        return Caducidad(ficha.fecha_caducidad_registrada, "Registrada en la ficha del Senado.",
                         ficha.fecha_caducidad_registrada <= hoy, True)
    if situacion.nivel in ("sancionado", "vetado", "rechazado", "archivado", "caducado"):
        return None

    tipo, origen = ficha.id.tipo, ficha.id.origen
    fecha = None
    fundamento = ""

    if tipo == "PL":
        if situacion.nivel == "aprobado":
            if origen == "CD" and "MODIFIC" in normalizar(nota_senado) and fecha_senado:
                anio = anio_parlamentario(fecha_senado)
                fecha = fin_anio_parlamentario(anio + 1)
                fundamento = ("Ley 13.640, art. 1, 2° párrafo: aprobado con modificaciones por la cámara revisora; "
                              f"debe terminar el trámite en el año parlamentario {anio} o el siguiente.")
            elif origen != "CD" and ficha.fecha_mesa_entradas:
                anio = anio_parlamentario(ficha.fecha_mesa_entradas)
                fecha = fin_anio_parlamentario(anio + 2)
                fundamento = ("Ley 13.640: con media sanción, vigencia de tres años parlamentarios desde el ingreso "
                              f"(año parlamentario {anio}); el plazo corre ahora en la Cámara de Diputados.")
            else:
                return None
        elif origen == "CD":
            if not (ficha.etapa_diputados and ficha.etapa_diputados.expedientes):
                return None
            anios = [int(e.rsplit("-", 1)[-1]) for e in ficha.etapa_diputados.expedientes]
            anio = max(anios)
            ultimo = next(e for e in ficha.etapa_diputados.expedientes if e.endswith(str(anio)))
            fecha = fin_anio_parlamentario(anio + 2)
            fundamento = ("Ley 13.640: proyecto con sanción de Diputados, vigencia de tres años parlamentarios "
                          f"contados desde el expediente {ultimo}.")
        elif ficha.fecha_mesa_entradas:
            anio = anio_parlamentario(ficha.fecha_mesa_entradas)
            fecha = fin_anio_parlamentario(anio + 1)
            fundamento = ("Ley 13.640 (texto según Ley 23.821): caduca si no obtiene sanción en una de las cámaras "
                          f"durante el año parlamentario de ingreso ({anio}) o el siguiente.")
        if fecha and _EXCEPCIONES.search(normalizar(ficha.extracto)):
            fundamento += (" Atención: podría estar exceptuado por el art. 2 de la Ley 13.640 "
                           "(códigos o tratados internacionales).")
    elif tipo in config.INSTRUMENTO:
        base = ficha.fecha_dado_cuenta or ficha.fecha_mesa_entradas
        if base:
            anio = anio_parlamentario(base)
            fecha = fin_anio_parlamentario(anio + 1)
            fundamento = ("Resolución del H. Senado del 13/06/1991: caduca si no obtiene sanción durante el año "
                          f"parlamentario en que se dio cuenta ({anio}) o el siguiente.")
    if not fecha:
        return None
    return Caducidad(fecha, fundamento, fecha < hoy, False)
