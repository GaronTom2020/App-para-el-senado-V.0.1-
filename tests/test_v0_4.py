"""Versión 0.4.0: PDF, exportar el seguimiento, relacionados en el seguimiento, resumen por correo y versiones."""

import hashlib
import os
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


class _Descarga:
    def __init__(self, partes, corte=False):
        self._partes, self._corte = partes, corte

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, _tamano):
        yield from self._partes
        if self._corte:
            raise actualizaciones.requests.ConnectionError("conexión cerrada")


@pytest.mark.parametrize("partes, corte, completa", [
    ([b"x" * 600, b"x" * 400], False, True),
    ([b"x" * 600], False, False),          # llegó menos de lo que informa GitHub
    ([b"x" * 600], True, False),           # se cortó la conexión a mitad de camino
    ([], False, False),                    # no llegó nada
])
def test_instalar_verifica_la_descarga(monkeypatch, tmp_path, partes, corte, completa):
    actual = tmp_path / "InformeExpediente.exe"
    actual.write_bytes(b"viejo")
    monkeypatch.setattr(actualizaciones.sys, "executable", str(actual))
    monkeypatch.setattr(actualizaciones.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(actualizaciones.requests, "get", lambda *a, **k: _Descarga(partes, corte))
    version = actualizaciones.Version("9.0.0", "https://x", "https://x/InformeExpediente.exe", tamano=1000)
    nuevo = tmp_path / "InformeExpediente.nuevo.exe"
    if completa:
        assert actualizaciones.instalar(version).exists()
        assert nuevo.stat().st_size == 1000
    else:
        with pytest.raises(OSError):
            actualizaciones.instalar(version)
        assert not nuevo.exists()
    assert actual.read_bytes() == b"viejo"


def test_instalar_guarda_la_version_anterior(monkeypatch, tmp_path):
    actual = tmp_path / "InformeExpediente.exe"
    actual.write_bytes(b"viejo")
    monkeypatch.setattr(actualizaciones.sys, "executable", str(actual))
    monkeypatch.setattr(actualizaciones.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(actualizaciones.requests, "get", lambda *a, **k: _Descarga([b"x" * 1000]))
    version = actualizaciones.Version("9.0.0", "https://x", "https://x/InformeExpediente.exe", tamano=1000)
    bat = actualizaciones.instalar(version).read_text(encoding="mbcs" if os.name == "nt" else "utf-8")
    anterior = tmp_path / "InformeExpediente.anterior.exe"
    # Primero se copia el actual como anterior, después se pone el nuevo en su lugar.
    assert bat.index(f'copy /y "{actual}" "{anterior}"') < bat.index(f'move /y "{tmp_path / "InformeExpediente.nuevo.exe"}"')

    monkeypatch.setattr(actualizaciones.sys, "frozen", True, raising=False)
    assert not actualizaciones.hay_anterior()
    with pytest.raises(OSError):
        actualizaciones.volver_a_anterior()
    anterior.write_bytes(b"viejo")
    assert actualizaciones.hay_anterior()
    bat = actualizaciones.volver_a_anterior().read_text(encoding="mbcs" if os.name == "nt" else "utf-8")
    assert f'move /y "{anterior}" "{actual}"' in bat and "copy" not in bat


def test_cambios_de_las_notas():
    notas = ("Descargá InformeExpediente.exe y reemplazá el anterior.\r\n\r\n## Cambios\r\n"
             "* Actualizaciones más seguras by @GaronTom2020 in https://github.com/x/y/pull/16\r\n"
             "* Control de sitios by @GaronTom2020 in https://github.com/x/y/pull/19\r\n\r\n"
             "**Full Changelog**: https://github.com/x/y/compare/v0.4.0.7...v0.4.0.8")
    assert actualizaciones.cambios(notas) == ["Actualizaciones más seguras", "Control de sitios"]
    muchas = "\n".join(f"* Cambio {i} by @a in https://x/{i}" for i in range(10))
    assert actualizaciones.cambios(muchas, maximo=3) == ["Cambio 0", "Cambio 1", "Cambio 2", "y 7 cambios más"]
    assert actualizaciones.cambios("") == []


@pytest.mark.parametrize("huella, instala", [
    (hashlib.sha256(b"x" * 1000).hexdigest(), True),
    ("0" * 64, False),                     # el archivo no es el que publicó GitHub
    ("", True),                            # GitHub no informó la huella: alcanza con el tamaño
])
def test_instalar_verifica_la_huella(monkeypatch, tmp_path, huella, instala):
    actual = tmp_path / "InformeExpediente.exe"
    actual.write_bytes(b"viejo")
    monkeypatch.setattr(actualizaciones.sys, "executable", str(actual))
    monkeypatch.setattr(actualizaciones.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(actualizaciones.requests, "get", lambda *a, **k: _Descarga([b"x" * 1000]))
    version = actualizaciones.Version("9.0.0", "https://x", "https://x/InformeExpediente.exe", tamano=1000,
                                      sha256=huella)
    if instala:
        assert actualizaciones.instalar(version).exists()
    else:
        with pytest.raises(OSError, match="no coincide"):
            actualizaciones.instalar(version)
        assert not (tmp_path / "InformeExpediente.nuevo.exe").exists()
    assert actual.read_bytes() == b"viejo"


def test_version_nueva(monkeypatch):
    publicadas = [
        {"tag_name": "manual", "assets": []},
        {"tag_name": "v9.1.0", "prerelease": True, "assets": []},
        {"tag_name": "v9.0.0", "html_url": "https://github.com/x/releases/tag/v9.0.0",
         "assets": [{"name": "InformeExpediente.exe", "browser_download_url": "https://x/InformeExpediente.exe",
                     "size": 1234, "digest": "sha256:ABC123"}]},
        {"tag_name": "v0.3.0", "assets": []},
    ]
    monkeypatch.setattr(actualizaciones.requests, "get", lambda *a, **k: _Respuesta(publicadas))
    v = actualizaciones.hay_nueva()
    assert (v.numero, v.exe, v.tamano, v.sha256) == ("9.0.0", "https://x/InformeExpediente.exe", 1234, "abc123")
    monkeypatch.setattr(actualizaciones, "__version__", "9.0.0")
    assert actualizaciones.hay_nueva() is None
    assert actualizaciones.clave("v0.10.1") > actualizaciones.clave("0.9.9")


def test_manual_local_o_de_releases(tmp_path, monkeypatch):
    monkeypatch.setattr(actualizaciones, "MANUAL_LOCAL", tmp_path / "Manual-de-usuario.pdf")
    assert actualizaciones.manual().startswith("https://github.com/")
    (tmp_path / "Manual-de-usuario.pdf").write_bytes(b"%PDF")
    assert actualizaciones.manual() == str(tmp_path / "Manual-de-usuario.pdf")


def test_resumen_diario_una_vez_por_dia_con_aviso(config_vacia, monkeypatch):
    enviados, avisos = [], []
    monkeypatch.setattr(correo, "enviar", lambda *a: enviados.append(a))
    principal = Lista()
    principal.agregar("PE-99/26", hoy=HOY)
    principal.guardar()
    cfg = correo.ConfigCorreo(activo=True, destinatarios=["a@b.ar"], asuntos=False)
    assert correo.ejecutar_diario(cfg, ClienteFalso(), hoy=HOY, mostrar=avisos.append).vacio
    assert enviados == [] and avisos == []                 # primera vez: solo toma el estado
    propia = Lista(correo.config.carpeta_app() / "correo_seguimiento.json")
    propia.seguidos[0].foto["situacion"] = "En comisión"
    propia.guardar()
    # El mismo día no se repite (la tarea pudo correr a la hora y otra vez al iniciar sesión).
    assert correo.ejecutar_diario(correo.ConfigCorreo.cargar(), ClienteFalso(), hoy=HOY, mostrar=avisos.append) is None
    otro_dia = date(2026, 10, 31)
    res = correo.ejecutar_diario(correo.ConfigCorreo.cargar(), ClienteFalso(), hoy=otro_dia, mostrar=avisos.append)
    assert len(enviados) == 1 and avisos == [res]
    assert correo.lineas_aviso(res)[0].startswith("PE-99/26: Cambió la situación")
    assert correo.archivo_ultimo_resumen().read_text(encoding="utf-8").count("PE-99/26") >= 1


def test_aviso_sin_correo_y_error_de_envio(config_vacia, monkeypatch):
    def falla(*_a):
        raise correo.ErrorCorreo("Outlook no está instalado")
    monkeypatch.setattr(correo, "enviar", falla)
    principal = Lista()
    principal.agregar("PE-99/26", hoy=HOY)
    principal.guardar()
    cfg = correo.ConfigCorreo(activo=True, destinatarios=["a@b.ar"], asuntos=False)
    correo.ejecutar_diario(cfg, ClienteFalso(), hoy=HOY, mostrar=lambda r: None)
    propia = Lista(correo.config.carpeta_app() / "correo_seguimiento.json")
    propia.seguidos[0].foto["situacion"] = "En comisión"
    propia.guardar()
    avisos = []
    res = correo.ejecutar_diario(correo.ConfigCorreo.cargar(), ClienteFalso(), hoy=date(2026, 10, 31),
                                 mostrar=avisos.append)
    assert avisos and any("Outlook no está instalado" in x for x in correo.lineas_aviso(res))


class _SMTPFalso:
    """Imita smtplib.SMTP: anota lo que se hizo, sin conectarse a nada."""
    hechos: list = []
    rechazar = False

    def __init__(self, servidor, puerto, timeout=None):
        _SMTPFalso.hechos = [("conectar", servidor, puerto)]

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def starttls(self):
        self.hechos.append(("starttls",))

    def login(self, usuario, clave):
        if _SMTPFalso.rechazar:
            import smtplib
            raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
        self.hechos.append(("login", usuario, clave))

    def send_message(self, m):
        self.hechos.append(("enviar", m["From"], m["To"], m["Subject"]))


def test_envio_desde_la_cuenta_de_la_oficina(tmp_path, monkeypatch):
    monkeypatch.setattr(correo.smtplib, "SMTP", _SMTPFalso)
    monkeypatch.setattr(correo, "_carpeta_programa", lambda: tmp_path)
    monkeypatch.setattr(correo, "__file__", str(tmp_path / "paquete" / "correo.py"))
    monkeypatch.delenv("INFORME_CUENTA_ENVIO", raising=False)
    cfg = correo.ConfigCorreo(destinatarios=["a@b.ar", "c@d.ar"])
    with pytest.raises(correo.ErrorCorreo, match="cuenta de envío"):
        correo.enviar(cfg, "Prueba", "<p>hola</p>", "hola")

    # El .exe ya no trae la cuenta adentro: una en recursos/ se ignora.
    (tmp_path / "paquete" / "recursos").mkdir(parents=True)
    (tmp_path / "paquete" / "recursos" / "cuenta_envio.txt").write_text("vieja@gmail.com\nclave0\n", encoding="utf-8")
    assert correo.cuenta_envio() is None

    # La de la carpeta compartida, con la contraseña como la muestra Google.
    (tmp_path / "cuenta_envio.txt").write_text(
        "# cuenta de la oficina\nresumen.oficina@gmail.com\nabcd efgh ijkl mnop\n", encoding="utf-8")
    correo.enviar(cfg, "Prueba", "<p>hola</p>", "hola")
    assert _SMTPFalso.hechos == [("conectar", "smtp.gmail.com", 587), ("starttls",),
                                 ("login", "resumen.oficina@gmail.com", "abcdefghijklmnop"),
                                 ("enviar", "Resumen parlamentario <resumen.oficina@gmail.com>", "a@b.ar, c@d.ar",
                                  "Prueba")]
    # El archivo gana sobre la variable de entorno; sin el archivo, vale la variable.
    monkeypatch.setenv("INFORME_CUENTA_ENVIO", "otra@gmail.com\nclave2")
    assert correo.cuenta_envio() == ("resumen.oficina@gmail.com", "abcdefghijklmnop")
    (tmp_path / "cuenta_envio.txt").unlink()
    assert correo.cuenta_envio() == ("otra@gmail.com", "clave2")
    (tmp_path / "cuenta_envio.txt").write_text("nueva@gmail.com\nclave3\n", encoding="utf-8")

    _SMTPFalso.rechazar = True
    try:
        with pytest.raises(correo.ErrorCorreo, match="no aceptó la contraseña"):
            correo.enviar(cfg, "Prueba", "<p>hola</p>", "hola")
    finally:
        _SMTPFalso.rechazar = False


def test_cuenta_elegida_a_mano(tmp_path, monkeypatch):
    monkeypatch.setattr(correo, "_carpeta_programa", lambda: tmp_path / "programa")
    monkeypatch.setattr(correo.config, "carpeta_app", lambda: tmp_path / "datos")
    monkeypatch.delenv("INFORME_CUENTA_ENVIO", raising=False)
    assert correo.cuenta_envio() is None
    mal = tmp_path / "mal.txt"
    mal.write_text("solo un renglon\n", encoding="utf-8")
    with pytest.raises(correo.ErrorCorreo, match="dos renglones"):
        correo.cargar_cuenta(mal)
    assert correo.cuenta_envio() is None

    # Se copia a la carpeta de datos: sirve aunque después se borre o no se tenga a mano el original.
    elegido = tmp_path / "pendrive" / "cuenta_envio.txt"
    elegido.parent.mkdir()
    elegido.write_text("oficina@gmail.com\nabcd efgh ijkl mnop\n", encoding="utf-8")
    assert correo.cargar_cuenta(elegido) == ("oficina@gmail.com", "abcdefghijklmnop")
    elegido.unlink()
    assert correo.cuenta_envio() == ("oficina@gmail.com", "abcdefghijklmnop")

    # La de la carpeta compartida, junto al .exe, gana sobre la copia del usuario.
    (tmp_path / "programa").mkdir()
    (tmp_path / "programa" / "cuenta_envio.txt").write_text("compartida@gmail.com\nclave\n", encoding="utf-8")
    assert correo.cuenta_envio() == ("compartida@gmail.com", "clave")
