"""Asuntos entrados: los DAE nuevos desde la última revisión."""

from datetime import date

import pytest
from conftest import ClienteFalso, leer

from informe_expedientes import asuntos_entrados as ae


def test_leer_un_dae():
    assert ae.ultimos(leer("dae_2026_84.html"))[:3] == [(84, 2026), (83, 2026), (82, 2026)]
    asuntos = ae.leer_dae(leer("dae_2026_84.html"))
    assert len(asuntos) == 20
    primero = asuntos[0]
    assert (primero.fecha, primero.dae, primero.expediente, primero.tipo) == ("2026-10-21", "84/2026", "PE-13/26", "PL")
    assert primero.giros == ["Asuntos Constitucionales", "Legislación General"]
    assert primero.url_ficha == "https://www.senado.gob.ar/parlamentario/comisiones/verExp/13.26/PE/PL"


def test_primera_revision_desde_una_fecha_y_despues_solo_lo_nuevo(tmp_path):
    registro = ae.Registro.cargar(tmp_path / "ae.json")
    with pytest.raises(ValueError):
        ae.revisar(ClienteFalso(), registro)                          # la primera vez hace falta la fecha
    res = ae.revisar(ClienteFalso(), registro, desde=date(2026, 10, 21))
    assert res.daes == ["84/2026", "83/2026", "82/2026"]                # el 82 ya trae asuntos anteriores
    assert all(a.fecha >= "2026-10-21" for a in res.asuntos) and len(res.asuntos) >= 20
    assert res.asuntos[0].fecha >= res.asuntos[-1].fecha                  # lo más nuevo primero
    vuelta = ae.Registro.cargar(tmp_path / "ae.json")
    assert vuelta.ultimo_dae == (84, 2026) and vuelta.desde == "2026-10-21"
    assert len(vuelta.ultimos_asuntos) == len(res.asuntos)
    otra = ae.revisar(ClienteFalso(), vuelta)                           # no hay DAE nuevos
    assert otra.asuntos == [] and otra.daes == []
    assert ae.resumen(otra) == "No hay Diarios de Asuntos Entrados nuevos desde la última revisión."


def test_filtros():
    asuntos = ae.leer_dae(leer("dae_2026_84.html"))
    leyes = ae.filtrar(asuntos, {"PL"})
    assert leyes and all(a.tipo == "PL" for a in leyes)
    assert all(a.origen == "CD" for a in ae.filtrar(asuntos, origen="CD"))
    assert [a.expediente for a in ae.filtrar(asuntos, texto="discapacidad")] == ["CD-18/26"]
    assert [a.expediente for a in ae.filtrar(asuntos, texto="salud", tipos={"PL"})] == ["CD-20/26"]


def test_ultimo_dae_de_un_periodo_cerrado():
    assert ae.leer_dae(leer("dae_vacio.html")) == []                    # un DAE inexistente viene sin registros
    asuntos = ae.leer_dae(leer("dae_2025_111.html"))
    assert asuntos and all(a.fecha.startswith("2026-02") for a in asuntos)   # período 2025: llega a febrero de 2026
    cliente = ClienteFalso()
    assert ae.ultimo_de(cliente, 2025) == 111
    assert len(cliente.pedidos) < 12                                    # búsqueda binaria, no uno por uno


def _sinteticos(monkeypatch, pedidos):
    """DAE de mentira para recorrer el cambio de período: 1/2026 es de marzo, 111 y 110/2025 de febrero."""
    fechas = {(1, 2026): "2026-03-02", (111, 2025): "2026-02-25", (110, 2025): "2026-02-13",
              (109, 2025): "2026-02-02"}

    def bajar(_cliente, numero, anio):
        pedidos.append((numero, anio))
        if (numero, anio) in fechas:
            return [ae.Asunto(fechas[(numero, anio)], f"{numero}/{anio}", f"S-{numero}/26", "S", "PD")]
        if anio == 2026 and numero <= 83:
            return [ae.Asunto("2026-06-01", f"{numero}/{anio}", f"S-{1000 + numero}/26", "S", "PL")]
        return []

    monkeypatch.setattr(ae, "bajar_dae", bajar)
    monkeypatch.setattr(ae, "ultimo_de", lambda _c, anio: 111 if anio == 2025 else 0)


def test_la_primera_busqueda_cruza_al_periodo_anterior(tmp_path, monkeypatch):
    pedidos = []
    _sinteticos(monkeypatch, pedidos)
    monkeypatch.setattr(ae, "MAX_DAE", 200)
    res = ae.revisar(ClienteFalso(), ae.Registro.cargar(tmp_path / "ae.json"), desde=date(2026, 2, 10))
    assert res.daes[-3:] == ["111/2025", "110/2025", "109/2025"]        # siguió en el período 2025
    expedientes = {a.expediente for a in res.asuntos}
    assert {"S-111/26", "S-110/26"} <= expedientes and "S-109/26" not in expedientes   # el 109 es anterior
    assert res.advertencias == []


def test_una_revision_que_cruza_el_cambio_de_periodo(tmp_path, monkeypatch):
    pedidos = []
    _sinteticos(monkeypatch, pedidos)
    monkeypatch.setattr(ae, "MAX_DAE", 200)
    registro = ae.Registro.cargar(tmp_path / "ae.json")
    registro.ultimo_dae, registro.desde = (110, 2025), "2026-02-01"
    res = ae.revisar(ClienteFalso(), registro)
    assert res.daes[0] == "84/2026" and res.daes[-1] == "111/2025"      # termina el 2025 y para en el 110
    assert registro.ultimo_dae == (84, 2026)


def test_informe_de_asuntos_entrados(tmp_path):
    import zipfile
    from informe_expedientes import informe_asuntos
    res = ae.revisar(ClienteFalso(), ae.Registro.cargar(tmp_path / "ae.json"), desde=date(2026, 10, 21))
    leyes = ae.filtrar(res.asuntos, {"PL"})
    archivos = informe_asuntos.escribir(res, leyes, tmp_path / "informes", filtros="tipos: ley")
    html = archivos["html"].read_text(encoding="utf-8")
    assert "Asuntos entrados desde el 21/10/2026" in html and "Filtros: tipos: ley" in html
    assert f"<h2>Proyectos de ley ({len(leyes)})</h2>" in html and "Proyectos de declaración" not in html
    assert "https://www.senado.gob.ar/parlamentario/comisiones/verExp/18.26/CD/PL" in html
    assert "EMERGENCIA NACIONAL EN DISCAPACIDAD" in html and "DAE leídos: 84/2026, 83/2026, 82/2026" in html
    with zipfile.ZipFile(archivos["docx"]) as z:
        documento = z.read("word/document.xml").decode("utf-8")
    assert "Proyectos de ley" in documento and "CD-18/26" in documento


def test_asuntos_que_no_figuran_en_un_dae(tmp_path, monkeypatch):
    """Copias de cortesía como el PE-361/26 MD: entran por Mesa de Entradas pero no salen en un DAE."""
    from informe_expedientes import busqueda, ficha
    from informe_expedientes.modelos import Ficha, Giro

    filas = [{"expediente": "361/26", "tipo": "MD", "origen": "PE", "extracto": "JEFATURA DE GABINETE: REMITE COPIA"},
             {"expediente": "13/26", "tipo": "PL", "origen": "PE", "extracto": "YA EN EL DAE"},
             {"expediente": "500/26", "tipo": "CE", "origen": "OV", "extracto": "OFICIAL VARIO"}]
    monkeypatch.setattr(busqueda.Buscador, "consultar", lambda self, *a, **k: filas)
    pedidas = []

    def descargar(_cliente, ident):
        pedidas.append(ident.corto)
        return Ficha(ident, ident.url_ficha(), extracto="JEFATURA DE GABINETE: REMITE COPIA DEL MENSAJE N° 316/26",
                     fecha_mesa_entradas=date(2026, 11, 4), giros=[Giro("DE PRESUPUESTO Y HACIENDA", 1, None, None)])

    monkeypatch.setattr(ficha, "descargar_ficha", descargar)
    registro = ae.Registro.cargar(tmp_path / "ae.json")
    res = ae.revisar(ClienteFalso(), registro, desde=date(2026, 10, 21), hoy=date(2026, 11, 6))
    copia = [a for a in res.asuntos if a.expediente == "PE-361/26"]
    assert len(copia) == 1 and copia[0].dae == ae.SIN_DAE and copia[0].tipo == "MD"
    assert copia[0].fecha == "2026-11-04" and copia[0].giros == ["Presupuesto y Hacienda"]
    assert res.asuntos[0].expediente == "PE-361/26"                    # es lo más nuevo
    assert pedidas == ["PE-361/26"]                                     # ni el que ya está en el DAE ni otros orígenes
    vuelta = ae.Registro.cargar(tmp_path / "ae.json")
    assert vuelta.sin_dae == ["PE-361/26"] and vuelta.maximos["PE/2026"] >= 13
    otra = ae.revisar(ClienteFalso(), vuelta, hoy=date(2026, 11, 6))   # ya informado: no se repite
    assert otra.asuntos == []


def _sitio_falso(monkeypatch, filas, fechas):
    from informe_expedientes import busqueda, ficha
    from informe_expedientes.modelos import Ficha
    monkeypatch.setattr(busqueda.Buscador, "consultar", lambda self, *a, **k: filas)
    pedidas = []

    def descargar(_cliente, ident):
        pedidas.append(ident.corto)
        return Ficha(ident, ident.url_ficha(), extracto=f"EXTRACTO {ident.corto}",
                     fecha_mesa_entradas=fechas[ident.corto])

    monkeypatch.setattr(ficha, "descargar_ficha", descargar)
    return pedidas


def test_profundidad_solo_dae(tmp_path, monkeypatch):
    pedidas = _sitio_falso(monkeypatch, [{"expediente": "361/26", "tipo": "MD", "origen": "PE", "extracto": "X"}],
                           {"PE-361/26": date(2026, 11, 4)})
    registro = ae.Registro.cargar(tmp_path / "ae.json")
    res = ae.revisar(ClienteFalso(), registro, desde=date(2026, 10, 21), profundidad="dae")
    assert all(a.dae != ae.SIN_DAE for a in res.asuntos) and pedidas == []
    assert ae.Registro.cargar(tmp_path / "ae.json").profundidad == "dae"   # se recuerda para la próxima


def test_profundidad_todo_suma_oficiales_varios(tmp_path, monkeypatch):
    """OV no sale en los DAE: el punto de partida se ubica por fecha, leyendo pocas fichas."""
    fechas = {f"OV-{n}/26": date(2026, 3, 1 + n // 10) if n < 200 else date(2026, 10, 15 + (n - 200))
              for n in range(1, 211)}                                   # OV-206 entró el 21/10
    filas = [{"expediente": f"{n}/26", "tipo": "CV", "origen": "OV", "extracto": "OFICIAL"} for n in range(1, 211)]
    pedidas = _sitio_falso(monkeypatch, filas, fechas)
    registro = ae.Registro.cargar(tmp_path / "ae.json")
    res = ae.revisar(ClienteFalso(), registro, desde=date(2026, 10, 21), profundidad="todo")
    ov = sorted(a.ident.numero for a in res.asuntos if a.origen == "OV")
    assert ov == [206, 207, 208, 209, 210]
    assert len(set(pedidas)) < 30                                      # búsqueda binaria + las nuevas, no las 210
    assert registro.maximos["OV/2026"] == 210
    otra = ae.revisar(ClienteFalso(), ae.Registro.cargar(tmp_path / "ae.json"), hoy=date(2026, 11, 6))
    assert not [a for a in otra.asuntos if a.origen == "OV"]           # ya revisados: no se repiten


def test_casillas_de_profundidad():
    assert ae.profundidad_de(False, False) == "dae" and ae.origenes_de("dae") == ()
    assert ae.profundidad_de(True, False) == "general" and "PE" in ae.origenes_de("general")
    assert ae.origenes_de(ae.profundidad_de(True, True)) == ("S", "PE", "CD", "OV", "P")
    assert ae.origenes_de(ae.profundidad_de(False, True)) == ("OV", "P")
