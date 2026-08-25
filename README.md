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

## El apartado de investigación de IAAS

La pestaña "Investigación de IAAS" se alimenta del formulario de KoboToolbox
`aefXsYwJo5RsrZYfaCEcva` en `kf.kobotoolbox.org`, leído en cada ejecución del
workflow.

Necesita el secret **`KOBO_TOKEN`** (Settings → Secrets and variables →
Actions) con un token de la API de Kobo. Sin él, o si Kobo no responde, el
dashboard **se publica igual**: la pestaña muestra el motivo y la hora del
intento, y el run queda marcado con un aviso en Actions. Nunca se publica un
dashboard incompleto sin que se sepa por qué.

El apartado mide **producción, no cumplimiento**: cuántos registros declaran
cada actividad, por quién, en qué servicio y en qué mes. Destaca las tres
actividades principales —casos nuevos investigados, casos en seguimiento y
cierre de casos— con un KPI cada una; las otras tres se monitorean en su
propia tarjeta, al final.

Las respuestas SI/NO de cada actividad se leen en Kobo pero **no se
publican**. Consecuencia a tener presente: un `NO` nuevo en el formulario no
aparecerá en ninguna parte del dashboard.

Del formulario solo se publican fecha, responsable, servicio y actividades
declaradas. El nombre del paciente, el expediente, las conclusiones y el
responsable de reporte no salen del proceso de construcción: `kobo.py` los
descarta al cargar, con una lista blanca —lo que no está declarado no se
publica, así que una pregunta nueva en Kobo no se filtra por descuido— y una
prueba comprueba que no aparecen en el HTML generado.

Los pacientes distintos se muestran como un total del periodo, no como un KPI
que responda a los filtros: para filtrarlo habría que publicar un
identificador por fila, y fecha + servicio + responsable basta para
reidentificar a alguien.

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
