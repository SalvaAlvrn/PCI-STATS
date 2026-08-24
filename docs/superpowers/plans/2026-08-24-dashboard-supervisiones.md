# Dashboard de supervisiones PCI — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generar `dashboard.html`, un archivo autocontenido y offline que permite a cada responsable ver sus estadísticas de supervisión y a la jefatura comparar entre responsables, a partir de `SupPCI.xlsx`.

**Architecture:** `build_dashboard.py` lee el Excel, valida su estructura, limpia los datos, los codifica en columnas paralelas con diccionarios, e inyecta el resultado junto a Chart.js en una plantilla HTML. Todo el filtrado y la agregación ocurren en JavaScript en el navegador sobre 2806 filas en memoria, de modo que cualquier combinación de filtros funciona sin regenerar el archivo.

**Tech Stack:** Python 3 + pandas 3.0.3 + openpyxl (lectura), pytest (pruebas), Chart.js 4.4.1 vendorizado (gráficos de línea y barra), CSS Grid puro (mapa de calor), JavaScript vanilla sin framework.

**Spec:** `docs/superpowers/specs/2026-08-24-dashboard-supervisiones-design.md`

## Global Constraints

- **Métrica principal:** tasa de `CUMPLE_CORRECTAMENTE = SI` sobre el total de registros **con dictamen**. Los registros con `CUMPLE_CORRECTAMENTE` nulo se excluyen del denominador y se reportan aparte como "sin dictamen". Nunca cuentan como incumplimiento.
- **Eje temporal:** `FECHA_EVENTO`, nunca `FECHA_REGISTRO`. Semana ISO.
- **Clave de formulario:** `ID_FORMULARIO`. El nombre mostrado es el de la versión más reciente en `FORMULARIOS`.
- **Sin eje Y secundario en ningún gráfico.** Dos medidas de escala distinta van en dos gráficos apilados que comparten el eje X. Esta restricción anula lo que decía la sección 4 del spec sobre "barras de volumen en eje secundario".
- **Paleta fija, validada:** categórico slot 1 `#2a78d6` claro / `#3987e5` oscuro; slot 2 `#eb6834` / `#d95926`. Rampa secuencial azul 100→700 según `references/palette.md` de la skill `dataviz`. Estado: good `#0ca30c`, warning `#fab219`, serious `#ec835a`, critical `#d03b3b`. Superficies: claro `#fcfcfb`, oscuro `#1a1a19`.
- **Sin rampa de color sobre categorías nominales.** Un gráfico de barras de una sola serie usa un color para todas las barras.
- **Modo oscuro obligatorio**, con los pasos propios de cada modo, no una inversión automática.
- **Toda etiqueta de texto procedente de los datos se inserta con `textContent`**, nunca con `innerHTML`. Los nombres vienen del Excel y son datos no confiables.
- **Cada gráfico tiene su tabla equivalente** accesible desde el propio card.
- **Sin conexión:** el HTML generado no puede referenciar ninguna URL externa.
- Idioma de toda la interfaz: español.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `build_dashboard.py` | Pipeline: `load` → `validate` → `clean` → `encode` → `render_html`. Único lugar donde se transforman datos. |
| `template.html` | Plantilla con la marca `/*__DATA__*/` y `/*__CHARTJS__*/`. Contiene CSS, los cinco módulos JS y el marcado. |
| `vendor/chart.umd.min.js` | Chart.js 4.4.1 vendorizado para inyectarlo inline. |
| `tests/test_build.py` | Pruebas de `validate`, `clean`, `encode` y cifras de control contra pandas. |
| `tests/conftest.py` | Fixtures: DataFrames sintéticos mínimos. |
| `tests/test_agg.html` | Harness de aserciones en navegador para el módulo `agg`. |
| `dashboard.html` | Salida generada. En `.gitignore`. |

Los cinco módulos JS viven en `template.html`, cada uno en su propio bloque `<script>`: `store`, `agg`, `charts`, `views`, `app`.

---

### Task 1: Andamiaje del proyecto y `load()`

**Files:**
- Create: `build_dashboard.py`
- Create: `tests/test_build.py`
- Create: `tests/conftest.py`
- Create: `.gitignore`
- Create: `vendor/.gitkeep`

**Interfaces:**
- Consumes: nada.
- Produces: `load(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]` que devuelve `(registros, formularios)`. `BuildError(Exception)`, la excepción que todas las validaciones posteriores levantan.

- [ ] **Step 1: Crear `.gitignore` y el directorio vendor**

```bash
printf 'dashboard.html\nSupPCI.xlsx\n__pycache__/\n.pytest_cache/\nvendor/*.js\n.idea/\n' > .gitignore
mkdir -p vendor tests && touch vendor/.gitkeep
```

- [ ] **Step 2: Escribir la prueba que falla**

`tests/test_build.py`:

```python
from pathlib import Path

import pytest

from build_dashboard import BuildError, load

XLSX = Path(__file__).resolve().parent.parent / "SupPCI.xlsx"


def test_load_devuelve_registros_y_formularios():
    registros, formularios = load(XLSX)
    assert len(registros) == 2806
    assert len(formularios) == 76
    assert "CUMPLE_CORRECTAMENTE" in registros.columns
    assert "METODO_CUMPLIMIENTO" in formularios.columns


def test_load_archivo_inexistente_levanta_builderror():
    with pytest.raises(BuildError, match="no existe"):
        load(Path("no_tal_archivo.xlsx"))
```

- [ ] **Step 3: Ejecutar la prueba para verificar que falla**

Run: `python -m pytest tests/test_build.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'build_dashboard'`

- [ ] **Step 4: Escribir la implementación mínima**

`build_dashboard.py`:

```python
"""Genera dashboard.html a partir de SupPCI.xlsx.

Pipeline: load -> validate -> clean -> encode -> render_html.
Ver docs/superpowers/specs/2026-08-24-dashboard-supervisiones-design.md
"""

from pathlib import Path

import pandas as pd


class BuildError(Exception):
    """La estructura del Excel no es la esperada. Aborta el build."""


def load(path):
    """Lee las hojas REGISTROS y FORMULARIOS de SupPCI.xlsx."""
    path = Path(path)
    if not path.exists():
        raise BuildError(f"El archivo {path} no existe")
    libro = pd.ExcelFile(path)
    faltantes = {"REGISTROS", "FORMULARIOS"} - set(libro.sheet_names)
    if faltantes:
        raise BuildError(f"Faltan hojas en el libro: {sorted(faltantes)}")
    registros = pd.read_excel(libro, "REGISTROS")
    formularios = pd.read_excel(libro, "FORMULARIOS")
    return registros, formularios
```

- [ ] **Step 5: Ejecutar las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_build.py -v`
Expected: PASS, 2 pruebas.

- [ ] **Step 6: Commit**

```bash
git add .gitignore build_dashboard.py tests/ vendor/.gitkeep
git commit -m "feat: add build scaffolding and Excel loader"
```

---

### Task 2: Validación de la estructura del Excel

**Files:**
- Modify: `build_dashboard.py`
- Modify: `tests/test_build.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: `BuildError` de Task 1.
- Produces: `validate(registros: pd.DataFrame, formularios: pd.DataFrame) -> None`, que levanta `BuildError` con un mensaje explícito ante cada condición de la sección 7 del spec. Las constantes `COLUMNAS_REGISTROS`, `COLUMNAS_FORMULARIOS`, `SLUG_NAME_MAP`.

- [ ] **Step 1: Escribir las fixtures sintéticas**

`tests/conftest.py`:

```python
import pandas as pd
import pytest


@pytest.fixture
def registros_ok():
    """Cuatro filas válidas: dos cumplen, una no, una sin dictamen."""
    return pd.DataFrame(
        {
            "ID_REGISTRO": ["R1", "R2", "R3", "R4"],
            "FECHA_REGISTRO": pd.to_datetime(
                ["2026-07-02", "2026-07-03", "2026-07-04", "2026-08-01"]
            ),
            "FECHA_EVENTO": pd.to_datetime(
                ["2026-07-01", "2026-07-02", "2026-07-03", "2026-08-01"]
            ),
            "ID_FORMULARIO": ["F001", "F001", "F002", "F002"],
            "VERSION_FORMULARIO": [1, 1, 2, 2],
            "FORMULARIO": ["Lavado", "Lavado", "Guantes", "Guantes"],
            "MEDIDA": ["Medidas estándar"] * 4,
            "SUBMEDIDA": ["Higiene", "Higiene", "Barreras", "Barreras"],
            "RESPONSABLE": [
                "Ana Pérez",
                "ana_mar_a_p_rez_g_mez",
                "Ana Pérez",
                "Ana Pérez",
            ],
            "UNIDAD_SERVICIO_APLICACION": ["UCI", "UCI", "Emergencia", "UCI"],
            "AREA_ESPECIFICA_APLICACION": ["Box 1", None, "Triage", "Box 2"],
            "GRUPO_OCUPACIONAL": ["Enfermería"] * 4,
            "CARGO": ["Técnico(a) operativo"] * 4,
            "NOMBRE_EVALUADO": ["Juan", "Luis", "Marta", "Rosa"],
            "PORCENTAJE_CUMPLIMIENTO": [100, 60, 100, 90],
            "TOTAL_SI": [5, 3, 4, 4],
            "TOTAL_NO": [0, 2, 0, 1],
            "TOTAL_NA": [1, 1, 2, 0],
            "TOTAL_PENDIENTES": [0, 0, 0, 0],
            "CUMPLE_CORRECTAMENTE": ["SI", "NO", "SI", None],
            "MOTIVO_NO_CUMPLIMIENTO": [None, "Sin insumos", None, None],
            "CONCLUSIONES_RECOMENDACIONES": [None, "Reponer jabón", None, None],
            "ESTADO_VALIDACION": ["Aprobado", "En espera", "En espera", "En espera"],
            "NIVEL_RIESGO": [None, "Alto", None, None],
        }
    )


@pytest.fixture
def formularios_ok():
    """F001 con una versión; F002 con dos y cambio de nombre entre ellas."""
    return pd.DataFrame(
        {
            "ID_FORMULARIO": ["F001", "F002", "F002"],
            "VERSION_FORMULARIO": [1, 1, 2],
            "MEDIDA": ["Medidas estándar"] * 3,
            "SUBMEDIDA": ["Higiene", "Barreras", "Barreras"],
            "NOMBRE_FORMULARIO": ["Lavado", "Guantes viejo", "Guantes"],
            "METODO_CUMPLIMIENTO": ["SI_NO_NA"] * 3,
            "ES_VERSION_ACTUAL": [True, False, True],
        }
    )
```

- [ ] **Step 2: Escribir las pruebas que fallan**

Añadir a `tests/test_build.py`:

```python
from build_dashboard import validate


def test_validate_acepta_datos_correctos(registros_ok, formularios_ok):
    validate(registros_ok, formularios_ok)  # no levanta


def test_validate_detecta_columna_faltante(registros_ok, formularios_ok):
    sin_columna = registros_ok.drop(columns=["CUMPLE_CORRECTAMENTE"])
    with pytest.raises(BuildError, match="CUMPLE_CORRECTAMENTE"):
        validate(sin_columna, formularios_ok)


def test_validate_rechaza_valor_desconocido_en_cumple(registros_ok, formularios_ok):
    registros_ok.loc[0, "CUMPLE_CORRECTAMENTE"] = "PARCIAL"
    with pytest.raises(BuildError, match="PARCIAL"):
        validate(registros_ok, formularios_ok)


def test_validate_rechaza_porcentaje_fuera_de_rango(registros_ok, formularios_ok):
    registros_ok.loc[0, "PORCENTAJE_CUMPLIMIENTO"] = 140
    with pytest.raises(BuildError, match="PORCENTAJE_CUMPLIMIENTO"):
        validate(registros_ok, formularios_ok)


def test_validate_rechaza_fecha_fuera_de_rango(registros_ok, formularios_ok):
    registros_ok.loc[0, "FECHA_EVENTO"] = pd.Timestamp("1999-01-01")
    with pytest.raises(BuildError, match="FECHA_EVENTO"):
        validate(registros_ok, formularios_ok)


def test_validate_avisa_de_metodo_no_soportado(registros_ok, formularios_ok):
    formularios_ok.loc[0, "METODO_CUMPLIMIENTO"] = "INFORMACION"
    with pytest.raises(BuildError, match="INFORMACION"):
        validate(registros_ok, formularios_ok)


def test_validate_rechaza_slug_desconocido(registros_ok, formularios_ok):
    registros_ok.loc[0, "RESPONSABLE"] = "pedro_nuevo_sin_mapear"
    with pytest.raises(BuildError, match="pedro_nuevo_sin_mapear"):
        validate(registros_ok, formularios_ok)


def test_validate_pasa_sobre_el_excel_real():
    registros, formularios = load(XLSX)
    validate(registros, formularios)  # no levanta
```

- [ ] **Step 3: Ejecutar las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_build.py -v`
Expected: FAIL con `ImportError: cannot import name 'validate'`

- [ ] **Step 4: Escribir la implementación**

Añadir a `build_dashboard.py`:

```python
COLUMNAS_REGISTROS = [
    "ID_REGISTRO", "FECHA_REGISTRO", "FECHA_EVENTO", "ID_FORMULARIO",
    "VERSION_FORMULARIO", "FORMULARIO", "MEDIDA", "SUBMEDIDA", "RESPONSABLE",
    "UNIDAD_SERVICIO_APLICACION", "AREA_ESPECIFICA_APLICACION",
    "GRUPO_OCUPACIONAL", "CARGO", "NOMBRE_EVALUADO",
    "PORCENTAJE_CUMPLIMIENTO", "TOTAL_SI", "TOTAL_NO", "TOTAL_NA",
    "CUMPLE_CORRECTAMENTE", "MOTIVO_NO_CUMPLIMIENTO",
    "CONCLUSIONES_RECOMENDACIONES", "ESTADO_VALIDACION", "NIVEL_RIESGO",
]

COLUMNAS_FORMULARIOS = [
    "ID_FORMULARIO", "VERSION_FORMULARIO", "MEDIDA", "SUBMEDIDA",
    "NOMBRE_FORMULARIO", "METODO_CUMPLIMIENTO",
]

# Dos responsables quedaron con el nombre en formato slug tras la migración.
# El mapa es explícito a propósito: des-sluguificar automáticamente no puede
# recuperar la acentuación y un error silencioso crearía un responsable
# fantasma que partiría sus estadísticas en dos.
SLUG_NAME_MAP = {
    "ana_mar_a_p_rez_g_mez": "Ana María Pérez Gómez",
    "luis_fernando_l_pez_d_az": "Luis Fernando López Díaz",
}

CUMPLE_VALIDOS = {"SI", "NO"}
METODO_SOPORTADO = "SI_NO_NA"
FECHA_MINIMA = pd.Timestamp("2020-01-01")


def _columnas_faltantes(df, esperadas, hoja):
    faltan = [c for c in esperadas if c not in df.columns]
    if faltan:
        raise BuildError(f"Faltan columnas en la hoja {hoja}: {faltan}")


def validate(registros, formularios):
    """Aborta el build si el Excel no tiene la forma que el dashboard asume."""
    _columnas_faltantes(registros, COLUMNAS_REGISTROS, "REGISTROS")
    _columnas_faltantes(formularios, COLUMNAS_FORMULARIOS, "FORMULARIOS")

    valores = set(registros["CUMPLE_CORRECTAMENTE"].dropna().unique())
    desconocidos = valores - CUMPLE_VALIDOS
    if desconocidos:
        raise BuildError(
            "CUMPLE_CORRECTAMENTE trae valores no soportados: "
            f"{sorted(desconocidos)}. El dashboard solo sabe interpretar "
            f"{sorted(CUMPLE_VALIDOS)} y nulo."
        )

    pct = pd.to_numeric(registros["PORCENTAJE_CUMPLIMIENTO"], errors="coerce")
    if pct.isna().any() or ((pct < 0) | (pct > 100)).any():
        raise BuildError(
            "PORCENTAJE_CUMPLIMIENTO tiene valores no numéricos o fuera de 0-100"
        )

    fechas = pd.to_datetime(registros["FECHA_EVENTO"], errors="coerce")
    if fechas.isna().any():
        raise BuildError("FECHA_EVENTO tiene valores no parseables como fecha")
    tope = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    if (fechas < FECHA_MINIMA).any() or (fechas > tope).any():
        raise BuildError(
            f"FECHA_EVENTO tiene valores fuera del rango {FECHA_MINIMA.date()} "
            f"a {tope.date()}"
        )

    metodos = set(formularios["METODO_CUMPLIMIENTO"].dropna().unique())
    usados = set(registros["ID_FORMULARIO"].unique())
    metodos_usados = set(
        formularios[formularios["ID_FORMULARIO"].isin(usados)][
            "METODO_CUMPLIMIENTO"
        ].dropna()
    )
    no_soportados = metodos_usados - {METODO_SOPORTADO}
    if no_soportados:
        raise BuildError(
            f"Hay registros de formularios con METODO_CUMPLIMIENTO "
            f"{sorted(no_soportados)}. Estos formularios no calculan "
            "cumplimiento y requieren una decisión de producto antes de "
            "incluirlos; no se pueden promediar con los SI_NO_NA."
        )
    del metodos  # solo se valida sobre los métodos realmente usados

    slugs = {
        nombre
        for nombre in registros["RESPONSABLE"].dropna().unique()
        if "_" in nombre and nombre == nombre.lower()
    }
    sin_mapear = slugs - set(SLUG_NAME_MAP)
    if sin_mapear:
        raise BuildError(
            f"Responsables con nombre en formato slug sin mapear: "
            f"{sorted(sin_mapear)}. Añádelos a SLUG_NAME_MAP con su nombre "
            "correcto y acentuado."
        )
```

- [ ] **Step 5: Ejecutar las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_build.py -v`
Expected: PASS, 10 pruebas. En particular `test_validate_pasa_sobre_el_excel_real` confirma que las reglas no rechazan los datos reales.

- [ ] **Step 6: Commit**

```bash
git add build_dashboard.py tests/test_build.py tests/conftest.py
git commit -m "feat: validate Excel structure before building"
```

---

### Task 3: `clean()` — normalización y derivadas

**Files:**
- Modify: `build_dashboard.py`
- Modify: `tests/test_build.py`

**Interfaces:**
- Consumes: `SLUG_NAME_MAP`, `BuildError`.
- Produces: `clean(registros: pd.DataFrame, formularios: pd.DataFrame) -> pd.DataFrame`. Devuelve un DataFrame con las columnas originales más `NOMBRE_FORMULARIO_ACTUAL`, `MES` (`str`, `"2026-07"`), `SEMANA` (`str`, `"2026-W27"`), `DIA` (`int`, días desde epoch) y `CUMPLE` (`int`: 1 = SI, 0 = NO, -1 = sin dictamen). Constante `AREA_NULA = "(Sin área específica)"`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir a `tests/test_build.py`:

```python
from build_dashboard import AREA_NULA, clean


def test_clean_normaliza_slug_y_respeta_los_demas(registros_ok, formularios_ok):
    limpio = clean(registros_ok, formularios_ok)
    nombres = set(limpio["RESPONSABLE"])
    assert "Ana María Pérez Gómez" in nombres
    assert "ana_mar_a_p_rez_g_mez" not in nombres
    assert "Ana Pérez" in nombres


def test_clean_rellena_areas_nulas_sin_perder_filas(registros_ok, formularios_ok):
    limpio = clean(registros_ok, formularios_ok)
    assert len(limpio) == len(registros_ok)
    assert limpio["AREA_ESPECIFICA_APLICACION"].isna().sum() == 0
    assert (limpio["AREA_ESPECIFICA_APLICACION"] == AREA_NULA).sum() == 1


def test_clean_resuelve_nombre_de_la_version_mas_reciente(
    registros_ok, formularios_ok
):
    limpio = clean(registros_ok, formularios_ok)
    f002 = limpio[limpio["ID_FORMULARIO"] == "F002"]
    assert set(f002["NOMBRE_FORMULARIO_ACTUAL"]) == {"Guantes"}


def test_clean_codifica_cumple_como_entero(registros_ok, formularios_ok):
    limpio = clean(registros_ok, formularios_ok)
    assert list(limpio["CUMPLE"]) == [1, 0, 1, -1]


def test_clean_deriva_mes_semana_y_dia(registros_ok, formularios_ok):
    limpio = clean(registros_ok, formularios_ok)
    assert list(limpio["MES"]) == ["2026-07", "2026-07", "2026-07", "2026-08"]
    assert limpio["SEMANA"].iloc[0] == "2026-W27"
    assert limpio["DIA"].iloc[0] == int(
        pd.Timestamp("2026-07-01").timestamp() // 86400
    )


def test_clean_sobre_el_excel_real_conserva_todas_las_filas():
    registros, formularios = load(XLSX)
    limpio = clean(registros, formularios)
    assert len(limpio) == 2806
    assert limpio["RESPONSABLE"].nunique() == 21
    assert limpio["ID_FORMULARIO"].nunique() == 47
    assert limpio["NOMBRE_FORMULARIO_ACTUAL"].nunique() == 47
    assert limpio["AREA_ESPECIFICA_APLICACION"].isna().sum() == 0
```

- [ ] **Step 2: Ejecutar las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_build.py -k clean -v`
Expected: FAIL con `ImportError: cannot import name 'AREA_NULA'`

- [ ] **Step 3: Escribir la implementación**

Añadir a `build_dashboard.py`:

```python
AREA_NULA = "(Sin área específica)"


def _nombres_actuales(formularios):
    """Nombre de cada formulario según su versión más alta.

    F031 cambió de nombre entre versiones, de modo que ID_FORMULARIO tiene
    47 valores distintos pero FORMULARIO tiene 48. La clave es el ID.
    """
    ordenado = formularios.sort_values("VERSION_FORMULARIO")
    ultimo = ordenado.groupby("ID_FORMULARIO").last()
    return ultimo["NOMBRE_FORMULARIO"].to_dict()


def clean(registros, formularios):
    """Normaliza valores y deriva las columnas que el dashboard agrega."""
    df = registros.copy()

    df["RESPONSABLE"] = df["RESPONSABLE"].replace(SLUG_NAME_MAP)

    df["AREA_ESPECIFICA_APLICACION"] = (
        df["AREA_ESPECIFICA_APLICACION"].fillna(AREA_NULA)
    )
    df["MOTIVO_NO_CUMPLIMIENTO"] = df["MOTIVO_NO_CUMPLIMIENTO"].fillna("")
    df["CONCLUSIONES_RECOMENDACIONES"] = (
        df["CONCLUSIONES_RECOMENDACIONES"].fillna("")
    )
    df["NIVEL_RIESGO"] = df["NIVEL_RIESGO"].fillna("(Sin nivel de riesgo)")

    nombres = _nombres_actuales(formularios)
    df["NOMBRE_FORMULARIO_ACTUAL"] = df["ID_FORMULARIO"].map(nombres)
    sin_nombre = df["NOMBRE_FORMULARIO_ACTUAL"].isna()
    if sin_nombre.any():
        ids = sorted(df.loc[sin_nombre, "ID_FORMULARIO"].unique())
        raise BuildError(
            f"Hay registros de formularios ausentes del catálogo: {ids}"
        )

    fecha = pd.to_datetime(df["FECHA_EVENTO"])
    df["MES"] = fecha.dt.strftime("%Y-%m")
    iso = fecha.dt.isocalendar()
    df["SEMANA"] = (
        iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    )
    # Días desde epoch. El cast a datetime64[D] es independiente de la
    # unidad de la columna: pandas 3 usa datetime64[us], de modo que un
    # astype("int64") daría microsegundos, no nanosegundos.
    df["DIA"] = fecha.values.astype("datetime64[D]").astype("int64")

    df["CUMPLE"] = (
        df["CUMPLE_CORRECTAMENTE"].map({"SI": 1, "NO": 0}).fillna(-1).astype(int)
    )

    return df
```

- [ ] **Step 4: Ejecutar las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_build.py -v`
Expected: PASS, 16 pruebas.

- [ ] **Step 5: Commit**

```bash
git add build_dashboard.py tests/test_build.py
git commit -m "feat: clean and derive columns from raw records"
```

---

### Task 4: `encode()` y cifras de control

**Files:**
- Modify: `build_dashboard.py`
- Modify: `tests/test_build.py`

**Interfaces:**
- Consumes: la salida de `clean()`.
- Produces: `encode(df: pd.DataFrame) -> dict` con la forma descrita en la sección 5 del spec. Claves de dimensión: `responsable`, `formulario`, `medida`, `submedida`, `unidad`, `area`, `grupo`, `cargo`, `estado`, `riesgo`, `motivo`, `mes`, `semana`. Las columnas de `rows` llevan el mismo nombre que su dimensión, más `dia`, `cumple`, `pct`, `si`, `no`, `na`.

Esta task incluye las **cifras de control**: la prueba que compara lo que produce el pipeline con un `groupby` directo de pandas sobre el Excel. Es la prueba que impide que el dashboard mienta, y por eso vive junto a `encode` en lugar de al final.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir a `tests/test_build.py`:

```python
from build_dashboard import encode


def _tasa(serie):
    """Tasa de cumplimiento sobre los registros con dictamen."""
    con_dictamen = serie[serie.isin(["SI", "NO"])]
    return (con_dictamen == "SI").sum() / len(con_dictamen)


def test_encode_construye_dimensiones_y_filas(registros_ok, formularios_ok):
    data = encode(clean(registros_ok, formularios_ok))
    assert data["dims"]["responsable"] == [
        "Ana Pérez",
        "Ana María Pérez Gómez",
    ]
    assert len(data["rows"]["cumple"]) == 4
    assert data["rows"]["cumple"] == [1, 0, 1, -1]
    assert data["dims"]["mes"] == ["2026-07", "2026-08"]


def test_encode_es_reversible(registros_ok, formularios_ok):
    limpio = clean(registros_ok, formularios_ok)
    data = encode(limpio)
    decodificado = [
        data["dims"]["responsable"][i] for i in data["rows"]["responsable"]
    ]
    assert decodificado == list(limpio["RESPONSABLE"])
    decodificado_area = [data["dims"]["area"][i] for i in data["rows"]["area"]]
    assert decodificado_area == list(limpio["AREA_ESPECIFICA_APLICACION"])


def test_encode_guarda_metadatos_de_formulario(registros_ok, formularios_ok):
    data = encode(clean(registros_ok, formularios_ok))
    assert data["forms"]["F002"]["nombre"] == "Guantes"
    assert data["forms"]["F002"]["medida"] == "Medidas estándar"


def test_encode_solo_embebe_conclusiones_de_los_que_no_cumplen(
    registros_ok, formularios_ok
):
    data = encode(clean(registros_ok, formularios_ok))
    assert list(data["texts"]["conclusiones"]) == ["1"]
    assert data["texts"]["conclusiones"]["1"] == "Reponer jabón"


def test_encode_deja_evaluado_como_texto_plano(registros_ok, formularios_ok):
    data = encode(clean(registros_ok, formularios_ok))
    assert data["texts"]["evaluado"] == ["Juan", "Luis", "Marta", "Rosa"]
    assert "evaluado" not in data["dims"]


def test_cifra_de_control_tasa_global():
    registros, formularios = load(XLSX)
    data = encode(clean(registros, formularios))
    cumple = data["rows"]["cumple"]
    con_dictamen = [c for c in cumple if c >= 0]
    del_pipeline = sum(con_dictamen) / len(con_dictamen)
    de_pandas = _tasa(registros["CUMPLE_CORRECTAMENTE"])
    assert del_pipeline == pytest.approx(de_pandas)


def test_cifra_de_control_tasa_por_responsable():
    registros, formularios = load(XLSX)
    limpio = clean(registros, formularios)
    data = encode(limpio)
    dims = data["dims"]["responsable"]
    filas = data["rows"]
    for indice, nombre in enumerate(dims):
        cumple = [
            c
            for fila, c in enumerate(filas["cumple"])
            if filas["responsable"][fila] == indice and c >= 0
        ]
        esperado = _tasa(
            limpio.loc[limpio["RESPONSABLE"] == nombre, "CUMPLE_CORRECTAMENTE"]
        )
        assert sum(cumple) / len(cumple) == pytest.approx(esperado), nombre


def test_cifra_de_control_tasa_por_mes():
    registros, formularios = load(XLSX)
    limpio = clean(registros, formularios)
    data = encode(limpio)
    dims = data["dims"]["mes"]
    filas = data["rows"]
    for indice, mes in enumerate(dims):
        cumple = [
            c
            for fila, c in enumerate(filas["cumple"])
            if filas["mes"][fila] == indice and c >= 0
        ]
        esperado = _tasa(limpio.loc[limpio["MES"] == mes, "CUMPLE_CORRECTAMENTE"])
        assert sum(cumple) / len(cumple) == pytest.approx(esperado), mes
```

- [ ] **Step 2: Ejecutar las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_build.py -k encode -v`
Expected: FAIL con `ImportError: cannot import name 'encode'`

- [ ] **Step 3: Escribir la implementación**

Añadir a `build_dashboard.py`:

```python
# columna del DataFrame limpio -> clave de dimensión en DATA
DIMENSIONES = {
    "RESPONSABLE": "responsable",
    "ID_FORMULARIO": "formulario",
    "MEDIDA": "medida",
    "SUBMEDIDA": "submedida",
    "UNIDAD_SERVICIO_APLICACION": "unidad",
    "AREA_ESPECIFICA_APLICACION": "area",
    "GRUPO_OCUPACIONAL": "grupo",
    "CARGO": "cargo",
    "ESTADO_VALIDACION": "estado",
    "NIVEL_RIESGO": "riesgo",
    "MOTIVO_NO_CUMPLIMIENTO": "motivo",
    "MES": "mes",
    "SEMANA": "semana",
}


def encode(df):
    """Codifica el DataFrame limpio en diccionarios + columnas paralelas."""
    dims = {}
    rows = {}
    for columna, clave in DIMENSIONES.items():
        categoria = df[columna].astype("category")
        # Orden alfabético para que el archivo sea determinista entre builds.
        categoria = categoria.cat.reorder_categories(
            sorted(categoria.cat.categories)
        )
        dims[clave] = list(categoria.cat.categories)
        rows[clave] = [int(c) for c in categoria.cat.codes]

    rows["dia"] = [int(v) for v in df["DIA"]]
    rows["cumple"] = [int(v) for v in df["CUMPLE"]]
    rows["pct"] = [int(v) for v in df["PORCENTAJE_CUMPLIMIENTO"]]
    rows["si"] = [int(v) for v in df["TOTAL_SI"]]
    rows["no"] = [int(v) for v in df["TOTAL_NO"]]
    rows["na"] = [int(v) for v in df["TOTAL_NA"]]

    forms = {}
    for id_form, grupo in df.groupby("ID_FORMULARIO"):
        ultima = grupo.sort_values("VERSION_FORMULARIO").iloc[-1]
        forms[id_form] = {
            "nombre": ultima["NOMBRE_FORMULARIO_ACTUAL"],
            "version": int(ultima["VERSION_FORMULARIO"]),
            "medida": ultima["MEDIDA"],
            "submedida": ultima["SUBMEDIDA"],
        }

    # Las conclusiones solo se consultan sobre lo que falló; embeberlas todas
    # duplicaría el peso del archivo sin que nadie las lea.
    conclusiones = {
        str(i): texto
        for i, (cumple, texto) in enumerate(
            zip(df["CUMPLE"], df["CONCLUSIONES_RECOMENDACIONES"])
        )
        if cumple == 0 and texto
    }

    return {
        "dims": dims,
        "forms": forms,
        "rows": rows,
        # NOMBRE_EVALUADO tiene 2012 valores distintos sobre 2806 filas: el
        # diccionario no comprimiría nada. No es dimensión de agregación.
        "texts": {
            "evaluado": [str(v) for v in df["NOMBRE_EVALUADO"]],
            "conclusiones": conclusiones,
        },
        "meta": {
            "generado": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
            "filas": len(df),
            "dia_min": int(df["DIA"].min()),
            "dia_max": int(df["DIA"].max()),
        },
    }
```

- [ ] **Step 4: Ejecutar las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_build.py -v`
Expected: PASS, 24 pruebas. Las tres cifras de control confirman que la tasa global, por responsable y por mes coinciden con pandas.

- [ ] **Step 5: Commit**

```bash
git add build_dashboard.py tests/test_build.py
git commit -m "feat: encode clean data into dictionary + column format

Includes control-figure tests comparing pipeline rates against direct
pandas groupby results, per spec section 8."
```

---

### Task 5: Plantilla base, tokens de color y `render_html()`

**Files:**
- Create: `template.html`
- Modify: `build_dashboard.py`
- Modify: `tests/test_build.py`
- Create: `vendor/chart.umd.min.js` (descargado)

**Interfaces:**
- Consumes: la salida de `encode()`.
- Produces: `render_html(data: dict, template: Path, vendor: Path, salida: Path) -> int` que devuelve los bytes escritos. `main()`, el punto de entrada.

Al terminar esta task, `python build_dashboard.py` produce un `dashboard.html` que abre, muestra los tokens aplicados y una cabecera con los metadatos. Todavía no hay gráficos.

- [ ] **Step 1: Descargar Chart.js**

```bash
curl -L https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js -o vendor/chart.umd.min.js
ls -l vendor/chart.umd.min.js
```

Expected: un archivo de aproximadamente 200 KB. Si la descarga falla, cualquier copia de Chart.js 4.4.x sirve; el código solo usa API estable de la v4.

- [ ] **Step 2: Escribir la prueba que falla**

Añadir a `tests/test_build.py`:

```python
from build_dashboard import render_html

TEMPLATE = Path(__file__).resolve().parent.parent / "template.html"
VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "chart.umd.min.js"


def test_render_html_produce_un_archivo_sin_urls_externas(tmp_path):
    registros, formularios = load(XLSX)
    data = encode(clean(registros, formularios))
    salida = tmp_path / "dashboard.html"
    escritos = render_html(data, TEMPLATE, VENDOR, salida)

    html = salida.read_text(encoding="utf-8")
    assert escritos == len(html.encode("utf-8"))
    assert "/*__DATA__*/" not in html
    assert "/*__CHARTJS__*/" not in html
    assert "Chart" in html
    assert "https://" not in html
    assert "http://" not in html


def test_render_html_embebe_los_datos_reales(tmp_path):
    registros, formularios = load(XLSX)
    data = encode(clean(registros, formularios))
    salida = tmp_path / "dashboard.html"
    render_html(data, TEMPLATE, VENDOR, salida)
    html = salida.read_text(encoding="utf-8")
    assert "Ana María Pérez Gómez" in html
    assert "ana_mar_a_p_rez_g_mez" not in html
```

- [ ] **Step 3: Ejecutar la prueba para verificar que falla**

Run: `python -m pytest tests/test_build.py -k render -v`
Expected: FAIL con `ImportError: cannot import name 'render_html'`

- [ ] **Step 4: Escribir la plantilla**

`template.html`. Los tokens salen de `references/palette.md` de la skill `dataviz`; los valores oscuros son pasos elegidos para la superficie oscura, no una inversión.

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Supervisiones PCI</title>
<style>
:root {
  color-scheme: light;
  --plane:          #f9f9f7;
  --surface:        #fcfcfb;
  --text-primary:   #0b0b0b;
  --text-secondary: #52514e;
  --text-muted:     #898781;
  --grid:           #e1e0d9;
  --axis:           #c3c2b7;
  --border:         rgba(11,11,11,0.10);
  --series-1:       #2a78d6;
  --series-2:       #eb6834;
  --context:        #c3c2b7;
  --good:           #0ca30c;
  --critical:       #d03b3b;
  --warning:        #fab219;
  --serious:        #ec835a;
  --seq-100: #cde2fb; --seq-250: #86b6ef; --seq-400: #3987e5;
  --seq-550: #1c5cab; --seq-700: #0d366b;
  --sans: system-ui, -apple-system, "Segoe UI", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --plane: #0d0d0d; --surface: #1a1a19;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #d95926; --context: #52514e;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --plane: #0d0d0d; --surface: #1a1a19;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --series-1: #3987e5; --series-2: #d95926; --context: #52514e;
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--plane); color: var(--text-primary);
  font-family: var(--sans); font-size: 14px; line-height: 1.5;
}
.wrap { max-width: 1200px; margin: 0 auto; padding: 24px 20px 64px; }
h1 { font-size: 20px; font-weight: 600; margin: 0; }
h2 { font-size: 15px; font-weight: 600; margin: 0 0 4px; }
.sub { color: var(--text-secondary); font-size: 13px; }

.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px 18px; margin-bottom: 16px;
}
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 860px) { .grid-2 { grid-template-columns: 1fr; } }

/* El contenedor crece con su contenido: fijar la altura recortaría la
   banda del eje X y crearía un scroll anidado dentro del card. */
.plot { position: relative; height: 260px; }

.kpis { display: flex; flex-wrap: wrap; gap: 12px; }
.kpi {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 16px; min-width: 150px; flex: 1;
}
.kpi .label { color: var(--text-secondary); font-size: 12px; }
.kpi .value { font-size: 26px; font-weight: 600; margin-top: 2px; }
.kpi .delta { font-size: 12px; color: var(--text-secondary); }
.hero { font-size: 48px; font-weight: 600; line-height: 1.1; }

table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--grid); }
th { color: var(--text-secondary); font-weight: 600; cursor: pointer; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.scroll-x { overflow-x: auto; }

.tabs { display: flex; gap: 4px; margin-bottom: 16px; }
.tabs button {
  font: inherit; padding: 7px 14px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--border); background: transparent; color: var(--text-secondary);
}
.tabs button[aria-selected="true"] {
  background: var(--surface); color: var(--text-primary); font-weight: 600;
}

.filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; margin-bottom: 12px; }
.filters label { display: flex; flex-direction: column; font-size: 12px; color: var(--text-secondary); gap: 3px; }
.filters select, .filters input {
  font: inherit; font-size: 13px; padding: 5px 8px; border-radius: 7px;
  border: 1px solid var(--border); background: var(--surface); color: var(--text-primary);
}
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
.chip {
  font-size: 12px; padding: 3px 8px; border-radius: 999px;
  border: 1px solid var(--border); background: var(--surface); cursor: pointer;
}
.empty { color: var(--text-secondary); padding: 28px 0; text-align: center; }

/* Mapa de calor: CSS Grid en lugar de un plugin de Chart.js. Menos código,
   control total del gap de 2px y de los tooltips. */
.heat { display: grid; gap: 2px; font-size: 11px; }
.heat .cell { padding: 6px 4px; text-align: center; border-radius: 3px; }
.heat .rowlab, .heat .collab { color: var(--text-secondary); padding: 4px; }
.heat .rowlab { text-align: right; white-space: nowrap; }

.tip {
  position: fixed; pointer-events: none; z-index: 20; display: none;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; font-size: 12px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.14); max-width: 280px;
}
.tip .v { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.tip .k { display: inline-block; width: 14px; height: 2px; vertical-align: middle; margin-right: 6px; }
.tip .n { color: var(--text-secondary); }
</style>
</head>
<body>
<div class="wrap">
  <header style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin-bottom:18px">
    <div>
      <h1>Supervisiones PCI</h1>
      <div class="sub" id="meta"></div>
    </div>
    <button id="theme" class="chip" type="button">Cambiar tema</button>
  </header>

  <div class="tabs" role="tablist">
    <button role="tab" data-view="global" aria-selected="true">Global</button>
    <button role="tab" data-view="responsable" aria-selected="false">Por responsable</button>
    <button role="tab" data-view="formulario" aria-selected="false">Por formulario</button>
  </div>

  <div class="filters" id="filters"></div>
  <div class="chips" id="chips"></div>
  <main id="view"></main>
</div>
<div class="tip" id="tip"></div>

<script>/*__CHARTJS__*/</script>
<script>const DATA = /*__DATA__*/;</script>
<script id="mod-store"></script>
<script id="mod-agg"></script>
<script id="mod-charts"></script>
<script id="mod-views"></script>
<script id="mod-app">
document.getElementById('meta').textContent =
  DATA.meta.filas + ' supervisiones · generado ' + DATA.meta.generado;
document.getElementById('theme').addEventListener('click', () => {
  const actual = document.documentElement.getAttribute('data-theme');
  document.documentElement.setAttribute('data-theme', actual === 'dark' ? 'light' : 'dark');
  window.dispatchEvent(new Event('themechange'));
});
</script>
</body>
</html>
```

- [ ] **Step 5: Escribir `render_html()` y `main()`**

Añadir a `build_dashboard.py`:

```python
import json
import sys


def render_html(data, template, vendor, salida):
    """Inyecta datos y Chart.js en la plantilla. Devuelve bytes escritos."""
    html = Path(template).read_text(encoding="utf-8")
    chartjs = Path(vendor).read_text(encoding="utf-8")

    # ensure_ascii=False mantiene los acentos legibles y pesa menos que \uXXXX.
    # separators sin espacios recorta cerca de un 8% del JSON.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # </script> dentro de una cadena JSON cerraría el bloque antes de tiempo.
    payload = payload.replace("</", "<\\/")

    html = html.replace("/*__CHARTJS__*/", chartjs)
    html = html.replace("/*__DATA__*/", payload)

    salida = Path(salida)
    salida.write_text(html, encoding="utf-8")
    return len(html.encode("utf-8"))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    raiz = Path(__file__).resolve().parent
    origen = Path(argv[0]) if argv else raiz / "SupPCI.xlsx"
    salida = raiz / "dashboard.html"

    registros, formularios = load(origen)
    print(f"Leídas {len(registros)} filas de REGISTROS")

    validate(registros, formularios)

    limpio = clean(registros, formularios)
    slugs = sum(registros["RESPONSABLE"].isin(SLUG_NAME_MAP))
    areas = int(registros["AREA_ESPECIFICA_APLICACION"].isna().sum())
    print(f"Nombres normalizados: {slugs}")
    print(f"Áreas nulas rellenadas como «{AREA_NULA}»: {areas}")
    print(f"Filas descartadas: {len(registros) - len(limpio)}")

    data = encode(limpio)
    escritos = render_html(
        data, raiz / "template.html", raiz / "vendor" / "chart.umd.min.js", salida
    )
    print(f"Escrito {salida} — {escritos / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Ejecutar las pruebas y el build**

```bash
python -m pytest tests/test_build.py -v
python build_dashboard.py
```

Expected: 26 pruebas PASS. El build imprime el resumen y escribe `dashboard.html`. Comprobar que el tamaño está en el rango previsto (1.0–1.4 MB con Chart.js incluido).

- [ ] **Step 7: Abrir el archivo y mirarlo**

Abrir `dashboard.html` en el navegador. Debe mostrar la cabecera con el conteo de filas y la fecha de generación, las tres pestañas y el botón de tema. El botón de tema debe cambiar el fondo entre claro y oscuro. Todavía no hay contenido en las vistas.

- [ ] **Step 8: Commit**

```bash
git add template.html build_dashboard.py tests/test_build.py
git commit -m "feat: render self-contained HTML with embedded data and Chart.js"
```

---

### Task 6: Módulo `store` — estado de filtros

**Files:**
- Modify: `template.html` (bloque `#mod-store`)
- Create: `tests/test_agg.html`

**Interfaces:**
- Consumes: la constante global `DATA`.
- Produces: el objeto global `store` con `store.filters`, `store.activeRows() -> number[]`, `store.set(clave, valor)`, `store.clear(clave)`, `store.clearAll()`, `store.onChange(fn)`, `store.emit()`. Las claves de filtro son `desde`, `hasta` (días desde epoch) más `medida`, `submedida`, `unidad`, `grupo`, `cargo`, `estado` (índices de dimensión, `null` = sin filtrar).

- [ ] **Step 1: Escribir el harness de pruebas que falla**

`tests/test_agg.html`. El harness es intencionadamente mínimo: `store` y `agg` son funciones puras, así que basta con aserciones sobre un `DATA` sintético.

```html
<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><title>Pruebas de agg</title>
<style>body{font-family:system-ui,sans-serif;padding:20px}
.ok{color:#0ca30c}.fail{color:#d03b3b;font-weight:600}</style>
</head>
<body>
<h1>Pruebas de store y agg</h1>
<div id="out"></div>

<script>
// DATA sintético: 5 filas, 2 responsables, 2 meses.
// Ana: SI, NO, SI -> tasa 2/3. Beto: SI, sin dictamen -> tasa 1/1.
const DATA = {
  dims: {
    responsable: ["Ana", "Beto"],
    formulario: ["F001", "F002"],
    medida: ["Estándar", "Específica"],
    submedida: ["Higiene", "Barreras"],
    unidad: ["UCI", "Emergencia"],
    area: ["Box 1", "Triage"],
    grupo: ["Enfermería", "Medicina"],
    cargo: ["Técnico", "Jefe"],
    estado: ["Aprobado", "En espera"],
    riesgo: ["(Sin nivel de riesgo)", "Alto"],
    motivo: ["", "Sin insumos"],
    mes: ["2026-07", "2026-08"],
    semana: ["2026-W27", "2026-W28", "2026-W32"]
  },
  forms: {
    F001: {nombre: "Lavado", version: 1, medida: "Estándar", submedida: "Higiene"},
    F002: {nombre: "Guantes", version: 2, medida: "Específica", submedida: "Barreras"}
  },
  rows: {
    responsable: [0, 0, 0, 1, 1],
    formulario:  [0, 0, 1, 1, 1],
    medida:      [0, 0, 1, 1, 1],
    submedida:   [0, 0, 1, 1, 1],
    unidad:      [0, 1, 0, 0, 1],
    area:        [0, 1, 0, 1, 0],
    grupo:       [0, 0, 1, 1, 0],
    cargo:       [0, 0, 0, 0, 1],
    estado:      [0, 1, 1, 1, 1],
    riesgo:      [0, 1, 0, 0, 0],
    motivo:      [0, 1, 0, 0, 0],
    mes:         [0, 0, 1, 0, 1],
    semana:      [0, 1, 2, 1, 2],
    dia:         [20635, 20642, 20670, 20642, 20670],
    cumple:      [1, 0, 1, 1, -1],
    pct:         [100, 60, 100, 90, 80],
    si:          [5, 3, 4, 4, 4],
    no:          [0, 2, 0, 1, 0],
    na:          [1, 1, 2, 0, 0]
  },
  texts: {
    evaluado: ["Juan", "Luis", "Marta", "Rosa", "Ema"],
    conclusiones: {"1": "Reponer jabón"}
  },
  meta: {generado: "2026-08-24 09:00", filas: 5, dia_min: 20635, dia_max: 20670}
};

let pasadas = 0, fallidas = 0;
function check(nombre, real, esperado) {
  const a = JSON.stringify(real), b = JSON.stringify(esperado);
  const ok = a === b;
  ok ? pasadas++ : fallidas++;
  const linea = document.createElement('div');
  linea.className = ok ? 'ok' : 'fail';
  linea.textContent = (ok ? 'PASA  ' : 'FALLA ') + nombre +
    (ok ? '' : ` — esperado ${b}, obtenido ${a}`);
  document.getElementById('out').appendChild(linea);
}
function resumen() {
  const linea = document.createElement('h2');
  linea.textContent = `${pasadas} pasan, ${fallidas} fallan`;
  linea.className = fallidas ? 'fail' : 'ok';
  document.getElementById('out').appendChild(linea);
}
</script>

<!-- Los módulos bajo prueba se pegan aquí, copiados de template.html -->
<script id="mod-store"></script>
<script id="mod-agg"></script>

<script>
check('sin filtros devuelve todas las filas', store.activeRows(), [0,1,2,3,4]);
store.set('unidad', 0);
check('filtro por unidad UCI', store.activeRows(), [0,2,3]);
store.clearAll();
store.set('desde', 20660);
check('filtro por fecha desde', store.activeRows(), [2,4]);
store.clearAll();
store.set('medida', 1); store.set('cargo', 0);
check('dos filtros se combinan con AND', store.activeRows(), [2,3]);
store.clearAll();
check('clearAll restaura todo', store.activeRows(), [0,1,2,3,4]);
resumen();
</script>
</body>
</html>
```

- [ ] **Step 2: Abrir el harness para verificar que falla**

Abrir `tests/test_agg.html` en el navegador.
Expected: la consola muestra `ReferenceError: store is not defined` y no aparece ninguna línea de resultado.

- [ ] **Step 3: Escribir el módulo `store`**

En `template.html`, rellenar `<script id="mod-store">`:

```js
const store = (() => {
  const DIMS_FILTRABLES = [
    'medida', 'submedida', 'unidad', 'grupo', 'cargo', 'estado'
  ];
  const filters = {desde: null, hasta: null};
  DIMS_FILTRABLES.forEach(k => { filters[k] = null; });

  const oyentes = [];
  const n = DATA.rows.cumple.length;

  function activeRows() {
    const r = DATA.rows;
    const out = [];
    for (let i = 0; i < n; i++) {
      if (filters.desde !== null && r.dia[i] < filters.desde) continue;
      if (filters.hasta !== null && r.dia[i] > filters.hasta) continue;
      let pasa = true;
      for (const k of DIMS_FILTRABLES) {
        if (filters[k] !== null && r[k][i] !== filters[k]) { pasa = false; break; }
      }
      if (pasa) out.push(i);
    }
    return out;
  }

  function set(clave, valor) { filters[clave] = valor; emit(); }
  function clear(clave) { filters[clave] = null; emit(); }
  function clearAll() {
    Object.keys(filters).forEach(k => { filters[k] = null; });
    emit();
  }
  function onChange(fn) { oyentes.push(fn); }
  function emit() { oyentes.forEach(fn => fn()); }

  return {filters, dimsFiltrables: DIMS_FILTRABLES,
          activeRows, set, clear, clearAll, onChange, emit};
})();
```

- [ ] **Step 4: Copiar el módulo al harness y ejecutar**

Copiar el mismo código dentro de `<script id="mod-store">` en `tests/test_agg.html` y recargar.
Expected: las cinco líneas de `store` muestran PASA. El resumen dirá que las de `agg` aún no existen, porque ese bloque está vacío — eso se resuelve en la Task 7.

Nota para quien ejecute: el harness duplica el código de los módulos a propósito. Extraer los módulos a archivos `.js` separados rompería el requisito de HTML autocontenido y offline, y no hay build step de JavaScript en este proyecto.

- [ ] **Step 5: Commit**

```bash
git add template.html tests/test_agg.html
git commit -m "feat: add filter store with browser test harness"
```

---

### Task 7: Módulo `agg` — agregaciones puras

**Files:**
- Modify: `template.html` (bloque `#mod-agg`)
- Modify: `tests/test_agg.html`

**Interfaces:**
- Consumes: `DATA`, `store.activeRows()`.
- Produces: el objeto global `agg` con:
  - `agg.kpis(rows) -> {total, conDictamen, sinDictamen, tasa, aprobados, tasaAprobado, responsables, formularios}`. `tasa` es `null` cuando `conDictamen === 0`.
  - `agg.rateBy(rows, dimKey) -> [{idx, label, si, no, sin, total, tasa}]` ordenado por `tasa` descendente, con los de `tasa === null` al final.
  - `agg.series(rows, periodo) -> {labels, tasa, volumen}` donde `periodo` es `'mes'` o `'semana'`. `tasa[i]` es `null` si ese periodo no tiene registros con dictamen.
  - `agg.heatmap(rows, dimKey, periodo) -> {rowLabels, colLabels, cells}` con `cells[f][c] = {tasa, total}`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir al bloque final de `tests/test_agg.html`, antes de `resumen()`:

```js
store.clearAll();
const todas = store.activeRows();

const k = agg.kpis(todas);
check('kpis total', k.total, 5);
check('kpis con dictamen', k.conDictamen, 4);
check('kpis sin dictamen', k.sinDictamen, 1);
check('kpis tasa', k.tasa, 0.75);
check('kpis responsables', k.responsables, 2);
check('kpis formularios', k.formularios, 2);

const porResp = agg.rateBy(todas, 'responsable');
check('rateBy ordena por tasa descendente',
      porResp.map(f => f.label), ['Beto', 'Ana']);
check('rateBy tasa de Ana', porResp[1].tasa, 2 / 3);
check('rateBy total de Beto cuenta el sin dictamen', porResp[0].total, 2);
check('rateBy con dictamen de Beto', porResp[0].si + porResp[0].no, 1);

const mes = agg.series(todas, 'mes');
check('series etiquetas de mes', mes.labels, ['2026-07', '2026-08']);
check('series volumen por mes', mes.volumen, [3, 2]);
check('series tasa de julio', mes.tasa[0], 2 / 3);
check('series tasa de agosto', mes.tasa[1], 1);

const semana = agg.series(todas, 'semana');
check('series etiquetas de semana', semana.labels,
      ['2026-W27', '2026-W28', '2026-W32']);
check('series volumen por semana', semana.volumen, [1, 2, 2]);

const calor = agg.heatmap(todas, 'submedida', 'mes');
check('heatmap filas', calor.rowLabels, ['Higiene', 'Barreras']);
check('heatmap columnas', calor.colLabels, ['2026-07', '2026-08']);
check('heatmap celda Barreras/agosto', calor.cells[1][1], {tasa: 1, total: 2});
check('heatmap celda vacía es null',
      calor.cells[0][1], {tasa: null, total: 0});

const vacio = agg.kpis([]);
check('kpis sobre conjunto vacío no divide por cero', vacio.tasa, null);
check('series sobre conjunto vacío', agg.series([], 'mes').labels, []);
```

- [ ] **Step 2: Recargar el harness para verificar que falla**

Abrir `tests/test_agg.html`.
Expected: `ReferenceError: agg is not defined`.

- [ ] **Step 3: Escribir el módulo `agg`**

En `template.html`, rellenar `<script id="mod-agg">`:

```js
const agg = (() => {
  const r = DATA.rows;

  /** Tasa sobre los registros con dictamen. null si no hay ninguno. */
  function tasaDe(si, no) {
    const conDictamen = si + no;
    return conDictamen === 0 ? null : si / conDictamen;
  }

  function kpis(rows) {
    let si = 0, no = 0, sin = 0, aprobados = 0;
    const resp = new Set(), form = new Set();
    const idxAprobado = DATA.dims.estado.indexOf('Aprobado');
    for (const i of rows) {
      if (r.cumple[i] === 1) si++;
      else if (r.cumple[i] === 0) no++;
      else sin++;
      if (r.estado[i] === idxAprobado) aprobados++;
      resp.add(r.responsable[i]);
      form.add(r.formulario[i]);
    }
    return {
      total: rows.length,
      conDictamen: si + no,
      sinDictamen: sin,
      tasa: tasaDe(si, no),
      aprobados,
      tasaAprobado: rows.length ? aprobados / rows.length : null,
      responsables: resp.size,
      formularios: form.size
    };
  }

  function rateBy(rows, dimKey) {
    const etiquetas = DATA.dims[dimKey];
    const acc = new Map();
    for (const i of rows) {
      const idx = r[dimKey][i];
      let e = acc.get(idx);
      if (!e) { e = {idx, label: etiquetas[idx], si: 0, no: 0, sin: 0}; acc.set(idx, e); }
      if (r.cumple[i] === 1) e.si++;
      else if (r.cumple[i] === 0) e.no++;
      else e.sin++;
    }
    const salida = [...acc.values()];
    for (const e of salida) {
      e.total = e.si + e.no + e.sin;
      e.tasa = tasaDe(e.si, e.no);
    }
    // Los que no tienen dictamen van al final: no son "los peores", son
    // "los que no se pueden puntuar".
    salida.sort((a, b) => {
      if (a.tasa === null && b.tasa === null) return b.total - a.total;
      if (a.tasa === null) return 1;
      if (b.tasa === null) return -1;
      return b.tasa - a.tasa || b.total - a.total;
    });
    return salida;
  }

  function series(rows, periodo) {
    const etiquetas = DATA.dims[periodo];
    const presentes = new Set();
    const si = new Map(), no = new Map(), vol = new Map();
    for (const i of rows) {
      const p = r[periodo][i];
      presentes.add(p);
      vol.set(p, (vol.get(p) || 0) + 1);
      if (r.cumple[i] === 1) si.set(p, (si.get(p) || 0) + 1);
      else if (r.cumple[i] === 0) no.set(p, (no.get(p) || 0) + 1);
    }
    // dims.mes y dims.semana vienen ordenados alfabéticamente desde Python,
    // que para "YYYY-MM" y "YYYY-Www" equivale al orden cronológico.
    const orden = [...presentes].sort((a, b) => a - b);
    return {
      labels: orden.map(p => etiquetas[p]),
      volumen: orden.map(p => vol.get(p) || 0),
      tasa: orden.map(p => tasaDe(si.get(p) || 0, no.get(p) || 0))
    };
  }

  function heatmap(rows, dimKey, periodo) {
    const filasPresentes = new Set(), colsPresentes = new Set();
    const si = new Map(), no = new Map(), tot = new Map();
    const clave = (f, c) => f + '|' + c;
    for (const i of rows) {
      const f = r[dimKey][i], c = r[periodo][i];
      filasPresentes.add(f); colsPresentes.add(c);
      const k = clave(f, c);
      tot.set(k, (tot.get(k) || 0) + 1);
      if (r.cumple[i] === 1) si.set(k, (si.get(k) || 0) + 1);
      else if (r.cumple[i] === 0) no.set(k, (no.get(k) || 0) + 1);
    }
    const fs = [...filasPresentes].sort((a, b) => a - b);
    const cs = [...colsPresentes].sort((a, b) => a - b);
    return {
      rowLabels: fs.map(f => DATA.dims[dimKey][f]),
      colLabels: cs.map(c => DATA.dims[periodo][c]),
      cells: fs.map(f => cs.map(c => {
        const k = clave(f, c);
        return {
          tasa: tasaDe(si.get(k) || 0, no.get(k) || 0),
          total: tot.get(k) || 0
        };
      }))
    };
  }

  return {kpis, rateBy, series, heatmap, tasaDe};
})();
```

- [ ] **Step 4: Copiar al harness y ejecutar**

Copiar el módulo dentro de `<script id="mod-agg">` en `tests/test_agg.html` y recargar.
Expected: `26 pasan, 0 fallan`.

- [ ] **Step 5: Commit**

```bash
git add template.html tests/test_agg.html
git commit -m "feat: add pure aggregation module with browser tests"
```

---

### Task 8: Módulo `charts` — envoltura de Chart.js y tooltips

**Files:**
- Modify: `template.html` (bloque `#mod-charts`)

**Interfaces:**
- Consumes: `Chart` global, tokens CSS.
- Produces: el objeto global `charts` con:
  - `charts.line(canvas, {labels, series, formato})` donde `series` es `[{label, data, color, ancho}]`. Traza líneas de 2px con crosshair.
  - `charts.bars(canvas, {labels, values, formato, etiquetar})` barras horizontales de una serie, color slot 1.
  - `charts.columns(canvas, {labels, values, formato})` columnas verticales de una serie.
  - `charts.heat(contenedor, {rowLabels, colLabels, cells})` mapa de calor en CSS Grid.
  - `charts.tabla(contenedor, columnas, filas)` tabla ordenable, la vista equivalente de cada gráfico.
  - `charts.destroyAll()` destruye todas las instancias vivas.
  - `charts.token(nombre)` lee un token CSS del `:root` actual.

Todas las etiquetas de datos se insertan con `textContent`. Ningún gráfico tiene eje Y secundario.

- [ ] **Step 1: Escribir el módulo**

En `template.html`, rellenar `<script id="mod-charts">`:

```js
const charts = (() => {
  const vivos = new Set();
  const tip = document.getElementById('tip');

  function token(nombre) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue('--' + nombre).trim();
  }

  const pct = v => v === null ? '—' : (v * 100).toFixed(1) + '%';
  const num = v => v === null ? '—' : v.toLocaleString('es');

  function destroyAll() {
    vivos.forEach(c => c.destroy());
    vivos.clear();
  }

  /** Tooltip HTML propio: el valor manda, el nombre de la serie acompaña. */
  function mostrarTip(x, y, filas) {
    tip.replaceChildren();
    for (const f of filas) {
      const linea = document.createElement('div');
      if (f.color) {
        const key = document.createElement('span');
        key.className = 'k';
        key.style.background = f.color;
        linea.appendChild(key);
      }
      const v = document.createElement('span');
      v.className = 'v';
      v.textContent = f.valor;
      linea.appendChild(v);
      if (f.nombre) {
        const nm = document.createElement('span');
        nm.className = 'n';
        nm.textContent = ' ' + f.nombre;
        linea.appendChild(nm);
      }
      tip.appendChild(linea);
    }
    tip.style.display = 'block';
    // Reposicionar tras medir, para no salirse del viewport.
    const caja = tip.getBoundingClientRect();
    const izq = Math.min(x + 14, window.innerWidth - caja.width - 8);
    const arr = Math.min(y + 14, window.innerHeight - caja.height - 8);
    tip.style.left = izq + 'px';
    tip.style.top = arr + 'px';
  }
  function ocultarTip() { tip.style.display = 'none'; }

  const base = () => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: {mode: 'index', intersect: false},
    plugins: {legend: {display: false}, tooltip: {enabled: false}},
    scales: {
      x: {
        grid: {display: false},
        border: {color: token('axis')},
        ticks: {color: token('text-muted'), font: {family: token('sans'), size: 11}}
      },
      y: {
        grid: {color: token('grid'), lineWidth: 1},
        border: {display: false},
        ticks: {color: token('text-muted'), font: {family: token('sans'), size: 11}}
      }
    }
  });

  function enganchaTip(canvas, grafico, describir) {
    const mover = ev => {
      const puntos = grafico.getElementsAtEventForMode(
        ev, 'index', {intersect: false}, false);
      if (!puntos.length) { ocultarTip(); return; }
      mostrarTip(ev.clientX, ev.clientY, describir(puntos[0].index));
    };
    canvas.addEventListener('pointermove', mover);
    canvas.addEventListener('pointerleave', ocultarTip);
    // El teclado ve lo mismo que el puntero.
    canvas.tabIndex = 0;
    let foco = 0;
    canvas.addEventListener('keydown', ev => {
      if (ev.key !== 'ArrowLeft' && ev.key !== 'ArrowRight') return;
      ev.preventDefault();
      const n = grafico.data.labels.length;
      foco = (foco + (ev.key === 'ArrowRight' ? 1 : n - 1)) % n;
      const caja = canvas.getBoundingClientRect();
      mostrarTip(caja.left + caja.width * (foco + 0.5) / n,
                 caja.top + 20, describir(foco));
    });
    canvas.addEventListener('blur', ocultarTip);
  }

  function line(canvas, {labels, series, formato = pct}) {
    const opciones = base();
    if (formato === pct) {
      opciones.scales.y.min = 0;
      opciones.scales.y.max = 1;
      opciones.scales.y.ticks.callback = v => (v * 100) + '%';
    }
    const grafico = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: series.map(s => ({
          label: s.label,
          data: s.data,
          borderColor: s.color,
          backgroundColor: s.color,
          borderWidth: s.ancho || 2,
          pointRadius: 4,             // marcador de 8px de diámetro
          pointHoverRadius: 6,
          pointBorderColor: token('surface'),
          pointBorderWidth: 2,        // anillo de superficie
          spanGaps: true,
          tension: 0
        }))
      },
      options: opciones
    });
    vivos.add(grafico);
    enganchaTip(canvas, grafico, i => [
      {valor: labels[i], nombre: ''},
      ...series.map(s => ({
        color: s.color, valor: formato(s.data[i]), nombre: s.label
      }))
    ]);
    return grafico;
  }

  function _barras(canvas, {labels, values, formato, horizontal}) {
    const opciones = base();
    opciones.indexAxis = horizontal ? 'y' : 'x';
    if (horizontal) {
      opciones.scales.x.grid = {color: token('grid'), lineWidth: 1};
      opciones.scales.y.grid = {display: false};
      if (formato === pct) {
        opciones.scales.x.min = 0;
        opciones.scales.x.max = 1;
        opciones.scales.x.ticks.callback = v => (v * 100) + '%';
      }
    } else if (formato === pct) {
      opciones.scales.y.min = 0;
      opciones.scales.y.max = 1;
      opciones.scales.y.ticks.callback = v => (v * 100) + '%';
    }
    const grafico = new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: token('series-1'),
          borderRadius: 4,            // extremo de datos redondeado
          borderSkipped: 'start',     // cuadrado en la línea base
          maxBarThickness: 24,
          // El hueco entre barras lo hace la superficie, no un borde.
          categoryPercentage: 0.82,
          barPercentage: 0.92
        }]
      },
      options: opciones
    });
    vivos.add(grafico);
    return grafico;
  }

  function bars(canvas, cfg) {
    const grafico = _barras(canvas, {...cfg, horizontal: true});
    enganchaTip(canvas, grafico, i => [
      {valor: (cfg.formato || pct)(cfg.values[i]), nombre: cfg.labels[i]},
      ...(cfg.extra ? [{valor: cfg.extra[i], nombre: ''}] : [])
    ]);
    return grafico;
  }

  function columns(canvas, cfg) {
    const grafico = _barras(canvas, {...cfg, horizontal: false});
    enganchaTip(canvas, grafico, i => [
      {valor: (cfg.formato || num)(cfg.values[i]), nombre: cfg.labels[i]}
    ]);
    return grafico;
  }

  /** Mapa de calor en CSS Grid. Rampa secuencial de un solo tono. */
  function heat(contenedor, {rowLabels, colLabels, cells}) {
    const pasos = ['seq-100', 'seq-250', 'seq-400', 'seq-550', 'seq-700']
      .map(token);
    contenedor.replaceChildren();
    const reja = document.createElement('div');
    reja.className = 'heat';
    reja.style.gridTemplateColumns =
      `max-content repeat(${colLabels.length}, minmax(52px, 1fr))`;

    reja.appendChild(document.createElement('div'));  // esquina vacía
    for (const c of colLabels) {
      const celda = document.createElement('div');
      celda.className = 'collab';
      celda.style.textAlign = 'center';
      celda.textContent = c;
      reja.appendChild(celda);
    }

    rowLabels.forEach((etiqueta, f) => {
      const lab = document.createElement('div');
      lab.className = 'rowlab';
      lab.textContent = etiqueta;
      reja.appendChild(lab);
      cells[f].forEach((celda, c) => {
        const div = document.createElement('div');
        div.className = 'cell';
        if (celda.total === 0 || celda.tasa === null) {
          div.style.background = 'transparent';
          div.style.color = token('text-muted');
          div.textContent = '·';
        } else {
          const paso = Math.min(4, Math.floor(celda.tasa * 5));
          div.style.background = pasos[paso];
          // Blanco o tinta según la luminancia del relleno, para que la
          // etiqueta siempre tenga contraste.
          div.style.color = paso >= 3 ? '#ffffff' : '#0b0b0b';
          div.textContent = (celda.tasa * 100).toFixed(0);
        }
        div.tabIndex = 0;
        const describir = ev => mostrarTip(
          ev.clientX || div.getBoundingClientRect().left,
          ev.clientY || div.getBoundingClientRect().top,
          [{valor: pct(celda.tasa), nombre: `${etiqueta} · ${colLabels[c]}`},
           {valor: num(celda.total), nombre: 'supervisiones'}]);
        div.addEventListener('pointermove', describir);
        div.addEventListener('focus', describir);
        div.addEventListener('pointerleave', ocultarTip);
        div.addEventListener('blur', ocultarTip);
        reja.appendChild(div);
      });
    });
    contenedor.appendChild(reja);
  }

  /** Tabla ordenable: la vista equivalente que acompaña a cada gráfico. */
  function tabla(contenedor, columnas, filas) {
    contenedor.replaceChildren();
    const envoltura = document.createElement('div');
    envoltura.className = 'scroll-x';
    const t = document.createElement('table');
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    columnas.forEach((col, i) => {
      const th = document.createElement('th');
      if (col.num) th.className = 'num';
      th.textContent = col.titulo;
      th.addEventListener('click', () => {
        const asc = th.dataset.orden !== 'asc';
        filas.sort((a, b) => {
          const x = a[i], y = b[i];
          const cmp = typeof x === 'number' && typeof y === 'number'
            ? x - y : String(x).localeCompare(String(y), 'es');
          return asc ? cmp : -cmp;
        });
        th.dataset.orden = asc ? 'asc' : 'desc';
        tabla(contenedor, columnas, filas);
      });
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    t.appendChild(thead);
    const tbody = document.createElement('tbody');
    for (const fila of filas) {
      const tr = document.createElement('tr');
      columnas.forEach((col, i) => {
        const td = document.createElement('td');
        if (col.num) td.className = 'num';
        td.textContent = col.formato ? col.formato(fila[i]) : fila[i];
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    }
    t.appendChild(tbody);
    envoltura.appendChild(t);
    contenedor.appendChild(envoltura);
  }

  return {line, bars, columns, heat, tabla, destroyAll, token, pct, num};
})();
```

- [ ] **Step 2: Verificación manual**

Añadir temporalmente al final de `#mod-app`, ejecutar el build, abrir el archivo, comprobar, y borrar el bloque:

```js
document.getElementById('view').innerHTML =
  '<div class="card"><div class="plot"><canvas id="_prueba"></canvas></div></div>';
const s = agg.series(store.activeRows(), 'mes');
charts.line(document.getElementById('_prueba'), {
  labels: s.labels,
  series: [{label: 'Tasa de cumplimiento', data: s.tasa, color: charts.token('series-1')}]
});
```

Run: `python build_dashboard.py` y abrir `dashboard.html`.
Expected: una línea de 2px con marcadores anillados, eje Y de 0 a 100%, rejilla hairline. Al pasar el puntero aparece el tooltip con el mes y el valor. Con Tab y flechas se recorre la serie. Cambiar el tema y recargar debe repintar con los colores del modo oscuro.

- [ ] **Step 3: Commit**

```bash
git add template.html
git commit -m "feat: add chart module with tooltips, heatmap and table view"
```

---

### Task 9: Barra de filtros, enrutado y estados vacíos

**Files:**
- Modify: `template.html` (bloques `#mod-views` y `#mod-app`)

**Interfaces:**
- Consumes: `store`, `agg`, `charts`.
- Produces: el objeto global `views` con `views.render()`, `views.estado` (`{vista, responsable, formulario}`) y el ayudante `views.card(titulo, subtitulo) -> HTMLElement`. `app` construye la barra de filtros y los chips.

- [ ] **Step 1: Escribir el esqueleto de `views` y los estados vacíos**

En `template.html`, rellenar `<script id="mod-views">`:

```js
const views = (() => {
  const estado = {vista: 'global', responsable: null, formulario: null};
  const contenedor = document.getElementById('view');

  /** Card con título y, opcionalmente, un botón que alterna gráfico/tabla. */
  function card(titulo, subtitulo) {
    const div = document.createElement('div');
    div.className = 'card';
    const h = document.createElement('h2');
    h.textContent = titulo;
    div.appendChild(h);
    if (subtitulo) {
      const s = document.createElement('div');
      s.className = 'sub';
      s.textContent = subtitulo;
      div.appendChild(s);
    }
    return div;
  }

  /** Zona de contenido dentro de un card.
   *
   * charts.tabla() hace replaceChildren() sobre su contenedor, así que
   * pasarle el card directamente borraría su <h2>. Siempre se le pasa una
   * zona propia.
   */
  function zonaDe(tarjeta) {
    const zona = document.createElement('div');
    tarjeta.appendChild(zona);
    return zona;
  }

  function conTabla(tarjeta, columnas, filas, dibujarGrafico) {
    const zona = document.createElement('div');
    tarjeta.appendChild(zona);
    const boton = document.createElement('button');
    boton.className = 'chip';
    boton.type = 'button';
    boton.style.marginTop = '10px';
    let mostrandoTabla = false;
    const pintar = () => {
      zona.replaceChildren();
      if (mostrandoTabla) charts.tabla(zona, columnas, filas);
      else dibujarGrafico(zona);
      boton.textContent = mostrandoTabla ? 'Ver gráfico' : 'Ver tabla';
    };
    boton.addEventListener('click', () => { mostrandoTabla = !mostrandoTabla; pintar(); });
    tarjeta.appendChild(boton);
    pintar();
  }

  function plot(zona, id) {
    const caja = document.createElement('div');
    caja.className = 'plot';
    const lienzo = document.createElement('canvas');
    lienzo.id = id;
    caja.appendChild(lienzo);
    zona.appendChild(caja);
    return lienzo;
  }

  function vacio(mensaje) {
    const div = document.createElement('div');
    div.className = 'empty';
    div.textContent = mensaje;
    return div;
  }

  function kpi(etiqueta, valor, delta) {
    const div = document.createElement('div');
    div.className = 'kpi';
    const l = document.createElement('div');
    l.className = 'label';
    l.textContent = etiqueta;
    const v = document.createElement('div');
    v.className = 'value';
    v.textContent = valor;
    div.append(l, v);
    if (delta) {
      const d = document.createElement('div');
      d.className = 'delta';
      d.textContent = delta;
      div.appendChild(d);
    }
    return div;
  }

  function render() {
    charts.destroyAll();
    contenedor.replaceChildren();
    const filas = store.activeRows();
    if (!filas.length) {
      contenedor.appendChild(vacio('Sin registros para estos filtros.'));
      return;
    }
    if (estado.vista === 'global') renderGlobal(filas);
    else if (estado.vista === 'responsable') renderResponsable(filas);
    else renderFormulario(filas);
  }

  // renderGlobal, renderResponsable y renderFormulario se añaden en las
  // tasks 10, 11 y 12. Hasta entonces son marcadores visibles.
  function renderGlobal(filas) {
    contenedor.appendChild(vacio('Vista global — pendiente (Task 10)'));
  }
  function renderResponsable(filas) {
    contenedor.appendChild(vacio('Vista responsable — pendiente (Task 11)'));
  }
  function renderFormulario(filas) {
    contenedor.appendChild(vacio('Vista formulario — pendiente (Task 12)'));
  }

  return {estado, render, card, conTabla, zonaDe, plot, vacio, kpi};
})();
```

Las tres funciones marcador se sustituyen **en su sitio, dentro del propio
módulo**, en las tasks 10, 11 y 12. `render()` las llama por nombre desde el
ámbito del módulo, de modo que reemplazar la declaración basta: no hace falta
exportarlas ni reasignarlas desde fuera.

- [ ] **Step 2: Escribir la barra de filtros y el enrutado**

Sustituir el contenido de `<script id="mod-app">` por:

```js
document.getElementById('meta').textContent =
  DATA.meta.filas + ' supervisiones · generado ' + DATA.meta.generado;

const app = (() => {
  const barra = document.getElementById('filters');
  const zonaChips = document.getElementById('chips');

  const ETIQUETAS = {
    medida: 'Medida', submedida: 'Submedida', unidad: 'Unidad / servicio',
    grupo: 'Grupo ocupacional', cargo: 'Cargo', estado: 'Estado de validación'
  };
  const DIA_MS = 86400000;
  const aISO = dia => new Date(dia * DIA_MS).toISOString().slice(0, 10);
  const aDia = iso => Math.floor(Date.parse(iso) / DIA_MS);

  function selector(clave) {
    const label = document.createElement('label');
    label.textContent = ETIQUETAS[clave];
    const sel = document.createElement('select');
    const todos = document.createElement('option');
    todos.value = '';
    todos.textContent = 'Todos';
    sel.appendChild(todos);
    DATA.dims[clave].forEach((valor, i) => {
      const op = document.createElement('option');
      op.value = String(i);
      op.textContent = valor;   // valor del Excel: textContent, no innerHTML
      sel.appendChild(op);
    });
    sel.addEventListener('change', () => {
      store.set(clave, sel.value === '' ? null : Number(sel.value));
    });
    sel.dataset.clave = clave;
    label.appendChild(sel);
    return label;
  }

  function fecha(clave, texto) {
    const label = document.createElement('label');
    label.textContent = texto;
    const input = document.createElement('input');
    input.type = 'date';
    input.min = aISO(DATA.meta.dia_min);
    input.max = aISO(DATA.meta.dia_max);
    input.addEventListener('change', () => {
      store.set(clave, input.value ? aDia(input.value) : null);
    });
    input.dataset.clave = clave;
    label.appendChild(input);
    return label;
  }

  function construirBarra() {
    // El rango de fechas va primero: es el filtro al que todos van.
    barra.append(fecha('desde', 'Desde'), fecha('hasta', 'Hasta'));
    store.dimsFiltrables.forEach(k => barra.appendChild(selector(k)));
    const limpiar = document.createElement('button');
    limpiar.className = 'chip';
    limpiar.type = 'button';
    limpiar.textContent = 'Limpiar filtros';
    limpiar.addEventListener('click', () => {
      barra.querySelectorAll('select, input').forEach(c => { c.value = ''; });
      store.clearAll();
    });
    barra.appendChild(limpiar);
  }

  function pintarChips() {
    zonaChips.replaceChildren();
    for (const [clave, valor] of Object.entries(store.filters)) {
      if (valor === null) continue;
      const chip = document.createElement('button');
      chip.className = 'chip';
      chip.type = 'button';
      const texto = clave === 'desde' ? 'Desde ' + aISO(valor)
        : clave === 'hasta' ? 'Hasta ' + aISO(valor)
        : ETIQUETAS[clave] + ': ' + DATA.dims[clave][valor];
      chip.textContent = texto + ' ✕';
      chip.addEventListener('click', () => {
        const control = barra.querySelector(`[data-clave="${clave}"]`);
        if (control) control.value = '';
        store.clear(clave);
      });
      zonaChips.appendChild(chip);
    }
  }

  function pestanas() {
    document.querySelectorAll('.tabs button').forEach(b => {
      b.addEventListener('click', () => {
        document.querySelectorAll('.tabs button').forEach(otro =>
          otro.setAttribute('aria-selected', String(otro === b)));
        views.estado.vista = b.dataset.view;
        views.render();
      });
    });
  }

  construirBarra();
  pestanas();
  store.onChange(() => { pintarChips(); views.render(); });
  // Repintar los gráficos al cambiar de tema: Chart.js copió los colores
  // al construirse y no vuelve a leer las variables CSS por su cuenta.
  window.addEventListener('themechange', () => views.render());
  matchMedia('(prefers-color-scheme: dark)')
    .addEventListener('change', () => views.render());
  views.render();

  return {pintarChips};
})();

document.getElementById('theme').addEventListener('click', () => {
  const actual = document.documentElement.getAttribute('data-theme');
  document.documentElement.setAttribute('data-theme', actual === 'dark' ? 'light' : 'dark');
  window.dispatchEvent(new Event('themechange'));
});
```

- [ ] **Step 3: Ejecutar el build y comprobar**

Run: `python build_dashboard.py` y abrir `dashboard.html`.
Expected: la barra de filtros muestra Desde, Hasta y los seis selectores en una sola fila sobre el contenido. Elegir un valor añade un chip; pulsar el chip lo quita y repone el selector a "Todos". Las tres pestañas cambian el marcador de la vista. Filtrar hasta dejar cero registros muestra "Sin registros para estos filtros."

- [ ] **Step 4: Commit**

```bash
git add template.html
git commit -m "feat: add filter bar, tab routing and empty states"
```

---

### Task 10: Vista Global

**Files:**
- Modify: `template.html` (bloque `#mod-views`)

**Interfaces:**
- Consumes: `agg.kpis`, `agg.rateBy`, `agg.series`, `agg.heatmap`, `charts.*`, `views.card/conTabla/plot/kpi`.
- Produces: `views.renderGlobal(filas)` asignado sobre el marcador de la Task 9.

La evolución mensual son **dos gráficos apilados que comparten el eje X**, no uno con doble eje: la tasa arriba, el volumen abajo. Dos escalas Y en un mismo plot inventarían una correlación que no está en los datos.

- [ ] **Step 1: Escribir la vista**

Sustituir la función `renderGlobal` marcador dentro de `#mod-views`:

```js
function renderGlobal(filas) {
  const k = agg.kpis(filas);

  const fila = document.createElement('div');
  fila.className = 'kpis';
  fila.style.marginBottom = '16px';
  fila.append(
    kpi('Supervisiones', charts.num(k.total)),
    kpi('Tasa de cumplimiento', charts.pct(k.tasa),
        `${charts.num(k.conDictamen)} con dictamen · ${charts.num(k.sinDictamen)} sin dictamen`),
    kpi('Responsables activos', charts.num(k.responsables)),
    kpi('Formularios usados', charts.num(k.formularios)),
    kpi('Aprobados', charts.pct(k.tasaAprobado), charts.num(k.aprobados) + ' registros')
  );
  contenedor.appendChild(fila);

  // Ranking de responsables. Categorías nominales: un solo color para todas
  // las barras. La longitud ya codifica la magnitud; teñirlas por rango
  // duplicaría la codificación y quemaría el canal de color.
  const porResp = agg.rateBy(filas, 'responsable');
  const tarjetaResp = card(
    'Cumplimiento por responsable',
    'Ordenado por tasa. El número entre paréntesis es el volumen de supervisiones.');
  conTabla(
    tarjetaResp,
    [{titulo: 'Responsable'}, {titulo: 'Supervisiones', num: true},
     {titulo: 'Cumplen', num: true}, {titulo: 'No cumplen', num: true},
     {titulo: 'Sin dictamen', num: true},
     {titulo: 'Tasa', num: true, formato: charts.pct}],
    porResp.map(e => [e.label, e.total, e.si, e.no, e.sin, e.tasa]),
    zona => {
      const caja = document.createElement('div');
      caja.className = 'plot';
      caja.style.height = Math.max(200, porResp.length * 26 + 40) + 'px';
      const lienzo = document.createElement('canvas');
      caja.appendChild(lienzo);
      zona.appendChild(caja);
      charts.bars(lienzo, {
        labels: porResp.map(e => `${e.label} (${e.total})`),
        values: porResp.map(e => e.tasa),
        extra: porResp.map(e => `${e.si} de ${e.si + e.no} con dictamen`),
        formato: charts.pct
      });
    });
  contenedor.appendChild(tarjetaResp);

  // Evolución: dos plots apilados sobre el mismo eje X. Nunca un eje Y
  // secundario — ver Global Constraints.
  const s = agg.series(filas, 'mes');
  const rejilla = document.createElement('div');
  rejilla.className = 'grid-2';

  const tTasa = card('Tasa de cumplimiento por mes', null);
  conTabla(tTasa,
    [{titulo: 'Mes'}, {titulo: 'Tasa', num: true, formato: charts.pct}],
    s.labels.map((l, i) => [l, s.tasa[i]]),
    zona => charts.line(plot(zona, 'g-tasa'), {
      labels: s.labels,
      series: [{label: 'Tasa de cumplimiento', data: s.tasa,
                color: charts.token('series-1')}]
    }));

  const tVol = card('Supervisiones por mes', null);
  conTabla(tVol,
    [{titulo: 'Mes'}, {titulo: 'Supervisiones', num: true}],
    s.labels.map((l, i) => [l, s.volumen[i]]),
    zona => charts.columns(plot(zona, 'g-vol'), {
      labels: s.labels, values: s.volumen, formato: charts.num
    }));

  rejilla.append(tTasa, tVol);
  contenedor.appendChild(rejilla);

  // Mapa de calor: magnitud continua, rampa secuencial de un solo tono.
  const calor = agg.heatmap(filas, 'submedida', 'mes');
  const tCalor = card('Cumplimiento por submedida y mes',
                      'Porcentaje de cumplimiento. Un punto marca que no hubo registros con dictamen.');
  conTabla(tCalor,
    [{titulo: 'Submedida'}, {titulo: 'Mes'},
     {titulo: 'Tasa', num: true, formato: charts.pct},
     {titulo: 'Supervisiones', num: true}],
    calor.rowLabels.flatMap((f, i) =>
      calor.colLabels.map((c, j) => [f, c, calor.cells[i][j].tasa, calor.cells[i][j].total])),
    zona => charts.heat(zona, calor));
  contenedor.appendChild(tCalor);
}
```

Nota: esta declaración sustituye a la función marcador dentro del bloque `#mod-views`. No añadir ninguna asignación desde fuera del módulo — `render()` la resuelve por nombre en el ámbito del módulo.

- [ ] **Step 2: Ejecutar el build y mirar el resultado**

Run: `python build_dashboard.py` y abrir `dashboard.html`.
Expected: cinco KPIs, el ranking de los 21 responsables con una sola tonalidad de azul, los dos plots mensuales apilados y el mapa de calor de 17 submedidas × 7 meses. Comprobar concretamente:
- Ninguna etiqueta del eje Y del ranking queda cortada.
- El card del ranking crece con el número de barras; no aparece un scroll vertical anidado.
- "Ver tabla" alterna a la tabla y "Ver gráfico" vuelve.
- Cambiar de tema repinta los gráficos con los colores oscuros.

- [ ] **Step 3: Commit**

```bash
git add template.html
git commit -m "feat: implement global comparison view"
```

---

### Task 11: Vista Responsable

**Files:**
- Modify: `template.html` (bloque `#mod-views`)

**Interfaces:**
- Consumes: lo mismo que la Task 10, más `views.estado.responsable` (índice en `DATA.dims.responsable`).
- Produces: `views.renderResponsable(filas)`, y la función `views.irA(vista, clave)` que la vista Global usa para navegar.

El desglose por dimensión compara al responsable contra el conjunto filtrado. La evolución usa **emphasis**: la línea de la persona en el color de serie, la línea global en gris de contexto — es "una serie es el punto, el resto es contexto", no dos series de identidad equivalente.

- [ ] **Step 1: Escribir la vista**

Sustituir la función `renderResponsable` marcador:

```js
const DIMENSIONES_DESGLOSE = [
  ['medida', 'Medida'],
  ['submedida', 'Submedida'],
  ['unidad', 'Unidad / servicio'],
  ['area', 'Área específica'],
  ['grupo', 'Grupo ocupacional'],
  ['cargo', 'Cargo']
];
const TOPE_BARRAS = 15;

function selectorResponsable() {
  const label = document.createElement('label');
  label.style.cssText = 'display:flex;flex-direction:column;font-size:12px;gap:3px';
  label.textContent = 'Responsable';
  const sel = document.createElement('select');
  sel.style.cssText = 'font:inherit;font-size:14px;padding:6px 9px;border-radius:7px;' +
    'border:1px solid var(--border);background:var(--surface);color:var(--text-primary)';
  DATA.dims.responsable.forEach((nombre, i) => {
    const op = document.createElement('option');
    op.value = String(i);
    op.textContent = nombre;
    if (i === estado.responsable) op.selected = true;
    sel.appendChild(op);
  });
  sel.addEventListener('change', () => {
    estado.responsable = Number(sel.value);
    render();
  });
  label.appendChild(sel);
  return label;
}

function renderResponsable(filas) {
  if (estado.responsable === null) estado.responsable = 0;
  const suyas = filas.filter(i => DATA.rows.responsable[i] === estado.responsable);

  const cabecera = document.createElement('div');
  cabecera.style.cssText = 'display:flex;gap:16px;align-items:flex-end;margin-bottom:16px';
  cabecera.appendChild(selectorResponsable());
  contenedor.appendChild(cabecera);

  if (!suyas.length) {
    contenedor.appendChild(
      vacio('Este responsable no tiene registros para estos filtros.'));
    return;
  }

  const k = agg.kpis(suyas);
  const global = agg.kpis(filas);
  const delta = (a, b) => {
    if (a === null || b === null) return '';
    const d = (a - b) * 100;
    const signo = d >= 0 ? '+' : '−';
    return `${signo}${Math.abs(d).toFixed(1)} pts vs. el conjunto filtrado`;
  };

  const fila = document.createElement('div');
  fila.className = 'kpis';
  fila.style.marginBottom = '16px';
  fila.append(
    kpi('Supervisiones', charts.num(k.total),
        `${(k.total / global.total * 100).toFixed(1)}% del total filtrado`),
    kpi('Tasa de cumplimiento', charts.pct(k.tasa), delta(k.tasa, global.tasa)),
    kpi('Sin dictamen', charts.num(k.sinDictamen)),
    kpi('Formularios distintos', charts.num(k.formularios)),
    kpi('Aprobados', charts.pct(k.tasaAprobado), delta(k.tasaAprobado, global.tasaAprobado))
  );
  contenedor.appendChild(fila);

  // Volumen, con conmutador mes / semana.
  const tVol = card('Formularios realizados', null);
  const conmutador = document.createElement('div');
  conmutador.style.margin = '8px 0';
  let periodo = 'mes';
  const zonaVol = document.createElement('div');
  const pintarVol = () => {
    zonaVol.replaceChildren();
    const s = agg.series(suyas, periodo);
    const caja = document.createElement('div');
    caja.className = 'plot';
    const lienzo = document.createElement('canvas');
    caja.appendChild(lienzo);
    zonaVol.appendChild(caja);
    charts.columns(lienzo, {labels: s.labels, values: s.volumen, formato: charts.num});
  };
  [['mes', 'Por mes'], ['semana', 'Por semana']].forEach(([valor, texto]) => {
    const b = document.createElement('button');
    b.className = 'chip';
    b.type = 'button';
    b.textContent = texto;
    b.addEventListener('click', () => { periodo = valor; pintarVol(); });
    conmutador.appendChild(b);
  });
  tVol.append(conmutador, zonaVol);
  pintarVol();
  contenedor.appendChild(tVol);

  // Evolución con emphasis: la persona en color, el conjunto en gris.
  const suya = agg.series(suyas, 'mes');
  const todaGlobal = agg.series(filas, 'mes');
  const mapaGlobal = new Map(todaGlobal.labels.map((l, i) => [l, todaGlobal.tasa[i]]));
  const tEvo = card('Evolución de su cumplimiento',
                    'La línea gris es el conjunto filtrado completo, como referencia.');
  conTabla(tEvo,
    [{titulo: 'Mes'}, {titulo: 'Su tasa', num: true, formato: charts.pct},
     {titulo: 'Conjunto', num: true, formato: charts.pct}],
    suya.labels.map((l, i) => [l, suya.tasa[i], mapaGlobal.get(l) ?? null]),
    zona => charts.line(plot(zona, 'r-evo'), {
      labels: suya.labels,
      series: [
        {label: 'Conjunto filtrado',
         data: suya.labels.map(l => mapaGlobal.get(l) ?? null),
         color: charts.token('context')},
        {label: DATA.dims.responsable[estado.responsable],
         data: suya.tasa, color: charts.token('series-1')}
      ]
    }));
  contenedor.appendChild(tEvo);

  // Desglose en las seis dimensiones.
  const rejilla = document.createElement('div');
  rejilla.className = 'grid-2';
  for (const [clave, titulo] of DIMENSIONES_DESGLOSE) {
    const datos = agg.rateBy(suyas, clave);
    const recortado = datos.length > TOPE_BARRAS;
    let mostrando = recortado ? TOPE_BARRAS : datos.length;
    const tarjeta = card(titulo,
      recortado ? `${datos.length} valores; se muestran los ${TOPE_BARRAS} primeros.` : null);
    const zona = document.createElement('div');
    const pintar = () => {
      zona.replaceChildren();
      const vista = datos.slice(0, mostrando);
      const caja = document.createElement('div');
      caja.className = 'plot';
      caja.style.height = Math.max(140, vista.length * 24 + 40) + 'px';
      const lienzo = document.createElement('canvas');
      caja.appendChild(lienzo);
      zona.appendChild(caja);
      charts.bars(lienzo, {
        labels: vista.map(e => `${e.label} (${e.total})`),
        values: vista.map(e => e.tasa),
        extra: vista.map(e => `${e.si} de ${e.si + e.no} con dictamen`),
        formato: charts.pct
      });
    };
    tarjeta.appendChild(zona);
    if (recortado) {
      const ver = document.createElement('button');
      ver.className = 'chip';
      ver.type = 'button';
      ver.style.marginTop = '8px';
      ver.textContent = 'Ver todas';
      ver.addEventListener('click', () => {
        mostrando = mostrando === datos.length ? TOPE_BARRAS : datos.length;
        ver.textContent = mostrando === datos.length ? 'Ver menos' : 'Ver todas';
        pintar();
      });
      tarjeta.appendChild(ver);
    }
    pintar();
    rejilla.appendChild(tarjeta);
  }
  contenedor.appendChild(rejilla);

  // Sus formularios, enlazados a la vista de formulario.
  const porForm = agg.rateBy(suyas, 'formulario');
  const tForm = card('Sus formularios', 'Pulse una fila para ver el detalle del formulario.');
  const zonaTabla = document.createElement('div');
  charts.tabla(zonaTabla,
    [{titulo: 'Formulario'}, {titulo: 'Supervisiones', num: true},
     {titulo: 'Tasa', num: true, formato: charts.pct}],
    porForm.map(e => [DATA.forms[e.label].nombre, e.total, e.tasa]));
  zonaTabla.querySelectorAll('tbody tr').forEach((tr, i) => {
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', () => irA('formulario', porForm[i].idx));
  });
  tForm.appendChild(zonaTabla);
  contenedor.appendChild(tForm);
}

function irA(vista, clave) {
  estado.vista = vista;
  if (vista === 'responsable') estado.responsable = clave;
  if (vista === 'formulario') estado.formulario = clave;
  document.querySelectorAll('.tabs button').forEach(b =>
    b.setAttribute('aria-selected', String(b.dataset.view === vista)));
  render();
}

```

Dos ajustes al módulo: sustituir la declaración marcador de `renderResponsable` en su sitio, y añadir `irA` al objeto que devuelve el módulo `views`, que pasa a ser `{estado, render, card, conTabla, plot, vacio, kpi, irA}` — la vista Global la necesita desde fuera del módulo.

- [ ] **Step 2: Hacer clicable el ranking global**

En `renderGlobal`, dentro de la llamada a `conTabla` del ranking, añadir tras `charts.bars(...)`:

```js
      lienzo.style.cursor = 'pointer';
      lienzo.addEventListener('click', ev => {
        const puntos = grafico.getElementsAtEventForMode(
          ev, 'index', {intersect: false}, false);
        if (puntos.length) views.irA('responsable', porResp[puntos[0].index].idx);
      });
```

y capturar el retorno de `charts.bars` en `const grafico = charts.bars(...)`.

- [ ] **Step 3: Ejecutar el build y mirar el resultado**

Run: `python build_dashboard.py` y abrir `dashboard.html`.
Expected: la pestaña "Por responsable" arranca con el primero de la lista. Comprobar:
- El conmutador mes/semana cambia el gráfico de volumen; en semanal aparecen unas 26 columnas legibles.
- La evolución muestra la línea gris de contexto detrás de la línea azul.
- "Área específica" aparece recortada a 15 con el botón "Ver todas", y al expandirla el card crece sin recortar etiquetas.
- Pulsar una barra del ranking global lleva a esa persona.
- Pulsar una fila de "Sus formularios" lleva a la vista de formulario.

- [ ] **Step 4: Commit**

```bash
git add template.html
git commit -m "feat: implement per-responsable view with six-dimension breakdown"
```

---

### Task 12: Vista Formulario y verificación final

**Files:**
- Modify: `template.html` (bloque `#mod-views`)
- Create: `README.md` (reemplazar el existente)

**Interfaces:**
- Consumes: todo lo anterior, más `DATA.forms`, `DATA.texts.evaluado`, `DATA.texts.conclusiones`.
- Produces: `views.renderFormulario(filas)`. Nada consume esta task.

El bloque de nivel de riesgo solo se dibuja si hay datos tras el filtro: `NIVEL_RIESGO` está vacío en 2698 de 2806 registros, y un gráfico de una sola categoría "(Sin nivel de riesgo)" no informa de nada.

- [ ] **Step 1: Escribir la vista**

Sustituir la función `renderFormulario` marcador:

```js
const TOPE_MOTIVOS = 10;
const SIN_RIESGO = '(Sin nivel de riesgo)';

function selectorFormulario(disponibles) {
  const label = document.createElement('label');
  label.style.cssText = 'display:flex;flex-direction:column;font-size:12px;gap:3px';
  label.textContent = 'Formulario';
  const sel = document.createElement('select');
  sel.style.cssText = 'font:inherit;font-size:14px;padding:6px 9px;border-radius:7px;' +
    'border:1px solid var(--border);background:var(--surface);color:var(--text-primary)';
  disponibles.forEach(idx => {
    const id = DATA.dims.formulario[idx];
    const op = document.createElement('option');
    op.value = String(idx);
    op.textContent = DATA.forms[id].nombre;
    if (idx === estado.formulario) op.selected = true;
    sel.appendChild(op);
  });
  sel.addEventListener('change', () => {
    estado.formulario = Number(sel.value);
    render();
  });
  label.appendChild(sel);
  return label;
}

function renderFormulario(filas) {
  const disponibles = [...new Set(filas.map(i => DATA.rows.formulario[i]))]
    .sort((a, b) => DATA.forms[DATA.dims.formulario[a]].nombre
      .localeCompare(DATA.forms[DATA.dims.formulario[b]].nombre, 'es'));
  if (estado.formulario === null || !disponibles.includes(estado.formulario)) {
    estado.formulario = disponibles[0];
  }

  const id = DATA.dims.formulario[estado.formulario];
  const meta = DATA.forms[id];
  const suyas = filas.filter(i => DATA.rows.formulario[i] === estado.formulario);

  const cabecera = document.createElement('div');
  cabecera.style.cssText = 'display:flex;gap:16px;align-items:flex-end;margin-bottom:8px';
  cabecera.appendChild(selectorFormulario(disponibles));
  contenedor.appendChild(cabecera);

  const ficha = document.createElement('div');
  ficha.className = 'sub';
  ficha.style.marginBottom = '16px';
  ficha.textContent =
    `${meta.medida} · ${meta.submedida} · versión ${meta.version} · ${id}`;
  contenedor.appendChild(ficha);

  if (!suyas.length) {
    contenedor.appendChild(vacio('Sin registros de este formulario para estos filtros.'));
    return;
  }

  const k = agg.kpis(suyas);
  const fila = document.createElement('div');
  fila.className = 'kpis';
  fila.style.marginBottom = '16px';
  fila.append(
    kpi('Supervisiones', charts.num(k.total)),
    kpi('Tasa de cumplimiento', charts.pct(k.tasa),
        charts.num(k.sinDictamen) + ' sin dictamen'),
    kpi('Responsables', charts.num(k.responsables)),
    kpi('Aprobados', charts.pct(k.tasaAprobado))
  );
  contenedor.appendChild(fila);

  // Evolución y volumen: de nuevo dos plots apilados, nunca doble eje.
  const s = agg.series(suyas, 'mes');
  const rejillaTiempo = document.createElement('div');
  rejillaTiempo.className = 'grid-2';
  const tTasa = card('Tasa de cumplimiento por mes', null);
  conTabla(tTasa,
    [{titulo: 'Mes'}, {titulo: 'Tasa', num: true, formato: charts.pct}],
    s.labels.map((l, i) => [l, s.tasa[i]]),
    zona => charts.line(plot(zona, 'f-tasa'), {
      labels: s.labels,
      series: [{label: 'Tasa de cumplimiento', data: s.tasa,
                color: charts.token('series-1')}]
    }));
  const tVol = card('Supervisiones por mes', null);
  conTabla(tVol,
    [{titulo: 'Mes'}, {titulo: 'Supervisiones', num: true}],
    s.labels.map((l, i) => [l, s.volumen[i]]),
    zona => charts.columns(plot(zona, 'f-vol'), {
      labels: s.labels, values: s.volumen, formato: charts.num
    }));
  rejillaTiempo.append(tTasa, tVol);
  contenedor.appendChild(rejillaTiempo);

  // Desglose por unidad, área, grupo y responsable.
  const rejilla = document.createElement('div');
  rejilla.className = 'grid-2';
  for (const [clave, titulo] of [
    ['unidad', 'Unidad / servicio'], ['area', 'Área específica'],
    ['grupo', 'Grupo ocupacional'], ['responsable', 'Responsable']
  ]) {
    const datos = agg.rateBy(suyas, clave).slice(0, TOPE_BARRAS);
    const tarjeta = card(titulo, null);
    conTabla(tarjeta,
      [{titulo}, {titulo: 'Supervisiones', num: true},
       {titulo: 'Tasa', num: true, formato: charts.pct}],
      datos.map(e => [e.label, e.total, e.tasa]),
      zona => {
        const caja = document.createElement('div');
        caja.className = 'plot';
        caja.style.height = Math.max(140, datos.length * 24 + 40) + 'px';
        const lienzo = document.createElement('canvas');
        caja.appendChild(lienzo);
        zona.appendChild(caja);
        charts.bars(lienzo, {
          labels: datos.map(e => `${e.label} (${e.total})`),
          values: datos.map(e => e.tasa),
          formato: charts.pct
        });
      });
    rejilla.appendChild(tarjeta);
  }
  contenedor.appendChild(rejilla);

  // Estado de validación: dos clases, tabla directa. Un gráfico de dos
  // barras no añadiría nada a dos números.
  const porEstado = agg.rateBy(suyas, 'estado');
  const tEstado = card('Estado de validación', null);
  charts.tabla(zonaDe(tEstado),
    [{titulo: 'Estado'}, {titulo: 'Supervisiones', num: true},
     {titulo: 'Tasa', num: true, formato: charts.pct}],
    porEstado.map(e => [e.label, e.total, e.tasa]));
  contenedor.appendChild(tEstado);

  // Nivel de riesgo: solo si hay algo más que "(Sin nivel de riesgo)".
  const porRiesgo = agg.rateBy(suyas, 'riesgo')
    .filter(e => e.label !== SIN_RIESGO);
  const tRiesgo = card('Nivel de riesgo', null);
  if (porRiesgo.length) {
    charts.tabla(zonaDe(tRiesgo),
      [{titulo: 'Nivel'}, {titulo: 'Supervisiones', num: true}],
      porRiesgo.map(e => [e.label, e.total]));
  } else {
    tRiesgo.appendChild(vacio('Sin datos de riesgo para este formulario.'));
  }
  contenedor.appendChild(tRiesgo);

  // Motivos de no cumplimiento. Texto libre, 366 valores distintos en el
  // conjunto completo: cola larga. Top 10 y el resto agrupado.
  const fallidas = suyas.filter(i => DATA.rows.cumple[i] === 0);
  const tMotivos = card('Motivos de no cumplimiento',
                        `${fallidas.length} supervisiones no cumplieron.`);
  if (fallidas.length) {
    const cuenta = new Map();
    for (const i of fallidas) {
      const m = DATA.dims.motivo[DATA.rows.motivo[i]] || '(Sin motivo indicado)';
      cuenta.set(m, (cuenta.get(m) || 0) + 1);
    }
    const orden = [...cuenta.entries()].sort((a, b) => b[1] - a[1]);
    const top = orden.slice(0, TOPE_MOTIVOS);
    const resto = orden.slice(TOPE_MOTIVOS).reduce((n, e) => n + e[1], 0);
    if (resto) top.push(['Otros motivos', resto]);
    charts.tabla(zonaDe(tMotivos),
      [{titulo: 'Motivo'}, {titulo: 'Supervisiones', num: true}], top);

    const detalles = document.createElement('details');
    detalles.style.marginTop = '10px';
    const resumenEl = document.createElement('summary');
    resumenEl.textContent = 'Ver conclusiones y recomendaciones';
    resumenEl.style.cursor = 'pointer';
    detalles.appendChild(resumenEl);
    for (const i of fallidas) {
      const texto = DATA.texts.conclusiones[String(i)];
      if (!texto) continue;
      const p = document.createElement('p');
      p.style.cssText = 'margin:8px 0;padding-left:10px;border-left:2px solid var(--grid)';
      const quien = document.createElement('strong');
      quien.textContent = DATA.dims.responsable[DATA.rows.responsable[i]] + ': ';
      p.appendChild(quien);
      p.appendChild(document.createTextNode(texto));
      detalles.appendChild(p);
    }
    tMotivos.appendChild(detalles);
  } else {
    tMotivos.appendChild(vacio('Todas las supervisiones de este formulario cumplieron.'));
  }
  contenedor.appendChild(tMotivos);

  // Registros individuales.
  const DIA_MS = 86400000;
  const tRegistros = card('Registros', null);
  charts.tabla(zonaDe(tRegistros),
    [{titulo: 'Fecha'}, {titulo: 'Responsable'}, {titulo: 'Evaluado'},
     {titulo: 'Unidad'}, {titulo: '%', num: true}, {titulo: 'Sí', num: true},
     {titulo: 'No', num: true}, {titulo: 'N/A', num: true},
     {titulo: 'Cumple'}, {titulo: 'Estado'}],
    suyas.map(i => [
      new Date(DATA.rows.dia[i] * DIA_MS).toISOString().slice(0, 10),
      DATA.dims.responsable[DATA.rows.responsable[i]],
      DATA.texts.evaluado[i],
      DATA.dims.unidad[DATA.rows.unidad[i]],
      DATA.rows.pct[i], DATA.rows.si[i], DATA.rows.no[i], DATA.rows.na[i],
      DATA.rows.cumple[i] === 1 ? 'Sí' : DATA.rows.cumple[i] === 0 ? 'No' : '—',
      DATA.dims.estado[DATA.rows.estado[i]]
    ]));
  contenedor.appendChild(tRegistros);
}
```

Como en las dos tasks anteriores, esta declaración sustituye a la función marcador dentro del bloque `#mod-views`.

- [ ] **Step 2: Ejecutar el build y revisar las tres vistas**

Run: `python build_dashboard.py` y abrir `dashboard.html`.
Expected, comprobando cada punto:
- Vista Formulario: el selector lista los formularios presentes tras el filtro; la ficha muestra medida, submedida, versión e ID.
- El bloque de riesgo dice "Sin datos de riesgo para este formulario" en la gran mayoría de formularios, y muestra la tabla en los pocos que sí tienen `NIVEL_RIESGO`.
- Los motivos muestran como mucho once filas, la última "Otros motivos" cuando hay cola.
- El desplegable de conclusiones abre y el texto no rompe el layout.
- La tabla de registros desplaza en horizontal dentro de su card; el `body` de la página no desplaza en horizontal.
- Ninguna vista muestra `NaN`, `undefined` ni `null` en pantalla.

- [ ] **Step 3: Verificación de accesibilidad y modo oscuro**

- Recorrer con Tab: los selectores, los botones de tabla y las celdas del mapa de calor reciben foco, y las celdas muestran su tooltip al enfocarse.
- Cambiar a modo oscuro con el botón y recorrer las tres vistas: los gráficos se repintan con los pasos oscuros; ningún texto queda ilegible.
- Poner el sistema operativo en oscuro con el tema sin fijar y recargar: la página arranca en oscuro.
- Estrechar la ventana a 600px: la rejilla de dos columnas colapsa a una y nada desborda.

- [ ] **Step 4: Ejecutar toda la suite y reportar**

```bash
python -m pytest tests/ -v
python build_dashboard.py
ls -lh dashboard.html
```

Expected: 26 pruebas PASS. El build imprime el resumen completo. Abrir `tests/test_agg.html` y confirmar `26 pasan, 0 fallan`.

Registrar el tamaño real del archivo. Si supera 2 MB, revisar si `texts.conclusiones` creció; el spec estimó 1.0–1.4 MB.

- [ ] **Step 5: Escribir el README**

`README.md`:

```markdown
# PCI-STATS — Dashboard de supervisiones

Genera un dashboard HTML interactivo y autocontenido a partir de `SupPCI.xlsx`.

## Uso

    python build_dashboard.py

Escribe `dashboard.html` en la raíz del repositorio. El archivo no necesita
conexión ni servidor: se abre con doble clic y se puede enviar por correo.

Para usar otro libro:

    python build_dashboard.py ruta/al/otro.xlsx

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

Y abrir `tests/test_agg.html` en el navegador para las pruebas de agregación.

## Si el build falla

`build_dashboard.py` aborta a propósito cuando el Excel cambia de forma:
columna faltante, un valor nuevo en `CUMPLE_CORRECTAMENTE`, un porcentaje
fuera de 0-100, un formulario con `METODO_CUMPLIMIENTO` distinto de
`SI_NO_NA`, o un responsable nuevo con nombre en formato slug. El mensaje dice
qué encontró. Prefiere fallar a generar un dashboard con cifras equivocadas.

Los nombres en formato slug se corrigen añadiéndolos a `SLUG_NAME_MAP` en
`build_dashboard.py`, con su acentuación correcta.

## Diseño

`docs/superpowers/specs/2026-08-24-dashboard-supervisiones-design.md`
```

- [ ] **Step 6: Commit**

```bash
git add template.html README.md
git commit -m "feat: implement per-form detail view and document the project"
```
