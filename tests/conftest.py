import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from informe_expedientes.cliente import ErrorRed, Respuesta  # noqa: E402
from informe_expedientes.comisiones import RE_NOTA  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
B = "https://www.senado.gob.ar"

MAPA = {
    f"{B}/parlamentario/parlamentaria/": "buscador.html",
    f"{B}/parlamentario/comisiones/verExp/35.23/CD/PL": "ficha_cd_35_23.html",
    f"{B}/parlamentario/comisiones/verExp/14.24/CD/PL": "ficha_cd_14_24.html",
    f"{B}/parlamentario/comisiones/verExp/351.25/S/PL": "ficha_s_351_25.html",
    f"{B}/parlamentario/parlamentaria/ordenDelDiaResultadoLink/2023/234": "od_2023_234.html",
    f"{B}/parlamentario/parlamentaria/ordenDelDiaResultadoLink/2024/146": "od_2024_146.html",
    f"{B}/parlamentario/parlamentaria/ordenDelDiaResultadoLink/2025/527": "od_2025_527.html",
    f"{B}/parlamentario/comisiones/info/75": "comision_75.html",
    f"{B}/parlamentario/comisiones/info/75?Reuniones=2": "comision_75_reuniones_2.html",
    f"{B}/parlamentario/comisiones/info/75?ReunionesVarias=2": "comision_75_varias_2.html",
    f"{B}/parlamentario/comisiones/info/54": "comision_54.html",
    f"{B}/parlamentario/comisiones/info/78": "comision_78.html",
    f"{B}/micrositios/nota/23244/noticias": "nota_23244.html",
    f"{B}/micrositios/nota/23192/noticias": "nota_23192.html",
    f"{B}/micrositios/nota/24350/noticias": "nota_salud_24350.html",
    f"{B}/parlamentario/comisiones/agenda/75": "agenda_75.html",
    f"{B}/parlamentario/comisiones/agenda/54": "agenda_vacia.html",
    f"{B}/parlamentario/comisiones/agenda/78": "agenda_vacia.html",
    f"{B}/votaciones/actas": "votaciones_actas_2026.html",
    f"{B}/votaciones/detalleActa/2847": "acta_2847.html",
    f"{B}/votaciones/detalleActa/2623": "acta_2623.html",
    f"{B}/votaciones/detalleActa/2867": "acta_2867_pendiente.html",
    f"{B}/votaciones/detalleActa/2874": "acta_2874_inexistente.html",
    f"{B}/senadores/listados/agrupados-por-bloques": "senadores_bloques.html",
    f"{B}/parlamentario/comisiones/verExp/99.26/PE/PL": "ficha_pe_99_26.html",
    f"{B}/parlamentario/comisiones/verExp/159.25/PE/PL": "ficha_pe_159_25.html",
    f"{B}/parlamentario/parlamentaria/ordenDelDiaResultadoLink/2026/409": "od_2026_409.html",
}
BINARIOS = {
    f"{B}/votaciones/verActaVotacion/2867": "acta_2867.pdf",
    f"{B}/votaciones/verActaVotacion/2847": "acta_2847.pdf",
    f"{B}/votaciones/verActaVotacion/2868": "acta_2868.pdf",
    f"{B}/votaciones/verActaVotacion/2869": "acta_2869.pdf",
    f"{B}/votaciones/verActaVotacion/2870": "acta_2870.pdf",
}
MAPA_POST = {f"{B}/parlamentario/parlamentaria/avanzada": "resultados_avanzada.html"}


def leer(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


class ClienteFalso:
    """Imita al Cliente real sirviendo las páginas de prueba."""

    def __init__(self, mapa=None):
        self.mapa = dict(MAPA if mapa is None else mapa)
        self.pedidos: list[str] = []
        self.cancelar = None

    def get(self, url, ttl=None, binario=False):
        self.pedidos.append(url)
        if url == f"{B}/micrositios/DatosAbiertosExpedientes/BusquedaAvanzada/XLS":
            return Respuesta(url, 200, contenido=(FIXTURES / "busqueda_avanzada.xls").read_bytes())
        if url in BINARIOS:
            return Respuesta(url, 200, contenido=(FIXTURES / BINARIOS[url]).read_bytes())
        archivo = self.mapa.get(url)
        if archivo is None and RE_NOTA.search(url):
            archivo = "nota_generica.html"
        if archivo is None:
            raise ErrorRed(f"El sitio respondió con el código 404 para {url}.")
        return Respuesta(url, 200, leer(archivo))

    def post(self, url, datos):
        self.pedidos.append("POST " + url)
        self.ultimo_post = datos
        archivo = MAPA_POST.get(url)
        if url == f"{B}/votaciones/actas":
            archivo = f"votaciones_actas_{datos.get('busqueda_actas[anio]')}.html"
            if not (FIXTURES / archivo).exists():
                raise ErrorRed("404")
        if archivo is None:
            raise ErrorRed("404")
        return Respuesta(url, 200, leer(archivo))

    def sesion_nueva(self):
        pass

    def verificar_cancelacion(self):
        pass


@pytest.fixture
def cliente():
    return ClienteFalso()
