"""Ficha del expediente en el sitio del Senado (página «verExp»).

La ficha reúne: cabecera (número, origen, tipo, extracto), autores, etapa en
Diputados, fechas de mesa de entradas, giros a comisiones, hitos del trámite
(archivo, caducidad, moción de preferencia), resoluciones (sanción, ley, Poder
Ejecutivo), observaciones, órdenes del día y enlaces a los textos.

Las tablas se reconocen por su atributo `summary` (estable en el sitio) y, si
falta, por los títulos de sus columnas. Cada sección se lee por separado: si
una falla, se registra una advertencia y el resto sigue.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from . import config
from .cliente import Cliente, ErrorRed
from .comisiones import actualizar_mapa_comisiones
from .identificador import RE_URL_FICHA, IdExpediente
from .modelos import (
    Autor, BloqueResolucion, Documento, EtapaDiputados, Ficha, Giro, OrdenDelDia,
)
from .paginas import celdas, encabezado, filas_datos, sopa, tablas_hoja, texto
from .util import anio_cuatro_digitos, limpiar, normalizar, parsear_fecha


class ExpedienteNoEncontrado(Exception):
    """El sitio no devolvió una ficha válida para el expediente."""


_RE_TOKEN = re.compile(
    r'name="busqueda_proyectos\[_token\]"[^>]*value="([^"]+)"'
    r'|value="([^"]+)"[^>]*name="busqueda_proyectos\[_token\]"'
)
_CAMPOS_BUSQUEDA = [
    "autor", "palabra", "opcion", "palabra2", "comision", "tipoDocumento",
    "expedienteLugar", "expedienteNumeroPre", "expedienteNumeroPos", "expedienteTipo",
]
_RE_KV = re.compile(r"^([A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ0-9 .°º/()\-]{1,60}?)\s*:\s*(.*)$")
_RE_ANOTACION = re.compile(r"^\d{1,2}-\d{1,2}-\d{2,4}\s*[-–.]?\s+\S.{4,}$")
_SECCIONES_FICHA = (
    "NUMERO DE EXPEDIENTE", "FECHAS EN DIR", "FECHA DE INGRESO A DIR", "GIROS DEL EXPEDIENTE",
    "RESOLUCIONES", "ORDENES DEL DIA", "LISTADO DE AUTORES",
)


# ============================================================ tipo del expediente

def resolver_tipo(cliente: Cliente, ident: IdExpediente, avisar=None) -> str:
    """Devuelve el código de tipo (PL, PD…). Primero el buscador; si no, prueba la ficha."""
    avisar = avisar or (lambda *a, **k: None)
    if ident.tipo:
        return ident.tipo
    try:
        tipo = buscar_tipo(cliente, ident)
        if tipo:
            avisar("log", f"El buscador del Senado indica tipo {tipo}.")
            return tipo
    except ErrorRed as e:
        avisar("log", f"El buscador no respondió ({e}); se prueba directamente con la ficha.")

    for candidato in config.CANDIDATOS_TIPO.get(ident.origen, ["PL"]):
        cliente.verificar_cancelacion()
        try:
            r = cliente.get(ident.url_ficha(candidato), ttl=config.TTL_FICHA)
        except ErrorRed:
            continue
        ficha = parsear_ficha(r.texto, ident.url_ficha(candidato), ident.con_tipo(candidato))
        if ficha_valida(ficha, ident):
            real = config.TIPO_POR_NOMBRE.get(normalizar(ficha.tipo_texto))
            tipo = real or candidato
            avisar("log", f"Ficha encontrada como {tipo}.")
            return tipo
    raise ExpedienteNoEncontrado(
        f"No se encontró el expediente {ident.corto} en el sitio del Senado. "
        "Revisá el número, el año y el origen, o elegí el tipo a mano."
    )


def buscar_tipo(cliente: Cliente, ident: IdExpediente) -> str | None:
    """Usa la búsqueda avanzada del sitio (formulario con token por sesión)."""
    cliente.sesion_nueva()
    r = cliente.get(config.URL_BUSCADOR)
    m = _RE_TOKEN.search(r.texto)
    if not m:
        return None
    actualizar_mapa_comisiones(r.texto)
    datos = {f"busqueda_proyectos[{c}]": "" for c in _CAMPOS_BUSQUEDA}
    datos.update({
        "busqueda_proyectos[expedienteLugar]": ident.origen,
        "busqueda_proyectos[expedienteNumeroPre]": str(ident.numero),
        "busqueda_proyectos[expedienteNumeroPos]": str(ident.anio),
        "busqueda_proyectos[_token]": m.group(1) or m.group(2),
    })
    resultados = cliente.post(config.URL_AVANZADA, datos)
    tipo = tipo_desde_resultados(resultados.texto, ident)
    if tipo:
        return tipo
    try:
        import xlrd  # noqa: F401  (opcional: sin él se omite la exportación XLS)
        xls = cliente.get(config.URL_XLS_AVANZADA, binario=True)
        return tipo_desde_xls(xls.contenido or b"", ident)
    except ImportError:
        return None
    except Exception:
        return None


def tipo_desde_resultados(html: str, ident: IdExpediente) -> str | None:
    s = sopa(html)
    for a in s.find_all("a", href=True):
        if ident.coincide_url(a["href"]):
            m = RE_URL_FICHA.search(a["href"])
            if m:
                return m.group("tipo").upper()
    patron = re.compile(rf"^0*{ident.numero}\s*/\s*(?:20)?{ident.anio2:02d}$")

    def codigo_tipo(valor: str) -> str | None:
        v = valor.upper()
        return v if v in config.TIPOS else config.TIPO_POR_NOMBRE.get(normalizar(valor))

    def es_origen(valor: str) -> bool:
        return valor.upper() == ident.origen or config.ORIGEN_POR_NOMBRE.get(normalizar(valor)) == ident.origen

    for tabla in s.find_all("table"):
        enc = encabezado(tabla)
        i_tipo = next((i for i, h in enumerate(enc) if h.startswith("TIPO")), None)
        i_origen = next((i for i, h in enumerate(enc) if h.startswith("ORIGEN")), None)
        for tr in filas_datos(tabla):
            valores = celdas(tr)
            if not any(patron.match(v) for v in valores):
                continue
            if i_origen is not None and i_origen < len(valores) and not es_origen(valores[i_origen]):
                continue
            if i_tipo is not None and i_tipo < len(valores):
                codigo = codigo_tipo(valores[i_tipo])
                if codigo:
                    return codigo
                continue
            # Sin títulos de columna: se descarta una celda igual al origen y se toma el primer tipo.
            restantes = list(valores)
            for i, v in enumerate(restantes):
                if es_origen(v):
                    del restantes[i]
                    break
            for v in restantes:
                codigo = codigo_tipo(v)
                if codigo:
                    return codigo
    return None


def tipo_desde_xls(contenido: bytes, ident: IdExpediente) -> str | None:
    import xlrd
    libro = xlrd.open_workbook(file_contents=contenido, ignore_workbook_corruption=True)
    hoja = libro.sheet_by_index(0)
    objetivo = f"{ident.numero}/{ident.anio2:02d}"
    for f in range(1, hoja.nrows):
        numero = limpiar(str(hoja.cell_value(f, 0))).lstrip("0")
        tipo = limpiar(str(hoja.cell_value(f, 1))).upper()
        origen = limpiar(str(hoja.cell_value(f, 2))).upper() if hoja.ncols > 2 else ident.origen
        if numero == objetivo and origen == ident.origen and tipo in config.TIPOS:
            return tipo
    return None


# ================================================================ ficha completa

def descargar_ficha(cliente: Cliente, ident: IdExpediente) -> Ficha:
    url = ident.url_ficha()
    r = cliente.get(url, ttl=config.TTL_FICHA)
    ficha = parsear_ficha(r.texto, url, ident)
    if not ficha_valida(ficha, ident):
        raise ExpedienteNoEncontrado(
            f"El Senado no devolvió datos para {ident.corto} con tipo {ident.tipo}. "
            "Revisá el número, el origen y el tipo."
        )
    origen_ficha = config.ORIGEN_POR_NOMBRE.get(normalizar(ficha.origen_texto))
    if origen_ficha and origen_ficha != ident.origen:
        ficha.advertencias.append(
            f"La ficha indica origen «{ficha.origen_texto}», distinto del código {ident.origen}."
        )
    return ficha


def ficha_valida(ficha: Ficha, ident: IdExpediente) -> bool:
    if not (ficha.origen_texto or ficha.extracto):
        return False
    m = re.match(r"0*(\d+)\s*/\s*(\d{2,4})", ficha.numero_texto or "")
    if m and (int(m.group(1)) != ident.numero or anio_cuatro_digitos(m.group(2)) != ident.anio):
        return False
    return True


def completar_ordenes_del_dia(cliente: Cliente, ficha: Ficha) -> None:
    """Busca el PDF de cada orden del día en su página de resultado."""
    for od in ficha.ordenes_del_dia:
        if not od.url:
            continue
        try:
            r = cliente.get(od.url, ttl=config.TTL_ORDEN_DIA)
        except ErrorRed:
            continue
        a = sopa(r.texto).find("a", href=re.compile(r"downloadOrdenDia", re.I))
        if a:
            od.url_pdf = urljoin(config.BASE, a["href"])


def parsear_ficha(html: str, url: str, ident: IdExpediente) -> Ficha:
    s = sopa(html)
    ficha = Ficha(id=ident, url=url)
    titulo = s.find(string=re.compile(r"N[úu]mero de Expediente", re.I))
    if titulo:
        m = re.search(r"Expediente\s+(\d+\s*/\s*\d{2,4})", limpiar(titulo))
        if m:
            ficha.numero_texto = m.group(1).replace(" ", "")

    lectores = {
        "cabecera": _cabecera, "autores": _autores, "diputados": _diputados, "mesa": _mesa,
        "dgc": _dgc, "giros": _giros, "ordenes": _ordenes, "observaciones": _observaciones,
    }
    leidas = []
    for tabla in tablas_hoja(s):
        clase = _clasificar(tabla)
        try:
            if clase in lectores:
                lectores[clase](tabla, ficha)
            elif clase == "otra":
                bloque = _bloque(tabla)
                if not bloque:
                    continue
                ficha.resoluciones.append(bloque)
            else:
                continue
            leidas.append(tabla)
        except Exception as e:  # una sección rara no debe impedir el informe
            ficha.advertencias.append(f"No se pudo leer una sección de la ficha ({clase}): {e}")

    try:
        _hitos(s, ficha)
        _textos(s, ficha)
    except Exception as e:
        ficha.advertencias.append(f"No se pudieron leer los hitos o los textos de la ficha: {e}")

    for tabla in leidas:
        tabla.decompose()
    _anotaciones(s, ficha)
    return ficha


# ---------------------------------------------------------------- secciones

def _clasificar(tabla) -> str:
    resumen = normalizar(tabla.get("summary", ""))
    enc = encabezado(tabla)
    enc_txt = " | ".join(enc)
    todo = normalizar(tabla.get_text(" "))
    if "LISTADO DE AUTORES" in resumen or "LISTADO DE AUTORES" in enc_txt:
        return "autores"
    if "GIROS DEL EXPEDIENTE" in resumen or ("COMISION" in enc_txt and "FECHA DE INGRESO" in enc_txt):
        return "giros"
    if "DIR. GRAL" in enc_txt or "INGRESO DEL DICTAMEN" in enc_txt:
        return "dgc"
    if "MESA DE ENTRADAS" in resumen or ("MESA DE ENTRADAS" in enc_txt and "DADO CUENTA" in enc_txt):
        return "mesa"
    if "ORIGEN" in enc and "EXTRACTO" in enc:
        return "cabecera"
    if "ESTADO" in enc_txt and "NUMERO" in enc_txt and "FECHA" in enc_txt:
        return "ordenes"
    if "EXP. HCD" in todo or "AUTOR HCD" in todo or "NRO. TP" in todo:
        return "diputados"
    if enc and enc[0] == "OBSERVACIONES":
        return "observaciones"
    if "ARCHIVOS" in enc_txt:
        return "archivos"
    return "otra"


def _cabecera(tabla, ficha: Ficha) -> None:
    enc = encabezado(tabla)
    filas = filas_datos(tabla)
    if not filas:
        return
    valores = [texto(c) for c in filas[0].find_all(["td", "th"])]

    def columna(prefijo: str) -> str:
        for i, nombre in enumerate(enc):
            if nombre.startswith(prefijo) and i < len(valores):
                return valores[i]
        return ""

    ficha.numero_texto = columna("N") or ficha.numero_texto
    ficha.origen_texto = columna("ORIGEN")
    ficha.tipo_texto = columna("TIPO")
    ficha.extracto = columna("EXTRACTO")


def _autores(tabla, ficha: Ficha) -> None:
    for td in tabla.find_all("td"):
        nombre = texto(td)
        if not nombre or normalizar(nombre) == "LISTADO DE AUTORES":
            continue
        nombre = re.sub(r"\s+,", ",", nombre)
        enlace = td.find("a", href=True)
        ficha.autores.append(Autor(nombre, urljoin(config.BASE, enlace["href"]) if enlace else None))


def _despues_de_dos_puntos(valor: str) -> str:
    return limpiar(valor.split(":", 1)[1]) if ":" in valor else limpiar(valor)


def _diputados(tabla, ficha: Ficha) -> None:
    etapa = ficha.etapa_diputados or EtapaDiputados()
    for celda in tabla.find_all(["td", "th"]):
        valor = texto(celda)
        n = normalizar(valor)
        if n.startswith("EXP. HCD") or n.startswith("EXP HCD"):
            etapa.texto_expedientes = _despues_de_dos_puntos(valor)
            etapa.expedientes, etapa.orden_del_dia = parsear_expedientes_hcd(etapa.texto_expedientes)
        elif n.startswith("NRO. TP") or n.startswith("NRO TP"):
            etapa.tramite_parlamentario = _despues_de_dos_puntos(valor) or None
        elif n.startswith("FECHA SANCION"):
            etapa.fecha_sancion = parsear_fecha(valor)
        elif n.startswith("AUTOR HCD"):
            etapa.autor = _despues_de_dos_puntos(valor).rstrip(".") or None
    ficha.etapa_diputados = etapa


def parsear_expedientes_hcd(valor: str) -> tuple[list[str], str | None]:
    """«422; 1324;1415; Y 1888-D-24 OD 71» → ([0422-D-2024, …, 1888-D-2024], '71')."""
    texto_mayus = (valor or "").upper()
    orden = None
    m = re.search(r"\bO\.?\s*D\.?\s*(?:N[°º]\s*)?(\d{1,5})\b", texto_mayus)
    if m:
        orden = m.group(1)
        texto_mayus = texto_mayus[:m.start()] + " " + texto_mayus[m.end():]
    pendientes: list[str] = []
    resultado: list[str] = []
    ultimo = None
    for t in re.finditer(r"(\d{1,5})(?:\s*-\s*([A-Z]{1,3})\s*-\s*(\d{2,4}))?", texto_mayus):
        numero, camara, anio = t.groups()
        if camara:
            ultimo = (camara, anio_cuatro_digitos(anio))
            for p in pendientes + [numero]:
                resultado.append(f"{int(p):04d}-{ultimo[0]}-{ultimo[1]}")
            pendientes = []
        else:
            pendientes.append(numero)
    if pendientes and ultimo:
        resultado.extend(f"{int(p):04d}-{ultimo[0]}-{ultimo[1]}" for p in pendientes)
    return list(dict.fromkeys(resultado)), orden


def _mesa(tabla, ficha: Ficha) -> None:
    filas = filas_datos(tabla)
    if not filas:
        return
    valores = [texto(td) for td in filas[0].find_all("td")]
    if valores:
        ficha.fecha_mesa_entradas = parsear_fecha(valores[0])
    if len(valores) > 1:
        ficha.fecha_dado_cuenta = parsear_fecha(valores[1])
    if len(valores) > 2 and valores[2]:
        partes = re.split(r"tipo\s*:", valores[2], flags=re.I)
        ficha.dae = limpiar(partes[0]) or None
        ficha.dae_tipo = limpiar(partes[1]) if len(partes) > 1 else None


def _dgc(tabla, ficha: Ficha) -> None:
    for tr in filas_datos(tabla):
        valores = [texto(td) for td in tr.find_all("td")]
        if valores and any(valores):
            ficha.ingresos_comisiones.append((parsear_fecha(valores[0]), valores[1] if len(valores) > 1 else ""))


def _giros(tabla, ficha: Ficha) -> None:
    for tr in filas_datos(tabla):
        tds = tr.find_all("td")
        if not tds:
            continue
        primera = texto(tds[0])
        if not primera:
            continue
        m = re.match(r"^(.*?)\s*ORDEN\s+DE\s+GIRO\s*:?\s*(\d+)\s*$", primera, re.I)
        nombre, orden = (limpiar(m.group(1)), int(m.group(2))) if m else (primera, None)
        ingreso = parsear_fecha(texto(tds[1])) if len(tds) > 1 else None
        egreso = parsear_fecha(texto(tds[2])) if len(tds) > 2 else None
        ficha.giros.append(Giro(nombre, orden, ingreso, egreso))


def _ordenes(tabla, ficha: Ficha) -> None:
    for tr in filas_datos(tabla):
        tds = tr.find_all("td")
        if not tds:
            continue
        numero = texto(tds[0])
        if not numero:
            continue
        enlace = tds[0].find("a", href=True)
        ficha.ordenes_del_dia.append(OrdenDelDia(
            numero=numero,
            fecha=parsear_fecha(texto(tds[1])) if len(tds) > 1 else None,
            estado=texto(tds[2]) if len(tds) > 2 else "",
            anexo=texto(tds[3]) if len(tds) > 3 else "",
            url=urljoin(config.BASE, enlace["href"]) if enlace else None,
        ))


def _observaciones(tabla, ficha: Ficha) -> None:
    for td in tabla.find_all("td"):
        valor = texto(td)
        if valor and valor not in ficha.observaciones:
            ficha.observaciones.append(valor)


def _bloque(tabla) -> BloqueResolucion | None:
    titulo = " ".join(t for t in (texto(th) for th in tabla.find_all("th")) if t)
    campos = []
    for td in tabla.find_all("td"):
        m = _RE_KV.match(texto(td))
        if m:
            campos.append((limpiar(m.group(1)), limpiar(m.group(2))))
    if not campos:
        return None
    return BloqueResolucion(titulo or "Resolución", campos)


def _hitos(s, ficha: Ficha) -> None:
    for h in s.find_all(re.compile(r"^h[1-6]$")):
        valor = texto(h)
        n = normalizar(valor)
        if not valor or any(n.startswith(sec) for sec in _SECCIONES_FICHA):
            continue
        if re.search(r"\d{1,2}-\d{1,2}-\d{2,4}", valor) or ":" in valor:
            ficha.hitos.append(valor)
            m = re.match(r"^PARA\s*:\s*(.+)$", n)
            if m:
                ficha.mocion_para = m.group(1)

    completo = normalizar(s.get_text(" "))
    m = re.search(r"ENVIADO AL ARCHIVO\s*:?\s*(\d{1,2}-\d{1,2}-\d{2,4})", completo)
    if m:
        ficha.fecha_archivo = parsear_fecha(m.group(1))
    m = re.search(r"CADUC\w*\s+EL\s+(\d{1,2}-\d{1,2}-\d{2,4})", completo)
    if m:
        ficha.fecha_caducidad_registrada = parsear_fecha(m.group(1))
    m = re.search(r"MOCION DE PREFERENCIA\s*:?\s*(\d{1,2}-\d{1,2}-\d{2,4})", completo)
    if m:
        ficha.mocion_preferencia = parsear_fecha(m.group(1))


def _textos(s, ficha: Ficha) -> None:
    for a in s.find_all("a", href=True):
        href = a["href"]
        if "downloadPdf" in href and ficha.texto_original is None:
            ficha.texto_original = Documento("Texto original (PDF)", urljoin(config.BASE, href))
        elif "descargarPdfParla" in href:
            etiqueta = texto(a) or "Texto definitivo"
            if not any(d.url.endswith(href) for d in ficha.textos_definitivos):
                ficha.textos_definitivos.append(Documento(etiqueta, urljoin(config.BASE, href)))
    if "EN PROCESO DE CARGA" in normalizar(s.get_text(" ")):
        ficha.texto_definitivo_pendiente = True


def _anotaciones(s, ficha: Ficha) -> None:
    """Líneas sueltas con fecha (p. ej. «31-07-25 INC. DE FIRMA SDOR. …»)."""
    existentes = " ".join(normalizar(o) for o in ficha.observaciones)
    for linea in s.get_text("\n").split("\n"):
        valor = limpiar(linea)
        if (
            _RE_ANOTACION.match(valor)
            and len(valor) < 600
            and normalizar(valor) not in existentes
            and valor not in ficha.hitos
            and valor not in ficha.anotaciones
        ):
            ficha.anotaciones.append(valor)
