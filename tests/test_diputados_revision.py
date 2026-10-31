"""Etapa en la Cámara de Diputados como cámara revisora (Fase 3), con casos reales del 31/10/2026."""

import json
import zipfile
from datetime import date

import pytest
from conftest import ClienteFalso, leer

from informe_expedientes import contenido, hcdn, seguimiento
from informe_expedientes.identificador import IdExpediente
from informe_expedientes.servicio import Opciones, generar

HOY = date(2026, 10, 31)


def _proyecto(archivo: str, ident: IdExpediente):
    return next(p for p in hcdn.parsear_resultado(leer(archivo)) if p.expediente_senado == hcdn.numero_hcdn(ident))


def _informe(texto: str, tmp_path, formatos=("html",)):
    return generar(texto, Opciones(tipo="PL", carpeta_salida=tmp_path, formatos=formatos, buscar_reuniones=False,
                                   buscar_agenda=False), ClienteFalso(), hoy=HOY)


@pytest.mark.parametrize("archivo, ident, clave, texto", [
    ("hcdn_s_361_26.html", IdExpediente(361, 2026, "S"), "en_comision", "en comisión"),
    ("hcdn_pe_99_26.html", IdExpediente(99, 2026, "PE"), "ingresado", "ingresó, todavía sin giro a comisión"),
    ("hcdn_pe_13_26.html", IdExpediente(13, 2026, "PE"), "modificado",
     "aprobado con modificaciones el 21/10/2026: vuelve al Senado"),
    ("hcdn_s_1167_25.html", IdExpediente(1167, 2025, "S"), "rechazado", "rechazado el 08/10/2025"),
    ("hcdn_pe_98_26.html", IdExpediente(98, 2026, "PE"), "sancionado", "sanción definitiva el 24/06/2026"),
])
def test_estado_en_diputados(archivo, ident, clave, texto):
    estado = _proyecto(archivo, ident).estado("Diputados", "Senado")
    assert (estado.clave, estado.texto) == (clave, texto)


def test_estado_con_dictamen_y_resumen_de_la_mayoria():
    p = _proyecto("hcdn_pe_13_26.html", IdExpediente(13, 2026, "PE"))
    p.tramite = [m for m in p.tramite if not (m.camara == "Diputados" and m.fecha)]     # antes de la sesión
    p.tramite = [m for m in p.tramite if not m.movimiento.startswith("VUELVE")]
    assert p.estado("Diputados", "Senado").texto == ("con dictamen de comisión: Orden del Día N° 448/2026 "
                                                     "(16/10/2026), con modificaciones")
    assert hcdn.mayoria("DICTAMEN DE MAYORIA: ACONSEJA SU SANCION; 2 DICTAMENES DE MINORIA: CON MODIFICACIONES") == \
        "aconseja su sanción"
    assert hcdn.mayoria("DICTAMEN DE MAYORIA: CON MODIFICACIONES LA COMISION HA TENIDO A LA VISTA…") == \
        "con modificaciones"


def test_media_sancion_en_comision_de_diputados(tmp_path):
    r = _informe("S-361/26", tmp_path)
    s = r.situacion
    assert s.titulo == "Media sanción del Senado"
    assert ("En Diputados (expediente 57-S-2026): en las comisiones de Recursos Naturales y Conservacion del "
            "Ambiente Humano y Presupuesto y Hacienda.") in s.detalle
    paso = {p.nombre: p for p in s.pasos}["Cámara de Diputados"]
    assert (paso.estado, paso.detalle) == ("actual", "en comisión")
    filas = {k: "".join(f.texto for f in v) for k, v in contenido.datos_diputados_hcdn(r)}
    assert filas["Expediente en Diputados"] == "57-S-2026" and filas["Estado en Diputados"] == "En comisión."
    html = r.archivos["html"].read_text(encoding="utf-8")
    assert "<h2>Etapa en la Cámara de Diputados (revisión)</h2>" in html


def test_modificado_por_diputados_vuelve_al_senado(tmp_path):
    r = _informe("PE-13/26", tmp_path, formatos=("html", "docx"))
    s = r.situacion
    assert s.titulo == "Con modificaciones de Diputados: vuelve al Senado"
    assert any(d.startswith("La Cámara de Diputados lo aprobó con modificaciones el 21/10/2026: vuelve al Senado")
               for d in s.detalle)
    assert [(p.nombre, p.estado) for p in s.pasos][-3:] == [("Cámara de Diputados", "hecho"),
                                                            ("Vuelve al Senado", "actual"),
                                                            ("Ley y Poder Ejecutivo", "pendiente")]
    filas = {k: "".join(f.texto for f in v) for k, v in contenido.datos_diputados_hcdn(r)}
    assert filas["Dictamen en Diputados"] == "Orden del Día N° 448/2026 (16/10/2026): con modificaciones"
    assert filas["Votación en Diputados"] == "Aprobado con modificaciones el 21/10/2026: vuelve al Senado"
    assert filas["Giro en Diputados"] == "Asuntos Constitucionales y Legislacion General"
    with zipfile.ZipFile(r.archivos["docx"]) as z:
        assert "Etapa en la Cámara de Diputados (revisión)" in z.read("word/document.xml").decode("utf-8")


def test_rechazado_por_diputados(tmp_path):
    r = _informe("S-1167/25", tmp_path)
    s = r.situacion
    assert (s.nivel, s.titulo) == ("rechazado", "Rechazado por la Cámara de Diputados")
    assert ("Rechazado por la Cámara de Diputados el 08/10/2025: un proyecto desechado totalmente no puede "
            "repetirse en las sesiones de ese año (art. 81 CN).") in s.detalle
    pasos = {p.nombre: p for p in s.pasos}
    assert (pasos["Dictamen"].estado, pasos["Dictamen"].detalle) == ("hecho", "sin dictamen")     # sobre tablas
    assert (pasos["Cámara de Diputados"].estado, pasos["Cámara de Diputados"].detalle) == ("detenido", "rechazó")
    assert s.caducidad is None


def test_sancionado_por_diputados(tmp_path):
    r = _informe("PE-98/26", tmp_path)
    assert r.situacion.titulo == "Sancionado: Ley N° 27.818"
    assert {p.nombre: p.detalle for p in r.situacion.pasos}["Cámara de Diputados"] == "sancionó"
    filas = {k: "".join(f.texto for f in v) for k, v in contenido.datos_diputados_hcdn(r)}
    assert filas["Dictamen en Diputados"].endswith(": aconseja su sanción")


def test_seccion_de_origen_para_los_que_vienen_de_diputados(tmp_path):
    r = generar("CD-14/24", Opciones(carpeta_salida=tmp_path, formatos=("html",), buscar_reuniones=False,
                                     buscar_agenda=False), ClienteFalso(), hoy=HOY)
    assert contenido.titulo_etapa_diputados(r) == "Etapa en la Cámara de Diputados (origen)"
    assert "Etapa en la Cámara de Diputados (origen)" in contenido.texto_resumen(r)


def test_novedades_de_diputados_en_el_seguimiento(tmp_path):
    nueva = seguimiento.foto(_informe("S-361/26", tmp_path))
    vieja = json.loads(json.dumps(nueva))
    vieja.update({"diputados_numero": None, "diputados_giros": [], "diputados": vieja["diputados"][:1]})
    textos = [n.texto for n in seguimiento.comparar(vieja, nueva, HOY)]
    assert "El sitio de Diputados registra: pasó a Diputados." in textos
    assert "Ingresó a Diputados como expediente 57-S-2026." in textos
    assert ("Diputados lo giró a las comisiones de Recursos Naturales y Conservacion del Ambiente Humano y "
            "Presupuesto y Hacienda.") in textos
    con_dictamen = seguimiento.foto(_informe("PE-13/26", tmp_path))
    antes = json.loads(json.dumps(con_dictamen))
    antes["diputados_dictamenes"] = []
    assert "Dictamen en Diputados: Orden del Día N° 448/2026 del 16/10/2026, con modificaciones." in [
        n.texto for n in seguimiento.comparar(antes, con_dictamen, HOY)]
    rechazo = seguimiento.foto(_informe("S-1167/25", tmp_path))
    previo = json.loads(json.dumps(rechazo))
    previo["diputados"] = [m for m in previo["diputados"] if m[3] != "RECHAZADO"]
    assert "El sitio de Diputados registra: Diputados: rechazo total del proyecto (08/10/2025)." in [
        n.texto for n in seguimiento.comparar(previo, rechazo, HOY)]
