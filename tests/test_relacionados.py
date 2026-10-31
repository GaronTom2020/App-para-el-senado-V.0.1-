"""Expedientes relacionados (Fase 5): tratados en conjunto y tenidos a la vista."""

import zipfile
from datetime import date

from conftest import FIXTURES, ClienteFalso, leer

from informe_expedientes import contenido, hcdn, plan_labor, relacionados as R
from informe_expedientes.ficha import parsear_ficha
from informe_expedientes.identificador import IdExpediente, encontrar
from informe_expedientes.modelos import Reunion
from informe_expedientes.servicio import Opciones, generar

HOY = date(2026, 10, 31)


def _cortos(idents):
    return [i.corto for i in idents]


def _dictamen(nombre):
    return R.texto_dictamen((FIXTURES / nombre).read_bytes())


def test_dictamen_considerado_y_a_la_vista():
    od146 = _dictamen("od_2024_146.pdf")
    assert _cortos(R.considerados(od146)) == ["CD-14/24"]
    assert _cortos(R.a_la_vista(od146)) == ["S-285/24", "S-637/24", "S-638/24", "S-984/24", "S-1092/24", "S-1560/24"]
    od366 = _dictamen("od_2026_366.pdf")
    assert _cortos(R.considerados(od366)) == ["S-808/26", "S-865/26", "S-718/26"]       # dictamen conjunto
    assert R.a_la_vista(od366) == []


def test_observaciones_de_la_ficha():
    obs = ("03/09/2024.- DICTAMEN EN EL EXPTE. C.D. 14/24, TENIENDO A LA VISTA LOS EXPTES. S. 285-637-638-984- 1092 "
           "Y 1560/24.- VETO TOTAL REF. P.E.107/24 09-10-2024")
    assert _cortos(R.a_la_vista(obs)) == ["S-285/24", "S-637/24", "S-638/24", "S-984/24", "S-1092/24", "S-1560/24"]
    assert _cortos(i for _p, i in encontrar("08/09/26: DICT. CONJ. S. 808/26, 865/26 FIRMA DISIDENCIA")) == [
        "S-808/26", "S-865/26"]


def test_temarios_de_reuniones():
    assert _cortos(R.temario(leer("nota_21973.html"))) == ["CD-14/24", "S-285/24", "S-637/24", "S-638/24",
                                                          "S-984/24", "S-1092/24", "S-1560/24"]
    assert _cortos(R.temario(leer("nota_24293.html"))) == ["S-808/26", "S-865/26", "S-718/26"]


def test_detectar_con_todas_las_fuentes():
    ident = IdExpediente(14, 2024, "CD", "PL")
    f = parsear_ficha(leer("ficha_cd_14_24.html"), ident.url_ficha(), ident)
    p = next(x for x in hcdn.parsear_resultado(leer("hcdn_cd_14_24.html")) if x.expediente_senado == "0014-CD-2024")
    ods = {"146/24": plan_labor.expedientes_de_od(leer("od_2024_146.html"))}
    reunion = Reunion("u", "21973", "Plenario", date(2024, 9, 3), [], "Plenario")
    lista = R.detectar(f, ods, {"146/24": _dictamen("od_2024_146.pdf")}, p,
                       [(reunion, R.temario(leer("nota_21973.html")))])
    relaciones = {r.ident.corto: r.texto_relacion() for r in lista}
    assert relaciones["S-285/24"] == "Tenido a la vista en el dictamen (Orden del Día N° 146/24)"
    assert relaciones["PE-107/24"] == "Citado en las observaciones de la ficha"           # el mensaje del veto
    assert "CD-14/24" not in relaciones                                                  # no se cita a sí mismo
    assert [r.ident.corto for r in lista][:6] == ["S-285/24", "S-637/24", "S-638/24", "S-984/24", "S-1092/24",
                                                  "S-1560/24"]


def test_conjunto_en_la_ficha_y_en_diputados():
    ident = IdExpediente(159, 2025, "PE", "PL")
    f = parsear_ficha(leer("ficha_pe_159_25.html"), ident.url_ficha(), ident)
    p = next(x for x in hcdn.parsear_resultado(leer("hcdn_pe_159_25.html")) if x.expediente_senado == "0159-PE-2025")
    [relacionado] = R.detectar(f, diputados=p)
    assert relacionado.ident.corto == "PE-186/25"
    assert relacionado.texto_relacion() == "Tratado en conjunto (ficha del Senado)"
    assert relacionado.relaciones[R.CONJUNTO_SANCION] == "tratado en conjunto (ficha del Senado)"


def test_reunion_con_muchos_temas_no_cuenta_como_conjunto():
    f = parsear_ficha(leer("ficha_s_351_25.html"), "u", IdExpediente(351, 2025, "S", "PL"))
    muchos = [IdExpediente(n, 2025, "S") for n in range(1, 12)]
    reunion = Reunion("u", "1", "Reunión", date(2025, 9, 1), [], "Comisión")
    assert R.detectar(f, reuniones=[(reunion, muchos)]) == []
    pocos = R.detectar(f, reuniones=[(reunion, muchos[:3])])
    assert pocos[0].texto_relacion() == "Tratado en la misma reunión de comisión (01/09/2025)"


def test_informe_con_relacionados_y_su_situacion(tmp_path):
    r = generar("S-718/26", Opciones(tipo="PL", carpeta_salida=tmp_path, formatos=("html", "docx"),
                                     buscar_reuniones=False, buscar_agenda=False), ClienteFalso(), hoy=HOY)
    assert contenido.texto_relacionados(r) == "Se encontraron DOS (2) expedientes relacionados."
    filas = [(e.texto, e.url, rel, sit) for e, rel, sit in contenido.filas_relacionados(r)]
    assert filas[0] == ("S-808/26", "https://www.senado.gob.ar/parlamentario/comisiones/verExp/808.26/S/PL",
                        "Dictaminado en conjunto (Orden del Día N° 366/26)", "Media sanción del Senado")
    assert [x[0] for x in filas] == ["S-808/26", "S-865/26"]
    html = r.archivos["html"].read_text(encoding="utf-8")
    assert "<h2>Expedientes relacionados</h2>" in html and "Dictaminado en conjunto" in html
    with zipfile.ZipFile(r.archivos["docx"]) as z:
        assert "Expedientes relacionados" in z.read("word/document.xml").decode("utf-8")
    assert "Expedientes relacionados" in contenido.texto_resumen(r)


def test_relacionado_sin_ficha_y_opcion_apagada(tmp_path):
    r = generar("CD-14/24", Opciones(carpeta_salida=tmp_path, formatos=("html",), buscar_reuniones=False,
                                     buscar_agenda=False), ClienteFalso(), hoy=HOY)
    assert len(r.relacionados) == 7
    sin_ficha = dict((e.texto, s) for e, _rel, s in contenido.filas_relacionados(r))
    assert sin_ficha["S-285/24"] == "no se pudo leer la ficha"                             # no hay copia de prueba
    apagado = generar("CD-14/24", Opciones(carpeta_salida=tmp_path, formatos=("html",), buscar_reuniones=False,
                                           buscar_agenda=False, buscar_relacionados=False), ClienteFalso(), hoy=HOY)
    assert apagado.relacionados == [] and not apagado.relacionados_consultados
    assert "Expedientes relacionados" not in apagado.archivos["html"].read_text(encoding="utf-8")
