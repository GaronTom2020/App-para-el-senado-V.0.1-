"""Informe de sesión: los asuntos del plan de labor, cada uno con la ficha de sus expedientes.

`generar_sesion()` resuelve cada orden del día a sus expedientes (página de la OD),
arma la ficha de cada expediente con `servicio.generar()` sin escribir archivos y
deja el resultado listo para escribir un único informe (Word, HTML, Excel) y el CSV
para el tablero de sesiones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import config, plan_labor, taquigrafica
from .cliente import Cancelado, Cliente, ErrorRed
from .identificador import IdExpediente
from .modelos import Resultado
from .numeros import cantidad
from .servicio import Opciones, generar
from .util import fmt_fecha, nombre_archivo_seguro

MAX_EXPEDIENTES = 150


@dataclass
class OpcionesSesion:
    buscar_reuniones: bool = False          # lento: una sesión puede tener decenas de expedientes
    buscar_relacionados: bool = False       # los temas ya agrupan los expedientes tratados en conjunto
    incluir_asesores: bool = True
    buscar_taquigrafica: bool = True       # si la sesión ya se hizo: votaciones y modificaciones
    formatos: tuple[str, ...] = ("docx", "html", "xlsx", "csv")
    carpeta_salida: Path = field(default_factory=config.carpeta_informes_por_defecto)
    nombre_archivo: str | None = None


@dataclass
class Tema:
    asunto: plan_labor.Asunto
    expedientes: list[IdExpediente] = field(default_factory=list)
    resultados: list[Resultado] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    debate: taquigrafica.Debate | None = None       # su tratamiento según la versión taquigráfica

    @property
    def titulo(self) -> str:
        """El nombre del plan o, si no lo trae, el extracto del primer expediente."""
        if self.asunto.titulo:
            return self.asunto.titulo
        if self.resultados and self.resultados[0].ficha.extracto:
            return self.resultados[0].ficha.extracto
        return "Asunto sin título en el plan de labor"


@dataclass
class ResultadoSesion:
    plan: plan_labor.PlanDeLabor
    temas: list[Tema]
    generado: datetime = field(default_factory=datetime.now)
    archivos: dict[str, Path] = field(default_factory=dict)
    advertencias: list[str] = field(default_factory=list)
    taquigrafica: taquigrafica.VersionTaquigrafica | None = None

    @property
    def fecha(self) -> date | None:
        return self.plan.fecha_sesion or self.plan.fecha_reunion

    @property
    def expedientes(self) -> list[Resultado]:
        vistos, salida = set(), []
        for t in self.temas:
            for r in t.resultados:
                if r.ficha.id.corto not in vistos:
                    vistos.add(r.ficha.id.corto)
                    salida.append(r)
        return salida


def _nada(*_args, **_kwargs):
    return None


def resolver(cliente: Cliente, plan: plan_labor.PlanDeLabor, avisar=_nada) -> list[Tema]:
    """Expedientes de cada asunto: los nombrados y los de sus órdenes del día."""
    temas = []
    for asunto in plan.asuntos:
        tema = Tema(asunto)
        for ref in asunto.referencias:
            cliente.verificar_cancelacion()
            if ref.clase == "expediente":
                if all(ref.ident.corto != x.corto for x in tema.expedientes):
                    tema.expedientes.append(ref.ident)
                continue
            try:
                html = cliente.get(plan_labor.url_od(ref.od), ttl=config.TTL_ORDEN_DIA).texto
            except ErrorRed as e:
                tema.errores.append(f"No se pudo abrir la Orden del Día N° {ref.od}: {e}")
                continue
            idents = plan_labor.expedientes_de_od(html)
            if not idents:
                tema.errores.append(f"La Orden del Día N° {ref.od} no lista expedientes en el sitio.")
            for ident in idents:
                if all(ident.corto != x.corto for x in tema.expedientes):
                    tema.expedientes.append(ident)
        temas.append(tema)
    return temas


def generar_sesion(plan: plan_labor.PlanDeLabor, opciones: OpcionesSesion, cliente: Cliente, avisar=_nada,
                   hoy: date | None = None, escribir: bool = True) -> ResultadoSesion:
    hoy = hoy or date.today()
    advertencias: list[str] = []
    avisar("etapa", f"Leyendo las órdenes del día de {cantidad(len(plan.asuntos), 'asunto', 'asuntos')}…")
    temas = resolver(cliente, plan, avisar)
    for t in temas:
        advertencias += t.errores
    pendientes: list[IdExpediente] = []
    for t in temas:
        for ident in t.expedientes:
            if all(ident.corto != x.corto for x in pendientes):
                pendientes.append(ident)
    if len(pendientes) > MAX_EXPEDIENTES:
        advertencias.append(f"El plan nombra {len(pendientes)} expedientes; se consultan los primeros "
                            f"{MAX_EXPEDIENTES}.")
        pendientes = pendientes[:MAX_EXPEDIENTES]

    hechos: dict[str, Resultado] = {}
    for i, ident in enumerate(pendientes, 1):
        avisar("etapa", f"Ficha {i} de {len(pendientes)}: {ident.corto}…")
        avisar("progreso", actual=i - 1, total=len(pendientes))
        try:
            hechos[ident.corto] = generar(
                ident.corto, Opciones(tipo=ident.tipo, buscar_reuniones=opciones.buscar_reuniones,
                                      buscar_relacionados=opciones.buscar_relacionados,
                                      incluir_asesores=opciones.incluir_asesores, buscar_agenda=False,
                                      formatos=()),
                cliente, lambda ev, msg="", **d: avisar("log", msg) if ev in ("log", "advertencia") else None,
                hoy=hoy, escribir=False)
        except Cancelado:
            raise
        except Exception as e:  # noqa: BLE001 - un expediente que falla no corta el informe
            advertencias.append(f"No se pudo leer {ident.corto}: {e}")
    avisar("progreso", actual=len(pendientes), total=len(pendientes))
    for t in temas:
        t.resultados = [hechos[x.corto] for x in t.expedientes if x.corto in hechos]

    res = ResultadoSesion(plan, temas, advertencias=advertencias)
    if opciones.buscar_taquigrafica and res.fecha and res.fecha <= hoy:
        avisar("etapa", "Buscando la versión taquigráfica de la sesión…")
        error = None
        try:
            res.taquigrafica = taquigrafica.buscar(cliente, res.fecha)
        except Cancelado:
            raise
        except Exception as e:  # noqa: BLE001 - sin la versión taquigráfica el informe sigue
            error = e
        if error is not None:
            advertencias.append(f"No se pudo leer la versión taquigráfica: {error}")
        elif res.taquigrafica is None:
            advertencias.append(f"La versión taquigráfica de la sesión del {fmt_fecha(res.fecha)} todavía no está "
                                "publicada: el informe no trae las votaciones ni las modificaciones del recinto.")
        else:
            for t in temas:
                t.debate = res.taquigrafica.debate_de(t.asunto.ordenes_del_dia, t.asunto.titulo)
            avisar("log", f"Versión taquigráfica: {sum(1 for t in temas if t.debate)} asuntos ubicados.")
    if escribir:
        escribir_informes(res, opciones, avisar)
    return res


# ================================================================== textos

def resumen(res: ResultadoSesion) -> str:
    """Párrafo inicial, con las cantidades en forma normativa."""
    temas = res.temas
    con_numero = [t for t in temas if t.asunto.referencias]
    sin_numero = len(temas) - len(con_numero)
    cuando = f" para la sesión del {fmt_fecha(res.fecha)}" if res.fecha else ""
    texto = f"El plan de labor{cuando} acordó {cantidad(len(temas), 'asunto', 'asuntos')}"
    if con_numero and sin_numero:
        texto += (f": {cantidad(len(con_numero), 'con orden del día o expediente', 'con orden del día o expediente')}"
                  f" y {cantidad(sin_numero, 'sin número (jura, acuerdo o asunto sobre tablas)', 'sin número (juras, acuerdos o asuntos sobre tablas)')}")
    texto += "."
    n = len(res.expedientes)
    if n:
        texto += f" Se consultaron las fichas de {cantidad(n, 'expediente', 'expedientes')}."
    return texto


def etiqueta_referencias(tema: Tema) -> str:
    partes = [f"OD {od}" for od in tema.asunto.ordenes_del_dia]
    partes += [x.corto for x in tema.asunto.expedientes]
    return ", ".join(partes)


def comisiones(r: Resultado) -> list[str]:
    from .util import nombre_comision
    return list(dict.fromkeys(nombre_comision(g.comision) for g in r.ficha.giros))


def escribir_informes(res: ResultadoSesion, opciones: OpcionesSesion, avisar=_nada) -> dict[str, Path]:
    from . import informe_sesion

    carpeta = Path(opciones.carpeta_salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    fecha = res.fecha or res.generado.date()
    base = nombre_archivo_seguro(opciones.nombre_archivo or f"Informe de sesión ({fecha:%Y-%m-%d})")
    escritores = {"docx": informe_sesion.escribir_docx, "html": informe_sesion.escribir_html,
                  "xlsx": informe_sesion.escribir_xlsx, "csv": informe_sesion.escribir_csv}
    for formato in opciones.formatos:
        if formato not in escritores:
            continue
        avisar("etapa", f"Escribiendo el informe de sesión ({formato.upper()})…")
        destino = carpeta / f"{base}.{formato}"
        try:
            escritores[formato](res, destino)
        except PermissionError:
            destino = carpeta / f"{base} {res.generado:%H%M%S}.{formato}"
            escritores[formato](res, destino)
        res.archivos[formato] = destino
        avisar("log", f"Guardado: {destino}")
    return res.archivos


__all__ = ["OpcionesSesion", "Tema", "ResultadoSesion", "generar_sesion", "resolver", "resumen",
           "escribir_informes"]
