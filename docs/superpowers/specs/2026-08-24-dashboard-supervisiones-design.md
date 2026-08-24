# Dashboard interactivo de supervisiones PCI — Diseño

Fecha: 2026-08-24
Estado: aprobado en brainstorming, pendiente de plan de implementación

## 1. Propósito

Cada responsable de supervisión necesita ver, sin depender de nadie, cómo va su
trabajo: cuántos formularios ha aplicado por mes y por semana, y cómo evoluciona
el cumplimiento de sus supervisiones a lo largo del tiempo, desglosado por
medida, submedida, unidad/servicio, área específica, grupo ocupacional y cargo.
La jefatura necesita además una vista comparativa entre responsables. Ambos
necesitan poder abrir un formulario concreto y ver sus estadísticas.

El entregable es un archivo HTML autocontenido que funciona sin conexión y se
regenera corriendo un script cuando el Excel cambia.

## 2. Fuente de datos

`SupPCI.xlsx`. De sus diez hojas, el dashboard consume dos:

- `REGISTROS` (2806 filas, 28 columnas) — la tabla de hechos. Una fila por
  supervisión realizada.
- `FORMULARIOS` (76 filas) — catálogo de formularios por versión: medida,
  submedida, nombre, método de cumplimiento, estado de la versión.

La hoja `PREGUNTAS` no se consume en esta versión. Se menciona aquí para dejar
constancia de que se evaluó y se descartó.

Las hojas `_MIGRACION_*`, `_LOG_*`, `_AUDITORIA_*`, `_DESTINOS_FORMULARIOS`,
`_CONFIGURACION` y `AUDITORIA_CORRECCION_NOMBRES` son infraestructura del
proceso de migración y quedan fuera del alcance.

### Perfil de los datos actuales

| Dimensión | Valores distintos | Notas |
|---|---|---|
| RESPONSABLE | 21 | sin nulos; dos con nombre en formato slug |
| ID_FORMULARIO | 47 | 48 nombres distintos: `F031` cambió de nombre entre versiones |
| MEDIDA | 3 | Medidas estándar (2040), Medidas específicas (763), Herramientas de evaluación (3) |
| SUBMEDIDA | 17 | |
| UNIDAD_SERVICIO_APLICACION | 25 | sin nulos |
| AREA_ESPECIFICA_APLICACION | 66 | 161 nulos |
| GRUPO_OCUPACIONAL | 24 | sin nulos |
| CARGO | 5 | distribución muy sesgada: 2615 de 2806 son Técnico(a) operativo |
| ESTADO_VALIDACION | 2 | En espera 2415, Aprobado 391 |
| NIVEL_RIESGO | 3 | vacío en 2698 de 2806 filas |
| CUMPLE_CORRECTAMENTE | 2 | SI 2012, NO 763, nulo 31 |
| NOMBRE_EVALUADO | 2012 | texto libre, casi único por fila |
| MOTIVO_NO_CUMPLIMIENTO | 366 | texto libre; informado solo en 407 filas |

Rango temporal de `FECHA_EVENTO`: 2026-02-27 a 2026-08-23. El volumen se
concentra fuertemente en los últimos meses (junio 397, julio 1213, agosto 912),
lo que significa que las series mensuales tendrán meses iniciales muy escasos.
Los gráficos deben mostrar el volumen junto a la tasa para que esto resulte
evidente al leerlos.

Los 2806 registros corresponden todos a formularios con
`METODO_CUMPLIMIENTO = SI_NO_NA`. El catálogo contiene también formularios con
método `INFORMACION`, que por definición no calculan cumplimiento; hoy no tienen
registros, pero el pipeline debe contemplarlos (ver sección 7).

## 3. Decisiones de diseño

### 3.1 Distribución

Un único archivo HTML con todos los datos embebidos, con dos modos de uso: una
vista global comparativa entre responsables y una vista individual por
responsable. No hay aislamiento de datos entre responsables; se asume que el
archivo circula dentro del equipo.

### 3.2 Métrica principal de cumplimiento

La métrica principal es la **tasa de `CUMPLE_CORRECTAMENTE = SI`**: número de
supervisiones que cumplen sobre el total de supervisiones con dictamen. La tasa
global actual es 72.5%.

Los 31 registros sin valor en `CUMPLE_CORRECTAMENTE` se **excluyen del
denominador** y se reportan por separado como "sin dictamen". Nunca se cuentan
como incumplimiento.

`PORCENTAJE_CUMPLIMIENTO` sigue estando disponible en las tablas de detalle y en
la vista de formulario, pero no dirige los gráficos de evolución ni los
rankings.

### 3.3 Eje temporal

Las series temporales usan `FECHA_EVENTO` (cuándo se realizó la supervisión), no
`FECHA_REGISTRO` (cuándo se capturó en el sistema). La agregación semanal usa
semana ISO.

### 3.4 Cálculo en el navegador

El script de build exporta datos limpios; toda la agregación ocurre en
JavaScript al vuelo. Con 2806 filas el coste es despreciable y permite cualquier
combinación de filtros sin regenerar el archivo.

Se descartaron dos alternativas. Precalcular los agregados en Python haría
imposibles los filtros cruzados y obligaría a regenerar el archivo ante cada
necesidad nueva. Embeber SQLite WASM es desproporcionado para este volumen.

### 3.5 Limpieza de datos

Estas transformaciones ocurren en el build y cambian lo que el usuario ve, por
lo que se documentan explícitamente:

- **Nombres en formato slug.** `ana_mar_a_p_rez_g_mez` y
  `luis_fernando_l_pez_d_az` se normalizan a "Ana María Pérez Gómez" y
  "Luis Fernando López Díaz" mediante un mapa explícito en el código. No se
  usa des-slugificación automática: no se puede recuperar la acentuación de
  forma fiable y un error silencioso crearía un responsable fantasma.
- **Áreas nulas.** Los 161 nulos de `AREA_ESPECIFICA_APLICACION` pasan a la
  categoría visible `(Sin área específica)`. No se descarta ninguna fila.
- **Identidad de formulario.** La clave es `ID_FORMULARIO`. El nombre mostrado
  es el de la versión más reciente presente en `FORMULARIOS`, lo que resuelve el
  caso de `F031`. La versión se muestra como dato en la cabecera del formulario.

## 4. Vistas

Tres vistas seleccionables por pestañas. Una barra de filtros global persistente
se aplica a las tres: rango de fechas, medida, submedida, unidad/servicio, grupo
ocupacional, cargo y estado de validación. Los filtros activos se muestran como
chips removibles, de forma que ninguna cifra pueda leerse sin saber qué recorte
la produjo.

### Vista A — Global

Destinada a jefatura y a la comparación entre responsables.

- Fila de indicadores: total de supervisiones, tasa de cumplimiento, número de
  responsables activos, número de formularios utilizados, porcentaje aprobado.
- Ranking de responsables: barras horizontales ordenadas por tasa de
  cumplimiento, con el volumen de supervisiones etiquetado junto a cada barra.
  Mostrar tasa y volumen juntos es obligatorio: 535 supervisiones al 70% y 10
  supervisiones al 70% no significan lo mismo.
- Evolución mensual: línea de tasa de cumplimiento con barras de volumen en eje
  secundario.
- Mapa de calor submedida × mes con la tasa de cumplimiento por celda, para
  localizar dónde y cuándo cae el cumplimiento.
- Tabla comparativa de responsables, ordenable por cualquier columna.

### Vista B — Responsable

El caso de uso central. Se accede eligiendo del selector o pulsando un
responsable en la vista global.

- Indicadores de la persona, cada uno con su diferencia respecto al promedio
  global.
- Volumen de formularios por mes, con conmutador a vista semanal.
- Evolución de su tasa de cumplimiento en el tiempo, con la línea global de
  fondo como referencia.
- Desglose del cumplimiento en las seis dimensiones solicitadas: medida,
  submedida, unidad/servicio, área específica, grupo ocupacional y cargo. Cada
  dimensión se presenta como un panel de barras horizontales con tasa y volumen.
  Las dimensiones largas (área específica, con 66 valores) se recortan a los 15
  primeros con un control "ver todas".
- Tabla de los formularios que ha aplicado, con volumen y tasa, enlazada a la
  vista de formulario.

### Vista C — Formulario

- Cabecera con medida, submedida, versión y método de cumplimiento.
- Indicadores, evolución temporal y desglose por unidad, área, grupo ocupacional
  y responsable.
- Estado de validación (Aprobado / En espera) y nivel de riesgo. Dado que
  `NIVEL_RIESGO` está vacío en el 96% de los registros, el bloque de riesgo solo
  se dibuja si hay datos tras el filtro; en caso contrario muestra "sin datos de
  riesgo" en lugar de un gráfico vacío.
- Motivos de no cumplimiento: ranking de `MOTIVO_NO_CUMPLIMIENTO` y lista
  expandible de `CONCLUSIONES_RECOMENDACIONES` de los registros que no
  cumplieron. `MOTIVO_NO_CUMPLIMIENTO` es texto libre, no un catálogo cerrado:
  366 valores distintos sobre 407 registros que lo tienen informado. El ranking
  muestra los 10 primeros y el resto agrupado como "otros motivos", con acceso
  a la lista completa. No se intenta agrupar motivos por similitud de texto.
- Tabla de registros individuales: fecha, responsable, evaluado, unidad,
  porcentaje, totales SI/NO/NA y estado de validación.

## 5. Formato de datos embebido

Para evitar repetir 28 nombres de clave en 2806 objetos, los datos se embeben
como diccionarios más una tabla de hechos en columnas paralelas:

```js
DATA = {
  dims: {
    responsable: [...],   // 21 nombres, ya normalizados
    formulario: [...],    // 47 ids
    medida: [...], submedida: [...], unidad: [...],
    area: [...], grupo: [...], cargo: [...],
    estado: [...], riesgo: [...], motivo: [...]   // 366 textos libres
  },
  forms: {                // metadatos por ID_FORMULARIO
    "F001": { nombre, version, medida, submedida, metodo }
  },
  rows: {                 // 2806 entradas por array, índices alineados
    fecha: [...],         // días desde epoch (entero)
    responsable: [...],   // índice en dims.responsable
    formulario: [...], medida: [...], submedida: [...],
    unidad: [...], area: [...], grupo: [...], cargo: [...],
    estado: [...], riesgo: [...], motivo: [...],
    cumple: [...],        // 1 = SI, 0 = NO, -1 = sin dictamen
    pct: [...], si: [...], no: [...], na: [...]
  },
  texts: {
    evaluado: [...],                             // 2806 cadenas, sin codificar
    conclusiones: { "<índice de fila>": "..." }  // solo filas con cumple = 0
  }
}
```

`NOMBRE_EVALUADO` tiene 2012 valores distintos sobre 2806 filas, así que la
codificación por diccionario no comprime nada. Se embebe como array de cadenas
en `texts` y no se ofrece como dimensión de agregación: agrupar por una columna
casi única no produce estadística útil. Solo aparece como columna en las tablas
de detalle.

`CONCLUSIONES_RECOMENDACIONES` solo se embebe para los registros que no
cumplieron, que es donde se consulta. Peso estimado del archivo final,
incluyendo Chart.js inline: 1.0–1.4 MB.

Medido tras implementar: 583 KB, de los cuales 369 KB son el JSON de datos y
205 KB Chart.js. La estimación era conservadora — la codificación por
diccionario comprime más de lo previsto.

## 6. Estructura del código

### 6.1 `build_dashboard.py`

Cuatro funciones con una responsabilidad cada una:

- `load(path)` — lee `REGISTROS` y `FORMULARIOS`.
- `clean(registros, formularios)` — normaliza nombres slug, rellena áreas nulas,
  resuelve el nombre de formulario por ID, deriva mes y semana ISO desde
  `FECHA_EVENTO`. Es el único lugar donde se transforman valores.
- `encode(df)` — construye los diccionarios y las columnas de índices.
- `render_html(data, template)` — inyecta el JSON y Chart.js en la plantilla y
  escribe `dashboard.html`.

Al terminar imprime un resumen: filas leídas, filas descartadas y su motivo,
nulos rellenados, nombres normalizados y peso del HTML generado.

### 6.2 `dashboard.html`

Cinco módulos, cada uno en su propio bloque `<script>`:

| Módulo | Responsabilidad |
|---|---|
| `store` | Contiene `DATA` y el estado de filtros. Expone `activeRows()`, que devuelve los índices que pasan el filtro. Ningún otro módulo modifica los filtros. |
| `agg` | Funciones puras de agregación: `rateBy(rows, dim)`, `seriesByMonth(rows)`, `seriesByWeek(rows)`, `heatmap(rows, dimA, dimB)`. Sin DOM y sin estado. |
| `charts` | Envoltura de Chart.js. Un creador por tipo de gráfico; todos reciben datos ya agregados. |
| `views` | `renderGlobal()`, `renderResponsable(id)`, `renderFormulario(id)`. Piden a `agg` y entregan a `charts`. |
| `app` | Enrutado de pestañas, barra de filtros y arranque. |

Un cambio de filtro dispara un único `render()` de la vista activa. Los gráficos
se destruyen y se recrean en cada render; a este volumen es instantáneo y evita
el estado residual de Chart.js.

## 7. Manejo de errores

El riesgo real no es un fallo de JavaScript en ejecución, sino que la estructura
del Excel cambie y el dashboard siga generándose con cifras equivocadas. El
build valida antes de generar y aborta con un mensaje explícito si:

- Falta alguna de las columnas esperadas en `REGISTROS` o `FORMULARIOS`.
- `CUMPLE_CORRECTAMENTE` contiene un valor distinto de `SI`, `NO` o nulo.
- `PORCENTAJE_CUMPLIMIENTO` queda fuera del rango 0–100.
- `FECHA_EVENTO` no es parseable o cae fuera de un rango razonable.
- Aparecen registros con `METODO_CUMPLIMIENTO` distinto de `SI_NO_NA`. Estos
  formularios no calculan cumplimiento y requieren una decisión de producto
  antes de incluirlos; hoy no existen, y el build debe avisar en cuanto
  aparezcan en lugar de promediarlos silenciosamente.
- Aparece un responsable nuevo con nombre en formato slug que no esté en el mapa
  de normalización.

En el navegador, cualquier vista cuyo filtro no devuelva filas muestra "sin
registros para estos filtros". Nunca se dibuja un gráfico vacío ni se muestra
`NaN`.

## 8. Pruebas

### `test_build.py` (pytest)

- `clean()` normaliza los dos nombres en formato slug y deja intactos los otros
  diecinueve.
- `clean()` rellena las áreas nulas sin perder filas: el número de filas de
  entrada y de salida coincide.
- `clean()` resuelve `F031` a un único nombre, el de la versión más reciente.
- Cada validación de la sección 7 aborta ante su entrada inválida
  correspondiente.
- `encode()` es reversible: decodificar los índices reproduce los valores
  originales columna por columna.
- **Cifras de control:** la tasa global de cumplimiento que produce el pipeline
  coincide con un `groupby` directo de pandas sobre el Excel. La misma
  comprobación se aplica a la tasa por responsable y a la tasa por mes. Esta
  prueba es la que impide que el dashboard mienta.

### `test_agg.html`

`agg` está compuesto de funciones puras, de modo que se prueba con un `DATA`
sintético pequeño y resultados esperados escritos a mano. Se verifica abriendo
el archivo en el navegador.

## 9. Fuera de alcance

- Estadísticas a nivel de pregunta individual. `REGISTROS` solo guarda los
  totales `TOTAL_SI` / `TOTAL_NO` / `TOTAL_NA`; las respuestas ítem por ítem
  viven en las spreadsheets externas referidas por `_DESTINOS_FORMULARIOS`, que
  no forman parte de este archivo.
- Aislamiento de datos entre responsables.
- Edición de datos desde el dashboard. Es estrictamente de solo lectura.
- Actualización automática. El archivo se regenera ejecutando
  `build_dashboard.py`.
