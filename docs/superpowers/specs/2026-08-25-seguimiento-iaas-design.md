# Seguimiento al cumplimiento de la investigación de casos de IAAS — Diseño

Fecha: 2026-08-25
Estado: aprobado en brainstorming, pendiente de plan de implementación
Diseños previos: `2026-08-24-dashboard-supervisiones-design.md`,
`2026-08-24-publicacion-y-datos-en-vivo-design.md`

## 0. Cambio del 2026-08-25, posterior a la primera publicación

El apartado se diseñó midiendo cumplimiento y producción. Con el apartado ya
en producción se decidió **quitar el cumplimiento por completo**: las
respuestas SI/NO se siguen leyendo de Kobo pero no se publican, y el apartado
mide solo producción, destacando tres actividades —casos nuevos investigados,
casos en seguimiento y cierre de casos— sobre las otras tres.

Qué queda obsoleto de este documento: la sección 5 (la métrica de
cumplimiento), las tarjetas 2, 3 y 6 de la sección 7, y la referencia a los 24
ítems en la sección 4 —el manifiesto ya no los declara, lo que de paso quita
del módulo 24 etiquetas de texto libre que podían romperlo al reescribir una
pregunta en Kobo—. Lo demás sigue vigente, incluida la sección 4 en todo lo
relativo a la privacidad.

Consecuencia asumida al decidirlo: un `NO` nuevo en el formulario no aparece
en ninguna parte del dashboard.

## 1. Propósito

El equipo llena en KoboToolbox un formulario de seguimiento al cumplimiento de
la investigación de casos de IAAS, y hoy esos datos no se ven en ninguna parte
salvo descargando el export desde Kobo. Este diseño añade al dashboard una
pestaña que los muestra, alimentada desde la API de Kobo en cada ejecución del
workflow.

No cambia nada del pipeline de supervisiones. Añade una segunda fuente, un
segundo esquema y una vista.

## 2. Estado de partida

- `build_dashboard.py` lee el Google Sheet en vivo y produce `dashboard.html`,
  autocontenido, publicado en <https://salvaalvrn.github.io/PCI-STATS/> por el
  workflow `publicar.yml` cada hora.
- 51 pruebas de pytest y 37 aserciones del harness JS en verde.
- El repositorio es **público**, y también lo es la página publicada.

### Verificación hecha antes de diseñar

Se leyó el export
`Formulario_de_seguimiento_al_cumplimiento_de_la_investigación_de_casos_de_IAAS_producción_-_all_versions_-_labels_-_2026-08-25-14-40-08.xlsx`
(155 envíos, 57 columnas, del 2026-07-02 en adelante). De ahí salen los hechos
que sostienen este diseño:

- 5 responsables de investigación, 7 servicios, 4 responsables de reporte.
- Cada envío declara de 1 a 6 actividades en `Producción Reportada`
  (select_multiple, expandido por Kobo en seis columnas `0`/`1`).
- Los 24 ítems SI/NO solo se responden para las actividades declaradas; de ahí
  que cada bloque tenga entre 68 y 119 nulos sobre 155 filas.
- Solo dos ítems presentan algún `NO`: "La investigación fue iniciada
  oportunamente" y "Se documentó la evolución del caso en el formulario de
  investigación". El resto está al 100 %.
- 75 expedientes distintos y 82 nombres de paciente distintos sobre 155 envíos.

La consecuencia para las expectativas: el bloque de cumplimiento saldrá casi
todo al 100 % hasta que haya más variación en los datos. Donde hay señal hoy es
en esos dos ítems y en la producción.

## 3. Decisiones tomadas

| Decisión | Elegida | Alternativas descartadas |
|---|---|---|
| Fuente en producción | API de KoboToolbox con token en secret | Export manual versionado; copiar a un Google Sheet |
| Alcance | Cumplimiento **y** producción | Solo uno de los dos |
| Ubicación | Pestaña nueva en el mismo `dashboard.html` | Página aparte en `/iaas/` |
| Fallo de Kobo | Publicar sin los datos, con el motivo visible | Abortar el build; reutilizar el último volcado bueno |
| Arquitectura | Módulo `kobo.py` propio, ensamblado en `build_dashboard.py` | Generalizar el pipeline a N fuentes; JSON intermedio |

Sobre el fallo de Kobo: la opción elegida no aborta el build, pero el proyecto
tiene un compromiso explícito contra los fallos silenciosos. El diseño lo
respeta haciendo el fallo visible en tres sitios —la pestaña, stderr y una
anotación del workflow— en lugar de dejar que la pestaña desaparezca sin
explicación.

## 4. Privacidad: lista blanca

El export contiene datos de pacientes y la página es pública. Solo estos campos
sobreviven a la carga; el descarte ocurre en `kobo.py`, antes de cualquier
cálculo, y es una **lista blanca**: un campo nuevo en Kobo no se publica por
defecto.

| Campo publicado | Origen en Kobo | Uso |
|---|---|---|
| `fecha` | Fecha de registro | Eje temporal y filtro desde/hasta |
| `responsable` | Responsable de investigación | Dimensión (5 valores) |
| `servicio` | Servicio al que pertenece la investigación | Dimensión (7 valores) |
| `actividades` | `Producción Reportada/*` | 6 booleanos |
| `items` | Las 24 preguntas SI/NO | `1`, `0` o `null` |

Nunca llegan al HTML: `Nombre del paciente`, `Expediente`, `CONCLUSIONES`,
`_uuid`, `meta/rootUuid`, `_id`, `_notes`, `_tags`, `_submitted_by`,
`Responsable de reporte`, `start`, `end`.

Dos matices aprobados explícitamente:

1. `Expediente` **sí se lee en memoria**, únicamente para contar pacientes
   distintos. Al HTML sale el número, nunca los expedientes.
2. Los nombres de los responsables de investigación **sí** se publican, igual
   que ya ocurre con los responsables de supervisión.

## 5. Métricas

**Cumplimiento.** Por envío, `SI / (SI + NO)` sobre los ítems respondidos. Un
ítem en blanco porque su actividad no se declaró es un "no aplica" y queda
fuera del denominador: el mismo trato que "sin dictamen" en supervisiones, y
por la misma razón —no se puede puntuar lo que no se preguntó—.

Los agregados por responsable, servicio, actividad y mes se **ponderan por
volumen** (`Σ SI / Σ respondidos`). No se promedian tasas: un envío con un ítem
respondido no puede pesar lo mismo que uno con quince.

**Producción.** Recuento de envíos que declararon cada actividad, desglosado por
responsable, servicio y periodo, más los pacientes distintos.

## 6. Arquitectura

### 6.1 `kobo.py`

Módulo nuevo, con el mismo reparto de responsabilidades que
`build_dashboard.py`:

- `cargar(token, servidor, uid)` — descarga el esquema del formulario
  (`/api/v2/assets/{uid}.json`) y los envíos (`/api/v2/assets/{uid}/data.json`),
  siguiendo la paginación por `_next` hasta agotarla. Timeout de 60 s, el mismo
  que la descarga del Sheet.
- `validar(esquema, envios)` — comprueba que todas las etiquetas esperadas del
  manifiesto existen en el esquema. Si falta una, error de forma.
- `limpiar(envios)` — aplica la lista blanca y normaliza fechas y valores.
- `codificar(envios)` — produce el bloque `DATA.iaas` con el mismo formato de
  columnas paralelas que ya usa `encode` para supervisiones.

`build_dashboard.py` lo llama desde `main()`, en un único punto, y coloca el
resultado en `DATA.iaas`.

### 6.2 Nombres XML frente a etiquetas

El export trae etiquetas ("Se realizó seguimiento a los casos programados para
el día") pero la API devuelve nombres XML
(`Se_realiz_seguimiento_a_los_casos_programados`). Como hoy solo se conocen las
etiquetas, el manifiesto se escribe **en etiquetas normalizadas** (sin espacios
duros `\xa0`, sin dobles espacios, sin distinguir mayúsculas) y `kobo.py`
construye el mapa etiqueta→nombre leyendo el esquema en cada ejecución.

Contrapartida asumida: renombrar una etiqueta en Kobo rompe el emparejamiento y
se comporta como un cambio de forma. Para cerrarlo, el módulo incluye
`--volcar-esquema`, que imprime el mapa real; tras la primera ejecución con
token se fijan los nombres XML en el manifiesto y la fragilidad desaparece.
Este paso queda **fuera de este diseño**, como trabajo de seguimiento.

### 6.3 Ajustes

- `KOBO_SERVIDOR = "kf.kobotoolbox.org"` y
  `KOBO_ASSET_UID = "aefXsYwJo5RsrZYfaCEcva"`, constantes en `kobo.py`. El uid
  no es una credencial: sin token no sirve.
- El token se lee solo del entorno (`KOBO_TOKEN`), nunca del árbol de trabajo.
- En el workflow, un secret `KOBO_TOKEN` pasado como variable de entorno al
  paso de construcción.

### 6.4 Lado del navegador

`agg` está atado hoy a la global `DATA.rows`. Pasa a ser una fábrica
`crearAgg(dataset)`, y el código actual se convierte en
`const agg = crearAgg(DATA)`. Cambio mecánico que las 37 aserciones existentes
cubren, y que evita un segundo módulo de agregación calcado del primero.

La vista nueva reutiliza `card`, `kpi`, `conTabla`, `charts.*` y `agg.totalDe`
sin estrenar componentes.

## 7. La vista

Pestaña **Investigación de IAAS**, con barra de filtros propia: responsable,
servicio, actividad y rango de fechas. La barra se pinta por vista, porque los
filtros de supervisión —medida, submedida, cargo— no existen en Kobo y
aparecerían como selectores muertos.

Tarjetas, en orden:

1. **KPIs** — registros, pacientes distintos, cumplimiento ponderado, ítems
   respondidos, responsables activos.
2. **Cumplimiento por actividad** — seis barras. Responde "¿qué parte del
   proceso falla?".
3. **Ítems** — los 24 ítems con respondidos, `NO` y tasa, ordenados por `NO`
   descendente para que los incumplimientos queden arriba. Con fila de total.
4. **Producción por actividad** — columnas con el recuento de envíos.
5. **Por responsable** — registros, pacientes, tasa, con fila de total.
6. **Por servicio** — tasa y volumen.
7. **Evolución mensual** — volumen en columnas, tasa en línea.

Todas con "Ver tabla".

## 8. Errores

Ningún fallo de Kobo aborta el build.

- Red, HTTP, timeout, token ausente o cambio de forma: `kobo.py` devuelve
  `{error: "<motivo>", fecha: "<intento>"}` en lugar de datos.
- La pestaña **sigue apareciendo** y muestra el motivo: "Datos de Kobo no
  disponibles: HTTP 401".
- El build lo escribe en stderr y el paso del workflow emite `::warning`, de
  modo que el run queda marcado en la interfaz de Actions.
- Sin token, el build local funciona igual, con la pestaña avisando de que no
  hay credenciales.
- Un error de programación propio **no** se traga: el `except` cubre el fallo de
  red y el de forma, registra tipo y mensaje, y no envuelve el resto del
  pipeline.

## 9. Pruebas

Ninguna toca la red, como el resto de la suite.

- **La que más importa**: construir con un envío sintético cuyo paciente,
  expediente y conclusiones sean cadenas inconfundibles, y afirmar que no
  aparecen en el HTML generado. Protege la lista blanca de la sección 4.
- Tasa ponderada por actividad y por responsable.
- Ítem en blanco por actividad no declarada: fuera del denominador, no cuenta
  como incumplimiento.
- Falta una etiqueta esperada en el esquema: error de forma, no dato silencioso.
- HTTP 401 y timeout: el build termina bien y `DATA.iaas.error` trae el motivo.
- JS: `crearAgg` queda cubierto por las aserciones actuales; se añaden las del
  agregador de IAAS.

## 10. Fuera de alcance

- Fijar los nombres XML en el manifiesto (requiere una ejecución con token).
- Cualquier cambio al pipeline o a las vistas de supervisiones.
- Publicar `CONCLUSIONES`, aunque sea resumido o agregado.

## 11. Pendiente antes de implementar

- El secret `KOBO_TOKEN` creado en Settings → Secrets and variables → Actions.
  Sin él, el módulo se puede escribir y probar entero contra respuestas
  sintéticas, pero la primera ejecución real no puede correr.
