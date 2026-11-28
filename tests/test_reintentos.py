"""Reintentos y pausa de la búsqueda por expediente: un pico de lag no la frena, y si el sitio no responde la
búsqueda se detiene en el asunto que no pudo definir y deja reanudar o cancelar."""

import queue
import threading
from types import SimpleNamespace

import pytest

from informe_expedientes import gui
from informe_expedientes.cliente import Cancelado, ErrorRed


def _yo(decisiones=()):
    yo = SimpleNamespace(cola=queue.Queue(), cancelar=threading.Event(), _decision=queue.Queue(),
                         ESPERAS_REINTENTO=(0, 0, 0))
    for d in decisiones:
        yo._decision.put(d)
    return yo


def _correr(monkeypatch, yo, respuestas):
    """respuestas: lo que va devolviendo/lanzando generar() en cada llamada (excepción = se lanza)."""
    llamadas, escritos = [], []

    def falso_generar(texto, opciones, cliente, avisar, escribir=True):
        llamadas.append(texto)
        r = respuestas[min(len(llamadas) - 1, len(respuestas) - 1)]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(gui, "generar", falso_generar)
    monkeypatch.setattr(gui, "escribir_informes", lambda resultado, opciones, avisar: escritos.append(resultado))
    avisar = lambda *a, **k: None  # noqa: E731
    try:
        salida = gui.Aplicacion._generar_con_reintentos(yo, "S-1/24", None, None, avisar, "")
    except Cancelado:
        salida = "cancelado"
    except gui.AsuntoOmitido as e:
        salida = ("omitido", e.texto)
    return salida, llamadas, escritos


def _eventos(yo):
    out = []
    while not yo.cola.empty():
        out.append(yo.cola.get())
    return out


def test_un_pico_de_lag_no_pausa_la_busqueda(monkeypatch):
    ok = SimpleNamespace(fallas_red=[])
    yo = _yo()
    salida, llamadas, escritos = _correr(monkeypatch, yo, [ErrorRed("lento"), ok])
    assert salida is ok and len(llamadas) == 2 and escritos == [ok]
    assert not [e for e in _eventos(yo) if e[0] == "pausa"]


def test_pasos_incompletos_se_reintentan_y_no_se_escribe_el_incompleto(monkeypatch):
    incompleto = SimpleNamespace(fallas_red=["No se pudo revisar la agenda: x"])
    ok = SimpleNamespace(fallas_red=[])
    salida, _, escritos = _correr(monkeypatch, _yo(), [incompleto, ok])
    assert salida is ok and escritos == [ok]


def test_si_sigue_fallando_pausa_y_cancelar_no_escribe_nada(monkeypatch):
    yo = _yo(["cancelar"])
    salida, llamadas, escritos = _correr(monkeypatch, yo, [ErrorRed("caído")])
    assert salida == "cancelado" and escritos == []
    assert len(llamadas) == 4                     # el intento inicial y 3 reintentos
    pausas = [e for e in _eventos(yo) if e[0] == "pausa"]
    assert len(pausas) == 1 and pausas[0][2]["texto"] == "el informe de S-1/24"


def test_reintentar_vuelve_a_intentar_el_mismo_asunto(monkeypatch):
    ok = SimpleNamespace(fallas_red=[])
    yo = _yo(["reintentar"])
    salida, llamadas, escritos = _correr(monkeypatch, yo, [ErrorRed("caído")] * 4 + [ok])
    assert salida is ok and len(llamadas) == 5 and escritos == [ok]


def test_continuar_omite_el_asunto_sin_escribir_nada(monkeypatch):
    salida, llamadas, escritos = _correr(monkeypatch, _yo(["continuar"]), [ErrorRed("caído")])
    assert salida == ("omitido", "S-1/24") and escritos == [] and len(llamadas) == 4


def test_cancelar_mientras_espera_corta_enseguida(monkeypatch):
    yo = _yo()
    yo.ESPERAS_REINTENTO = (5,)
    yo.cancelar.set()
    salida, llamadas, _ = _correr(monkeypatch, yo, [ErrorRed("lento")])
    assert salida == "cancelado" and len(llamadas) == 1


# ------------------------------------------------------------------ compuerta de las luces

def _luces(monkeypatch, hsn, hcdn, acepta=True):
    mensajes = []
    yo = SimpleNamespace(_estado_sitios={"HSN": hsn, "HCDN": hcdn}, _lanzar_comprobacion=lambda: None)
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda titulo, texto: mensajes.append(titulo))
    monkeypatch.setattr(gui.messagebox, "askokcancel", lambda titulo, texto: mensajes.append(titulo) or acepta)
    return gui.Aplicacion._permitir_busqueda(yo), mensajes


@pytest.mark.parametrize("hsn,hcdn,titulo", [(False, False, "Sitio sin respuesta"),
                                             (False, True, "Sitio sin respuesta"),
                                             ("sin_red", "sin_red", "Sin conexión a internet")])
def test_sin_senado_o_sin_internet_no_se_busca(monkeypatch, hsn, hcdn, titulo):
    permiso, mensajes = _luces(monkeypatch, hsn, hcdn)
    assert permiso is None and mensajes == [titulo]


def test_solo_diputados_caido_avisa_y_sigue_sin_contraste(monkeypatch):
    assert _luces(monkeypatch, True, False)[0] == "sin_diputados"
    permiso, mensajes = _luces(monkeypatch, True, False, acepta=False)
    assert permiso is None and mensajes == ["Diputados no responde"]


def test_todo_verde_o_sin_saber_deja_buscar(monkeypatch):
    assert _luces(monkeypatch, True, True) == (True, [])
    assert _luces(monkeypatch, None, None) == (True, [])


# ------------------------------------------------------------------ búsquedas de una sola operación

def _simple(monkeypatch, yo, acciones):
    """Corre _ejecutar_con_pausa con una acción que va lanzando/devolviendo lo indicado."""
    llamadas = []

    def accion():
        llamadas.append(1)
        r = acciones[min(len(llamadas) - 1, len(acciones) - 1)]
        if isinstance(r, Exception):
            raise r
        return r
    try:
        salida = gui.Aplicacion._ejecutar_con_pausa(yo, accion, "el informe temático", lambda *a, **k: None)
    except Cancelado:
        salida = "cancelado"
    except gui.AsuntoOmitido as e:
        salida = ("omitido", e.texto)
    return salida, len(llamadas)


def test_una_operacion_se_recupera_de_un_pico_de_lag(monkeypatch):
    assert _simple(monkeypatch, _yo(), [ErrorRed("lento"), "ok"]) == ("ok", 2)


def test_una_operacion_que_sigue_fallando_pausa_y_se_puede_omitir(monkeypatch):
    yo = _yo(["continuar"])
    assert _simple(monkeypatch, yo, [ErrorRed("caído")]) == (("omitido", "el informe temático"), 4)
    assert [e for e in _eventos(yo) if e[0] == "pausa"][0][2]["texto"] == "el informe temático"


def test_una_operacion_reintenta_o_cancela_desde_la_pausa(monkeypatch):
    assert _simple(monkeypatch, _yo(["reintentar"]), [ErrorRed("caído")] * 4 + ["ok"]) == ("ok", 5)
    assert _simple(monkeypatch, _yo(["cancelar"]), [ErrorRed("caído")]) == ("cancelado", 4)
