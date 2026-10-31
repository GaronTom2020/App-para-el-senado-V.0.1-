"""Lista de seguimiento: expedientes que se revisan seguido para avisar qué cambió.

De cada expediente se guarda una «foto» del último estado conocido (situación, giros,
órdenes del día, sanción, votaciones, movimientos en Diputados, reuniones y convocatorias). Al revisar, se arma
el informe de nuevo, sin escribir archivos, y se compara con la foto anterior.

La lista se guarda en `seguimiento.json`, en la carpeta de configuración del programa
(o en el archivo que se indique, por ejemplo para correrla en GitHub Actions).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape
from pathlib import Path

from . import __version__, config, hcdn
from .cliente import Cancelado, Cliente
from .identificador import ErrorIdentificador, parsear
from .modelos import Resultado
from .numeros import cantidad, en_letras
from .contenido import sesiones_votadas
from .servicio import Opciones, generar
from .util import fmt_fecha, nombre_comision, nombre_archivo_seguro, normalizar, titulo_es

DIAS_AVISO_CADUCIDAD = 60
VERSION = 1

# Orden en que se listan las novedades de un expediente.
CLASES = ("error", "alta", "situacion", "sancion", "votacion", "diputados", "dictamen", "egreso", "giro",
          "convocatoria", "reunion", "caducidad")
# Movimientos del sitio de Diputados que interesan para el seguimiento.
_MOVIMIENTOS = ("PASA A", "VUELVE A", "VETO", "INSISTENCIA", "OBSERVA")


def archivo_por_defecto() -> Path:
    return config.carpeta_app() / "seguimiento.json"


@dataclass
class Seguido:
    expediente: str                    # forma corta: PE-99/26
    tipo: str | None = None
    agregado: str = ""
    revisado: str | None = None
    foto: dict | None = None

    @property
    def ident(self):
        return parsear(self.expediente, self.tipo)


@dataclass
class Novedad:
    clase: str
    texto: str
    url: str | None = None


@dataclass
class Revision:
    seguido: Seguido
    novedades: list[Novedad] = field(default_factory=list)
    situacion: str = ""
    url: str | None = None
    error: str | None = None


@dataclass
class OpcionesSeguimiento:
    buscar_reuniones: bool = True
    incluir_asesores: bool = True
    formatos: tuple[str, ...] = ("html", "md")
    carpeta_salida: Path = field(default_factory=config.carpeta_informes_por_defecto)
    nombre_archivo: str | None = None


@dataclass
class ResultadoSeguimiento:
    revisiones: list[Revision]
    generado: datetime = field(default_factory=datetime.now)
    archivos: dict[str, Path] = field(default_factory=dict)

    @property
    def con_novedades(self) -> list[Revision]:
        return [r for r in self.revisiones if r.novedades]


# ===================================================================== lista

class Lista:
    def __init__(self, archivo: Path | None = None):
        self.archivo = Path(archivo) if archivo else archivo_por_defecto()
        self.seguidos: list[Seguido] = []
        try:
            datos = json.loads(self.archivo.read_text(encoding="utf-8"))
            for d in datos.get("expedientes", []):
                self.seguidos.append(Seguido(d["expediente"], d.get("tipo"), d.get("agregado", ""),
                                             d.get("revisado"), d.get("foto")))
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def guardar(self) -> None:
        datos = {"version": VERSION, "expedientes": [
            {"expediente": s.expediente, "tipo": s.tipo, "agregado": s.agregado, "revisado": s.revisado,
             "foto": s.foto} for s in self.seguidos]}
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.archivo.with_suffix(".tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporal, self.archivo)

    def buscar(self, texto: str) -> Seguido | None:
        corto = parsear(texto).corto
        return next((s for s in self.seguidos if s.expediente == corto), None)

    def agregar(self, texto: str, tipo: str | None = None, hoy: date | None = None) -> tuple[Seguido, bool]:
        """Devuelve (seguido, si era nuevo). Lanza ErrorIdentificador si el número no se entiende."""
        ident = parsear(texto, tipo)
        existente = self.buscar(ident.corto)
        if existente:
            if ident.tipo and not existente.tipo:
                existente.tipo = ident.tipo
            return existente, False
        nuevo = Seguido(ident.corto, ident.tipo, (hoy or date.today()).isoformat())
        self.seguidos.append(nuevo)
        return nuevo, True

    def quitar(self, texto: str) -> bool:
        try:
            s = self.buscar(texto)
        except ErrorIdentificador:
            return False
        if s:
            self.seguidos.remove(s)
        return s is not None


# ====================================================================== foto

def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _fecha(valor: str | None) -> date | None:
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def foto(r: Resultado) -> dict:
    """Estado del expediente, en datos simples que se pueden guardar en JSON."""
    f, s = r.ficha, r.situacion
    return {
        "situacion": s.titulo,
        "nivel": s.nivel,
        "tipo": f.id.tipo,
        "url": f.url,
        "giros": [[g.comision, _iso(g.ingreso), _iso(g.egreso)] for g in f.giros],
        "ordenes": [[od.numero, od.estado, _iso(od.fecha), od.url] for od in f.ordenes_del_dia],
        "resoluciones": [[b.titulo, [list(c) for c in b.campos if c[1]]] for b in f.resoluciones],
        "votaciones": [[sv.fecha, " ".join(sv.lineas), sv.enlaces[0].url if sv.enlaces else None]
                       for sv in sesiones_votadas(r)],
        "diputados": [[m.camara, m.movimiento, _iso(m.fecha), m.resultado]
                      for m in (r.diputados.tramite if r.diputados is not None else [])
                      if normalizar(m.resultado) in ("MEDIA SANCION", "SANCIONADO", "RECHAZADO")
                      or any(k in normalizar(m.movimiento) for k in _MOVIMIENTOS)],
        "diputados_url": r.diputados.url if r.diputados is not None else None,
        "diputados_numero": r.diputados.expediente_diputados if r.diputados is not None else None,
        "diputados_giros": list(r.diputados.giros_diputados) if r.diputados is not None else [],
        "diputados_dictamenes": [[d.orden_del_dia, _iso(d.fecha), hcdn.mayoria(d.texto)]
                                 for d in (r.diputados.dictamenes_de("Diputados") if r.diputados is not None else [])],
        "reuniones": [[x.nota_id, _iso(x.fecha), x.titulo, x.url] for x in r.reuniones],
        "reuniones_buscadas": r.busqueda.realizada,
        "convocadas": [[_iso(c.fecha) or c.fecha_texto, c.hora, c.titulo, c.comision, c.url] for c in r.convocadas],
        "caducidad": _iso(s.caducidad.fecha) if s.caducidad else None,
    }


# ================================================================ comparación

def _sin_ceros(numero: str) -> str:
    n, _, resto = numero.partition("-")
    return f"{int(n)}-{resto}" if n.isdigit() else numero


def _movimiento(camara: str, movimiento: str, fecha: str | None, resultado: str) -> str:
    """«Senado: media sanción (29/10/2026)» · «pasó a Diputados» · «Diputados: veto total del Poder Ejecutivo»."""
    cuando = f" ({fmt_fecha(_fecha(fecha))})" if fecha else ""
    n = normalizar(movimiento)
    if normalizar(resultado) == "RECHAZADO":
        return f"{camara}: rechazo total del proyecto{cuando}"
    if normalizar(resultado) in ("MEDIA SANCION", "SANCIONADO"):
        que = "media sanción" if normalizar(resultado) == "MEDIA SANCION" else "sanción definitiva"
        if "MODIFICACION" in n:
            que += ", con modificaciones"
        return f"{camara}: {que}{cuando}"
    destino = re.match(r"(PASA|VUELVE) A (SENADO|DIPUTADOS)", n)
    if destino:
        return ("pasó a " if destino.group(1) == "PASA" else "volvió a ") + destino.group(2).capitalize() + cuando
    if "VETO" in n or "OBSERVA" in n:
        return f"{camara}: {'veto parcial' if 'PARCIAL' in n else 'veto total'} del Poder Ejecutivo{cuando}"
    if "INSISTENCIA" in n:
        rechazada = "RECHAZO" in n or "ACEPTA VETO" in n
        return f"{camara}: {'no alcanzó los dos tercios para insistir' if rechazada else 'insistencia'}{cuando}"
    return f"{camara}: {titulo_es(movimiento.rstrip(' -')).lower()}{cuando}"


def comparar(anterior: dict | None, nueva: dict, hoy: date) -> list[Novedad]:
    novedades: list[Novedad] = []
    agregar = novedades.append
    if anterior is None:
        agregar(Novedad("alta", f"Primera revisión. Situación: {nueva['situacion']}.", nueva.get("url")))
    else:
        if anterior.get("situacion") != nueva["situacion"]:
            agregar(Novedad("situacion", f"Cambió la situación: de «{anterior.get('situacion')}» a "
                                         f"«{nueva['situacion']}».", nueva.get("url")))

        previos = {(g[0], g[1]): g for g in anterior.get("giros", [])}
        for comision, ingreso, egreso in nueva["giros"]:
            antes = previos.get((comision, ingreso))
            nombre = nombre_comision(comision)
            if antes is None:
                agregar(Novedad("giro", f"Giro nuevo a la comisión de {nombre}"
                                        + (f" (ingreso el {fmt_fecha(_fecha(ingreso))})." if ingreso else ".")))
            elif egreso and not antes[2]:
                agregar(Novedad("egreso", f"Egresó de la comisión de {nombre} el {fmt_fecha(_fecha(egreso))}."))

        ods_previas = {o[0]: o for o in anterior.get("ordenes", [])}
        for numero, estado, fecha, url in nueva["ordenes"]:
            antes = ods_previas.get(numero)
            if antes is None:
                cuando = f" del {fmt_fecha(_fecha(fecha))}" if fecha else ""
                agregar(Novedad("dictamen", f"Dictamen nuevo: Orden del Día N° {numero}{cuando} ({estado.lower()}).",
                                url))
            elif antes[1] != estado:
                agregar(Novedad("dictamen", f"La Orden del Día N° {numero} pasó de «{antes[1].lower()}» a "
                                            f"«{estado.lower()}».", url))

        resoluciones_previas = {b[0]: b[1] for b in anterior.get("resoluciones", [])}
        for titulo, campos in nueva["resoluciones"]:
            if resoluciones_previas.get(titulo) != campos:
                detalle = "; ".join(f"{k.lower()}: {v}" for k, v in campos)
                agregar(Novedad("sancion", f"La ficha registra {titulo.lower()}: {detalle}.", nueva.get("url")))

        sesiones_previas = {v[0] for v in anterior.get("votaciones", []) if len(v) == 3}
        for fecha, texto, url in nueva["votaciones"]:
            if fecha not in sesiones_previas:
                agregar(Novedad("votacion", f"Votación en el recinto el {fecha}. {texto}", url))

        movimientos_previos = {tuple(m[:3]) for m in anterior.get("diputados", [])}
        for camara, movimiento, fecha, resultado in nueva.get("diputados", []):
            if (camara, movimiento, fecha) not in movimientos_previos:
                agregar(Novedad("diputados", f"El sitio de Diputados registra: {_movimiento(camara, movimiento, fecha, resultado)}.",
                                nueva.get("diputados_url")))

        url_dip = nueva.get("diputados_url")
        if nueva.get("diputados_numero") and not anterior.get("diputados_numero"):
            agregar(Novedad("diputados", f"Ingresó a Diputados como expediente {_sin_ceros(nueva['diputados_numero'])}.",
                            url_dip))
        giros_previos = set(anterior.get("diputados_giros", []))
        nuevos_giros = [g for g in nueva.get("diputados_giros", []) if g not in giros_previos]
        if nuevos_giros:
            nombres = [nombre_comision(titulo_es(g)) for g in nuevos_giros]
            agregar(Novedad("diputados", "Diputados lo giró a " + ("la comisión de " if len(nombres) == 1 else
                                                                  "las comisiones de ")
                            + (nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1])
                            + ".", url_dip))
        dictamenes_previos = {d[0] for d in anterior.get("diputados_dictamenes", [])}
        for od, fecha, que in nueva.get("diputados_dictamenes", []):
            if od not in dictamenes_previos:
                cuando = f" del {fmt_fecha(_fecha(fecha))}" if fecha else ""
                agregar(Novedad("diputados", f"Dictamen en Diputados: Orden del Día N° {hcdn._od(od)}{cuando}"
                                             + (f", {que}" if que else "") + ".", url_dip))

        if nueva.get("reuniones_buscadas") and anterior.get("reuniones_buscadas"):
            notas_previas = {x[0] for x in anterior.get("reuniones", [])}
            for nota_id, fecha, titulo, url in nueva["reuniones"]:
                if nota_id not in notas_previas:
                    agregar(Novedad("reunion", f"Se trató en la reunión del {fmt_fecha(_fecha(fecha))}: {titulo}.", url))

        convocadas_previas = {(c[0], c[2]) for c in anterior.get("convocadas", [])}
        for fecha, hora, titulo, comision, url in nueva["convocadas"]:
            if (fecha, titulo) not in convocadas_previas:
                cuando = fmt_fecha(_fecha(fecha), fecha or "") + (f", {hora} h" if hora else "")
                agregar(Novedad("convocatoria", f"Reunión convocada con el expediente en el temario: {cuando}, "
                                                f"{comision} ({titulo}).", url))

    caducidad = _fecha(nueva.get("caducidad"))
    if caducidad and 0 <= (caducidad - hoy).days < DIAS_AVISO_CADUCIDAD:
        faltan = (caducidad - hoy).days
        cuando = "hoy" if faltan == 0 else f"en {cantidad(faltan, 'día', 'días')}"
        agregar(Novedad("caducidad", f"Caducidad cercana: {fmt_fecha(caducidad)} ({cuando})."))
    novedades.sort(key=lambda n: CLASES.index(n.clase))
    return novedades


# ================================================================= revisión

def _nada(*_args, **_kwargs):
    return None


def revisar(lista: Lista, cliente: Cliente, opciones: OpcionesSeguimiento | None = None, avisar=_nada,
            hoy: date | None = None) -> ResultadoSeguimiento:
    opciones = opciones or OpcionesSeguimiento()
    hoy = hoy or date.today()
    revisiones: list[Revision] = []
    total = len(lista.seguidos)
    for i, s in enumerate(lista.seguidos, 1):
        avisar("etapa", f"Revisando {s.expediente} ({i} de {total})…")
        avisar("progreso", actual=i - 1, total=total)
        try:
            r = generar(s.expediente, Opciones(tipo=s.tipo, buscar_reuniones=opciones.buscar_reuniones,
                                               buscar_relacionados=False,
                                               incluir_asesores=opciones.incluir_asesores, formatos=()),
                        cliente, lambda ev, msg="", **d: avisar("log", msg) if ev in ("log", "advertencia") else None,
                        hoy=hoy, escribir=False)
        except Cancelado:
            raise
        except Exception as e:  # noqa: BLE001 - un expediente que falla no corta la revisión
            texto = f"No se pudo revisar: {e}"
            revisiones.append(Revision(s, [Novedad("error", texto)], (s.foto or {}).get("situacion", ""),
                                       (s.foto or {}).get("url"), str(e)))
            avisar("advertencia", f"{s.expediente}: {texto}")
            continue
        nueva = foto(r)
        revisiones.append(Revision(s, comparar(s.foto, nueva, hoy), nueva["situacion"], nueva["url"]))
        s.foto, s.revisado, s.tipo = nueva, datetime.now().isoformat(timespec="minutes"), r.ficha.id.tipo
    avisar("progreso", actual=total, total=total)
    lista.guardar()
    resultado = ResultadoSeguimiento(revisiones)
    if opciones.formatos:
        escribir(resultado, opciones)
    return resultado


# ================================================================== salidas

def resumen(res: ResultadoSeguimiento) -> str:
    n = len(res.revisiones)
    if not n:
        return "La lista de seguimiento está vacía."
    k = len(res.con_novedades)
    if n == 1:
        return f"Se revisó {cantidad(1, 'expediente', 'expedientes')}, {'con' if k else 'sin'} novedades."
    texto = f"Se revisaron {cantidad(n, 'expediente', 'expedientes')}"
    if k == 0:
        return texto + ", sin novedades."
    if k == n:
        return texto + ", todos con novedades."
    return texto + f": {en_letras(k)} ({k}) con novedades y {en_letras(n - k)} ({n - k}) sin novedades."


def markdown(res: ResultadoSeguimiento) -> str:
    lineas = [f"# Seguimiento de expedientes — {res.generado:%d/%m/%Y}", "", resumen(res), ""]
    for r in res.con_novedades:
        titulo = f"[{r.seguido.expediente}]({r.url})" if r.url else r.seguido.expediente
        lineas += [f"## {titulo}", "", f"*{r.situacion}*" if r.situacion else "", ""]
        for n in r.novedades:
            lineas.append(f"- {n.texto}" + (f" ([ver]({n.url}))" if n.url else ""))
        lineas.append("")
    sin = [r for r in res.revisiones if not r.novedades]
    if sin:
        lineas += ["## Sin novedades", ""]
        lineas += [f"- {r.seguido.expediente}: {r.situacion}" for r in sin]
        lineas.append("")
    lineas.append(f"_Generado el {res.generado:%d/%m/%Y a las %H:%M} con Informe de Expedientes {__version__}, "
                  "con datos públicos de senado.gob.ar._")
    return "\n".join(x for x in lineas) + "\n"


def html(res: ResultadoSeguimiento) -> str:
    from .informe_html import ESTILOS

    def e(t) -> str:
        return escape(str(t or ""), quote=True)

    def enlace(texto, url) -> str:
        return f'<a href="{e(url)}" target="_blank" rel="noopener">{e(texto)}</a>' if url else e(texto)

    partes = ['<div class="membrete"><span>H. Senado de la Nación</span>'
              f"<span>Revisión del {res.generado:%d/%m/%Y, %H:%M} h</span></div>",
              '<h1 class="numero">Seguimiento de expedientes</h1>',
              f'<p class="extracto">{e(resumen(res))}</p>']
    for r in res.con_novedades:
        clase = "lacre" if any(n.clase in ("error", "caducidad") for n in r.novedades) else ""
        partes.append(f'<section class="situacion {clase}"><p class="rotulo">{e(r.situacion)}</p>'
                      f"<h2>{enlace(r.seguido.expediente, r.url)}</h2><ul>")
        partes += [f"<li>{e(n.texto)}" + (f" {enlace('Ver', n.url)}" if n.url else "") + "</li>" for n in r.novedades]
        partes.append("</ul></section>")
    sin = [r for r in res.revisiones if not r.novedades]
    if sin:
        filas = "".join(f"<tr><td>{enlace(r.seguido.expediente, r.url)}</td><td>{e(r.situacion)}</td></tr>"
                        for r in sin)
        partes.append("<h2>Sin novedades</h2><div class='tabla'><table><thead><tr><th>Expediente</th>"
                      f"<th>Situación</th></tr></thead><tbody>{filas}</tbody></table></div>")
    partes.append("<footer><p>Revisión automática con datos públicos del sitio del H. Senado de la Nación. "
                  f"Programa Informe de Expedientes, versión {e(__version__)}.</p></footer>")
    return ('<!DOCTYPE html>\n<html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>Seguimiento de expedientes — {res.generado:%d/%m/%Y}</title>"
            f"<style>{ESTILOS}</style></head><body><main class='hoja'>" + "".join(partes) + "</main></body></html>\n")


def escribir(res: ResultadoSeguimiento, opciones: OpcionesSeguimiento) -> dict[str, Path]:
    carpeta = Path(opciones.carpeta_salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    base = nombre_archivo_seguro(opciones.nombre_archivo or f"Seguimiento ({res.generado:%Y-%m-%d})")
    for formato, generador in (("html", html), ("md", markdown)):
        if formato in opciones.formatos:
            destino = carpeta / f"{base}.{formato}"
            destino.write_text(generador(res), encoding="utf-8")
            res.archivos[formato] = destino
    return res.archivos
