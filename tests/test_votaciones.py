import json
import time
import zipfile
from datetime import date

from conftest import FIXTURES, ClienteFalso, leer

from informe_expedientes import contenido, votaciones
from informe_expedientes.identificador import IdExpediente
from informe_expedientes.modelos import Ficha, OrdenDelDia, Votacion
from informe_expedientes.servicio import Opciones, generar
from informe_expedientes.situacion import calcular

HOY = date(2026, 10, 31)
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


def test_solo_las_votaciones_sobre_el_contenido():
    filas = {f.id: f for f in votaciones.parsear_listado(leer("votaciones_actas_2025.html"))}
    relevantes = {i for i, f in filas.items() if votaciones.relevante(f)}
    assert 2598 in relevantes and filas[2598].insistencia         # «Insistencia en la sanción original…» (OTRA)
    assert 2575 not in relevantes                                  # habilitación sobre tablas de la insistencia
    assert 2541 not in relevantes                                  # moción de preferencia
    mocion = next(f for f in votaciones.parsear_listado(leer("votaciones_actas_2026.html"))
                  if f.tipo == "MOCIÓN DE ORDEN")
    assert not votaciones.relevante(mocion)


def test_detalle_completo_pendiente_e_inexistente():
    v = votaciones.parsear_detalle(leer("acta_2847.html"), 2847)
    assert v.titulo == "Modificación de la Carta Orgánica del Banco Central. Artículo 20."
    assert (v.fecha, v.hora, v.mayoria, v.resultado, v.tipo) == (date(2026, 9, 24), "17:44", "SIMPLE",
                                                                  "AFIRMATIVO", "EN PARTICULAR")
    assert (v.afirmativos, v.negativos, v.abstenciones, v.ausentes) == (46, 22, 0, 4)
    ml = votaciones.parsear_detalle(leer("acta_2623.html"), 2623)
    assert ml.expedientes == ["PE-159/25"] and (ml.afirmativos, ml.negativos) == (42, 30)
    pendiente = votaciones.parsear_detalle(leer("acta_2867_pendiente.html"), 2867)
    assert pendiente.resultado == "AFIRMATIVO" and not pendiente.con_totales
    assert votaciones.parsear_detalle(leer("acta_2874_inexistente.html"), 2874) is None


def test_pdf_del_acta_con_quorum_y_articulos():
    v = _pdf("acta_2867.pdf", 2867)
    assert v.titulo == "EN GENERAL OD 409/26 - SALUD MENTAL"
    assert (v.fecha, v.hora) == (date(2026, 10, 30), "00:52")
    assert (v.afirmativos, v.negativos, v.abstenciones, v.ausentes) == (42, 21, 0, 9)
    assert (v.quorum, v.mayoria, v.presentes, v.resultado) == ("MAS 1/2 MC", "MAS 1/2 LEGISLADORES PRESENTES", 63,
                                                                "AFIRMATIVO")
    assert v.presidente == "VILLARRUEL, Victoria Eugenia" and v.numero_en_sesion == "20"
    assert v.dos_tercios is True                        # 42 de 63 presentes: justo los dos tercios
    v.afirmativos = 41
    assert v.dos_tercios is False
    assert votaciones.rango(votaciones.articulos(_pdf("acta_2868.pdf", 2868))) == "1-22"
    assert votaciones.rango(votaciones.articulos(_pdf("acta_2869.pdf", 2869))) == "23-24"
    bcra = _pdf("acta_2847.pdf", 2847)
    assert (bcra.afirmativos, bcra.negativos, bcra.ausentes) == (46, 22, 4)


def test_articulos_y_rangos():
    def arts(titulo, articulos=""):
        return votaciones.articulos(Votacion(1, None, titulo=titulo, articulos=articulos))
    assert arts("ART. 25 AL 34 OD 409/26 - SALUD MENTAL") == [str(i) for i in range(25, 35)]
    assert arts("Carta Orgánica. Artículos 8, 9, 10 y 11.", "Art. 8, Art. 9, Art. 10, Art. 11") == ["8", "9", "10", "11"]
    assert arts("Ley de Bases. Título V: Modernización laboral. Artículo 96.") == ["96"]
    assert arts("Medidas Fiscales. Título V: Impuesto a las Ganancias.") == []
    assert votaciones.rango(["1", "2", "3", "5", "6 bis", "7", "8"]) == "1-3, 5, 7-8 y 6 bis"
    assert votaciones.describir_articulos(["7"]) == "el art. 7"
    assert votaciones.describir_articulos(["2", "3", "4"]) == "los arts. 2-4"
    assert votaciones.parte_votada(Votacion(1, None, titulo="Medidas Fiscales Paliativas y Relevantes. Título V: "
                                                             "Impuesto a las Ganancias.")) == \
        "Título V: Impuesto a las Ganancias"


def test_sesion_con_articulos_rechazados(tmp_path):
    from informe_expedientes.modelos import Resultado, Situacion
    f = Ficha(id=IdExpediente(1, 2024, "PE", "PL"), url="")
    votos = [Votacion(1, date(2024, 6, 12), titulo="Medidas Fiscales.", tipo="EN GENERAL", resultado="AFIRMATIVO",
                      afirmativos=38, negativos=34, abstenciones=0, ausentes=0),
             Votacion(2, date(2024, 6, 12), titulo="Medidas Fiscales. Título V: Impuesto a las Ganancias.",
                      tipo="EN PARTICULAR", resultado="NEGATIVO"),
             Votacion(3, date(2024, 6, 12), titulo="Medidas Fiscales. Artículos 101 y 102.", tipo="EN PARTICULAR",
                      resultado="NEGATIVO"),
             Votacion(4, date(2024, 6, 12), titulo="Medidas Fiscales. Artículo 103.", tipo="EN PARTICULAR",
                      resultado="AFIRMATIVO")]
    r = Resultado(ficha=f, situacion=Situacion("x", "en_tramite"), votaciones=votos)
    [sesion] = contenido.sesiones_votadas(r)
    assert sesion.lineas == ["En general: aprobado (38 a 34).",
                             "En particular: se rechazaron los arts. 101-102; se rechazó Título V: Impuesto a las "
                             "Ganancias."]


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
    assert r.votaciones[0].fuente == "pdf" and r.votaciones[0].titulo.endswith("SALUD MENTAL")
    s = r.situacion
    assert s.nivel == "aprobado" and s.titulo == "Media sanción del Senado (votada en el recinto)"
    assert s.detalle[:2] == ["Votado en el recinto el 29/10/2026 (42 a 21); la ficha oficial todavía no "
                             "registra la sanción.",
                             "Pasa a la Cámara de Diputados para su revisión (art. 78 CN)."]
    assert s.contraste == ["El sitio de Diputados confirma la media sanción del Senado del 29/10/2026, con "
                           "modificaciones al dictamen y el pase a la Cámara de Diputados."]
    pasos = {p.nombre: p for p in s.pasos}
    assert pasos["Sanción del Senado"].estado == "hecho" and pasos["Sanción del Senado"].fecha == date(2026, 10, 29)
    assert "con modificaciones" in pasos["Sanción del Senado"].detalle
    assert pasos["Cámara de Diputados"].estado == "actual"
    assert s.caducidad.fecha == date(2029, 2, 28)
    [sesion] = contenido.sesiones_votadas(r)
    assert sesion.fecha == "29/10/2026"
    assert sesion.lineas == ["En general: aprobado (42 a 21).",
                             "En particular: se aprobó con modificaciones respecto del dictamen (las actas no "
                             "indican qué artículos: ver el texto aprobado)."]
    assert [e.texto for e in sesion.enlaces] == ["Acta", "Texto de la media sanción"]
    html = r.archivos["html"].read_text(encoding="utf-8")
    assert "Votaciones en el recinto" in html and "Se votó en UNA (1) sesión." in html
    assert f'href="{B}/votaciones/verActaVotacion/2867"' in html
    assert "Cómo votó cada bloque" not in html and "Afirmativos</th>" not in html
    assert "pasó a Diputados; todavía sin número propio" in html
    assert "Votado en el recinto el 29/10/2026 (42 a 21)" in contenido.texto_resumen(r)
    with zipfile.ZipFile(r.archivos["docx"]) as z:
        documento = z.read("word/document.xml").decode("utf-8")
    assert "En particular: se aprobó con modificaciones" in documento and "art. 78 CN" in documento


def test_votacion_ya_registrada_no_cambia_la_situacion(tmp_path):
    r = generar("PE-159/25", Opciones(carpeta_salida=tmp_path, formatos=("html",), buscar_reuniones=False,
                                      buscar_agenda=False), ClienteFalso(), hoy=HOY)
    assert r.situacion.titulo == "Sancionado: Ley N° 27.802"
    assert r.votaciones[0].id == 2623 and r.votaciones[0].fuente == "detalle"
    assert not any("votado en el recinto" in d.lower() for d in r.situacion.detalle)


def test_rechazo_en_el_recinto():
    filas = {x.id: x for x in votaciones.parsear_listado(leer("votaciones_actas_2026.html"))}
    v = filas[2867]
    v.resultado, v.afirmativos, v.negativos, v.abstenciones, v.ausentes = "NEGATIVO", 20, 40, 0, 12
    s = calcular(_ficha_od("409/26"), HOY, [v])
    assert s.nivel == "rechazado" and s.titulo == "Rechazado en el recinto"
    assert "(20 a 40), con resultado negativo" in s.detalle[0]
    assert any("no puede repetirse en las sesiones de ese año (art. 81 CN)" in d for d in s.detalle)


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


def test_detalle_y_pdf_que_no_coinciden():
    """Acta 2867 (Salud Mental en general): el detalle publicado el 31/10 no coincide con el PDF."""
    detalle = votaciones.parsear_detalle(leer("acta_2867_completa.html"), 2867)
    assert (detalle.afirmativos, detalle.negativos, detalle.ausentes) == (52, 15, 5)
    pdf = _pdf("acta_2867.pdf", 2867)
    assert votaciones.discrepancia(detalle, pdf) == (
        "el detalle del acta registra 52 a 15 (5 ausentes) y su PDF, 42 a 21 (9 ausentes): verificar con la "
        "Secretaría Parlamentaria")
    assert votaciones.discrepancia(pdf, pdf) == ""
    fila = Votacion(2867, date(2026, 10, 29), tipo="EN GENERAL", resultado="AFIRMATIVO", ordenes_del_dia=["409/26"],
                    url_detalle=f"{B}/votaciones/detalleActa/2867", url_pdf=f"{B}/votaciones/verActaVotacion/2867")
    cliente = ClienteFalso()
    cliente.mapa[fila.url_detalle] = "acta_2867_completa.html"
    v = votaciones.Indice(None).completar(cliente, fila)
    assert v.fuente == "detalle" and v.afirmativos == 52 and v.discrepancia.startswith("el detalle del acta")


def test_ficha_que_ya_registra_la_sancion(tmp_path):
    cliente = ClienteFalso()
    cliente.mapa[f"{B}/parlamentario/comisiones/verExp/99.26/PE/PL"] = "ficha_pe_99_26_registrada.html"
    r = generar("PE-99/26", Opciones(carpeta_salida=tmp_path, formatos=("html",), buscar_reuniones=False,
                                     buscar_agenda=False), cliente, hoy=HOY)
    s = r.situacion
    assert s.titulo == "Media sanción del Senado"
    assert s.detalle[0] == "Aprobado por el Senado el 30/10/2026 con modificaciones al dictamen."
    assert "Pasa a la Cámara de Diputados para su revisión (art. 78 CN)." in s.detalle
    assert s.contraste == []                  # la ficha y Diputados coinciden
