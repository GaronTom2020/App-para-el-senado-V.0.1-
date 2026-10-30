import json
import time
import zipfile
from datetime import date

from conftest import FIXTURES, ClienteFalso, leer

from informe_expedientes import contenido, votaciones
from informe_expedientes.identificador import IdExpediente
from informe_expedientes.modelos import Ficha, OrdenDelDia
from informe_expedientes.servicio import Opciones, generar
from informe_expedientes.situacion import calcular

HOY = date(2026, 10, 30)
B = "https://www.senado.gob.ar"


def _pdf(nombre: str, vid: int):
    return votaciones.parsear_pdf(votaciones.texto_pdf((FIXTURES / nombre).read_bytes()), vid)


def test_listado_anual_con_expedientes_od_y_pendientes():
    filas = votaciones.parsear_listado(leer("votaciones_actas_2026.html"))
    assert len(filas) == 165
    por_id = {f.id: f for f in filas}
    ml = por_id[2623]
    assert (ml.fecha, ml.numero_en_sesion, ml.titulo) == (date(2026, 2, 11), "1", "Modernización Laboral.")
    assert (ml.tipo, ml.resultado, ml.mayoria) == ("EN GENERAL", "AFIRMATIVO", "SIMPLE")
    assert ml.expedientes == ["PE-159/25"] and ml.ordenes_del_dia == ["699/25"]
    assert ml.url_detalle == f"{B}/votaciones/detalleActa/2623" and ml.video.startswith("https://www.youtube.com")
    bcra = por_id[2847]
    assert bcra.ordenes_del_dia == ["367/26"] and bcra.articulos == "Art. 20" and bcra.expedientes == []
    # Sesión del 29/10/2026: ya figura en el listado, pero solo con el PDF.
    salud = por_id[2867]
    assert (salud.titulo, salud.tipo, salud.ordenes_del_dia) == ("", "EN GENERAL", ["409/26"])
    assert salud.url_detalle is None and salud.url_pdf == f"{B}/votaciones/verActaVotacion/2867"
    acuerdos = next(f for f in filas if len(f.expedientes) > 20)
    assert "PE-136/26" in acuerdos.expedientes


def test_listados_de_anios_anteriores():
    for anio, cantidad in ((2025, 97), (2024, 91), (2023, 27)):
        leidas = votaciones.parsear_listado(leer(f"votaciones_actas_{anio}.html"))
        assert len(leidas) == cantidad and all(f.fecha.year == anio for f in leidas)


def test_detalle_completo_pendiente_e_inexistente():
    v = votaciones.parsear_detalle(leer("acta_2847.html"), 2847)
    assert v.titulo == "Modificación de la Carta Orgánica del Banco Central. Artículo 20."
    assert (v.fecha, v.hora, v.mayoria, v.resultado, v.tipo) == (date(2026, 9, 24), "17:44", "SIMPLE",
                                                                  "AFIRMATIVO", "EN PARTICULAR")
    assert (v.afirmativos, v.negativos, v.abstenciones, v.ausentes) == (46, 22, 0, 4)
    assert len(v.votos) == 72
    mendoza = v.votos[0]
    assert (mendoza.nombre, mendoza.bloque, mendoza.provincia, mendoza.voto, mendoza.senador_id) == (
        "MENDOZA, SANDRA MARIELA", "CONVICCIÓN FEDERAL", "TUCUMÁN", "AFIRMATIVO", 540)
    assert any(x.senador_id is None for x in v.votos)       # una fila sin enlace al senador
    ml = votaciones.parsear_detalle(leer("acta_2623.html"), 2623)
    assert ml.expedientes == ["PE-159/25"] and (ml.afirmativos, ml.negativos) == (42, 30)
    pendiente = votaciones.parsear_detalle(leer("acta_2867_pendiente.html"), 2867)
    assert pendiente.resultado == "AFIRMATIVO" and not pendiente.votos and not pendiente.con_totales
    assert votaciones.parsear_detalle(leer("acta_2874_inexistente.html"), 2874) is None


def test_pdf_del_acta_con_quorum():
    v = _pdf("acta_2867.pdf", 2867)
    assert v.titulo == "EN GENERAL OD 409/26 - SALUD MENTAL"
    assert (v.fecha, v.hora) == (date(2026, 10, 30), "00:52")
    assert (v.afirmativos, v.negativos, v.abstenciones, v.ausentes) == (42, 21, 0, 9)
    assert len(v.votos) == 72 and v.resultado == "AFIRMATIVO"
    assert (v.quorum, v.mayoria, v.presentes) == ("MAS 1/2 MC", "MAS 1/2 LEGISLADORES PRESENTES", 63)
    assert v.presidente == "VILLARRUEL, Victoria Eugenia" and v.numero_en_sesion == "20"
    assert v.votos[0].nombre == "Abad, Maximiliano" and v.votos[-1].voto == "NEGATIVO"
    bcra = _pdf("acta_2847.pdf", 2847)
    assert (bcra.afirmativos, bcra.negativos, bcra.ausentes) == (46, 22, 4)


def test_bloques_por_nombre():
    bloques = votaciones.parsear_bloques(leer("senadores_bloques.html"))
    assert sum(len(x) for x in bloques.values()) == 72
    assert ("MENDOZA, SANDRA MARIELA", 540) in bloques["Convicción Federal"]
    v = _pdf("acta_2867.pdf", 2867)
    assert votaciones.asignar_bloques(v, bloques) == 0
    por_bloque = {b: n for b, *n in v.por_bloque()}
    assert por_bloque["La Libertad Avanza"] == [21, 0, 0, 0]
    assert por_bloque["Justicialista"] == [0, 15, 0, 7]
    assert sum(sum(n) for n in por_bloque.values()) == 72


def _ficha_od(numero_od: str) -> Ficha:
    f = Ficha(id=IdExpediente(99, 2026, "PE", "PL"), url="")
    f.ordenes_del_dia = [OrdenDelDia(numero_od, date(2026, 10, 21), "PENDIENTE")]
    f.fecha_mesa_entradas = date(2026, 4, 20)
    return f


def test_corresponde_por_enlace_od_y_titulo():
    filas = {f.id: f for f in votaciones.parsear_listado(leer("votaciones_actas_2026.html"))}
    assert votaciones.corresponde(filas[2867], _ficha_od("409/26"))
    assert not votaciones.corresponde(filas[2867], _ficha_od("410/26"))
    ml = Ficha(id=IdExpediente(159, 2025, "PE", "PL"), url="")
    assert votaciones.corresponde(filas[2623], ml)
    mocion = next(f for f in filas.values() if "retorno a comisión del expediente PE-159/25" in f.titulo)
    assert mocion.expedientes == [] and votaciones.corresponde(mocion, ml)


def test_informe_pe_99_26_votado_sin_registrar(tmp_path):
    eventos = []
    r = generar("PE-99/26", Opciones(carpeta_salida=tmp_path, buscar_reuniones=False, buscar_agenda=False),
                ClienteFalso(), lambda ev, msg="", **d: eventos.append((ev, msg)), hoy=HOY)
    assert not [m for e, m in eventos if e == "advertencia"]
    assert [v.id for v in r.votaciones] == [2867, 2868, 2869, 2870]
    general = r.votaciones[0]
    assert general.fuente == "pdf" and general.bloques_actuales and general.titulo.endswith("SALUD MENTAL")
    s = r.situacion
    assert s.nivel == "aprobado" and s.titulo == "Media sanción del Senado (votada en el recinto)"
    assert s.detalle[0] == ("Votado en el recinto el 29/10/2026 (42 a 21); la ficha oficial todavía no "
                            "registra la sanción.")
    pasos = {p.nombre: p for p in s.pasos}
    assert pasos["Sanción del Senado"].estado == "hecho" and pasos["Sanción del Senado"].fecha == date(2026, 10, 29)
    assert pasos["Cámara de Diputados"].estado == "actual"
    assert s.caducidad.fecha == date(2029, 2, 28)
    html = r.archivos["html"].read_text(encoding="utf-8")
    assert "Votaciones en el recinto" in html and "CUATRO (4) votaciones nominales" in html
    assert f'href="{B}/votaciones/verActaVotacion/2867"' in html
    assert "Cómo votó cada bloque: en general, 29/10/2026" in html
    assert '<td>La Libertad Avanza</td><td class="num">21</td>' in html
    assert "listado de bloques actual" in html
    assert "Votado en el recinto el 29/10/2026 (42 a 21)" in contenido.texto_resumen(r)
    with zipfile.ZipFile(r.archivos["docx"]) as z:
        documento = z.read("word/document.xml").decode("utf-8")
    assert "Cómo votó cada bloque" in documento and "La Libertad Avanza" in documento


def test_votacion_ya_registrada_no_cambia_la_situacion(tmp_path):
    r = generar("PE-159/25", Opciones(carpeta_salida=tmp_path, formatos=("html",), buscar_reuniones=False,
                                      buscar_agenda=False), ClienteFalso(), hoy=HOY)
    assert r.situacion.titulo == "Sancionado: Ley N° 27.802"
    assert r.votaciones[0].id == 2623 and r.votaciones[0].fuente == "detalle"
    assert not any("recinto" in d for d in r.situacion.detalle)


def test_rechazo_en_el_recinto():
    filas = {x.id: x for x in votaciones.parsear_listado(leer("votaciones_actas_2026.html"))}
    v = filas[2867]
    v.resultado, v.afirmativos, v.negativos, v.abstenciones, v.ausentes = "NEGATIVO", 20, 40, 0, 12
    s = calcular(_ficha_od("409/26"), HOY, [v])
    assert s.nivel == "rechazado" and s.titulo == "Rechazado en el recinto"
    assert "(20 a 40), con resultado negativo" in s.detalle[0]


def test_indice_guarda_listados_y_actas(tmp_path):
    archivo = tmp_path / "indice_votaciones.json"
    cliente = ClienteFalso()
    ficha = _ficha_od("409/26")
    primera = votaciones.buscar(cliente, ficha, HOY, indice=votaciones.Indice(archivo))
    pedidos = len(cliente.pedidos)
    assert pedidos and archivo.exists()
    guardado = json.loads(archivo.read_text(encoding="utf-8"))
    assert "2026" in guardado["anios"] and "2867" in guardado["actas"]
    segunda = votaciones.buscar(cliente, ficha, HOY, indice=votaciones.Indice(archivo))
    assert len(cliente.pedidos) == pedidos                   # todo salió del índice
    assert [v.afirmativos for v in segunda] == [v.afirmativos for v in primera]
    # El listado del año en curso vence a las pocas horas; las actas ya leídas se conservan.
    guardado["anios"]["2026"]["guardado"] = time.time() - 4 * 3600
    archivo.write_text(json.dumps(guardado), encoding="utf-8")
    votaciones.buscar(cliente, ficha, HOY, indice=votaciones.Indice(archivo))
    assert cliente.pedidos[pedidos:] == [f"{B}/votaciones/actas"]
