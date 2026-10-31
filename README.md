# Informe de Expedientes — H. Senado de la Nación

Programa de escritorio con cuatro modos:

- **Un expediente**: a partir de su número, arma un informe en Word y HTML con su situación en el trámite parlamentario, las reuniones de comisión en que se trató y los enlaces a cada fuente.
- **Por tema**: a partir de un eje temático o de palabras clave, encuentra todos los expedientes que responden a ese tema y arma un informe consolidado en Word, HTML y Excel con la etapa de cada uno.
- **Seguimiento**: una lista de expedientes que se revisa seguido para avisar qué cambió.
- **Sesión**: a partir del plan de labor parlamentaria, un único informe con cada asunto en el orden de tratamiento y la ficha de sus expedientes, más un CSV para el tablero de sesiones.

Usa solamente información pública de www.senado.gob.ar y www.hcdn.gob.ar.

## Qué incluye el informe

- **Situación actual**: en comisión, con dictamen, aprobado, sancionado, vetado, caducado o archivado, con una línea de pasos del trámite que marca dónde está o dónde se detuvo. En los proyectos de ley, la situación sigue el recorrido de la Constitución (arts. 77 a 84) y dice qué sigue: el pase a la cámara revisora (art. 78), la vuelta a la cámara de origen cuando la revisora lo modificó y las mayorías para aceptar o insistir (art. 81), la promulgación tácita a los diez días útiles y la promulgación parcial (art. 80), el veto y la insistencia con dos tercios (art. 83), y que un proyecto rechazado o con el veto firme no puede repetirse en las sesiones de ese año.
- **Contraste con la Cámara de Diputados**: en los proyectos de ley se consulta también el sitio de Diputados (hcdn.gob.ar), que suele registrar antes la media sanción, el pase a la otra cámara, el veto y la insistencia. Lo que figura allí y todavía no en la ficha del Senado se avisa en la situación («El sitio de Diputados registra la media sanción del Senado del 29/10/2026, con modificaciones al dictamen; la ficha del Senado todavía no»), igual que si los números de ley no coinciden.
- **Caducidad**: la registrada en la ficha del Senado o, si no figura, una estimación según la Ley 13.640 (proyectos de ley) o la Resolución del Senado del 13/06/1991 (declaración, resolución, comunicación y decreto).
- **Origen** (Senado, Poder Ejecutivo, Cámara de Diputados…), tipo, extracto, autores, fecha de mesa de entradas, dado cuenta y número de DAE.
- **Enlaces** a la ficha del Senado, al texto original y al texto sancionado o definitivo.
- **Etapa en la Cámara de Diputados (revisión)**, para los proyectos de ley que salen del Senado, o **(origen)**, para los que vienen de Diputados: el número que le asignó Diputados (del tipo 57-S-2026) enlazado a su sitio, en qué está allí (ingresó, en comisión, con dictamen, aprobado, aprobado con modificaciones y de vuelta al Senado, sancionado o rechazado), el giro a sus comisiones, el dictamen con su Orden del Día y lo que aconseja, la votación, los artículos modificados o rechazados en particular y el último movimiento. Para los que vienen de Diputados se suma lo que trae la ficha del Senado (Trámite Parlamentario, Orden del Día y fecha de sanción). La línea de pasos refleja esa etapa («Cámara de Diputados: en comisión», «dictamen, OD 448/2026», «rechazó») y la situación la explica («En Diputados (expediente 57-S-2026): en las comisiones de …»). Si Diputados lo rechazó, la situación queda «Rechazado por la Cámara de Diputados», con la regla del art. 81.
- **Giros a comisiones**, con fechas de ingreso y egreso.
- **Reuniones de comisión** en que se trató: fecha (enlazada a la nota de la reunión), título, comisiones, tipo (comisión, plenario o asesores), versión taquigráfica y video.
- **Reuniones ya convocadas** en la agenda de las comisiones del giro.
- **Órdenes del Día del Senado**, con su estado y el PDF del dictamen.
- **Votaciones en el recinto**: una línea por sesión. La votación en general con su resultado («aprobado (42 a 21)»); en particular, solo los artículos rechazados o modificados, en rangos («se rechazaron los arts. 23-24»), o «aprobado sin observaciones»; y las insistencias (art. 83), con si alcanzaron los dos tercios. Las mociones, preferencias y habilitaciones sobre tablas no se incluyen. Si el Senado aprobó con modificaciones y las actas no dicen qué artículos, se aclara y se enlaza el texto aprobado. Si el detalle del acta y su PDF dan totales distintos, se avisa. Si hay una votación más reciente que lo que registra la ficha, la situación lo dice («Votado en el recinto el 29/10/2026 (42 a 21); la ficha oficial todavía no registra la sanción») y la línea de pasos marca la sanción del Senado como hecha.
- Sanción, número de ley, resolución del Poder Ejecutivo (veto o promulgación, decreto y Boletín Oficial), observaciones de la ficha y notas propias.

## Instalación

**Opción A, con el ejecutable (recomendada para la oficina).** El `.exe` se compila una sola vez y después se copia a cada PC, que no necesita Python. Para compilarlo hay dos caminos:

- *En una PC con Python.* Instalá Python desde https://www.python.org/downloads/ (3.10 o posterior), marcando **Add python.exe to PATH** en la primera pantalla del instalador; si no tenés permisos de administrador, desmarcá *Use admin privileges when installing py.exe*. Después, doble clic en `construir_exe_windows.bat`, que genera `dist\InformeExpediente.exe`. Ojo: el «python» que ofrece abrir la Microsoft Store no es Python, es un atajo de Windows.
- *En GitHub, sin instalar nada.* Subí el programa a un repositorio, copiá `despliegue/compilar-exe-windows.yml` a `.github/workflows/` y ejecutalo desde la pestaña *Actions*: compila en una máquina Windows de GitHub, corre las pruebas y deja el `.exe` para descargar.

Si el antivirus o Sistemas bloquean el `.exe`, pedí que lo autoricen: es un programa sin firma digital.

**Opción B, desde el código.** Con Python 3.10 o posterior (al instalarlo, marcar *Add python.exe to PATH*), hacer doble clic en `iniciar.bat`. La primera vez instala las dependencias en una carpeta `.venv`; las siguientes abre directamente la ventana.

En Linux o macOS: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python app.py`.

## Uso

1. Escribí uno o más expedientes, uno por línea: `S-1234/24`, `CD-14/24`, `PE-107/24`, `1370-S-2020` o el enlace a la ficha del Senado.
2. Dejá el tipo en *Detectar automáticamente* (el programa lo consulta en el buscador del Senado) o elegilo si lo sabés.
3. Elegí qué buscar y el formato, y presioná **Generar informe** (o Ctrl+Enter).
4. Al terminar, el resumen aparece en la ventana con los enlaces activos. Los botones de abajo abren el Word, el HTML o la carpeta de informes.

En la pestaña *Reuniones*, el doble clic abre la nota de la reunión y el clic derecho ofrece la versión taquigráfica, el video o copiar el enlace.

## Informe temático (por eje o palabras clave)

En la pestaña **Por tema**:

1. Elegí un **eje temático** (completa solo las palabras) o escribí tus propias **palabras clave**, separadas por coma.
2. Indicá si el extracto tiene que tener **alguna** o **todas** las palabras, y si querés **excluir** los que mencionen otras (por ejemplo, el eje «Consumo» excluye «consumo problemático»).
3. Ajustá los **años** de los expedientes, el **origen**, la **comisión del giro** y los **tipos** (por defecto: ley, resolución y comunicación; las declaraciones quedan afuera porque suelen ser muy numerosas).
4. Elegí qué hacer con cada expediente encontrado: consultar su ficha (para saber su etapa y comisión, recomendado), buscar sus reuniones de comisión (lento) o generar además su informe completo.
5. Presioná **Generar informe temático**. La lista aparece en la pestaña *Expedientes*: doble clic abre la ficha, clic derecho genera el informe completo de ese expediente.

**Cómo busca.** Consulta la búsqueda avanzada del Senado por extracto, una vez por año y por palabra, y descarga la exportación completa de resultados. Sobre eso aplica un filtro propio que no distingue tildes ni mayúsculas y busca el **comienzo** de cada palabra: «universidad» encuentra «universidades», pero «penal» no encuentra «despenalizar». Con «todas», consulta al sitio por la palabra más larga y exige las demás en el extracto.

**Cuánto tarda.** Hace una consulta por año y por palabra (dos si la palabra lleva tilde, para no perder extractos cargados sin tilde), más una por cada ficha. Un eje de seis palabras en dos años son unas 15 consultas de búsqueda y luego una por expediente encontrado: entre uno y tres minutos. Para períodos largos conviene acotar con comisión o tipo. Se consultan como máximo 200 fichas; el resto figura en el informe sin etapa.

**Qué trae el informe.** Un resumen con las cantidades en forma normativa («Se identificaron VEINTIÚN (21) expedientes… DOCE (12) en comisión…»), la cuenta por etapa, tipo y origen, los criterios usados y la tabla de expedientes agrupada por etapa, con el extracto (las palabras encontradas resaltadas), la situación, la caducidad, la comisión y la fecha de ingreso. El Excel trae una fila por expediente, con filtros y enlaces, y una hoja *Resumen* cuyos totales son fórmulas (`CONTAR.SI`) que se recalculan si filtrás o borrás filas.

**Ejes temáticos.** Vienen doce ejes iniciales (educación, salud, ambiente, seguridad, economía, trabajo, género, niñez, energía, discapacidad, consumo y transferencia de inmuebles). Con **Guardar como eje…** guardás las palabras, exclusiones, modo y comisión actuales con un nombre; **Borrar eje** lo elimina. Se guardan en `ejes.json` dentro de la carpeta de configuración; para que todo el equipo use los mismos, copiá ese archivo en cada PC o pasalo con `--ejes` en la línea de comandos. Formato:

```json
{"ejes": [{"nombre": "Litio", "palabras": ["litio", "minería"], "modo": "alguna",
           "excluir": [], "comision_id": 65}]}
```

`comision_id` es el número de la comisión en el sitio del Senado (`comisiones/info/{número}`); puede ser `null`.

## Informe de sesión (plan de labor)

En la pestaña **Sesión**:

1. Cargá el plan de labor: **Abrir archivo…** (Word `.docx`, PDF o texto), **Buscar en el sitio** (lista los planes publicados en el Plenario de Labor Parlamentaria del Senado; elegí uno y se descarga) o pegá el texto en el cuadro. El texto queda a la vista y se puede corregir.
2. **Ver los asuntos** muestra lo que el programa entendió, en el orden de tratamiento, antes de consultar nada.
3. Elegí los formatos (Word, HTML, Excel y CSV) y presioná **Generar informe de sesión**.

**Qué entiende del plan.** Toma la lista «Se acordó el tratamiento de los siguientes temas» en su orden; después suma las órdenes del día impresas que no estaban en esa lista, las preferencias y los asuntos sobre tablas. Reconoce las órdenes del día en sus formas habituales («OD 409/26 y Anexo», «OD de acuerdos: 338; 353; 354», «OD 340 a 342 y 344 a 352», «OD 22/26 a 27/26 inclusive», incluso «0D 206/26») y los expedientes, también en listas abreviadas («S-285, 637 y 638/24»). Si una orden del día no lleva año, usa el de la sesión. Los asuntos sin número (juras, «Dar cuenta de acuerdos», proyectos sobre tablas nombrados solo por su título) figuran en el índice sin ficha. Si el texto no tiene la estructura del plan (una lista pegada a mano), toma un asunto por renglón.

**Qué trae el informe.** Un resumen («El plan de labor para la sesión del 29/10/2026 acordó NUEVE (9) asuntos…»), el índice de asuntos con su orden del día, sus expedientes y la situación de cada uno, y la ficha completa de cada expediente, la misma del informe individual, con la situación, el contraste con Diputados y las votaciones. De cada orden del día se toman los expedientes que trata (pueden ser varios, en conjunto). Por defecto no se buscan las reuniones de comisión, porque una sesión puede tener decenas de expedientes.

**CSV para el tablero de Power BI.** Una fila por asunto, separado por punto y coma, en UTF-8 con BOM y con fechas dd/mm/aaaa. Columnas: `Fecha de sesión`, `Orden`, `Expediente` (varios, separados por coma), `OD`, `Título` (el del plan o, si no lo trae, el extracto), `Tipo` y `Comisiones` (del giro, separadas por « / », porque algunos nombres llevan coma). Las columnas están en `informe_sesion.COLUMNAS_CSV`.

## Lista de seguimiento

En la pestaña **Seguimiento** se arma una lista de expedientes para revisar seguido. Se agregan escribiendo el número (o varios, separados por coma) o, desde la lista del modo *Por tema*, con clic derecho → *Agregar a la lista de seguimiento*. Para quitarlos, elegilos y presioná *Quitar los elegidos* (o Supr).

**Revisar novedades** vuelve a consultar cada expediente y lo compara con la revisión anterior. Avisa:

- giro nuevo a una comisión y egreso de una comisión;
- dictamen u orden del día nuevos, o cambio de estado de una orden del día;
- votación en el recinto y sanción registrada en la ficha;
- media sanción, sanción, rechazo, pase a la otra cámara, veto o insistencia que registra el sitio de Diputados, y en Diputados el número que le asignó, el giro a sus comisiones y el dictamen;
- reunión convocada con el expediente en el temario y reunión de comisión en que se trató (si se buscan reuniones);
- cambio de situación y caducidad cercana (menos de 60 días).

La primera revisión de cada expediente solo guarda su estado («Primera revisión»). El resumen queda en la ventana y en un HTML y un Markdown en la carpeta de informes; *Copiar resumen* copia el Markdown. La lista y la última «foto» de cada expediente se guardan en `seguimiento.json`, en la carpeta de configuración.

## Cómo se buscan las votaciones

El programa lee el listado anual de votaciones del Senado (`votaciones/actas`), desde el año de ingreso del expediente hasta hoy, y toma las filas que enlazan el expediente o su orden del día, o que lo nombran en el título. Solo se tienen en cuenta las votaciones sobre el contenido (en general, en particular e insistencias). De las votaciones en general abre el detalle del acta, que trae los totales, y lo contrasta con el PDF. En las sesiones recientes el detalle se publica vacío durante unos días: mientras tanto se usa el PDF, que ya trae la lista nominal, el quórum y, en el título, los artículos votados («ART. 1 AL 22»). De las votaciones en particular basta el listado, salvo en esas sesiones recientes.

Las actas del Senado no dicen qué artículos se modificaron respecto del dictamen. Eso sale del sitio de Diputados, que en sus votaciones en particular sí los nombra («APROBACION CON MODIFICACIONES EN PARTICULAR DE LOS ARTICULOS 2, 3, 4, 5 Y 6»), y de la ficha o del trámite cuando el Senado aprobó «con modificaciones».

Los listados y las actas ya leídas se guardan en un índice (`indice_votaciones.json`, en la carpeta de caché): el año en curso se vuelve a leer cada 3 horas, los anteriores cada 30 días, y un acta completa no se vuelve a pedir. Se detallan hasta 40 votaciones por expediente (las en general, siempre); las demás figuran solo con su resultado. Los datos abiertos del Senado no publican votaciones, por eso se leen estas páginas.

## Cómo se buscan las reuniones

La ficha del expediente no lista las reuniones, así que el programa:

1. toma las comisiones a las que fue girado el expediente;
2. recorre la lista de reuniones publicadas por cada una (más nuevas primero) hasta pasar la fecha de ingreso del expediente;
3. abre cada nota de reunión de ese período y busca el expediente en el temario, por el enlace a su ficha o por el número escrito (`S-1234/24`, `C.D. 14/24`, `1234-S-2024`…);
4. de cada reunión toma la versión taquigráfica, el video y los demás archivos adjuntos.

Puede tardar entre medio minuto y un par de minutos según cuántas reuniones haya en el período; las consultas siguientes son mucho más rápidas porque las notas quedan guardadas en caché.

**Límites a tener en cuenta**

- Solo aparecen las reuniones publicadas en las páginas de las comisiones del giro. Una reunión que no se publicó, o una nota que menciona el expediente de forma abreviada (por ejemplo, una lista "S-285, 637 y 638/24"), puede no detectarse.
- Las reuniones de asesores se incluyen o no según la opción elegida, y se marcan como tales.
- La situación se deduce de los datos de la ficha, y la caducidad estimada es **orientativa**: antes de usarla en un trámite oficial, verificala con la Dirección de Mesa de Entradas.

## Si algo no funciona

- **"No se pudo conectar con el sitio"**: revisá la conexión o probá más tarde; el sitio del Senado a veces responde lento.
- **"No se encontró el expediente"**: revisá número, año y origen, o elegí el tipo a mano.
- **Una sección del informe aparece vacía o rara**: el sitio pudo haber cambiado. Activá *Herramientas → Guardar las páginas descargadas*, repetí la consulta y enviá la carpeta que se abre con *Herramientas → Abrir carpeta de diagnóstico* a quien mantiene el programa.
- **Datos viejos**: *Herramientas → Vaciar caché*. La ficha se vuelve a consultar siempre que pasan más de 10 minutos; las listas de reuniones, cada 6 horas.

La configuración y la caché se guardan en `%APPDATA%\InformeExpedientes` (Windows) o `~/.informe_expedientes`.

## Línea de comandos

```
python app.py S-351/25 CD-35/23 --salida "C:\Informes"
python app.py PE-107/24 --tipo PL --sin-reuniones --formatos html
python app.py --tema "Salud" --anios 2025-2026
python app.py --palabras "litio, minería" --tipos PL,PC --comision "Minería" --formatos xlsx
python app.py --tema "Educación y universidades" --nombre index --salida informes/educacion
python app.py --seguimiento agregar PE-99/26 S-351/25
python app.py --seguimiento revisar --salida "C:\Informes" --formatos html,md
python app.py --seguimiento listar
python app.py --sesion "Plan de labor.pdf"
python app.py --sesion ultima --formatos html,csv --nombre sesion --salida informes/sesion
python app.py --sesion 29/10/2026 --solo-asuntos
python app.py --help
```

`--sesion` acepta un archivo (`.docx`, `.pdf` o `.txt`), `ultima` (el último plan publicado en el sitio) o la fecha de la sesión o de la reunión; `--solo-asuntos` lista lo que entendió del plan sin consultar fichas y `--con-reuniones` suma las reuniones de comisión. `--seguimiento revisar` deja el resumen de novedades en HTML y Markdown; `--lista-seguimiento archivo.json` usa otra lista en lugar de la de la configuración, y `--sin-reuniones` acelera la revisión.

`--nombre` fija el nombre del archivo (sin fecha), útil para publicar siempre en la misma dirección.

## Despliegue

### En las PC de la oficina (recomendado)

1. **Compilar una sola vez.** En una PC con Python 3.10 o posterior, doble clic en `construir_exe_windows.bat`. Genera `dist\InformeExpediente.exe`, un solo archivo que incluye todo lo necesario.
2. **Distribuir.** Copiá el `.exe` a una carpeta compartida de la red (por ejemplo `\\servidor\Prosecretaria\InformeExpedientes\`) y creá un acceso directo en el escritorio de cada usuario. No hace falta instalar nada en las PC.
3. **Primera ejecución.** Como el programa no tiene firma digital, Windows puede mostrar «Windows protegió su PC»: *Más información → Ejecutar de todas formas*. Para evitar el aviso, pedí a Sistemas que lo habilite o lo firme con el certificado institucional.
4. **Red.** El programa necesita salir por HTTPS a `www.senado.gob.ar` y `www.hcdn.gob.ar`. Usa la configuración de proxy de Windows; si el proxy pide usuario y contraseña, definí la variable de entorno `HTTPS_PROXY` (por ejemplo `http://usuario:clave@proxy:8080`). Si la red usa un proxy con autenticación integrada de Windows, pedí a Sistemas que habilite esos dos sitios.
5. **Actualizar.** Reemplazá el `.exe` de la carpeta compartida. La configuración, los ejes y la caché de cada usuario quedan en `%APPDATA%\InformeExpedientes` y no se pierden.

### Publicación automática en GitHub Pages

Para tener informes temáticos siempre actualizados en un sitio del equipo, el archivo `despliegue/informe-tematico.yml` es un flujo de GitHub Actions que, de lunes a viernes a las 8:00, corre el programa por línea de comandos para los ejes elegidos y publica el HTML y el Excel con nombre fijo (`informes/<eje>/index.html`). Las instrucciones están al comienzo del archivo.

No se puede publicar el programa como una página web que consulte al Senado desde el navegador: los navegadores no dejan que una página de otro dominio lea `senado.gob.ar`. Por eso la consulta corre en la PC o en GitHub Actions, y lo que se publica es el informe ya armado.

Lo que se publica en GitHub Pages es público. Los datos ya lo son, pero conviene acordarlo con la Prosecretaría antes de sumarlo al sitio institucional.

### Seguimiento diario con un issue en GitHub

`despliegue/seguimiento.yml` es un flujo de GitHub Actions que, de lunes a viernes a las 8:00 de Buenos Aires, revisa una lista guardada en el repositorio (`seguimiento/lista.json`), vuelve a guardar en ese archivo la foto de cada expediente y abre un issue nuevo con el resumen de novedades en Markdown. Las instrucciones están al comienzo del archivo; con `SOLO_CON_NOVEDADES: "si"` el issue se abre solo cuando hay novedades.

### En un servidor interno (más adelante)

Si se quisiera usar desde el navegador sin instalar nada, el mismo paquete puede servirse con una pequeña aplicación web (por ejemplo Flask) en un servidor de la Casa con salida a internet. La lógica (`servicio.generar` y `tematico.generar_tematico`) ya está separada de la ventana, así que alcanza con agregar las pantallas web.

## Para quien mantiene el programa

| Módulo | Qué hace |
|---|---|
| `identificador.py` | Interpreta el número de expediente en sus distintas formas. |
| `cliente.py` | Pedidos al sitio: reintentos, pausa entre pedidos, caché en disco, cancelación y diagnóstico. |
| `ficha.py` | Lee la ficha (`verExp`) y resuelve el tipo con la búsqueda avanzada del sitio. |
| `comisiones.py` | Listados de reuniones por comisión, análisis de cada nota y agenda. |
| `situacion.py` | Situación, pasos del trámite y caducidad. |
| `busqueda.py`, `ejes.py` | Búsqueda por palabras y filtros; ejes temáticos. |
| `tematico.py`, `informe_tematico.py` | Informe temático y su escritura en Word, HTML y Excel. |
| `votaciones.py` | Listado anual de votaciones, detalle y PDF de cada acta, artículos en rangos, sesiones y el índice guardado. |
| `hcdn.py` | El proyecto en el sitio de Diputados: número, giros, dictámenes y trámite de las dos cámaras. |
| `tramite.py` | Recorrido del proyecto de ley según la Constitución (arts. 77 a 84), con la ficha, Diputados y las actas. |
| `seguimiento.py` | Lista de seguimiento, foto del estado, comparación y resumen de novedades (HTML y Markdown). |
| `plan_labor.py` | Lectura del plan de labor (Word, PDF, texto o sitio) y sus asuntos en el orden de tratamiento. |
| `sesion.py`, `informe_sesion.py` | Informe de sesión: expedientes de cada asunto y escritura en Word, HTML, Excel y CSV. |
| `numeros.py` | Cantidades en letras («VEINTIÚN (21)»). |
| `contenido.py`, `informe_docx.py`, `informe_html.py` | Contenido y escritura de los informes. |
| `servicio.py` | Encadena todo; es lo que usan la ventana (`gui.py`) y la línea de comandos (`app.py`). |

Las tablas de la ficha se reconocen por su atributo `summary` y, si falta, por los títulos de sus columnas; cada sección se lee por separado, así que un cambio en el sitio afecta solo esa parte y se informa como aviso. Si el sitio cambia, lo más probable es tener que ajustar `ficha.py` o `comisiones.py`: guardá las páginas con el modo diagnóstico, agregalas a `tests/fixtures` y corregí hasta que pasen las pruebas.

En `docs/relevamiento-fase0.md` está relevado qué publican el sitio del Senado y el de Diputados sobre votaciones nominales, el plan de labor, los proyectos en revisión en Diputados y la búsqueda por autor y bloque, con las páginas reales guardadas en `tests/fixtures` (las que empiezan con `acta_`, `votaciones_`, `plenario_`, `plan_labor_`, `hcdn_`, `senadores_` y `avanzada_autor_`).

Pruebas: `pip install pytest` y luego `python -m pytest`. Usan páginas de prueba que reproducen la estructura real del sitio, sin conexión a internet.

Direcciones que usa: `parlamentario/comisiones/verExp/{número}.{año}/{origen}/{tipo}` (ficha), `parlamentario/parlamentaria/avanzada` (búsqueda) y `micrositios/DatosAbiertosExpedientes/BusquedaAvanzada/XLS` (su exportación completa), `parlamentario/comisiones/info/{id}` y `?Reuniones=N` (reuniones), `micrositios/nota/{id}/noticias` (nota de cada reunión), `parlamentario/comisiones/agenda/{id}` (agenda) `parlamentario/parlamentaria/ordenDelDiaResultadoLink/{año}/{número}` (órdenes del día), `votaciones/actas` (listado anual; otros años por POST con `busqueda_actas[anio]`), `votaciones/detalleActa/{id}` y `votaciones/verActaVotacion/{id}` (detalle y PDF de cada acta) y `parlamentario/parlamentaria/actas` (Plenario de Labor Parlamentaria, con el PDF de cada plan; los nombres de archivo no siguen un patrón, por eso se usa el enlace de la tabla). En Diputados, la búsqueda `proyectos/resultado.html?strNumExp={número}&strNumExpOrig={origen}&strNumExpAnio={año}` (con `strMostrarTramites=on` y las demás opciones para que traiga el trámite), que sirve también como enlace (la dirección `proyecto.jsp` ya no existe). Se busca por el número del Senado; la respuesta puede traer otros proyectos con el mismo número, y se toma el que tiene ese «Expediente Senado».

Los PDF de actas se leen con `pypdf`, incluida en `requirements.txt`; sin ella, las votaciones de sesiones recientes figuran solo con su resultado.
