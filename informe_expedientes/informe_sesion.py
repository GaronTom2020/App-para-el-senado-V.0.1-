"""Escritura del informe de sesión: índice de asuntos y la ficha de cada tema (Word, HTML, Excel) y CSV."""

from __future__ import annotations

import csv
from html import escape
from pathlib import Path

from . import __version__
from .contenido import nombre_tipo
from .informe_docx import SERIF, _Escritor, _bordes_tabla, _borde_celda, _hipervinculo, _margenes_celdas, _sombrear
from .informe_html import contenido_html, pagina
from .sesion import ResultadoSesion, comisiones, etiqueta_referencias, resumen
from .util import fmt_fecha

# Columnas del CSV para el tablero de sesiones de Power BI (acordadas el 31/10/2026).
COLUMNAS_CSV = ["Fecha de sesión", "Orden", "Expediente", "OD", "Título", "Tipo", "Comisiones"]

ESTILOS_SESION = """
.indice td.orden{width:2.5em;color:var(--tinta-suave);font-variant-numeric:tabular-nums}
.indice .sin-numero td{color:var(--tinta-suave)}
.tema{margin-top:56px;padding-top:12px;border-top:3px solid var(--cupula)}
.tema > h2{border:0;margin-top:0}
.tema .numero{font-size:38px}
.tema .seccion{font-size:13px;color:var(--tinta-suave);margin:0}
.ficha + .ficha{margin-top:36px;padding-top:24px;border-top:1px dashed var(--linea)}
"""


def _e(t) -> str:
    return escape(str(t or ""), quote=True)


def _a(texto: str, url: str | None) -> str:
    return f'<a href="{_e(url)}" target="_blank" rel="noopener">{_e(texto)}</a>' if url else _e(texto)


def _situaciones(tema) -> str:
    return "; ".join(f"{r.ficha.id.corto}: {r.situacion.titulo}" for r in tema.resultados) or \
        ("; ".join(tema.errores) if tema.errores else "—")


# ===================================================================== HTML

def generar_html(res: ResultadoSesion) -> str:
    plan = res.plan
    partes = ['<div class="membrete"><span>H. Senado de la Nación</span>'
              f"<span>Informe del {res.generado:%d/%m/%Y, %H:%M} h</span></div>",
              '<p class="descripcion" style="margin-top:22px">Informe de sesión</p>',
              f'<h1 class="numero">{_e(fmt_fecha(res.fecha, "Sesión"))}</h1>']
    datos = []
    if plan.hora:
        datos.append(f"Hora de la sesión: {plan.hora} h")
    if plan.fecha_reunion:
        datos.append(f"Plan de labor acordado el {fmt_fecha(plan.fecha_reunion)}")
    if plan.fuente:
        datos.append(_a("Plan de labor (fuente)", plan.fuente) if plan.fuente.startswith("http") else
                     f"Plan de labor: {_e(Path(plan.fuente).name)}")
    if datos:
        partes.append('<p class="enlaces">' + "".join(f"<span>{d}</span>" for d in datos) + "</p>")
    partes.append(f'<section class="situacion"><p class="rotulo">Resumen</p><h2>{_e(resumen(res))}</h2></section>')

    filas = []
    for t in res.temas:
        a = t.asunto
        clase = "" if a.referencias else ' class="sin-numero"'
        enlace = f'<a href="#tema-{a.orden}">{_e(t.titulo)}</a>' if t.resultados else _e(t.titulo)
        exps = ", ".join(_a(r.ficha.id.corto, r.ficha.url) for r in t.resultados) or "—"
        seccion = "" if a.seccion == "Temas acordados" else f"<p class='secundario'>{_e(a.seccion)}</p>"
        filas.append(f"<tr{clase}><td class='orden'>{a.orden}</td><td>{enlace}{seccion}"
                     f"</td><td>{_e(etiqueta_referencias(t) or '—')}</td>"
                     f"<td>{exps}</td><td>{_e(_situaciones(t))}</td></tr>")
    partes.append("<h2>Asuntos en el orden de tratamiento</h2><div class='tabla'><table class='indice'><thead><tr>"
                  "<th>N°</th><th>Asunto</th><th>OD / expediente</th><th>Expedientes</th><th>Situación</th></tr>"
                  f"</thead><tbody>{''.join(filas)}</tbody></table></div>")

    for t in res.temas:
        if not t.resultados:
            continue
        partes.append(f'<section class="tema" id="tema-{t.asunto.orden}"><p class="seccion">'
                      f"Asunto {t.asunto.orden} · {_e(t.asunto.seccion)}"
                      + (f" · {_e(etiqueta_referencias(t))}" if etiqueta_referencias(t) else "") + "</p>"
                      f"<h2>{_e(t.titulo)}</h2>")
        for r in t.resultados:
            partes.append(f'<div class="ficha">{contenido_html(r, incrustado=True)}</div>')
        if t.errores:
            partes.append("<p class='secundario'>" + " ".join(_e(x) for x in t.errores) + "</p>")
        partes.append("</section>")

    partes.append("<footer><p>Informe generado automáticamente con el plan de labor y los datos públicos del sitio "
                  "del H. Senado de la Nación y de la H. Cámara de Diputados. Antes de usarlo en un trámite oficial, "
                  f"verificá los datos en la fuente. Programa Informe de Expedientes, versión {_e(__version__)}.</p>")
    if res.advertencias:
        partes.append("<p>Durante la consulta hubo avisos:</p><ul>"
                      + "".join(f"<li>{_e(x)}</li>" for x in res.advertencias) + "</ul>")
    partes.append("</footer>")
    html = pagina(f"Informe de sesión {fmt_fecha(res.fecha, '')} — H. Senado de la Nación", "".join(partes))
    return html.replace("</style>", ESTILOS_SESION + "</style>", 1)


def escribir_html(res: ResultadoSesion, destino: Path) -> Path:
    Path(destino).write_text(generar_html(res), encoding="utf-8")
    return Path(destino)


# ===================================================================== Word

class _EscritorSesion(_Escritor):
    def __init__(self, res: ResultadoSesion):
        super().__init__(res, encabezado=f"H. Senado de la Nación — Informe de sesión del {fmt_fecha(res.fecha)}")
        self.sesion = res

    def escribir(self, destino: Path, ejemplo: bool = False) -> Path:
        from docx.enum.text import WD_BREAK, WD_TAB_ALIGNMENT
        from docx.shared import Cm

        res, plan = self.sesion, self.sesion.plan
        p = self.parrafo("H. Senado de la Nación", 9, "suave", despues=0)
        p.paragraph_format.tab_stops.add_tab_stop(Cm(self.ancho), WD_TAB_ALIGNMENT.RIGHT)
        self._run(p, f"\tInforme del {res.generado:%d/%m/%Y, %H:%M} h", 9, "suave")
        self.parrafo("Informe de sesión", 11, "suave", antes=12, despues=0)
        self.parrafo(fmt_fecha(res.fecha, "Sesión"), 30, "tinta", SERIF, despues=4)
        datos = [x for x in (f"Hora de la sesión: {plan.hora} h" if plan.hora else "",
                             f"Plan de labor acordado el {fmt_fecha(plan.fecha_reunion)}" if plan.fecha_reunion else "")
                 if x]
        if datos or plan.fuente:
            p = self.parrafo(" · ".join(datos), 9.5, "suave", despues=8)
            if plan.fuente.startswith("http"):
                self._run(p, "    ")
                _hipervinculo(p, "Plan de labor (fuente)", plan.fuente, 9.5)
            elif plan.fuente:
                self._run(p, f"    Plan de labor: {Path(plan.fuente).name}", 9.5, "suave")

        caja = self.doc.add_table(rows=1, cols=1)
        caja.autofit = False
        _bordes_tabla(caja, color="cupula_tenue")
        _margenes_celdas(caja, 160, 140, 260, 200)
        celda = caja.rows[0].cells[0]
        celda.width = Cm(self.ancho)
        _sombrear(celda, "cupula_tenue")
        _borde_celda(celda, "left", "cupula", 36)
        self._run(celda.paragraphs[0], resumen(res), 12, "tinta", SERIF)

        self.titulo("Asuntos en el orden de tratamiento")
        anchos = [1.0, 5.6, 2.8, 2.4, 4.8]
        t = self.tabla(["N°", "Asunto", "OD / expediente", "Expedientes", "Situación"], anchos)
        for tema in res.temas:
            fila = self.fila(t, anchos)
            color = None if tema.asunto.referencias else "suave"
            self._run(fila.cells[0].paragraphs[0], str(tema.asunto.orden), 9, "suave")
            self._run(fila.cells[1].paragraphs[0], tema.titulo, 9, color)
            if tema.asunto.seccion != "Temas acordados":
                self._run(fila.cells[1].add_paragraph(), tema.asunto.seccion, 7.5, "suave")
            self._run(fila.cells[2].paragraphs[0], etiqueta_referencias(tema) or "—", 8.5, color)
            if tema.resultados:
                for j, r in enumerate(tema.resultados):
                    pe = fila.cells[3].paragraphs[0] if j == 0 else fila.cells[3].add_paragraph()
                    _hipervinculo(pe, r.ficha.id.corto, r.ficha.url, 8.5)
            else:
                self._run(fila.cells[3].paragraphs[0], "—", 8.5, "suave")
            self._run(fila.cells[4].paragraphs[0], _situaciones(tema), 8.5, color)

        for tema in res.temas:
            if not tema.resultados:
                continue
            salto = self.doc.add_paragraph()
            salto.add_run().add_break(WD_BREAK.PAGE)
            self.parrafo(f"Asunto {tema.asunto.orden} · {tema.asunto.seccion}"
                         + (f" · {etiqueta_referencias(tema)}" if etiqueta_referencias(tema) else ""), 9, "suave",
                         despues=0)
            self.doc.add_heading(tema.titulo, level=1)
            for k, r in enumerate(tema.resultados):
                self.r = r
                self.cuerpo(numero_grande=False)
                if r.advertencias:
                    self.parrafo("Avisos de la consulta: " + " ".join(r.advertencias), 8, "suave", antes=4)
            for error in tema.errores:
                self.parrafo(error, 8.5, "suave", antes=4)

        self.parrafo("Informe generado automáticamente con el plan de labor y los datos públicos del sitio del "
                     "H. Senado de la Nación y de la H. Cámara de Diputados. Antes de usarlo en un trámite oficial, "
                     f"verificá los datos en la fuente. Programa Informe de Expedientes, versión {__version__}.",
                     8.5, "suave", antes=22)
        if res.advertencias:
            self.parrafo("Durante la consulta hubo avisos:", 8.5, "suave", antes=4)
            for x in res.advertencias:
                self._run(self.doc.add_paragraph(style="List Bullet"), x, 8.5, "suave")
        self.doc.core_properties.title = f"Informe de sesión del {fmt_fecha(res.fecha)}"
        self.doc.core_properties.author = "Informe de Expedientes"
        self.doc.save(str(destino))
        return Path(destino)


def escribir_docx(res: ResultadoSesion, destino: Path) -> Path:
    return _EscritorSesion(res).escribir(Path(destino))


# ===================================================================== Excel

def escribir_xlsx(res: ResultadoSesion, destino: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    normal = Font(name="Arial", size=10)
    titulo = Font(name="Arial", size=14, bold=True, color="1F4E45")
    blanco = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    enlace = Font(name="Arial", size=10, color="1F4E45", underline="single")
    relleno = PatternFill("solid", fgColor="2E6B5F")
    arriba = Alignment(vertical="top", wrap_text=True)

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Asuntos"
    hoja["A1"] = f"Informe de sesión del {fmt_fecha(res.fecha)}"
    hoja["A1"].font = titulo
    hoja["A2"] = resumen(res)
    hoja["A2"].font = normal
    columnas = ["Orden", "Asunto", "Sección", "OD", "Expediente", "Tipo", "Extracto", "Situación", "Comisiones",
                "Caducidad", "Ficha"]
    anchos = [8, 38, 18, 14, 13, 20, 60, 40, 34, 12, 12]
    for i, (nombre, ancho) in enumerate(zip(columnas, anchos), 1):
        c = hoja.cell(row=4, column=i, value=nombre)
        c.font, c.fill = blanco, relleno
        hoja.column_dimensions[get_column_letter(i)].width = ancho
    fila = 5
    for tema in res.temas:
        filas = tema.resultados or [None]
        for r in filas:
            valores = [tema.asunto.orden, tema.titulo, tema.asunto.seccion, ", ".join(tema.asunto.ordenes_del_dia)]
            if r is None:
                valores += [", ".join(x.corto for x in tema.expedientes), "", "", "; ".join(tema.errores), "", "", ""]
            else:
                f, s = r.ficha, r.situacion
                valores += [f.id.corto, nombre_tipo(f), f.extracto, s.titulo, ", ".join(comisiones(r)),
                            s.caducidad.fecha if s.caducidad else None, "Ver ficha"]
            for i, v in enumerate(valores, 1):
                c = hoja.cell(row=fila, column=i, value=v)
                c.font, c.alignment = normal, arriba
                if columnas[i - 1] == "Caducidad" and v:
                    c.number_format = "DD/MM/YYYY"
            if r is not None:
                c = hoja.cell(row=fila, column=len(columnas))
                c.hyperlink, c.font = r.ficha.url, enlace
            fila += 1
    hoja.freeze_panes = "A5"
    hoja.auto_filter.ref = f"A4:{get_column_letter(len(columnas))}{max(fila - 1, 4)}"
    libro.save(str(destino))
    return Path(destino)


# ======================================================================= CSV

def filas_csv(res: ResultadoSesion) -> list[list[str]]:
    """Una fila por asunto, para el tablero de sesiones de Power BI."""
    fecha = fmt_fecha(res.fecha, "")
    filas = []
    for tema in res.temas:
        resultados = tema.resultados
        expedientes = [r.ficha.id.corto for r in resultados] or [x.corto for x in tema.expedientes]
        tipos = list(dict.fromkeys(nombre_tipo(r.ficha) for r in resultados))
        comis = list(dict.fromkeys(c for r in resultados for c in comisiones(r)))
        filas.append([fecha, str(tema.asunto.orden), ", ".join(expedientes), ", ".join(tema.asunto.ordenes_del_dia),
                      tema.titulo, ", ".join(tipos), " / ".join(comis)])
    return filas


def escribir_csv(res: ResultadoSesion, destino: Path) -> Path:
    """Punto y coma, UTF-8 con BOM (Excel y Power BI lo abren con tildes) y fechas dd/mm/aaaa."""
    with open(destino, "w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.writer(archivo, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        escritor.writerow(COLUMNAS_CSV)
        escritor.writerows(filas_csv(res))
    return Path(destino)
