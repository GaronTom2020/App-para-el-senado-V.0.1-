"""Versión 0.4.0: PDF, exportar el seguimiento, relacionados en el seguimiento, resumen por correo y versiones."""

import sys
from datetime import date

import pytest
from conftest import ClienteFalso

from informe_expedientes import actualizaciones, correo, pdf, seguimiento
from informe_expedientes.seguimiento import Lista, OpcionesSeguimiento, comparar, revisar

HOY = date(2026, 10, 30)


@pytest.fixture
def config_vacia(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return tmp_path


# ------------------------------------------------------------ seguimiento

def test_relacionados_nuevos_son_novedad():
    base = {"situacion": "En comisión", "giros": [], "ordenes": [], "votaciones": [], "diputados": [],
            "reuniones": [], "convocadas": [], "resoluciones": [], "relacionados_buscados": True,
            "relacionados": [["S-808/26", "Dictaminado en conjunto (Orden del Día N° 366/26)", None, "Con dictamen"]]}
    nueva = dict(base, relacionados=base["relacionados"] + [["S-865/26", "Tenido a la vista", "https://x", ""]])
    novedades = comparar(base, nueva, HOY)
    assert [(n.clase, n.texto, n.url) for n in novedades] == [
        ("relacionado", "Expediente relacionado nuevo: S-865/26 — Tenido a la vista.", "https://x")]
    # Si la revisión anterior no los buscó, no se avisan todos como nuevos.
    assert comparar(dict(base, relacionados_buscados=False, relacionados=[]), nueva, HOY) == []


def test_exportar_lista_a_excel_con_grupos(tmp_path):
    from openpyxl import load_workbook
    lista = Lista(tmp_path / "seguimiento.json")
    lista.agregar("PE-99/26", hoy=HOY, alias="Presupuesto")
    lista.agregar("S-351/25", hoy=HOY)
    grupo = lista.crear_grupo("Salud")
    lista.sumar_a_grupo(lista.seguidos[1], grupo)
    revisar(lista, ClienteFalso(), OpcionesSeguimiento(buscar_reuniones=False, formatos=()), hoy=HOY)
    destino = seguimiento.exportar_lista(lista, tmp_path, "xlsx")
    libro = load_workbook(destino)
    assert libro.sheetnames == ["Todos", "Salud"]
    hoja = libro["Todos"]
    assert [c.value for c in hoja[1]][:4] == ["Expediente", "Nombre", "Grupos", "Situación"]
    assert [hoja.cell(row=f, column=1).value for f in (2, 3)] == ["PE-99/26", "S-351/25"]
    assert hoja.cell(row=2, column=2).value == "Presupuesto" and hoja.cell(row=3, column=3).value == "Salud"
    assert hoja.cell(row=3, column=4).value.startswith("En comisión")
    assert [libro["Salud"].cell(row=f, column=1).value for f in (2, 3)] == ["S-351/25", None]
    html = seguimiento.html_lista(lista)
    assert "<h2>Salud</h2>" in html and "<h2>Sin grupo</h2>" in html and "Presupuesto" in html


@pytest.mark.skipif(pdf.navegador() is None, reason="sin Edge ni Chrome")
def test_pdf_con_el_navegador(tmp_path):
    destino = pdf.texto_a_pdf("<h1>Prueba</h1><p>Informe en PDF.</p>", tmp_path / "prueba.pdf")
    assert destino.read_bytes().startswith(b"%PDF")


def test_pdf_sin_navegador_avisa(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf, "navegador", lambda: None)
    with pytest.raises(pdf.ErrorPDF):
        pdf.texto_a_pdf("<p>x</p>", tmp_path / "x.pdf")
    # El informe de un expediente guarda los demás formatos igual y avisa.
    from informe_expedientes.servicio import Opciones, generar
    avisos = []
    r = generar("S-351/25", Opciones(formatos=("html", "pdf"), carpeta_salida=tmp_path, buscar_reuniones=False,
                                     buscar_agenda=False, buscar_relacionados=False), ClienteFalso(),
                lambda ev, msg="", **d: avisos.append(msg) if ev == "advertencia" else None, hoy=HOY)
    assert set(r.archivos) == {"html"} and any("Edge" in a for a in avisos)


# ------------------------------------------------------------------ correo

def test_resumen_diario_usa_su_propio_registro(config_vacia):
    principal = Lista()
    principal.agregar("PE-99/26", hoy=HOY)
    principal.agregar("S-351/25", hoy=HOY)
    grupo = principal.crear_grupo("Presupuesto")
    principal.sumar_a_grupo(principal.seguidos[0], grupo)
    principal.guardar()
    cfg = correo.ConfigCorreo(activo=True, destinatarios=["a@b.ar"], grupos=["Presupuesto"], asuntos=False)

    primera = correo.armar(cfg, ClienteFalso(), hoy=HOY)
    assert [r.seguido.expediente for r in primera.seguimiento.revisiones] == ["PE-99/26"]
    assert primera.vacio                                   # la «Primera revisión» no es una novedad
    # La lista de la ventana no se tocó: sigue sin revisar.
    assert all(s.foto is None for s in Lista().seguidos)

    # Una foto vieja en el registro del correo: la segunda vez hay novedades.
    propia = Lista(correo.config.carpeta_app() / "correo_seguimiento.json")
    propia.seguidos[0].foto["situacion"] = "En comisión"
    propia.guardar()
    segunda = correo.armar(cfg, ClienteFalso(), hoy=HOY)
    assert not segunda.vacio and "1 con novedades" in correo.asunto_correo(segunda)
    cuerpo = correo.html(segunda)
    assert "PE-99/26" in cuerpo and "Cambió la situación" in cuerpo and "S-351/25" not in cuerpo


def test_resumen_diario_sin_novedades_no_envia(config_vacia, monkeypatch):
    enviados = []
    monkeypatch.setattr(correo, "enviar", lambda *a: enviados.append(a))
    cfg = correo.ConfigCorreo(activo=True, destinatarios=["a@b.ar"], seguimiento=True, asuntos=False)
    correo.enviar_resumen(cfg, ClienteFalso())
    assert enviados == []
    cfg.enviar_vacio = True
    correo.enviar_resumen(cfg, ClienteFalso())
    assert len(enviados) == 1 and "sin novedades" in enviados[0][1]


def test_configuracion_del_correo_se_guarda(config_vacia):
    cfg = correo.ConfigCorreo(activo=True, destinatarios=["a@b.ar", "c@d.ar"], hora="20:00", grupos=["Salud"])
    cfg.guardar()
    vuelta = correo.ConfigCorreo.cargar()
    assert vuelta.destinatarios == ["a@b.ar", "c@d.ar"] and vuelta.hora == "20:00" and vuelta.grupos == ["Salud"]


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI es de Windows")
def test_clave_cifrada_con_la_cuenta_de_windows():
    guardada = correo.cifrar_clave("contraseña de prueba")
    assert "contraseña" not in guardada
    assert correo.descifrar_clave(guardada) == "contraseña de prueba"


def test_linea_de_comandos_resumen_diario_desactivado(config_vacia, capsys):
    import app
    assert app.linea_de_comandos(["--resumen-diario"]) == 0
    assert "desactivado" in capsys.readouterr().out


# ---------------------------------------------------------------- versiones

class _Respuesta:
    def __init__(self, datos):
        self._datos = datos

    def raise_for_status(self):
        pass

    def json(self):
        return self._datos


def test_version_nueva(monkeypatch):
    publicadas = [
        {"tag_name": "manual", "assets": []},
        {"tag_name": "v9.1.0", "prerelease": True, "assets": []},
        {"tag_name": "v9.0.0", "html_url": "https://github.com/x/releases/tag/v9.0.0",
         "assets": [{"name": "InformeExpediente.exe", "browser_download_url": "https://x/InformeExpediente.exe"}]},
        {"tag_name": "v0.3.0", "assets": []},
    ]
    monkeypatch.setattr(actualizaciones.requests, "get", lambda *a, **k: _Respuesta(publicadas))
    v = actualizaciones.hay_nueva()
    assert (v.numero, v.exe) == ("9.0.0", "https://x/InformeExpediente.exe")
    monkeypatch.setattr(actualizaciones, "__version__", "9.0.0")
    assert actualizaciones.hay_nueva() is None
    assert actualizaciones.clave("v0.10.1") > actualizaciones.clave("0.9.9")


def test_manual_local_o_de_releases(tmp_path, monkeypatch):
    monkeypatch.setattr(actualizaciones, "MANUAL_LOCAL", tmp_path / "Manual-de-usuario.pdf")
    assert actualizaciones.manual().startswith("https://github.com/")
    (tmp_path / "Manual-de-usuario.pdf").write_bytes(b"%PDF")
    assert actualizaciones.manual() == str(tmp_path / "Manual-de-usuario.pdf")
