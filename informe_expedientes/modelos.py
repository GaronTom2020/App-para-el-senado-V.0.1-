"""Estructuras de datos del informe."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .identificador import IdExpediente
from .util import normalizar


@dataclass
class Documento:
    etiqueta: str
    url: str


@dataclass
class Autor:
    nombre: str
    url: str | None = None


@dataclass
class EtapaDiputados:
    texto_expedientes: str = ""
    expedientes: list[str] = field(default_factory=list)    # 1752-D-2023
    orden_del_dia: str | None = None                        # número de OD de Diputados
    tramite_parlamentario: str | None = None
    fecha_sancion: date | None = None
    autor: str | None = None


@dataclass
class Giro:
    comision: str
    orden: int | None
    ingreso: date | None
    egreso: date | None
    comision_id: int | None = None

    @property
    def abierto(self) -> bool:
        return self.ingreso is not None and self.egreso is None


@dataclass
class OrdenDelDia:
    numero: str
    fecha: date | None
    estado: str
    anexo: str = ""
    url: str | None = None
    url_pdf: str | None = None

    @property
    def situacion(self) -> str:
        n = normalizar(self.estado)
        if "CADUC" in n:
            return "caduca"
        if "RECHAZ" in n:
            return "rechazada"
        if "APROB" in n:
            return "aprobada"
        if "RETIR" in n:
            return "retirada"
        if "VUELT" in n or "VUELVE" in n:
            return "vuelta"
        return "vigente"


@dataclass
class BloqueResolucion:
    titulo: str
    campos: list[tuple[str, str]]

    def valor(self, clave: str) -> str | None:
        objetivo = normalizar(clave)
        for k, v in self.campos:
            if normalizar(k) == objetivo:
                return v or None
        return None


@dataclass
class Ficha:
    id: IdExpediente
    url: str
    numero_texto: str = ""
    origen_texto: str = ""
    tipo_texto: str = ""
    extracto: str = ""
    autores: list[Autor] = field(default_factory=list)
    etapa_diputados: EtapaDiputados | None = None
    fecha_mesa_entradas: date | None = None
    fecha_dado_cuenta: date | None = None
    dae: str | None = None
    dae_tipo: str | None = None
    ingresos_comisiones: list[tuple[date | None, str]] = field(default_factory=list)
    giros: list[Giro] = field(default_factory=list)
    hitos: list[str] = field(default_factory=list)
    fecha_archivo: date | None = None
    fecha_caducidad_registrada: date | None = None
    mocion_preferencia: date | None = None
    mocion_para: str | None = None
    resoluciones: list[BloqueResolucion] = field(default_factory=list)
    observaciones: list[str] = field(default_factory=list)
    anotaciones: list[str] = field(default_factory=list)
    ordenes_del_dia: list[OrdenDelDia] = field(default_factory=list)
    texto_original: Documento | None = None
    textos_definitivos: list[Documento] = field(default_factory=list)
    texto_definitivo_pendiente: bool = False
    advertencias: list[str] = field(default_factory=list)

    def bloque(self, *fragmentos: str, exacto: bool = False) -> BloqueResolucion | None:
        for b in self.resoluciones:
            t = normalizar(b.titulo)
            if exacto and t in [normalizar(f) for f in fragmentos]:
                return b
            if not exacto and all(normalizar(f) in t for f in fragmentos):
                return b
        return None


@dataclass
class Reunion:
    url: str
    nota_id: str
    titulo: str
    fecha: date | None
    comisiones: list[str]
    tipo: str                      # Comisión · Plenario · Asesores
    resumen: str = ""
    videos: list[str] = field(default_factory=list)
    versiones: list[Documento] = field(default_factory=list)
    otros_archivos: list[Documento] = field(default_factory=list)


@dataclass
class ReunionConvocada:
    fecha: date | None
    fecha_texto: str
    hora: str
    lugar: str
    titulo: str
    comision: str
    url: str


@dataclass
class Paso:
    nombre: str
    estado: str                    # hecho · actual · pendiente · detenido
    fecha: date | None = None
    detalle: str = ""


@dataclass
class Caducidad:
    fecha: date
    fundamento: str
    vencida: bool
    registrada: bool               # True si figura en la ficha del Senado


@dataclass
class Situacion:
    titulo: str
    nivel: str                     # en_comision · con_dictamen · aprobado · sancionado · vetado ·
                                   # caducado · archivado · rechazado · en_tramite · desconocido
    detalle: list[str] = field(default_factory=list)
    pasos: list[Paso] = field(default_factory=list)
    caducidad: Caducidad | None = None
    contraste: list[str] = field(default_factory=list)   # lo que agrega o corrige el sitio de Diputados


@dataclass
class BusquedaReuniones:
    realizada: bool = False
    desde: date | None = None
    hasta: date | None = None
    comisiones: list[str] = field(default_factory=list)
    comisiones_sin_pagina: list[str] = field(default_factory=list)
    notas_revisadas: int = 0
    incluye_asesores: bool = True
    motivo: str = ""


@dataclass
class Votacion:
    """Una votación nominal del recinto, tal como la publica la Secretaría Parlamentaria."""
    id: int
    fecha: date | None
    titulo: str = ""
    tipo: str = ""                 # EN GENERAL · EN PARTICULAR · EN GENERAL Y EN PARTICULAR · MOCIÓN DE ORDEN…
    resultado: str = ""            # AFIRMATIVO · NEGATIVO
    mayoria: str = ""
    numero_en_sesion: str = ""
    articulos: str = ""
    expedientes: list[str] = field(default_factory=list)    # S-1234/24
    ordenes_del_dia: list[str] = field(default_factory=list)  # 409/26
    hora: str = ""
    quorum: str = ""
    presentes: int | None = None
    presidente: str = ""
    afirmativos: int | None = None
    negativos: int | None = None
    abstenciones: int | None = None
    ausentes: int | None = None
    fuente: str = "listado"        # listado · detalle · pdf
    discrepancia: str = ""         # si el detalle y el PDF del acta no coinciden
    url_detalle: str | None = None
    url_pdf: str | None = None
    video: str | None = None

    @property
    def aprobada(self) -> bool:
        return normalizar(self.resultado).startswith("AFIRMATIV")

    @property
    def rechazada(self) -> bool:
        return normalizar(self.resultado).startswith("NEGATIV")

    @property
    def en_general(self) -> bool:
        """Votación que decide sobre el proyecto (no un artículo ni una moción)."""
        return normalizar(self.tipo) in ("EN GENERAL", "EN GENERAL Y EN PARTICULAR") and not self.insistencia

    @property
    def en_particular(self) -> bool:
        return normalizar(self.tipo) == "EN PARTICULAR"

    @property
    def insistencia(self) -> bool:
        """Insistencia ante un veto o en la sanción original (arts. 81 y 83 de la Constitución)."""
        tipo = normalizar(self.tipo)
        return ("INSISTENCIA" in normalizar(self.titulo) and not normalizar(self.titulo).startswith("HABILITACION")
                and "HABILITACION" not in tipo and "MOCION" not in tipo)

    @property
    def presentes_contados(self) -> int | None:
        if self.presentes:
            return self.presentes
        if self.con_totales:
            return (self.afirmativos or 0) + (self.negativos or 0) + (self.abstenciones or 0)
        return None

    @property
    def dos_tercios(self) -> bool | None:
        """¿Los afirmativos alcanzan las dos terceras partes de los presentes?"""
        presentes = self.presentes_contados
        if not presentes or self.afirmativos is None:
            return None
        return 3 * self.afirmativos >= 2 * presentes

    @property
    def con_totales(self) -> bool:
        return bool(self.afirmativos or self.negativos or self.abstenciones or self.ausentes)

    @property
    def url(self) -> str | None:
        return self.url_detalle if self.fuente == "detalle" else (self.url_pdf or self.url_detalle)


@dataclass
class Resultado:
    ficha: Ficha
    situacion: Situacion
    reuniones: list[Reunion] = field(default_factory=list)
    convocadas: list[ReunionConvocada] = field(default_factory=list)
    busqueda: BusquedaReuniones = field(default_factory=BusquedaReuniones)
    agenda_consultada: bool = False
    votaciones: list[Votacion] = field(default_factory=list)
    votaciones_consultadas: bool = False
    diputados: object | None = None            # hcdn.ProyectoHCDN, si se consultó y se encontró
    diputados_consultado: bool = False
    notas_usuario: str = ""
    generado: datetime = field(default_factory=datetime.now)
    archivos: dict[str, Path] = field(default_factory=dict)
    advertencias: list[str] = field(default_factory=list)
