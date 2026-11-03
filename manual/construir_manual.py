"""Compila el manual de usuario en PDF (y una copia en HTML).

Toma ``manual/contenido.md``, le suma las secciones vigentes del ``README.md`` y las capturas de
``manual/capturas`` y lo imprime con Chromium (Playwright). Después, con PyMuPDF, agrega el encabezado
con el capítulo, el pie con el número de página y el enlace «Volver al índice», y los marcadores.

    python manual/construir_manual.py                 # deja manual/salida/Manual de usuario.pdf
    python manual/construir_manual.py --salida otra/carpeta

Necesita: markdown, playwright (con «python -m playwright install chromium») y pymupdf.
"""

from __future__ import annotations

import argparse
import base64
import html
import re
from datetime import date
from pathlib import Path

import markdown
import pymupdf
from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
CAPTURAS = AQUI / "capturas"
LOGO = RAIZ / "informe_expedientes" / "recursos" / "logo_senado.png"
TITULO = "Sistema de Información Parlamentaria"
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")
ROMANOS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV")

# Encabezado y pie (en puntos; A4 = 595 × 842).
CELESTE = (0x27 / 255, 0xAA / 255, 0xE1 / 255)
CUPULA = (0x1A / 255, 0x64 / 255, 0xAB / 255)
GRIS = (0.83, 0.85, 0.88)
FUENTES = {"sans": ["C:/Windows/Fonts/calibri.ttf", "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf"],
           "italica": ["C:/Windows/Fonts/cambriai.ttf", "/usr/share/fonts/truetype/crosextra/Caladea-Italic.ttf"]}


# ============================================================== README
def leer_readme() -> str:
    return (RAIZ / "README.md").read_text(encoding="utf-8")


def version(readme: str) -> str:
    m = re.search(r"Versión actual:\s*\*\*([^*]+)\*\*", readme)
    if m:
        return m.group(1).strip()
    m = re.search(r'__version__\s*=\s*"([^"]+)"', (RAIZ / "informe_expedientes" / "__init__.py").read_text("utf-8"))
    return m.group(1) if m else "s/d"


def _secciones(readme: str) -> list[tuple[int, str, int, int]]:
    """(nivel, título, inicio del cuerpo, fin) de cada encabezado del README, fuera de los bloques de código."""
    marcas, en_codigo, pos = [], False, 0
    for renglon in readme.splitlines(keepends=True):
        if renglon.startswith("```"):
            en_codigo = not en_codigo
        m = None if en_codigo else re.match(r"(#{1,6})\s+(.+?)\s*$", renglon)
        if m:
            marcas.append((len(m.group(1)), m.group(2), pos, pos + len(renglon)))
        pos += len(renglon)
    salida = []
    for i, (nivel, titulo, ini, cuerpo) in enumerate(marcas):
        fin = next((m[2] for m in marcas[i + 1:] if m[0] <= nivel), len(readme))
        salida.append((nivel, titulo, cuerpo, fin))
    return salida


def _sin_adornos(texto: str) -> str:
    """Saca los separadores decorativos del README (docs/img/separador.svg): en el manual sobran."""
    return re.sub(r"^<p[^>]*><img[^>]*separador\.svg[^>]*></p>\s*$", "", texto, flags=re.M).strip()


def _bajar_encabezados(texto: str, nivel_origen: int, nivel_destino: int = 3) -> str:
    texto = _sin_adornos(texto)
    dif = nivel_destino - nivel_origen - 1

    def cambiar(m):
        return "#" * min(6, len(m.group(1)) + dif) + " "
    partes = re.split(r"(```.*?```)", texto, flags=re.S)
    return "".join(p if p.startswith("```") else re.sub(r"^(#{1,6})\s", cambiar, p, flags=re.M) for p in partes)


def seccion_readme(readme: str, titulo: str) -> str:
    for nivel, t, ini, fin in _secciones(readme):
        if t.strip().lower() == titulo.strip().lower():
            return _bajar_encabezados(readme[ini:fin].strip(), nivel)
    raise SystemExit(f"El README no tiene la sección «{titulo}» que pide manual/contenido.md.")


def novedades_readme(readme: str) -> str:
    partes = []
    for nivel, t, ini, fin in _secciones(readme):
        m = re.match(r"Novedades de la versión\s+(.+)", t)
        if m:
            partes.append(f"### Versión {m.group(1)}\n\n" + _bajar_encabezados(readme[ini:fin].strip(), nivel, 4))
    return "\n\n".join(partes) or "_El README no registra novedades._"


# ============================================================== Markdown → HTML
def preparar(texto: str, readme: str, ver: str) -> str:
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S)
    texto = texto.replace("{{version}}", ver)
    texto = texto.replace("{{readme-novedades}}", '<div class="desde-readme" markdown="1">\n\n'
                          + novedades_readme(readme) + "\n\n</div>")
    texto = re.sub(r"\{\{readme:\s*(.+?)\}\}", lambda m: '<div class="desde-readme" markdown="1">\n\n'
                   + seccion_readme(readme, m.group(1)) + "\n\n</div>", texto)
    # «>> nota» → nota al margen
    return re.sub(r"^>>\s?(.+)$", lambda m: '<aside class="margen">'
                  + markdown.markdown(m.group(1))[3:-4] + "</aside>\n", texto, flags=re.M)


def _imagen(ruta: str) -> str:
    """Las capturas viajan dentro del HTML, así el PDF no depende de rutas."""
    archivo = (AQUI / ruta).resolve()
    if not archivo.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(archivo.read_bytes()).decode()


def capitulos(cuerpo_md: str) -> list[dict]:
    caps, n_cap, n_anexo, n_fig = [], 0, 0, 0
    for bloque in re.split(r"^# (?=\S)", cuerpo_md, flags=re.M)[1:]:
        titulo, _, resto = bloque.partition("\n")
        titulo = titulo.strip()
        anexo = re.match(r"Anexo\s+(\w+)\.?\s*(.*)", titulo)
        if anexo:
            n_anexo += 1
            etiqueta, titulo = f"Anexo {anexo.group(1)}", anexo.group(2)
        else:
            etiqueta = f"Capítulo {ROMANOS[n_cap]}"
            n_cap += 1
        cid = f"cap{len(caps) + 1}"
        cuerpo = markdown.markdown(resto, extensions=["tables", "admonition", "attr_list", "md_in_html",
                                                       "sane_lists", "fenced_code"])
        secciones = []

        def h2(m):
            sid = f"{cid}-s{len(secciones) + 1}"
            secciones.append((sid, re.sub(r"<[^>]+>", "", m.group(1))))
            return f'<h2 id="{sid}">{m.group(1)}</h2>'
        cuerpo = re.sub(r"<h2>(.*?)</h2>", h2, cuerpo)

        def figura(m):
            nonlocal n_fig
            n_fig += 1
            alt, src = html.unescape(m.group(1)), m.group(2)
            ancha = ' class="ancha"' if re.search(r"0[1-3]_|08_", src) else ""
            return (f'<figure{ancha}><img src="{_imagen(src)}" alt="{html.escape(alt)}">'
                    f"<figcaption><b>Figura {n_fig}.</b> {html.escape(alt)}</figcaption></figure>")
        cuerpo = re.sub(r'<p><img alt="([^"]*)" src="([^"]+)"\s*/?></p>', figura, cuerpo)
        caps.append({"id": cid, "etiqueta": etiqueta, "titulo": titulo, "html": cuerpo, "secciones": secciones})
    return caps


def armar_html(caps: list[dict], ver: str, paginas: dict[str, int] | None = None) -> str:
    paginas = paginas or {}
    hoy = date.today()
    fecha = f"{MESES[hoy.month - 1]} de {hoy.year}"

    def pag(i):
        return f'<a class="pag" href="#{i}">{paginas.get(i, "00")}</a>'
    indice = []
    for c in caps:
        subs = "".join(f'<li><a class="tit" href="#{sid}">{html.escape(t)}</a>{pag(sid)}</li>'
                       for sid, t in c["secciones"])
        indice.append(f'<div class="cap"><div class="num">{c["etiqueta"]}</div><div class="linea">'
                      f'<a class="tit" href="#{c["id"]}">{html.escape(c["titulo"])}</a>{pag(c["id"])}</div>'
                      f"<ul>{subs}</ul></div>")
    cuerpo = "".join(
        f'<section class="capitulo" id="{c["id"]}"><div class="apertura"><div class="banda">{c["etiqueta"]}</div>'
        f'<h1>{html.escape(c["titulo"])}</h1></div>{c["html"]}</section>' for c in caps)
    foto = _imagen("capturas/02_resultado.png") or _imagen("capturas/01_inicio.png")
    logo = "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode()
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Manual de usuario — {TITULO}</title><style>{(AQUI / "estilo.css").read_text(encoding="utf-8")}</style></head><body>
<div class="portada">
  {'<img class="foto" src="' + foto + '" alt="">' if foto else ''}
  <div class="hemiciclo">Honorable Senado de la Nación<br><b>Prosecretaría Parlamentaria</b></div>
  <div class="columna">
    <div class="bloque b1"><img src="{logo}" alt="Senado Argentina"></div>
    <div class="bloque b2"><div class="t">MANUAL<br>DE USUARIO</div><div class="v">Versión {html.escape(ver)}</div></div>
    <div class="bloque b3"><div class="raya"></div><div class="n">Sistema de<b>Información Parlamentaria</b></div>
      <div class="f">{fecha.capitalize()}</div></div>
  </div>
  <div class="titulo-reg"><div>Guía paso a paso para el uso<br>del programa y sus funciones</div>
    <span>Expedientes · Por tema · Seguimiento · Sesión · Asuntos entrados</span></div>
</div>
<section class="indice" id="indice"><div class="banda">Índice general</div>{"".join(indice)}</section>
{cuerpo}
</body></html>"""


# ============================================================== PDF
def imprimir(navegador, html_texto: str, destino: Path) -> None:
    pagina = navegador.new_page()
    pagina.set_content(html_texto, wait_until="load")
    pagina.pdf(path=str(destino), format="A4", print_background=True, prefer_css_page_size=True)
    pagina.close()


def paginas_del_indice(pdf: Path, caps: list[dict]) -> dict[str, int]:
    """Página de cada capítulo y sección, según los destinos de los enlaces del índice general."""
    ids = {i for c in caps for i in [c["id"], *[s for s, _ in c["secciones"]]]}
    doc = pymupdf.open(pdf)
    paginas = {}
    for n in range(1, doc.page_count):
        for e in doc[n].get_links():
            if e.get("nameddest") in ids and "page" in e:
                paginas.setdefault(e["nameddest"], e["page"] + 1)
    doc.close()
    if len(paginas) != len(ids):
        print(f"Aviso: el índice ubica {len(paginas)} de {len(ids)} entradas.")
    return paginas


def _fuente(pagina, nombre: str) -> str:
    for archivo in FUENTES[nombre]:
        if Path(archivo).exists():
            pagina.insert_font(fontname=nombre, fontfile=archivo)
            return nombre
    return "helv"


def _centrado(pagina, caja: pymupdf.Rect, texto: str, fuente: str, tam: float, color) -> None:
    """Texto centrado en la caja (insert_textbox no escribe nada si la caja le queda justa)."""
    archivo = next((f for f in FUENTES.get(fuente, []) if Path(f).exists()), None)
    ancho = pymupdf.Font(fontfile=archivo).text_length(texto, tam) if archivo else pymupdf.get_text_length(texto, "helv", tam)
    pagina.insert_text(((caja.x0 + caja.x1 - ancho) / 2, caja.y1 - (caja.height - tam * 0.68) / 2), texto,
                       fontname=fuente, fontsize=tam, color=color)


def decorar(pdf: Path, caps: list[dict], paginas: dict[str, int], ver: str) -> None:
    doc = pymupdf.open(pdf)
    inicio = sorted((paginas.get(c["id"], 0), c) for c in caps if c["id"] in paginas)
    indice = 1                                                   # la página que sigue a la portada
    for n in range(1, doc.page_count):
        p = doc[n]
        ancho, alto = p.rect.width, p.rect.height
        sans, italica = _fuente(p, "sans"), _fuente(p, "italica")
        cap = next((c for pg, c in reversed(inicio) if pg <= n + 1), None)
        # Encabezado: etiqueta celeste con el capítulo y el título del manual en cursiva (como el Reglamento).
        if cap and n + 1 != paginas.get(cap["id"]):
            p.draw_rect(pymupdf.Rect(51, 30, 180, 46), color=None, fill=CELESTE)
            p.insert_textbox(pymupdf.Rect(51, 33, 174, 46), cap["etiqueta"].upper(), fontname=sans, fontsize=8.5,
                             color=(1, 1, 1), align=pymupdf.TEXT_ALIGN_RIGHT)
            p.insert_textbox(pymupdf.Rect(188, 33, ancho - 51, 46), f"Manual de usuario · {TITULO}",
                             fontname=italica, fontsize=9, color=CUPULA, align=pymupdf.TEXT_ALIGN_RIGHT)
        # Pie: barra gris con el número en un recuadro y el enlace al índice.
        y = alto - 50
        p.draw_rect(pymupdf.Rect(51, y, ancho - 51, y + 16), color=None, fill=GRIS)
        par = (n + 1) % 2 == 0
        caja = pymupdf.Rect(51, y, 79, y + 16) if par else pymupdf.Rect(ancho - 79, y, ancho - 51, y + 16)
        p.draw_rect(caja, color=None, fill=(1, 1, 1))
        p.draw_rect(caja, color=GRIS, width=1.2)
        _centrado(p, caja, str(n + 1), sans, 9.5, (0.2, 0.2, 0.2))
        if n != indice:
            zona = pymupdf.Rect(ancho / 2 - 60, y, ancho / 2 + 60, y + 16)
            _centrado(p, zona, "« Volver al índice", sans, 8.5, CUPULA)
            p.insert_link({"kind": pymupdf.LINK_GOTO, "from": zona, "page": indice, "to": pymupdf.Point(0, 0)})
        margen = pymupdf.Rect(80, y + 3.5, ancho / 2 - 64, y + 16) if par else pymupdf.Rect(
            ancho / 2 + 64, y + 3.5, ancho - 82, y + 16)
        p.insert_textbox(margen, f"Versión {ver}", fontname=sans, fontsize=7.5, color=(0.4, 0.42, 0.47),
                         align=pymupdf.TEXT_ALIGN_LEFT if par else pymupdf.TEXT_ALIGN_RIGHT)
    marcadores = [[1, "Portada", 1], [1, "Índice general", 2]]
    for c in caps:
        if c["id"] in paginas:
            marcadores.append([1, f'{c["etiqueta"]}. {c["titulo"]}', paginas[c["id"]]])
            marcadores += [[2, t, paginas[s]] for s, t in c["secciones"] if s in paginas]
    doc.set_toc(marcadores)
    doc.set_metadata({"title": f"Manual de usuario — {TITULO}", "subject": f"Versión {ver}",
                      "author": "H. Senado de la Nación — Prosecretaría Parlamentaria", "creator": "construir_manual.py"})
    doc.save(pdf.with_suffix(".tmp.pdf"), garbage=3, deflate=True)
    doc.close()
    pdf.with_suffix(".tmp.pdf").replace(pdf)


def captura_informe_html(navegador) -> None:
    """Imagen del informe HTML de ejemplo que deja capturar.py."""
    origen = CAPTURAS / "informe_ejemplo.html"
    if not origen.exists():
        return
    pagina = navegador.new_page(viewport={"width": 1150, "height": 820}, device_scale_factor=1.25)
    pagina.goto(origen.resolve().as_uri())
    pagina.screenshot(path=str(CAPTURAS / "08_informe_html.png"))
    pagina.close()


def principal() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("--salida", type=Path, default=AQUI / "salida")
    args.add_argument("--nombre", default="Manual de usuario")
    a = args.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)
    readme = leer_readme()
    ver = version(readme)
    with sync_playwright() as pw:
        navegador = pw.chromium.launch()
        captura_informe_html(navegador)
        caps = capitulos(preparar((AQUI / "contenido.md").read_text(encoding="utf-8"), readme, ver))
        pdf = a.salida / f"{a.nombre}.pdf"
        imprimir(navegador, armar_html(caps, ver), pdf)              # 1.ª pasada: averiguar las páginas
        paginas = paginas_del_indice(pdf, caps)
        final = armar_html(caps, ver, paginas)
        imprimir(navegador, final, pdf)                              # 2.ª pasada: índice con números
        navegador.close()
    if paginas_del_indice(pdf, caps) != paginas:
        print("Aviso: al numerar el índice cambió la paginación; revisá los números.")
    decorar(pdf, caps, paginas, ver)
    (a.salida / f"{a.nombre}.html").write_text(final, encoding="utf-8")
    print(f"Manual {ver}: {pdf} ({pymupdf.open(pdf).page_count} páginas)")


if __name__ == "__main__":
    principal()
