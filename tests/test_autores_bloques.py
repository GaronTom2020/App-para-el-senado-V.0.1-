"""Búsqueda por autor y por bloque (Fase 4), con las exportaciones reales del Senado de 2026."""

from datetime import date

from conftest import ClienteFalso, leer

from informe_expedientes import senadores
from informe_expedientes.busqueda import Consulta, planificar
from informe_expedientes.tematico import OpcionesTematicas, generar_tematico, resumen

HOY = date(2026, 10, 31)


def _bloques():
    return senadores.parsear_bloques(leer("senadores_bloques.html"))


def _autores():
    return senadores.parsear_autores(leer("buscador.html"))


def test_autores_del_buscador_avanzado():
    autores = _autores()
    assert len(autores) == 478
    mendoza = next(s for s in autores if s.id == 540)
    assert (mendoza.nombre, mendoza.legible) == ("MENDOZA,SANDRA MARIELA", "Mendoza, Sandra Mariela")


def test_bloques_actuales_con_sus_integrantes():
    bloques = _bloques()
    assert len(bloques) == 14 and sum(len(x) for x in bloques.values()) == 72
    assert {s.id for s in bloques["Convicción Federal"]} == {554, 519, 540}
    assert len(bloques["Justicialista"]) == 22 and len(bloques["La Libertad Avanza"]) == 21


def test_buscar_senador_y_bloque():
    autores, bloques = _autores(), _bloques()
    assert [s.id for s in senadores.buscar_senador("Mendoza", autores)] == [540]
    assert [s.id for s in senadores.buscar_senador("mendoza sandra", autores)] == [540]
    assert [s.id for s in senadores.buscar_senador("540", autores)] == [540]
    assert len(senadores.buscar_senador("López", autores)) == 4                 # hay que precisar
    assert [s.id for s in senadores.buscar_senador("Fernández Sagasti", autores)] == [468]
    assert senadores.buscar_senador("zzz", autores) == []
    assert senadores.buscar_bloque("convicción federal", bloques) == "Convicción Federal"
    assert senadores.buscar_bloque("radical", bloques) == "UCR - Unión Cívica Radical"
    assert senadores.buscar_bloque("frente", bloques) is None                   # ambiguo
    assert senadores.carpeta_bloque("UCR - Unión Cívica Radical") == "ucr-union-civica-radical"


def test_plan_de_consultas_por_autor():
    mendoza = senadores.Senador(540, "MENDOZA,SANDRA MARIELA")
    c = Consulta(palabras=["salud", "hospital"], anio_desde=2025, anio_hasta=2026, autores=[mendoza])
    assert planificar(c) == [("", 2025, 540), ("", 2026, 540)]                 # las palabras se filtran después
    assert c.titulo() == "salud, hospital — Mendoza, Sandra Mariela"
    assert ("Autor", "Mendoza, Sandra Mariela (como autor o coautor)") in c.criterios()


def test_busqueda_por_autor_incluye_coautorias(tmp_path):
    cliente = ClienteFalso()
    mendoza = senadores.Senador(540, "MENDOZA,SANDRA MARIELA")
    c = Consulta(anio_desde=2026, anio_hasta=2026, tipos={"PL"}, autores=[mendoza])
    res = generar_tematico(c, OpcionesTematicas(carpeta_salida=tmp_path, detallar=False, formatos=("html",)),
                           cliente, hoy=HOY)
    assert cliente.ultimo_post["busqueda_proyectos[autor]"] == "540"
    assert cliente.ultimo_post["busqueda_proyectos[expedienteTipo]"] == "PL"
    assert resumen(res) == ("Se identificaron VEINTIOCHO (28) expedientes con la firma de Mendoza, Sandra Mariela, "
                            "ingresados en 2026.")
    # «MOISES Y OTROS: …»: el sitio devuelve también los proyectos que firmó como coautora.
    s_1844 = next(it for it in res.items if it.hallazgo.ident.corto == "S-1844/26")
    assert s_1844.hallazgo.extracto.startswith("MOISES Y OTROS")
    assert "Mendoza, Sandra Mariela" in res.archivos["html"].read_text(encoding="utf-8")


def test_busqueda_por_autor_y_palabras(tmp_path):
    mendoza = senadores.Senador(540, "MENDOZA,SANDRA MARIELA")
    c = Consulta(palabras=["salud"], anio_desde=2026, anio_hasta=2026, tipos=None, autores=[mendoza])
    res = generar_tematico(c, OpcionesTematicas(carpeta_salida=tmp_path, detallar=False, formatos=()), ClienteFalso(),
                           hoy=HOY)
    assert resumen(res) == ("Se identificaron TRES (3) expedientes que mencionan «salud» en su extracto y llevan la "
                            "firma de Mendoza, Sandra Mariela, ingresados en 2026.")


def test_busqueda_por_bloque(tmp_path):
    bloques = _bloques()
    c = Consulta(anio_desde=2026, anio_hasta=2026, tipos={"PL"}, autores=bloques["Convicción Federal"],
                 bloque="Convicción Federal")
    res = generar_tematico(c, OpcionesTematicas(carpeta_salida=tmp_path, detallar=False, formatos=("html", "xlsx")),
                           ClienteFalso(), hoy=HOY)
    assert res.estadisticas["consultas"] == 3                                   # una por integrante y año
    assert resumen(res) == ("Se identificaron TREINTA Y CUATRO (34) expedientes con la firma de algún integrante "
                            "del bloque Convicción Federal, ingresados en 2026.")
    assert c.titulo() == "Bloque Convicción Federal"
    criterio = dict(c.criterios())["Bloque"]
    assert criterio.startswith("Convicción Federal: proyectos con la firma de alguno de sus integrantes actuales")
    assert len({it.hallazgo.ident.corto for it in res.items}) == 34              # sin repetir los firmados por varios


def test_linea_de_comandos_por_autor_y_bloque(tmp_path, monkeypatch, capsys):
    import app
    monkeypatch.setattr(app, "Cliente", lambda *a, **k: ClienteFalso())
    assert app.linea_de_comandos(["--listar-bloques"]) == 0
    salida = capsys.readouterr().out
    assert "Convicción Federal (3)\n" in salida and "Justicialista (22)\n" in salida
    assert app.linea_de_comandos(["--autor", "López", "--anios", "2026", "--salida", str(tmp_path)]) == 2
    error = capsys.readouterr().err
    assert "coincide con 5 senadores" in error and "López, Claudia Cecilia (597)" in error    # recién jurada
    assert app.linea_de_comandos(["--autor", "Mendoza", "--anios", "2026", "--tipos", "PL", "--sin-detalle",
                                  "--salida", str(tmp_path), "--nombre", "mendoza", "--formatos", "html"]) == 0
    assert "VEINTIOCHO (28) expedientes con la firma de Mendoza" in capsys.readouterr().out
    assert (tmp_path / "mendoza.html").exists()
    assert app.linea_de_comandos(["--bloque", "Inexistente", "--anios", "2026", "--salida", str(tmp_path)]) == 2
    codigo = app.linea_de_comandos(["--por-bloque", "--bloque", "convicción", "--anios", "2026", "--tipos", "PL",
                                    "--sin-detalle", "--salida", str(tmp_path / "bloques")])
    assert codigo == 0
    indice = (tmp_path / "bloques" / "index.html").read_text(encoding="utf-8")
    assert 'href="conviccion-federal/index.html"' in indice and "TREINTA Y CUATRO (34)" in indice
    assert (tmp_path / "bloques" / "conviccion-federal" / "index.html").exists()
    assert (tmp_path / "bloques" / "conviccion-federal" / "index.xlsx").exists()


def test_senadores_que_el_buscador_todavia_no_tiene():
    autores, bloques = _autores(), _bloques()
    assert not senadores.buscar_senador("López Claudia", autores)
    completos = senadores.con_integrantes(autores, bloques)
    assert [s.id for s in senadores.buscar_senador("López Claudia", completos)] == [597]
    assert len(completos) == len(autores) + 1
