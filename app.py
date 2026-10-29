"""Informe de Expedientes del H. Senado de la Nación.

Sin argumentos abre la ventana. Con argumentos funciona por línea de comandos:

    Un expediente o varios:
        python app.py S-351/25 CD-35/23 --salida "C:/Informes"

    Informe temático (por eje guardado o por palabras):
        python app.py --tema "Salud" --anios 2025-2026
        python app.py --palabras "litio, minería" --tipos PL,PC --comision "Minería"
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from informe_expedientes import __version__, config
from informe_expedientes.cliente import Cancelado, Cliente
from informe_expedientes.servicio import Opciones, generar


def _anios(texto: str) -> tuple[int, int]:
    partes = [int(p) for p in texto.replace(" ", "").split("-") if p]
    if len(partes) == 1:
        return partes[0], partes[0]
    if len(partes) == 2 and partes[0] <= partes[1]:
        return partes[0], partes[1]
    raise argparse.ArgumentTypeError("usá un año (2026) o un rango (2025-2026)")


def linea_de_comandos(argumentos: list[str]) -> int:
    hoy = date.today().year
    p = argparse.ArgumentParser(prog="InformeExpediente",
                                description="Genera informes de expedientes del H. Senado de la Nación.")
    p.add_argument("expedientes", nargs="*", help="Ej.: S-1234/24 CD-14/24 PE-107/24 (o enlaces a la ficha)")
    p.add_argument("--tipo", help="Tipo del expediente si se conoce: PL, PD, PR, PC…")
    p.add_argument("--salida", type=Path, default=config.carpeta_informes_por_defecto(), help="Carpeta de destino")
    p.add_argument("--formatos", help="docx, html y/o xlsx separados por coma")
    p.add_argument("--nombre", help="Nombre fijo del archivo, sin fecha (p. ej. index para publicar)")
    p.add_argument("--sin-reuniones", action="store_true", help="No buscar reuniones de comisión")
    p.add_argument("--sin-asesores", action="store_true", help="Excluir reuniones de asesores")
    p.add_argument("--sin-agenda", action="store_true", help="No revisar reuniones convocadas")
    p.add_argument("--sin-cache", action="store_true", help="Descargar todo de nuevo")
    p.add_argument("--diagnostico", type=Path, help="Guardar las páginas descargadas en esta carpeta")
    t = p.add_argument_group("informe temático")
    t.add_argument("--tema", help="Nombre de un eje temático guardado")
    t.add_argument("--palabras", help="Palabras clave separadas por coma")
    t.add_argument("--todas", action="store_true", help="Exigir todas las palabras (por defecto, alguna)")
    t.add_argument("--excluir", help="Descartar los que mencionen estas palabras")
    t.add_argument("--anios", type=_anios, default=(hoy - 1, hoy), help="Año o rango, p. ej. 2025-2026")
    t.add_argument("--origen", choices=list(config.ORIGENES), help="Solo un origen (S, CD, PE…)")
    t.add_argument("--tipos", default="PL,PR,PC", help="Tipos separados por coma (PL,PR,PC,PD,OTROS) o TODOS")
    t.add_argument("--comision", help="Comisión del giro: número o nombre")
    t.add_argument("--sin-detalle", action="store_true", help="No consultar la ficha de cada expediente")
    t.add_argument("--con-reuniones", action="store_true", help="Buscar también las reuniones de cada uno")
    t.add_argument("--individuales", action="store_true", help="Generar además el informe completo de cada uno")
    t.add_argument("--limite", type=int, default=200, help="Máximo de fichas a consultar (200)")
    t.add_argument("--ejes", type=Path, help="Archivo de ejes temáticos a usar (JSON)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    a = p.parse_args(argumentos)

    tematico = bool(a.tema or a.palabras or a.comision)
    if not tematico and not a.expedientes:
        p.error("indicá uno o más expedientes, o --tema / --palabras / --comision")

    cliente = Cliente(carpeta_cache=config.carpeta_app() / "cache", usar_cache=not a.sin_cache,
                      carpeta_diagnostico=a.diagnostico)

    def avisar(evento, mensaje="", **_datos):
        if evento in ("etapa", "log"):
            print(mensaje, flush=True)
        elif evento == "advertencia":
            print(f"Aviso: {mensaje}", flush=True)

    if tematico:
        return _tematico(a, cliente, avisar)

    formatos = tuple(f.strip().lower() for f in (a.formatos or "docx,html").split(",") if f.strip())
    opciones = Opciones(
        tipo=a.tipo.upper() if a.tipo else None, buscar_reuniones=not a.sin_reuniones,
        incluir_asesores=not a.sin_asesores, buscar_agenda=not a.sin_agenda, formatos=formatos,
        carpeta_salida=a.salida, nombre_archivo=a.nombre if len(a.expedientes) == 1 else None,
    )
    errores = 0
    for texto in a.expedientes:
        try:
            r = generar(texto, opciones, cliente, avisar)
            print(f"\n{r.ficha.id.corto}: {r.situacion.titulo}\nReuniones encontradas: {len(r.reuniones)}")
            for ruta in r.archivos.values():
                print(f"  {ruta}")
            print()
        except Cancelado:
            return 130
        except Exception as e:  # noqa: BLE001
            errores += 1
            print(f"Error con {texto}: {e}", file=sys.stderr)
    return 1 if errores else 0


def _tematico(a, cliente: Cliente, avisar) -> int:
    from informe_expedientes.busqueda import OTROS, Consulta, separar_palabras
    from informe_expedientes.comisiones import id_comision
    from informe_expedientes.ejes import buscar_eje, cargar_ejes
    from informe_expedientes.tematico import OpcionesTematicas, generar_tematico, resumen

    palabras, excluir, modo, comision_id, eje = [], [], "todas" if a.todas else "alguna", None, None
    if a.tema:
        encontrado = buscar_eje(a.tema, cargar_ejes(a.ejes))
        if not encontrado:
            nombres = ", ".join(e.nombre for e in cargar_ejes(a.ejes))
            print(f"No existe el eje «{a.tema}». Ejes disponibles: {nombres}", file=sys.stderr)
            return 2
        eje, palabras, excluir, modo, comision_id = (encontrado.nombre, list(encontrado.palabras),
                                                     list(encontrado.excluir), encontrado.modo, encontrado.comision_id)
    if a.palabras:
        palabras = separar_palabras(a.palabras)
    if a.excluir:
        excluir = separar_palabras(a.excluir)
    if a.comision:
        comision_id = int(a.comision) if a.comision.isdigit() else id_comision(a.comision)
        if not comision_id:
            print(f"No se reconoce la comisión «{a.comision}».", file=sys.stderr)
            return 2
    tipos_texto = a.tipos.upper().replace(" ", "")
    tipos = None if tipos_texto == "TODOS" else {t if t != "OTROS" else OTROS for t in tipos_texto.split(",") if t}
    consulta = Consulta(palabras=palabras, modo=modo, excluir=excluir, anio_desde=a.anios[0], anio_hasta=a.anios[1],
                        origen=a.origen, tipos=tipos, comision_id=comision_id, eje=eje)
    formatos = tuple(f.strip().lower() for f in (a.formatos or "docx,html,xlsx").split(",") if f.strip())
    opciones = OpcionesTematicas(
        detallar=not a.sin_detalle or a.con_reuniones or a.individuales, buscar_reuniones=a.con_reuniones,
        incluir_asesores=not a.sin_asesores, informes_individuales=a.individuales, limite=a.limite,
        formatos=formatos, carpeta_salida=a.salida, nombre_archivo=a.nombre,
    )
    try:
        res = generar_tematico(consulta, opciones, cliente, avisar)
    except Cancelado:
        return 130
    except Exception as e:  # noqa: BLE001
        print(f"Error en la búsqueda temática: {e}", file=sys.stderr)
        return 1
    print("\n" + resumen(res))
    for ruta in res.archivos.values():
        print(f"  {ruta}")
    return 0


def main() -> None:
    if len(sys.argv) > 1:
        sys.exit(linea_de_comandos(sys.argv[1:]))
    from informe_expedientes.gui import ejecutar
    ejecutar()


if __name__ == "__main__":
    main()
