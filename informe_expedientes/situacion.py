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

from . import config, tramite
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


def calcular(ficha: Ficha, hoy: date | None = None, votaciones: list[Votacion] | None = None,
             diputados=None) -> Situacion:
    """`diputados` es el proyecto en hcdn.gob.ar (hcdn.ProyectoHCDN), si se consultó."""
    hoy = hoy or date.today()
    tipo, origen = ficha.id.tipo, ficha.id.origen

    b_senado = ficha.bloque("SENADO", exacto=True)
    b_ley = ficha.bloque("SANCION DE LEY")
    b_pe = ficha.bloque("PODER EJECUTIVO")

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
    votada = None
    if not (numero_ley or "APROB" in sancion or "RECHAZ" in sancion):
        votada = votacion_sin_registrar(ficha, votaciones)
    r = tramite.armar(ficha, diputados, votada) if tipo == "PL" else None
    if r is not None and r.revision is not None and r.revision.camara == tramite.SENADO and not r.revision.votacion:
        r.revision.votacion = next((v for v in votaciones or [] if v.en_general and v.fecha == r.revision.fecha), None)
    segun_diputados = None
    if r is not None and not votada:
        paso_senado = r.aprobacion_origen if r.origen == tramite.SENADO else r.revision
        if paso_senado is not None and paso_senado.fuente == "diputados":
            segun_diputados = paso_senado

    if numero_ley or (r is not None and r.sancion and r.sancion.fuente == "diputados"):
        numero = numero_ley or (r.numero_ley if r else None)
        titulo = f"Sancionado: Ley N° {fmt_numero_ley(numero)}" if numero else "Sancionado por el Congreso"
        nivel = "sancionado"
        if numero_ley and fecha_ley:
            detalle.append(f"Sanción definitiva el {fmt_fecha(fecha_ley)}.")
        elif not numero_ley:
            fecha_ley = r.sancion.fecha
            detalle.append(f"Sanción definitiva el {fmt_fecha(fecha_ley)}, según el sitio de Diputados; la ficha del "
                           "Senado todavía no la registra.")
        resolucion = (b_pe.valor("RESOLUCION") if b_pe else None) or (r.pe if r else None) or ""
        if b_pe:
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
            if r is not None and r.insistencia == "lograda":
                nivel = "sancionado"
                titulo = titulo.replace("(vetada:", "(insistencia ante el veto:")
    elif "APROB" in sancion and r is not None and r.rechazo and r.rechazo.camara == r.revisora:
        nivel = "rechazado"
        titulo = f"Rechazado por {'la Cámara de Diputados' if r.revisora == tramite.DIPUTADOS else 'el Senado'}"
        if fecha_senado:
            detalle.append(f"El Senado lo había aprobado el {fmt_fecha(fecha_senado)}.")
    elif "APROB" in sancion:
        nivel = "aprobado"
        cuando = f" el {fmt_fecha(fecha_senado)}" if fecha_senado else ""
        if tipo == "PL" and origen == "CD":
            if "MODIFIC" in normalizar(nota_senado):
                titulo = "Aprobado por el Senado con modificaciones: vuelve a Diputados"
            else:
                titulo = "Aprobado por el Senado como cámara revisora"
            detalle.append(f"Aprobado{cuando}.")
        elif tipo == "PL":
            if r is not None and r.revision_modifico and not r.vuelta:
                titulo = "Con modificaciones de Diputados: vuelve al Senado"
            elif r is not None and r.revision:
                titulo = "Aprobado por las dos cámaras"
            else:
                titulo = "Media sanción del Senado"
            modif = " con modificaciones al dictamen" if r is not None and r.aprobacion_origen and \
                r.aprobacion_origen.con_modificaciones else ""
            detalle.append(f"Aprobado por el Senado{cuando}{modif}.")
        elif tipo in config.INSTRUMENTO:
            titulo = f"Aprobado por el Senado ({config.INSTRUMENTO[tipo]})"
            detalle.append(f"Aprobado{cuando}.")
        else:
            titulo = "Aprobado por el Senado"
            detalle.append(f"Aprobado{cuando}.")
        if nota_senado.strip():
            detalle.append(f"Nota de la ficha: {nota_senado.strip().rstrip('.')}.")
    elif "RECHAZ" in sancion:
        nivel = "rechazado"
        titulo = "Rechazado por el Senado"
        if fecha_senado and tipo != "PL":
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
    elif segun_diputados is not None:
        nivel = "aprobado"
        fecha_senado, sancion = segun_diputados.fecha, "APROBO"
        titulo = ("Media sanción del Senado (según Diputados)" if origen != "CD"
                  else "Aprobado por el Senado como cámara revisora (según Diputados)")
        detalle.append(f"Aprobado por el Senado el {fmt_fecha(segun_diputados.fecha)}, según el sitio de Diputados; "
                       "la ficha oficial todavía no registra la sanción.")
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

    if r is not None and nivel not in ("caducado", "archivado"):
        detalle += tramite.lineas(r, hoy)
    if ficha.fecha_archivo and nivel != "archivado":
        detalle.append(f"Enviado al archivo el {fmt_fecha(ficha.fecha_archivo)}.")
    if ficha.mocion_preferencia:
        texto = f"Moción de preferencia del {fmt_fecha(ficha.mocion_preferencia)}"
        descripcion = _descripcion_mocion(ficha.mocion_para)
        detalle.append(texto + (f", {descripcion}." if descripcion else "."))

    situacion = Situacion(titulo=titulo, nivel=nivel, detalle=detalle, contraste=list(r.contraste) if r else [])
    situacion.pasos = _pasos(ficha, situacion, r, numero_ley, fecha_ley, fecha_senado, sancion, b_pe,
                             votada is not None)
    situacion.caducidad = estimar_caducidad(ficha, situacion, hoy, fecha_senado, nota_senado)
    return situacion


# ======================================================================= pasos

def _detalle_paso(paso, base: str) -> str:
    partes = [base] if base else []
    if paso is not None and paso.con_modificaciones and "modific" not in base:
        partes.append("con modificaciones")
    if paso is not None and paso.fuente == "votación":
        partes.append("en el recinto; sin registro en la ficha")
    elif paso is not None and paso.fuente == "diputados":
        partes.append("según Diputados")
    return ", ".join(partes)


def _pasos_congreso(r, numero_ley, fecha_ley, b_pe) -> list[Paso]:
    """Sanción en cada cámara, vuelta a la de origen, Poder Ejecutivo e insistencia (arts. 78 a 83 CN)."""
    pasos: list[Paso] = []
    if r.origen == tramite.SENADO:
        senado, diputados = r.aprobacion_origen, r.revision
    else:
        senado, diputados = r.revision, None
    rechazo_senado = r.rechazo if r.rechazo and r.rechazo.camara == tramite.SENADO else None
    pasos.append(Paso(
        "Sanción del Senado",
        "hecho" if senado else "pendiente",
        senado.fecha if senado else (rechazo_senado.fecha if rechazo_senado else None),
        _detalle_paso(senado, "aprobado") if senado else ("rechazado" if rechazo_senado else ""),
    ))
    if r.origen == tramite.SENADO:
        definitiva = r.sancion is not None and r.sancion.camara == tramite.DIPUTADOS
        rechazo = r.rechazo if r.rechazo and r.rechazo.camara == tramite.DIPUTADOS else None
        estado = r.estado_revisora
        if diputados:
            paso = Paso("Cámara de Diputados", "hecho", diputados.fecha,
                        _detalle_paso(diputados, "con modificaciones" if r.revision_modifico else
                                      ("sancionó" if definitiva else "aprobó")))
        elif rechazo:
            paso = Paso("Cámara de Diputados", "detenido", rechazo.fecha, "rechazó")
        else:
            detalle = ""
            if estado is not None and estado.clave == "con_dictamen":
                detalle = estado.texto.replace("con dictamen de comisión: Orden del Día N°", "dictamen, OD")
                detalle = detalle.split(" (")[0]
            elif estado is not None and estado.clave in ("en_comision", "ingresado"):
                detalle = "en comisión" if estado.clave == "en_comision" else "ingresó"
            paso = Paso("Cámara de Diputados", "pendiente", estado.fecha if estado else None, detalle)
        pasos.append(paso)
    if r.revision_modifico:
        pasos.append(Paso(
            "Vuelve al Senado" if r.origen == tramite.SENADO else "Vuelve a Diputados",
            "hecho" if r.vuelta else "pendiente",
            r.vuelta.fecha if r.vuelta else None,
            ("insistió en su texto" if r.vuelta_insistio else "aceptó las modificaciones") if r.vuelta else "art. 81 CN",
        ))
    ley = numero_ley or r.numero_ley
    detalle_ley = f"Ley {fmt_numero_ley(ley)}" if ley else ""
    resolucion = (b_pe.valor("RESOLUCION") if b_pe else None) or r.pe
    if resolucion:
        detalle_ley += ("; " if detalle_ley else "") + resolucion.lower()
    pasos.append(Paso(
        "Ley y Poder Ejecutivo",
        "hecho" if (ley or r.sancion) else "pendiente",
        fecha_ley or (r.sancion.fecha if r.sancion else None),
        detalle_ley,
    ))
    if r.veto:
        if r.insistencia is None:
            pasos[-1].estado = "detenido"
        pasos.append(Paso(
            "Insistencia",
            {"lograda": "hecho", "rechazada": "detenido"}.get(r.insistencia or "", "pendiente"),
            r.insistencia_fecha,
            {"lograda": "dos tercios en ambas cámaras", "rechazada": "sin los dos tercios"}.get(
                r.insistencia or "", "art. 83 CN"),
        ))
    return pasos


def _pasos(ficha, situacion, r, numero_ley, fecha_ley, fecha_senado, sancion, b_pe,
           por_votacion: bool = False) -> list[Paso]:
    tipo, origen = ficha.id.tipo, ficha.id.origen
    pasos: list[Paso] = []
    etapa = ficha.etapa_diputados

    if origen == "CD":
        hecha = (r.aprobacion_origen is not None) if r is not None else bool(
            etapa and (etapa.fecha_sancion or etapa.expedientes))
        pasos.append(Paso(
            "Sanción de Diputados",
            "hecho" if hecha else "pendiente",
            (r.aprobacion_origen.fecha if r is not None and r.aprobacion_origen else None)
            or (etapa.fecha_sancion if etapa else None),
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
    if r is not None:
        pasos += _pasos_congreso(r, numero_ley, fecha_ley, b_pe)
    else:
        pasos.append(Paso(
            "Sanción del Senado",
            "hecho" if sancion else "pendiente",
            fecha_senado,
            ("aprobado" if "APROB" in sancion else ("rechazado" if "RECHAZ" in sancion else ""))
            + (" en el recinto; sin registro en la ficha" if por_votacion else ""),
        ))

    # Comisión y dictamen no se hicieron si se trató sobre tablas: no son donde se detuvo.
    hechos = [i for i, p in enumerate(pasos) if p.estado == "hecho"]
    for i, p in enumerate(pasos):
        if p.nombre in ("Comisión", "Dictamen") and p.estado == "pendiente" and hechos and i < hechos[-1]:
            p.estado, p.detalle = "hecho", ("sin dictamen" if p.nombre == "Dictamen" else "sin giro")

    # Marca dónde está (o dónde se detuvo) el expediente.
    if situacion.nivel in ("caducado", "archivado", "rechazado") and not any(p.estado == "detenido" for p in pasos):
        for p in pasos:
            if p.estado == "pendiente":
                p.estado = "detenido"
                break
    elif situacion.nivel not in NIVELES_FINALES or (situacion.nivel == "aprobado" and tipo == "PL"):
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
