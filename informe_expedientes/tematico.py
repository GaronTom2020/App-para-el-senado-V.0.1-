"""Informe temático: todos los expedientes que responden a un eje o a palabras clave.

`generar_tematico()` busca los expedientes, consulta la ficha de cada uno para
saber en qué etapa está (opcionalmente también sus reuniones de comisión o su
informe completo) y escribe un informe consolidado en Word, HTML y Excel.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import busqueda, comisiones, config, ficha as ficha_mod, situacion as situacion_mod
from .busqueda import Consulta, Hallazgo
from .cliente import Cancelado, Cliente
from .modelos import Ficha, Reunion, Situacion
from .numeros import cantidad
from .util import fmt_fecha, nombre_archivo_seguro, nombre_comision

ORDEN = ["con_dictamen", "en_comision", "en_tramite", "aprobado", "sancionado", "vetado", "rechazado",
         "caducado", "archivado", "desconocido", "error", None]
ETAPA = {
    "con_dictamen": "Con dictamen", "en_comision": "En comisión", "en_tramite": "En trámite",
    "aprobado": "Aprobado por el Senado", "sancionado": "Sancionado", "vetado": "Vetado",
    "rechazado": "Rechazado", "caducado": "Caducado", "archivado": "Archivado",
    "desconocido": "Sin datos suficientes", "error": "Ficha no disponible", None: "Sin consultar la ficha",
}
_FRASE = {
    "con_dictamen": ("con dictamen", "con dictamen"), "en_comision": ("en comisión", "en comisión"),
    "en_tramite": ("en otra etapa del trámite", "en otras etapas del trámite"),
    "aprobado": ("aprobado por el Senado", "aprobados por el Senado"),
    "sancionado": ("sancionado como ley", "sancionados como ley"), "vetado": ("vetado", "vetados"),
    "rechazado": ("rechazado", "rechazados"), "caducado": ("caducado", "caducados"),
    "archivado": ("archivado", "archivados"), "desconocido": ("sin datos suficientes", "sin datos suficientes"),
    "error": ("cuya ficha no se pudo leer", "cuyas fichas no se pudieron leer"),
    None: ("sin consultar la ficha", "sin consultar la ficha"),
}
NOMBRE_TIPO_PLURAL = {"PL": ("proyecto de ley", "proyectos de ley"),
                      "PR": ("proyecto de resolución", "proyectos de resolución"),
                      "PC": ("proyecto de comunicación", "proyectos de comunicación"),
                      "PD": ("proyecto de declaración", "proyectos de declaración")}


@dataclass
class OpcionesTematicas:
    detallar: bool = True                    # consultar la ficha de cada expediente
    buscar_reuniones: bool = False           # además, sus reuniones de comisión (lento)
    incluir_asesores: bool = True
    informes_individuales: bool = False      # además, el informe completo de cada uno
    limite: int = 200                        # máximo de fichas a consultar
    formatos: tuple[str, ...] = ("docx", "html", "xlsx")
    carpeta_salida: Path = field(default_factory=config.carpeta_informes_por_defecto)
    notas_usuario: str = ""
    max_hilos: int = config.HILOS_POR_DEFECTO
    nombre_archivo: str | None = None


@dataclass
class Item:
    hallazgo: Hallazgo
    ficha: Ficha | None = None
    situacion: Situacion | None = None
    reuniones: list[Reunion] = field(default_factory=list)
    reuniones_buscadas: bool = False
    error: str = ""
    informes: dict[str, Path] = field(default_factory=dict)

    @property
    def nivel(self) -> str | None:
        if self.situacion:
            return self.situacion.nivel
        return "error" if self.error else None

    @property
    def url(self) -> str:
        ident = self.hallazgo.ident
        return self.ficha.url if self.ficha else (ident.url_ficha() if ident.tipo else config.URL_BUSCADOR)

    def comisiones(self) -> str:
        if not self.ficha or not self.ficha.giros:
            return ""
        giros = [g for g in self.ficha.giros if g.abierto] or self.ficha.giros
        nombres = list(dict.fromkeys(nombre_comision(g.comision) for g in sorted(giros, key=lambda g: g.orden or 99)))
        return ", ".join(nombres)


@dataclass
class ResultadoTematico:
    consulta: Consulta
    items: list[Item]
    generado: datetime = field(default_factory=datetime.now)
    archivos: dict[str, Path] = field(default_factory=dict)
    advertencias: list[str] = field(default_factory=list)
    estadisticas: dict = field(default_factory=dict)
    detallados: int = 0
    limite_aplicado: bool = False
    busco_reuniones: bool = False
    notas_usuario: str = ""

    def conteo_etapas(self) -> list[tuple[str | None, int]]:
        cuenta: dict = {}
        for it in self.items:
            cuenta[it.nivel] = cuenta.get(it.nivel, 0) + 1
        return [(n, cuenta[n]) for n in ORDEN if cuenta.get(n)]

    def conteo(self, clave) -> list[tuple[str, int]]:
        cuenta: dict = {}
        for it in self.items:
            k = clave(it)
            cuenta[k] = cuenta.get(k, 0) + 1
        return sorted(cuenta.items(), key=lambda kv: (-kv[1], kv[0]))


def _lista(partes: list[str]) -> str:
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def resumen(res: ResultadoTematico) -> str:
    """«Se identificaron VEINTIÚN (21) expedientes …: DOCE (12) en comisión, …»."""
    c = res.consulta
    total = len(res.items)
    if c.eje:
        objeto = f"que responden al eje «{c.eje}»"
    elif len(c.palabras) == 1:
        objeto = f"que mencionan «{c.palabras[0]}» en su extracto"
    elif c.palabras:
        cuales = "todas estas palabras" if c.modo == "todas" else "alguna de estas palabras"
        objeto = f"que mencionan {cuales} en su extracto: {', '.join(c.palabras)}"
    else:
        objeto = "con los criterios indicados"
    periodo = f"en {c.anio_desde}" if c.anio_desde == c.anio_hasta else f"entre {c.anio_desde} y {c.anio_hasta}"
    if not total:
        return f"No se identificaron expedientes {objeto} entre los ingresados {periodo}."
    texto = f"Se identificaron {cantidad(total, 'expediente', 'expedientes')} {objeto}, ingresados {periodo}"
    etapas = [(n, k) for n, k in res.conteo_etapas()]
    if res.detallados and etapas:
        partes = [f"{cantidad(k, '', '').strip()} {_FRASE[n][0 if k == 1 else 1]}" for n, k in etapas]
        texto += ": " + _lista(partes)
    return texto + "."


def resumen_tipos(res: ResultadoTematico) -> str:
    partes = []
    for tipo, k in res.conteo(lambda it: it.hallazgo.ident.tipo or "?"):
        sing, plur = NOMBRE_TIPO_PLURAL.get(tipo, (config.TIPOS.get(tipo, tipo).lower(),) * 2)
        partes.append(cantidad(k, sing, plur))
    return ("Por tipo: " + _lista(partes) + ".") if partes else ""


def texto_resumen_tematico(res: ResultadoTematico) -> str:
    lineas = [f"Informe temático: {res.consulta.titulo()}", "", resumen(res), resumen_tipos(res), ""]
    lineas += [f"{k}: {v}" for k, v in res.consulta.criterios()]
    lineas.append("")
    for it in res.items:
        i = it.hallazgo.ident
        etapa = it.situacion.titulo if it.situacion else ETAPA[it.nivel]
        lineas.append(f"{i.corto} ({i.tipo or '—'})  {etapa}")
        lineas.append(f"    {it.hallazgo.extracto[:160]}")
        lineas.append(f"    {it.url}")
    return "\n".join(lineas)


def _nada(*_a, **_k):
    return None


def _orden(it: Item):
    i = it.hallazgo.ident
    return (ORDEN.index(it.nivel), -i.anio, i.origen, -i.numero)


def _detallar(cliente: Cliente, it: Item, opciones: OpcionesTematicas, hoy: date) -> None:
    try:
        ident = it.hallazgo.ident
        if not ident.tipo:
            ident = ident.con_tipo(ficha_mod.resolver_tipo(cliente, ident))
            it.hallazgo.ident = ident
        it.ficha = ficha_mod.descargar_ficha(cliente, ident)
        it.situacion = situacion_mod.calcular(it.ficha, hoy)
        if opciones.buscar_reuniones:
            it.reuniones, _ = comisiones.buscar_reuniones(cliente, it.ficha, opciones.incluir_asesores, 2, None, hoy)
            it.reuniones_buscadas = True
    except Cancelado:
        raise
    except Exception as e:  # noqa: BLE001 - se informa en el renglón del expediente
        it.error = str(e) or type(e).__name__


def generar_tematico(consulta: Consulta, opciones: OpcionesTematicas, cliente: Cliente, avisar=_nada,
                     hoy: date | None = None, escribir: bool = True) -> ResultadoTematico:
    from .servicio import Opciones, generar

    hoy = hoy or date.today()
    advertencias: list[str] = []

    def avisar_y_guardar(evento, mensaje="", **datos):
        if evento == "advertencia" and mensaje:
            advertencias.append(mensaje)
        avisar(evento, mensaje, **datos)

    avisar("etapa", f"Buscando expedientes: {consulta.titulo()}…")
    hallazgos, estadisticas = busqueda.buscar(cliente, consulta, avisar_y_guardar)
    avisar("log", f"Cumplen los criterios: {len(hallazgos)} (el sitio devolvió {estadisticas['distintos']} distintos).")
    items = [Item(h) for h in hallazgos]

    a_detallar = items[:opciones.limite] if opciones.detallar else []
    limite_aplicado = opciones.detallar and len(items) > opciones.limite
    if limite_aplicado:
        avisar_y_guardar("advertencia", f"Se consultó la ficha de los primeros {opciones.limite} de {len(items)} "
                                         "expedientes; el resto figura sin etapa. Acotá la búsqueda o subí el límite.")
    if a_detallar:
        avisar("etapa", f"Consultando la ficha de {len(a_detallar)} expedientes…")
        hilos = 2 if opciones.buscar_reuniones else max(1, opciones.max_hilos)
        with ThreadPoolExecutor(max_workers=hilos) as ejecutor:
            futuros = [ejecutor.submit(_detallar, cliente, it, opciones, hoy) for it in a_detallar]
            try:
                for n, futuro in enumerate(as_completed(futuros), 1):
                    futuro.result()
                    avisar("progreso", actual=n, total=len(a_detallar))
            except Cancelado:
                for f in futuros:
                    f.cancel()
                raise
        fallidas = [it for it in a_detallar if it.error]
        if fallidas:
            avisar_y_guardar("advertencia", f"No se pudo leer la ficha de {len(fallidas)} expediente(s): "
                                             + ", ".join(it.hallazgo.ident.corto for it in fallidas[:10])
                                             + ("…" if len(fallidas) > 10 else ""))

    if opciones.informes_individuales:
        con_ficha = [it for it in a_detallar if it.ficha]
        carpeta = Path(opciones.carpeta_salida) / nombre_archivo_seguro(
            f"Informes completos - {consulta.titulo()[:60]} ({hoy:%Y-%m-%d})")
        formatos = tuple(f for f in opciones.formatos if f in ("docx", "html")) or ("docx",)
        for n, it in enumerate(con_ficha, 1):
            ident = it.hallazgo.ident
            avisar("etapa", f"Informe completo {n} de {len(con_ficha)}: {ident.corto}…")
            try:
                r = generar(ident.corto, Opciones(tipo=ident.tipo, formatos=formatos, carpeta_salida=carpeta,
                                                  incluir_asesores=opciones.incluir_asesores,
                                                  max_hilos=opciones.max_hilos),
                            cliente, _nada, hoy)
                it.informes = r.archivos
                if not it.reuniones_buscadas:
                    it.reuniones, it.reuniones_buscadas = r.reuniones, True
            except Cancelado:
                raise
            except Exception as e:  # noqa: BLE001
                avisar_y_guardar("advertencia", f"No se pudo generar el informe completo de {ident.corto}: {e}")

    items.sort(key=_orden)
    res = ResultadoTematico(
        consulta=consulta, items=items, generado=datetime.now(), advertencias=advertencias,
        estadisticas=estadisticas, detallados=len(a_detallar), limite_aplicado=limite_aplicado,
        busco_reuniones=any(it.reuniones_buscadas for it in items), notas_usuario=opciones.notas_usuario.strip(),
    )
    if escribir:
        escribir_informes(res, opciones, avisar)
    return res


def escribir_informes(res: ResultadoTematico, opciones: OpcionesTematicas, avisar=_nada) -> dict[str, Path]:
    from . import informe_tematico

    carpeta = Path(opciones.carpeta_salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    base = nombre_archivo_seguro(opciones.nombre_archivo or
                                 f"Informe temático - {res.consulta.titulo()[:60]} ({res.generado:%Y-%m-%d})")
    escritores = {"docx": informe_tematico.escribir_docx, "html": informe_tematico.escribir_html,
                  "xlsx": informe_tematico.escribir_xlsx}
    for formato in opciones.formatos:
        if formato not in escritores:
            continue
        avisar("etapa", f"Escribiendo el informe temático ({formato.upper()})…")
        destino = carpeta / f"{base}.{formato}"
        try:
            escritores[formato](res, destino)
        except PermissionError:
            destino = carpeta / f"{base} {res.generado:%H%M%S}.{formato}"
            escritores[formato](res, destino)
        res.archivos[formato] = destino
        avisar("log", f"Guardado: {destino}")
    return res.archivos


__all__ = ["OpcionesTematicas", "ResultadoTematico", "generar_tematico", "resumen", "texto_resumen_tematico",
           "fmt_fecha"]
