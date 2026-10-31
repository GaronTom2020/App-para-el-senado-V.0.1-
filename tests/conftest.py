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
H = ("https://www.hcdn.gob.ar/proyectos/resultado.html?zezion=true&strTipo=todos&strCantPagina=20"
     "&strMostrarTramites=on&strMostrarDictamenes=on&strMostrarFirmantes=on&strMostrarComisiones=on")
MAPA.update({
    f"{H}&strNumExp=99&strNumExpOrig=PE&strNumExpAnio=2026": "hcdn_pe_99_26.html",
    f"{H}&strNumExp=159&strNumExpOrig=PE&strNumExpAnio=2025": "hcdn_pe_159_25.html",
    f"{H}&strNumExp=14&strNumExpOrig=CD&strNumExpAnio=2024": "hcdn_cd_14_24.html",
    f"{H}&strNumExp=351&strNumExpOrig=S&strNumExpAnio=2025": "hcdn_s_351_25.html",
    f"{H}&strNumExp=35&strNumExpOrig=CD&strNumExpAnio=2023": "hcdn_cd_35_23.html",
})
# Sesión del 29/10/2026 (plan de labor del 28/10): órdenes del día, fichas y Diputados.
for _od in (413, 366, 241, 132, 370):
    MAPA[f"{B}/parlamentario/parlamentaria/ordenDelDiaResultadoLink/2026/{_od}"] = f"od_2026_{_od}.html"
for _n, _t in ((702, "PL"), (718, "PL"), (808, "PL"), (865, "PL"), (645, "PL"), (695, "PL"), (700, "CO"), (255, "PL")):
    MAPA[f"{B}/parlamentario/comisiones/verExp/{_n}.26/S/{_t}"] = f"ficha_s_{_n}_26.html"
    if _t == "PL":
        MAPA[f"{H}&strNumExp={_n}&strNumExpOrig=S&strNumExpAnio=2026"] = f"hcdn_s_{_n}_26.html"
# Etapa en Diputados (Fase 3): en comisión, modificado, rechazado y sancionado.
for _n, _a, _o in ((361, 2026, "S"), (13, 2026, "PE"), (1167, 2025, "S"), (98, 2026, "PE")):
    _archivo = f"{_o.lower()}_{_n}_{_a % 100:02d}.html"
    MAPA[f"{B}/parlamentario/comisiones/verExp/{_n}.{_a % 100:02d}/{_o}/PL"] = f"ficha_{_archivo}"
    MAPA[f"{H}&strNumExp={_n}&strNumExpOrig={_o}&strNumExpAnio={_a}"] = f"hcdn_{_archivo}"
MAPA[f"{B}/parlamentario/parlamentaria/actas"] = "plenario_labor.html"
MAPA[f"{B}/senadores/listados/agrupados-por-bloques"] = "senadores_bloques.html"
BINARIOS[f"{B}/parlamentario/parlamentaria/Acta%20de%20labor%20parlamentaria%20%2028-10-2026.pdf/download"] = \
    "plan_labor_2026-10-28.pdf"
for _acta in (2848, 2863, 2871, 2872, 2873):
    BINARIOS[f"{B}/votaciones/verActaVotacion/{_acta}"] = f"acta_{_acta}.pdf"
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
            # Las búsquedas por autor (2026) tienen su propia exportación real; las demás, la general.
            autor = getattr(self, "ultimo_post", {}).get("busqueda_proyectos[autor]", "")
            anio = getattr(self, "ultimo_post", {}).get("busqueda_proyectos[expedienteNumeroPos]", "")
            if autor:
                archivo = FIXTURES / f"avanzada_autor_{autor}_{anio}.xls"
                if not archivo.exists():
                    raise ErrorRed(f"El sitio respondió con el código 404 para {url}.")
                return Respuesta(url, 200, contenido=archivo.read_bytes())
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
