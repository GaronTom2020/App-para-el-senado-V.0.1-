import re
from datetime import date

import pytest
from conftest import leer

from informe_expedientes import situacion
from informe_expedientes.ficha import parsear_expedientes_hcd, parsear_ficha, tipo_desde_resultados
from informe_expedientes.identificador import ErrorIdentificador, IdExpediente, parsear, separar_lote

HOY = date(2026, 10, 19)


# ---------------------------------------------------------------- identificador

@pytest.mark.parametrize("texto, esperado", [
    ("S-1234/24", ("S", 1234, 2024, None)),
    ("s 1234/2024", ("S", 1234, 2024, None)),
    ("C.D.-14/24", ("CD", 14, 2024, None)),
    ("CD-14/24-PL", ("CD", 14, 2024, "PL")),
    ("PE 107/24 PL", ("PE", 107, 2024, "PL")),
    ("P.E.N. 107/24", ("PE", 107, 2024, None)),
    ("1370-S-2020", ("S", 1370, 2020, None)),
    ("Expte. S-830/24", ("S", 830, 2024, None)),
    ("EXPEDIENTE N° OV-484/26", ("OV", 484, 2026, None)),
    ("https://www.senado.gob.ar/parlamentario/comisiones/verExp/14.24/CD/PL", ("CD", 14, 2024, "PL")),
    ("https://www.senado.gob.ar/parlamentario/parlamentaria/verExp/parla/S-2025.06-PC", ("S", 2025, 2006, "PC")),
    ("JGM-3/25", ("JGM", 3, 2025, None)),
])
def test_parsear_formatos(texto, esperado):
    i = parsear(texto)
    assert (i.origen, i.numero, i.anio, i.tipo) == esperado


@pytest.mark.parametrize("texto", ["1234/24", "1888-D-24", "XX-1/24", "S-0/24", "hola", ""])
def test_parsear_errores(texto):
    with pytest.raises(ErrorIdentificador):
        parsear(texto)


def test_tipo_por_defecto_y_lote():
    assert parsear("S-1/26", tipo="PD").tipo == "PD"
    assert separar_lote("S-1/26\nCD-14/24; PE-3/25 , \n") == ["S-1/26", "CD-14/24", "PE-3/25"]


def test_patron_texto_no_confunde_numeros():
    patron = IdExpediente(351, 2025, "S").patron_texto()
    assert patron.search("Expte. S-351/25, GALARETTO")
    assert patron.search("expte. s 351/2025")
    assert patron.search("Expediente 351-S-2025")
    assert not patron.search("S-1351/25")
    assert not patron.search("CD-351/25")
    assert not patron.search("S-351/24")
    cd = IdExpediente(35, 2023, "CD").patron_texto()
    assert cd.search("EXPTE. C.D.-35/23") and not cd.search("CD-135/23")


def test_coincide_url():
    i = IdExpediente(35, 2023, "CD")
    assert i.coincide_url("https://www.senado.gob.ar/parlamentario/comisiones/verExp/35.23/CD/PL")
    assert i.coincide_url("/parlamentario/comisiones/verExp/35.2023/cd/PL")
    assert not i.coincide_url("/parlamentario/comisiones/verExp/37.23/CD/PL")


# ---------------------------------------------------------------- ficha

def ficha(nombre, ident):
    return parsear_ficha(leer(nombre), ident.url_ficha(), ident)


def test_ficha_cd_35_23():
    ident = IdExpediente(35, 2023, "CD", "PL")
    f = ficha("ficha_cd_35_23.html", ident)
    assert f.numero_texto == "35/23"
    assert f.origen_texto == "Cámara De Diputados"
    assert f.extracto.startswith("PROYECTO DE LEY EN REVISION QUE CREA LA UNIVERSIDAD")
    assert f.etapa_diputados.expedientes == ["1752-D-2023"]
    assert f.etapa_diputados.orden_del_dia == "736"
    assert f.etapa_diputados.tramite_parlamentario == "42"
    assert f.etapa_diputados.fecha_sancion == date(2023, 10, 10)
    assert f.fecha_mesa_entradas == date(2023, 10, 12)
    assert f.fecha_dado_cuenta == date(2024, 4, 18)
    assert (f.dae, f.dae_tipo) == ("108/2023", "NORMAL")
    assert len(f.ingresos_comisiones) == 2
    assert len(f.giros) == 4
    assert f.giros[0].comision == "DE EDUCACIÓN Y CULTURA" and f.giros[0].orden == 1
    assert f.giros[0].egreso == date(2026, 6, 17)
    assert f.fecha_caducidad_registrada == date(2026, 2, 28)
    assert f.fecha_archivo == date(2026, 6, 22)
    assert f.mocion_preferencia == date(2025, 9, 18) and f.mocion_para == "C/DESPACHO"
    assert f.observaciones and f.observaciones[0].startswith("06-02-2024- VUELVE")
    assert f.anotaciones == []
    assert [o.numero for o in f.ordenes_del_dia] == ["234/23"]
    assert f.ordenes_del_dia[0].situacion == "caduca"
    assert f.texto_original.url.endswith("/475915/downloadPdf")
    assert f.texto_definitivo_pendiente
    assert f.resoluciones == []
    assert not f.advertencias


def test_ficha_cd_14_24_resoluciones():
    ident = IdExpediente(14, 2024, "CD", "PL")
    f = ficha("ficha_cd_14_24.html", ident)
    assert f.etapa_diputados.expedientes == [
        "0422-D-2024", "1324-D-2024", "1415-D-2024", "1416-D-2024", "1888-D-2024"]
    assert f.etapa_diputados.orden_del_dia == "71"
    titulos = [b.titulo for b in f.resoluciones]
    assert titulos == ["SENADO", "SANCION DE LEY", "PODER EJECUTIVO DE LA NACION"]
    assert f.bloque("SANCION DE LEY").valor("NUMERO DE LEY") == "27757"
    assert f.bloque("PODER EJECUTIVO").valor("RESOLUCION") == "Veto Total"
    assert f.bloque("SENADO", exacto=True).valor("COMENTARIO") is None
    assert f.textos_definitivos and "27757" in f.textos_definitivos[0].etiqueta
    assert f.ordenes_del_dia[0].situacion == "aprobada"


def test_ficha_s_351_25_autores_y_anotaciones():
    ident = IdExpediente(351, 2025, "S", "PL")
    f = ficha("ficha_s_351_25.html", ident)
    assert [a.nombre for a in f.autores] == [
        "Galaretto, Eduardo Horacio", "Abad, Maximiliano", "Losada, Carolina", "Zimmermann, Victor"]
    assert f.autores[0].url == "https://www.senado.gob.ar/senadores/senador/573"
    assert f.autores[3].url is None
    assert f.giros[0].abierto and not f.giros[1].abierto
    assert f.anotaciones == ["31-07-25 INC. DE FIRMA SDOR. ABAD (F. 6)"]


def test_ficha_sin_atributos_summary():
    """Si el sitio quitara los summary, las tablas se reconocen por sus columnas."""
    html = re.sub(r'\s+summary="[^"]*"', "", leer("ficha_s_351_25.html"))
    ident = IdExpediente(351, 2025, "S", "PL")
    f = parsear_ficha(html, ident.url_ficha(), ident)
    assert len(f.autores) == 4 and len(f.giros) == 2
    assert f.fecha_mesa_entradas == date(2025, 3, 27)


def test_expedientes_hcd_variantes():
    assert parsear_expedientes_hcd("839; 1626; 1802; 2173; 2581; Y 2792-D- 25 OD 924") == (
        ["0839-D-2025", "1626-D-2025", "1802-D-2025", "2173-D-2025", "2581-D-2025", "2792-D-2025"], "924")
    assert parsear_expedientes_hcd("1752-D-23 OD736") == (["1752-D-2023"], "736")
    assert parsear_expedientes_hcd("0012-PE-2024 Y 33-D-24") == (["0012-PE-2024", "0033-D-2024"], None)


def test_tipo_desde_resultados_respeta_origen():
    html = leer("resultados_avanzada.html")
    assert tipo_desde_resultados(html, IdExpediente(35, 2023, "CD")) == "PL"
    assert tipo_desde_resultados(html, IdExpediente(35, 2023, "OV")) == "CV"
    assert tipo_desde_resultados(html, IdExpediente(36, 2023, "CD")) is None


# ---------------------------------------------------------------- situación

def test_situacion_caducado():
    f = ficha("ficha_cd_35_23.html", IdExpediente(35, 2023, "CD", "PL"))
    s = situacion.calcular(f, HOY)
    assert s.nivel == "caducado"
    assert s.titulo == "Caducó el 28/02/2026"
    assert "Enviado al archivo el 22/06/2026." in s.detalle
    assert any("con despacho de comisión" in d for d in s.detalle)
    assert s.caducidad.registrada and s.caducidad.fecha == date(2026, 2, 28)
    estados = {p.nombre: p.estado for p in s.pasos}
    assert estados["Sanción de Diputados"] == "hecho"
    assert estados["Dictamen"] == "detenido"


def test_caducidad_estimada_coincide_con_la_registrada():
    """La regla de tres años para proyectos de Diputados da la misma fecha que registró el Senado."""
    f = ficha("ficha_cd_35_23.html", IdExpediente(35, 2023, "CD", "PL"))
    f.fecha_caducidad_registrada = None
    f.fecha_archivo = None
    for g in f.giros[:2]:
        g.egreso = None      # como si siguiera en comisión
    s = situacion.calcular(f, date(2025, 11, 1))
    assert s.nivel == "en_comision"
    assert not s.caducidad.registrada
    assert s.caducidad.fecha == date(2026, 2, 28)


def test_situacion_ley_vetada():
    f = ficha("ficha_cd_14_24.html", IdExpediente(14, 2024, "CD", "PL"))
    s = situacion.calcular(f, HOY)
    assert s.nivel == "vetado"
    assert s.titulo.startswith("Sancionado: Ley N° 27.757")
    assert any("Decreto 879/24" in d for d in s.detalle)
    assert any("sin despacho de comisión" in d for d in s.detalle)
    assert s.caducidad is None
    # Con veto, el último paso es la insistencia del art. 83 de la Constitución.
    assert [p.nombre for p in s.pasos][-2:] == ["Ley y Poder Ejecutivo", "Insistencia"]
    assert [p.estado for p in s.pasos] == ["hecho"] * 5 + ["detenido", "pendiente"]
    assert any("puede insistir con dos tercios" in d and "art. 83 CN" in d for d in s.detalle)


def test_situacion_en_comision_tras_renovacion():
    f = ficha("ficha_s_351_25.html", IdExpediente(351, 2025, "S", "PL"))
    s = situacion.calcular(f, HOY)
    assert s.nivel == "en_comision"
    assert s.titulo == "En comisión: Salud"
    assert any("caducó por la renovación bienal" in d for d in s.detalle)
    assert s.caducidad.fecha == date(2027, 2, 28) and not s.caducidad.vencida
    estados = {p.nombre: p.estado for p in s.pasos}
    assert estados["Comisión"] == "actual" and estados["Dictamen"] == "pendiente"
