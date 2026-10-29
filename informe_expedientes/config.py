"""Direcciones del sitio, códigos oficiales y parámetros por defecto."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE = "https://www.senado.gob.ar"

URL_FICHA = BASE + "/parlamentario/comisiones/verExp/{numero}.{anio2:02d}/{origen}/{tipo}"
URL_BUSCADOR = BASE + "/parlamentario/parlamentaria/"
URL_AVANZADA = BASE + "/parlamentario/parlamentaria/avanzada"
URL_XLS_AVANZADA = BASE + "/micrositios/DatosAbiertosExpedientes/BusquedaAvanzada/XLS"
URL_COMISION = BASE + "/parlamentario/comisiones/info/{id}"
URL_AGENDA = BASE + "/parlamentario/comisiones/agenda/{id}"
URL_HCDN_PROYECTO = "https://www.hcdn.gob.ar/proyectos/proyecto.jsp?exp={exp}"

USER_AGENT = (
    "Mozilla/5.0 (compatible; InformeExpedientes/1.0; "
    "consulta de expedientes del H. Senado de la Nacion)"
)

# Orígenes tal como los usa el buscador del Senado (busqueda_proyectos[expedienteLugar]).
ORIGENES: dict[str, str] = {
    "S": "Senado de la Nación",
    "CD": "Cámara de Diputados",
    "PE": "Poder Ejecutivo Nacional",
    "JGM": "Jefatura de Gabinete de Ministros",
    "OV": "Oficiales varios",
    "OVD": "Oficiales varios de la H. Cámara de Diputados",
    "P": "Particulares",
    "DCD": "Comunicación de dictamen de Diputados",
}

# Nombre del origen en la ficha → código.
ORIGEN_POR_NOMBRE: dict[str, str] = {
    "SENADO DE LA NACION": "S",
    "CAMARA DE DIPUTADOS": "CD",
    "PODER EJECUTIVO NACIONAL": "PE",
    "PODER EJECUTIVO": "PE",
    "JEFATURA GABINETE MINISTROS": "JGM",
    "JEFATURA DE GABINETE DE MINISTROS": "JGM",
    "OFICIALES VARIOS": "OV",
    "OFIC.VARIOS H.CAMARA DIPUTADOS": "OVD",
    "PARTICULARES": "P",
    "COMUNIC.DICTAMEN DIPUTADOS": "DCD",
}

# Tipos de expediente (busqueda_proyectos[expedienteTipo]).
TIPOS: dict[str, str] = {
    "PL": "Proyecto de ley",
    "PD": "Proyecto de declaración",
    "PR": "Proyecto de resolución",
    "PC": "Proyecto de comunicación",
    "DE": "Proyecto de decreto",
    "AC": "Acuerdos",
    "DC": "Decreto",
    "MS": "Mensaje de Senado",
    "MD": "Mensaje de Diputados",
    "RC": "Resolución conjunta",
    "CA": "Comunicaciones de auditoría",
    "CC": "Comunicaciones de comisiones",
    "CD": "Comunicaciones de Diputados",
    "CM": "Comunicaciones de ministerios",
    "CO": "Comunicaciones de senadores",
    "CV": "Comunicaciones varias",
    "CE": "Comunicación del Poder Ejecutivo",
    "C1": "C.E. (art. 101 C.N.)",
    "C2": "C.E. (art. 37 Ley 24.156)",
    "PP": "Peticiones",
    "RP": "Respuesta de presidencia",
}

# Nombre del tipo en el sitio (normalizado) → código.
TIPO_POR_NOMBRE: dict[str, str] = {
    "ACUERDOS": "AC",
    "C.E. (ART. 101 C.N.)": "C1",
    "C.E. (ART. 37 LEY 24.156)": "C2",
    "COMUNICACIONES DE AUDITORIA": "CA",
    "COMUNICACIONES DE COMISIONES": "CC",
    "COMUNICACIONES DE DIPUTADOS": "CD",
    "COMUNICACIONES DE MINISTERIOS": "CM",
    "COMUNICACIONES DE SENADORES": "CO",
    "COMUNICACIONES VARIAS": "CV",
    "COMUNICACION DEL P.EJECUTIVO": "CE",
    "COMUNICACION DEL PODER EJECUTIVO": "CE",
    "DECRETO": "DC",
    "MENSAJE DE SENADO": "MS",
    "MENSAJE DIPUTADOS": "MD",
    "PETICIONES": "PP",
    "PROYECTO DE COMUNICACION": "PC",
    "PROYECTO DE DECLARACION": "PD",
    "PROYECTO DE DECRETO": "DE",
    "PROYECTO DE LEY": "PL",
    "PROYECTO DE RESOLUCION": "PR",
    "RESOLUCION CONJUNTA": "RC",
    "RESPUESTA DE PRESIDENCIA": "RP",
}

# Instrumento que resulta de aprobar cada tipo de proyecto.
INSTRUMENTO: dict[str, str] = {
    "PD": "declaración",
    "PR": "resolución",
    "PC": "comunicación",
    "DE": "decreto",
}

# Si el usuario no indica el tipo y el buscador no responde, se prueban en este orden.
CANDIDATOS_TIPO: dict[str, list[str]] = {
    "S": ["PL", "PD", "PR", "PC", "DE", "CO", "MS", "RC", "CC", "PP"],
    "CD": ["PL", "CD", "MD", "PR", "PD", "PC"],
    "PE": ["PL", "DC", "AC", "CE", "MS", "C1", "C2"],
    "JGM": ["CE", "CM", "C1", "C2", "PL", "DC"],
    "OV": ["CV", "CM", "CA", "CC", "PP"],
    "OVD": ["CV", "CD", "CM"],
    "P": ["PP", "CV"],
    "DCD": ["CD", "MD", "CV"],
}

# Comisiones del Senado con su número interno (comisiones/info/{id}).
# Copiado del formulario oficial; al iniciar una búsqueda se actualiza desde el sitio.
COMISIONES: dict[int, str] = {
    76: 'BANCA DE LA MUJER',
    117: 'BICAMERAL ASESORA DE LA FEDERACIÓN ARGENTINA DE MUNICIPIOS (LEY 24.807)',
    118: 'BICAMERAL DE CONTROL DE LOS FONDOS DE LA SEGURIDAD SOCIAL (LEY 26.425)',
    315: 'BICAMERAL DE REFORMA DEL ESTADO Y DEL SEGUIMIENTO DE LAS PRIVATIZACIONES (LEY 23.696)',
    104: 'BICAMERAL PERMANENTE DE FISCALIZACIÓN DE LOS ORGANISMOS Y ACTIVIDADES DE INTELIGENCIA (LEY 25.520)',
    107: 'BICAMERAL PERMANENTE DE FISCALIZACIÓN DE LOS ÓRGANOS Y ACTIVIDADES DE SEGURIDAD INTERIOR (LEY 24.059 Y SUS MODIFICATORIAS LEYES 24.194 Y 25.520)',
    103: 'BICAMERAL PERMANENTE DE LA DEFENSORÍA DEL PUEBLO',
    106: 'BICAMERAL PERMANENTE DE PROMOCIÓN Y SEGUIMIENTO DE LA COMUNICACIÓN AUDIOVISUAL, LAS TECNOLOGÍAS DE LAS TELECOMUNICACIONES Y LA DIGITALIZACIÓN (LEY 26.522,Y SUS MODIFICATORIAS 27.078 Y DNU 267/15)',
    114: 'BICAMERAL PERMANENTE DE SEGUIMIENTO DE CONTRATOS DE PARTICIPACIÓN PÚBLICO-PRIVADA (LEY 27.328)',
    119: 'BICAMERAL PERMANENTE DE SEGUIMIENTO DE LA FABRICACIÓN, COMERCIALIZACIÓN Y DISTRIBUCIÓN DE PASTA CELULOSA Y DE PAPEL PARA DIARIOS (LEY 26.736, ARTÍCULO 2°)',
    111: 'BICAMERAL PERMANENTE DE SEGUIMIENTO Y CONTROL DE LA GESTIÓN DE CONTRATACIÓN Y DE PAGO DE LA DEUDA EXTERIOR DE LA NACIÓN (LEY 27.249)',
    110: 'BICAMERAL PERMANENTE DE SEGUIMIENTO Y CONTROL DEL MINISTERIO PÚBLICO DE LA NACIÓN (LEY 24.946 Y SUS MODIFICATORIAS LEY 27.148 Y 27.149)',
    105: 'BICAMERAL PERMANENTE DE TRÁMITE LEGISLATIVO (LEY 26.122)',
    115: 'BICAMERAL PERMANENTE DEL DEFENSOR DE LOS DERECHOS DE NIÑAS, NIÑOS Y ADOLESCENTES (LEY 26.061)',
    108: 'BICAMERAL PERMANENTE DEL DIGESTO JURÍDICO ARGENTINO (LEY 26.939)',
    112: 'BICAMERAL PERMANENTE INTERPARLAMENTARIA ARGENTINO-MEXICANA',
    100: 'BICAMERAL PERMANENTE MIXTA REVISORA DE CUENTAS',
    113: 'BICAMERAL PERMANENTE PARLAMENTARIA CONJUNTA ARGENTINO-CHILENA',
    71: 'DE ACUERDOS',
    62: 'DE AGRICULTURA, GANADERÍA Y PESCA',
    69: 'DE AMBIENTE Y DESARROLLO SUSTENTABLE',
    55: 'DE ASUNTOS ADMINISTRATIVOS Y MUNICIPALES',
    50: 'DE ASUNTOS CONSTITUCIONALES',
    74: 'DE CIENCIA Y TECNOLOGÍA',
    72: 'DE COPARTICIPACIÓN FEDERAL DE IMPUESTOS',
    56: 'DE DEFENSA NACIONAL',
    77: 'DE DEPORTE',
    64: 'DE DERECHOS Y GARANTÍAS',
    58: 'DE ECONOMÍA NACIONAL E INVERSIÓN',
    60: 'DE ECONOMÍAS REGIONALES, ECONOMÍA SOCIAL, MICRO, PEQUEÑA Y MEDIANA EMPRESA',
    75: 'DE EDUCACIÓN Y CULTURA',
    59: 'DE INDUSTRIA Y COMERCIO',
    67: 'DE INFRAESTRUCTURA, VIVIENDA Y TRANSPORTE',
    116: 'DE INTEGRACIÓN BILATERAL Y COOPERACIÓN ENTRE LA REPÚBLICA ARGENTINA Y LA REPÚBLICA FEDERATIVA DE BRASIL',
    109: 'DE INVESTIGACION DEL ORIGEN Y SEGUIMIENTO DE LA GESTION Y DEL PAGO DE LA DEUDA EXTERIOR DE LA NACION - LEY 26.984 ART. 12.',
    52: 'DE JUSTICIA Y ASUNTOS PENALES',
    53: 'DE LEGISLACIÓN GENERAL',
    65: 'DE MINERÍA, ENERGÍA Y COMBUSTIBLES',
    70: 'DE POBLACIÓN Y DESARROLLO HUMANO',
    54: 'DE PRESUPUESTO Y HACIENDA',
    51: 'DE RELACIONES EXTERIORES Y CULTO',
    78: 'DE SALUD',
    57: 'DE SEGURIDAD INTERIOR Y NARCOTRÁFICO',
    68: 'DE SISTEMAS, MEDIOS DE COMUNICACIÓN Y LIBERTAD DE EXPRESIÓN',
    61: 'DE TRABAJO Y PREVISIÓN SOCIAL',
    73: 'DE TURISMO',
}

# Vigencia de la caché, en segundos.
TTL_FICHA = 10 * 60
TTL_LISTADO = 6 * 3600
TTL_NOTA_RECIENTE = 12 * 3600
TTL_NOTA_ANTIGUA = 90 * 86400
TTL_AGENDA = 3600
TTL_ORDEN_DIA = 30 * 86400

INTERVALO_ENTRE_PEDIDOS = 0.3   # segundos entre pedidos al sitio
HILOS_POR_DEFECTO = 4
MAX_PAGINAS_POR_LISTADO = 40


def carpeta_app() -> Path:
    """Carpeta para la configuración y la caché del programa."""
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home()) / "InformeExpedientes"
    return Path.home() / ".informe_expedientes"


def carpeta_informes_por_defecto() -> Path:
    documentos = Path.home() / "Documents"
    if not documentos.exists():
        documentos = Path.home() / "Documentos"
    if not documentos.exists():
        documentos = Path.home()
    return documentos / "Informes de expedientes"
