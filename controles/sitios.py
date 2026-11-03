"""Control diario de los sitios del Senado y de Diputados.

Las pruebas usan páginas guardadas (tests/fixtures): si un sitio cambia, siguen en verde aunque el programa
deje de leerlo. Este control consulta en vivo unos casos conocidos y estables y comprueba que se sigan leyendo
los datos básicos. Lo corre el workflow «Control de sitios» todos los días hábiles; si algo falla, abre un issue.

    python controles/sitios.py

Sale con código 1 si algún control falla, y escribe el detalle en Markdown en la salida estándar.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from informe_expedientes import asuntos_entrados, busqueda, hcdn  # noqa: E402
from informe_expedientes.cliente import Cliente  # noqa: E402
from informe_expedientes.identificador import parsear  # noqa: E402
from informe_expedientes.servicio import Opciones, generar  # noqa: E402


def _ficha(cliente: Cliente, numero: str) -> list[str]:
    """La ficha del Senado de un expediente cerrado: tiene que traer extracto, giros, tipo y situación, y los
    autores si es del Senado (los que vienen de Diputados no los traen en la ficha)."""
    r = generar(numero, Opciones(buscar_reuniones=False, buscar_agenda=False, buscar_relacionados=False,
                                 contrastar_diputados=False, formatos=()), cliente, escribir=False)
    f = r.ficha
    faltan = [que for que, hay in [("extracto", f.extracto), ("giros", f.giros), ("tipo", f.tipo_texto)]
              if not hay]
    if numero.startswith("S-") and not f.autores:
        faltan.append("autores")
    if r.situacion.nivel == "desconocido":
        faltan.append("situación")
    return [f"{numero}: la ficha del Senado ya no trae {', '.join(faltan)}"] if faltan else []


def _diputados(cliente: Cliente, numero: str) -> list[str]:
    """El buscador de Diputados tiene que encontrar el proyecto y su trámite."""
    p = hcdn.buscar(cliente, parsear(numero))
    if p is None:
        return [f"{numero}: el sitio de Diputados ya no lo encuentra"]
    faltan = [que for que, hay in [("número de Diputados", p.expediente_diputados), ("trámite", p.tramite)]
              if not hay]
    return [f"{numero}: el sitio de Diputados ya no trae {', '.join(faltan)}"] if faltan else []


def _dae(cliente: Cliente, numero: int, anio: int) -> list[str]:
    """Un Diario de Asuntos Entrados ya publicado tiene que seguir trayendo asuntos con expediente y extracto."""
    asuntos = asuntos_entrados.bajar_dae(cliente, numero, anio)
    if not asuntos:
        return [f"DAE {numero}/{anio}: no se leyó ningún asunto"]
    if not all(a.expediente and a.extracto for a in asuntos):
        return [f"DAE {numero}/{anio}: hay asuntos sin expediente o sin extracto"]
    return []


def _buscador(cliente: Cliente) -> list[str]:
    """El buscador de proyectos del Senado tiene que devolver resultados para una palabra común."""
    hallazgos, _ = busqueda.buscar(cliente, busqueda.Consulta(palabras=["salud"], anio_desde=2025, anio_hasta=2025))
    return [] if hallazgos else ["Buscador del Senado: «salud» en 2025 no devolvió resultados"]


CONTROLES = [
    ("Ficha del Senado (S-351/25)", lambda c: _ficha(c, "S-351/25")),
    ("Ficha del Senado (CD-14/24)", lambda c: _ficha(c, "CD-14/24")),
    ("Sitio de Diputados (CD-14/24)", lambda c: _diputados(c, "CD-14/24")),
    ("Asuntos entrados (DAE 111/2025)", lambda c: _dae(c, 111, 2025)),
    ("Buscador de proyectos", _buscador),
]


def main() -> int:
    cliente = Cliente(usar_cache=False)
    fallas = 0
    print("| Control | Resultado |\n|---|---|")
    for nombre, control in CONTROLES:
        try:
            problemas = control(cliente)
        except Exception as e:  # noqa: BLE001 — cualquier error es una falla del control
            problemas = [f"error: {type(e).__name__}: {e}"]
            traceback.print_exc(file=sys.stderr)
        fallas += bool(problemas)
        print(f"| {nombre} | {'✅ bien' if not problemas else '❌ ' + '<br>'.join(problemas)} |")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
