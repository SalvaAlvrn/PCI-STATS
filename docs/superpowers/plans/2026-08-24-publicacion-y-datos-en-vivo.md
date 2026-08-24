# Publicación y datos en vivo — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `build_dashboard.py` lea los datos del Google Sheet en vivo y que un botón en GitHub Actions publique el dashboard en una URL fija.

**Architecture:** `load()` gana una segunda fuente: además de una ruta local acepta el documento de Sheets, que descarga como `.xlsx` a un temporal y procesa por el camino que ya existe. El mapa de normalización de nombres sale del código a un archivo ignorado por git, que en CI proviene de un secret. Un workflow `workflow_dispatch` corre las pruebas, construye y publica en GitHub Pages, deteniéndose sin publicar si algo falla.

**Tech Stack:** Python 3.12, pandas 3.0.3, openpyxl, requests 2.34, pytest 9.1.1, GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-08-24-publicacion-y-datos-en-vivo-design.md`

## Global Constraints

- **El Sheet es el origen por defecto.** `python build_dashboard.py` sin argumentos lee los datos en vivo; con una ruta lee ese archivo.
- **Documento maestro:** id `1jBPvj080XoeAVbTEKqMgkqPRCQkiitv-3zYbyT2Rvf0`, de lectura pública. El id es una constante del código, no un secreto.
- **Se descarga el libro completo** (`export?format=xlsx`), nunca hojas sueltas como CSV: una sola petición evita que `REGISTROS` y `FORMULARIOS` queden desincronizadas, y conserva los tipos de fecha.
- **Ninguna prueba toca la red.** La suite debe correr sin conexión y sin depender de que el documento esté disponible. Toda descarga se simula.
- **El build aborta antes de publicar.** Cualquier fallo de validación, prueba o descarga detiene el workflow; la URL conserva la última versión buena. El dashboard prefiere estar desactualizado a mostrar cifras equivocadas.
- **Ningún nombre real de persona entra en el repositorio.** Ni en código, ni en tests, ni en documentación nueva.
- **La métrica no cambia:** tasa de `CUMPLE_CORRECTAMENTE = SI` sobre registros con dictamen; los registros sin dictamen se excluyen del denominador y nunca cuentan como incumplimiento.
- Idioma del producto: español. Commits con rutas explícitas, nunca `git add -A`.
- `template.html` no se toca en ninguna task.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `build_dashboard.py` | Gana `cargar_nombres()`, `_extraer_id()`, `_descargar_sheet()`, `_leer_libro()`; `load()` despacha entre archivo y URL |
| `nombres.json` | Mapa de normalización con los nombres reales. **Ignorado por git** |
| `nombres.json.ejemplo` | Plantilla versionada con nombres ficticios |
| `requirements.txt` | Dependencias, para que CI instale lo mismo que hay en local |
| `.github/workflows/publicar.yml` | El workflow `workflow_dispatch` |
| `tests/test_build.py` | Pruebas del origen URL y del mapa de nombres |
| `README.md` | URL pública, el botón, y el setup del secret |

Las tasks 1 a 3 son cambios de código con su ciclo de pruebas. Las tasks 4 y 5 son procedimientos operativos que **no** ejecuta un subagente: reescriben historial, hacen un push forzado y cambian la visibilidad del repositorio. Están escritas para que las corra el controlador junto a su humano, con confirmación explícita.

---

### Task 1: Sacar el mapa de nombres del código

**Files:**
- Modify: `build_dashboard.py`
- Create: `nombres.json`
- Create: `nombres.json.ejemplo`
- Modify: `.gitignore`
- Modify: `tests/test_build.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: `BuildError` (ya existe).
- Produces: `cargar_nombres(ruta="nombres.json") -> dict[str, str]`. `validate(registros, formularios, nombres)` y `clean(registros, formularios, nombres)` reciben el mapa como tercer parámetro. La constante `SLUG_NAME_MAP` desaparece.

Los nombres reales dejan de estar en el código. El mapa se pasa explícitamente en lugar de leerse dentro de `clean()`, para que las funciones del pipeline sigan sin hacer entrada/salida y las pruebas puedan darles un diccionario literal.

- [ ] **Step 1: Escribir las pruebas que fallan**

En `tests/test_build.py`, añadir a la línea de import de `build_dashboard` los nombres `cargar_nombres`, y añadir estas pruebas:

```python
def test_cargar_nombres_lee_el_mapa(tmp_path):
    ruta = tmp_path / "nombres.json"
    ruta.write_text('{"ana_p_rez": "Ana Pérez"}', encoding="utf-8")
    assert cargar_nombres(ruta) == {"ana_p_rez": "Ana Pérez"}


def test_cargar_nombres_sin_archivo_levanta_builderror(tmp_path):
    with pytest.raises(BuildError, match="nombres.json"):
        cargar_nombres(tmp_path / "no_existe.json")


def test_cargar_nombres_json_invalido_levanta_builderror(tmp_path):
    ruta = tmp_path / "nombres.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    with pytest.raises(BuildError, match="no es un JSON válido"):
        cargar_nombres(ruta)


def test_cargar_nombres_rechaza_valores_no_texto(tmp_path):
    ruta = tmp_path / "nombres.json"
    ruta.write_text('{"ana_p_rez": 3}', encoding="utf-8")
    with pytest.raises(BuildError, match="cadenas de texto"):
        cargar_nombres(ruta)


def test_el_ejemplo_versionado_es_cargable():
    ejemplo = Path(__file__).resolve().parent.parent / "nombres.json.ejemplo"
    mapa = cargar_nombres(ejemplo)
    assert mapa, "la plantilla no puede estar vacía"
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in mapa.items())
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `python -m pytest tests/test_build.py -k nombres -v`
Expected: FAIL con `ImportError: cannot import name 'cargar_nombres'`

- [ ] **Step 3: Escribir `cargar_nombres()` y quitar la constante**

En `build_dashboard.py`, borrar el bloque `SLUG_NAME_MAP = {...}` junto con su comentario, y añadir en su lugar:

```python
RUTA_NOMBRES = Path(__file__).resolve().parent / "nombres.json"

# El mapa de normalización de nombres vive fuera del código: contiene nombres
# de personas reales y el repositorio es público. En CI llega desde un secret.
# Sigue siendo explícito a propósito: des-sluguificar automáticamente no puede
# recuperar la acentuación, y un error silencioso crearía un responsable
# fantasma que partiría sus estadísticas en dos.


def cargar_nombres(ruta=RUTA_NOMBRES):
    """Lee el mapa de normalización de nombres de responsables."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise BuildError(
            f"No existe {ruta}. Es el mapa que corrige los nombres que la "
            "migración dejó en formato slug. Copia nombres.json.ejemplo a "
            "nombres.json y pon los nombres reales. En CI lo escribe el "
            "workflow desde el secret NOMBRES_JSON."
        )
    try:
        mapa = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BuildError(f"{ruta} no es un JSON válido: {error}")
    if not isinstance(mapa, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in mapa.items()
    ):
        raise BuildError(
            f"{ruta} debe ser un objeto cuyas claves y valores sean todos "
            "cadenas de texto"
        )
    return mapa
```

- [ ] **Step 4: Pasar el mapa a `validate()` y `clean()`**

Cambiar las dos firmas y sus usos internos. En `validate`, la línea de la firma pasa a `def validate(registros, formularios, nombres):` y la comprobación de slugs sin mapear usa `nombres` en lugar de `SLUG_NAME_MAP`:

```python
    sin_mapear = slugs - set(nombres)
```

En `clean`, la firma pasa a `def clean(registros, formularios, nombres):` y la normalización usa el parámetro:

```python
    df["RESPONSABLE"] = df["RESPONSABLE"].replace(nombres)
```

En `main()`, cargar el mapa antes de usarlo y pasarlo a ambas:

```python
    nombres = cargar_nombres()
    validate(registros, formularios, nombres)
    limpio = clean(registros, formularios, nombres)
```

y cambiar la línea del resumen que contaba nombres normalizados:

```python
    normalizados = int(registros["RESPONSABLE"].isin(nombres).sum())
    print(f"Nombres normalizados: {normalizados}")
```

- [ ] **Step 5: Crear los dos archivos de mapa**

`nombres.json.ejemplo`, versionado, con nombres inventados:

```json
{
  "ana_mar_a_p_rez_g_mez": "Ana María Pérez Gómez",
  "luis_fernando_l_pez_d_az": "Luis Fernando López Díaz"
}
```

`nombres.json`, **no versionado**, con los reales. Créalo copiando los dos pares que hoy están en `SLUG_NAME_MAP` **antes** de borrar la constante:

```bash
grep -A4 "SLUG_NAME_MAP = {" build_dashboard.py
```

Si ya la borraste, recupéralos con `git show HEAD:build_dashboard.py | grep -A4 SLUG_NAME_MAP`.

Añadir a `.gitignore`, después de la línea `SupPCI.xlsx`:

```
nombres.json
```

- [ ] **Step 6: Actualizar las pruebas y fixtures existentes**

En `tests/conftest.py`, el fixture `registros_ok` usa un slug como valor de `RESPONSABLE`. Sustituirlo por el slug ficticio `ana_mar_a_p_rez_g_mez`, y añadir un fixture nuevo:

```python
@pytest.fixture
def nombres_ok():
    """Mapa de normalización con nombres ficticios."""
    return {
        "ana_mar_a_p_rez_g_mez": "Ana María Pérez Gómez",
        "luis_fernando_l_pez_d_az": "Luis Fernando López Díaz",
    }
```

En `tests/test_build.py`:
- Toda llamada a `validate(registros, formularios)` pasa a `validate(registros, formularios, nombres_ok)`, y toda llamada a `clean(registros, formularios)` a `clean(registros, formularios, nombres_ok)`. Añadir `nombres_ok` a los parámetros de cada prueba afectada.
- Las aserciones que buscaban el primer nombre real del mapa pasan a buscar `"Ana María Pérez Gómez"`, el primero de `nombres.json.ejemplo`.
- Las pruebas que corren sobre el libro real (`test_validate_pasa_sobre_el_excel_real`, `test_clean_sobre_el_excel_real_conserva_todas_las_filas`, las tres cifras de control y las dos de `render_html`) necesitan el mapa real: usan `cargar_nombres()` sin argumento. Si `nombres.json` no existe en la máquina, esas pruebas fallarán con un mensaje claro, que es el comportamiento correcto.

**No debilites ninguna aserción.** Si una expectativa deja de cuadrar, el fixture cambió de forma inesperada: revísalo en vez de ajustar el número.

- [ ] **Step 7: Ejecutar la suite completa**

Run: `python -m pytest tests/ -v`
Expected: PASS, 36 pruebas (31 previas + 5 nuevas).

- [ ] **Step 8: Verificar que no queda ningún nombre real**

Los nombres a buscar se leen de `nombres.json`, para no escribirlos en un
archivo versionado. Busca en todo el árbol excepto el propio `nombres.json`,
que está ignorado y sí debe contenerlos:

```bash
python - <<'PY' > /tmp/patrones.txt
import json
mapa = json.load(open("nombres.json", encoding="utf-8"))
print("\n".join(list(mapa) + list(mapa.values())))
PY
grep -rnFf /tmp/patrones.txt --exclude=nombres.json --exclude-dir=.git . ; echo "salida vacía = correcto"
rm /tmp/patrones.txt
```

Expected: sin coincidencias. Si alguna aparece, no continúes: quítala antes de commitear.

- [ ] **Step 9: Commit**

```bash
git add build_dashboard.py nombres.json.ejemplo .gitignore tests/test_build.py tests/conftest.py
git commit -m "refactor: move the name map out of the code into an ignored file"
```

---

### Task 2: Leer los datos del Sheet en vivo

**Files:**
- Modify: `build_dashboard.py`
- Modify: `tests/test_build.py`

**Interfaces:**
- Consumes: `BuildError`.
- Produces: `load(origen=None)`, que sin argumento descarga el documento en vivo, con una URL de Sheets descarga ese documento, y con una ruta lee ese archivo. Helpers `_extraer_id(url) -> str`, `_descargar_sheet(id_documento, destino: Path) -> Path`, `_leer_libro(path) -> tuple[DataFrame, DataFrame]`. Constantes `ID_DOCUMENTO`, `URL_EXPORT`, `TIMEOUT_SEGUNDOS`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir a los imports de `tests/test_build.py`:

```python
from unittest.mock import Mock, patch

import requests

from build_dashboard import ID_DOCUMENTO, _descargar_sheet, _extraer_id
```

y las pruebas:

```python
@pytest.mark.parametrize(
    "url",
    [
        "https://docs.google.com/spreadsheets/d/ABC123_-xyz/edit?gid=7#gid=7",
        "https://docs.google.com/spreadsheets/d/ABC123_-xyz/edit",
        "https://docs.google.com/spreadsheets/d/ABC123_-xyz",
    ],
)
def test_extraer_id_reconoce_las_formas_de_url(url):
    assert _extraer_id(url) == "ABC123_-xyz"


def test_extraer_id_rechaza_una_url_ajena():
    with pytest.raises(BuildError, match="no parece una URL de Google Sheets"):
        _extraer_id("https://example.com/algo")


def test_descargar_sheet_escribe_el_contenido(tmp_path):
    destino = tmp_path / "sheet.xlsx"
    respuesta = Mock(status_code=200, content=b"contenido-binario")
    with patch("build_dashboard.requests.get", return_value=respuesta) as get:
        _descargar_sheet("ABC123", destino)
    assert destino.read_bytes() == b"contenido-binario"
    assert "ABC123" in get.call_args.args[0]


def test_descargar_sheet_con_http_no_exitoso_levanta_builderror(tmp_path):
    respuesta = Mock(status_code=403, content=b"")
    with patch("build_dashboard.requests.get", return_value=respuesta):
        with pytest.raises(BuildError, match="403"):
            _descargar_sheet("ABC123", tmp_path / "sheet.xlsx")


def test_descargar_sheet_sin_red_levanta_builderror(tmp_path):
    with patch(
        "build_dashboard.requests.get",
        side_effect=requests.ConnectionError("sin ruta al host"),
    ):
        with pytest.raises(BuildError, match="No se pudo contactar"):
            _descargar_sheet("ABC123", tmp_path / "sheet.xlsx")


def test_load_sin_argumento_usa_el_documento_configurado():
    contenido = XLSX.read_bytes()
    respuesta = Mock(status_code=200, content=contenido)
    with patch("build_dashboard.requests.get", return_value=respuesta) as get:
        registros, formularios = load()
    assert ID_DOCUMENTO in get.call_args.args[0]
    assert len(registros) == 2806
    assert len(formularios) == 76


def test_load_con_url_descarga_ese_documento():
    contenido = XLSX.read_bytes()
    respuesta = Mock(status_code=200, content=contenido)
    with patch("build_dashboard.requests.get", return_value=respuesta) as get:
        registros, _ = load("https://docs.google.com/spreadsheets/d/OTRO_ID/edit")
    assert "OTRO_ID" in get.call_args.args[0]
    assert len(registros) == 2806


def test_load_con_ruta_sigue_leyendo_el_archivo():
    with patch("build_dashboard.requests.get") as get:
        registros, formularios = load(XLSX)
    get.assert_not_called()
    assert len(registros) == 2806
```

Las dos últimas son las que importan: confirman que la ruta local nunca sale a la red y que la red se usa exactamente cuando debe.

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `python -m pytest tests/test_build.py -k "extraer_id or descargar or load_" -v`
Expected: FAIL con `ImportError: cannot import name '_extraer_id'`

- [ ] **Step 3: Escribir la implementación**

En `build_dashboard.py`, añadir `import re` y `import tempfile` a los imports, más `import requests`. Añadir las constantes junto a las demás:

```python
# Documento maestro en Google Sheets. No es un secreto: la hoja es de lectura
# pública y el id ya aparece en la URL que se comparte con el equipo.
ID_DOCUMENTO = "1jBPvj080XoeAVbTEKqMgkqPRCQkiitv-3zYbyT2Rvf0"
URL_EXPORT = "https://docs.google.com/spreadsheets/d/{id}/export?format=xlsx"
TIMEOUT_SEGUNDOS = 60
```

Sustituir `load()` por estas cuatro funciones:

```python
def _extraer_id(url):
    """Saca el id del documento de una URL de Google Sheets."""
    encontrado = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url)
    if not encontrado:
        raise BuildError(f"{url} no parece una URL de Google Sheets")
    return encontrado.group(1)


def _descargar_sheet(id_documento, destino):
    """Descarga el libro completo como .xlsx.

    Se pide el libro entero y no cada hoja por separado: una sola petición
    garantiza que REGISTROS y FORMULARIOS vienen del mismo instante, y el
    formato conserva las fechas como fechas en lugar de como texto.
    """
    url = URL_EXPORT.format(id=id_documento)
    try:
        respuesta = requests.get(url, timeout=TIMEOUT_SEGUNDOS)
    except requests.RequestException as error:
        raise BuildError(
            f"No se pudo contactar con Google Sheets: {error}. Si necesitas "
            "publicar igualmente, construye desde un export local pasando su "
            "ruta: python build_dashboard.py SupPCI.xlsx"
        )
    if respuesta.status_code != 200:
        raise BuildError(
            f"Google Sheets respondió {respuesta.status_code} al pedir el "
            f"documento {id_documento}. Comprueba que sigue siendo de lectura "
            "pública."
        )
    destino = Path(destino)
    destino.write_bytes(respuesta.content)
    return destino


def _leer_libro(path):
    """Lee las hojas REGISTROS y FORMULARIOS de un libro .xlsx."""
    path = Path(path)
    if not path.exists():
        raise BuildError(f"El archivo {path} no existe")
    libro = pd.ExcelFile(path)
    try:
        faltantes = {"REGISTROS", "FORMULARIOS"} - set(libro.sheet_names)
        if faltantes:
            raise BuildError(f"Faltan hojas en el libro: {sorted(faltantes)}")
        registros = pd.read_excel(libro, "REGISTROS")
        formularios = pd.read_excel(libro, "FORMULARIOS")
    finally:
        libro.close()
    return registros, formularios


def load(origen=None):
    """Lee REGISTROS y FORMULARIOS del Sheet en vivo o de un .xlsx local.

    Sin argumento usa el documento configurado en ID_DOCUMENTO. Con una URL
    de Sheets usa ese documento. Con una ruta lee ese archivo.
    """
    if origen is None or str(origen).startswith("http"):
        id_documento = (
            ID_DOCUMENTO if origen is None else _extraer_id(str(origen))
        )
        with tempfile.TemporaryDirectory() as carpeta:
            descargado = _descargar_sheet(
                id_documento, Path(carpeta) / "sheet.xlsx"
            )
            return _leer_libro(descargado)
    return _leer_libro(origen)
```

El `libro.close()` en un `finally` importa en Windows: sin él, el handle abierto impide borrar la carpeta temporal.

- [ ] **Step 4: Actualizar `main()` para que el Sheet sea el origen por defecto**

```python
def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    raiz = Path(__file__).resolve().parent
    origen = argv[0] if argv else None
    salida = raiz / "dashboard.html"

    if origen is None:
        print(f"Leyendo el documento en vivo {ID_DOCUMENTO}")
    else:
        print(f"Leyendo {origen}")
    registros, formularios = load(origen)
    print(f"Leídas {len(registros)} filas de REGISTROS")
    ...
```

El resto de `main()` no cambia.

- [ ] **Step 5: Ejecutar la suite completa**

Run: `python -m pytest tests/ -v`
Expected: PASS, 46 pruebas (36 previas + 10 nuevas; la prueba de las formas de URL está parametrizada con tres casos y cuenta como tres).

- [ ] **Step 6: Comprobación manual contra el documento real**

Esta es la única comprobación que toca la red, y se hace a mano precisamente para que la suite no dependa de ella:

```bash
python build_dashboard.py
```

Expected: imprime el id del documento, un número de filas cercano a 2800, el resumen habitual, y escribe `dashboard.html`. Anota el número de filas y la tasa, y compáralos con los del `.xlsx` local — es normal que difieran, porque el Sheet está vivo.

- [ ] **Step 7: Commit**

```bash
git add build_dashboard.py tests/test_build.py
git commit -m "feat: read data from the live Google Sheet by default"
```

---

### Task 3: El workflow de publicación

**Files:**
- Create: `requirements.txt`
- Create: `.github/workflows/publicar.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `python build_dashboard.py` y `python -m pytest tests/`.
- Produces: nada que consuma código. El workflow es la interfaz de usuario del despliegue.

No hay pruebas automáticas de esta task: un workflow solo se verifica ejecutándolo, cosa que ocurre en la Task 5. Su corrección se comprueba leyendo el orden de los pasos.

- [ ] **Step 1: Crear `requirements.txt`**

```
pandas==3.0.3
openpyxl
requests==2.34.0
pytest==9.1.1
```

Comprobar que refleja el entorno local:

```bash
python -c "import pandas, openpyxl, requests, pytest; print(pandas.__version__, requests.__version__, pytest.__version__)"
```

Expected: `3.0.3 2.34.0 9.1.1`.

- [ ] **Step 2: Escribir el workflow**

`.github/workflows/publicar.yml`:

```yaml
name: Publicar dashboard

# El botón. Aparece como "Run workflow" en la pestaña Actions.
on:
  workflow_dispatch:

# Permisos mínimos para que el job pueda publicar en Pages.
permissions:
  contents: read
  pages: write
  id-token: write

# Si alguien pulsa el botón dos veces, la segunda ejecución espera en vez de
# pisar a la primera a medias.
concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  publicar:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.despliegue.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip

      - name: Instalar dependencias
        run: pip install -r requirements.txt

      - name: Escribir el mapa de nombres
        # Contiene nombres de personas reales y el repositorio es público,
        # así que vive en un secret y nunca en el árbol de trabajo.
        run: echo "$NOMBRES_JSON" > nombres.json
        env:
          NOMBRES_JSON: ${{ secrets.NOMBRES_JSON }}

      - name: Descargar Chart.js
        # vendor/*.js no está versionado.
        run: |
          curl -fsSL -o vendor/chart.umd.min.js \
            https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js

      - name: Correr las pruebas
        # Antes de construir: si el código está roto no se publica nada.
        run: python -m pytest tests/ -q

      - name: Construir desde el Sheet en vivo
        # Aborta si el documento cambió de forma. La URL conserva entonces
        # la última versión buena.
        run: python build_dashboard.py

      - name: Preparar el sitio
        run: |
          mkdir -p sitio
          cp dashboard.html sitio/index.html

      - uses: actions/configure-pages@v5

      - uses: actions/upload-pages-artifact@v3
        with:
          path: sitio

      - id: despliegue
        uses: actions/deploy-pages@v4
```

El orden es la garantía del diseño: pruebas, luego build, y solo entonces publicar. Cada paso que falla detiene el job antes de tocar la URL. `dashboard.html` se copia a `sitio/index.html` para que la URL raíz sirva el dashboard sin que nadie tenga que escribir el nombre del archivo.

- [ ] **Step 3: Validar la sintaxis YAML**

```bash
python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/publicar.yml',encoding='utf-8')); print('YAML válido')"
```

Si `yaml` no está instalado: `pip install pyyaml` y repetir. No añadas pyyaml a `requirements.txt`; es solo para esta comprobación.

Expected: `YAML válido`.

- [ ] **Step 4: Actualizar el README**

Sustituir la sección `## Uso` por:

```markdown
## Ver el dashboard

<https://salvaalvrn.github.io/PCI-STATS/>

El enlace es fijo. Se comparte una vez y no cambia.

## Actualizar los datos publicados

En GitHub, pestaña **Actions** → **Publicar dashboard** → **Run workflow**.

El workflow lee el Google Sheet en vivo, corre las pruebas, construye y publica.
Tarda un par de minutos. Si algo falla —el Sheet cambió de forma, una prueba se
rompió— el workflow se detiene y **no publica**: la URL sigue mostrando la última
versión buena. Es deliberado: el dashboard prefiere estar desactualizado a
mostrar cifras equivocadas.

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
```

En la sección "Si el build falla", añadir a la lista de causas:

```markdown
- `nombres.json` no existe o no es un JSON de cadenas.
- Google Sheets no responde, o el documento dejó de ser de lectura pública.
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .github/workflows/publicar.yml README.md
git commit -m "feat: add the publish workflow and document the deployment"
```

---

### Task 4: Reescribir el historial — procedimiento manual

**Files:** ninguno. Reescribe los commits existentes.

**Interfaces:** ninguna.

> **Esta task NO la ejecuta un subagente.** Reescribe el historial de git y prepara un push forzado. La ejecuta el controlador junto a su humano, con confirmación explícita antes de cada paso destructivo.

El objetivo es que los nombres reales de dos empleados no queden en el historial de un repositorio público. Los commits que los contienen son 6 de los 26; los mensajes de commit están limpios.

- [ ] **Step 1: Confirmar el estado de partida**

```bash
git status --short
git log --oneline origin/main..main | wc -l
python - <<'PY'
import json, subprocess
apellido = list(json.load(open("nombres.json", encoding="utf-8")).values())[0]
salida = subprocess.run(["git", "log", "--oneline", "-S", apellido, "--all"],
                        capture_output=True, text=True).stdout
print(f"commits con el primer nombre real: {len(salida.splitlines())}")
PY
```

Expected: árbol limpio; una treintena de commits locales sin subir —el número exacto depende de cuántos hicieran las tasks 1 a 3, y no importa—; y **exactamente 6** commits conteniendo los nombres. Ese 6 sí importa: si sale otro número, alguna task posterior volvió a introducir un nombre real y hay que averiguar dónde antes de reescribir. Si el árbol no está limpio, commitea o guarda los cambios antes de seguir.

- [ ] **Step 2: Copia de seguridad**

```bash
git branch respaldo-antes-de-reescribir
```

Si algo sale mal, `git reset --hard respaldo-antes-de-reescribir` devuelve todo a este punto.

- [ ] **Step 3: Instalar git-filter-repo**

```bash
pip install git-filter-repo
python -m git_filter_repo --version
```

- [ ] **Step 4: Escribir las sustituciones**

El archivo de sustituciones contiene los nombres reales, así que se **genera**
desde `nombres.json` y `nombres.json.ejemplo` en lugar de escribirse a mano, y
se deja **fuera del repositorio**. Cada entrada real se empareja por posición
con su equivalente ficticio:

```bash
python - <<'PY' > /tmp/reemplazos.txt
import json
reales = json.load(open("nombres.json", encoding="utf-8"))
ficticios = json.load(open("nombres.json.ejemplo", encoding="utf-8"))
assert len(reales) == len(ficticios), (
    "nombres.json y nombres.json.ejemplo deben tener el mismo número de "
    "entradas para poder emparejarlas"
)
for (slug_real, nombre_real), (slug_fic, nombre_fic) in zip(
    reales.items(), ficticios.items()
):
    print(f"{slug_real}==>{slug_fic}")
    print(f"{nombre_real}==>{nombre_fic}")
PY
wc -l /tmp/reemplazos.txt
```

Expected: `4 /tmp/reemplazos.txt` — dos líneas por persona, el slug y el nombre.
Si la aserción salta, añade a `nombres.json.ejemplo` tantas entradas ficticias
como reales tenga `nombres.json`.

- [ ] **Step 5: Reescribir**

```bash
python -m git_filter_repo --replace-text /ruta/a/reemplazos.txt --force
```

`git-filter-repo` elimina el remoto `origin` por diseño, para que nadie empuje por accidente sobre un historial que ya no coincide. Se repone en el paso siguiente.

- [ ] **Step 6: Verificar que no queda rastro**

```bash
python - <<'PY'
import json, subprocess
mapa = json.load(open("nombres.json", encoding="utf-8"))
for aguja in list(mapa) + list(mapa.values()):
    salida = subprocess.run(["git", "log", "--all", "--oneline", "-S", aguja],
                            capture_output=True, text=True).stdout
    print(f"{len(salida.splitlines()):3d} commits contienen {aguja!r}")
PY
```

Expected: `0` en los tres. Si alguno no es cero, **detente**: la reescritura no fue completa y publicar el repositorio expondría los nombres.

- [ ] **Step 7: Comprobar que el código sigue funcionando**

```bash
git remote add origin https://github.com/SalvaAlvrn/PCI-STATS.git
python -m pytest tests/ -q
```

Expected: PASS. La reescritura tocó `build_dashboard.py` y los tests en commits antiguos, pero el contenido actual debe ser idéntico al de antes salvo por los nombres ficticios. Si falla, compara con `git diff respaldo-antes-de-reescribir` y arregla antes de continuar.

- [ ] **Step 8: Borrar el archivo de sustituciones**

```bash
rm /ruta/a/reemplazos.txt
```

Contiene los nombres reales; no tiene por qué sobrevivir al procedimiento.

---

### Task 5: Publicar — procedimiento manual

**Files:** ninguno.

**Interfaces:** ninguna.

> **Esta task NO la ejecuta un subagente.** Hace público un repositorio y fuerza la reescritura del remoto. Ambas son acciones que el humano debe autorizar explícitamente, y la primera no se deshace del todo: lo que se exponga puede quedar cacheado o indexado aunque después se revierta.

- [ ] **Step 1: Confirmar con el humano antes de nada**

Presentar exactamente qué va a pasar y esperar un sí:

- El repositorio `SalvaAlvrn/PCI-STATS` pasará de privado a **público**. Cualquiera podrá leer el código, los documentos de diseño y todo el historial.
- Se hará un **push forzado** sobre `origin/main`, que reemplaza el commit inicial que hoy está en el remoto.
- La URL publicada mostrará a los 21 responsables por nombre con su tasa de cumplimiento, y la tabla de registros con el nombre de la persona evaluada. Cualquiera con el enlace la verá.

- [ ] **Step 2: Crear el secret**

En GitHub: Settings → Secrets and variables → Actions → New repository secret.

- Nombre: `NOMBRES_JSON`
- Valor: el contenido íntegro del `nombres.json` local, incluidas las llaves.

Créalo **antes** de hacer público el repositorio: los secrets no se exponen, pero así el primer workflow ya lo encuentra.

- [ ] **Step 3: Hacer público el repositorio**

Settings → General → Danger Zone → Change repository visibility → Public.

- [ ] **Step 4: Subir el historial reescrito**

```bash
git push --force origin main
```

- [ ] **Step 5: Activar Pages**

Settings → Pages → Source: **GitHub Actions**. No elegir "Deploy from a branch": el workflow publica un artefacto, no una rama, y `dashboard.html` no está versionado.

- [ ] **Step 6: Pulsar el botón**

Actions → Publicar dashboard → Run workflow.

Seguir la ejecución. Expected: los siete pasos en verde y una URL en el resumen del job.

- [ ] **Step 7: Verificar lo publicado**

Abrir <https://salvaalvrn.github.io/PCI-STATS/> y comprobar:

- La cabecera muestra un número de supervisiones y una fecha de generación de hoy.
- Las tres pestañas cargan y los filtros funcionan.
- El número de supervisiones coincide con el que imprimió el workflow.
- La consola del navegador no muestra errores.

- [ ] **Step 8: Comprobar que el fallo también funciona**

Vale la pena confirmar una vez que la garantía es real. Con el humano de acuerdo, renombrar temporalmente una columna del Sheet —por ejemplo `CARGO`— y pulsar el botón otra vez.

Expected: el workflow falla en el paso de construir, con el mensaje que nombra la columna que falta, y **la URL sigue mostrando la versión anterior**. Deshacer el cambio en el Sheet y volver a publicar.

Si este paso no se ejecuta, anotarlo: la garantía queda sin verificar.

- [ ] **Step 9: Borrar la rama de respaldo**

Solo cuando la URL funcione y estés conforme:

```bash
git branch -D respaldo-antes-de-reescribir
```
