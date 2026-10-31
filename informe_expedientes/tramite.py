"""Recorrido de un proyecto de ley según la Constitución Nacional (arts. 77 a 84).

- Art. 78: aprobado por la cámara de origen, pasa a la revisora; aprobado por ambas,
  pasa al Poder Ejecutivo, que lo promulga.
- Art. 80: se reputa aprobado si el Poder Ejecutivo no lo devuelve en diez días útiles.
  Las partes no vetadas solo pueden promulgarse si tienen autonomía normativa.
- Art. 81: un proyecto desechado totalmente no puede repetirse en las sesiones del
  año. Si la revisora lo modifica, vuelve a la de origen, que puede aceptar los
  cambios por mayoría absoluta o insistir en su texto; si la revisora los votó por dos
  tercios, la de origen necesita también dos tercios. No puede agregar cambios nuevos.
- Art. 83: vetado en todo o en parte, vuelve a la cámara de origen; si las dos
  insisten con dos tercios, es ley. Si difieren, no puede repetirse en ese año.

El recorrido se arma con la ficha del Senado y se completa con el sitio de Diputados
(que suele registrar antes la media sanción, el pase y el veto) y con las actas del
recinto. Lo que solo figura en Diputados se anota como contraste.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .modelos import Ficha, Votacion
from .numeros import cantidad
from .util import fmt_fecha, normalizar, parsear_fecha

SENADO, DIPUTADOS = "Senado", "Diputados"


@dataclass
class Paso:
    camara: str
    fecha: date | None
    fuente: str                    # ficha · diputados · votación
    con_modificaciones: bool = False
    votacion: Votacion | None = None


@dataclass
class Recorrido:
    origen: str
    revisora: str
    aprobacion_origen: Paso | None = None
    revision: Paso | None = None            # la revisora aprobó (sin cambios o con modificaciones)
    revision_modifico: bool = False
    vuelta: Paso | None = None              # la de origen resolvió sobre los cambios (art. 81)
    vuelta_insistio: bool = False
    rechazo: Paso | None = None
    sancion: Paso | None = None             # sanción definitiva del Congreso
    numero_ley: str | None = None
    pe: str | None = None                   # promulgó · veto total · veto parcial
    pe_fecha: date | None = None
    pe_decreto: str | None = None
    insistencia: str | None = None          # lograda · rechazada
    insistencia_fecha: date | None = None
    insistencia_camara: str = ""
    contraste: list[str] = field(default_factory=list)

    @property
    def veto(self) -> bool:
        return bool(self.pe and "VETO" in normalizar(self.pe))

    @property
    def veto_parcial(self) -> bool:
        return bool(self.pe and "PARCIAL" in normalizar(self.pe))


def _camara(titulo: str) -> str | None:
    n = normalizar(titulo)
    if n.startswith("SENAD"):
        return SENADO
    if "DIPUTADOS" in n:
        return DIPUTADOS
    return None


def _la(camara: str) -> str:
    return "el Senado" if camara == SENADO else "la Cámara de Diputados"


def _del(camara: str) -> str:
    return "del Senado" if camara == SENADO else "de la Cámara de Diputados"


def _La(camara: str) -> str:
    return "El Senado" if camara == SENADO else "La Cámara de Diputados"


def _al(camara: str) -> str:
    return "al Senado" if camara == SENADO else "a la Cámara de Diputados"


def armar(ficha: Ficha, diputados=None, votada: Votacion | None = None) -> Recorrido:
    """`diputados` es un hcdn.ProyectoHCDN (o None); `votada`, una votación que la ficha no registra."""
    origen = DIPUTADOS if ficha.id.origen == "CD" else SENADO
    r = Recorrido(origen, SENADO if origen == DIPUTADOS else DIPUTADOS)

    # ---- ficha del Senado, en el orden en que la escribe
    if origen == DIPUTADOS and ficha.etapa_diputados and (ficha.etapa_diputados.fecha_sancion
                                                          or ficha.etapa_diputados.expedientes):
        r.aprobacion_origen = Paso(DIPUTADOS, ficha.etapa_diputados.fecha_sancion, "ficha")
    for b in ficha.resoluciones:
        n = normalizar(b.titulo)
        if n.startswith("SANCION DE LEY"):
            r.numero_ley = b.valor("NUMERO DE LEY")
            r.sancion = r.sancion or Paso(r.vuelta.camara if r.vuelta else (r.revisora if r.revision else r.origen),
                                          parsear_fecha(b.valor("FECHA DE SANCION")), "ficha")
            continue
        if n.startswith("PODER EJECUTIVO"):
            r.pe = b.valor("RESOLUCION")
            r.pe_fecha = parsear_fecha(b.valor("FECHA DEL DECRETO") or b.valor("FECHA"))
            r.pe_decreto = b.valor("DECRETO NUMERO")
            continue
        camara = _camara(b.titulo)
        if not camara:
            continue
        sancion = normalizar(b.valor("SANCION") or "")
        comentario = normalizar(" ".join(filter(None, [b.valor("COMENTARIO"), b.valor("NOTA")])))
        paso = Paso(camara, parsear_fecha(b.valor("FECHA DE SANCION")), "ficha",
                    "MODIFIC" in sancion or "MODIFICACION" in comentario)
        if "RECHAZ" in sancion:
            r.rechazo = paso
        elif camara == r.origen and r.revision is None:
            r.aprobacion_origen = paso
        elif camara == r.revisora:
            r.revision, r.revision_modifico = paso, paso.con_modificaciones
        elif camara == r.origen and r.revision is not None:
            r.vuelta, r.vuelta_insistio = paso, "INSIST" in sancion + comentario
        if re.search(r"\bLEY\b", comentario) and not r.sancion:
            r.sancion = Paso(camara, paso.fecha, "ficha")

    # ---- votación del recinto que la ficha todavía no registra
    if votada is not None and votada.aprobada:
        paso = Paso(SENADO, votada.fecha, "votación", votacion=votada)
        if r.origen == SENADO and not r.aprobacion_origen:
            r.aprobacion_origen = paso
        elif r.revisora == SENADO and not r.revision:
            r.revision = paso
    elif votada is not None and votada.rechazada and not r.rechazo:
        r.rechazo = Paso(SENADO, votada.fecha, "votación", votacion=votada)

    if diputados is not None:
        _completar_con_diputados(r, diputados)
    return r


def _completar_con_diputados(r: Recorrido, p) -> None:
    """Agrega lo que registra Diputados y la ficha todavía no; anota cada diferencia."""
    vuelve = any(normalizar(m.movimiento).startswith("VUELVE A") for m in p.pases())
    vista_revisora = False
    for m in p.sanciones():
        camara = SENADO if normalizar(m.camara).startswith("SENAD") else DIPUTADOS
        modif = "MODIFICACION" in normalizar(m.movimiento)
        definitiva = normalizar(m.resultado) == "SANCIONADO"
        if camara == r.origen and not vista_revisora:
            # Aprobación de la cámara de origen (media sanción).
            if r.aprobacion_origen is None:
                r.aprobacion_origen = Paso(camara, m.fecha, "diputados", modif)
                r.contraste.append(f"El sitio de Diputados registra la media sanción {_del(camara)} del "
                                   f"{fmt_fecha(m.fecha)}" + (", con modificaciones al dictamen" if modif else "")
                                   + "; la ficha del Senado todavía no.")
            else:
                if r.aprobacion_origen.fuente == "votación":
                    r.contraste.append(f"El sitio de Diputados confirma la media sanción {_del(camara)} del "
                                       f"{fmt_fecha(m.fecha)}" + (", con modificaciones al dictamen" if modif else "")
                                       + f" y el pase {_al(r.revisora)}.")
                r.aprobacion_origen.con_modificaciones |= modif
        elif camara == r.revisora:
            vista_revisora = True
            modifico = vuelve and not definitiva
            if r.revision is None:
                r.revision, r.revision_modifico = Paso(camara, m.fecha, "diputados", modifico), modifico
                r.contraste.append(f"El sitio de Diputados registra que {_la(camara)} "
                                   + ("lo aprobó con modificaciones" if modifico else "lo sancionó")
                                   + f" el {fmt_fecha(m.fecha)}; la ficha del Senado todavía no.")
            elif modifico and not r.revision_modifico:
                r.revision_modifico = r.revision.con_modificaciones = True
            if definitiva and not r.sancion:
                r.sancion = Paso(camara, m.fecha, "diputados")
        elif camara == r.origen and definitiva:
            # Vuelta a la cámara de origen (art. 81).
            if r.vuelta is None:
                r.vuelta = Paso(camara, m.fecha, "diputados")
                r.vuelta_insistio = "INSIST" in normalizar(m.movimiento)
                r.contraste.append(f"El sitio de Diputados registra la sanción definitiva {_del(camara)} del "
                                   f"{fmt_fecha(m.fecha)}; la ficha del Senado todavía no.")
            if not r.sancion:
                r.sancion = Paso(camara, m.fecha, "diputados")
    if p.ley and r.numero_ley and re.sub(r"\D", "", p.ley) != re.sub(r"\D", "", r.numero_ley):
        r.contraste.append(f"Atención: Diputados registra la Ley {p.ley} y la ficha del Senado, la Ley {r.numero_ley}.")
    if p.ley and not r.numero_ley:
        r.numero_ley = p.ley
        r.contraste.append(f"El sitio de Diputados registra el número de ley ({p.ley}); la ficha del Senado todavía no.")
    veto = p.veto()
    if veto and not r.pe:
        n = normalizar(veto.movimiento)
        r.pe = "Veto parcial" if "PARCIAL" in n else "Veto total"
        r.contraste.append(f"El sitio de Diputados registra el {r.pe.lower()} del Poder Ejecutivo; la ficha del Senado "
                           "todavía no.")
    for m in p.insistencia():
        n = normalizar(m.movimiento)
        r.insistencia_fecha, r.insistencia_camara = m.fecha, (SENADO if normalizar(m.camara).startswith("SENAD")
                                                               else DIPUTADOS)
        r.insistencia = "rechazada" if ("RECHAZO" in n or "ACEPTA VETO" in n or "NO ALCANZA" in n) else "lograda"


# =========================================================== textos (Constitución)

def lineas(r: Recorrido, hoy: date) -> list[str]:
    """Qué sigue según la Constitución, para el detalle de la situación."""
    salida: list[str] = []
    if r.rechazo and not r.sancion:
        salida.append(f"Rechazado por {_la(r.rechazo.camara)} el {fmt_fecha(r.rechazo.fecha)}: un proyecto desechado "
                      "totalmente no puede repetirse en las sesiones de ese año (art. 81 CN).")
        return salida
    if r.sancion:
        if r.vuelta:
            salida.append(f"{_La(r.origen)} "
                          + ("insistió en su texto original" if r.vuelta_insistio
                             else "aceptó las modificaciones " + _del(r.revisora))
                          + f" el {fmt_fecha(r.vuelta.fecha)} (art. 81 CN).")
        if not r.pe:
            salida.append("Pasa al Poder Ejecutivo: si no lo devuelve en diez días útiles, queda promulgado "
                          "(art. 80 CN).")
        elif r.veto:
            decreto = f" (Decreto {r.pe_decreto})" if r.pe_decreto else ""
            if r.veto_parcial:
                salida.append(f"Vetado parcialmente{decreto}: las partes no observadas solo pueden promulgarse si "
                              "tienen autonomía normativa (art. 80 CN); sobre lo observado, la cámara de origen puede "
                              "insistir con dos tercios (art. 83 CN).")
            else:
                salida.append(f"Vetado totalmente{decreto}: vuelve a {_la(r.origen)}, que puede insistir con dos "
                              "tercios de los votos; si las dos cámaras insisten con esa mayoría, es ley (art. 83 CN).")
            if r.insistencia == "rechazada":
                salida.append(f"El {fmt_fecha(r.insistencia_fecha)}, {_la(r.insistencia_camara)} no alcanzó los dos "
                              "tercios para insistir: queda firme el veto y el proyecto no puede repetirse en las "
                              "sesiones de ese año (art. 83 CN).")
            elif r.insistencia == "lograda":
                salida.append(f"El {fmt_fecha(r.insistencia_fecha)}, {_la(r.insistencia_camara)} insistió con dos "
                              "tercios (art. 83 CN).")
        return salida
    if r.revision and r.revision_modifico:
        texto = (f"{_La(r.revisora)} lo aprobó con modificaciones el {fmt_fecha(r.revision.fecha)}: "
                 f"vuelve {_al(r.origen)}, que puede aceptarlas por mayoría absoluta de los presentes o insistir en "
                 "su texto original; si las modificaciones se votaron por dos tercios de los presentes, para insistir "
                 "hacen falta también dos tercios. No puede introducir cambios nuevos (art. 81 CN).")
        salida.append(texto)
        v = r.revision.votacion
        if v is not None and v.dos_tercios is not None:
            salida.append(f"En el Senado se votó con {cantidad(v.afirmativos, 'voto afirmativo', 'votos afirmativos')} "
                          f"sobre {cantidad(v.presentes_contados, 'presente', 'presentes')}: "
                          + ("alcanza" if v.dos_tercios else "no alcanza")
                          + " los dos tercios (dato de la votación en general, orientativo).")
        return salida
    if r.revision:
        salida.append(f"{_La(r.revisora)} lo aprobó sin cambios el {fmt_fecha(r.revision.fecha)}.")
        return salida
    if r.aprobacion_origen:
        salida.append(f"Pasa {_al(r.revisora)} para su revisión (art. 78 CN).")
    return salida


__all__ = ["Recorrido", "Paso", "armar", "lineas", "SENADO", "DIPUTADOS"]
