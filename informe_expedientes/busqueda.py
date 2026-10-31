"""Búsqueda de expedientes por palabras clave, eje temático y filtros.

1. Se consulta la búsqueda avanzada del Senado (por extracto) una vez por año y
   por palabra; para cada consulta se descarga la exportación XLS, que trae el
   resultado completo (la página web lo muestra de a 10).
2. Sobre lo recibido se aplica un filtro propio que no distingue tildes ni
   mayúsculas: palabras (alguna o todas), exclusiones, años, origen y tipo.
   Cada palabra se busca como comienzo de palabra: «universidad» encuentra
   también «universidades».
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field
from datetime import date

from . import config
from .cliente import Cliente, ErrorRed
from .comisiones import actualizar_mapa_comisiones
from .identificador import IdExpediente
from .paginas import celdas, sopa
from .util import anio_cuatro_digitos, limpiar, nombre_comision, normalizar, sin_acentos

TIPOS_PRINCIPALES = ("PL", "PR", "PC", "PD")
OTROS = "OTROS"
_RE_TOKEN = re.compile(
    r'name="busqueda_proyectos\[_token\]"[^>]*value="([^"]+)"'
    r'|value="([^"]+)"[^>]*name="busqueda_proyectos\[_token\]"'
)
_CAMPOS = ["autor", "palabra", "opcion", "palabra2", "comision", "tipoDocumento", "expedienteLugar",
           "expedienteNumeroPre", "expedienteNumeroPos", "expedienteTipo"]
COLUMNAS_XLS = ["NUMERO EXPEDIENTE", "TIPO", "ORIGEN", "EXTRACTO"]


class ErrorBusqueda(Exception):
    """La búsqueda del sitio no devolvió resultados legibles."""


def separar_palabras(texto: str) -> list[str]:
    vistas, salida = set(), []
    for p in re.split(r"[,;\n]+", texto or ""):
        p = limpiar(p)
        if p and normalizar(p) not in vistas:
            vistas.add(normalizar(p))
            salida.append(p)
    return salida


@dataclass
class Consulta:
    palabras: list[str] = field(default_factory=list)
    modo: str = "alguna"                       # alguna · todas
    excluir: list[str] = field(default_factory=list)
    anio_desde: int = field(default_factory=lambda: date.today().year - 1)
    anio_hasta: int = field(default_factory=lambda: date.today().year)
    origen: str | None = None
    tipos: set[str] | None = None              # None = todos; OTROS = los no principales
    comision_id: int | None = None
    eje: str | None = None
    autores: list = field(default_factory=list)  # senadores.Senador: proyectos con su firma
    bloque: str | None = None                  # si los autores son los integrantes actuales de un bloque

    def quien(self) -> str:
        """«Bloque Justicialista» · «Mendoza, Sandra Mariela» · «3 senadores»."""
        if self.bloque:
            return f"Bloque {self.bloque}"
        if len(self.autores) == 1:
            return self.autores[0].legible
        if self.autores:
            return f"{len(self.autores)} senadores"
        return ""

    def titulo(self) -> str:
        if self.eje:
            base = self.eje
        elif self.palabras:
            base = ", ".join(self.palabras)
        elif self.comision_id:
            base = f"Comisión de {nombre_comision(config.COMISIONES.get(self.comision_id, str(self.comision_id)))}"
        else:
            base = ""
        if self.quien():
            return f"{base} — {self.quien()}" if base else self.quien()
        return base or "Búsqueda de expedientes"

    def criterios(self) -> list[tuple[str, str]]:
        filas = []
        if self.eje:
            filas.append(("Eje temático", self.eje))
        if self.palabras:
            unidas = ", ".join(self.palabras)
            filas.append(("Palabras clave", unidas + (" (todas)" if self.modo == "todas" and len(self.palabras) > 1
                                                      else " (alguna)" if len(self.palabras) > 1 else "")))
        if self.excluir:
            filas.append(("Se excluyen", ", ".join(self.excluir)))
        filas.append(("Años de los expedientes", str(self.anio_desde) if self.anio_desde == self.anio_hasta
                      else f"{self.anio_desde} a {self.anio_hasta}"))
        filas.append(("Origen", config.ORIGENES.get(self.origen, "Todos") if self.origen else "Todos"))
        if self.tipos is None:
            filas.append(("Tipos", "Todos"))
        else:
            nombres = [config.TIPOS[t].lower() if t != OTROS else "otros tipos" for t in sorted(self.tipos)]
            filas.append(("Tipos", ", ".join(nombres).capitalize()))
        if self.comision_id:
            filas.append(("Comisión del giro",
                          nombre_comision(config.COMISIONES.get(self.comision_id, str(self.comision_id)))))
        if self.bloque:
            filas.append(("Bloque", f"{self.bloque}: proyectos con la firma de alguno de sus integrantes actuales ("
                                    + "; ".join(s.legible for s in self.autores) + ")"))
        elif self.autores:
            filas.append(("Autor" if len(self.autores) == 1 else "Autores",
                          "; ".join(s.legible for s in self.autores) + " (como autor o coautor)"))
        return filas


@dataclass
class Hallazgo:
    ident: IdExpediente
    extracto: str
    coincidencias: list[str] = field(default_factory=list)


def _patron(palabra: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Z0-9]){re.escape(normalizar(palabra))}")


def coincidencias(extracto: str, palabras: list[str]) -> list[str]:
    texto = normalizar(extracto)
    return [p for p in palabras if _patron(p).search(texto)]


def tipo_admitido(tipo: str | None, tipos: set[str] | None) -> bool:
    if tipos is None:
        return True
    if tipo in TIPOS_PRINCIPALES:
        return tipo in tipos
    return OTROS in tipos or (tipo in tipos)


def cumple(h: Hallazgo, c: Consulta) -> bool:
    i = h.ident
    if not c.anio_desde <= i.anio <= c.anio_hasta:
        return False
    if c.origen and i.origen != c.origen:
        return False
    if not tipo_admitido(i.tipo, c.tipos):
        return False
    if c.excluir and coincidencias(h.extracto, c.excluir):
        return False
    if c.palabras:
        h.coincidencias = coincidencias(h.extracto, c.palabras)
        if c.modo == "todas":
            return len(h.coincidencias) == len(c.palabras)
        return bool(h.coincidencias)
    return True


def planificar(c: Consulta) -> list[tuple[str, int, int | None]]:
    """Consultas al sitio: (palabra, año, autor). Con «todas» basta la palabra más larga.

    Con autores se pide una consulta por autor y año, sin palabra: las palabras se filtran
    después sobre el extracto (son muchas menos consultas que palabra × autor × año).
    """
    if c.autores:
        return [("", anio, s.id) for s in c.autores for anio in range(c.anio_desde, c.anio_hasta + 1)]
    if c.palabras:
        terminos = list(c.palabras) if c.modo == "alguna" else [max(c.palabras, key=len)]
    else:
        terminos = [""]
    variantes: list[str] = []
    for t in terminos:
        for v in (t, sin_acentos(t)):          # el sitio puede no igualar tildes
            if v not in variantes:
                variantes.append(v)
    return [(v, anio, None) for anio in range(c.anio_desde, c.anio_hasta + 1) for v in variantes]


class Buscador:
    """Usa la búsqueda avanzada del sitio. Todo en el mismo hilo: el resultado queda en la sesión."""

    def __init__(self, cliente: Cliente):
        self.cliente = cliente
        self.token: str | None = None

    def _pedir_token(self) -> str:
        self.cliente.sesion_nueva()
        r = self.cliente.get(config.URL_BUSCADOR)
        m = _RE_TOKEN.search(r.texto)
        if not m:
            raise ErrorBusqueda("El buscador del Senado cambió: no se encontró el formulario.")
        actualizar_mapa_comisiones(r.texto)
        return m.group(1) or m.group(2)

    def consultar(self, palabra: str, anio: int, c: Consulta, autor: int | None = None) -> list[dict]:
        unico_tipo = ""
        if c.tipos and len(c.tipos) == 1 and next(iter(c.tipos)) in TIPOS_PRINCIPALES:
            unico_tipo = next(iter(c.tipos))
        datos = {f"busqueda_proyectos[{k}]": "" for k in _CAMPOS}
        datos.update({
            "busqueda_proyectos[palabra]": palabra,
            "busqueda_proyectos[opcion]": "Y",
            "busqueda_proyectos[tipoDocumento]": "EX" if palabra else "",
            "busqueda_proyectos[comision]": str(c.comision_id or ""),
            "busqueda_proyectos[expedienteLugar]": c.origen or "",
            "busqueda_proyectos[expedienteNumeroPos]": str(anio),
            "busqueda_proyectos[expedienteTipo]": unico_tipo,
            "busqueda_proyectos[autor]": str(autor or ""),
        })
        ultimo_error = None
        for _intento in range(2):
            if not self.token:
                self.token = self._pedir_token()
            datos["busqueda_proyectos[_token]"] = self.token
            pagina = self.cliente.post(config.URL_AVANZADA, datos)
            try:
                return self._xls()
            except ErrorBusqueda as e:
                ultimo_error = e
                filas = filas_html(pagina.texto)
                if filas is not None:
                    return filas
                self.token = None          # token vencido: se pide otro y se reintenta
        raise ultimo_error or ErrorBusqueda("La búsqueda no devolvió resultados legibles.")

    def _xls(self) -> list[dict]:
        if importlib.util.find_spec("xlrd") is None:
            raise ErrorBusqueda("Falta la biblioteca xlrd para leer la exportación del Senado.")
        try:
            r = self.cliente.get(config.URL_XLS_AVANZADA, binario=True)
        except ErrorRed as e:
            raise ErrorBusqueda(str(e)) from e
        return filas_xls(r.contenido or b"")


def filas_xls(contenido: bytes) -> list[dict]:
    import xlrd
    try:
        libro = xlrd.open_workbook(file_contents=contenido, ignore_workbook_corruption=True)
    except Exception as e:  # noqa: BLE001 - formato inesperado
        raise ErrorBusqueda(f"La exportación del Senado no es un XLS legible ({type(e).__name__}).") from e
    hoja = libro.sheet_by_index(0)
    if hoja.nrows < 1:
        return []
    encabezado = [normalizar(str(hoja.cell_value(0, c))) for c in range(hoja.ncols)]
    if encabezado[:4] != COLUMNAS_XLS:
        raise ErrorBusqueda(f"Cambiaron las columnas de la exportación del Senado: {encabezado}")
    filas = []
    for f in range(1, hoja.nrows):
        valores = [limpiar(str(hoja.cell_value(f, c))) for c in range(4)]
        if valores[0]:
            filas.append({"expediente": valores[0], "tipo": valores[1], "origen": valores[2], "extracto": valores[3]})
    return filas


def filas_html(html: str) -> list[dict] | None:
    """Respaldo: lee la primera página de resultados (hasta 10 filas)."""
    s = sopa(html)
    for tabla in s.find_all("table"):
        encabezado = [normalizar(th.get_text(" ")) for th in tabla.find_all("th")]
        if not encabezado or not any(h.startswith("EXP") for h in encabezado):
            continue
        idx = {h.split(" ")[0]: i for i, h in enumerate(encabezado)}
        filas = []
        for tr in tabla.find_all("tr"):
            v = celdas(tr)
            if len(v) < 4 or not re.match(r"^\d+\s*/\s*\d{2,4}$", v[0]):
                continue
            filas.append({"expediente": v[idx.get("EXP", 0)], "tipo": v[idx.get("TIPO", 1)],
                          "origen": v[idx.get("ORIGEN", 2)], "extracto": v[idx.get("EXTRACTO", 3)]})
        return filas
    return None


def a_hallazgo(fila: dict) -> Hallazgo | None:
    m = re.match(r"^0*(\d+)\s*/\s*(\d{2,4})$", fila.get("expediente", ""))
    origen = (fila.get("origen") or "").upper()
    tipo = (fila.get("tipo") or "").upper() or None
    if not m or origen not in config.ORIGENES:
        return None
    if tipo and tipo not in config.TIPOS:
        tipo = config.TIPO_POR_NOMBRE.get(normalizar(tipo))
    ident = IdExpediente(int(m.group(1)), anio_cuatro_digitos(m.group(2)), origen, tipo)
    return Hallazgo(ident, fila.get("extracto", ""))


def buscar(cliente: Cliente, c: Consulta, avisar=None) -> tuple[list[Hallazgo], dict]:
    avisar = avisar or (lambda *a, **k: None)
    plan = planificar(c)
    buscador = Buscador(cliente)
    vistos: dict[tuple, Hallazgo] = {}
    filas_recibidas = 0
    nombres = {s.id: s.legible for s in c.autores}
    for i, (palabra, anio, autor) in enumerate(plan, 1):
        cliente.verificar_cancelacion()
        avisar("progreso", actual=i - 1, total=len(plan))
        etiqueta = f"«{palabra}»" if palabra else (nombres.get(autor, str(autor)) if autor else "todos")
        filas = buscador.consultar(palabra, anio, c, autor)
        filas_recibidas += len(filas)
        avisar("log", f"Búsqueda {etiqueta} en {anio}: {len(filas)} resultados del sitio.")
        for fila in filas:
            h = a_hallazgo(fila)
            if h:
                vistos.setdefault((h.ident.numero, h.ident.anio, h.ident.origen), h)
    avisar("progreso", actual=len(plan), total=len(plan))
    seleccion = [h for h in vistos.values() if cumple(h, c)]
    seleccion.sort(key=lambda h: (-h.ident.anio, h.ident.origen, -h.ident.numero))
    return seleccion, {"consultas": len(plan), "filas_recibidas": filas_recibidas, "distintos": len(vistos),
                       "descartados": len(vistos) - len(seleccion)}
