"""Cantidades en forma normativa: «VEINTIÚN (21) expedientes»."""

from __future__ import annotations

_HASTA_29 = [
    "", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ", "ONCE", "DOCE",
    "TRECE", "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE", "VEINTIUNO",
    "VEINTIDÓS", "VEINTITRÉS", "VEINTICUATRO", "VEINTICINCO", "VEINTISÉIS", "VEINTISIETE", "VEINTIOCHO",
    "VEINTINUEVE",
]
_DECENAS = {3: "TREINTA", 4: "CUARENTA", 5: "CINCUENTA", 6: "SESENTA", 7: "SETENTA", 8: "OCHENTA", 9: "NOVENTA"}
_CENTENAS = {1: "CIENTO", 2: "DOSCIENTOS", 3: "TRESCIENTOS", 4: "CUATROCIENTOS", 5: "QUINIENTOS",
             6: "SEISCIENTOS", 7: "SETECIENTOS", 8: "OCHOCIENTOS", 9: "NOVECIENTOS"}


def _apocope(texto: str, femenino: bool) -> str:
    """Forma que precede al sustantivo: UNO → UN/UNA, VEINTIUNO → VEINTIÚN/VEINTIUNA."""
    if texto.endswith("VEINTIUNO"):
        return texto[:-9] + ("VEINTIUNA" if femenino else "VEINTIÚN")
    if texto.endswith("UNO"):
        return texto[:-3] + ("UNA" if femenino else "UN")
    return texto


def _menor_que_mil(n: int, femenino: bool) -> str:
    if n == 100:
        return "CIEN"
    centena, resto = divmod(n, 100)
    partes = []
    if centena:
        palabra = _CENTENAS[centena]
        if femenino and centena > 1:
            palabra = palabra[:-2] + "AS"
        partes.append(palabra)
    if resto:
        if resto < 30:
            partes.append(_HASTA_29[resto])
        else:
            decena, unidad = divmod(resto, 10)
            partes.append(_DECENAS[decena] + (f" Y {_HASTA_29[unidad]}" if unidad else ""))
    return " ".join(partes)


def en_letras(n: int, femenino: bool = False) -> str:
    """Cardinal en mayúsculas, en la forma que va antes de un sustantivo."""
    if n == 0:
        return "CERO"
    if n < 0:
        return "MENOS " + en_letras(-n, femenino)
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes = []
    if millones:
        partes.append("UN MILLÓN" if millones == 1 else _apocope(_menor_que_mil(millones, False), False) + " MILLONES")
    if miles:
        partes.append("MIL" if miles == 1 else _apocope(_menor_que_mil(miles, femenino), femenino) + " MIL")
    if unidades:
        partes.append(_apocope(_menor_que_mil(unidades, femenino), femenino))
    return " ".join(partes)


def cantidad(n: int, singular: str, plural: str, femenino: bool = False) -> str:
    """cantidad(21, 'expediente', 'expedientes') → 'VEINTIÚN (21) expedientes'."""
    return f"{en_letras(n, femenino)} ({n}) {singular if n == 1 else plural}"
