"""Informe de Expedientes del H. Senado de la Nación.

Sin argumentos abre la ventana. Con argumentos funciona por línea de comandos:

    Un expediente o varios:
        python app.py S-351/25 CD-35/23 --salida "C:/Informes"

    Informe temático (por eje guardado o por palabras):
        python app.py --tema "Salud" --anios 2025-2026
        python app.py --palabras "litio, minería" --tipos PL,PC --comision "Minería"
        python app.py --autor "Mendoza" --anios 2026 --tipos PL
        python app.py --tema "Salud" --bloque "Justicialista"
        python app.py --por-bloque --tipos PL --anios 2026 --salida informes/bloques

    Lista de seguimiento:
        python app.py --seguimiento agregar PE-99/26 S-351/25
        python app.py --seguimiento revisar --salida "C:/Informes"

    Informe de sesión (a partir del plan de labor):
        python app.py --sesion "Plan de labor.pdf"
        python app.py --sesion ultima --formatos html,csv
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
    t.add_argument("--autor", help="Senador autor o coautor: apellido (o apellido y nombre) o su número; "
                                   "varios, separados por punto y coma")
    t.add_argument("--bloque", help="Bloque actual: los proyectos con la firma de alguno de sus integrantes "
                                    "(con --por-bloque, varios separados por punto y coma)")
    t.add_argument("--por-bloque", action="store_true", help="Una página por bloque (todos, o los de --bloque) "
                                                             "y un índice, en la carpeta de --salida")
    t.add_argument("--listar-bloques", action="store_true", help="Mostrar los bloques actuales y salir")
    s = p.add_argument_group("lista de seguimiento")
    s.add_argument("--seguimiento", choices=["revisar", "agregar", "quitar", "listar"],
                   help="revisar la lista y anotar las novedades; agregar o quitar los expedientes indicados; listar")
    s.add_argument("--lista-seguimiento", type=Path, help="Archivo de la lista (por defecto, el de la configuración)")
    ss = p.add_argument_group("informe de sesión")
    ss.add_argument("--sesion", help="Plan de labor: un archivo (.docx, .pdf o .txt), «ultima» (el último "
                                     "publicado en el sitio) o la fecha de la sesión (dd/mm/aaaa)")
    ss.add_argument("--solo-asuntos", action="store_true", help="Solo listar los asuntos del plan, sin consultar fichas")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    a = p.parse_args(argumentos)

    tematico = bool(a.tema or a.palabras or a.comision or a.autor or a.bloque or a.por_bloque or a.listar_bloques)
    if not tematico and not a.expedientes and a.seguimiento not in ("revisar", "listar") and not a.sesion:
        p.error("indicá uno o más expedientes, o --tema / --palabras / --comision, o --seguimiento revisar")

    if a.seguimiento in ("agregar", "quitar", "listar"):
        return _editar_seguimiento(a)

    cliente = Cliente(carpeta_cache=config.carpeta_app() / "cache", usar_cache=not a.sin_cache,
                      carpeta_diagnostico=a.diagnostico)

    def avisar(evento, mensaje="", **_datos):
        if evento in ("etapa", "log"):
            print(mensaje, flush=True)
        elif evento == "advertencia":
            print(f"Aviso: {mensaje}", flush=True)

    if a.seguimiento == "revisar":
        return _revisar_seguimiento(a, cliente, avisar)
    if a.sesion:
        return _sesion(a, cliente, avisar)
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


def _editar_seguimiento(a) -> int:
    from informe_expedientes.identificador import ErrorIdentificador
    from informe_expedientes.seguimiento import Lista

    lista = Lista(a.lista_seguimiento)
    errores = 0
    for texto in a.expedientes:
        try:
            if a.seguimiento == "agregar":
                s, nuevo = lista.agregar(texto, a.tipo.upper() if a.tipo else None)
                print(f"{s.expediente}: {'agregado' if nuevo else 'ya estaba en la lista'}")
            elif lista.quitar(texto):
                print(f"{texto}: quitado")
            else:
                print(f"{texto}: no estaba en la lista")
        except ErrorIdentificador as e:
            errores += 1
            print(f"{texto}: {e}", file=sys.stderr)
    if a.seguimiento != "listar":
        lista.guardar()
    print(f"\nLista de seguimiento ({lista.archivo}): {len(lista.seguidos)} expedientes")
    for s in lista.seguidos:
        situacion = (s.foto or {}).get("situacion", "sin revisar todavía")
        print(f"  {s.expediente:<12} {situacion}")
    return 2 if errores else 0


def _revisar_seguimiento(a, cliente: Cliente, avisar) -> int:
    from informe_expedientes.seguimiento import Lista, OpcionesSeguimiento, resumen, revisar

    lista = Lista(a.lista_seguimiento)
    if not lista.seguidos:
        print(f"La lista de seguimiento está vacía ({lista.archivo}). Agregá expedientes con "
              "--seguimiento agregar S-1234/24.", file=sys.stderr)
        return 2
    formatos = tuple(f.strip().lower() for f in (a.formatos or "html,md").split(",") if f.strip())
    opciones = OpcionesSeguimiento(buscar_reuniones=not a.sin_reuniones, incluir_asesores=not a.sin_asesores,
                                   formatos=formatos, carpeta_salida=a.salida, nombre_archivo=a.nombre)
    try:
        res = revisar(lista, cliente, opciones, avisar)
    except Cancelado:
        return 130
    print("\n" + resumen(res))
    for r in res.con_novedades:
        print(f"\n{r.seguido.expediente} ({r.situacion})")
        for n in r.novedades:
            print(f"  - {n.texto}")
    for ruta in res.archivos.values():
        print(f"  {ruta}")
    return 0


def _sesion(a, cliente: Cliente, avisar) -> int:
    from informe_expedientes import plan_labor
    from informe_expedientes.sesion import OpcionesSesion, etiqueta_referencias, generar_sesion, resumen
    from informe_expedientes.util import parsear_fecha

    try:
        ruta = Path(a.sesion)
        if ruta.exists():
            plan = plan_labor.leer(plan_labor.texto_de_archivo(ruta), str(ruta))
        else:
            publicados = plan_labor.planes_publicados(cliente)
            fecha = parsear_fecha(a.sesion)
            if a.sesion.lower() in ("ultima", "última"):
                elegido = publicados[0] if publicados else None
            elif fecha:
                elegido = next((x for x in publicados if fecha in (x.fecha_sesion, x.fecha_reunion)), None)
            else:
                print(f"No existe el archivo «{a.sesion}». Indicá un archivo, «ultima» o una fecha (dd/mm/aaaa).",
                      file=sys.stderr)
                return 2
            if elegido is None:
                print("No se encontró ese plan de labor en el sitio del Senado.", file=sys.stderr)
                return 2
            print(f"Plan de labor publicado: {elegido.etiqueta}", flush=True)
            plan = plan_labor.plan_publicado(cliente, elegido)
    except (plan_labor.ErrorPlan, OSError) as e:
        print(f"No se pudo leer el plan de labor: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 - sin conexión con el sitio
        print(f"No se pudo consultar el sitio del Senado: {e}", file=sys.stderr)
        return 1
    if not plan.asuntos:
        print("No se encontraron asuntos en el plan de labor.", file=sys.stderr)
        return 2
    if a.solo_asuntos:
        for asunto in plan.asuntos:
            refs = ", ".join(r.clave for r in asunto.referencias)
            print(f"{asunto.orden:>2}. {asunto.titulo or '(sin título)'}" + (f"  [{refs}]" if refs else "")
                  + ("" if asunto.seccion == "Temas acordados" else f"  ({asunto.seccion.lower()})"))
        return 0
    formatos = tuple(f.strip().lower() for f in (a.formatos or "docx,html,xlsx,csv").split(",") if f.strip())
    opciones = OpcionesSesion(buscar_reuniones=a.con_reuniones, incluir_asesores=not a.sin_asesores,
                              formatos=formatos, carpeta_salida=a.salida, nombre_archivo=a.nombre)
    try:
        res = generar_sesion(plan, opciones, cliente, avisar)
    except Cancelado:
        return 130
    print("\n" + resumen(res))
    for tema in res.temas:
        print(f"{tema.asunto.orden:>2}. {tema.titulo}  [{etiqueta_referencias(tema) or 'sin número'}]")
        for r in tema.resultados:
            print(f"      {r.ficha.id.corto}: {r.situacion.titulo}")
    for ruta in res.archivos.values():
        print(f"  {ruta}")
    return 0


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
    if a.listar_bloques or a.por_bloque or a.bloque or a.autor:
        try:
            filtro = _autores_y_bloques(a, cliente, consulta)
        except Exception as e:  # noqa: BLE001 - sin conexión con el sitio
            print(f"No se pudo leer la lista de senadores o de bloques: {e}", file=sys.stderr)
            return 1
        if filtro is not None:
            return filtro
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


def _autores_y_bloques(a, cliente: Cliente, consulta) -> int | None:
    """Completa la consulta con autores o bloque. Devuelve un código de salida si ya terminó."""
    from dataclasses import replace

    from informe_expedientes import senadores
    from informe_expedientes.informe_tematico import escribir_indice_bloques
    from informe_expedientes.tematico import OpcionesTematicas, generar_tematico, resumen

    bloques = senadores.bloques(cliente)
    if a.listar_bloques:
        for nombre, integrantes in bloques.items():
            print(f"{nombre} ({len(integrantes)})")
        return 0
    if a.autor:
        lista = senadores.con_integrantes(senadores.autores(cliente), bloques)
        elegidos = []
        for texto in [x.strip() for x in a.autor.split(";") if x.strip()]:
            hallados = senadores.buscar_senador(texto, lista)
            if len(hallados) != 1:
                opciones = "; ".join(f"{s.legible} ({s.id})" for s in hallados[:12]) or "ninguno"
                print(f"«{texto}» coincide con {len(hallados)} senadores: {opciones}. Usá el apellido y el nombre "
                      "o el número.", file=sys.stderr)
                return 2
            elegidos.append(hallados[0])
        consulta.autores = elegidos
    nombres_bloque = [x.strip() for x in (a.bloque or "").split(";") if x.strip()]
    elegidos_bloque = []
    for texto in nombres_bloque:
        nombre = senadores.buscar_bloque(texto, bloques)
        if not nombre:
            print(f"No se reconoce el bloque «{texto}». Bloques actuales: {', '.join(bloques)}", file=sys.stderr)
            return 2
        elegidos_bloque.append(nombre)
    if not a.por_bloque:
        if elegidos_bloque:
            if len(elegidos_bloque) > 1:
                print("Para varios bloques usá --por-bloque.", file=sys.stderr)
                return 2
            consulta.bloque, consulta.autores = elegidos_bloque[0], bloques[elegidos_bloque[0]]
        return None
    formatos = tuple(f.strip().lower() for f in (a.formatos or "html,xlsx").split(",") if f.strip())
    paginas = []
    for nombre in elegidos_bloque or list(bloques):
        carpeta = a.salida / senadores.carpeta_bloque(nombre)
        opciones = OpcionesTematicas(detallar=not a.sin_detalle, buscar_reuniones=a.con_reuniones,
                                     incluir_asesores=not a.sin_asesores, limite=a.limite, formatos=formatos,
                                     carpeta_salida=carpeta, nombre_archivo="index")
        print(f"\n— Bloque {nombre}", flush=True)
        try:
            res = generar_tematico(replace(consulta, bloque=nombre, autores=bloques[nombre]), opciones, cliente,
                                   lambda ev, msg="", **d: print(msg, flush=True) if ev in ("etapa",) else None)
        except Cancelado:
            return 130
        except Exception as e:  # noqa: BLE001 - un bloque que falla no corta los demás
            print(f"Error con el bloque {nombre}: {e}", file=sys.stderr)
            continue
        print(resumen(res))
        paginas.append((nombre, len(bloques[nombre]), resumen(res), f"{senadores.carpeta_bloque(nombre)}/index.html"))
    indice = escribir_indice_bloques(paginas, consulta, a.salida / "index.html")
    print(f"\nÍndice: {indice}")
    return 0


def main() -> None:
    if len(sys.argv) > 1:
        sys.exit(linea_de_comandos(sys.argv[1:]))
    from informe_expedientes.gui import ejecutar
    ejecutar()


if __name__ == "__main__":
    main()
