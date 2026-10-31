"""Senadores (autores) y bloques, para filtrar la búsqueda de expedientes.

- Los autores salen del selector «busqueda_proyectos[autor]» del buscador avanzado: un
  ID numérico por senador, actuales e históricos. Es el mismo ID de la página del
  senador (`/senadores/senador/{id}`) y de las actas de votación.
- Los bloques salen del listado «agrupados por bloques», que tiene solo a los senadores
  en funciones: el filtro por bloque usa la composición de hoy, no la de la fecha de
  cada proyecto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import config
from .cliente import Cliente
from .paginas import sopa, texto
from .util import limpiar, normalizar, titulo_es

URL_BLOQUES = config.BASE + "/senadores/listados/agrupados-por-bloques"
TTL_SENADORES = 86400


@dataclass(frozen=True)
class Senador:
    id: int
    nombre: str                    # APELLIDO, NOMBRES (como en el sitio)

    @property
    def legible(self) -> str:
        """«MENDOZA,SANDRA MARIELA» → «Mendoza, Sandra Mariela»."""
        apellido, _, nombres = self.nombre.partition(",")
        return titulo_es(limpiar(apellido)) + (f", {titulo_es(limpiar(nombres))}" if nombres.strip() else "")


def parsear_autores(html: str) -> list[Senador]:
    """Opciones del selector de autor del buscador avanzado."""
    m = re.search(r'<select[^>]*name="busqueda_proyectos\[autor\]".*?</select>', html or "", re.S)
    if not m:
        return []
    autores = []
    for valor, nombre in re.findall(r'<option value="(\d+)"[^>]*>([^<]*)', m.group(0)):
        nombre = limpiar(nombre)
        if nombre:
            autores.append(Senador(int(valor), nombre))
    return autores


def parsear_bloques(html: str) -> dict[str, list[Senador]]:
    """Listado de bloques actual: nombre del bloque → integrantes (con su ID)."""
    s = sopa(html)
    bloques: dict[str, list[Senador]] = {}
    for a in s.find_all("a", onclick=re.compile(r"ver\('?\w+'?\)")):
        nombre = texto(a)
        clave = re.search(r"ver\('?(\w+)'?\)", a["onclick"]).group(1)
        integrantes: list[Senador] = []
        for zona in (a.find_parent("tr"), s.find("tr", id=clave)):
            if zona is None:
                continue
            for enlace in zona.find_all("a", href=re.compile(r"/senadores/senador/\d+")):
                sid = int(re.search(r"/senador/(\d+)", enlace["href"]).group(1))
                titulo = limpiar((enlace.get("title") or "").replace("H.S.N.", ""))
                if titulo and all(sid != x.id for x in integrantes):
                    integrantes.append(Senador(sid, titulo))
        if nombre:
            bloques[nombre] = integrantes
    return bloques


def autores(cliente: Cliente) -> list[Senador]:
    return parsear_autores(cliente.get(config.URL_BUSCADOR, ttl=TTL_SENADORES).texto)


def bloques(cliente: Cliente) -> dict[str, list[Senador]]:
    return parsear_bloques(cliente.get(URL_BLOQUES, ttl=TTL_SENADORES).texto)


def con_integrantes(lista: list[Senador], todos: dict[str, list[Senador]]) -> list[Senador]:
    """Los autores del buscador más los senadores en funciones que el selector todavía no tiene (recién juran)."""
    ids = {s.id for s in lista}
    nuevos = [s for integrantes in todos.values() for s in integrantes if s.id not in ids]
    return sorted(lista + list({s.id: s for s in nuevos}.values()), key=lambda s: normalizar(s.nombre))


def _clave(nombre: str) -> str:
    return re.sub(r"[^A-Z ]", " ", normalizar(nombre)).split()


def buscar_senador(texto_buscado: str, lista: list[Senador]) -> list[Senador]:
    """Senadores que coinciden con un ID o con las palabras escritas («Mendoza», «mendoza sandra»)."""
    t = limpiar(texto_buscado)
    if t.isdigit():
        return [s for s in lista if s.id == int(t)]
    palabras = _clave(t)
    if not palabras:
        return []
    candidatos = [s for s in lista if all(p in _clave(s.nombre) for p in palabras)]
    exactos = [s for s in candidatos if normalizar(s.nombre).split(",")[0].strip() == " ".join(palabras)]
    return exactos or candidatos


def buscar_bloque(texto_buscado: str, todos: dict[str, list[Senador]]) -> str | None:
    """Nombre del bloque que coincide con lo escrito (sin distinguir tildes ni mayúsculas)."""
    n = normalizar(texto_buscado)
    exacto = next((b for b in todos if normalizar(b) == n), None)
    if exacto:
        return exacto
    parciales = [b for b in todos if n and n in normalizar(b)]
    return parciales[0] if len(parciales) == 1 else None


def carpeta_bloque(nombre: str) -> str:
    """«UCR - Unión Cívica Radical» → «ucr-union-civica-radical» (para publicar una página por bloque)."""
    return re.sub(r"[^a-z0-9]+", "-", normalizar(nombre).lower()).strip("-") or "bloque"


__all__ = ["carpeta_bloque", "Senador", "parsear_autores", "parsear_bloques", "autores", "bloques", "buscar_senador", "buscar_bloque"]
