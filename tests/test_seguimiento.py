import json
from datetime import date, timedelta

import pytest
from conftest import ClienteFalso

from informe_expedientes import seguimiento
from informe_expedientes.identificador import ErrorIdentificador
from informe_expedientes.seguimiento import Lista, OpcionesSeguimiento, comparar, revisar

HOY = date(2026, 10, 30)


def _opciones(tmp_path, **k):
    return OpcionesSeguimiento(buscar_reuniones=False, carpeta_salida=tmp_path, **k)


def test_lista_agregar_quitar_y_guardar(tmp_path):
    archivo = tmp_path / "seguimiento.json"
    lista = Lista(archivo)
    assert lista.seguidos == []
    s, nuevo = lista.agregar("PE 99/2026", hoy=HOY)
    assert nuevo and s.expediente == "PE-99/26" and s.agregado == "2026-10-30"
    _, nuevo = lista.agregar("PE-99/26-PL")
    assert not nuevo and lista.seguidos[0].tipo == "PL"
    lista.agregar("S-351/25")
    with pytest.raises(ErrorIdentificador):
        lista.agregar("cualquier cosa")
    lista.guardar()
    vuelta = Lista(archivo)
    assert [x.expediente for x in vuelta.seguidos] == ["PE-99/26", "S-351/25"]
    assert vuelta.quitar("S 351/25") and not vuelta.quitar("S-1/20") and not vuelta.quitar("???")
    archivo.write_text("no es json", encoding="utf-8")
    assert Lista(archivo).seguidos == []


def test_primera_revision_y_novedades_contra_la_foto(tmp_path):
    lista = Lista(tmp_path / "seguimiento.json")
    lista.agregar("PE-99/26")
    res = revisar(lista, ClienteFalso(), _opciones(tmp_path, formatos=()), hoy=HOY)
    primera = res.revisiones[0]
    assert [n.clase for n in primera.novedades] == ["alta"]
    assert primera.situacion == "Media sanción del Senado (votada en el recinto)"
    foto = lista.seguidos[0].foto
    assert foto["votaciones"][0][0] == "29/10/2026"
    assert foto["votaciones"][0][1].startswith("En general: aprobado (42 a 21). En particular:")
    assert [m[3] for m in foto["diputados"]] == ["MEDIA SANCION", ""]          # media sanción y pase a Diputados
    assert lista.seguidos[0].tipo == "PL" and lista.seguidos[0].revisado

    # Sin cambios en el sitio, la segunda revisión no trae novedades.
    assert revisar(lista, ClienteFalso(), _opciones(tmp_path, formatos=()), hoy=HOY).con_novedades == []

    # Una foto vieja: antes de la votación y de que Diputados la registrara, con la comisión abierta,
    # sin un giro y sin la orden del día.
    vieja = json.loads(json.dumps(foto))
    vieja["situacion"] = "Con dictamen de comisión: Orden del Día N° 409/26"
    vieja["votaciones"] = []
    vieja["diputados"] = []
    vieja["giros"] = [[vieja["giros"][0][0], vieja["giros"][0][1], None]]
    vieja["ordenes"] = []
    lista.seguidos[0].foto = vieja
    res = revisar(lista, ClienteFalso(), _opciones(tmp_path), hoy=HOY)
    textos = [n.texto for n in res.revisiones[0].novedades]
    clases = [n.clase for n in res.revisiones[0].novedades]
    assert clases == ["situacion", "votacion", "diputados", "diputados", "dictamen", "egreso", "giro"]
    assert textos[0] == ("Cambió la situación: de «Con dictamen de comisión: Orden del Día N° 409/26» a "
                         "«Media sanción del Senado (votada en el recinto)».")
    assert textos[1].startswith("Votación en el recinto el 29/10/2026. En general: aprobado (42 a 21).")
    assert textos[2] == "El sitio de Diputados registra: Senado: media sanción, con modificaciones (29/10/2026)."
    assert textos[3] == "El sitio de Diputados registra: pasó a Diputados."
    assert textos[4] == "Dictamen nuevo: Orden del Día N° 409/26 del 21/10/2026 (pendiente)."
    assert textos[5] == "Egresó de la comisión de Salud el 21/10/2026."
    assert textos[6] == "Giro nuevo a la comisión de Legislación General (ingreso el 23/04/2026)."
    md = res.archivos["md"].read_text(encoding="utf-8")
    assert md.startswith("# Seguimiento de expedientes — ")
    assert "Se revisó UN (1) expediente, con novedades." in md and "- Egresó de la comisión de Salud el 21/10/2026." in md
    assert "([ver](https://www.senado.gob.ar/votaciones/verActaVotacion/2867))" in md
    html = res.archivos["html"].read_text(encoding="utf-8")
    assert "<h2><a href=\"https://www.senado.gob.ar/parlamentario/comisiones/verExp/99.26/PE/PL\"" in html
    assert "#2E6B5F" in html                          # misma paleta que los informes


def test_un_expediente_que_falla_no_corta_la_revision(tmp_path):
    lista = Lista(tmp_path / "seguimiento.json")
    lista.agregar("S-9999/26", "PL")
    lista.agregar("PE-99/26")
    res = revisar(lista, ClienteFalso(), _opciones(tmp_path, formatos=()), hoy=HOY)
    assert [r.novedades[0].clase for r in res.revisiones] == ["error", "alta"]
    assert lista.seguidos[0].foto is None and lista.seguidos[1].foto
    assert seguimiento.resumen(res) == "Se revisaron DOS (2) expedientes, todos con novedades."
    res.revisiones[1].novedades = []
    assert seguimiento.resumen(res) == ("Se revisaron DOS (2) expedientes: UN (1) con novedades y UN (1) "
                                        "sin novedades.")


def test_caducidad_cercana_y_convocatoria():
    base = {"situacion": "En comisión: Salud", "giros": [], "ordenes": [], "resoluciones": [], "votaciones": [],
            "reuniones": [], "reuniones_buscadas": True, "convocadas": [], "caducidad": None}
    nueva = dict(base, caducidad=(HOY + timedelta(days=22)).isoformat(),
                 convocadas=[["2026-11-04", "11:00", "REUNIÓN DE LA COMISIÓN DE SALUD", "Salud", "https://x"]])
    novedades = comparar(base, nueva, HOY)
    assert [n.texto for n in novedades] == [
        "Reunión convocada con el expediente en el temario: 04/11/2026, 11:00 h, Salud "
        "(REUNIÓN DE LA COMISIÓN DE SALUD).",
        "Caducidad cercana: 21/11/2026 (en VEINTIDÓS (22) días).",
    ]
    lejos = dict(base, caducidad=(HOY + timedelta(days=60)).isoformat())
    assert comparar(base, lejos, HOY) == []


def test_linea_de_comandos_de_seguimiento(tmp_path, monkeypatch, capsys):
    import app
    monkeypatch.setattr(app, "Cliente", lambda *a, **k: ClienteFalso())
    lista = str(tmp_path / "lista.json")
    assert app.linea_de_comandos(["--seguimiento", "revisar", "--lista-seguimiento", lista]) == 2
    assert app.linea_de_comandos(["--seguimiento", "agregar", "PE-99/26", "--lista-seguimiento", lista]) == 0
    assert "PE-99/26: agregado" in capsys.readouterr().out
    codigo = app.linea_de_comandos(["--seguimiento", "revisar", "--lista-seguimiento", lista, "--sin-reuniones",
                                    "--salida", str(tmp_path), "--nombre", "novedades"])
    salida = capsys.readouterr().out
    assert codigo == 0 and "Primera revisión. Situación: Media sanción del Senado" in salida
    assert (tmp_path / "novedades.html").exists() and (tmp_path / "novedades.md").exists()
    assert app.linea_de_comandos(["--seguimiento", "listar", "--lista-seguimiento", lista]) == 0
    assert "PE-99/26     Media sanción del Senado" in capsys.readouterr().out
    assert app.linea_de_comandos(["--seguimiento", "quitar", "PE-99/26", "--lista-seguimiento", lista]) == 0
    assert "0 expedientes" in capsys.readouterr().out
