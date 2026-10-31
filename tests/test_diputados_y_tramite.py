"""Sitio de Diputados (hcdn.gob.ar) y recorrido según la Constitución (arts. 77 a 84)."""

from datetime import date

from conftest import ClienteFalso, leer

from informe_expedientes import contenido, hcdn, situacion, tramite
from informe_expedientes.ficha import parsear_ficha
from informe_expedientes.identificador import IdExpediente
from informe_expedientes.servicio import Opciones, generar

HOY = date(2026, 10, 31)


def _proyecto(archivo: str, ident: IdExpediente):
    return next(p for p in hcdn.parsear_resultado(leer(archivo)) if p.expediente_senado == hcdn.numero_hcdn(ident))


def _ficha(archivo: str, ident: IdExpediente):
    return parsear_ficha(leer(archivo), ident.url_ficha(), ident)


def test_resultado_de_diputados_con_tramite_completo():
    p = _proyecto("hcdn_pe_159_25.html", IdExpediente(159, 2025, "PE"))
    assert (p.iniciado_en, p.expediente_diputados, p.expediente_senado, p.ley) == (
        "Senado", "0065-S-2025", "0159-PE-2025", "27802")
    assert p.giros_diputados == ["LEGISLACION DEL TRABAJO", "PRESUPUESTO Y HACIENDA"]
    assert [(d.camara, d.orden_del_dia) for d in p.dictamenes] == [("Diputados", "0006/2025"), ("Senado", "0699/2025"),
                                                                  ("Senado", "0706/2025")]
    assert [(m.camara, m.fecha, m.resultado) for m in p.sanciones()] == [
        ("Senado", date(2026, 2, 11), "MEDIA SANCION"), ("Diputados", date(2026, 2, 19), "MEDIA SANCION"),
        ("Senado", date(2026, 2, 27), "SANCIONADO")]
    assert [m.movimiento for m in p.pases()] == ["PASA A DIPUTADOS -", "VUELVE A SENADO -"]
    assert ("Media Sanción Senado", "http://www.senado.gov.ar/web/proyectos/verExpe.php?origen=PE&nro_comision=&"
            "tipo=PL&numexp=159/25&tConsulta=5") in p.textos


def test_busqueda_trae_otros_proyectos_con_el_mismo_numero():
    proyectos = hcdn.parsear_resultado(leer("hcdn_cd_14_24.html"))
    assert [p.expediente_senado for p in proyectos] == ["0014-CD-2025", "0014-CD-2024"]
    elegido = _proyecto("hcdn_cd_14_24.html", IdExpediente(14, 2024, "CD"))
    assert elegido.expediente_diputados == "0422-D-2024"


def test_veto_insistencia_y_articulos_en_diputados():
    p = _proyecto("hcdn_cd_14_24.html", IdExpediente(14, 2024, "CD"))
    assert "VETO TOTAL" in p.veto().movimiento
    [insistencia] = p.insistencia()
    assert insistencia.fecha == date(2024, 10, 9) and "ACEPTA VETO" in insistencia.movimiento
    assert p.articulos_en_particular("Diputados") == (["2", "3", "4", "5", "6"], ["7"])
    assert hcdn.articulos_en_texto("CONSIDERACION Y RECHAZO EN PARTICULAR DE NUEVO ARTICULO PROPUESTO COMO 7") == ["7"]


def test_media_sancion_que_la_ficha_todavia_no_registra():
    ident = IdExpediente(99, 2026, "PE", "PL")
    f = _ficha("ficha_pe_99_26.html", ident)
    antes = _proyecto("hcdn_pe_99_26_antes.html", ident)        # 30/10, antes de que Diputados lo cargara
    assert antes.sanciones() == []
    ahora = _proyecto("hcdn_pe_99_26.html", ident)
    s = situacion.calcular(f, HOY, diputados=ahora)
    assert s.titulo == "Media sanción del Senado (según Diputados)"
    assert s.detalle[:2] == ["Aprobado por el Senado el 29/10/2026, según el sitio de Diputados; la ficha oficial "
                             "todavía no registra la sanción.",
                             "Pasa a la Cámara de Diputados para su revisión (art. 78 CN)."]
    assert s.contraste == ["El sitio de Diputados registra la media sanción del Senado del 29/10/2026, con "
                           "modificaciones al dictamen; la ficha del Senado todavía no."]
    assert {p.nombre: p.estado for p in s.pasos}["Cámara de Diputados"] == "actual"


def test_modificaciones_de_la_revisora_y_vuelta_al_senado():
    ident = IdExpediente(159, 2025, "PE", "PL")
    f = _ficha("ficha_pe_159_25.html", ident)
    r = tramite.armar(f, _proyecto("hcdn_pe_159_25.html", ident))
    assert r.origen == tramite.SENADO and r.revision_modifico and r.vuelta.fecha == date(2026, 2, 27)
    s = situacion.calcular(f, HOY, diputados=_proyecto("hcdn_pe_159_25.html", ident))
    assert [(p.nombre, p.estado, p.detalle) for p in s.pasos][3:] == [
        ("Sanción del Senado", "hecho", "aprobado, con modificaciones"),
        ("Cámara de Diputados", "hecho", "con modificaciones"),
        ("Vuelve al Senado", "hecho", "aceptó las modificaciones"),
        ("Ley y Poder Ejecutivo", "hecho", "Ley 27.802; promulgo"),
    ]
    assert "El Senado aceptó las modificaciones de la Cámara de Diputados el 27/02/2026 (art. 81 CN)." in s.detalle
    # Mientras el Senado no resolvió, la Constitución le da dos caminos.
    f.resoluciones = f.resoluciones[:2]
    s = situacion.calcular(f, HOY)
    assert s.titulo == "Con modificaciones de Diputados: vuelve al Senado"
    assert any("puede aceptarlas por mayoría absoluta" in d and "No puede introducir cambios nuevos (art. 81 CN)" in d
               for d in s.detalle)
    assert {p.nombre: p.estado for p in s.pasos}["Vuelve al Senado"] == "actual"


def test_veto_con_insistencia_rechazada():
    ident = IdExpediente(14, 2024, "CD", "PL")
    s = situacion.calcular(_ficha("ficha_cd_14_24.html", ident), HOY,
                           diputados=_proyecto("hcdn_cd_14_24.html", ident))
    assert s.nivel == "vetado"
    assert any(d.startswith("El 09/10/2024, la Cámara de Diputados no alcanzó los dos tercios para insistir")
               for d in s.detalle)
    assert [(p.nombre, p.estado) for p in s.pasos][-2:] == [("Ley y Poder Ejecutivo", "hecho"),
                                                            ("Insistencia", "detenido")]


def test_revisora_por_dos_tercios():
    from informe_expedientes.modelos import Votacion
    ident = IdExpediente(14, 2024, "CD", "PL")
    f = _ficha("ficha_cd_14_24.html", ident)
    f.resoluciones = f.resoluciones[:1]
    f.resoluciones[0].campos = [("FECHA DE SANCION", "12-09-2024"), ("SANCION", "APROBO"),
                                ("COMENTARIO", "CON MODIFICACIONES")]
    general = Votacion(2502, date(2024, 9, 12), tipo="EN GENERAL", resultado="AFIRMATIVO",
                       afirmativos=57, negativos=10, abstenciones=0, ausentes=5)
    s = situacion.calcular(f, HOY, [general])
    assert s.titulo == "Aprobado por el Senado con modificaciones: vuelve a Diputados"
    assert any("vuelve a la Cámara de Diputados, que puede aceptarlas" in d for d in s.detalle)
    assert ("En el Senado se votó con CINCUENTA Y SIETE (57) votos afirmativos sobre SESENTA Y SIETE (67) presentes: "
            "alcanza los dos tercios (dato de la votación en general, orientativo).") in s.detalle


def test_informe_con_etapa_en_diputados(tmp_path):
    r = generar("CD-14/24", Opciones(carpeta_salida=tmp_path, formatos=("html",), buscar_reuniones=False,
                                     buscar_agenda=False), ClienteFalso(), hoy=HOY)
    filas = {k: "".join(fr.texto for fr in v) for k, v in contenido.datos_diputados_hcdn(r)}
    assert filas["Expediente en Diputados"] == "422-D-2024"
    assert filas["En particular"] == "Modificó los arts. 2-6; rechazó el art. 7."
    assert filas["Votación en Diputados"] == "Media sanción el 14/08/2024"
    assert filas["Último movimiento en Diputados"].startswith("Consideracion y rechazo de la insistencia")
    html = r.archivos["html"].read_text(encoding="utf-8")
    assert "strNumExp=422&amp;strNumExpOrig=D&amp;strNumExpAnio=2024" in html


def test_sin_diputados_para_proyectos_que_no_son_de_ley(tmp_path):
    # La resolución del Senado no pasa por Diputados: no se consulta su sitio.
    cliente = ClienteFalso()
    cliente.mapa["https://www.senado.gob.ar/parlamentario/comisiones/verExp/351.25/S/PR"] = "ficha_s_351_25.html"
    r = generar("S-351/25", Opciones(carpeta_salida=tmp_path, formatos=("html",), buscar_reuniones=False,
                                     buscar_agenda=False, tipo="PR"), cliente, hoy=HOY)
    assert not r.diputados_consultado and not any("hcdn" in u for u in cliente.pedidos)
