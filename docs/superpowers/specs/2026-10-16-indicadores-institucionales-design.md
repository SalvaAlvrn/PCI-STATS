# Indicadores institucionales de PCI editables — Diseño

Fecha: 2026-10-16
Estado: aprobado en brainstorming, pendiente de plan de implementación
Diseños previos: `2026-08-24-dashboard-supervisiones-design.md`,
`2026-08-24-publicacion-y-datos-en-vivo-design.md`,
`2026-08-25-seguimiento-iaas-design.md`

## 1. Propósito

El equipo de PCI lleva los indicadores institucionales en un Excel suelto
(`INDICADOR INSTITUCIONAL.xlsx`): la hoja «Indicadores institucionales PCI»
define cada indicador y la «Hoja1» es la cuadrícula mensual donde se escriben
numerador (N) y denominador (D) y se calcula la tasa (T). Este diseño lleva esa
cuadrícula al dashboard como una pestaña nueva, **«Indicadores»**, donde los
valores se ven y también se editan y se guardan, compartidos para todos.

Es el primer apartado del dashboard que escribe datos. Todo lo demás solo lee.

## 2. Estado de partida

- `dashboard.html` es estático y público en GitHub Pages; el workflow
  `publicar.yml` lo reconstruye cada hora con `build_dashboard.py` desde Google
  Sheets y Kobo.
- No hay servidor propio. Para guardar hace falta un servicio externo que
  acepte escrituras desde el navegador.
- Las fuentes opcionales (Kobo, vigilancia) siguen un patrón: si fallan, el
  bloque de `DATA` sale con `{ok: false, error, fecha}` y el resto del tablero
  se publica igual.

## 3. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Dónde se guarda | Un Google Sheet nuevo y dedicado, escrito por un Apps Script desplegado como web app |
| Quién guarda | Quien conozca una clave compartida del equipo; ver es público |
| Cómo lee la página | En vivo desde el Apps Script, con respaldo en la copia incrustada por el build |
| Periodos | Años con enero a diciembre; selector de año |
| Metas | Una meta por indicador y año, editable; es un tope |

No se usa el libro de vigilancia de IAAS: el script tendría permiso de
escritura sobre un libro con datos de pacientes, y no le hace falta.

## 4. Los indicadores

Viven en código, en `indicadores.py`, como los demás manifiestos. El Sheet
guarda solo números: nadie rompe una definición editando un texto.

| id | Indicador | Numerador | Denominador | k |
|---|---|---|---|---|
| `incidencia_iaas` | Tasa de Incidencia de IAAS | Casos nuevos (excluyendo Hemodiálisis y Diálisis Peritoneal, Colitis Pseudomembranosa e ISQ) | Ingresos hospitalarios | 100 |
| `densidad_iaas` | Densidad de Incidencia de IAAS | Casos nuevos (excluyendo Hemodiálisis y Diálisis Peritoneal, Colitis Pseudomembranosa) | Días-paciente | 1000 |
| `bacvc` | Densidad de Incidencia de Bacteriemia Asociada a Catéter Venoso Central | Casos nuevos de BACVC | Días de mantenimiento de CVC | 1000 |
| `bacteriemia_hd` | Incidencia de Bacteriemia Asociada a Hemodiálisis | Casos nuevos de bacteriemia asociada a catéter de hemodiálisis | Procedimientos de hemodiálisis | 100 |
| `peritonitis_dp` | Incidencia de Peritonitis Asociada a Diálisis Peritoneal | Casos nuevos de peritonitis asociada a DP | Procedimientos de diálisis peritoneal | 100 |
| `navm` | Densidad de Incidencia de Neumonía Asociada a Ventilación Mecánica | Casos nuevos de NAVM | Días de ventilación mecánica invasiva | 1000 |
| `ituacu` | Densidad de Incidencia de ITU Asociada a Catéter Urinario | Casos nuevos de ITUACU | Días de catéter urinario | 1000 |
| `isq` | Incidencia de Infección del Sitio Quirúrgico | Casos nuevos de ISQ IAAS | Procedimientos quirúrgicos | 100 |
| `colitis_cdiff` | Incidencia de Colitis Pseudomembranosa por C. difficile | Casos nuevos de colitis pseudomembranosa | Egresos hospitalarios | 100 |
| `proporcion_dispositivo` | Proporción por tipo de infección relacionada a dispositivo | IAAS a desagregar del periodo (BACVC, ITUACU, NAVMI, ISQ) | Total de IAAS del periodo | 100 |

Los textos se copian literales de la hoja de definiciones, salvo la
ortografía corregida («ingesos»). El indicador 10 no estaba en la Hoja1; se
incluye.

**T = N / D · k.** Se calcula siempre; nunca se guarda ni se escribe a mano.

## 5. Almacenamiento: el Google Sheet

Un libro nuevo, propiedad de la cuenta del equipo, compartido como «cualquiera
con el enlace puede ver» (el build lo lee por CSV público, igual que el libro
de IAAS). Tres pestañas en formato largo:

- **`VALORES`**: `ANIO`, `MES` (1–12), `INDICADOR` (id de la sección 4),
  `NUMERADOR`, `DENOMINADOR`. Una fila por indicador y mes con algún valor;
  las celdas vacías se guardan vacías, no como 0.
- **`METAS`**: `ANIO`, `INDICADOR`, `META`.
- **`CONTROL`**: `ANIO`, `ACTUALIZADO` (marca ISO de la última escritura de ese
  año). La usa la detección de conflictos de la sección 7.

## 6. El Apps Script

`apps_script/indicadores.gs`, versionado en el repo y desplegado a mano una
vez como web app («Ejecutar como: yo», «Acceso: cualquiera»). La clave vive en
las Script Properties (`CLAVE`), nunca en el repo ni en la página.

- **`doGet`** → `{ok: true, valores: [...], metas: [...], control: {...}}`,
  todo el libro. Sin clave: los datos son públicos de todos modos.
- **`doPost`** con cuerpo JSON `{clave, anio, actualizado, valores, metas}`:
  1. Clave distinta de la guardada → `{ok:false, error:"Clave incorrecta"}`.
  2. Validación (las mismas reglas que el navegador, sección 8): año entero
     entre 2020 y 2100, mes 1–12, indicador conocido, números ≥ 0 o vacío.
     Cualquier fallo → `{ok:false, error}` sin escribir nada.
  3. `LockService` durante la escritura.
  4. Si `actualizado` no coincide con `CONTROL` para ese año → `{ok:false,
     conflicto:true, error:"Otra persona guardó cambios en este año; recarga
     para verlos"}`.
  5. Reemplaza las filas de ese año en `VALORES` y `METAS`, escribe la marca
     nueva en `CONTROL` y devuelve el año guardado con su marca nueva.

La lista de ids de indicador se repite en el `.gs`. Una prueba en Python
comprueba que coincide con `indicadores.py`, para que no diverjan.

La lógica de validación va en funciones puras dentro del `.gs`, separadas de
las llamadas a `SpreadsheetApp`.

## 7. Flujo en la página

1. **Al abrir la pestaña** se pinta en el acto la copia del build
   (`DATA.indicadores`). En paralelo, `fetch` al `doGet` con un límite de 8 s:
   si responde, reemplaza los datos y la nota dice «en vivo»; si no, se queda
   la copia y la nota dice «copia de las HH:MM UTC».
2. **Vista**: selector de año (los años con datos más el actual). Tabla con un
   indicador por fila y un mes por columna: T grande, N/D pequeño debajo, y la
   columna de meta. Con meta, T > meta se pinta en rojo y T ≤ meta en verde;
   sin meta o sin T, sin color. Los meses futuros del año en curso salen en
   gris.
3. **Editar**: copia el año a un borrador y muestra la cuadrícula: N y D por
   mes, y la meta. T se recalcula al escribir. La vista no cambia hasta
   guardar.
4. **Guardar**: pide la clave si no está en `sessionStorage` y hace un POST
   con `Content-Type: text/plain` (evita el preflight de CORS, que Apps Script
   no responde). Éxito → la vista toma lo que devuelve el script y se cierra la
   cuadrícula. Fallo → el borrador se conserva y se muestra el error. Clave
   incorrecta → se borra de `sessionStorage`.
5. **Cancelar**: descarta el borrador.

Conflictos: el POST lleva la marca `actualizado` que la página leyó. Si otra
persona guardó en medio, el script rechaza (paso 4 de la sección 6) y nadie
pisa en silencio el trabajo de otro.

## 8. Validación

Idéntica en navegador y script:

- N, D y meta: vacío, o número ≥ 0. Decimales permitidos (la meta de la Hoja1
  ya los usa).
- D = 0 o vacío → T vacío. Nunca 0 ni infinito.
- N > D se acepta: el indicador 10 puede acercarse a 100 y no es un error de
  captura.

## 9. Build

`indicadores.py`:

- `INDICADORES`: el manifiesto de la sección 4.
- `ID_LIBRO` y `URL_SCRIPT`: se rellenan cuando el Sheet y el despliegue
  existan. La URL del script es pública por naturaleza: la página la necesita.
- `construir()` lee `VALORES`, `METAS` y `CONTROL` por CSV, valida columnas e
  ids (un id desconocido falla con mensaje claro, igual que `iaas.validar`) y
  devuelve `{ok, indicadores, valores, metas, control, url_script, generado}`.

`build_dashboard.py` lo llama en su propio `try`, como la vigilancia: un fallo
imprime `AVISO:` y la pestaña muestra el error, con el resto del tablero
intacto. Si `URL_SCRIPT` está vacía, la pestaña se muestra sin botón Editar.

## 10. Importación inicial

`scripts/importar_indicadores.py`, de un solo uso: lee la Hoja1 del Excel y
escribe un CSV por pestaña listo para pegar en el Sheet. Mapeo fila→id por
nombre normalizado. Se importan solo N y D: los meses que en la Hoja1 tienen T
sin N o D (junio y julio de Incidencia de IAAS) quedan vacíos y se avisan en
la salida. La meta 15 de Incidencia de IAAS se importa para 2026.

## 11. Pruebas

- **Python (pytest)**: manifiesto con 10 ids únicos y k ∈ {100, 1000};
  `construir()` con CSV falsos (correcto, columna faltante, id desconocido,
  números ilegibles); el bloque llega al HTML; los ids del `.gs` coinciden con
  el manifiesto; la importación produce las filas esperadas a partir de un
  libro sintético.
- **JS**: un bloque `<script id="mod-indicadores">` con funciones puras
  —`tasa`, `validar`, `estadoMeta`, `aplicarBorrador`— probado con node como
  `tests/test_vigilancia_js.py`.
- **Apps Script**: no corre en CI. Lista de prueba manual tras desplegar:
  `doGet` responde; guardar con clave buena escribe; clave mala no escribe;
  dos pestañas guardando el mismo año → la segunda recibe conflicto; un valor
  negativo se rechaza.

## 12. Puesta en marcha (pasos manuales)

1. Crear el Google Sheet con las tres pestañas y sus cabeceras; compartir como
   lector público por enlace.
2. Pegar `apps_script/indicadores.gs` en Extensiones → Apps Script, definir la
   propiedad `CLAVE` y desplegar como web app.
3. Poner `ID_LIBRO` y `URL_SCRIPT` en `indicadores.py`.
4. Correr la importación y pegar los CSV.

## 13. Fuera de alcance

Gráficos por indicador, exportar a CSV, historial de cambios, calcular N
automáticamente desde la vigilancia, y metas con sentido inverso (todas las
metas son topes).
