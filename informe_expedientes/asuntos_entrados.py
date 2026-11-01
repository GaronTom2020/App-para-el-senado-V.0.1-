"""Asuntos entrados: los expedientes que ingresaron desde la última revisión.

Fuente: el Diario de Asuntos Entrados (DAE) digital del Senado. Cada DAE está numerado por año
(«84/2026») y trae, por asunto, la fecha de Mesa de Entradas, el expediente, los giros a comisiones
y el extracto. La página principal muestra el último DAE y la lista de los anteriores; cada uno se
pide con un POST a «DAEDIGITAL/Resultado».

La primera vez se indica una fecha de partida: se recorren los DAE hacia atrás hasta pasar esa
fecha, pasando a los períodos anteriores si hace falta. Después, cada revisión trae solo los DAE nuevos desde el último registrado. El
estado se guarda en `asuntos_entrados.json`, en la carpeta de configuración del programa.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import config
from .cliente import Cliente
from .identificador import IdExpediente
from .paginas import sopa
from .util import anio_cuatro_digitos, limpiar, parsear_fecha, titulo_es

URL_DAE = config.BASE + "/parlamentario/DAEDIGITAL/"
URL_RESULTADO = URL_DAE + "Resultado"
MAX_DAE = 60                     # tope por revisión (unos 1200 asuntos)
_RE_EXPEDIENTE = re.compile(r"^\s*([A-Z]{1,4})\s*-\s*(\d{1,5})\s*/\s*(\d{2,4})\s*-\s*([A-Z0-9]{2})\s*$")
_RE_DAE = re.compile(r"(\d{1,3})\s*/\s*(\d{4})")


@dataclass
class Asunto:
    fecha: str                   # ISO, fecha de Mesa de Entradas
    dae: str                     # «84/2026»
    expediente: str              # «S-1856/26»
    origen: str
    tipo: str
    giros: list[str] = field(default_factory=list)
    extracto: str = ""
    url_texto: str | None = None

    @property
    def ident(self) -> IdExpediente:
        numero, anio = self.expediente.split("-", 1)[1].split("/")
        return IdExpediente(int(numero), anio_cuatro_digitos(anio), self.origen, self.tipo)

    @property
    def fecha_d(self) -> date | None:
        try:
            return date.fromisoformat(self.fecha)
        except ValueError:
            return None

    @property
    def url_ficha(self) -> str:
        return self.ident.url_ficha()


# =================================================================== lectura

def ultimos(html: str) -> list[tuple[int, int]]:
    """Los DAE de tipo normal que lista la página principal, del más nuevo al más viejo."""
    lista = sopa(html).find("select", attrs={"name": "ultimosnormal"})
    salida = []
    for opcion in lista.find_all("option") if lista else []:
        m = _RE_DAE.search(opcion.get("value") or "")
        if m:
            salida.append((int(m.group(1)), int(m.group(2))))
    return salida


def leer_dae(html: str) -> list[Asunto]:
    """Asuntos de un DAE: la tabla «Fecha de Mesa de Entradas · Número/Año Dae · Expediente · Giros · Extracto»."""
    asuntos = []
    for fila in sopa(html).find_all("tr"):
        celdas = fila.find_all("td")
        if len(celdas) < 5:
            continue
        textos = [limpiar(c.get_text(" ")) for c in celdas]
        fecha = parsear_fecha(textos[0])
        m = _RE_EXPEDIENTE.match(textos[2])
        dae = _RE_DAE.search(textos[1])
        if not (fecha and m and dae):
            continue
        origen, numero, anio, tipo = m.groups()
        giros = [titulo_es(g.strip(" -")) for g in textos[3].split(" - ") if g.strip(" -")]
        giros = list(dict.fromkeys(re.sub(r"^De ", "", g) for g in giros))
        enlace = fila.find("a", href=True)
        url = enlace["href"].split("?")[0] if enlace else None
        if url and not url.startswith("http"):
            url = config.BASE + url
        asuntos.append(Asunto(fecha.isoformat(), f"{dae.group(1)}/{dae.group(2)}",
                              f"{origen}-{int(numero)}/{anio_cuatro_digitos(anio) % 100:02d}", origen, tipo,
                              giros, textos[4], url))
    return asuntos


def bajar_dae(cliente: Cliente, numero: int, anio: int) -> list[Asunto]:
    datos = {"dae_buscar[numero]": str(numero), "dae_buscar[anios]": str(anio), "dae_buscar[tipo]": "1",
             "ultimosnormal": "", "ultimosacuerdos": ""}
    return leer_dae(cliente.post(URL_RESULTADO, datos).texto)


# ================================================================= registro

def archivo_por_defecto() -> Path:
    return config.carpeta_app() / "asuntos_entrados.json"


@dataclass
class Registro:
    archivo: Path
    desde: str | None = None                   # fecha de partida (ISO), la primera vez
    ultimo_dae: tuple[int, int] | None = None   # último DAE revisado: (84, 2026)
    revisado: str | None = None                # fecha y hora de la última revisión
    ultimos_asuntos: list[Asunto] = field(default_factory=list)

    @classmethod
    def cargar(cls, archivo: Path | None = None) -> "Registro":
        archivo = Path(archivo) if archivo else archivo_por_defecto()
        r = cls(archivo)
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
            r.desde, r.revisado = datos.get("desde"), datos.get("revisado")
            r.ultimo_dae = tuple(datos["ultimo_dae"]) if datos.get("ultimo_dae") else None
            r.ultimos_asuntos = [Asunto(**a) for a in datos.get("ultimos_asuntos", [])]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return r

    @property
    def iniciado(self) -> bool:
        return self.ultimo_dae is not None

    def guardar(self) -> None:
        datos = {"desde": self.desde, "ultimo_dae": list(self.ultimo_dae) if self.ultimo_dae else None,
                 "revisado": self.revisado, "ultimos_asuntos": [asdict(a) for a in self.ultimos_asuntos]}
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.archivo.with_suffix(".tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporal, self.archivo)


@dataclass
class ResultadoAsuntos:
    asuntos: list[Asunto]
    daes: list[str]
    desde: str | None = None
    advertencias: list[str] = field(default_factory=list)
    generado: datetime = field(default_factory=datetime.now)
    archivos: dict = field(default_factory=dict)


def _nada(*_a, **_k):
    return None


def ultimo_de(cliente: Cliente, anio: int) -> int:
    """Último DAE de un período ya cerrado: se prueban números (un DAE que no existe viene sin registros)."""
    def existe(numero: int) -> bool:
        return bool(bajar_dae(cliente, numero, anio))

    if not existe(1):
        return 0
    bajo, alto = 1, 64
    while existe(alto):                     # 64, 128, 256…: hasta dar con uno que no existe
        bajo, alto = alto, alto * 2
        if alto > 4096:
            return bajo
    while alto - bajo > 1:                  # búsqueda binaria entre el último que existe y el primero que no
        medio = (bajo + alto) // 2
        if existe(medio):
            bajo = medio
        else:
            alto = medio
    return bajo


def revisar(cliente: Cliente, registro: Registro, desde: date | None = None, avisar=_nada,
            hoy: date | None = None) -> ResultadoAsuntos:
    """Trae los asuntos de los DAE nuevos. La primera vez hace falta `desde` (fecha de partida).

    Los DAE se numeran por período parlamentario (de marzo a febrero), no por año calendario: el 111/2025
    trae asuntos de febrero de 2026. Por eso, al terminar los DAE de un período, se sigue con el anterior,
    desde su último número.
    """
    if not registro.iniciado and desde is None:
        raise ValueError("La primera vez indicá desde qué fecha buscar.")
    avisar("etapa", "Leyendo el último Diario de Asuntos Entrados…")
    portada = cliente.get(URL_DAE, ttl=0).texto
    disponibles = ultimos(portada)
    if not disponibles:
        raise ValueError("El sitio del Senado no muestra la lista de Diarios de Asuntos Entrados.")
    ultimo = disponibles[0]
    limite = registro.ultimo_dae            # en las revisiones siguientes: hasta el último ya revisado
    advertencias: list[str] = []
    asuntos: list[Asunto] = []
    leidos: list[str] = []
    numero, anio = ultimo
    while True:
        if limite and (anio, numero) <= (limite[1], limite[0]):
            break
        if len(leidos) >= MAX_DAE:
            advertencias.append(f"Se leyeron {MAX_DAE} DAE (el tope por revisión): volvé a revisar para traer "
                                "los anteriores.")
            break
        avisar("etapa", f"Leyendo el DAE {numero}/{anio}…")
        cliente.verificar_cancelacion()
        lote = leer_dae(portada) if (numero, anio) == ultimo else bajar_dae(cliente, numero, anio)
        leidos.append(f"{numero}/{anio}")
        if limite:
            asuntos += lote
        else:
            asuntos += [a for a in lote if a.fecha_d and a.fecha_d >= desde]
            if lote and all(a.fecha_d and a.fecha_d < desde for a in lote):
                break                       # este DAE ya es anterior a la fecha de partida
        numero -= 1
        if numero < 1:                      # se terminó el período: sigue el anterior
            anio -= 1
            if limite is None and anio < desde.year - 1:
                break
            avisar("etapa", f"Buscando el último DAE de {anio}…")
            numero = ultimo_de(cliente, anio)
            if numero < 1:
                break

    asuntos.sort(key=lambda a: (a.fecha, a.origen, a.ident.numero), reverse=True)
    registro.ultimo_dae = ultimo
    registro.revisado = datetime.now().isoformat(timespec="minutes")
    if desde and not registro.desde:
        registro.desde = desde.isoformat()
    registro.ultimos_asuntos = asuntos
    registro.guardar()
    return ResultadoAsuntos(asuntos, leidos, registro.desde, advertencias)


# =================================================================== filtros

TIPOS = {"PL": "Ley", "PR": "Resolución", "PC": "Comunicación", "PD": "Declaración"}


def filtrar(asuntos: list[Asunto], tipos: set[str] | None = None, origen: str | None = None,
            texto: str = "") -> list[Asunto]:
    """`tipos`: códigos PL/PR/PC/PD y «OTROS» para el resto; None = todos."""
    from .util import normalizar
    palabras = [normalizar(p) for p in texto.split() if p.strip()]
    salida = []
    for a in asuntos:
        clave = a.tipo if a.tipo in TIPOS else "OTROS"
        if tipos is not None and clave not in tipos:
            continue
        if origen and a.origen != origen:
            continue
        if palabras and not all(p in normalizar(a.extracto + " " + " ".join(a.giros)) for p in palabras):
            continue
        salida.append(a)
    return salida


def resumen(res: ResultadoAsuntos, mostrados: int | None = None) -> str:
    from .numeros import cantidad
    n = len(res.asuntos)
    if not res.daes:
        return "No hay Diarios de Asuntos Entrados nuevos desde la última revisión."
    daes = res.daes[-1] + (f" a {res.daes[0]}" if len(res.daes) > 1 else "")
    texto = (f"{cantidad(n, 'asunto entrado', 'asuntos entrados')} nuevo{'s' if n != 1 else ''} "
             f"(DAE {daes})." if n else f"Sin asuntos nuevos (DAE {daes}).")
    if mostrados is not None and mostrados != n:
        texto += f" Con los filtros elegidos se muestran {mostrados}."
    return texto


__all__ = ["Asunto", "Registro", "ResultadoAsuntos", "revisar", "filtrar", "leer_dae", "ultimos", "bajar_dae",
           "resumen", "TIPOS"]
