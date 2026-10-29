import zipfile
from datetime import date

from conftest import ClienteFalso

from informe_expedientes import ejes
from informe_expedientes.busqueda import Consulta, Hallazgo, a_hallazgo, cumple, planificar, separar_palabras
from informe_expedientes.identificador import IdExpediente
from informe_expedientes.informe_tematico import tramos
from informe_expedientes.numeros import cantidad, en_letras
from informe_expedientes.tematico import OpcionesTematicas, generar_tematico, resumen

HOY = date(2026, 10, 29)


def test_numeros_en_forma_normativa():
    assert cantidad(21, "expediente", "expedientes") == "VEINTIÚN (21) expedientes"
    assert cantidad(1, "expediente", "expedientes") == "UN (1) expediente"
    assert cantidad(31, "reunión", "reuniones", femenino=True) == "TREINTA Y UNA (31) reuniones"
    assert en_letras(100) == "CIEN" and en_letras(101) == "CIENTO UN" and en_letras(2657) == \
        "DOS MIL SEISCIENTOS CINCUENTA Y SIETE"
    assert en_letras(16) == "DIECISÉIS" and en_letras(22) == "VEINTIDÓS" and en_letras(1000) == "MIL"


def test_palabras_y_filtros():
    assert separar_palabras("universidad, Universidad; educación\n") == ["universidad", "educación"]
    h = Hallazgo(IdExpediente(5, 2026, "S", "PL"), "PROYECTO DE LEY SOBRE EDUCACION Y UNIVERSIDADES NACIONALES")
    c = Consulta(palabras=["educación", "universidad"], modo="todas", anio_desde=2026, anio_hasta=2026)
    assert cumple(h, c) and h.coincidencias == ["educación", "universidad"]
    assert not cumple(h, Consulta(palabras=["educación"], excluir=["universidades"], anio_desde=2026, anio_hasta=2026))
    assert not cumple(h, Consulta(palabras=["ducacion"], anio_desde=2026, anio_hasta=2026))   # comienzo de palabra
    assert not cumple(h, Consulta(palabras=["educación"], tipos={"PD"}, anio_desde=2026, anio_hasta=2026))
    otro = Hallazgo(IdExpediente(5, 2026, "OV", "CV"), "UNIVERSIDAD NACIONAL: REMITE")
    assert cumple(otro, Consulta(palabras=["universidad"], tipos={"OTROS"}, anio_desde=2026, anio_hasta=2026))
    assert a_hallazgo({"expediente": "1/26", "tipo": "PL", "origen": "CD", "extracto": "x"}).ident == \
        IdExpediente(1, 2026, "CD", "PL")
    assert a_hallazgo({"expediente": "1/26", "tipo": "PL", "origen": "ZZ", "extracto": "x"}) is None


def test_plan_de_consultas():
    assert planificar(Consulta(palabras=["universidad"], anio_desde=2025, anio_hasta=2026)) == \
        [("universidad", 2025), ("universidad", 2026)]
    assert planificar(Consulta(palabras=["educación", "escuela"], anio_desde=2026, anio_hasta=2026)) == \
        [("educación", 2026), ("educacion", 2026), ("escuela", 2026)]
    assert planificar(Consulta(palabras=["universidad", "nacional"], modo="todas", anio_desde=2026,
                               anio_hasta=2026)) == [("universidad", 2026)]
    assert planificar(Consulta(comision_id=75, anio_desde=2026, anio_hasta=2026)) == [("", 2026)]


def test_resaltado_sin_tildes():
    t = tramos("CREA LA UNIVERSIDAD Y FINANCIA UNIVERSIDADES; EDUCACIÓN", ["universidad", "educacion"])
    assert [x for x, m in t if m] == ["UNIVERSIDAD", "UNIVERSIDADES", "EDUCACIÓN"]


def test_ejes_guardar_y_cargar(tmp_path):
    archivo = tmp_path / "ejes.json"
    assert ejes.cargar_ejes(archivo)[0].nombre == "Educación y universidades"
    propios = ejes.cargar_ejes(archivo) + [ejes.Eje("Mi eje", ["litio"], comision_id=65)]
    ejes.guardar_ejes(propios, archivo)
    vuelta = ejes.cargar_ejes(archivo)
    assert ejes.buscar_eje("mi EJE", vuelta).comision_id == 65
    archivo.write_text("no es json", encoding="utf-8")
    assert len(ejes.cargar_ejes(archivo)) == len(ejes.EJES_INICIALES)


def test_informe_tematico_completo(tmp_path):
    cliente = ClienteFalso()
    consulta = Consulta(palabras=["universidad"], anio_desde=2023, anio_hasta=2026, tipos={"PL", "PR", "PC"})
    res = generar_tematico(consulta, OpcionesTematicas(carpeta_salida=tmp_path), cliente, hoy=HOY)

    assert [it.hallazgo.ident.corto for it in res.items] == ["CD-14/24", "CD-35/23", "S-359/26", "S-342/26",
                                                            "CD-37/23"]
    assert [it.nivel for it in res.items] == ["vetado", "caducado", "error", "error", "error"]
    assert res.estadisticas["consultas"] == 4
    assert resumen(res) == ("Se identificaron CINCO (5) expedientes que mencionan «universidad» en su extracto, "
                            "ingresados entre 2023 y 2026: UN (1) vetado, UN (1) caducado y TRES (3) cuyas fichas "
                            "no se pudieron leer.")
    assert set(res.archivos) == {"docx", "html", "xlsx"}
    html = res.archivos["html"].read_text(encoding="utf-8")
    assert "<mark>UNIVERSIDADES</mark>" in html and "Vetado (1)" in html
    assert 'href="https://www.senado.gob.ar/parlamentario/comisiones/verExp/14.24/CD/PL"' in html
    with zipfile.ZipFile(res.archivos["xlsx"]) as z:
        hoja_resumen = z.read("xl/worksheets/sheet2.xml").decode("utf-8")
    assert "COUNTIF(Expedientes!$E$2:$E$6" in hoja_resumen
    post = cliente.ultimo_post
    assert post["busqueda_proyectos[palabra]"] == "universidad"
    assert post["busqueda_proyectos[tipoDocumento]"] == "EX"


def test_limite_y_sin_detalle(tmp_path):
    consulta = Consulta(palabras=["universidad"], anio_desde=2023, anio_hasta=2026, tipos={"PL"})
    res = generar_tematico(consulta, OpcionesTematicas(carpeta_salida=tmp_path, limite=2, formatos=("html",)),
                           ClienteFalso(), hoy=HOY)
    assert res.limite_aplicado and res.detallados == 2
    assert any("primeros 2 de 5" in a for a in res.advertencias)
    rapido = generar_tematico(consulta, OpcionesTematicas(carpeta_salida=tmp_path, detallar=False,
                                                          formatos=("docx", "xlsx")), ClienteFalso(), hoy=HOY)
    assert rapido.detallados == 0 and all(it.nivel is None for it in rapido.items)
    assert resumen(rapido).endswith("ingresados entre 2023 y 2026.")


def test_informes_individuales(tmp_path):
    consulta = Consulta(palabras=["financiamiento"], anio_desde=2024, anio_hasta=2024, tipos={"PL"})
    res = generar_tematico(consulta, OpcionesTematicas(carpeta_salida=tmp_path, informes_individuales=True,
                                                       formatos=("html",)), ClienteFalso(), hoy=HOY)
    item = res.items[0]
    assert item.hallazgo.ident.corto == "CD-14/24"
    assert item.informes["html"].exists() and item.reuniones_buscadas
    assert 'href="Informes completos' in res.archivos["html"].read_text(encoding="utf-8")


def test_linea_de_comandos_tematica(tmp_path, monkeypatch, capsys):
    import app
    monkeypatch.setattr(app, "Cliente", lambda *a, **k: ClienteFalso())
    codigo = app.linea_de_comandos(["--tema", "educación y universidades", "--anios", "2024", "--palabras",
                                    "financiamiento", "--salida", str(tmp_path), "--nombre", "index",
                                    "--formatos", "html"])
    salida = capsys.readouterr().out
    assert codigo == 0 and (tmp_path / "index.html").exists()
    assert "UN (1) expediente" in salida
    assert app.linea_de_comandos(["--tema", "No existe", "--salida", str(tmp_path)]) == 2
