"""Búsqueda por orden del día: sus expedientes forman un único despacho."""

import zipfile

from conftest import ClienteFalso

from informe_expedientes import orden_dia
from informe_expedientes.contenido import texto_resumen
from informe_expedientes.servicio import Opciones, generar


def test_numero_de_orden_del_dia():
    assert orden_dia.parsear_od("OD 366/26") == "366/26"
    assert orden_dia.parsear_od("O.D. N° 366/2026") == "366/26"
    assert orden_dia.parsear_od("Orden del Día 12/26") == "12/26"
    assert orden_dia.parsear_od("od-413-26") == "413/26"
    assert orden_dia.parsear_od("S-366/26") is None and orden_dia.parsear_od("366/26") is None


def test_informe_por_orden_del_dia(tmp_path):
    r = generar("OD 366/26", Opciones(buscar_reuniones=False, carpeta_salida=tmp_path), ClienteFalso())
    assert r.titulo == "OD 366/26" and r.ficha.id.corto == "S-718/26"          # la cabecera lleva la ficha
    assert [x.corto for x in r.od_expedientes] == ["S-718/26", "S-808/26", "S-865/26"]
    assert r.archivos["html"].name.startswith("Informe OD-366-26 (")
    html = r.archivos["html"].read_text(encoding="utf-8")
    assert '<h1 class="numero">Orden del Día N° 366/26</h1>' in html
    assert "Despacho único de la Orden del Día N° 366/26, integrado por TRES (3) expedientes" in html
    assert 'href="https://www.senado.gob.ar/parlamentario/comisiones/verExp/865.26/S/PL"' in html
    assert '<nav class="indice-doc"' in html                                     # índice de secciones
    with zipfile.ZipFile(r.archivos["docx"]) as z:
        assert "Orden del Día N° 366/26" in z.read("word/document.xml").decode("utf-8")
    assert texto_resumen(r).startswith("Orden del Día N° 366/26: S-718/26, S-808/26, S-865/26")
