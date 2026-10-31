"""Informe en HTML (un solo archivo, se abre con cualquier navegador)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from . import __version__
from .contenido import (
    Linea, alcance_busqueda, bloques_resolucion, comisiones_texto, datos_diputados, datos_generales,
    datos_diputados_hcdn, descripcion, sesiones_votadas, texto_votaciones,
)
from .modelos import Resultado
from .util import fmt_fecha, nombre_comision

ESTILOS = """
:root{
  --tinta:#1F2B28; --tinta-suave:#55645F; --cupula:#2E6B5F; --cupula-oscura:#1F4E45;
  --cupula-tenue:#E4EFEB; --piedra:#EEF2F0; --linea:#CBD5D1; --papel:#FFFFFF;
  --lacre:#8C2F2F; --lacre-tenue:#F6E7E5; --ambar:#8A5A10; --ambar-tenue:#F7EEDC;
  --serif: Georgia, "Times New Roman", serif;
  --sans: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark){
  :root{
    --tinta:#E2EBE8; --tinta-suave:#A7B8B3; --cupula:#86C5B3; --cupula-oscura:#A9DACB;
    --cupula-tenue:#1C322D; --piedra:#101716; --linea:#2D3E39; --papel:#141D1B;
    --lacre:#E8A39B; --lacre-tenue:#3B201D; --ambar:#E6BC70; --ambar-tenue:#372B16;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--piedra);color:var(--tinta);font:15px/1.55 var(--sans)}
.hoja{max-width:880px;margin:32px auto;background:var(--papel);padding:44px 56px 40px;border-top:6px solid var(--cupula)}
.membrete{display:flex;justify-content:space-between;gap:16px;font-size:13px;color:var(--tinta-suave)}
.numero{font-family:var(--serif);font-weight:normal;font-size:54px;line-height:1.05;margin:22px 0 6px;letter-spacing:.005em}
.descripcion{font-size:16px;color:var(--tinta-suave);margin:0 0 14px}
.extracto{font-family:var(--serif);font-size:17px;line-height:1.6;margin:0 0 16px;max-width:72ch}
.enlaces{display:flex;flex-wrap:wrap;gap:6px 22px;font-size:14px;margin:0}
a{color:var(--cupula-oscura);text-decoration-thickness:1px;text-underline-offset:2px}
a:hover{color:var(--cupula)}
a:focus-visible{outline:2px solid var(--cupula);outline-offset:2px}
.situacion{margin:30px 0 8px;padding:22px 26px 20px;background:var(--cupula-tenue);border-left:5px solid var(--cupula)}
.situacion.ambar{background:var(--ambar-tenue);border-color:var(--ambar)}
.situacion.lacre{background:var(--lacre-tenue);border-color:var(--lacre)}
.situacion .rotulo{font-size:13px;color:var(--tinta-suave);margin:0}
.situacion h2{font-family:var(--serif);font-weight:normal;font-size:25px;line-height:1.25;margin:4px 0 8px;border:0;padding:0}
.situacion ul{margin:0 0 4px;padding-left:20px}
.situacion li{margin:2px 0}
.pasos{list-style:none;margin:20px 0 6px;padding:0;display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));counter-reset:paso}
.paso{position:relative;padding:32px 10px 0 0;font-size:13px;line-height:1.35;color:var(--tinta-suave)}
.paso::before{counter-increment:paso;content:counter(paso);position:absolute;top:0;left:0;width:24px;height:24px;border-radius:50%;
  border:2px solid var(--linea);background:var(--papel);color:var(--tinta-suave);font-size:12px;line-height:20px;text-align:center;font-weight:600}
.paso::after{content:"";position:absolute;top:11px;left:30px;right:6px;height:2px;background:var(--linea)}
.paso:last-child::after{display:none}
.paso strong{display:block;color:var(--tinta);font-weight:600}
.paso.hecho::before{content:"✓";background:var(--cupula);border-color:var(--cupula);color:var(--papel)}
.paso.hecho::after{background:var(--cupula)}
.paso.actual::before{border-color:var(--cupula);color:var(--cupula-oscura);box-shadow:0 0 0 4px color-mix(in srgb,var(--cupula) 22%,transparent)}
.paso.actual strong{color:var(--cupula-oscura)}
.paso.detenido::before{content:"×";border-color:var(--lacre);color:var(--lacre);font-size:15px}
.paso.detenido strong{color:var(--lacre)}
.caducidad{margin:14px 0 0;font-size:13.5px}
.caducidad.vencida{color:var(--lacre)}
h2{font-family:var(--serif);font-weight:normal;font-size:21px;margin:40px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--linea)}
dl.datos{display:grid;grid-template-columns:minmax(150px,230px) 1fr;gap:8px 24px;margin:0}
dl.datos dt{color:var(--tinta-suave)}
dl.datos dd{margin:0}
.tabla{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-weight:600;color:var(--tinta-suave);background:var(--piedra);padding:8px 10px;white-space:nowrap}
td{padding:9px 10px;border-bottom:1px solid var(--linea);vertical-align:top}
td.fecha{white-space:nowrap;font-variant-numeric:tabular-nums}
.sesiones{list-style:none;margin:0;padding:0}
.sesiones li{display:grid;grid-template-columns:110px 1fr;gap:4px 18px;padding:10px 0;border-bottom:1px solid var(--linea)}
.sesiones .fecha{font-variant-numeric:tabular-nums;color:var(--tinta-suave)}
.sesiones p{margin:0}
.situacion .contraste{margin:8px 0 0;padding-left:20px;font-size:13.5px;color:var(--tinta-suave)}
@media (max-width:680px){.sesiones li{grid-template-columns:1fr}}
.tipo{display:inline-block;font-size:12px;padding:1px 9px;border-radius:999px;background:var(--cupula-tenue);color:var(--cupula-oscura);white-space:nowrap}
.tipo.asesores{background:var(--piedra);color:var(--tinta-suave)}
.secundario{color:var(--tinta-suave);font-size:13px;margin:4px 0 0}
.docs a{display:inline-block;margin-right:12px;white-space:nowrap}
.vacio{color:var(--tinta-suave);font-style:italic}
.bloques{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.bloque{border:1px solid var(--linea);padding:14px 16px}
.bloque h3{font-size:14px;margin:0 0 8px;font-weight:600}
.bloque dl{display:grid;grid-template-columns:auto 1fr;gap:3px 12px;margin:0;font-size:13.5px}
.bloque dt{color:var(--tinta-suave)}
.bloque dd{margin:0}
.notas{white-space:pre-wrap;font-family:var(--serif);font-size:16px;border-left:3px solid var(--linea);padding-left:16px}
footer{margin-top:44px;padding-top:14px;border-top:1px solid var(--linea);font-size:12.5px;color:var(--tinta-suave)}
footer ul{padding-left:18px;margin:6px 0}
@media (max-width:680px){
  .hoja{margin:0;padding:28px 20px}
  .numero{font-size:40px}
  dl.datos{grid-template-columns:1fr;gap:2px}
  dl.datos dd{margin-bottom:8px}
  .pasos{grid-template-columns:1fr;gap:10px}
  .paso{padding:2px 0 0 36px}
  .paso::after{display:none}
}
@media print{
  :root{--tinta:#1F2B28;--tinta-suave:#55645F;--papel:#fff;--piedra:#EEF2F0;--linea:#CBD5D1;
        --cupula:#2E6B5F;--cupula-oscura:#1F4E45;--cupula-tenue:#E4EFEB;--lacre:#8C2F2F;--lacre-tenue:#F6E7E5;
        --ambar:#8A5A10;--ambar-tenue:#F7EEDC}
  body{background:#fff}
  .hoja{margin:0;padding:0;max-width:none;border-top:0}
  h2{break-after:avoid}
  tr,.bloque{break-inside:avoid}
  .situacion,.paso::before,th{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
"""

_COLOR_NIVEL = {
    "con_dictamen": "ambar",
    "vetado": "lacre", "caducado": "lacre", "rechazado": "lacre", "archivado": "lacre",
}


def _e(texto) -> str:
    return escape(str(texto or ""), quote=True)


def _enlace(texto: str, url: str | None) -> str:
    if not url:
        return _e(texto)
    return f'<a href="{_e(url)}" target="_blank" rel="noopener">{_e(texto)}</a>'


def _linea(linea: Linea) -> str:
    return "".join(_enlace(f.texto, f.url) for f in linea)


def _dl(filas: list[tuple[str, Linea]]) -> str:
    return '<dl class="datos">' + "".join(
        f"<dt>{_e(etiqueta)}</dt><dd>{_linea(linea)}</dd>" for etiqueta, linea in filas
    ) + "</dl>"


def generar_html(resultado: Resultado, ejemplo: bool = False) -> str:
    f, s = resultado.ficha, resultado.situacion
    partes: list[str] = []
    agregar = partes.append

    agregar('<div class="membrete"><span>H. Senado de la Nación</span>'
            f'<span>Informe del {resultado.generado:%d/%m/%Y, %H:%M} h</span></div>')
    if ejemplo:
        agregar('<p class="secundario"><strong>Ejemplo generado con páginas de prueba.</strong> '
                'No reemplaza una consulta real.</p>')
    agregar(f'<h1 class="numero">{_e(f.id.corto)}</h1>')
    agregar(f'<p class="descripcion">{_e(descripcion(f))}</p>')
    if f.extracto:
        agregar(f'<p class="extracto">{_e(f.extracto)}</p>')
    enlaces = [_enlace("Ficha en el sitio del Senado", f.url)]
    if f.texto_original:
        enlaces.append(_enlace("Texto original (PDF)", f.texto_original.url))
    for d in f.textos_definitivos:
        enlaces.append(_enlace(d.etiqueta, d.url))
    agregar('<p class="enlaces">' + "".join(f"<span>{x}</span>" for x in enlaces) + "</p>")

    # ---- situación
    color = _COLOR_NIVEL.get(s.nivel, "")
    agregar(f'<section class="situacion {color}" aria-labelledby="situacion">')
    agregar('<p class="rotulo">Situación actual</p>')
    agregar(f'<h2 id="situacion">{_e(s.titulo)}</h2>')
    if s.detalle:
        agregar("<ul>" + "".join(f"<li>{_e(d)}</li>" for d in s.detalle) + "</ul>")
    if s.contraste:
        agregar('<ul class="contraste" aria-label="Contraste con el sitio de Diputados">'
                + "".join(f"<li>{_e(d)}</li>" for d in s.contraste) + "</ul>")
    if s.pasos:
        agregar(f'<ol class="pasos" style="--n:{len(s.pasos)}" aria-label="Recorrido del trámite">')
        for p in s.pasos:
            extra = " ".join(x for x in [fmt_fecha(p.fecha, ""), p.detalle] if x)
            estado = {"hecho": "cumplido", "actual": "etapa actual", "detenido": "se detuvo aquí",
                      "pendiente": "pendiente"}[p.estado]
            agregar(f'<li class="paso {p.estado}" aria-label="{_e(p.nombre)}: {estado}">'
                    f"<strong>{_e(p.nombre)}</strong>{_e(extra)}</li>")
        agregar("</ol>")
    if s.caducidad:
        c = s.caducidad
        etiqueta = "Caducidad registrada" if c.registrada else "Caducidad estimada"
        clase = " vencida" if (c.vencida and not c.registrada) else ""
        aviso = " El plazo estimado ya venció: verificar en la Dirección de Mesa de Entradas." \
            if c.vencida and not c.registrada else ""
        agregar(f'<p class="caducidad{clase}"><strong>{etiqueta}: {fmt_fecha(c.fecha)}.</strong> '
                f"{_e(c.fundamento)}{_e(aviso)}</p>")
    agregar("</section>")

    # ---- datos
    agregar("<h2>Datos del expediente</h2>")
    agregar(_dl(datos_generales(f)))

    dip = datos_diputados(f) + datos_diputados_hcdn(resultado)
    if dip:
        agregar("<h2>Etapa en la Cámara de Diputados</h2>")
        agregar(_dl(dip))

    if f.giros:
        agregar("<h2>Giros a comisiones</h2>")
        filas = "".join(
            f"<tr><td>{_e(nombre_comision(g.comision))}</td><td>{_e(g.orden or '—')}</td>"
            f'<td class="fecha">{fmt_fecha(g.ingreso)}</td><td class="fecha">'
            f"{fmt_fecha(g.egreso, 'en curso' if g.ingreso else '—')}</td></tr>"
            for g in f.giros)
        agregar('<div class="tabla"><table><thead><tr><th>Comisión</th><th>Orden de giro</th>'
                f"<th>Ingreso</th><th>Egreso</th></tr></thead><tbody>{filas}</tbody></table></div>")

    # ---- reuniones
    agregar("<h2>Reuniones de comisión en que se trató</h2>")
    if resultado.reuniones:
        filas = []
        for r in resultado.reuniones:
            docs = [_enlace(d.etiqueta if len(d.etiqueta) > 3 else "Versión taquigráfica", d.url) for d in r.versiones]
            docs += [_enlace("Video", v) for v in r.videos]
            docs += [_enlace(d.etiqueta, d.url) for d in r.otros_archivos]
            clase_tipo = "tipo asesores" if r.tipo == "Asesores" else "tipo"
            filas.append(
                f'<tr><td class="fecha">{_enlace(fmt_fecha(r.fecha), r.url)}</td>'
                f"<td>{_enlace(r.titulo, r.url)}"
                f'<p class="secundario">{_e(comisiones_texto(r.comisiones))}</p></td>'
                f'<td><span class="{clase_tipo}">{_e(r.tipo)}</span></td>'
                f'<td class="docs">{"".join(docs) or "<span class=vacio>sin archivos</span>"}</td></tr>')
        agregar('<div class="tabla"><table><thead><tr><th>Fecha</th><th>Reunión</th><th>Tipo</th>'
                f"<th>Documentos</th></tr></thead><tbody>{''.join(filas)}</tbody></table></div>")
    elif resultado.busqueda.realizada:
        agregar('<p class="vacio">No se encontraron reuniones publicadas en que figure este expediente.</p>')
    else:
        agregar('<p class="vacio">No se buscaron reuniones de comisión para este informe.</p>')
    agregar(f'<p class="secundario">{_e(alcance_busqueda(resultado))}</p>')

    if resultado.convocadas:
        agregar("<h2>Próximas reuniones convocadas</h2>")
        filas = "".join(
            f'<tr><td class="fecha">{_e(fmt_fecha(c.fecha, c.fecha_texto))}</td><td>{_e(c.hora or "—")}</td>'
            f"<td>{_enlace(c.titulo, c.url)}<p class='secundario'>{_e(c.comision)}</p></td>"
            f"<td>{_e(c.lugar or '—')}</td></tr>" for c in resultado.convocadas)
        agregar('<div class="tabla"><table><thead><tr><th>Fecha</th><th>Hora</th><th>Reunión</th>'
                f"<th>Lugar</th></tr></thead><tbody>{filas}</tbody></table></div>")

    if f.ordenes_del_dia:
        agregar("<h2>Órdenes del Día del Senado</h2>")
        filas = "".join(
            f"<tr><td>{_enlace('N° ' + od.numero, od.url)}</td><td class='fecha'>{fmt_fecha(od.fecha)}</td>"
            f"<td>{_e(od.estado.capitalize())}</td>"
            f"<td>{_enlace('Dictamen (PDF)', od.url_pdf) if od.url_pdf else '—'}</td></tr>"
            for od in f.ordenes_del_dia)
        agregar('<div class="tabla"><table><thead><tr><th>Número</th><th>Fecha</th><th>Estado</th>'
                f"<th>Texto</th></tr></thead><tbody>{filas}</tbody></table></div>")

    if resultado.votaciones_consultadas:
        agregar(_votaciones(resultado))

    bloques = bloques_resolucion(f)
    if bloques:
        agregar("<h2>Sanción y resoluciones</h2><div class='bloques'>")
        for titulo, campos in bloques:
            agregar(f"<div class='bloque'><h3>{_e(titulo)}</h3><dl>"
                    + "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in campos) + "</dl></div>")
        agregar("</div>")

    observaciones = f.observaciones + f.anotaciones
    otros_hitos = [h for h in f.hitos if not any(
        clave in h.upper() for clave in ("ARCHIVO", "CADUC", "PREFERENCIA", "PARA:"))]
    if observaciones or otros_hitos:
        agregar("<h2>Observaciones de la ficha</h2><ul>"
                + "".join(f"<li>{_e(o)}</li>" for o in observaciones + otros_hitos) + "</ul>")

    if resultado.notas_usuario:
        agregar(f"<h2>Notas</h2><p class='notas'>{_e(resultado.notas_usuario)}</p>")

    agregar("<footer>")
    agregar(f"<p>Informe generado automáticamente con datos públicos del sitio del H. Senado de la Nación "
            f"({_enlace('ficha del expediente', f.url)}). Antes de usarlo en un trámite oficial, "
            "verificá los datos en la fuente. Programa Informe de Expedientes, versión "
            f"{_e(__version__)}.</p>")
    if resultado.advertencias:
        agregar("<p>Durante la consulta hubo avisos:</p><ul>"
                + "".join(f"<li>{_e(a)}</li>" for a in resultado.advertencias) + "</ul>")
    agregar("</footer>")

    return (
        '<!DOCTYPE html>\n<html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Informe {_e(f.id.corto)} — H. Senado de la Nación</title>"
        f"<style>{ESTILOS}</style></head><body><main class='hoja'>"
        + "".join(partes) + "</main></body></html>\n"
    )


def _votaciones(resultado: Resultado) -> str:
    partes = ["<h2>Votaciones en el recinto</h2>", f"<p>{_e(texto_votaciones(resultado))}</p>"]
    sesiones = sesiones_votadas(resultado)
    if sesiones:
        partes.append('<ul class="sesiones">')
        for sv in sesiones:
            enlaces = " ".join(_enlace(fr.texto, fr.url) for fr in sv.enlaces)
            partes.append(f'<li><span class="fecha">{_e(sv.fecha)}</span><div>'
                          + "".join(f"<p>{_e(x)}</p>" for x in sv.lineas)
                          + (f'<p class="secundario docs">{enlaces}</p>' if enlaces else "") + "</div></li>")
        partes.append("</ul>")
    return "".join(partes)


def escribir(resultado: Resultado, destino: Path, ejemplo: bool = False) -> Path:
    Path(destino).write_text(generar_html(resultado, ejemplo), encoding="utf-8")
    return Path(destino)
