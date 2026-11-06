<p align="center">
  <img src="docs/img/banner.svg" alt="Sistema de Información Parlamentaria — H. Senado de la Nación" width="100%">
</p>

<p align="center">
  <a href="https://github.com/GaronTom2020/App-para-el-senado-V.0.1-/releases/latest"><img alt="Versión" src="https://img.shields.io/github/v/release/GaronTom2020/App-para-el-senado-V.0.1-?label=versi%C3%B3n&color=1A64AB&style=flat-square"></a>
  <a href="https://github.com/GaronTom2020/App-para-el-senado-V.0.1-/releases/tag/manual"><img alt="Manual de usuario" src="https://img.shields.io/badge/manual-PDF-27AAE1?style=flat-square"></a>
  <img alt="Windows" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0B3D7C?style=flat-square">
  <img alt="Python" src="https://img.shields.io/badge/Python-3-114E9A?style=flat-square">
  <img alt="Fuentes públicas" src="https://img.shields.io/badge/fuentes-senado.gob.ar%20%C2%B7%20hcdn.gob.ar-5A6478?style=flat-square">
</p>

<p align="center">
  <b><a href="https://github.com/GaronTom2020/App-para-el-senado-V.0.1-/releases/latest">⬇️ Descargar el programa</a></b>
  &nbsp;·&nbsp;
  <b><a href="https://github.com/GaronTom2020/App-para-el-senado-V.0.1-/releases/tag/manual">📘 Manual de usuario</a></b>
  &nbsp;·&nbsp;
  <b><a href="#si-algo-no-funciona">🛟 Si algo no funciona</a></b>
</p>

# Sistema de Información Parlamentaria — H. Senado de la Nación

Versión actual: **1.2.0**. Programa de escritorio con cinco modos:

| | Modo | Qué hace |
|:-:|---|---|
| 📄 | **Un expediente** | A partir de su número, arma un informe en Word y HTML con su situación en el trámite parlamentario, las reuniones de comisión en que se trató y los enlaces a cada fuente. |
| 🔎 | **Por tema** | A partir de un eje temático o de palabras clave, encuentra todos los expedientes que responden a ese tema y arma un informe consolidado en Word, HTML y Excel con la etapa de cada uno. |
| 👁️ | **Seguimiento** | Una lista de expedientes que se revisa seguido para avisar qué cambió. |
| 🏛️ | **Sesión** | A partir del plan de labor parlamentaria, un único informe con cada asunto en el orden de tratamiento y la ficha de sus expedientes, más un CSV para el tablero de sesiones. También arma el informe de una orden del día («OD 366/26») y lee la versión taquigráfica de la sesión. |
| 📥 | **Asuntos entrados** | Lee el Diario de Asuntos Entrados (DAE) digital del Senado desde una fecha de partida y después solo lo nuevo, con filtros por tipo, origen y palabras. Suma, si se pide, lo que entró y todavía no figura en un DAE (como las copias de cortesía) y los Oficiales Varios y Particulares. |

Usa solamente información pública de www.senado.gob.ar y www.hcdn.gob.ar.

**Contenido:** 📰 [Novedades](#novedades-de-la-versión-11) · 🗂️ [Historial de versiones](#historial-de-versiones) · 📋 [Qué incluye el informe](#qué-incluye-el-informe) · 💾 [Instalación](#instalación) · ▶️ [Uso](#uso) · 🔎 [Por tema](#informe-temático-por-eje-o-palabras-clave) · 🏛️ [Sesión](#informe-de-sesión-plan-de-labor) · 📥 [Asuntos entrados](#asuntos-entrados-dae) · ✉️ [Resumen diario](#resumen-diario-correo-y-aviso-en-pantalla) · 👁️ [Seguimiento](#lista-de-seguimiento) · 🛟 [Si algo no funciona](#si-algo-no-funciona) · ⌨️ [Línea de comandos](#línea-de-comandos) · 🚀 [Despliegue](#despliegue)

### Novedades de la versión 1.2

- **Asuntos entrados sin DAE**: con la casilla *Sumar → Sin DAE*, también aparecen los expedientes que ya entraron por Mesa de Entradas pero todavía no figuran en un Diario de Asuntos Entrados, o no figuran nunca, como las copias de cortesía de mensajes ingresados por Diputados (por ejemplo, el PE-361/26). Se marcan con DAE «Sin asignar».
- **Oficiales Varios y Particulares**: con la casilla *Sumar → Oficiales Varios y Particulares*, se agregan esos dos orígenes, que no salen en los DAE.
- **Casillas ☐ en la lista de resultados** de *Asuntos entrados* y *Por tema*, como en *Seguimiento*: se marcan varios expedientes y el clic derecho actúa sobre ellos.
- **Fecha y giro en columnas separadas** en la lista de asuntos entrados.
- **PDF con Edge 156**: los informes en PDF vuelven a generarse con la versión actual de Edge.

### Novedades de la versión 1.1

- **Vencimientos** (*Seguimiento → Informes → Vencimientos*): los expedientes de la lista ordenados por fecha de caducidad; en rojo los que caducan en menos de 60 días y, además en negrita, los de menos de 15.
- **Agenda de la semana** (*Seguimiento → Informes → Agenda de la semana*): las reuniones de comisión ya convocadas en los próximos siete días que tratan expedientes de la lista, día por día. Las dos vistas salen de la última revisión, sin consultar el sitio.
- **Interfaz más limpia**: el botón principal de cada pestaña dice «Cancelar» mientras trabaja; los formatos se eligen en un solo lugar (*Herramientas → Formatos de los informes…*, o *Formatos: … · cambiar* debajo de cada botón); en *Seguimiento*, los menús *Grupos*, *Acciones* e *Informes*; *Tipo* y *Comentario* en *Más opciones*; ayudas al pasar el mouse.
- **Manual al día** con las capturas de esta ventana, que GitHub vuelve a tomar solo cuando cambia el programa.
- **Números de versión** con el esquema lanzamiento.función.parche (ver el [historial](#historial-de-versiones)).

### Novedades de la versión 1.0

Primera versión estable, con actualizaciones más seguras y controles para que el programa siga funcionando cuando cambian los sitios:

- **Actualizaciones verificadas**: el programa comprueba que la versión nueva descargada esté completa y sea idéntica a la publicada antes de instalarla, muestra qué cambia y, si anda mal, permite volver a la anterior (*Ayuda → Volver a la versión anterior*).
- **Cuenta de envío fuera del .exe**: la contraseña del correo de la oficina se lee de `cuenta_envio.txt`, junto al `.exe`.
- **Control diario de los sitios**: los días hábiles, GitHub consulta el Senado y Diputados con casos conocidos y avisa con un issue si alguno dejó de leerse.

Lo anterior, versión por versión, está en el historial.

<p align="center"><img src="docs/img/separador.svg" width="70%" alt=""></p>

## Historial de versiones

Cada versión tiene tres números, **V.lanzamiento.función.parche**:

| Número | Sube cuando… | Ejemplo |
|---|---|---|
| **Lanzamiento** | se lanza una etapa nueva del programa (0 = antes del lanzamiento, 1 = primer lanzamiento). Los otros dos vuelven a 0. | 0.4.12 → **1**.0.0 |
| **Función** | se agrega algo que el usuario puede hacer y antes no podía. El parche vuelve a 0. | 1.0.0 → 1.**1**.0 |
| **Parche** | se une cualquier otro cambio: un arreglo, una mejora interna, documentación o una actualización de componentes. | 1.1.0 → 1.1.**1** |

Cada cambio entra al programa por un *pull request* (PR) en GitHub: un pedido de cambio que se revisa, pasa las pruebas automáticas y se une a la rama principal. Cada PR unido suma un número. La tabla los ordena así; las versiones de antes de 1.1.3 se publicaron con otro número (columna «Publicada como»).

| Versión | Tipo | PR | Qué cambió | Publicada como |
|---|---|---|---|---|
| 0.1.0 | Lanzamiento inicial | — | Primer código del programa | |
| 0.2.0 | Función | #1 | Votaciones, seguimiento, informe de sesión, Diputados como cámara revisora, búsqueda por autor y bloque, relacionados | |
| 0.3.0 | Función | #2 | Órdenes del día, seguimiento con grupos, versión taquigráfica, asuntos entrados, interfaz nueva | |
| 0.3.1 | Parche | #3 | README: novedades de la 0.3.0 | |
| 0.3.2 | Parche | #4 | Manual de usuario en PDF, compilado en GitHub | |
| 0.3.3 | Parche | #5 | Manual: otra forma de tomar las capturas | |
| 0.4.0 | Función | #6 | PDF, exportar el seguimiento, resumen diario por correo, aviso de versión nueva | |
| 0.4.1 | Parche | #7 | Arreglo de la compilación del .exe | |
| 0.4.2 | Parche | #8 | Correo enviado desde la cuenta de Gmail de la oficina | |
| 0.4.3 | Parche | #9 | Limpieza: sacar `desktop.ini` | |
| 0.4.4 | Parche | #10 | README con los colores del Senado | |
| 0.4.5 | Parche | #11 | README: instalación y despliegue | |
| 0.4.6 | Parche | #12 | Seguridad: cómo reportar vulnerabilidades (`SECURITY.md`) | |
| 0.4.7 | Parche | #13 | Seguridad: la contraseña del correo ya no va dentro del .exe | |
| 0.4.8 | Parche | #14 | Actualizaciones: no instalar una descarga incompleta | |
| 0.4.9 | Parche | #15 | Actualizaciones más seguras; elegir a mano el archivo de la cuenta | |
| 0.4.10 | Parche | #16 | Seguridad: huella de las descargas, pruebas en cada PR, Dependabot | |
| 0.4.11 | Parche | #18 | Componente actualizado: xlrd 2.0.2 | |
| 0.4.12 | Parche | #17 | Componentes de GitHub Actions actualizados | 0.4.0.8 |
| 0.5.0 | Función | #19 | Control diario de los sitios, lista de cambios al actualizar, volver a la versión anterior | |
| 0.5.1 | Parche | #20 | Actualizaciones: reemplazo confiable del .exe | |
| **1.0.0** | **Lanzamiento** | #21 | **Primera versión estable** | 1.0.0.9 |
| 1.1.0 | Función | #22 | Vencimientos, agenda de la semana, interfaz más limpia | 1.1.0.10 |
| 1.1.1 | Parche | #23 | Manual: capturas de la versión 1.1 | 1.1.0.11 |
| 1.1.2 | Parche | #24 | Manual: GitHub toma las capturas solo | |
| 1.1.3 | Parche | #25 | Numeración lanzamiento.función.parche; limpieza del manual | 1.1.3 |
| 1.1.4 | Parche | #26 | README más corto y con separadores; el manual se arma con capturas tomadas en GitHub | 1.1.4 |
| 1.2.0 | Función | #27 | Asuntos entrados sin DAE (copias de cortesía), Oficiales Varios y Particulares, casillas en los resultados; PDF con Edge 156 | 1.2.0 |

Desde la 1.1.3, la versión publicada es exactamente la de la tabla.

<p align="center"><img src="docs/img/separador.svg" width="70%" alt=""></p>

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
- **Expedientes relacionados**: los dictaminados o tratados en conjunto y los que se tuvieron a la vista, con su enlace, la relación («Dictaminado en conjunto (Orden del Día N° 366/26)», «Tenido a la vista en el dictamen (Orden del Día N° 146/24)», «Citado en las observaciones de la ficha») y su situación resumida. Salen de los otros expedientes de cada orden del día, del texto del dictamen (PDF: «han considerado…», «teniendo a la vista…»), de las observaciones y notas de la ficha («DICT. CONJ. S. 808/26, 865/26», «aprobado conjuntamente con el P.E. 186/25»), del trámite en el sitio de Diputados y del temario de las reuniones de comisión en que se trató, si es breve (hasta ocho expedientes: «tratado en la misma reunión»). Se lee la ficha de los primeros quince para su situación. En el informe de sesión y en el seguimiento no se buscan, para no alargar la consulta.
- **Votaciones en el recinto**: una línea por sesión. La votación en general con su resultado («aprobado (42 a 21)»); en particular, solo los artículos rechazados o modificados, en rangos («se rechazaron los arts. 23-24»), o «aprobado sin observaciones»; y las insistencias (art. 83), con si alcanzaron los dos tercios. Las mociones, preferencias y habilitaciones sobre tablas no se incluyen. Si el Senado aprobó con modificaciones y las actas no dicen qué artículos, se aclara y se enlaza el texto aprobado. Si el detalle del acta y su PDF dan totales distintos, se avisa. Si hay una votación más reciente que lo que registra la ficha, la situación lo dice («Votado en el recinto el 29/10/2026 (42 a 21); la ficha oficial todavía no registra la sanción») y la línea de pasos marca la sanción del Senado como hecha.
- Sanción, número de ley, resolución del Poder Ejecutivo (veto o promulgación, decreto y Boletín Oficial), observaciones de la ficha y notas propias.

## Manual de usuario

El manual para el uso diario, paso a paso y con capturas de cada pestaña, se compila en PDF a partir de `manual/contenido.md`, de las secciones vigentes de este README (lo que incluye el informe, las novedades, «Si algo no funciona» y la línea de comandos) y de capturas nuevas del programa. El workflow `.github/workflows/manual.yml` lo vuelve a armar cada vez que cambian el README, el manual o el programa en `main`, con capturas tomadas en GitHub (no hace falta tomarlas a mano ni subirlas), y lo publica en *Releases → Manual de usuario*. Para compilarlo en la PC:

```
python -m pip install markdown pymupdf playwright pytest pillow
python -m playwright install chromium
python manual/capturar.py
python manual/construir_manual.py
```

Deja `manual/salida/Manual de usuario.pdf` (y una copia en HTML). Para cambiar el texto, editá `manual/contenido.md`: al comienzo del archivo están las convenciones para notas al margen, recuadros, figuras y secciones tomadas del README.

<p align="center"><img src="docs/img/separador.svg" width="70%" alt=""></p>

## Instalación

> [!TIP]
> **Opción A, con el ejecutable (recomendada para la oficina).** Descargá `InformeExpediente.exe` de la última versión en [Releases](https://github.com/GaronTom2020/App-para-el-senado-V.0.1-/releases/latest) y abrilo: no necesita Python ni instalación. Desde ahí, el programa avisa solo cuando hay una versión nueva y ofrece instalarla.

El `.exe` se compila en GitHub: *Actions → Compilar InformeExpediente.exe → Run workflow* (`.github/workflows/main.yml`). Corre las pruebas en una máquina Windows, compila y publica la versión que figura en `informe_expedientes/__init__.py` (por ejemplo `v1.1.4`) en Releases, con la lista de cambios desde la anterior. Las versiones siguen el esquema lanzamiento.función.parche: cada PR sube su número (una función nueva, el del medio; un arreglo, el último). Si la versión ya está publicada, la compilación se detiene y pide subir el número. El `.exe` no lleva la cuenta de envío del resumen diario: se lee de `cuenta_envio.txt`, junto al `.exe` (ver [Resumen diario](#resumen-diario-correo-y-aviso-en-pantalla)). Para compilarlo en una PC con Python 3.10 o posterior (marcando **Add python.exe to PATH** al instalarlo; el «python» que ofrece la Microsoft Store no sirve), está `construir_exe_windows.bat`, que genera `dist\InformeExpediente.exe`; lo mismo vale para la cuenta de envío.

Si el antivirus o Sistemas bloquean el `.exe`, pedí que lo autoricen: es un programa sin firma digital.

El `.exe` y la ventana usan el hemiciclo del logo del Senado (`informe_expedientes/recursos/icono.ico`, con tamaños de 16 a 256 píxeles). Para cambiarlo, reemplazá ese archivo por otro `.ico` y volvé a compilar.

**Opción B, desde el código.** Con Python 3.10 o posterior (al instalarlo, marcar *Add python.exe to PATH*), hacer doble clic en `iniciar.bat`. La primera vez instala las dependencias en una carpeta `.venv`; las siguientes abre directamente la ventana.

En Linux o macOS: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python app.py`.

## Uso

1. Escribí uno o más expedientes, uno por línea: `S-1234/24`, `CD-14/24`, `PE-107/24`, `1370-S-2020` o el enlace a la ficha del Senado.
2. Elegí qué buscar y presioná **Generar informe** (o Ctrl+Enter). El formato se cambia con *Formatos: … · cambiar*, debajo del botón; el tipo, en *Más opciones* (por defecto, *Detectar automáticamente*: el programa lo consulta en el buscador del Senado).
3. Al terminar, el resumen aparece en la ventana con los enlaces activos. Los botones de abajo abren el Word, el HTML o la carpeta de informes.

En la pestaña *Reuniones*, el doble clic abre la nota de la reunión y el clic derecho ofrece la versión taquigráfica, el video o copiar el enlace.

<p align="center"><img src="docs/img/separador.svg" width="70%" alt=""></p>

## Informe temático (por eje o palabras clave)

En la pestaña **Por tema**:

1. Elegí un **eje temático** (completa solo las palabras) o escribí tus propias **palabras clave**, separadas por coma.
2. Indicá si el extracto tiene que tener **alguna** o **todas** las palabras, y si querés **excluir** los que mencionen otras (por ejemplo, el eje «Consumo» excluye «consumo problemático»).
3. Ajustá los **años** de los expedientes, el **origen**, la **comisión del giro** y los **tipos** (por defecto: ley, resolución y comunicación; las declaraciones quedan afuera porque suelen ser muy numerosas).
4. Si querés, elegí un **senador** (escribí el apellido y elegilo de la lista) o un **bloque**: se toman los proyectos con su firma, como autor o coautor. Se puede combinar con un eje o con palabras clave, o usar solo (todos los proyectos del senador o del bloque en esos años).
5. Elegí qué hacer con cada expediente encontrado: consultar su ficha (para saber su etapa y comisión, recomendado), buscar sus reuniones de comisión (lento) o generar además su informe completo.
6. Presioná **Generar informe temático**. La lista aparece en la pestaña *Expedientes*: doble clic abre la ficha, clic derecho genera el informe completo de ese expediente.

**Cómo busca.** Consulta la búsqueda avanzada del Senado por extracto, una vez por año y por palabra, y descarga la exportación completa de resultados. Sobre eso aplica un filtro propio que no distingue tildes ni mayúsculas y busca el **comienzo** de cada palabra: «universidad» encuentra «universidades», pero «penal» no encuentra «despenalizar». Con «todas», consulta al sitio por la palabra más larga y exige las demás en el extracto.

**Por autor y por bloque.** El buscador del Senado tiene un campo de autor (un número por senador, el mismo de su página en el sitio); con él se hace una consulta por senador y por año y las palabras se filtran después sobre el extracto. La exportación trae también los proyectos que el senador firmó como coautor («MOISES Y OTROS: …»). El bloque se arma con sus integrantes **actuales** (listado «agrupados por bloques» del sitio): un proyecto de alguien que cambió de bloque figura en el bloque de hoy, no en el de la fecha del proyecto, y el informe lo aclara en los criterios. Cada integrante es una consulta por año: un bloque grande en dos años son unas cuarenta consultas antes de abrir las fichas. Los senadores recién incorporados que el buscador todavía no lista se toman del listado de bloques.

**Cuánto tarda.** Hace una consulta por año y por palabra (dos si la palabra lleva tilde, para no perder extractos cargados sin tilde), más una por cada ficha. Un eje de seis palabras en dos años son unas 15 consultas de búsqueda y luego una por expediente encontrado: entre uno y tres minutos. Para períodos largos conviene acotar con comisión o tipo. Se consultan como máximo 200 fichas; el resto figura en el informe sin etapa.

**Qué trae el informe.** Un resumen con las cantidades en forma normativa («Se identificaron VEINTIÚN (21) expedientes… DOCE (12) en comisión…»), la cuenta por etapa, tipo y origen, los criterios usados y la tabla de expedientes agrupada por etapa, con el extracto (las palabras encontradas resaltadas), la situación, la caducidad, la comisión y la fecha de ingreso. El Excel trae una fila por expediente, con filtros y enlaces, y una hoja *Resumen* cuyos totales son fórmulas (`CONTAR.SI`) que se recalculan si filtrás o borrás filas.

**Ejes temáticos.** Vienen doce ejes iniciales (educación, salud, ambiente, seguridad, economía, trabajo, género, niñez, energía, discapacidad, consumo y transferencia de inmuebles). Con **Guardar…**, al lado del eje, guardás las palabras, exclusiones, modo y comisión actuales con un nombre; **Borrar** lo elimina. Se guardan en `ejes.json` dentro de la carpeta de configuración; para que todo el equipo use los mismos, copiá ese archivo en cada PC o pasalo con `--ejes` en la línea de comandos. Formato:

```json
{"ejes": [{"nombre": "Litio", "palabras": ["litio", "minería"], "modo": "alguna",
           "excluir": [], "comision_id": 65}]}
```

`comision_id` es el número de la comisión en el sitio del Senado (`comisiones/info/{número}`); puede ser `null`.

## Informe de sesión (plan de labor)

En la pestaña **Sesión**:

1. Cargá el plan de labor: **Abrir archivo…** (Word `.docx`, PDF o texto), **Buscar en el sitio** (lista los planes publicados en el Plenario de Labor Parlamentaria del Senado; elegí uno y se descarga) o pegá el texto en el cuadro. El texto queda a la vista y se puede corregir.
2. **Ver los asuntos** muestra lo que el programa entendió, en el orden de tratamiento, antes de consultar nada.
3. Presioná **Generar informe de sesión**. Los formatos (Word, HTML, Excel, CSV y PDF) se cambian con *Formatos: … · cambiar*, debajo del botón.

**Qué entiende del plan.** Toma la lista «Se acordó el tratamiento de los siguientes temas» en su orden; después suma las órdenes del día impresas que no estaban en esa lista, las preferencias y los asuntos sobre tablas. Reconoce las órdenes del día en sus formas habituales («OD 409/26 y Anexo», «OD de acuerdos: 338; 353; 354», «OD 340 a 342 y 344 a 352», «OD 22/26 a 27/26 inclusive», incluso «0D 206/26») y los expedientes, también en listas abreviadas («S-285, 637 y 638/24»). Si una orden del día no lleva año, usa el de la sesión. Los asuntos sin número (juras, «Dar cuenta de acuerdos», proyectos sobre tablas nombrados solo por su título) figuran en el índice sin ficha. Si el texto no tiene la estructura del plan (una lista pegada a mano), toma un asunto por renglón.

**Qué trae el informe.** Un resumen («El plan de labor para la sesión del 29/10/2026 acordó NUEVE (9) asuntos…»), el índice de asuntos con su orden del día, sus expedientes y la situación de cada uno, y la ficha completa de cada expediente, la misma del informe individual, con la situación, el contraste con Diputados y las votaciones. De cada orden del día se toman los expedientes que trata (pueden ser varios, en conjunto). Por defecto no se buscan las reuniones de comisión, porque una sesión puede tener decenas de expedientes.

**CSV para el tablero de Power BI.** Una fila por asunto, separado por punto y coma, en UTF-8 con BOM y con fechas dd/mm/aaaa. Columnas: `Fecha de sesión`, `Orden`, `Expediente` (varios, separados por coma), `OD`, `Título` (el del plan o, si no lo trae, el extracto), `Tipo` y `Comisiones` (del giro, separadas por « / », porque algunos nombres llevan coma). Las columnas están en `informe_sesion.COLUMNAS_CSV`.

## Asuntos entrados (DAE)

En la pestaña **Asuntos entrados** se elige una fecha de partida y el programa lee los Diarios de Asuntos Entrados digitales del Senado desde esa fecha; en las consultas siguientes trae solo los nuevos. Si la fecha cae en el período parlamentario anterior (marzo a febrero), sigue la numeración de ambos. Se filtran por tipo, origen y palabras, y cada asunto se puede sumar a la lista de seguimiento. El informe en Word y HTML es opcional.

Algunos asuntos tardan en publicarse en un DAE, o no se publican nunca (por ejemplo, las copias de cortesía que remite la Jefatura de Gabinete). Con **Sumar → Sin DAE**, el programa consulta además la búsqueda avanzada del año: los expedientes del Senado, el Poder Ejecutivo y Diputados con número mayor al último publicado en un DAE se completan con su ficha (fecha de Mesa de Entradas y giros) y se muestran con DAE «Sin asignar». **Sumar → Oficiales Varios y Particulares** agrega esos dos orígenes, que no salen en los DAE: la primera vez se ubica por fecha el primer número posterior a la de partida. Cada asunto sin DAE se informa una sola vez; cuando aparece en un DAE, vuelve a figurar con su número. Lo elegido se recuerda y también lo usa el resumen diario.

<p align="center"><img src="docs/img/separador.svg" width="70%" alt=""></p>

## Resumen diario (correo y aviso en pantalla)

En *Herramientas → Resumen diario (correo y aviso)…* cada usuario elige si quiere recibir, todos los días a una hora, un resumen con las novedades de la lista de seguimiento (de toda la lista o de los grupos que marque) y los asuntos entrados nuevos (con los tipos y las palabras que elija). Puede llegarle por correo, como un aviso en la esquina de la pantalla (con *Ver el resumen*, *Abrir el programa* y *Cerrar*), o de las dos formas. *Enviar una prueba* comprueba que el correo llega.

El correo sale de **una cuenta de Gmail de la oficina, creada solo para esto**. El usuario no inicia sesión ni da contraseñas: solo escribe dónde quiere recibirlo.

**Configurar la cuenta (una vez, quien mantiene el programa).**

1. En la cuenta de Gmail de la oficina, activá la *verificación en dos pasos* y creá una **contraseña de aplicación** en https://myaccount.google.com/apppasswords (16 letras).
2. Junto a `InformeExpediente.exe` (en la carpeta compartida, o en cada PC), creá un archivo `cuenta_envio.txt` con la dirección en el primer renglón y la contraseña de aplicación en el segundo. Para correr desde el código, el mismo archivo junto a `app.py` o la variable de entorno `INFORME_CUENTA_ENVIO` (`cuenta_envio.txt` está en `.gitignore`).

> [!WARNING]
> El `.exe` **no** lleva la cuenta adentro: se publica en Releases, y cualquiera que lo descargue podría sacarla.

**Si cambia la contraseña.** Al cambiar la contraseña de la cuenta, Google borra sus contraseñas de aplicación. Creá una nueva y reemplazala en `cuenta_envio.txt`; no hace falta recompilar.

Cualquiera con acceso a ese archivo podría, con conocimientos técnicos, sacar la contraseña de aplicación: por eso la cuenta tiene que servir solo para esto. Si pasa, se borra esa contraseña de aplicación en Google y se crea otra. Gmail admite unos 500 envíos por día; los primeros correos de una cuenta nueva pueden caer en spam (conviene marcarlos como «No es spam»).

Al guardar se crea la tarea programada de Windows «Informe de Expedientes - resumen diario», que corre `InformeExpediente.exe --resumen-diario` a esa hora. La tarea tiene activada la opción de Windows «ejecutar la tarea lo antes posible si se omitió un inicio programado»: si a esa hora la PC estaba apagada o sin la sesión iniciada, el resumen se arma apenas el usuario entra. Se arma una sola vez por día (`--forzar` lo repite). El último resumen queda en `ultimo_resumen.html`. Lo que pasa en cada envío queda en `correo.log`, en la carpeta de configuración. El correo lleva su propio registro de lo ya avisado (`correo_seguimiento.json` y `correo_asuntos_entrados.json`): la primera vez solo toma el estado de cada expediente.

## Lista de seguimiento

En la pestaña **Seguimiento** se arma una lista de expedientes para revisar seguido. Se agregan escribiendo el número (o varios, separados por coma) o, desde la lista del modo *Por tema*, con clic derecho → *Agregar a la lista de seguimiento*. Para quitarlos, elegilos y usá *Acciones → Quitar de la lista* (o Supr). El botón *Informes* arma el estado de la lista (Excel o PDF), los vencimientos y la agenda de la semana.

**Revisar novedades** vuelve a consultar cada expediente y lo compara con la revisión anterior. Avisa:

- giro nuevo a una comisión y egreso de una comisión;
- dictamen u orden del día nuevos, o cambio de estado de una orden del día;
- votación en el recinto y sanción registrada en la ficha;
- media sanción, sanción, rechazo, pase a la otra cámara, veto o insistencia que registra el sitio de Diputados, y en Diputados el número que le asignó, el giro a sus comisiones y el dictamen;
- reunión convocada con el expediente en el temario y reunión de comisión en que se trató (si se buscan reuniones);
- cambio de situación y caducidad cercana (menos de 60 días).

> [!NOTE]
> La primera revisión de cada expediente solo guarda su estado («Primera revisión»).

El resumen queda en la ventana y en un HTML y un Markdown en la carpeta de informes; *Copiar resumen* copia el Markdown. La lista y la última «foto» de cada expediente se guardan en `seguimiento.json`, en la carpeta de configuración.

<p align="center"><img src="docs/img/separador.svg" width="70%" alt=""></p>

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
- La situación se deduce de los datos de la ficha.

> [!IMPORTANT]
> La caducidad estimada es **orientativa**: antes de usarla en un trámite oficial, verificala con la Dirección de Mesa de Entradas.

<p align="center"><img src="docs/img/separador.svg" width="70%" alt=""></p>

## Si algo no funciona

- **"No se pudo conectar con el sitio"**: revisá la conexión o probá más tarde; el sitio del Senado a veces responde lento.
- **"No se encontró el expediente"**: revisá número, año y origen, o elegí el tipo a mano.
- **Una sección del informe aparece vacía o rara**: el sitio pudo haber cambiado. Activá *Herramientas → Guardar las páginas descargadas*, repetí la consulta y enviá la carpeta que se abre con *Herramientas → Abrir carpeta de diagnóstico* a quien mantiene el programa.
- **Datos viejos**: *Herramientas → Vaciar caché*. La ficha se vuelve a consultar siempre que pasan más de 10 minutos; las listas de reuniones, cada 6 horas.
- **La versión nueva anda mal**: *Ayuda → Volver a la versión anterior* (aparece después de una actualización desde el programa). Esa versión no se vuelve a ofrecer; la próxima que se publique, sí.

Quien mantiene el programa no depende de que le avisen: el workflow *Control de sitios* consulta en vivo, los días hábiles a las 7:00, unos expedientes conocidos en los sitios del Senado y de Diputados (`controles/sitios.py`). Si alguno deja de leerse, abre un issue «Control de sitios: falla», y lo cierra solo cuando vuelve a andar.

La configuración y la caché se guardan en `%APPDATA%\InformeExpedientes` (Windows) o `~/.informe_expedientes`.

## Línea de comandos

```
python app.py S-351/25 CD-35/23 --salida "C:\Informes"
python app.py PE-107/24 --tipo PL --sin-reuniones --formatos html
python app.py --tema "Salud" --anios 2025-2026
python app.py --palabras "litio, minería" --tipos PL,PC --comision "Minería" --formatos xlsx
python app.py --autor "Mendoza" --anios 2026 --tipos PL
python app.py --tema "Salud" --bloque "Justicialista"
python app.py --listar-bloques
python app.py --por-bloque --tipos PL --anios 2026 --formatos html,xlsx --salida informes/bloques
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

<p align="center"><img src="docs/img/separador.svg" width="70%" alt=""></p>

## Despliegue

### En las PC de la oficina (recomendado)

1. **Publicar una versión.** Después de unir los cambios en `main`, ejecutá *Actions → Compilar InformeExpediente.exe → Run workflow*. En unos minutos aparece la versión nueva en Releases.
2. **Primera vez en cada PC.** Descargá el `.exe` de Releases (o copialo de una carpeta compartida, por ejemplo `\\servidor\Prosecretaria\InformeExpedientes\`) y creá un acceso directo en el escritorio. No hace falta instalar nada.
3. **Aviso de Windows.** Como el programa no tiene firma digital, Windows puede mostrar «Windows protegió su PC»: *Más información → Ejecutar de todas formas*. Para evitar el aviso, pedí a Sistemas que lo habilite o lo firme con el certificado institucional.
4. **Red.** El programa necesita salir por HTTPS a `www.senado.gob.ar`, `www.hcdn.gob.ar`, `api.github.com` y `github.com` (para las actualizaciones) y, si se usa el resumen por correo, a `smtp.gmail.com` (puerto 587). Usa la configuración de proxy de Windows; si el proxy pide usuario y contraseña, definí la variable de entorno `HTTPS_PROXY` (por ejemplo `http://usuario:clave@proxy:8080`). Si la red usa un proxy con autenticación integrada de Windows, pedí a Sistemas que habilite esos sitios.
5. **Actualizar.** No hace falta repartir el `.exe` de nuevo: al abrir (una vez por día) o desde *Ayuda → Buscar actualizaciones*, cada PC ofrece instalar la versión nueva. Si se usa desde una carpeta compartida, alcanza con reemplazar ese `.exe`. La configuración, los ejes y la caché de cada usuario quedan en `%APPDATA%\InformeExpedientes` y no se pierden.

### Flujos opcionales (no activos)

En `despliegue/` hay flujos de GitHub Actions listos para copiar a `.github/workflows/`, con las instrucciones al comienzo de cada archivo: `informe-tematico.yml` publica en GitHub Pages informes temáticos y por bloque actualizados todos los días hábiles (lo publicado es público: conviene acordarlo con la Prosecretaría), y `seguimiento.yml` revisa una lista guardada en el repositorio y abre un issue con las novedades. `compilar-exe-windows.yml` es la versión del compilador para otro repositorio. No se puede publicar el programa como página web que consulte al Senado desde el navegador: el navegador no deja leer `senado.gob.ar` desde otro dominio.

<p align="center"><img src="docs/img/separador.svg" width="70%" alt=""></p>

## Para quien mantiene el programa

| Módulo | Qué hace |
|---|---|
| `identificador.py` | Interpreta el número de expediente en sus distintas formas. |
| `cliente.py` | Pedidos al sitio: reintentos, pausa entre pedidos, caché en disco, cancelación y diagnóstico. |
| `ficha.py` | Lee la ficha (`verExp`) y resuelve el tipo con la búsqueda avanzada del sitio. |
| `comisiones.py` | Listados de reuniones por comisión, análisis de cada nota y agenda. |
| `situacion.py` | Situación, pasos del trámite y caducidad. |
| `busqueda.py`, `ejes.py` | Búsqueda por palabras, autor y filtros; ejes temáticos. |
| `senadores.py` | Autores (selector del buscador) y bloques actuales con sus integrantes. |
| `relacionados.py` | Expedientes tratados en conjunto o tenidos a la vista (OD, dictamen, ficha, Diputados, temarios). |
| `tematico.py`, `informe_tematico.py` | Informe temático y su escritura en Word, HTML y Excel. |
| `votaciones.py` | Listado anual de votaciones, detalle y PDF de cada acta, artículos en rangos, sesiones y el índice guardado. |
| `hcdn.py` | El proyecto en el sitio de Diputados: número, giros, dictámenes y trámite de las dos cámaras. |
| `tramite.py` | Recorrido del proyecto de ley según la Constitución (arts. 77 a 84), con la ficha, Diputados y las actas. |
| `seguimiento.py` | Lista de seguimiento, foto del estado, comparación y resumen de novedades (HTML y Markdown). |
| `plan_labor.py` | Lectura del plan de labor (Word, PDF, texto o sitio) y sus asuntos en el orden de tratamiento. |
| `sesion.py`, `informe_sesion.py` | Informe de sesión: expedientes de cada asunto y escritura en Word, HTML, Excel y CSV. |
| `asuntos_entrados.py`, `informe_asuntos.py` | Diario de Asuntos Entrados (DAE): lectura, registro de lo ya visto e informe. |
| `orden_dia.py` | Búsqueda por orden del día y sus expedientes. |
| `taquigrafica.py` | Versión taquigráfica de una sesión: qué se votó y las modificaciones aprobadas. |
| `correo.py` | Resumen diario: armado, envío por Gmail, aviso en pantalla y tarea programada de Windows. |
| `actualizaciones.py` | Versiones nuevas y manual en GitHub Releases; descarga y reemplazo del `.exe`. |
| `pdf.py` | Informes en PDF, imprimiendo el HTML con Edge o Chrome. |
| `config.py`, `modelos.py`, `paginas.py`, `util.py` | Direcciones y códigos, estructuras de datos y ayudas comunes. |
| `numeros.py` | Cantidades en letras («VEINTIÚN (21)»). |
| `contenido.py`, `informe_docx.py`, `informe_html.py` | Contenido y escritura de los informes. |
| `servicio.py` | Encadena todo; es lo que usan la ventana (`gui.py`) y la línea de comandos (`app.py`). |

Las tablas de la ficha se reconocen por su atributo `summary` y, si falta, por los títulos de sus columnas; cada sección se lee por separado, así que un cambio en el sitio afecta solo esa parte y se informa como aviso. Si el sitio cambia, lo más probable es tener que ajustar `ficha.py` o `comisiones.py`: guardá las páginas con el modo diagnóstico, agregalas a `tests/fixtures` y corregí hasta que pasen las pruebas.

En `docs/relevamiento-fase0.md` está relevado qué publican el sitio del Senado y el de Diputados sobre votaciones nominales, el plan de labor, los proyectos en revisión en Diputados y la búsqueda por autor y bloque, con las páginas reales guardadas en `tests/fixtures` (las que empiezan con `acta_`, `votaciones_`, `plenario_`, `plan_labor_`, `hcdn_`, `senadores_` y `avanzada_autor_`).

Pruebas: `pip install pytest` y luego `python -m pytest`. No usan internet: trabajan con páginas reales del Senado y de Diputados guardadas en `tests/fixtures` (bajadas entre el 30 y el 31/10/2026; de las HTML se quitaron scripts y estilos, y de algunos PDF largos se dejaron las primeras páginas) y con algunas páginas armadas para casos puntuales.

Direcciones que usa: `parlamentario/comisiones/verExp/{número}.{año}/{origen}/{tipo}` (ficha), `parlamentario/parlamentaria/avanzada` (búsqueda) y `micrositios/DatosAbiertosExpedientes/BusquedaAvanzada/XLS` (su exportación completa), `parlamentario/comisiones/info/{id}` y `?Reuniones=N` (reuniones), `micrositios/nota/{id}/noticias` (nota de cada reunión), `parlamentario/comisiones/agenda/{id}` (agenda) `parlamentario/parlamentaria/ordenDelDiaResultadoLink/{año}/{número}` (órdenes del día), `votaciones/actas` (listado anual; otros años por POST con `busqueda_actas[anio]`), `votaciones/detalleActa/{id}` y `votaciones/verActaVotacion/{id}` (detalle y PDF de cada acta), `senadores/listados/agrupados-por-bloques` (bloques actuales) y `parlamentario/parlamentaria/actas` (Plenario de Labor Parlamentaria, con el PDF de cada plan; los nombres de archivo no siguen un patrón, por eso se usa el enlace de la tabla). En Diputados, la búsqueda `proyectos/resultado.html?strNumExp={número}&strNumExpOrig={origen}&strNumExpAnio={año}` (con `strMostrarTramites=on` y las demás opciones para que traiga el trámite), que sirve también como enlace (la dirección `proyecto.jsp` ya no existe). Se busca por el número del Senado; la respuesta puede traer otros proyectos con el mismo número, y se toma el que tiene ese «Expediente Senado».

Los PDF de actas se leen con `pypdf`, incluida en `requirements.txt`; sin ella, las votaciones de sesiones recientes figuran solo con su resultado.

<p align="center"><img src="docs/img/separador.svg" width="70%" alt=""></p>

<p align="center"><sub>🏛️ Hecho para el H. Senado de la Nación · solo usa información pública de <a href="https://www.senado.gob.ar">senado.gob.ar</a> y <a href="https://www.hcdn.gob.ar">hcdn.gob.ar</a></sub></p>
