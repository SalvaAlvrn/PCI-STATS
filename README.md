# PCI-STATS — Dashboard de supervisiones

Genera un dashboard HTML interactivo y autocontenido a partir del Google Sheet
en vivo (o, para desarrollo local, de un export `.xlsx`).

## Ver el dashboard

<https://salvaalvrn.github.io/PCI-STATS/>

El enlace es fijo. Se comparte una vez y no cambia.

## Actualizar los datos publicados

Configuración única, la primera vez: **Settings → Pages → Source =
"GitHub Actions"**. Sin esto el workflow se ejecuta pero no tiene dónde
publicar.

El workflow se ejecuta solo **cada hora**, así que el dashboard se pone al día
con el Sheet sin que nadie toque nada. Para forzar una publicación inmediata:
pestaña **Actions** → **Publicar dashboard** → **Run workflow**.

Dos detalles del horario automático: GitHub retrasa el cron unos minutos cuando
sus runners tienen cola, y desactiva las ejecuciones programadas tras 60 días sin
actividad en el repositorio (avisa por correo antes). Un commit cualquiera, o
pulsar el botón, reinicia esa cuenta.

El workflow lee el Google Sheet en vivo, corre las pruebas, construye y publica.
Tarda un par de minutos. Si algo falla —el Sheet cambió de forma, una prueba se
rompió— el workflow se detiene y **no publica**: la URL sigue mostrando la última
versión buena. Es deliberado: el dashboard prefiere estar desactualizado a
mostrar cifras equivocadas.

## Los dos apartados de IAAS

El dashboard tiene dos pestañas de IAAS, con fuentes distintas que fallan por
separado. Conviven a propósito mientras el equipo termina de pasarse al sistema
nuevo: si una fuente se cae, su pestaña muestra el motivo y la otra se sigue
publicando.

| Pestaña | Fuente | Mide |
|---|---|---|
| Investigación de IAAS | Formularios de KoboToolbox | Producción declarada de PCI y casos confirmados por área |
| Vigilancia de IAAS | Libro «Sistema IAAS» v6.5 en Google Sheets | El caso epidemiológico completo |

## El apartado de investigación de IAAS

La pestaña "Investigación de IAAS" se alimenta del formulario de KoboToolbox
`aefXsYwJo5RsrZYfaCEcva` en `kf.kobotoolbox.org`, y abre con los casos
confirmados del formulario `ab9ihfUpzVx7UXnTJUvygP` ("Seguimiento Pacientes con
IAAS"). Ambos se leen en cada ejecución del workflow.

Necesita el secret **`KOBO_TOKEN`** (Settings → Secrets and variables →
Actions) con un token de la API de Kobo. Sin él, o si Kobo no responde, el
dashboard **se publica igual**: la pestaña muestra el motivo y la hora del
intento, y el run queda marcado con un aviso en Actions.

El apartado mide **producción, no cumplimiento**: cuántos registros declaran
cada actividad, por quién, en qué servicio y en qué mes. Destaca las tres
actividades principales —casos nuevos investigados, casos en seguimiento y
cierre de casos— con un KPI cada una; las otras tres se monitorean en su propia
tarjeta, al final. Las respuestas SI/NO de cada actividad se leen en Kobo pero
**no se publican**: un `NO` nuevo en el formulario no aparecerá en ninguna parte
del dashboard.

Del formulario de producción solo se publican fecha, responsable, servicio y
actividades declaradas; del de casos, fecha de notificación, unidad y
subservicio. Nombre, expediente, diagnóstico, conclusiones y observaciones no
salen del proceso de construcción: `kobo.py` los descarta con una lista blanca,
y una prueba comprueba que no aparecen en el HTML generado.

Los casos confirmados se reparten por la **ubicación del paciente**, no por
dónde se adquirió la infección, en sus dos niveles (`Ubi1` y `Ubi2`–`Ubi8`).
Solo el rango de fechas filtra esas tarjetas —responsable, servicio y actividad
son dimensiones del formulario de producción, que no existen en el de casos—, y
la propia tarjeta lo dice.

## El apartado de vigilancia de IAAS

La pestaña "Vigilancia de IAAS" se alimenta del libro **Sistema IAAS v6.5** de
la Unidad de Epidemiología, en Google Sheets
(`1fpUICeal47RTZeWwpyD_gR21yjgqp26OwHd6D4-YW50`), leído en cada ejecución del
workflow. Es el destino de la migración de los dos formularios de KoboToolbox,
que siguen alimentando la otra pestaña mientras dure la transición.

El libro es público con el enlace, así que la lectura no lleva credenciales. Si
alguna vez deja de serlo, la construcción falla con un 403 explícito y el
dashboard **se publica igual**: la pestaña muestra el motivo y la hora del
intento, y el run queda marcado con un aviso en Actions.

De las once hojas del libro se leen cinco: `CASOS_IAAS` (el caso), `PACIENTES`
(solo sexo y fecha de nacimiento, para el tramo de edad), `DISPOSITIVOS` (días
de exposición y bundles), `INVESTIGACIONES` (fechas y enfermedades crónicas) y
`KOBO_SEGUIMIENTO` (ver más abajo).

Las hojas se bajan por `export?format=csv&gid=`, no por la API `gviz/tq`: gviz
devuelve el libro a medias —81 de 186 casos, sin avisar— y un apartado
publicado con un tercio de los datos es peor que uno que falla. Los `gid` no
están escritos a mano: se leen del índice del libro por nombre de hoja, para
que recrear una hoja no rompa la descarga en silencio.

### Qué mide

El apartado mide **vigilancia epidemiológica**, no producción de PCI:

- **Proceso** — embudo de notificado a investigación cerrada, evolución
  mensual de confirmados frente a descartados, y oportunidad en días (ingreso →
  notificación, notificación → investigación, notificación → VIGEPES-08), con
  mediana y P90 en vez de media: la cola es larga y un solo caso demorado
  movería el promedio.
- **Dónde y qué** — servicio, ubicación, diagnóstico de IAAS y origen
  intrahospitalario o importado. El establecimiento de procedencia
  (`LUGAR_ORIGEN_EXTRA`) **no se publica**: es texto libre, y en una página
  pública eso es una fuga esperando a que alguien escriba ahí un nombre. Para
  recuperarlo, el sistema tendría que convertir el campo en lista de opciones.
- **Señales** — posibles conglomerados (3 o más casos confirmados del mismo
  microorganismo, mismo servicio, dentro de 14 días), con detalle al pinchar
  una fila: resumen del grupo y cronología caso a caso. La cronología no lleva
  edad, sexo ni desenlace por fila —fecha más ubicación ya señalan a una cama
  concreta y la página es pública—; los desenlaces van contados en el resumen.
  Y curva epidémica semanal
  con umbral de media móvil de 6 semanas más dos desviaciones típicas. Con
  recuentos de este tamaño el umbral es orientativo: señala variación inusual,
  no prueba un brote, y las tarjetas lo dicen.
- **Microbiología** — microorganismos aislados y su cruce con el servicio, que
  es donde se ve un conglomerado antes de que alguien lo llame brote.
- **Dispositivos** — casos, días de exposición registrados, densidad por 1.000
  días y cumplimiento de bundle. La densidad usa los días que registraron las
  investigaciones, **no** el censo de días-dispositivo del hospital: sirve para
  comparar dispositivos entre sí y en el tiempo, no como tasa oficial. La
  tarjeta lo dice.
- **ISQ** — clasificación de herida, tipo de intervención y procedimiento.
- **Desenlace y causas** — letalidad cruda por diagnóstico, Pareto de causa
  raíz y enfermedades crónicas de base.
- **Calidad del registro** — la última tarjeta cuenta los huecos: cada uno es
  un caso que no entra en alguna de las tarjetas de arriba.

El KPI «Último mes» compara el mes más reciente con la media de los anteriores,
y avisa cuando ese mes está en curso: un mes a medias siempre parece una caída.
La evolución conmuta entre mes y semana. Al filtrar por fechas, la pestaña dice
cuántos casos quedan fuera por no tener fecha de notificación, en vez de dejar
que el total baje sin explicación.

El botón **Descargar CSV** baja exactamente lo que los filtros dejan a la vista,
con las mismas columnas que la pestaña ya publica —ninguna más—, para escribir
el informe mensual sin copiar cifras a mano de la pantalla.

### Fechas perdidas en la migración

La migración desde Kobo dejó `FECHA_NOTIFICACION` y `FECHA_INGRESO` vacías en
101 de los 181 casos migrados; el export crudo del formulario, que vive en la
hoja `KOBO_SEGUIMIENTO` del mismo libro, sí las tiene todas. `iaas.py` las
rescata emparejando por `KOBO_UUID` y publica el recuento en la tarjeta de
calidad del registro.

Es un parche a la vista, no una solución: **lo correcto es rehacer ese tramo de
la migración en el sistema**. Sin el rescate, un tercio de los casos
confirmados se quedaría fuera de toda serie temporal.

### Privacidad

Del libro solo se publican las columnas de la lista blanca de `iaas.py`. Nombre
del paciente, expediente, cama, diagnóstico CIE-10, observaciones, responsable
de la cirugía y personal de PCI no salen del proceso de construcción: lo que no
está declarado no se copia, así que una columna nueva en el sistema no se
filtra por descuido. Dos pruebas lo comprueban, una sobre el bloque de datos y
otra sobre el HTML ya renderizado.

La fecha de nacimiento no se publica: solo el tramo de edad. Los pacientes
distintos se muestran como un total del periodo y no como un KPI que responda a
los filtros: para filtrarlo habría que publicar un identificador por caso, y
fecha + servicio + edad basta para reidentificar a alguien.

Se descargan y fallan juntas: si el libro cambia de forma, la pestaña muestra el
motivo y el resto del dashboard se publica igual.

## Generar el dashboard en tu equipo

Una vez, para preparar el entorno:

    pip install -r requirements.txt
    curl -L https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js -o vendor/chart.umd.min.js
    cp nombres.json.ejemplo nombres.json    # y pon los nombres reales

Después:

    python build_dashboard.py                 # datos en vivo del Google Sheet
    python build_dashboard.py SupPCI.xlsx     # un export local

Escribe `dashboard.html` en la raíz. El archivo es autocontenido: se abre con
doble clic y funciona sin conexión.

## nombres.json

Corrige los nombres de responsables que la migración dejó en formato slug. No
está versionado porque contiene nombres de personas reales y el repositorio es
público. `nombres.json.ejemplo` muestra el formato con nombres ficticios.

En GitHub vive como el secret **NOMBRES_JSON** (Settings → Secrets and variables
→ Actions), cuyo contenido es el JSON entero. El workflow lo escribe a disco
antes de construir.

Si falta, el build aborta con un mensaje que lo explica. No genera un dashboard
con responsables duplicados.

## Comprobar que la integración con Sheets sigue viva

    python build_dashboard.py

Ninguna prueba automática toca la red, a propósito: así la suite corre sin
conexión y no falla por razones ajenas al código. Esta es la comprobación
manual equivalente.

## Qué contiene el dashboard

- **Global** — comparación entre responsables, evolución mensual y mapa de
  calor de submedida por mes.
- **Por responsable** — volumen por mes y por semana, evolución del
  cumplimiento contra la referencia del conjunto, y desglose por medida,
  submedida, unidad/servicio, área específica, grupo ocupacional y cargo.
- **Por formulario** — evolución, desgloses, estado de validación, nivel de
  riesgo, motivos de no cumplimiento y la tabla de registros individuales.

Los filtros de la barra superior afectan a las tres vistas a la vez.

## Métrica

La tasa de cumplimiento es el porcentaje de supervisiones con
`CUMPLE_CORRECTAMENTE = SI` sobre las que tienen dictamen. Los registros sin
dictamen se excluyen del denominador y se reportan por separado; nunca cuentan
como incumplimiento.

## Pruebas

    python -m pytest tests/ -v

`SupPCI.xlsx` es opcional: es un export local del Sheet, no está versionado y
solo sirve como comodidad para desarrollo. Si no lo tienes, un puñado de
pruebas que pinchan cifras exactas de ese archivo concreto se muestran como
`SKIPPED` — es lo esperado, no un fallo. El resto de la suite (incluidas las
tres cifras de control y las pruebas de `render_html`) sigue corriendo igual,
usando el Sheet en vivo la primera vez que hace falta un libro real, así que
sigue cubriendo el pipeline completo.

Y abrir `tests/test_agg.html` en el navegador para las pruebas de agregación.

## Si el build falla

`build_dashboard.py` aborta a propósito cuando el Excel cambia de forma. El
mensaje dice qué encontró. Prefiere fallar a generar un dashboard con cifras
equivocadas. Motivos posibles:

- Falta la hoja `REGISTROS` o `FORMULARIOS`, o una columna esperada en
  cualquiera de las dos.
- Una columna de dimensión (`RESPONSABLE`, `MEDIDA`, `SUBMEDIDA`,
  `UNIDAD_SERVICIO_APLICACION`, `GRUPO_OCUPACIONAL`, `CARGO`,
  `ESTADO_VALIDACION`) trae un nulo: un nulo ahí se codificaría como una
  categoría fantasma en el JavaScript.
- Un valor nuevo en `CUMPLE_CORRECTAMENTE` (solo se interpretan `SI`, `NO` y
  nulo) o en `ESTADO_VALIDACION` (solo `Aprobado` y `En espera`).
- Un `PORCENTAJE_CUMPLIMIENTO` fuera de 0-100, o con decimales: se codifica
  con `int()` y un valor como `92.5` se truncaría en silencio.
- Un `FECHA_EVENTO` que no se puede interpretar como fecha, o fuera del
  rango 2020-01-01 hasta mañana.
- Un formulario usado en `REGISTROS` con `METODO_CUMPLIMIENTO` distinto de
  `SI_NO_NA`: ese método no calcula cumplimiento y no se puede promediar con
  los que sí.
- Un formulario usado en `REGISTROS` que no aparece en el catálogo
  `FORMULARIOS`.
- Un responsable nuevo con nombre en formato slug (falla la migración de
  acentos).
- Falta `vendor/chart.umd.min.js` — ver la sección "Generar el dashboard en tu
  equipo" arriba.
- `nombres.json` no existe o no es un JSON de cadenas.
- Google Sheets no responde, o el documento dejó de ser de lectura pública.

Los nombres en formato slug se corrigen añadiéndolos a `nombres.json`, con su
acentuación correcta. Ese archivo no está versionado porque contiene nombres
reales; copia `nombres.json.ejemplo` para ver su formato. En CI lo escribe el
workflow desde el secret `NOMBRES_JSON`.

## Diseño

`docs/superpowers/specs/2026-08-24-dashboard-supervisiones-design.md`
