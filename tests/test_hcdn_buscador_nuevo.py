"""Lectura del buscador nuevo de Diputados (https://www.hcdn.gob.ar/proyectos/buscador/, API JSON, noviembre 2026).

Reglas: solo datos oficiales. Cada movimiento queda sin cámara ni resultado (la API no los publica), y un proyecto
del Senado solo se acepta si coincide con la ficha del Senado en una Orden del Día del Senado o en el número de ley.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from informe_expedientes import ficha as ficha_mod
from informe_expedientes import hcdn
from informe_expedientes.cliente import ErrorRed, Respuesta
from informe_expedientes.hcdn import buscar as buscar_api   # el real: conftest reemplaza hcdn.buscar
from informe_expedientes.identificador import parsear

FIX = Path(__file__).parent / "fixtures"

# 0065-S-2025 (PE-159/25 en el Senado), copiado de la respuesta del 16/11/2026; solo los campos que se usan.
API_0065_S_2025 = {
    "clave": "pap-289082", "expediente": "0065-S-2025", "tipo": "MENSAJE", "titulo": "LEY DE MODERNIZACION LABORAL.",
    "camara_origen": "Senado", "estado": "ley", "ley_nro": "27802", "fecha_presentacion": "2025-12-11",
    "publicacion_tipo": "DAE", "publicacion_numero": 105,
    "dictamenes": [{"camara": "Senado", "od_nro": 699, "od_anio": 2025, "fecha": "2025-12-18", "detalle": None},
                   {"camara": "Diputados", "od_nro": 6, "od_anio": 2025, "fecha": "2026-02-18", "detalle": None},
                   {"camara": "Senado", "od_nro": 706, "od_anio": 2025, "fecha": "2026-02-20", "detalle": None}],
    "movimientos": [{"fecha": "2026-02-11", "texto": "CITACION SESION ESPECIAL"}],
    "giros": [{"comision": "TRABAJO Y PREVISION SOCIAL", "camara": "Senado"},
              {"comision": "LEGISLACION DEL TRABAJO", "camara": "Diputados"}],
}
# Otro proyecto que comparte número con el S-65/25 del Senado (el caso que no hay que confundir).
OTRO = dict(API_0065_S_2025, clave="pap-1", ley_nro=None,
            dictamenes=[{"camara": "Senado", "od_nro": 1, "od_anio": 2025, "fecha": None, "detalle": None}])


def _ficha(numero, archivo):
    ident = parsear(numero).con_tipo("PL")
    return ficha_mod.parsear_ficha((FIX / archivo).read_text(encoding="utf-8", errors="ignore"), "", ident)


class _Cliente:
    """Responde según qué se busca: {parámetro=valor: [items]} y {clave: detalle}."""

    def __init__(self, busquedas=None, detalles=None, error=None, html=None):
        self.busquedas, self.detalles, self.error, self.html, self.urls = busquedas or {}, detalles or {}, error, html, []

    def get(self, url, ttl=None, binario=False):
        self.urls.append(url)
        if self.error:
            raise self.error
        if self.html:
            return Respuesta(url, 200, texto=self.html)
        if "/proyectos/pap-" in url:
            clave = url.rsplit("/", 1)[1]
            if clave not in self.detalles:
                raise ErrorRed(f"El sitio respondió con el código 404 para {url}.")
            return Respuesta(url, 200, texto=json.dumps(self.detalles[clave]))
        items = next((v for k, v in self.busquedas.items() if k in url), [])
        return Respuesta(url, 200, texto=json.dumps({"items": items, "total": len(items)}))


def _json(nombre):
    return json.loads((FIX / nombre).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ fuera de servicio

def test_pagina_en_construccion():
    with pytest.raises(hcdn.BuscadorFueraDeServicio):
        buscar_api(_Cliente(html="<title>Sección en construcción</title>"), _ficha("PE-159/25", "ficha_pe_159_25.html"))


def test_404_del_buscador():
    with pytest.raises(hcdn.BuscadorFueraDeServicio):
        buscar_api(_Cliente(error=ErrorRed("El sitio respondió con el código 404 para x.")),
                   _ficha("PE-159/25", "ficha_pe_159_25.html"))


def test_otro_error_de_red_sigue_igual():
    with pytest.raises(ErrorRed) as e:
        buscar_api(_Cliente(error=ErrorRed("No se pudo conectar con x (Timeout).")),
                   _ficha("PE-159/25", "ficha_pe_159_25.html"))
    assert not isinstance(e.value, hcdn.BuscadorFueraDeServicio)


# ------------------------------------------------------------------ venidos de Diputados (CD)

def test_cd_se_busca_con_el_numero_de_diputados_de_la_ficha():
    f = _ficha("CD-14/24", "ficha_cd_14_24.html")
    assert f.etapa_diputados.expedientes[0] == "0422-D-2024"
    c = _Cliente({"exp=0422-D-2024": _json("hcdn_api_0422_d_2024_busqueda.json")["items"]},
                 {"pap-273255": _json("hcdn_api_0422_d_2024.json")})
    p = buscar_api(c, f)
    assert p.expediente_diputados == "0422-D-2024" and p.expediente_senado == "0014-CD-2024"
    assert p.ley == "27757" and p.iniciado_en == "Diputados"
    assert p.giros_diputados == ["EDUCACION", "PRESUPUESTO Y HACIENDA"]
    assert p.giros_senado == ["EDUCACION Y CULTURA", "PRESUPUESTO Y HACIENDA"]
    assert [(d.camara, d.orden_del_dia, d.fecha) for d in p.dictamenes] == [
        ("Diputados", "0071/2024", date(2024, 5, 27)), ("Senado", "0146/2024", date(2024, 9, 3))]
    assert p.url == "https://www.hcdn.gob.ar/proyectos/buscador/?proyecto=pap-273255"


def test_no_se_inventa_camara_ni_resultado():
    p = hcdn.parsear_api(_json("hcdn_api_0422_d_2024.json"))
    assert p.tramite and all(m.camara == "" and m.resultado == "" for m in p.tramite)
    assert p.sanciones() == [] and p.rechazos() == []
    # Lo que sí se sabe por cámara sale de los dictámenes oficiales.
    assert p.estado("Diputados", "Diputados").clave == "con_dictamen"
    assert p.estado("Senado", "Diputados").clave == "con_dictamen"


# ------------------------------------------------------------------ del Senado: corroborar con la ficha

def test_pe_con_otro_numero_en_diputados_se_encuentra_por_orden_del_dia():
    """PE-159/25 figura en Diputados como 0065-S-2025: coincide en las OD 699/25 y 706/25 del Senado."""
    f = _ficha("PE-159/25", "ficha_pe_159_25.html")
    c = _Cliente({"od_nro=699": [API_0065_S_2025]}, {"pap-289082": API_0065_S_2025})
    p = buscar_api(c, f)
    assert "exp=0159-PE-2025" in c.urls[0]           # primero, por el número del Senado (no lo encuentra)
    assert p.expediente_diputados == "0065-S-2025" and p.expediente_senado == "0159-PE-2025"
    assert p.ley == "27802"


def test_mismo_numero_pero_otro_proyecto_no_se_acepta():
    f = _ficha("PE-159/25", "ficha_pe_159_25.html")
    with pytest.raises(hcdn.SinCorroborar):
        buscar_api(_Cliente({"exp=0159-PE-2025": [OTRO]}), f)


def test_senado_con_su_numero_y_su_od():
    f = _ficha("S-351/25", "ficha_s_351_25.html")
    item = _json("hcdn_api_0351_s_2025_busqueda.json")["items"][0]
    if not hcdn.corrobora(item, f):
        pytest.skip("la ficha guardada de S-351/25 es anterior a su Orden del Día 527/25")
    p = buscar_api(_Cliente({"exp=0351-S-2025": [item]}, {"pap-283604": _json("hcdn_api_0351_s_2025.json")}), f)
    assert p.expediente_diputados == "0351-S-2025" and p.iniciado_en == "Senado"


def test_sin_dato_en_comun_no_se_afirma_nada():
    f = _ficha("PE-159/25", "ficha_pe_159_25.html")
    with pytest.raises(hcdn.SinCorroborar):
        buscar_api(_Cliente(), f)


def test_od_clave():
    assert hcdn._od_clave("699/25") == (699, 2025) and hcdn._od_clave("0146/2024") == (146, 2024)
