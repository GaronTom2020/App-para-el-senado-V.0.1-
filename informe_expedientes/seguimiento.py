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

from . import __version__, config, hcdn, orden_dia
from .cliente import Cancelado, Cliente
from .identificador import ErrorIdentificador, parsear
from .modelos import Resultado
from .numeros import cantidad, en_letras
from .contenido import sesiones_votadas
from .servicio import Opciones, generar
from .util import fmt_fecha, nombre_comision, nombre_archivo_seguro, normalizar, parsear_fecha, titulo_es

DIAS_AVISO_CADUCIDAD = 60
VERSION = 1

# Orden en que se listan las novedades de un expediente.
CLASES = ("error", "alta", "situacion", "sancion", "votacion", "diputados", "dictamen", "relacionado", "egreso",
          "giro", "convocatoria", "reunion", "caducidad")
# Movimientos del sitio de Diputados que interesan para el seguimiento.
_MOVIMIENTOS = ("PASA A", "VUELVE A", "VETO", "INSISTENCIA", "OBSERVA")


def archivo_por_defecto() -> Path:
    return config.carpeta_app() / "seguimiento.json"


def clave(texto: str, tipo: str | None = None) -> tuple[str, str | None]:
    """(forma corta, tipo): «PE-99/26» o «OD 413/26». Lanza ErrorIdentificador si no se entiende."""
    od = orden_dia.parsear_od(texto)
    if od:
        return orden_dia.etiqueta(od), None
    ident = parsear(texto, tipo)
    return ident.corto, ident.tipo


@dataclass
class Seguido:
    expediente: str                    # forma corta: PE-99/26, o «OD 413/26» para seguir un despacho
    tipo: str | None = None
    agregado: str = ""
    revisado: str | None = None
    foto: dict | None = None
    alias: str = ""                    # nombre con que se lo conoce: «Ley de Salud Mental»
    grupos: list[str] = field(default_factory=list)

    @property
    def ident(self):
        return parsear(self.expediente, self.tipo)

    @property
    def nombre(self) -> str:
        """«Ley de Salud Mental (PE-13/26)» si tiene nombre; si no, el número."""
        return f"{self.alias} ({self.expediente})" if self.alias else self.expediente


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

    @property
    def ultimo_movimiento(self) -> tuple[date | None, str]:
        return ultimo_movimiento(self.seguido.foto)

    def texto_movimiento(self) -> str:
        """«Último movimiento: 29/10/2026 (votación en el recinto)»; vacío si no hay fechas."""
        fecha, que = self.ultimo_movimiento
        return f"Último movimiento: {fmt_fecha(fecha)} ({que})" if fecha else ""


@dataclass
class OpcionesSeguimiento:
    buscar_reuniones: bool = True
    buscar_relacionados: bool = False      # lento: lee la ficha de cada relacionado
    incluir_asesores: bool = True
    formatos: tuple[str, ...] = ("html", "md")
    carpeta_salida: Path = field(default_factory=config.carpeta_informes_por_defecto)
    nombre_archivo: str | None = None


@dataclass
class ResultadoSeguimiento:
    revisiones: list[Revision]
    generado: datetime = field(default_factory=datetime.now)
    archivos: dict[str, Path] = field(default_factory=dict)
    grupo: str | None = None

    @property
    def con_novedades(self) -> list[Revision]:
        return [r for r in self.revisiones if r.novedades]


# ===================================================================== lista

class Lista:
    def __init__(self, archivo: Path | None = None):
        self.archivo = Path(archivo) if archivo else archivo_por_defecto()
        self.seguidos: list[Seguido] = []
        self.grupos: list[str] = []          # también los grupos vacíos, para que no se pierdan al guardar
        try:
            datos = json.loads(self.archivo.read_text(encoding="utf-8"))
            for d in datos.get("expedientes", []):
                self.seguidos.append(Seguido(d["expediente"], d.get("tipo"), d.get("agregado", ""),
                                             d.get("revisado"), d.get("foto"), d.get("alias") or "",
                                             list(d.get("grupos") or [])))
            self.grupos = [g for g in datos.get("grupos", []) if isinstance(g, str)]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        for s in self.seguidos:
            for g in s.grupos:
                if g not in self.grupos:
                    self.grupos.append(g)

    def guardar(self) -> None:
        datos = {"version": VERSION, "grupos": self.grupos, "expedientes": [
            {"expediente": s.expediente, "tipo": s.tipo, "agregado": s.agregado, "revisado": s.revisado,
             "alias": s.alias, "grupos": s.grupos, "foto": s.foto} for s in self.seguidos]}
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.archivo.with_suffix(".tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporal, self.archivo)

    def buscar(self, texto: str) -> Seguido | None:
        corto, _tipo = clave(texto)
        return next((s for s in self.seguidos if s.expediente == corto), None)

    def agregar(self, texto: str, tipo: str | None = None, hoy: date | None = None, alias: str = "",
                grupo: str | None = None) -> tuple[Seguido, bool]:
        """Devuelve (seguido, si era nuevo). Lanza ErrorIdentificador si el número no se entiende."""
        corto, tipo = clave(texto, tipo)
        existente = self.buscar(corto)
        if existente:
            if tipo and not existente.tipo:
                existente.tipo = tipo
            if alias and not existente.alias:
                existente.alias = alias.strip()
            if grupo:
                self.sumar_a_grupo(existente, grupo)
            return existente, False
        nuevo = Seguido(corto, tipo, (hoy or date.today()).isoformat(), alias=alias.strip())
        self.seguidos.append(nuevo)
        if grupo:
            self.sumar_a_grupo(nuevo, grupo)
        return nuevo, True

    # ---- grupos
    def crear_grupo(self, nombre: str) -> str:
        nombre = " ".join(nombre.split())
        if not nombre:
            raise ValueError("El grupo necesita un nombre.")
        existente = next((g for g in self.grupos if normalizar(g) == normalizar(nombre)), None)
        if existente:
            return existente
        self.grupos.append(nombre)
        return nombre

    def sumar_a_grupo(self, s: Seguido, grupo: str) -> None:
        grupo = self.crear_grupo(grupo)
        if grupo not in s.grupos:
            s.grupos.append(grupo)

    def sacar_de_grupo(self, s: Seguido, grupo: str) -> None:
        if grupo in s.grupos:
            s.grupos.remove(grupo)

    def renombrar_grupo(self, viejo: str, nuevo: str) -> str:
        nuevo = " ".join(nuevo.split())
        if not nuevo:
            raise ValueError("El grupo necesita un nombre.")
        if any(g != viejo and normalizar(g) == normalizar(nuevo) for g in self.grupos):
            raise ValueError(f"Ya existe un grupo llamado «{nuevo}».")
        self.grupos = [nuevo if g == viejo else g for g in self.grupos]
        for s in self.seguidos:
            s.grupos = [nuevo if g == viejo else g for g in s.grupos]
        return nuevo

    def borrar_grupo(self, nombre: str) -> None:
        """Borra el grupo; los expedientes siguen en la lista."""
        self.grupos = [g for g in self.grupos if g != nombre]
        for s in self.seguidos:
            if nombre in s.grupos:
                s.grupos.remove(nombre)

    def del_grupo(self, grupo: str | None) -> list[Seguido]:
        return list(self.seguidos) if not grupo else [s for s in self.seguidos if grupo in s.grupos]

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
        "extracto": f.extracto,
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
        "relacionados": [[x.ident.corto, x.texto_relacion(), x.url, x.situacion] for x in r.relacionados],
        "relacionados_buscados": r.relacionados_consultados,
    }


def situacion_breve(situacion: str) -> str:
    """«Media sanción del Senado (votado el 29/10/2026)» → «Media sanción del Senado»."""
    breve = re.split(r"\s*[(:;]|\s+[—–]\s+|\.\s", situacion or "", maxsplit=1)[0].strip(" .")
    return breve if len(breve) <= 48 else breve[:46].rsplit(" ", 1)[0] + "…"


def ultimo_movimiento(f: dict | None) -> tuple[date | None, str]:
    """La fecha más reciente de la foto (giros, dictámenes, votaciones, Diputados) y qué pasó ese día."""
    if not f:
        return None, ""
    eventos: list[tuple[date, str]] = []

    def sumar(fecha, que):
        d = fecha if isinstance(fecha, date) else (_fecha(fecha) or parsear_fecha(fecha))
        if d:
            eventos.append((d, que))

    for comision, ingreso, egreso in f.get("giros", []):
        sumar(ingreso, f"giro a la comisión de {nombre_comision(comision)}")
        sumar(egreso, f"egreso de la comisión de {nombre_comision(comision)}")
    for numero, estado, fecha, _url in f.get("ordenes", []):
        sumar(fecha, f"Orden del Día N° {numero}")
    for v in f.get("votaciones", []):
        sumar(v[0], "votación en el recinto")
    for camara, movimiento, fecha, resultado in f.get("diputados", []):
        sumar(fecha, _movimiento(camara, movimiento, None, resultado))
    for od, fecha, _que in f.get("diputados_dictamenes", []):
        sumar(fecha, f"dictamen en Diputados (OD {hcdn._od(od)})")
    if not eventos:
        return None, ""
    return max(eventos, key=lambda e: e[0])


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
    if anterior is not None and anterior.get("relacionados_buscados") and nueva.get("relacionados_buscados"):
        previos = {x[0] for x in anterior.get("relacionados", [])}
        for numero, relacion, url, situacion in nueva["relacionados"]:
            if numero not in previos:
                agregar(Novedad("relacionado", f"Expediente relacionado nuevo: {numero} — {relacion}"
                                               + (f" ({situacion})." if situacion else "."), url))
    novedades.sort(key=lambda n: CLASES.index(n.clase))
    return novedades


# ================================================================= revisión

def _nada(*_args, **_kwargs):
    return None


def revisar(lista: Lista, cliente: Cliente, opciones: OpcionesSeguimiento | None = None, avisar=_nada,
            hoy: date | None = None, grupo: str | None = None) -> ResultadoSeguimiento:
    """Revisa toda la lista o, con `grupo`, solo los expedientes de ese grupo."""
    opciones = opciones or OpcionesSeguimiento()
    hoy = hoy or date.today()
    revisiones: list[Revision] = []
    elegidos = lista.del_grupo(grupo)
    total = len(elegidos)
    for i, s in enumerate(elegidos, 1):
        avisar("etapa", f"Revisando {s.expediente} ({i} de {total})…")
        avisar("progreso", actual=i - 1, total=total)
        try:
            r = generar(s.expediente, Opciones(tipo=s.tipo, buscar_reuniones=opciones.buscar_reuniones,
                                               buscar_relacionados=opciones.buscar_relacionados,
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
        s.foto, s.revisado = nueva, datetime.now().isoformat(timespec="minutes")
        if not r.od:
            s.tipo = r.ficha.id.tipo
    avisar("progreso", actual=total, total=total)
    lista.guardar()
    resultado = ResultadoSeguimiento(revisiones, grupo=grupo)
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
    grupo = f" — {res.grupo}" if res.grupo else ""
    lineas = [f"# Seguimiento de expedientes{grupo} — {res.generado:%d/%m/%Y}", "", resumen(res), ""]
    for r in res.con_novedades:
        titulo = f"[{r.seguido.nombre}]({r.url})" if r.url else r.seguido.nombre
        lineas += [f"## {titulo}", "", f"*{r.situacion}*" if r.situacion else "",
                   r.texto_movimiento() + "." if r.texto_movimiento() else "", ""]
        for n in r.novedades:
            lineas.append(f"- {n.texto}" + (f" ([ver]({n.url}))" if n.url else ""))
        lineas.append("")
    sin = [r for r in res.revisiones if not r.novedades]
    if sin:
        lineas += ["## Sin novedades", ""]
        lineas += [f"- {r.seguido.nombre}: {r.situacion}" + (f" ({r.texto_movimiento().lower()})"
                                                             if r.texto_movimiento() else "") for r in sin]
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
              f'<p class="descripcion">Grupo: {e(res.grupo)}</p>' if res.grupo else "",
              f'<p class="extracto">{e(resumen(res))}</p>']
    for r in res.con_novedades:
        clase = "lacre" if any(n.clase in ("error", "caducidad") for n in r.novedades) else ""
        partes.append(f'<section class="situacion {clase}"><p class="rotulo">{e(r.situacion)}</p>'
                      f"<h2>{enlace(r.seguido.nombre, r.url)}</h2>"
                      + (f"<p class='secundario'>{e(r.texto_movimiento())}.</p>" if r.texto_movimiento() else "")
                      + "<ul>")
        partes += [f"<li>{e(n.texto)}" + (f" {enlace('Ver', n.url)}" if n.url else "") + "</li>" for n in r.novedades]
        partes.append("</ul></section>")
    sin = [r for r in res.revisiones if not r.novedades]
    if sin:
        filas = "".join(f"<tr><td>{enlace(r.seguido.nombre, r.url)}</td><td>{e(r.situacion)}</td>"
                        f"<td class='fecha'>{e(fmt_fecha(r.ultimo_movimiento[0], ''))}</td></tr>" for r in sin)
        partes.append("<h2>Sin novedades</h2><div class='tabla'><table><thead><tr><th>Expediente</th>"
                      f"<th>Situación</th><th>Último movimiento</th></tr></thead><tbody>{filas}</tbody></table></div>")
    partes.append("<footer><p>Revisión automática con datos públicos del sitio del H. Senado de la Nación. "
                  f"Programa Informe de Expedientes, versión {e(__version__)}.</p></footer>")
    return ('<!DOCTYPE html>\n<html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>Seguimiento de expedientes — {res.generado:%d/%m/%Y}</title>"
            f"<style>{ESTILOS}</style></head><body><main class='hoja'>" + "".join(partes) + "</main></body></html>\n")


# ============================================================ exportar la lista

def filas_lista(lista: Lista, grupo: str | None = None) -> list[dict]:
    """Una fila por expediente de la lista (o del grupo), con lo que se sabe de la última revisión."""
    filas = []
    for s in lista.del_grupo(grupo):
        f = s.foto or {}
        fecha, que = ultimo_movimiento(s.foto)
        filas.append({"expediente": s.expediente, "nombre": s.alias, "grupos": ", ".join(s.grupos),
                      "situacion": f.get("situacion", "Sin revisar"), "extracto": f.get("extracto", ""),
                      "movimiento": fecha, "que": que, "caducidad": _fecha(f.get("caducidad")),
                      "agregado": _fecha((s.agregado or "")[:10]), "revisado": (s.revisado or "").replace("T", " "),
                      "url": f.get("url")})
    return filas


def escribir_lista_xlsx(lista: Lista, destino: Path, grupo: str | None = None) -> Path:
    """Excel de la lista: una hoja con todos (con filtros) y una hoja por grupo."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    normal = Font(name="Arial", size=10)
    blanco = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    enlace = Font(name="Arial", size=10, color="114E9A", underline="single")
    relleno = PatternFill("solid", fgColor="1A64AB")
    arriba, envolver = Alignment(vertical="top"), Alignment(vertical="top", wrap_text=True)
    columnas = [("Expediente", 13, "expediente"), ("Nombre", 28, "nombre"), ("Grupos", 22, "grupos"),
                ("Situación", 40, "situacion"), ("Extracto", 60, "extracto"), ("Último movimiento", 13, "movimiento"),
                ("Qué fue", 26, "que"), ("Caducidad", 11, "caducidad"), ("Agregado", 11, "agregado"),
                ("Revisado", 16, "revisado"), ("Ficha", 48, "url")]

    def hoja(libro_hoja, filas):
        for col, (nombre, ancho, _) in enumerate(columnas, 1):
            celda = libro_hoja.cell(row=1, column=col, value=nombre)
            celda.font, celda.fill = blanco, relleno
            libro_hoja.column_dimensions[get_column_letter(col)].width = ancho
        for n, fila in enumerate(filas, 2):
            for col, (_, _, campo) in enumerate(columnas, 1):
                celda = libro_hoja.cell(row=n, column=col, value=fila[campo] or None)
                celda.font = normal
                celda.alignment = envolver if campo in ("situacion", "extracto", "nombre") else arriba
                if campo in ("movimiento", "caducidad", "agregado") and fila[campo]:
                    celda.number_format = "DD/MM/YYYY"
                if campo == "url" and fila[campo]:
                    celda.hyperlink, celda.font = fila[campo], enlace
        libro_hoja.freeze_panes = "B2"
        libro_hoja.auto_filter.ref = f"A1:{get_column_letter(len(columnas))}{max(1, len(filas) + 1)}"

    libro = Workbook()
    primera = libro.active
    primera.title = (grupo or "Todos")[:31]
    hoja(primera, filas_lista(lista, grupo))
    if not grupo:
        usados = {primera.title}
        for g in lista.grupos:
            titulo = re.sub(r"[\\/*?:\[\]]", "-", g)[:31]
            if titulo in usados:
                continue
            usados.add(titulo)
            hoja(libro.create_sheet(titulo), filas_lista(lista, g))
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    libro.save(destino)
    return destino


def html_lista(lista: Lista, grupo: str | None = None) -> str:
    """La lista como tabla, agrupada por grupo, para imprimir o pasar a PDF."""
    from .informe_html import ESTILOS

    def e(t) -> str:
        return escape(str(t or ""), quote=True)

    def tabla(filas) -> str:
        def enlace(f) -> str:
            return f'<a href="{e(f["url"])}">{e(f["expediente"])}</a>' if f["url"] else e(f["expediente"])

        cuerpo = "".join(
            f"<tr><td>{enlace(f)}"
            + (f"<br><span class='secundario'>{e(f['nombre'])}</span>" if f["nombre"] else "")
            + f"</td><td>{e(f['situacion'])}</td><td class='fecha'>{e(fmt_fecha(f['movimiento'], ''))}"
            + (f"<br><span class='secundario'>{e(f['que'])}</span>" if f["que"] else "") + "</td></tr>"
            for f in filas)
        return ("<div class='tabla'><table><thead><tr><th>Expediente</th><th>Situación</th>"
                f"<th>Último movimiento</th></tr></thead><tbody>{cuerpo}</tbody></table></div>")

    ahora = datetime.now()
    partes = ['<div class="membrete"><span>H. Senado de la Nación</span>'
              f"<span>Lista al {ahora:%d/%m/%Y, %H:%M} h</span></div>",
              '<h1 class="numero">Lista de seguimiento</h1>',
              f'<p class="descripcion">Grupo: {e(grupo)}</p>' if grupo else ""]
    if grupo or not lista.grupos:
        partes.append(tabla(filas_lista(lista, grupo)))
    else:
        for g in lista.grupos:
            filas = filas_lista(lista, g)
            if filas:
                partes += [f"<h2>{e(g)}</h2>", tabla(filas)]
        sueltos = [f for f, s in zip(filas_lista(lista), lista.seguidos) if not s.grupos]
        if sueltos:
            partes += ["<h2>Sin grupo</h2>", tabla(sueltos)]
    partes.append("<footer><p>Situación según la última revisión de cada expediente. Programa Informe de "
                  f"Expedientes, versión {e(__version__)}.</p></footer>")
    return ('<!DOCTYPE html>\n<html lang="es"><head><meta charset="utf-8">'
            f"<title>Lista de seguimiento — {ahora:%d/%m/%Y}</title>"
            f"<style>{ESTILOS}</style></head><body><main class='hoja'>" + "".join(partes) + "</main></body></html>\n")


def exportar_lista(lista: Lista, carpeta: Path, formato: str, grupo: str | None = None) -> Path:
    """Guarda la lista en Excel («xlsx») o PDF («pdf») y devuelve el archivo."""
    base = nombre_archivo_seguro(f"Lista de seguimiento{' ' + grupo if grupo else ''} ({date.today():%Y-%m-%d})")
    destino = Path(carpeta) / f"{base}.{formato}"
    if formato == "xlsx":
        return escribir_lista_xlsx(lista, destino, grupo)
    from .pdf import texto_a_pdf
    return texto_a_pdf(html_lista(lista, grupo), destino)


# ================================================== vencimientos y agenda de la lista
# Salen de la «foto» de la última revisión de cada expediente: no consultan el sitio, por eso son instantáneos.
# Para tenerlos al día, primero «Revisar novedades».

AVISO_VENCE = 60          # días: se marca en rojo
URGENTE_VENCE = 15        # días: además, en negrita
DIAS_AGENDA = 7           # «de la semana»: hoy y los seis días siguientes


def filas_vencimientos(lista: Lista, grupo: str | None = None, hoy: date | None = None) -> list[dict]:
    """Los expedientes con fecha de caducidad, del que vence antes al que vence después (los ya vencidos primero)."""
    hoy = hoy or date.today()
    filas = [f | {"faltan": (f["caducidad"] - hoy).days} for f in filas_lista(lista, grupo) if f["caducidad"]]
    return sorted(filas, key=lambda f: f["caducidad"])


def filas_agenda(lista: Lista, grupo: str | None = None, hoy: date | None = None) -> list[dict]:
    """Las reuniones de comisión ya convocadas con algún expediente de la lista, de hoy en adelante, en orden.

    Una reunión que trata varios expedientes de la lista aparece una vez, con todos ellos."""
    hoy = hoy or date.today()
    reuniones: dict[tuple, dict] = {}
    for s in lista.del_grupo(grupo):
        for fecha, hora, titulo, comision, url in (s.foto or {}).get("convocadas", []):
            dia = _fecha(fecha) or parsear_fecha(fecha)
            if dia is not None and dia < hoy:
                continue
            r = reuniones.setdefault((dia, hora or "", comision or titulo), {
                "fecha": dia, "fecha_texto": "" if dia else (fecha or ""), "hora": hora or "",
                "comision": comision or "", "titulo": titulo or "", "url": url, "expedientes": []})
            if s.nombre not in r["expedientes"]:
                r["expedientes"].append(s.nombre)
    return sorted(reuniones.values(), key=lambda r: (r["fecha"] is None, r["fecha"] or hoy, r["hora"]))


_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _dia(d: date) -> str:
    """«Martes 10/11»."""
    return f"{_DIAS[d.weekday()]} {d:%d/%m}"


def _cuantos(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _ultima_revision(lista: Lista, grupo: str | None) -> str:
    fechas = [s.revisado for s in lista.del_grupo(grupo) if s.revisado]
    return fmt_fecha(_fecha(min(fechas)[:10])) if fechas else ""


def _pagina(titulo: str, cuerpo: list[str], lista: Lista, grupo: str | None, estilos: str = "") -> str:
    from .informe_html import ESTILOS
    ahora = datetime.now()
    revision = _ultima_revision(lista, grupo)
    pie = ("Según la última revisión de cada expediente"
           + (f" (la más antigua, del {revision})" if revision else "")
           + ". Para tenerlo al día, primero «Revisar novedades». "
           f"Programa Informe de Expedientes, versión {escape(__version__)}.")
    return ('<!DOCTYPE html>\n<html lang="es"><head><meta charset="utf-8">'
            f"<title>{escape(titulo)} — {ahora:%d/%m/%Y}</title><style>{ESTILOS}{estilos}</style></head>"
            "<body><main class='hoja'>"
            f'<div class="membrete"><span>H. Senado de la Nación</span><span>{ahora:%d/%m/%Y, %H:%M} h</span></div>'
            f'<h1 class="numero">{escape(titulo)}</h1>'
            + (f'<p class="descripcion">Grupo: {escape(grupo)}</p>' if grupo else "")
            + "".join(cuerpo) + f"<footer><p>{pie}</p></footer></main></body></html>\n")


def _enlace_exp(f: dict) -> str:
    texto = escape(f["expediente"])
    enlace = f'<a href="{escape(f["url"], quote=True)}">{texto}</a>' if f["url"] else texto
    return enlace + (f"<br><span class='secundario'>{escape(f['nombre'])}</span>" if f["nombre"] else "")


def html_vencimientos(lista: Lista, grupo: str | None = None, hoy: date | None = None) -> str:
    filas = filas_vencimientos(lista, grupo, hoy)
    if not filas:
        cuerpo = ["<p>Ningún expediente de la lista tiene fecha de caducidad conocida. Si todavía no se revisaron, "
                  "usá «Revisar novedades».</p>"]
    else:
        def faltan(n: int) -> str:
            return "venció" if n < 0 else "hoy" if n == 0 else "1 día" if n == 1 else f"{n} días"

        def clase(n: int) -> str:
            return "urgente" if n <= URGENTE_VENCE else "pronto" if n <= AVISO_VENCE else ""

        pronto = sum(1 for f in filas if 0 <= f["faltan"] <= AVISO_VENCE)
        cuerpo = [f"<p>{_cuantos(pronto, 'expediente caduca', 'expedientes caducan')} en los próximos "
                  f"{AVISO_VENCE} días.</p>" if pronto else
                  f"<p>Ninguno caduca en los próximos {AVISO_VENCE} días.</p>",
                  "<div class='tabla'><table><thead><tr><th>Expediente</th><th>Caduca</th><th>Falta</th>"
                  "<th>Situación</th></tr></thead><tbody>"]
        cuerpo += [f"<tr class='{clase(f['faltan'])}'><td>{_enlace_exp(f)}</td>"
                   f"<td class='fecha'>{fmt_fecha(f['caducidad'])}</td><td class='fecha'>{faltan(f['faltan'])}</td>"
                   f"<td>{escape(f['situacion'])}</td></tr>" for f in filas]
        cuerpo.append("</tbody></table></div>")
        sin = len(lista.del_grupo(grupo)) - len(filas)
        if sin:
            cuerpo.append(f"<p class='secundario'>{_cuantos(sin, 'expediente no tiene', 'expedientes no tienen')} "
                          "fecha de caducidad conocida (sin revisar, o ya sancionados o archivados).</p>")
    return _pagina("Vencimientos", cuerpo, lista, grupo,
                   ".urgente td{color:var(--lacre);font-weight:700}.pronto td{color:var(--lacre)}")


def html_agenda(lista: Lista, grupo: str | None = None, hoy: date | None = None) -> str:
    hoy = hoy or date.today()
    hasta = date.fromordinal(hoy.toordinal() + DIAS_AGENDA - 1)
    reuniones = filas_agenda(lista, grupo, hoy)
    semana = [r for r in reuniones if r["fecha"] and r["fecha"] <= hasta]
    despues = [r for r in reuniones if r not in semana]

    def reunion(r) -> str:
        """«Comisión de Salud» (los nombres vienen en mayúsculas del sitio)."""
        return f"Comisión de {nombre_comision(r['comision'])}" if r["comision"] else r["titulo"]

    def tabla(rs: list[dict]) -> str:
        def fila(r):
            titulo = escape(reunion(r))
            if r["url"]:
                titulo = f'<a href="{escape(r["url"], quote=True)}">{titulo}</a>'
            return (f"<tr><td class='fecha'>{escape(r['hora'] or '—')}</td><td>{titulo}</td>"
                    f"<td>{'<br>'.join(escape(x) for x in r['expedientes'])}</td></tr>")
        # Columnas de ancho fijo: así las tablas de los distintos días quedan alineadas.
        return ("<div class='tabla'><table class='agenda'><thead><tr><th>Hora</th><th>Reunión</th>"
                "<th>Expedientes de la lista</th></tr></thead><tbody>" + "".join(fila(r) for r in rs)
                + "</tbody></table></div>")

    cuerpo = [f"<p>Reuniones de comisión ya convocadas del {fmt_fecha(hoy)} al {fmt_fecha(hasta)} que tratan "
              "expedientes de la lista.</p>"]
    if not semana:
        cuerpo.append("<p>No hay reuniones convocadas esta semana con expedientes de la lista.</p>")
    dias: dict[date, list[dict]] = {}
    for r in semana:
        dias.setdefault(r["fecha"], []).append(r)
    for dia, rs in dias.items():
        cuerpo += [f"<h2>{_dia(dia)}</h2>", tabla(rs)]
    if despues:
        cuerpo.append("<h2>Más adelante</h2>")
        cuerpo.append("<ul>" + "".join(
            f"<li>{escape(fmt_fecha(r['fecha'], r['fecha_texto']))} · {escape(reunion(r))}: "
            f"{escape(', '.join(r['expedientes']))}</li>" for r in despues) + "</ul>")
    return _pagina("Agenda de la semana", cuerpo, lista, grupo,
                   "table.agenda{table-layout:fixed;width:100%}table.agenda th:nth-child(1){width:14%}"
                   "table.agenda th:nth-child(2){width:40%}")


def guardar_vista(lista: Lista, carpeta: Path, vista: str, grupo: str | None = None) -> Path:
    """Guarda «vencimientos» o «agenda» en HTML y devuelve el archivo."""
    titulo, generador = {"vencimientos": ("Vencimientos", html_vencimientos),
                         "agenda": ("Agenda de la semana", html_agenda)}[vista]
    base = nombre_archivo_seguro(f"{titulo}{' ' + grupo if grupo else ''} ({date.today():%Y-%m-%d})")
    destino = Path(carpeta) / f"{base}.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(generador(lista, grupo), encoding="utf-8")
    return destino


def escribir(res: ResultadoSeguimiento, opciones: OpcionesSeguimiento) -> dict[str, Path]:
    carpeta = Path(opciones.carpeta_salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    base = nombre_archivo_seguro(opciones.nombre_archivo or f"Seguimiento{' ' + res.grupo if res.grupo else ''} "
                                                            f"({res.generado:%Y-%m-%d})")
    for formato, generador in (("html", html), ("md", markdown)):
        if formato in opciones.formatos:
            destino = carpeta / f"{base}.{formato}"
            destino.write_text(generador(res), encoding="utf-8")
            res.archivos[formato] = destino
    if "pdf" in opciones.formatos:
        from .pdf import ErrorPDF, texto_a_pdf
        try:
            res.archivos["pdf"] = texto_a_pdf(html(res), carpeta / f"{base}.pdf")
        except ErrorPDF:
            pass                                       # el HTML y el Markdown ya quedaron guardados
    return res.archivos
