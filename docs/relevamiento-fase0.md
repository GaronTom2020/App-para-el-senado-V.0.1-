# Relevamiento de la Fase 0 (30/10/2026)

Qué publica el sitio del Senado y el de Diputados para las funciones nuevas, con las páginas reales
guardadas en `tests/fixtures/`. Todas se bajaron el 30/10/2026. De las páginas HTML se quitaron los
`<script>`, `<style>`, `<link>` y comentarios para que pesen menos; el resto del HTML queda tal cual.
De `senadores_bloques.html` se quitó además la nómina de personal de cada bloque, que no hace falta.

## a) Actas de votación nominal

### Dónde están

| Página | Dirección | Qué trae |
|---|---|---|
| Listado del año | `GET /votaciones/actas` (año en curso) o `POST /votaciones/actas` con `busqueda_actas[anio]=2025` y `busqueda_actas[titulo]=` | Una fila por votación: fecha, número de acta en la sesión, título, expedientes, OD, tipo, resultado, mayoría, PDF, detalle y video. |
| Detalle | `GET /votaciones/detalleActa/{ID}` | Cabecera con totales y la tabla Senador / Bloque / Provincia / ¿Cómo votó? |
| PDF del acta | `GET /votaciones/verActaVotacion/{ID}` | Lista nominal, quórum, mayoría, presentes, presidente. **Se publica antes que el detalle.** |

- El `POST` del listado **no pide token** y funciona sin cookies previas. El filtro `busqueda_actas[titulo]`
  busca en el título («Banco» → 18 actas en 2026). Es cierto que `?anio=` no sirve.
- El listado de 2026 pesa ~1 MB (165 filas, 139 con detalle). 2025: 97 filas; 2024: 91; 2020: 93.
- Rangos de ID por año: 2026 = 2623–2873, 2025 = 2525–2622, 2024 = 2432–2524, 2020 = 1163–1261,
  2015 = 423–516. Desde 2024 son correlativos por año; antes no conviene suponer el orden.

### Cómo identifica el acta lo votado

En el listado (`votaciones_actas_2026.html`), cada fila puede traer:

1. **Enlaces a la ficha** (`verExp/159.25/PE/PL`), dentro de un bloque oculto «Ver Expedientes». Puede
   haber varios (hasta 27 en una votación de acuerdos). Es el dato más seguro.
2. **Enlace a la Orden del Día** (`ordenDelDiaResultadoLink/2026/367`) con el texto «O.D. 367/2026», y
   a veces los artículos votados («Art. 20», «Art. 6 Bis»).
3. Solo el **título** («Designación de…», «Moción de orden…»).

Cuántas filas traen cada dato:

| Año | Filas | Con expediente | Con OD | Ninguno de los dos |
|---|---|---|---|---|
| 2026 | 165 | 74 | 150 | 11 |
| 2025 | 97 | 49 | 44 | 28 |
| 2024 | 91 | 7 | 40 | 44 |
| 2020 | 93 | 29 | 81 | 10 |

Cuando solo está la OD, se llega al expediente con la página de la OD, que el programa ya lee
(`od_2026_409.html`: OD 409/2026 → PE-99/26-PL). Las filas sin ninguno de los dos son, sobre todo,
mociones, designaciones y habilitaciones sobre tablas. A veces el título nombra el expediente
(«…retorno a comisión del expediente PE-159/25»), y se puede buscar con `identificador.patron_texto()`.

### Cabecera del detalle (`acta_2847.html`, `acta_2623.html`)

- «Acta Nro: 17»: es el número **dentro de la sesión**, no el ID.
- Título, enlaces a expediente u OD y artículos.
- Fecha y hora («24/09/2026 - 17:44»).
- Mayoría requerida («SIMPLE»; en otras actas, «DOS TERCIOS DE VOTOS EMITIDOS»).
- Resultado («AFIRMATIVO»/«NEGATIVO») y tipo («EN GENERAL», «EN PARTICULAR», «EN GENERAL Y EN PARTICULAR»;
  en el listado aparecen también «MOCIÓN DE ORDEN», «HABILITACIÓN TRAT SOBRE TABLAS» y «OTRA»).
- Totales: afirmativos, negativos, abstenciones y ausentes.
- **El detalle no trae quórum.** Está en el PDF.
- Tabla `id="tabla"`, 72 filas: foto (enlace `/senadores/senador/{id}`), senador, bloque, provincia y voto.
  Una fila puede no tener enlace (en el acta 2847, «PAGOTTO, JUAN CARLOS»), así que hay que poder cruzar
  por nombre también.
- El botón «Datos abiertos» arma el Excel **en el navegador** (DataTables): no hay archivo en el servidor.

### Actas de la última sesión: primero sale el PDF

Las 26 votaciones de la sesión del 29-30/10/2026 (ID 2848 a 2873) **ya figuran en el listado, pero sin
enlace al detalle**, solo con el PDF. Su detalle (`acta_2867_pendiente.html`) tiene el resultado y la OD,
pero el título vacío, la hora vacía, los totales en 0 y la tabla sin filas.

El PDF, en cambio, ya está completo (`acta_2867.pdf`, Salud Mental en general):

> EN GENERAL OD 409/26 - SALUD MENTAL · 30/10/2026 00:52:56 · 42 SI, 21 NO, 0 abstenciones, 9 ausentes ·
> Tipo Quorum: MAS 1/2 MC · Mayoría: MAS 1/2 LEGISLADORES PRESENTES · Miembros del cuerpo: 72 ·
> Presentes: 63 · Resultado: AFIRMATIVA · Presidente: VILLARRUEL · Acta: 20 · Votación: NOMINAL

El PDF tiene la lista nominal (nombre y SI/NO/AUSENTE/ABSTENCION) pero **no el bloque**: hay que
cruzarlo por nombre con el último detalle completo o con el listado de bloques. El texto se extrae bien
con `pypdf`, aunque algunas etiquetas salen desordenadas («Negativos: Abstenciones: 21 0»): conviene
contar los votos de la lista en vez de leer esas etiquetas. Las fechas no coinciden: el listado dice 29/10
y el PDF, 30/10 00:52 (la sesión siguió después de medianoche).

**ID inexistente** (`acta_2874_inexistente.html`): el sitio responde 200 con la plantilla vacía, «Acta Nro:»
sin número y la fecha de hoy. Hay que tratarlo como «no existe», no como un acta.

### La forma más barata de encontrar actas nuevas

1. Un `GET /votaciones/actas` (año en curso, ~1 MB) con caché de algunas horas. Trae todas las filas, las
   pendientes incluidas, con sus enlaces a expediente y OD. Con eso alcanza para saber si un expediente
   o su OD tuvo votación, sin abrir ninguna acta.
2. Solo para las actas que corresponden al expediente: el detalle (bloques) si está completo, o el PDF si
   todavía no.
3. Para años anteriores, un `POST` por año; esos listados casi no cambian y pueden guardarse por mucho tiempo.
4. El índice ya revisado (ID → expedientes, OD, fecha, resultado, si estaba completa) se guarda en caché.
   Las actas pendientes se vuelven a consultar hasta que el detalle tenga filas.

No hace falta recorrer los ID uno por uno.

## b) Plan de labor parlamentaria

- **Se publica.** Página `GET /parlamentario/parlamentaria/actas` («Plenario de Labor Parlamentaria»,
  `plenario_labor.html`): tabla con fecha de la reunión, fecha prevista de la sesión y enlace «descargar».
  Son 565 registros, desde 1987; el último es del 28/10/2026, para la sesión del 29/10/2026.
- **Formato: PDF** con texto extraíble (no es una imagen escaneada). Se lee con `pypdf`, palabra por palabra,
  y hay que normalizar los espacios.
- **Los nombres de archivo son irregulares** («…%20%2028-10-2026.pdf», «…%2017-09-2026.pdf» para una reunión
  listada el 16-09, «…%208-07-2026.pdf», «Plan%20de%20Labor%2024_02_2026.pdf»). Hay que tomar el enlace
  de la tabla, no armarlo con la fecha.
- Estructura del PDF (`plan_labor_2026-10-28.pdf`): fecha de reunión y de sesión, hora, carácter, «Se acordó
  el tratamiento de los siguientes temas» (lista numerada en orden de tratamiento), «Órdenes del día impresos
  a considerar», preferencias, «Asuntos sobre tablas acordados» (**solo con título, sin número**, por ejemplo
  «Proyecto de resolución: Papa León XIV»), autoridades y presidentes de bloque presentes.
- Casi siempre nombra **órdenes del día**, no expedientes. Formas que aparecen:
  - «OD 413/26 - RIIR», «OD 409/26 y Anexo - Salud mental» (28/10)
  - «OD de acuerdos: 338; 353; 354», «OD 360 y 361», «OD 340 a 342 y 344 a 352», sin año (17/09)
  - «OD 22/26 a 27/26 inclusive», «OD 104/26 y anexos», y un error de tipeo, «0D 206/26» con cero (08/07)

## c) Diputados: proyectos que llegan del Senado

- Se busca con el formulario de Diputados, `POST https://www.hcdn.gob.ar/proyectos/resultado.html` con
  `strNumExp`, `strNumExpOrig` (PE, S, CD, D…) y `strNumExpAnio`, usando **el número del Senado**.
  También funciona por `GET` con los mismos parámetros, así que sirve como enlace.
- Diputados le asigna un número propio **NNNN-S-AAAA** y muestra los dos:
  PE-159/25 (Modernización Laboral) → «Expediente Diputados: **0065-S-2025** · Expediente Senado:
  0159-PE-2025». El año es el del expediente del Senado, no el del ingreso a Diputados (que fue en
  febrero de 2026). Los expedientes del Senado sin media sanción aparecen solo como «Expediente Senado:
  1247-S-2026».
- El resultado (`hcdn_pe_159_25_post.html`) trae en una sola página: giro a comisiones en Diputados y
  en el Senado, dictámenes de las dos cámaras («Diputados · Orden del Dia 0006/2025 · … · 18/02/2026»), el
  trámite completo con cámara, movimiento, fecha y resultado («MEDIA SANCION», «SANCIONADO»), firmantes y
  enlaces al texto. No hace falta otra página.
- **PE-99/26 (Salud Mental)**: Diputados ya lo tiene como «Expediente Senado: 0099-PE-2026», pero **todavía
  sin número de Diputados** (`hcdn_pe_99_26_antes.html`): la media sanción fue en la madrugada del 30/10.
  Lo mismo pasa en la ficha del Senado (`ficha_pe_99_26.html`), que muestra la OD 409/26 «PENDIENTE» y ninguna
  sanción.
- **Problema en el programa actual:** el enlace que arma hoy para Diputados,
  `https://www.hcdn.gob.ar/proyectos/proyecto.jsp?exp=…` (`config.URL_HCDN_PROYECTO`), **responde 404**,
  tanto para 1888-D-2024 como para 0065-S-2025. Habría que cambiarlo por
  `resultado.html?strNumExp=1888&strNumExpOrig=D&strNumExpAnio=2024`.

## d) Búsqueda por autor y bloque

- `busqueda_proyectos[autor]` del buscador avanzado tiene 479 senadores (actuales e históricos); el valor
  es el ID numérico, **el mismo de `/senadores/senador/{id}`** que usan las actas (MENDOZA, SANDRA MARIELA = 540).
- **Funciona con la exportación XLS** (`avanzada_autor_540_2026.xls`): autor 540 y año 2026 → 102 expedientes
  en el HTML y 102 filas en el XLS, con las mismas columnas de siempre (Numero Expediente, Tipo, Origen,
  Extracto). Incluye los proyectos en que el senador es **coautor** («MOISES Y OTROS: …»). El XLS no trae una
  columna de autor.
- Bloque de cada senador:
  - **Actuales:** `GET /senadores/listados/agrupados-por-bloques` (`senadores_bloques.html`), una sola página,
    con cada bloque, su presidente y los enlaces `/senadores/senador/{id}` de los integrantes.
  - **Históricos:** la página del senador redirige al inicio (`/senadores/senador/452` → 302). El bloque solo
    se puede sacar de las actas de su período (columna Bloque).
  - Los nombres de bloque se escriben distinto en las dos fuentes («Convicción Federal» en el listado,
    «CONVICCIÓN FEDERAL» y «UCR - UNIÓN CÍVICA RADICAL» en las actas): hay que normalizarlos.
  - Cambiar de bloque es común. Para un informe por bloque conviene usar el bloque actual (listado) y avisar
    que es el de hoy, no el de la fecha del proyecto.

## Decisiones que necesito antes de la Fase 1

1. **Nueva dependencia `pypdf`** (pura Python, sin compilar): hace falta para leer los PDF de las actas recientes
   (Fase 1) y el plan de labor (Fase 2). Se suma a `requirements.txt` y al `.exe`.
2. **Enlace roto a Diputados:** propongo corregirlo en la Fase 1 (es un cambio chico en `config.py` y
   `contenido.py`, con su prueba).
3. **pyflakes** ya marca dos avisos en el código actual (`xlrd` importado sin usar en `busqueda.py:199` y
   `ficha.py:102`; son importaciones a propósito para comprobar que está instalado). Propongo resolverlos en la
   Fase 1 con `importlib.util.find_spec("xlrd")`.
4. **CSV para Power BI (Fase 2):** sigue pendiente que me pases el formato exacto del tablero.

## Adenda (31/10/2026)

- **El trámite de Diputados detalla el recorrido constitucional.** La tabla «TRÁMITE» de hcdn.gob.ar registra,
  para las dos cámaras, la media sanción, «PASA A DIPUTADOS»/«VUELVE A SENADO», la sanción, el veto («SE OBSERVA
  TOTALMENTE… (VETO TOTAL …)») y la insistencia («RECHAZO DE LA INSISTENCIA (NO ALCANZA MAYORIA NECESARIA PARA
  INSISTIR - ACEPTA VETO)») (`hcdn_cd_14_24.html`, `hcdn_1888_d_2024.html`). Para que la traiga hay que pedir la
  búsqueda con `strMostrarTramites=on`; por GET funciona igual que por POST.
- **Artículos modificados.** Las actas del Senado no dicen qué artículos se modificaron. Diputados sí los nombra en
  sus votaciones en particular («CONSIDERACION Y APROBACION CON MODIFICACIONES EN PARTICULAR DE LOS ARTICULOS 2, 3,
  4, 5 Y 6»); para el Senado solo anota «CON MODIFICACIONES» o «POR TITULO». Los rechazos en particular del Senado
  sí se ven en las actas (resultado NEGATIVO de la votación del artículo o título).
- **Insistencias** (art. 83): figuran en el listado como «OTRA» o «EN GENERAL Y EN PARTICULAR» con «Insistencia» en el
  título (2025: actas 2576, 2582, 2597, 2598).
- **PE-99/26**: el 31/10 la ficha del Senado ya registra la sanción (30/10/2026, «CON MODIFICACIONES», «PASA A DIP.»)
  y Diputados, la media sanción del 29/10 y el pase (`ficha_pe_99_26_registrada.html`, `hcdn_pe_99_26.html`).
- **El detalle del acta y su PDF no coinciden.** El detalle del acta 2867 (Salud Mental en general), publicado el
  31/10, cuenta 52 afirmativos, 15 negativos y 5 ausentes; el PDF del mismo acta, sin cambios desde el 30/10, cuenta
  42, 21 y 9 (`acta_2867_completa.html`, `acta_2867.pdf`). No hay forma de saber desde el sitio cuál es la correcta.
