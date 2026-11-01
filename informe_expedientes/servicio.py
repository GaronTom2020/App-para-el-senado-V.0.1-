"""Arma el informe completo de un expediente.

`generar()` es lo único que usan la interfaz gráfica y la línea de comandos.
El progreso se informa con `avisar(evento, mensaje="", **datos)`:
    etapa        texto corto de lo que se está haciendo
    log          detalle para el registro
    advertencia  algo no se pudo leer, pero el informe sigue
    progreso     actual=…, total=…
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import comisiones, config, ficha as ficha_mod, hcdn, orden_dia, relacionados as relacionados_mod
from . import situacion as situacion_mod, votaciones as votaciones_mod
from .cliente import Cancelado, Cliente, ErrorRed
from .identificador import parsear
from .modelos import BusquedaReuniones, Resultado
from .util import nombre_archivo_seguro


@dataclass
class Opciones:
    tipo: str | None = None
    buscar_reuniones: bool = True
    incluir_asesores: bool = True
    buscar_agenda: bool = True
    completar_ordenes_del_dia: bool = True
    buscar_votaciones: bool = True
    contrastar_diputados: bool = True     # proyectos de ley: se confronta con hcdn.gob.ar
    buscar_relacionados: bool = True      # tratados en conjunto y tenidos a la vista
    formatos: tuple[str, ...] = ("docx", "html")
    carpeta_salida: Path = field(default_factory=config.carpeta_informes_por_defecto)
    notas_usuario: str = ""
    max_hilos: int = config.HILOS_POR_DEFECTO
    nombre_archivo: str | None = None       # sin fecha, p. ej. «index» para publicar


def _nada(*_args, **_kwargs):
    return None


def generar(texto: str, opciones: Opciones, cliente: Cliente, avisar=_nada, hoy: date | None = None,
            escribir: bool = True) -> Resultado:
    hoy = hoy or date.today()
    advertencias: list[str] = []

    def avisar_y_guardar(evento, mensaje="", **datos):
        if evento == "advertencia" and mensaje:
            advertencias.append(mensaje)
        avisar(evento, mensaje, **datos)

    # Por orden del día: sus expedientes forman un único despacho y la cabecera lleva la ficha.
    od = orden_dia.parsear_od(texto)
    od_expedientes = []
    if od:
        avisar("etapa", f"Leyendo la Orden del Día N° {od}…")
        od_expedientes = orden_dia.expedientes(cliente, od)
        avisar("log", f"OD {od}: {', '.join(x.corto for x in od_expedientes)}.")
        ident = od_expedientes[0]
    else:
        ident = parsear(texto, opciones.tipo)
    avisar("etapa", f"Buscando la ficha de {ident.corto}…")
    tipo = ficha_mod.resolver_tipo(cliente, ident, avisar_y_guardar)
    ident = ident.con_tipo(tipo)
    ficha = ficha_mod.descargar_ficha(cliente, ident)
    avisar("log", f"Ficha leída: {ficha.tipo_texto or tipo} · {ficha.origen_texto}.")
    for a in ficha.advertencias:
        avisar_y_guardar("advertencia", a)

    if opciones.completar_ordenes_del_dia and ficha.ordenes_del_dia:
        avisar("etapa", "Buscando los PDF de las órdenes del día…")
        ficha_mod.completar_ordenes_del_dia(cliente, ficha)

    reuniones, busqueda = [], BusquedaReuniones()
    if opciones.buscar_reuniones:
        try:
            reuniones, busqueda = comisiones.buscar_reuniones(
                cliente, ficha, opciones.incluir_asesores, opciones.max_hilos, avisar_y_guardar, hoy)
            avisar("log", f"Reuniones en que se trató: {len(reuniones)}.")
        except ErrorRed as e:
            avisar_y_guardar("advertencia", f"No se pudo completar la búsqueda de reuniones: {e}")
            busqueda = BusquedaReuniones(realizada=False, motivo=str(e))

    convocadas = []
    if opciones.buscar_agenda:
        avisar("etapa", "Revisando la agenda de las comisiones…")
        try:
            convocadas = comisiones.buscar_convocatorias(cliente, ficha, avisar_y_guardar, hoy)
        except ErrorRed as e:
            avisar_y_guardar("advertencia", f"No se pudo revisar la agenda: {e}")

    votaciones = []
    if opciones.buscar_votaciones:
        avisar("etapa", "Buscando votaciones nominales en el recinto…")
        try:
            votaciones = votaciones_mod.buscar(cliente, ficha, hoy, avisar_y_guardar)
            avisar("log", f"Votaciones nominales encontradas: {len(votaciones)}.")
        except (ErrorRed, votaciones_mod.ErrorVotaciones) as e:
            avisar_y_guardar("advertencia", f"No se pudieron revisar las votaciones del recinto: {e}")

    diputados, diputados_consultado = None, False
    if opciones.contrastar_diputados and ficha.id.tipo == "PL":
        avisar("etapa", "Contrastando con el sitio de la Cámara de Diputados…")
        try:
            diputados = hcdn.buscar(cliente, ficha.id)
            diputados_consultado = True
            avisar("log", f"Diputados: {diputados.expediente_diputados or 'sin número propio'}, "
                          f"{len(diputados.tramite)} movimientos." if diputados else
                   "Diputados: el proyecto no figura en su buscador.")
        except ErrorRed as e:
            avisar_y_guardar("advertencia", f"No se pudo consultar el sitio de Diputados: {e}")

    situacion = situacion_mod.calcular(ficha, hoy, votaciones, diputados)

    relacionados = []
    if opciones.buscar_relacionados:
        avisar("etapa", "Buscando expedientes relacionados…")
        try:
            relacionados = relacionados_mod.buscar(cliente, ficha, diputados, reuniones, avisar_y_guardar, hoy)
            avisar("log", f"Expedientes relacionados: {len(relacionados)}.")
        except ErrorRed as e:
            avisar_y_guardar("advertencia", f"No se pudieron buscar los expedientes relacionados: {e}")
    resultado = Resultado(
        ficha=ficha,
        situacion=situacion,
        reuniones=reuniones,
        convocadas=convocadas,
        busqueda=busqueda,
        agenda_consultada=opciones.buscar_agenda,
        votaciones=votaciones,
        votaciones_consultadas=opciones.buscar_votaciones,
        diputados=diputados,
        diputados_consultado=diputados_consultado,
        relacionados=relacionados,
        relacionados_consultados=opciones.buscar_relacionados,
        notas_usuario=opciones.notas_usuario.strip(),
        generado=datetime.now(),
        advertencias=advertencias,
        od=od,
        od_expedientes=od_expedientes,
    )
    if escribir:
        escribir_informes(resultado, opciones, avisar)
    return resultado


def escribir_informes(resultado: Resultado, opciones: Opciones, avisar=_nada) -> dict[str, Path]:
    from . import informe_docx, informe_html

    carpeta = Path(opciones.carpeta_salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    base = nombre_archivo_seguro(opciones.nombre_archivo or
                                 f"Informe {resultado.titulo.replace('/', '-').replace(' ', '-')} "
                                 f"({resultado.generado:%Y-%m-%d})")
    escritores = {"docx": informe_docx.escribir, "html": informe_html.escribir}
    for formato in opciones.formatos:
        if formato not in escritores:
            continue
        avisar("etapa", f"Escribiendo el informe ({formato.upper()})…")
        destino = carpeta / f"{base}.{formato}"
        try:
            escritores[formato](resultado, destino)
        except PermissionError:
            # Suele pasar si el archivo anterior está abierto en Word.
            destino = carpeta / f"{base} {resultado.generado:%H%M%S}.{formato}"
            escritores[formato](resultado, destino)
        resultado.archivos[formato] = destino
        avisar("log", f"Guardado: {destino}")
    return resultado.archivos


__all__ = ["Opciones", "generar", "escribir_informes", "Cancelado"]
