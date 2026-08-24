# Publicación del dashboard y datos en vivo desde Google Sheets — Diseño

Fecha: 2026-08-24
Estado: aprobado en brainstorming, pendiente de plan de implementación
Diseño previo: `2026-08-24-dashboard-supervisiones-design.md`

## 1. Propósito

El dashboard existe y funciona, pero se genera a partir de un `SupPCI.xlsx`
descargado a mano y solo se puede compartir enviando el archivo. Hacen falta dos
cosas: que los datos salgan directamente del Google Sheet donde ya vive el
sistema, y que el equipo lo consulte en una URL fija en lugar de recibir copias
por correo.

Este diseño no cambia el dashboard. Añade una fuente de datos y una vía de
publicación.

## 2. Estado de partida

- `build_dashboard.py` lee un `.xlsx` local y produce `dashboard.html`, un
  archivo autocontenido de 614 KB.
- 31 pruebas de pytest y 31 aserciones de navegador en verde.
- El repositorio `SalvaAlvrn/PCI-STATS` existe y es **privado**, con 26 commits
  locales sin subir.
- El sistema de origen ya vive en Google Sheets: 18 spreadsheets, uno por
  submedida, más el documento maestro que contiene `REGISTROS` y `FORMULARIOS`.

### Verificación hecha antes de diseñar

El documento maestro es
`1jBPvj080XoeAVbTEKqMgkqPRCQkiitv-3zYbyT2Rvf0` y es de lectura pública. Se
descargó su export `.xlsx` y **el pipeline actual lo procesó sin modificar una
sola línea**: `load`, `validate` y `clean` pasaron, devolviendo 21 responsables
y 47 formularios.

Los datos en vivo ya difieren del export local, lo que confirma que la
integración resuelve un problema real: 2804 registros frente a 2806, rango hasta
2026-08-24 en vez de 2026-08-23, y una tasa global de cumplimiento del 74.0%
frente al 72.5% del archivo.

## 3. Decisiones de diseño

### 3.1 Origen de datos

`load(origen)` acepta lo que ya aceptaba —una ruta de archivo— y además una URL
de Google Sheets. Ante una URL, extrae el id del documento, descarga
`https://docs.google.com/spreadsheets/d/<id>/export?format=xlsx` a un archivo
temporal y continúa por el camino que ya existe.

Se eligió el export del libro completo en lugar de leer cada hoja como CSV:

- Una sola petición devuelve `REGISTROS` y `FORMULARIOS`, de modo que no pueden
  quedar desincronizadas entre dos descargas de momentos distintos.
- Conserva los tipos. Las fechas llegan como fechas y no como texto que habría
  que volver a parsear, con el riesgo de unidad y zona horaria que ya causó un
  defecto en este proyecto.
- No cambia nada aguas abajo. `validate`, `clean`, `encode` y `render_html`
  siguen operando sobre los mismos DataFrames, así que las 31 pruebas siguen
  siendo válidas sin retocarlas.

El id del documento es una constante en `build_dashboard.py`, no un secreto: la
hoja es de lectura pública y el id ya aparece en la URL que se comparte.

**El Sheet es el origen por defecto.** Ejecutar el script sin argumentos lee los
datos en vivo; pasar una ruta lee ese archivo. Si alguien construye sin pensar,
obtiene lo actual y no un export de hace semanas.

```
python build_dashboard.py                 # Sheet en vivo
python build_dashboard.py SupPCI.xlsx     # archivo local
```

### 3.2 Frecuencia de actualización

La regeneración es manual, a petición. No hay tarea programada ni llamadas a
Sheets desde el navegador. El dashboard publicado sigue siendo un archivo
autocontenido que funciona sin conexión una vez cargado.

Se descartó el refresco automático por reloj: añade una pieza en marcha
permanente para un dato que no cambia por minutos, y quien conoce el estado de
los datos es quien decide cuándo vale la pena publicar.

### 3.3 Publicación

GitHub Pages, servido desde el repositorio, con el build ejecutado por GitHub
Actions. La URL resultante es `https://salvaalvrn.github.io/PCI-STATS/` y no
vuelve a cambiar.

El disparador es un workflow `workflow_dispatch`, que GitHub muestra como un
botón "Run workflow" en la pestaña Actions.

### 3.4 Visibilidad y datos personales

El dashboard será accesible para cualquiera que tenga el enlace. Es una decisión
tomada con conocimiento de que la página muestra a 21 responsables por nombre
con su tasa de cumplimiento, y una tabla de registros con el nombre de la
persona evaluada.

GitHub Pages en el plan gratuito exige que el repositorio sea público, de modo
que el repositorio pasa a ser público.

**Qué protege sacar los nombres del repositorio, y qué no.** Dos empleados
aparecen hoy por nombre en `build_dashboard.py`, en el plan, en el spec y en los
tests: son los dos cuyo registro quedó en formato slug tras la migración. El
dashboard publicado va a mostrar esos mismos nombres de todos modos, junto a los
otros 19. Lo que se evita es distinto y más acotado: que queden en un repositorio
público **etiquetados como un defecto de migración**, y de forma permanente en el
historial de git aunque después se edite el archivo. Es una mejora real, pero no
es privacidad — es no dejar una anotación desfavorable con nombre propio.

En consecuencia:

- El mapa de normalización sale del código a un `nombres.json` ignorado por git.
- El workflow lo obtiene de un GitHub Secret y lo escribe a disco antes del
  build, de modo que CI puede construir sin que el archivo viva en el repo.
- Los tests usan nombres inventados.
- Los 6 commits que contienen los nombres reales se reescriben. Los mensajes de
  commit están limpios: se verificó que ninguno menciona a una persona.

La reescritura se hace ahora porque nada se ha subido todavía. No hay copias de
nadie que queden desincronizadas, así que es el único momento en que sale gratis.

**Fuera de alcance:** `NOMBRE_EVALUADO`. Se planteó excluir del build las 2012
personas evaluadas, que no son la audiencia del dashboard y solo aparecen en la
tabla de registros. Queda anotado como posible mejora, no se implementa aquí.

## 4. Arquitectura

```
Google Sheet (público)
        │  export?format=xlsx
        ▼
   load() ─→ validate() ─→ clean() ─→ encode() ─→ render_html()
        │         │
        │         └── aborta ante estructura inesperada
        ▼
  dashboard.html ──→ GitHub Pages ──→ https://salvaalvrn.github.io/PCI-STATS/
```

El workflow ejecuta, en este orden:

1. Escribe `nombres.json` desde el secret.
2. Descarga Chart.js a `vendor/` (no está versionado).
3. Corre las 31 pruebas de pytest.
4. Construye `dashboard.html` desde el Sheet en vivo.
5. Publica el resultado en Pages.

**El orden es la garantía.** Cualquier paso que falle detiene el workflow y no se
publica nada: la URL conserva la última versión buena. Si el Sheet cambia de
forma —una columna renombrada, un valor nuevo en `CUMPLE_CORRECTAMENTE`, un
porcentaje fuera de rango, un responsable nuevo en formato slug— el build aborta
con el mensaje concreto que ya produce hoy. El dashboard prefiere quedarse
desactualizado a mostrar cifras equivocadas, que es la misma decisión que
gobierna todo el pipeline.

## 5. Estructura de archivos

| Archivo | Cambio |
|---|---|
| `build_dashboard.py` | `load()` acepta una URL; el mapa de nombres se lee de `nombres.json`; constante con el id del documento |
| `nombres.json` | **Nuevo.** Mapa de normalización. Ignorado por git |
| `nombres.json.ejemplo` | **Nuevo.** Plantilla versionada con nombres ficticios, para que quien clone sepa qué formato tiene |
| `.github/workflows/publicar.yml` | **Nuevo.** El workflow `workflow_dispatch` |
| `.gitignore` | Añade `nombres.json` |
| `tests/conftest.py`, `tests/test_build.py` | Nombres ficticios; pruebas nuevas del origen URL y del mapa ausente |
| `README.md` | Documenta la URL pública, el botón, y el setup del secret |

`template.html` no se toca.

`dashboard.html` **sigue ignorado por git**. Pages no publica desde el
repositorio sino desde el artefacto que sube el workflow, así que el archivo
generado nunca se versiona. Lo mismo vale para `vendor/chart.umd.min.js` y
`SupPCI.xlsx`.

La reescritura del historial cambia los 26 commits locales, mientras que el
remoto tiene el commit inicial. Publicar exige por tanto un push forzado sobre
`origin/main`. Es aceptable únicamente porque nadie más ha clonado el repositorio;
debe hacerse antes de compartir la URL con nadie y no puede repetirse a la
ligera después.

## 6. Manejo de errores

A las validaciones que ya existen se añaden dos, ambas abortando con `BuildError`:

- **`nombres.json` ausente o mal formado.** El mensaje dice qué archivo falta,
  qué forma debe tener y que en CI proviene del secret. Sin esto el build
  produciría responsables duplicados en silencio: los dos slugs aparecerían como
  personas distintas de sí mismas.
- **La descarga del Sheet falla** por red, permisos o porque el documento dejó de
  ser público. El mensaje distingue el fallo de red del HTTP no exitoso e incluye
  la sugerencia de construir desde el `.xlsx` local como alternativa.

Se conserva el respaldo: si Sheets no responde y hay que publicar, se pasa la
ruta de un export local y el build funciona como siempre.

## 7. Pruebas

Ampliando `tests/test_build.py`:

- `load()` distingue una URL de Sheets de una ruta local, y extrae el id del
  documento correctamente a partir de las formas de URL que Google produce
  (con `/edit`, con `#gid=`, con parámetros de consulta).
- La descarga se prueba con la red simulada: una respuesta correcta produce el
  DataFrame esperado; un error HTTP y un fallo de conexión producen cada uno un
  `BuildError` con su mensaje propio. Ninguna prueba de la suite toca la red de
  verdad, para que sigan corriendo sin conexión y sin depender de que el
  documento esté disponible.
- El mapa de nombres se lee de `nombres.json`; su ausencia y un JSON mal formado
  abortan con mensajes distinguibles.
- Las pruebas existentes que verificaban la normalización siguen verificándola,
  con nombres ficticios y un `nombres.json` de prueba.

**Una comprobación manual, deliberadamente no automatizada:** que el pipeline
procesa el Sheet real. Automatizarla haría que la suite dependiera de la red y
de un documento externo, y fallaría por razones ajenas al código. Se ejecuta a
mano al implementar y queda documentada en el README como el modo de comprobar
que la integración sigue viva.

## 8. Fuera de alcance

- Refresco automático por reloj o desde el navegador.
- Control de acceso al dashboard publicado. Es público por decisión explícita.
- Exclusión de `NOMBRE_EVALUADO` del build.
- Leer las 18 spreadsheets de destino. El dashboard consume el documento maestro,
  igual que antes consumía su export.
