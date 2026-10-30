from datetime import date

from conftest import ClienteFalso, leer

from informe_expedientes import comisiones, contenido
from informe_expedientes.identificador import IdExpediente
from informe_expedientes.servicio import Opciones, generar

HOY = date(2026, 10, 19)
B = "https://www.senado.gob.ar"


def test_mapa_de_comisiones():
    assert comisiones.id_comision("DE EDUCACIÓN Y CULTURA") == 75
    assert comisiones.id_comision("DE PRESUPUESTO Y HACIENDA") == 54
    assert comisiones.id_comision("Comisión de Salud") == 78
    assert comisiones.id_comision("BICAMERAL PERMANENTE DE TRÁMITE LEGISLATIVO (LEY 26.122)") == 105
    assert comisiones.id_comision("DE COMISION INEXISTENTE DE PRUEBA") is None
    assert comisiones.actualizar_mapa_comisiones(leer("buscador.html")) == 46


def test_listado_secciones_fechas_y_paginas():
    entradas, paginas = comisiones.parsear_listado(leer("comision_75.html"), f"{B}/parlamentario/comisiones/info/75", 75)
    por_id = {e.nota_id: e for e in entradas}
    assert paginas == {"ReunionesVarias": 2, "Reuniones": 8}
    assert por_id["23244"].fecha == date(2025, 10, 1)
    assert por_id["23244"].titulo == "CREACION DE UNIVERSIDADES"
    assert por_id["23244"].seccion == "REUNIONES"
    assert por_id["24417"].seccion == "REUNIONES VARIAS"
    assert por_id["22010"].seccion == "DOCUMENTACION"
    assert len([e for e in entradas if e.seccion == "REUNIONES"]) == 10


def test_listar_reuniones_corta_al_pasar_la_fecha():
    cliente = ClienteFalso()
    lista = comisiones.listar_reuniones(cliente, 75, date(2023, 10, 11))
    ids = {e.nota_id for e in lista}
    assert {"23192", "22300", "21000", "20800"} <= ids
    pedidos = [p for p in cliente.pedidos if "/info/75" in p]
    assert pedidos == [f"{B}/parlamentario/comisiones/info/75",
                       f"{B}/parlamentario/comisiones/info/75?ReunionesVarias=2",
                       f"{B}/parlamentario/comisiones/info/75?Reuniones=2"]


def test_nota_con_enlace_vt_y_video():
    datos = comisiones.analizar_nota(leer("nota_23244.html"), IdExpediente(35, 2023, "CD"))
    assert datos["titulo"] == "CREACION DE UNIVERSIDADES"
    assert datos["videos"] == ["https://www.youtube.com/watch?v=4JjcptV_SKU"]
    assert [(d.etiqueta, d.url) for d in datos["versiones"]] == [("VT", f"{B}/upload/archivo/55722")]
    assert datos["fecha"] == date(2025, 10, 1)
    assert "&" not in datos["resumen"] and "nbsp" not in datos["resumen"]


def test_nota_por_texto_y_otros_archivos():
    datos = comisiones.analizar_nota(leer("nota_salud_24350.html"), IdExpediente(351, 2025, "S"))
    assert datos is not None
    assert datos["videos"] == ["https://www.youtube.com/watch?v=ADX8Za9zlW4"]
    assert [d.etiqueta for d in datos["versiones"]] == ["Versión Taquigráfica Reunión."]
    assert [d.etiqueta for d in datos["otros"]] == ["Presentación del Ministerio de Salud"]


def test_nota_que_no_menciona_el_expediente():
    html = leer("nota_generica.html")
    assert comisiones.analizar_nota(html, IdExpediente(351, 2025, "S")) is None
    assert comisiones.analizar_nota(html, IdExpediente(35, 2023, "CD")) is None
    assert comisiones.analizar_nota(html, IdExpediente(999, 2025, "S")) is not None


def test_agenda_con_prefijo_fuera_del_enlace():
    url = f"{B}/parlamentario/comisiones/agenda/75"
    convocadas = comisiones.parsear_agenda(leer("agenda_75.html"), url, IdExpediente(643, 2025, "S"),
                                           "Educación y Cultura", HOY)
    assert len(convocadas) == 1
    c = convocadas[0]
    assert c.fecha == date(2026, 10, 20)
    assert (c.hora, c.lugar) == ("15:00", "FRONDIZI - MORENO")
    assert c.titulo == "REUNIÓN DE ASESORES DE EDUCACIÓN Y CULTURA"
    assert c.comision == "Educación y Cultura"
    assert comisiones.parsear_agenda(leer("agenda_75.html"), url, IdExpediente(35, 2023, "CD"), "x", HOY) == []


def test_informe_completo_cd_35_23(tmp_path):
    cliente = ClienteFalso()
    eventos = []
    opciones = Opciones(carpeta_salida=tmp_path, notas_usuario="Pedido de la Secretaría.")
    r = generar("CD-35/23", opciones, cliente, lambda ev, msg="", **d: eventos.append((ev, msg, d)), hoy=HOY)

    assert r.ficha.id.tipo == "PL"                      # resuelto con el buscador
    assert r.situacion.nivel == "caducado"
    assert [(x.fecha, x.tipo) for x in r.reuniones] == [(date(2025, 9, 24), "Asesores"),
                                                        (date(2025, 10, 1), "Plenario")]
    plenario = r.reuniones[1]
    assert plenario.comisiones == ["DE EDUCACIÓN Y CULTURA", "DE PRESUPUESTO Y HACIENDA"]
    assert plenario.versiones and plenario.videos
    assert r.busqueda.desde == date(2023, 10, 11) and r.busqueda.hasta == date(2026, 6, 24)
    assert r.busqueda.notas_revisadas == 16
    assert r.ficha.ordenes_del_dia[0].url_pdf == f"{B}/parlamentario/parlamentaria/34120/downloadOrdenDia"
    assert r.convocadas == []
    assert set(r.archivos) == {"docx", "html"} and all(p.exists() for p in r.archivos.values())
    assert not [e for e in eventos if e[0] == "advertencia"]

    html = r.archivos["html"].read_text(encoding="utf-8")
    assert "Caducó el 28/02/2026" in html
    assert 'href="https://www.senado.gob.ar/micrositios/nota/23244/noticias"' in html
    assert 'href="https://www.youtube.com/watch?v=4JjcptV_SKU"' in html
    assert 'href="https://www.hcdn.gob.ar/proyectos/resultado.html?strNumExp=1752&amp;strNumExpOrig=D&amp;strNumExpAnio=2023"' in html
    assert "Pedido de la Secretaría." in html
    texto = contenido.texto_resumen(r)
    assert "CREACION DE UNIVERSIDADES" in texto and "Situación: Caducó" in texto


def test_informe_s_351_25_tipo_por_prueba_y_reunion_por_texto(tmp_path):
    cliente = ClienteFalso()
    r = generar("S-351/25", Opciones(carpeta_salida=tmp_path, formatos=("html",)), cliente, hoy=HOY)
    assert r.ficha.id.tipo == "PL"
    assert r.situacion.titulo == "En comisión: Salud"
    assert [x.nota_id for x in r.reuniones] == ["24350"]
    assert r.reuniones[0].tipo == "Comisión"
    assert set(r.archivos) == {"html"}


def test_docx_tiene_hipervinculos(tmp_path):
    import zipfile
    r = generar("CD-14/24", Opciones(carpeta_salida=tmp_path, formatos=("docx",), buscar_reuniones=False,
                                     buscar_agenda=False), ClienteFalso(), hoy=HOY)
    with zipfile.ZipFile(r.archivos["docx"]) as z:
        documento = z.read("word/document.xml").decode("utf-8")
        relaciones = z.read("word/_rels/document.xml.rels").decode("utf-8")
    assert documento.count("<w:hyperlink") >= 8
    assert "verExp/14.24/CD/PL" in relaciones and "strNumExp=1888&amp;strNumExpOrig=D&amp;strNumExpAnio=2024" in relaciones
    assert "Ley N° 27.757" in documento
