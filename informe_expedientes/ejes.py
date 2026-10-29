"""Ejes temáticos: conjuntos de palabras clave guardados con un nombre.

Se guardan en ejes.json (carpeta de configuración del programa). Si el archivo
no existe se usan los ejes iniciales; desde la ventana se pueden agregar o
borrar ejes, y el archivo también se puede editar a mano.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import config


@dataclass
class Eje:
    nombre: str
    palabras: list[str]
    modo: str = "alguna"                 # alguna · todas
    excluir: list[str] = field(default_factory=list)
    comision_id: int | None = None


EJES_INICIALES: list[Eje] = [
    Eje("Educación y universidades", ["educación", "universidad", "universitario", "universitaria", "escuela",
                                      "docente"]),
    Eje("Salud", ["salud", "hospital", "medicamento", "enfermedad", "sanitario", "sanitaria"]),
    Eje("Ambiente", ["ambiente", "ambiental", "climático", "bosque", "glaciar", "residuos"]),
    Eje("Seguridad y justicia penal", ["código penal", "seguridad", "narcotráfico", "delito", "penal"],
        excluir=["seguridad social", "seguridad alimentaria", "seguridad vial"]),
    Eje("Economía y finanzas públicas", ["presupuesto", "impuesto", "tributario", "tributaria", "deuda pública",
                                         "coparticipación"]),
    Eje("Trabajo y previsión social", ["trabajo", "laboral", "jubilación", "jubilaciones", "previsional", "empleo",
                                       "seguridad social"]),
    Eje("Género", ["género", "mujeres", "violencia contra las mujeres", "igualdad"]),
    Eje("Niñez y adolescencia", ["niñez", "niñas", "niños", "adolescentes", "infancia"]),
    Eje("Energía y minería", ["energía", "minería", "minero", "hidrocarburos", "litio", "combustibles"]),
    Eje("Discapacidad", ["discapacidad"]),
    Eje("Consumo", ["consumidor", "consumidores", "consumo"],
        excluir=["consumo problemático", "consumo de sustancias", "consumo de alcohol"]),
    Eje("Transferencia de inmuebles", ["transfiere", "inmueble"], modo="todas"),
]


def archivo_ejes() -> Path:
    return config.carpeta_app() / "ejes.json"


def _copia_inicial() -> list[Eje]:
    return [Eje(**asdict(e)) for e in EJES_INICIALES]


def cargar_ejes(archivo: Path | None = None) -> list[Eje]:
    archivo = Path(archivo) if archivo else archivo_ejes()
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _copia_inicial()
    validos = {f.name for f in fields(Eje)}
    ejes = []
    for e in datos.get("ejes", []):
        if isinstance(e, dict) and e.get("nombre") and isinstance(e.get("palabras", []), list):
            ejes.append(Eje(**{k: v for k, v in e.items() if k in validos}))
    return ejes or _copia_inicial()


def guardar_ejes(ejes: list[Eje], archivo: Path | None = None) -> None:
    archivo = Path(archivo) if archivo else archivo_ejes()
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps({"ejes": [asdict(e) for e in ejes]}, ensure_ascii=False, indent=2),
                       encoding="utf-8")


def buscar_eje(nombre: str, ejes: list[Eje]) -> Eje | None:
    from .util import normalizar
    objetivo = normalizar(nombre)
    return next((e for e in ejes if normalizar(e.nombre) == objetivo), None)
