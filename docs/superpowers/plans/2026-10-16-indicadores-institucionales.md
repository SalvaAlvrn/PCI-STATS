# Indicadores institucionales editables — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pestaña «Indicadores» en el dashboard con los 10 indicadores institucionales de PCI por mes, editables (N, D y meta) y guardados en un Google Sheet compartido a través de un Apps Script.

**Architecture:** `indicadores.py` define los indicadores y lee el libro por CSV público en cada build (copia de respaldo en `DATA.indicadores`). `apps_script/indicadores.gs` es la única vía de escritura: `doGet` devuelve el libro, `doPost` valida clave, datos y conflicto, y reescribe un año. En `template.html`, el módulo puro `mod-indicadores` calcula, valida y arma borradores; `mod-views` pinta la vista, lee en vivo y guarda.

**Tech Stack:** Python 3.12 + pandas + openpyxl + pytest; JS de navegador sin dependencias (probado con node); Google Apps Script (V8).

**Spec:** `docs/superpowers/specs/2026-10-16-indicadores-institucionales-design.md`

## Global Constraints

- T = N / D · k. Se calcula siempre; nunca se guarda ni se escribe a mano.
- N, D y meta: vacío o número ≥ 0; decimales permitidos. D = 0 o vacío → T vacío, nunca 0 ni infinito. N > D se acepta.
- Años válidos: enteros entre 2020 y 2100. Meses 1–12.
- Pestañas del libro y sus cabeceras exactas: `VALORES` (`ANIO`, `MES`, `INDICADOR`, `NUMERADOR`, `DENOMINADOR`), `METAS` (`ANIO`, `INDICADOR`, `META`), `CONTROL` (`ANIO`, `ACTUALIZADO`).
- La clave vive solo en la Script Property `CLAVE`; nunca en el repo ni en la página.
- Lectura en vivo con límite de 8 s; POST con `Content-Type: text/plain;charset=utf-8`.
- Meta = tope: T > meta → rojo (`--critical`); T ≤ meta → verde (`--good`); sin meta o sin T → sin color.
- Si el libro falla, el build imprime `AVISO:` y el resto del tablero se publica igual. Si `URL_SCRIPT` está vacía, no hay botón Editar.
- Comentarios, mensajes y nombres en español, como el resto del repo.
- Fuera de alcance: gráficos, exportar CSV, historial, N automático desde vigilancia, metas de sentido inverso.

## Review Focus

- **Decimales con coma en el CSV de Google** (libro en configuración regional de El Salvador/España exporta `1,5`) → el build debe leer 1.5, no fallar. Prueba en Task 1.
- **Filas vacías en `VALORES`** que alguien deja al borrar a mano en el Sheet → se ignoran, no rompen el build. Prueba en Task 1.
- **Año nunca guardado** (sin fila en `CONTROL`) → la página envía `actualizado: ''` y el script no debe verlo como conflicto. Prueba en Task 3.
- **Lo que la gente escribe en la cuadrícula**: espacios alrededor, `1,5`, `1.234,5`, `-2`, `abc` → los dos primeros se aceptan, los tres últimos se marcan como error sin enviar nada. Prueba en Task 4.
- **Copia del build más vieja que el libro** (la lectura en vivo falló y otra persona guardó después) → el script responde conflicto y la página conserva el borrador. Prueba de `hayConflicto` en Task 3; borrador conservado verificado a mano en Task 5.

---

## Estructura de archivos

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `indicadores.py` | crear | Manifiesto de los 10 indicadores, lectura y validación del libro, bloque `DATA.indicadores` |
| `tests/test_indicadores.py` | crear | Pruebas de `indicadores.py` |
| `build_dashboard.py` | modificar | Llamar a `indicadores.construir()` en su propio `try` e incrustar el bloque |
| `tests/test_build.py` | modificar | `encode` lleva el bloque; `main` publica aunque el libro falle |
| `apps_script/indicadores.gs` | crear | Web app: `doGet`, `doPost`, validación pura |
| `tests/test_apps_script.py` | crear | Validación del `.gs` con node; ids iguales al manifiesto |
| `template.html` | modificar | Bloque `mod-indicadores`, CSS, pestaña, vista, editor, red |
| `tests/test_indicadores_js.py` | crear | Pruebas de `mod-indicadores` con node |
| `scripts/importar_indicadores.py` | crear | Importación única Hoja1 → CSV |
| `tests/test_importar_indicadores.py` | crear | Pruebas de la importación con un libro sintético |
| `README.md` | modificar | Sección de la pestaña y puesta en marcha |

Todas las pruebas se corren con `python -m pytest` desde la raíz del repo: `-m` pone la raíz en `sys.path`, que es como los tests importan `iaas`, `build_dashboard`, etc.

---

### Task 1: `indicadores.py` — manifiesto, lectura y validación

**Files:**
- Create: `indicadores.py`
- Test: `tests/test_indicadores.py`

**Interfaces:**
- Consumes: `iaas.indice_de_hojas(libro) -> dict[str, str]`, `iaas.descargar_hoja(hoja, gid, libro) -> DataFrame` (texto, vacíos como `""`), `iaas.texto(valor) -> str`, `iaas.IaasError`.
- Produces:
  - `ID_LIBRO: str`, `URL_SCRIPT: str` (vacías hasta la puesta en marcha)
  - `INDICADORES: list[dict]` con claves `id`, `nombre`, `numerador`, `denominador`, `k` (int)
  - `IDS: list[str]`
  - `HOJAS: dict[str, list[str]]`
  - `class IndicadoresError(Exception)`
  - `numero(valor, donde) -> int | float | None`
  - `descargar(libro=None) -> dict[str, DataFrame]`
  - `limpiar(libro: dict[str, DataFrame]) -> tuple[list, list, dict]` → `(valores, metas, control)`; `valores` = `[{"anio": int, "mes": int, "indicador": str, "n": num|None, "d": num|None}]`, `metas` = `[{"anio": int, "indicador": str, "meta": num}]`, `control` = `{"2026": "2026-10-16T12:00:00.000Z"}`
  - `construir(libro=None) -> dict` → `{"ok": True, "indicadores", "url_script", "valores", "metas", "control", "generado"}`
  - `bloque_fallido(error) -> dict` → `{"ok": False, "error": str, "fecha": str, "indicadores", "url_script"}`

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_indicadores.py`:

```python
"""Pruebas del libro de indicadores institucionales.

El libro lo escribe el Apps Script, pero también cualquiera con permiso de
edición en Google Sheets: las pruebas cubren lo que deja una edición a mano
—filas vacías, decimales con coma, un id mal escrito— además de lo que escribe
el script.
"""

from unittest.mock import patch

import pandas as pd
import pytest

import iaas
import indicadores


def hoja(filas, columnas):
    return pd.DataFrame(filas, columns=columnas, dtype=str).fillna("")


def libro(valores=(), metas=(), control=()):
    return {
        "VALORES": hoja(list(valores), indicadores.HOJAS["VALORES"]),
        "METAS": hoja(list(metas), indicadores.HOJAS["METAS"]),
        "CONTROL": hoja(list(control), indicadores.HOJAS["CONTROL"]),
    }


# --- manifiesto ------------------------------------------------------------

def test_el_manifiesto_tiene_los_diez_indicadores_con_ids_unicos():
    assert len(indicadores.INDICADORES) == 10
    assert len(set(indicadores.IDS)) == 10
    assert indicadores.IDS[0] == "incidencia_iaas"
    assert indicadores.IDS[-1] == "proporcion_dispositivo"


def test_cada_indicador_trae_textos_y_una_k_conocida():
    for ind in indicadores.INDICADORES:
        assert ind["k"] in (100, 1000), ind["id"]
        for campo in ("nombre", "numerador", "denominador"):
            assert ind[campo].strip(), (ind["id"], campo)


# --- números ---------------------------------------------------------------

@pytest.mark.parametrize("crudo, esperado", [
    ("", None), ("  ", None), ("12", 12), ("1.5", 1.5), ("1,5", 1.5),
    ("0", 0), (" 9939 ", 9939),
])
def test_numero_acepta_vacio_enteros_y_decimales_con_punto_o_coma(crudo, esperado):
    assert indicadores.numero(crudo, "aquí") == esperado


@pytest.mark.parametrize("crudo", ["-1", "abc", "1.234,5", "inf", "nan"])
def test_numero_rechaza_negativos_y_texto(crudo):
    with pytest.raises(indicadores.IndicadoresError, match="aquí"):
        indicadores.numero(crudo, "aquí")


# --- limpiar ---------------------------------------------------------------

def test_limpiar_convierte_las_tres_hojas():
    valores, metas, control = indicadores.limpiar(libro(
        valores=[["2026", "8", "incidencia_iaas", "12", "11099"],
                 ["2026", "9", "bacvc", "2", ""]],
        metas=[["2026", "incidencia_iaas", "1,5"]],
        control=[["2026", "2026-10-16T12:00:00.000Z"]],
    ))
    assert valores == [
        {"anio": 2026, "mes": 8, "indicador": "incidencia_iaas", "n": 12, "d": 11099},
        {"anio": 2026, "mes": 9, "indicador": "bacvc", "n": 2, "d": None},
    ]
    assert metas == [{"anio": 2026, "indicador": "incidencia_iaas", "meta": 1.5}]
    assert control == {"2026": "2026-10-16T12:00:00.000Z"}


def test_limpiar_ignora_filas_vacias():
    valores, metas, control = indicadores.limpiar(libro(
        valores=[["", "", "", "", ""], ["2026", "8", "navm", "8", "559"]],
        metas=[["", "", ""]],
        control=[["", ""]],
    ))
    assert [v["indicador"] for v in valores] == ["navm"]
    assert metas == [] and control == {}


def test_limpiar_ordena_por_anio_mes_y_orden_del_manifiesto():
    valores, _, _ = indicadores.limpiar(libro(valores=[
        ["2026", "9", "navm", "1", "2"],
        ["2026", "9", "incidencia_iaas", "1", "2"],
        ["2025", "12", "navm", "1", "2"],
    ]))
    assert [(v["anio"], v["mes"], v["indicador"]) for v in valores] == [
        (2025, 12, "navm"), (2026, 9, "incidencia_iaas"), (2026, 9, "navm")]


def test_limpiar_rechaza_un_id_desconocido_nombrando_la_fila():
    with pytest.raises(indicadores.IndicadoresError, match="VALORES fila 2.*navmi"):
        indicadores.limpiar(libro(valores=[["2026", "8", "navmi", "1", "2"]]))


@pytest.mark.parametrize("anio, mes", [("2019", "1"), ("2026", "13"), ("2026", "0"),
                                       ("2026.5", "1"), ("x", "1")])
def test_limpiar_rechaza_anio_o_mes_fuera_de_rango(anio, mes):
    with pytest.raises(indicadores.IndicadoresError, match="VALORES fila 2"):
        indicadores.limpiar(libro(valores=[[anio, mes, "navm", "1", "2"]]))


def test_limpiar_rechaza_un_mes_repetido():
    with pytest.raises(indicadores.IndicadoresError, match="repetido"):
        indicadores.limpiar(libro(valores=[["2026", "8", "navm", "1", "2"],
                                           ["2026", "8", "navm", "3", "4"]]))


def test_limpiar_rechaza_una_meta_repetida():
    with pytest.raises(indicadores.IndicadoresError, match="repetid"):
        indicadores.limpiar(libro(metas=[["2026", "navm", "1"],
                                         ["2026", "navm", "2"]]))


def test_limpiar_falla_si_falta_una_columna():
    roto = libro()
    roto["METAS"] = roto["METAS"].drop(columns=["META"])
    with pytest.raises(indicadores.IndicadoresError, match="METAS.*META"):
        indicadores.limpiar(roto)


# --- descargar y construir -------------------------------------------------

def test_descargar_sin_id_de_libro_explica_que_falta_configurarlo():
    with patch.object(indicadores, "ID_LIBRO", ""):
        with pytest.raises(indicadores.IndicadoresError, match="ID_LIBRO"):
            indicadores.descargar()


def test_descargar_nombra_las_hojas_que_faltan():
    with patch("iaas.indice_de_hojas", return_value={"VALORES": "0"}):
        with pytest.raises(indicadores.IndicadoresError, match="METAS"):
            indicadores.descargar("libro-x")


def test_descargar_traduce_los_errores_de_red():
    with patch("iaas.indice_de_hojas", side_effect=iaas.IaasError("HTTP 404")):
        with pytest.raises(indicadores.IndicadoresError, match="HTTP 404"):
            indicadores.descargar("libro-x")


def test_construir_devuelve_el_bloque_completo():
    with patch.object(indicadores, "descargar", return_value=libro(
            valores=[["2026", "8", "navm", "8", "559"]])):
        bloque = indicadores.construir("libro-x")
    assert bloque["ok"] is True
    assert bloque["indicadores"] == indicadores.INDICADORES
    assert bloque["url_script"] == indicadores.URL_SCRIPT
    assert bloque["valores"][0]["n"] == 8
    assert bloque["generado"].endswith("UTC")


def test_bloque_fallido_conserva_el_manifiesto_para_poder_leer_en_vivo():
    bloque = indicadores.bloque_fallido(indicadores.IndicadoresError("caído"))
    assert bloque["ok"] is False
    assert bloque["error"] == "caído"
    assert bloque["indicadores"] == indicadores.INDICADORES
    assert "url_script" in bloque and bloque["fecha"].endswith("UTC")
```

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `python -m pytest tests/test_indicadores.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'indicadores'`

- [ ] **Step 3: Escribir `indicadores.py`**

```python
"""Indicadores institucionales de PCI: el libro que se edita desde el dashboard.

A diferencia del resto de fuentes, este libro lo escribe la propia página a
través de un Apps Script (`apps_script/indicadores.gs`). El build solo lo lee,
por CSV público como el libro de IAAS, y deja una copia en `DATA.indicadores`
para cuando la lectura en vivo no responda.

Las definiciones de los indicadores viven aquí y no en el libro: el libro
guarda solo números, así que nadie rompe un indicador editando un texto.
"""

import math

import pandas as pd

import iaas

# Se rellenan en la puesta en marcha (sección 12 del diseño). La URL del
# script es pública por naturaleza: la página la necesita para leer y guardar.
ID_LIBRO = ""
URL_SCRIPT = ""

INDICADORES = [
    {"id": "incidencia_iaas", "nombre": "Tasa de Incidencia de IAAS",
     "numerador": "Casos nuevos (excluyendo Hemodiálisis y Diálisis Peritoneal, "
                  "Colitis Pseudomembranosa e ISQ)",
     "denominador": "Ingresos hospitalarios", "k": 100},
    {"id": "densidad_iaas", "nombre": "Densidad de Incidencia de IAAS",
     "numerador": "Casos nuevos (excluyendo Hemodiálisis y Diálisis Peritoneal, "
                  "Colitis Pseudomembranosa)",
     "denominador": "Días-paciente", "k": 1000},
    {"id": "bacvc",
     "nombre": "Densidad de Incidencia de Bacteriemia Asociada a Catéter "
               "Venoso Central",
     "numerador": "Casos nuevos de BACVC",
     "denominador": "Días de mantenimiento de CVC", "k": 1000},
    {"id": "bacteriemia_hd",
     "nombre": "Incidencia de Bacteriemia Asociada a Hemodiálisis",
     "numerador": "Casos nuevos de bacteriemia asociada a catéter de "
                  "hemodiálisis",
     "denominador": "Procedimientos de hemodiálisis", "k": 100},
    {"id": "peritonitis_dp",
     "nombre": "Incidencia de Peritonitis Asociada a Diálisis Peritoneal",
     "numerador": "Casos nuevos de peritonitis asociada a DP",
     "denominador": "Procedimientos de diálisis peritoneal", "k": 100},
    {"id": "navm",
     "nombre": "Densidad de Incidencia de Neumonía Asociada a Ventilación "
               "Mecánica",
     "numerador": "Casos nuevos de NAVM",
     "denominador": "Días de ventilación mecánica invasiva", "k": 1000},
    {"id": "ituacu",
     "nombre": "Densidad de Incidencia de ITU Asociada a Catéter Urinario",
     "numerador": "Casos nuevos de ITUACU",
     "denominador": "Días de catéter urinario", "k": 1000},
    {"id": "isq", "nombre": "Incidencia de Infección del Sitio Quirúrgico",
     "numerador": "Casos nuevos de ISQ IAAS",
     "denominador": "Procedimientos quirúrgicos", "k": 100},
    {"id": "colitis_cdiff",
     "nombre": "Incidencia de Colitis Pseudomembranosa por C. difficile",
     "numerador": "Casos nuevos de colitis pseudomembranosa",
     "denominador": "Egresos hospitalarios", "k": 100},
    {"id": "proporcion_dispositivo",
     "nombre": "Proporción por tipo de infección relacionada a dispositivo",
     "numerador": "IAAS a desagregar del periodo (BACVC, ITUACU, NAVMI, ISQ)",
     "denominador": "Total de IAAS del periodo", "k": 100},
]
IDS = [i["id"] for i in INDICADORES]

HOJAS = {
    "VALORES": ["ANIO", "MES", "INDICADOR", "NUMERADOR", "DENOMINADOR"],
    "METAS": ["ANIO", "INDICADOR", "META"],
    "CONTROL": ["ANIO", "ACTUALIZADO"],
}

ANIO_MIN, ANIO_MAX = 2020, 2100


class IndicadoresError(Exception):
    pass


def _ahora():
    return pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")


def numero(valor, donde):
    """Número ≥ 0 de una celda, o None si está vacía.

    Google exporta el CSV con el separador decimal de la configuración
    regional del libro: «1,5» es tan válido como «1.5». Con punto y coma a la
    vez («1.234,5») no se adivina cuál es el decimal: se rechaza.
    """
    t = iaas.texto(valor)
    if t == "":
        return None
    if "," in t and "." not in t:
        t = t.replace(",", ".")
    try:
        x = float(t)
    except ValueError:
        raise IndicadoresError(f"{donde}: «{valor}» no es un número.")
    if math.isnan(x) or math.isinf(x) or x < 0:
        raise IndicadoresError(f"{donde}: «{valor}» no es un número ≥ 0.")
    return int(x) if x.is_integer() else x


def _entero(valor, donde, minimo, maximo, que):
    x = numero(valor, donde)
    if x is None or not float(x).is_integer() or not minimo <= x <= maximo:
        raise IndicadoresError(
            f"{donde}: {que} «{valor}» fuera de rango ({minimo}–{maximo}).")
    return int(x)


def _indicador(valor, donde):
    t = iaas.texto(valor)
    if t not in IDS:
        raise IndicadoresError(
            f"{donde}: «{t}» no es un indicador conocido. Ids válidos: {IDS}.")
    return t


def _vacia(fila, columnas):
    return all(iaas.texto(fila[c]) == "" for c in columnas)


def descargar(libro=None):
    """{pestaña: DataFrame de texto} para las tres pestañas del libro."""
    libro = libro or ID_LIBRO
    if not libro:
        raise IndicadoresError(
            "El libro de indicadores aún no está configurado: falta ID_LIBRO "
            "en indicadores.py.")
    try:
        indice = iaas.indice_de_hojas(libro)
        faltan = [h for h in HOJAS if h not in indice]
        if faltan:
            raise IndicadoresError(
                f"El libro de indicadores no tiene estas pestañas: {faltan}. "
                f"Tiene {sorted(indice)}.")
        return {h: iaas.descargar_hoja(h, indice[h], libro) for h in HOJAS}
    except iaas.IaasError as error:
        raise IndicadoresError(f"Libro de indicadores: {error}") from error


def limpiar(libro):
    """(valores, metas, control) validados a partir de las tres pestañas."""
    for hoja, columnas in HOJAS.items():
        faltan = [c for c in columnas if c not in libro[hoja].columns]
        if faltan:
            raise IndicadoresError(
                f"La pestaña «{hoja}» del libro de indicadores no tiene estas "
                f"columnas: {faltan}.")

    # Fila 1 del Sheet es la cabecera: la fila i del DataFrame es la i + 2.
    valores, vistos = [], set()
    for i, fila in libro["VALORES"].iterrows():
        if _vacia(fila, HOJAS["VALORES"]):
            continue
        donde = f"VALORES fila {i + 2}"
        anio = _entero(fila["ANIO"], donde, ANIO_MIN, ANIO_MAX, "año")
        mes = _entero(fila["MES"], donde, 1, 12, "mes")
        ind = _indicador(fila["INDICADOR"], donde)
        if (anio, mes, ind) in vistos:
            raise IndicadoresError(
                f"{donde}: {ind} de {mes}/{anio} está repetido.")
        vistos.add((anio, mes, ind))
        valores.append({"anio": anio, "mes": mes, "indicador": ind,
                        "n": numero(fila["NUMERADOR"], donde),
                        "d": numero(fila["DENOMINADOR"], donde)})
    valores.sort(key=lambda v: (v["anio"], v["mes"], IDS.index(v["indicador"])))

    metas, vistas = [], set()
    for i, fila in libro["METAS"].iterrows():
        if _vacia(fila, HOJAS["METAS"]):
            continue
        donde = f"METAS fila {i + 2}"
        anio = _entero(fila["ANIO"], donde, ANIO_MIN, ANIO_MAX, "año")
        ind = _indicador(fila["INDICADOR"], donde)
        if (anio, ind) in vistas:
            raise IndicadoresError(f"{donde}: la meta de {ind} en {anio} está repetida.")
        vistas.add((anio, ind))
        meta = numero(fila["META"], donde)
        if meta is not None:
            metas.append({"anio": anio, "indicador": ind, "meta": meta})
    metas.sort(key=lambda m: (m["anio"], IDS.index(m["indicador"])))

    control = {}
    for i, fila in libro["CONTROL"].iterrows():
        if _vacia(fila, HOJAS["CONTROL"]):
            continue
        donde = f"CONTROL fila {i + 2}"
        anio = _entero(fila["ANIO"], donde, ANIO_MIN, ANIO_MAX, "año")
        control[str(anio)] = iaas.texto(fila["ACTUALIZADO"])
    return valores, metas, control


def _base():
    return {"indicadores": INDICADORES, "url_script": URL_SCRIPT}


def construir(libro=None):
    """Descarga y valida el libro. Devuelve el bloque DATA.indicadores."""
    valores, metas, control = limpiar(descargar(libro))
    return {"ok": True, **_base(), "valores": valores, "metas": metas,
            "control": control, "generado": _ahora()}


def bloque_fallido(error):
    """Bloque sin copia del libro. Conserva el manifiesto y la URL del script:
    la página puede seguir leyendo en vivo aunque el build no pudiera."""
    return {"ok": False, "error": str(error), "fecha": _ahora(), **_base()}
```

- [ ] **Step 4: Correr las pruebas y ver que pasan**

Run: `python -m pytest tests/test_indicadores.py -q`
Expected: PASS (todas)

- [ ] **Step 5: Commit**

```bash
git add indicadores.py tests/test_indicadores.py
git commit -m "feat: manifiesto y lectura del libro de indicadores institucionales"
```

---

### Task 2: integrar el bloque en el build

**Files:**
- Modify: `build_dashboard.py` (imports al inicio; `encode` ~línea 399; `main` tras el bloque de vigilancia ~línea 582)
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `indicadores.construir()`, `indicadores.bloque_fallido(error)`, `indicadores.IndicadoresError` (Task 1).
- Produces: `encode(df, formularios, iaas=None, vigilancia=None, institucionales=None)`; `DATA.indicadores` siempre presente en el HTML (con `ok` true o false, y siempre con `indicadores` y `url_script`).

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir a `tests/test_build.py` (junto a `test_encode_lleva_las_dos_fuentes_de_iaas_por_separado`); añadir `import indicadores` a los imports del archivo:

```python
def test_encode_lleva_el_bloque_de_indicadores(registros_ok, formularios_ok,
                                               nombres_ok):
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    bloque = {"ok": True, "valores": [], "metas": [], "control": {}}
    data = encode(limpio, formularios_ok, institucionales=bloque)
    assert data["indicadores"] is bloque


def test_encode_sin_indicadores_deja_un_bloque_fallido_con_manifiesto(
        registros_ok, formularios_ok, nombres_ok):
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    data = encode(limpio, formularios_ok)
    assert data["indicadores"]["ok"] is False
    assert data["indicadores"]["indicadores"] == indicadores.INDICADORES


def test_main_publica_igual_cuando_el_libro_de_indicadores_falla(libro_real,
                                                                  capsys):
    capturado = {}

    def espia(data, template, vendor, salida):
        capturado["data"] = data
        return 0

    with patch("build_dashboard.indicadores.construir",
               side_effect=indicadores.IndicadoresError("HTTP 404")), \
         patch("build_dashboard.render_html", side_effect=espia):
        codigo = build_dashboard.main([str(libro_real)])

    assert codigo == 0
    assert capturado["data"]["indicadores"]["ok"] is False
    assert capturado["data"]["indicadores"]["error"] == "HTTP 404"
    salida = capsys.readouterr()
    assert "AVISO: no se pudieron construir los indicadores: HTTP 404" in salida.err
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python -m pytest tests/test_build.py -q -k indicadores`
Expected: FAIL (`unexpected keyword argument 'institucionales'` / `KeyError: 'indicadores'`)

- [ ] **Step 3: Implementar**

En los imports de `build_dashboard.py`, junto a `import iaas as vigilancia`:

```python
import indicadores
```

Firma y retorno de `encode`:

```python
def encode(df, formularios, iaas=None, vigilancia=None, institucionales=None):
```

y en el diccionario devuelto, justo después de la clave `"vigilancia"`:

```python
        # A diferencia de las otras fuentes, el bloque fallido conserva el
        # manifiesto: la página puede leer el libro en vivo sin la copia.
        "indicadores": institucionales or indicadores.bloque_fallido(
            "No se consultó el libro de indicadores."),
```

En `main`, después del `except vigilancia.IaasError` y antes de `data = encode(...)`:

```python
    # Indicadores institucionales: libro propio, que la página también escribe.
    try:
        institucionales = indicadores.construir()
        print(f"Indicadores: {len(institucionales['valores'])} valores "
              f"mensuales, {len(institucionales['metas'])} metas")
    except indicadores.IndicadoresError as error:
        institucionales = indicadores.bloque_fallido(error)
        print(f"AVISO: no se pudieron construir los indicadores: {error}",
              file=sys.stderr)
```

y la llamada:

```python
    data = encode(limpio, formularios, iaas=investigacion,
                  vigilancia=casos, institucionales=institucionales)
```

- [ ] **Step 4: Correr toda la suite**

Run: `python -m pytest -q`
Expected: PASS. (Mientras `ID_LIBRO` esté vacío, las pruebas de `main` existentes ven el aviso de configuración y siguen pasando.)

- [ ] **Step 5: Commit**

```bash
git add build_dashboard.py tests/test_build.py
git commit -m "feat: incrustar el bloque de indicadores en el dashboard"
```

---

### Task 3: Apps Script

**Files:**
- Create: `apps_script/indicadores.gs`
- Test: `tests/test_apps_script.py`

**Interfaces:**
- Consumes: `indicadores.IDS` (solo en la prueba de coherencia).
- Produces (contrato HTTP que usa la Task 5):
  - `GET <URL_SCRIPT>` → `{ok: true, valores: [{anio, mes, indicador, n, d}], metas: [{anio, indicador, meta}], control: {"2026": "<ISO>"}}` o `{ok: false, error}`
  - `POST <URL_SCRIPT>` cuerpo `{clave, anio, actualizado, valores: [{mes, indicador, n, d}], metas: [{indicador, meta}]}` → `{ok: true, anio, valores, metas, actualizado}` o `{ok: false, error}` o `{ok: false, conflicto: true, error}`
  - Funciones puras: `validarPeticion(cuerpo) -> string|null`, `hayConflicto(control, anio, actualizado) -> bool`

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_apps_script.py`:

```python
"""Pruebas de la parte pura del Apps Script de indicadores.

El `.gs` no corre en CI —necesita SpreadsheetApp—, pero sus validaciones son
JavaScript sin dependencias: el archivo solo declara constantes y funciones,
así que node lo puede cargar entero y llamar a las que no tocan Google.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import indicadores

GS = Path(__file__).resolve().parent.parent / "apps_script" / "indicadores.gs"

requiere_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="requiere node")


def ejecutar(expresion):
    guion = f"{GS.read_text(encoding='utf-8')}\nconsole.log(JSON.stringify({expresion}));\n"
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, encoding="utf-8")
    if salida.returncode != 0:
        raise AssertionError(f"node falló:\n{salida.stderr}")
    return json.loads(salida.stdout)


def peticion(**cambios):
    cuerpo = {"clave": "x", "anio": 2026, "actualizado": "",
              "valores": [{"mes": 8, "indicador": "navm", "n": 8, "d": 559}],
              "metas": [{"indicador": "navm", "meta": 10}]}
    cuerpo.update(cambios)
    return json.dumps(cuerpo)


def test_los_ids_del_script_son_los_del_manifiesto():
    ids = re.search(r"const INDICADORES = \[(.*?)\];",
                    GS.read_text(encoding="utf-8"), re.S)
    assert ids, "indicadores.gs ya no declara const INDICADORES = [...]"
    assert re.findall(r"'([a-z_]+)'", ids[1]) == indicadores.IDS


@requiere_node
def test_una_peticion_correcta_no_tiene_error():
    assert ejecutar(f"validarPeticion({peticion()})") is None


@requiere_node
def test_valores_y_metas_vacios_son_validos():
    assert ejecutar(
        f"validarPeticion({peticion(valores=[{'mes': 1, 'indicador': 'navm', 'n': None, 'd': None}], metas=[])})"
    ) is None


@requiere_node
@pytest.mark.parametrize("cambios, motivo", [
    ({"anio": 2019}, "Año"),
    ({"anio": 2026.5}, "Año"),
    ({"valores": [{"mes": 13, "indicador": "navm", "n": 1, "d": 2}]}, "Mes"),
    ({"valores": [{"mes": 1, "indicador": "navmi", "n": 1, "d": 2}]}, "desconocido"),
    ({"valores": [{"mes": 1, "indicador": "navm", "n": -1, "d": 2}]}, "no válido"),
    ({"valores": [{"mes": 1, "indicador": "navm", "n": "8", "d": 2}]}, "no válido"),
    ({"valores": [{"mes": 1, "indicador": "navm", "n": 1, "d": 2},
                  {"mes": 1, "indicador": "navm", "n": 3, "d": 4}]}, "Repetido"),
    ({"metas": [{"indicador": "navm", "meta": None}]}, "Meta"),
    ({"metas": [{"indicador": "navm", "meta": -3}]}, "Meta"),
    ({"metas": "nada"}, "Faltan"),
])
def test_validar_peticion_rechaza(cambios, motivo):
    error = ejecutar(f"validarPeticion({peticion(**cambios)})")
    assert error and motivo in error


@requiere_node
def test_un_anio_nunca_guardado_no_es_conflicto():
    assert ejecutar("hayConflicto({}, 2026, '')") is False


@requiere_node
def test_misma_marca_no_es_conflicto_y_otra_si():
    marca = "2026-10-16T12:00:00.000Z"
    assert ejecutar(f"hayConflicto({{'2026': '{marca}'}}, 2026, '{marca}')") is False
    assert ejecutar(f"hayConflicto({{'2026': '{marca}'}}, 2026, '')") is True
    assert ejecutar(f"hayConflicto({{}}, 2026, '{marca}')") is True
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python -m pytest tests/test_apps_script.py -q`
Expected: FAIL (`FileNotFoundError` sobre `apps_script/indicadores.gs`)

- [ ] **Step 3: Escribir `apps_script/indicadores.gs`**

```javascript
/**
 * Indicadores institucionales de PCI: lectura y escritura del libro.
 *
 * Se pega en Extensiones → Apps Script del libro de indicadores y se despliega
 * como aplicación web («Ejecutar como: yo», «Quién tiene acceso: cualquier
 * usuario»). La clave del equipo va en Configuración del proyecto →
 * Propiedades del script → CLAVE; nunca en este archivo.
 *
 * Las funciones de validación no tocan SpreadsheetApp: tests/test_apps_script.py
 * las carga con node. La lista de ids debe coincidir con indicadores.py; esa
 * misma prueba lo comprueba.
 */

const INDICADORES = [
  'incidencia_iaas', 'densidad_iaas', 'bacvc', 'bacteriemia_hd',
  'peritonitis_dp', 'navm', 'ituacu', 'isq', 'colitis_cdiff',
  'proporcion_dispositivo',
];
const ANIO_MIN = 2020;
const ANIO_MAX = 2100;
const CABECERAS = {
  VALORES: ['ANIO', 'MES', 'INDICADOR', 'NUMERADOR', 'DENOMINADOR'],
  METAS: ['ANIO', 'INDICADOR', 'META'],
  CONTROL: ['ANIO', 'ACTUALIZADO'],
};
const MENSAJE_CONFLICTO =
  'Otra persona guardó cambios en este año; recarga para verlos';

// --- Funciones puras -------------------------------------------------------

function esNumeroValido(x) {
  return x === null || (typeof x === 'number' && isFinite(x) && x >= 0);
}

/** null si la petición es válida; si no, el motivo. No mira la clave. */
function validarPeticion(cuerpo) {
  if (!cuerpo || typeof cuerpo !== 'object') return 'Petición vacía';
  const anio = cuerpo.anio;
  if (!Number.isInteger(anio) || anio < ANIO_MIN || anio > ANIO_MAX) {
    return 'Año fuera de rango: ' + anio;
  }
  if (!Array.isArray(cuerpo.valores) || !Array.isArray(cuerpo.metas)) {
    return 'Faltan valores o metas';
  }
  const vistos = {};
  for (const v of cuerpo.valores) {
    if (!Number.isInteger(v.mes) || v.mes < 1 || v.mes > 12) {
      return 'Mes fuera de rango: ' + v.mes;
    }
    if (INDICADORES.indexOf(v.indicador) < 0) {
      return 'Indicador desconocido: ' + v.indicador;
    }
    if (!esNumeroValido(v.n) || !esNumeroValido(v.d)) {
      return 'Valor no válido en ' + v.indicador + ', mes ' + v.mes;
    }
    const clave = v.indicador + '|' + v.mes;
    if (vistos[clave]) return 'Repetido: ' + clave;
    vistos[clave] = true;
  }
  for (const m of cuerpo.metas) {
    if (INDICADORES.indexOf(m.indicador) < 0) {
      return 'Indicador desconocido: ' + m.indicador;
    }
    if (m.meta === null || !esNumeroValido(m.meta)) {
      return 'Meta no válida en ' + m.indicador;
    }
  }
  return null;
}

/** La página guarda sobre lo que leyó; si el año cambió desde entonces, no. */
function hayConflicto(control, anio, actualizado) {
  return (control[String(anio)] || '') !== (actualizado || '');
}

function aCelda(x) { return x === null ? '' : x; }
function deCelda(x) { return x === '' || x === null ? null : Number(x); }

// --- Libro -----------------------------------------------------------------

function hoja(nombre) {
  return SpreadsheetApp.getActiveSpreadsheet().getSheetByName(nombre);
}

/** Filas de datos de una pestaña, sin cabecera ni filas vacías. */
function leerFilas(nombre) {
  return hoja(nombre).getDataRange().getValues().slice(1)
    .filter(f => f[0] !== '');
}

function leerTodo() {
  const valores = leerFilas('VALORES').map(f => ({
    anio: Number(f[0]), mes: Number(f[1]), indicador: String(f[2]),
    n: deCelda(f[3]), d: deCelda(f[4]),
  }));
  const metas = leerFilas('METAS').map(f => ({
    anio: Number(f[0]), indicador: String(f[1]), meta: deCelda(f[2]),
  })).filter(m => m.meta !== null);
  const control = {};
  leerFilas('CONTROL').forEach(f => { control[String(f[0])] = String(f[1]); });
  return {valores, metas, control};
}

/** Reemplaza las filas del año `anio` de una pestaña por `nuevas`. */
function reescribir(nombre, anio, nuevas) {
  const cabecera = CABECERAS[nombre];
  const resto = leerFilas(nombre).filter(f => Number(f[0]) !== anio);
  const todas = [cabecera].concat(resto, nuevas);
  const h = hoja(nombre);
  h.clearContents();
  h.getRange(1, 1, todas.length, cabecera.length).setValues(todas);
}

function responder(objeto) {
  return ContentService.createTextOutput(JSON.stringify(objeto))
    .setMimeType(ContentService.MimeType.JSON);
}

// --- Web app ---------------------------------------------------------------

function doGet() {
  try {
    return responder(Object.assign({ok: true}, leerTodo()));
  } catch (error) {
    return responder({ok: false, error: String(error)});
  }
}

function doPost(e) {
  let cuerpo;
  try {
    cuerpo = JSON.parse(e.postData.contents);
  } catch (error) {
    return responder({ok: false, error: 'Petición ilegible'});
  }
  const clave = PropertiesService.getScriptProperties().getProperty('CLAVE');
  if (!clave || cuerpo.clave !== clave) {
    return responder({ok: false, error: 'Clave incorrecta'});
  }
  const motivo = validarPeticion(cuerpo);
  if (motivo) return responder({ok: false, error: motivo});

  const cerrojo = LockService.getScriptLock();
  if (!cerrojo.tryLock(10000)) {
    return responder({ok: false, error: 'El libro está ocupado; inténtalo de nuevo'});
  }
  try {
    const anio = cuerpo.anio;
    if (hayConflicto(leerTodo().control, anio, cuerpo.actualizado)) {
      return responder({ok: false, conflicto: true, error: MENSAJE_CONFLICTO});
    }
    reescribir('VALORES', anio, cuerpo.valores.map(v =>
      [anio, v.mes, v.indicador, aCelda(v.n), aCelda(v.d)]));
    reescribir('METAS', anio, cuerpo.metas.map(m => [anio, m.indicador, m.meta]));
    // Como texto: si Sheets convierte la marca en fecha, deja de coincidir con
    // la que la página leyó y todo guardado posterior sería un conflicto.
    hoja('CONTROL').getRange('B:B').setNumberFormat('@');
    const actualizado = new Date().toISOString();
    reescribir('CONTROL', anio, [[anio, actualizado]]);
    return responder({ok: true, anio, valores: cuerpo.valores,
                      metas: cuerpo.metas, actualizado});
  } finally {
    cerrojo.releaseLock();
  }
}
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python -m pytest tests/test_apps_script.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps_script/indicadores.gs tests/test_apps_script.py
git commit -m "feat: Apps Script para leer y guardar los indicadores"
```

---

### Task 4: módulo puro `mod-indicadores`

**Files:**
- Modify: `template.html` — insertar un bloque `<script id="mod-indicadores">` justo antes de `<script id="mod-charts">` (hoy ~línea 1053)
- Test: `tests/test_indicadores_js.py`

**Interfaces:**
- Consumes: nada (funciones puras).
- Produces: global `indicadoresMod` con
  - `MESES: string[12]` (`'Ene'`…`'Dic'`)
  - `tasa(n, d, k) -> number|null`
  - `validar(texto) -> {ok: true, valor: number|null} | {ok: false, error: string}`
  - `estadoMeta(t, meta) -> 'sobre'|'dentro'|null`
  - `anios(datos, actual) -> number[]`
  - `tablaAnio(datos, anio) -> [{indicador, meta, meses: [{n, d, t, estado}] ×12}]`
  - `borradorDeAnio(datos, anio) -> {anio, valores: {id: [{n: string, d: string}] ×12}, metas: {id: string}}`
  - `validarBorrador(borrador) -> {errores: [{indicador, mes, campo, error}], valores: [{mes, indicador, n, d}], metas: [{indicador, meta}]}`
  - `reemplazarAnio(datos, anio, valores, metas, actualizado) -> datos`
  - donde `datos = {indicadores, valores: [{anio, mes, indicador, n, d}], metas: [{anio, indicador, meta}], control: {}}`

(Nota: el diseño nombra `aplicarBorrador`; aquí queda partido en `validarBorrador` y `reemplazarAnio`, porque entre una y otra está el viaje al script.)

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_indicadores_js.py`:

```python
"""Pruebas de `mod-indicadores`, el cálculo y la validación de la cuadrícula.

El bloque vive en `template.html` y se extrae tal cual, como en
`tests/test_vigilancia_js.py`, para que la prueba no se quede atrás del
template.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parent.parent / "template.html"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="requiere node para ejecutar el módulo")

IND = [{"id": "incidencia_iaas", "k": 100}, {"id": "navm", "k": 1000}]


def ejecutar(expresion, datos=None):
    html = TEMPLATE.read_text(encoding="utf-8")
    bloque = re.search(r'<script id="mod-indicadores">(.*?)</script>', html, re.S)
    assert bloque, "template.html ya no trae el bloque «mod-indicadores»"
    guion = (f"{bloque[1]}\nconst m = indicadoresMod;\n"
             f"const datos = {json.dumps(datos)};\n"
             f"console.log(JSON.stringify({expresion}));\n")
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, encoding="utf-8")
    if salida.returncode != 0:
        raise AssertionError(f"node falló:\n{salida.stderr}")
    return json.loads(salida.stdout)


def datos(valores=(), metas=(), control=None):
    return {"indicadores": IND, "valores": list(valores),
            "metas": list(metas), "control": control or {}}


def test_tasa_es_n_entre_d_por_k():
    assert ejecutar("m.tasa(12, 11099, 100)") == pytest.approx(0.10812, rel=1e-3)


@pytest.mark.parametrize("n, d", [("null", "10"), ("3", "null"), ("3", "0")])
def test_tasa_vacia_sin_n_sin_d_o_con_d_cero(n, d):
    assert ejecutar(f"m.tasa({n}, {d}, 100)") is None


@pytest.mark.parametrize("texto, valor", [
    ("", None), ("   ", None), ("12", 12), (" 12 ", 12), ("1,5", 1.5),
    ("1.5", 1.5), ("0", 0)])
def test_validar_acepta(texto, valor):
    assert ejecutar(f"m.validar({json.dumps(texto)})") == {"ok": True, "valor": valor}


@pytest.mark.parametrize("texto", ["-2", "abc", "1.234,5", "1e3", "1,2,3"])
def test_validar_rechaza(texto):
    assert ejecutar(f"m.validar({json.dumps(texto)}).ok") is False


def test_estado_meta_es_un_tope():
    assert ejecutar("[m.estadoMeta(2, 1.5), m.estadoMeta(1.5, 1.5), "
                    "m.estadoMeta(1, 1.5), m.estadoMeta(null, 1.5), "
                    "m.estadoMeta(2, null)]") == ["sobre", "dentro", "dentro", None, None]


def test_anios_junta_los_que_tienen_datos_y_el_actual():
    d = datos(valores=[{"anio": 2025, "mes": 1, "indicador": "navm", "n": 1, "d": 2}],
              metas=[{"anio": 2027, "indicador": "navm", "meta": 1}])
    assert ejecutar("m.anios(datos, 2026)", d) == [2025, 2026, 2027]


def test_tabla_anio_calcula_t_y_compara_con_la_meta():
    d = datos(valores=[{"anio": 2026, "mes": 8, "indicador": "incidencia_iaas",
                        "n": 3, "d": 100}],
              metas=[{"anio": 2026, "indicador": "incidencia_iaas", "meta": 2}])
    fila = ejecutar("m.tablaAnio(datos, 2026)[0]", d)
    assert fila["meta"] == 2
    assert len(fila["meses"]) == 12
    assert fila["meses"][7] == {"n": 3, "d": 100, "t": 3, "estado": "sobre"}
    assert fila["meses"][0] == {"n": None, "d": None, "t": None, "estado": None}


def test_borrador_y_validacion_ida_y_vuelta():
    d = datos(valores=[{"anio": 2026, "mes": 8, "indicador": "navm", "n": 8, "d": 559}],
              metas=[{"anio": 2026, "indicador": "navm", "meta": 1.5}])
    r = ejecutar("m.validarBorrador(m.borradorDeAnio(datos, 2026))", d)
    assert r == {"errores": [],
                 "valores": [{"mes": 8, "indicador": "navm", "n": 8, "d": 559}],
                 "metas": [{"indicador": "navm", "meta": 1.5}]}


def test_validar_borrador_marca_cada_celda_mal_escrita():
    r = ejecutar("""(() => {
        const b = m.borradorDeAnio(datos, 2026);
        b.valores.navm[0] = {n: '-1', d: '10'};
        b.valores.navm[1] = {n: '2', d: 'abc'};
        b.metas.navm = 'x';
        return m.validarBorrador(b);
    })()""", datos())
    assert [(e["indicador"], e["mes"], e["campo"]) for e in r["errores"]] == [
        ("navm", 1, "n"), ("navm", 2, "d"), ("navm", None, "meta")]


def test_validar_borrador_omite_los_meses_completamente_vacios():
    r = ejecutar("m.validarBorrador(m.borradorDeAnio(datos, 2026))", datos())
    assert r["valores"] == [] and r["metas"] == []


def test_reemplazar_anio_solo_toca_ese_anio():
    d = datos(valores=[{"anio": 2025, "mes": 1, "indicador": "navm", "n": 1, "d": 2},
                       {"anio": 2026, "mes": 1, "indicador": "navm", "n": 9, "d": 9}],
              control={"2025": "a"})
    r = ejecutar("m.reemplazarAnio(datos, 2026, "
                 "[{mes: 2, indicador: 'navm', n: 3, d: 4}], [], 'b')", d)
    assert r["valores"] == [
        {"anio": 2025, "mes": 1, "indicador": "navm", "n": 1, "d": 2},
        {"anio": 2026, "mes": 2, "indicador": "navm", "n": 3, "d": 4}]
    assert r["control"] == {"2025": "a", "2026": "b"}
    assert r["indicadores"] == IND
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python -m pytest tests/test_indicadores_js.py -q`
Expected: FAIL con «template.html ya no trae el bloque «mod-indicadores»»

- [ ] **Step 3: Añadir el bloque a `template.html`** (antes de `<script id="mod-charts">`)

```html
<script id="mod-indicadores">
/** Indicadores institucionales: cálculo, validación y borradores.
 *
 * Funciones puras: la red y el DOM viven en mod-views. Se prueban con node en
 * tests/test_indicadores_js.py.
 */
const indicadoresMod = (() => {
  const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];

  /** T = N / D · k. Sin N, sin D o con D = 0 no hay tasa: ni 0 ni infinito. */
  function tasa(n, d, k) {
    if (n === null || d === null || d === 0) return null;
    return n / d * k;
  }

  /** Texto de una celda → número ≥ 0, o null si está vacía.
   *
   * Se acepta la coma decimal porque es la que escribe el equipo. Con punto y
   * coma a la vez no se adivina cuál es el decimal: es un error.
   */
  function validar(texto) {
    const limpio = String(texto === null || texto === undefined ? '' : texto)
      .trim().replace(',', '.');
    if (limpio === '') return {ok: true, valor: null};
    if (!/^\d+(\.\d+)?$/.test(limpio)) {
      return {ok: false, error: 'Debe ser un número mayor o igual que 0'};
    }
    return {ok: true, valor: Number(limpio)};
  }

  /** La meta es un tope: superarla es 'sobre'; igualarla o quedar debajo,
   * 'dentro'. Sin tasa o sin meta no hay comparación. */
  function estadoMeta(t, meta) {
    if (t === null || meta === null || meta === undefined) return null;
    return t > meta ? 'sobre' : 'dentro';
  }

  /** Años del selector: los que tienen datos más el actual, en orden. */
  function anios(datos, actual) {
    const s = new Set([actual]);
    datos.valores.forEach(v => s.add(v.anio));
    datos.metas.forEach(m => s.add(m.anio));
    return [...s].sort((a, b) => a - b);
  }

  /** Una fila por indicador con sus doce meses ya calculados. */
  function tablaAnio(datos, anio) {
    return datos.indicadores.map(ind => {
      const m = datos.metas.find(x => x.anio === anio && x.indicador === ind.id);
      const meta = m ? m.meta : null;
      const meses = MESES.map((_, i) => {
        const v = datos.valores.find(x =>
          x.anio === anio && x.mes === i + 1 && x.indicador === ind.id);
        const n = v ? v.n : null;
        const d = v ? v.d : null;
        const t = tasa(n, d, ind.k);
        return {n, d, t, estado: estadoMeta(t, meta)};
      });
      return {indicador: ind, meta, meses};
    });
  }

  /** Borrador editable de un año: los mismos números, como texto. */
  function borradorDeAnio(datos, anio) {
    const texto = x => x === null ? '' : String(x);
    const valores = {};
    const metas = {};
    for (const fila of tablaAnio(datos, anio)) {
      const id = fila.indicador.id;
      valores[id] = fila.meses.map(c => ({n: texto(c.n), d: texto(c.d)}));
      metas[id] = texto(fila.meta);
    }
    return {anio, valores, metas};
  }

  /** Borrador → lo que se envía al script, o las celdas mal escritas.
   * Los meses sin N ni D no se envían: no son una fila del libro. */
  function validarBorrador(borrador) {
    const errores = [];
    const valores = [];
    const metas = [];
    for (const [id, meses] of Object.entries(borrador.valores)) {
      meses.forEach((celda, i) => {
        const n = validar(celda.n);
        const d = validar(celda.d);
        if (!n.ok) errores.push({indicador: id, mes: i + 1, campo: 'n', error: n.error});
        if (!d.ok) errores.push({indicador: id, mes: i + 1, campo: 'd', error: d.error});
        if (n.ok && d.ok && (n.valor !== null || d.valor !== null)) {
          valores.push({mes: i + 1, indicador: id, n: n.valor, d: d.valor});
        }
      });
    }
    for (const [id, texto] of Object.entries(borrador.metas)) {
      const m = validar(texto);
      if (!m.ok) errores.push({indicador: id, mes: null, campo: 'meta', error: m.error});
      else if (m.valor !== null) metas.push({indicador: id, meta: m.valor});
    }
    return {errores, valores, metas};
  }

  /** Datos con el año `anio` sustituido por lo que guardó el script. */
  function reemplazarAnio(datos, anio, valores, metas, actualizado) {
    return {
      ...datos,
      valores: datos.valores.filter(v => v.anio !== anio)
        .concat(valores.map(v => ({anio, ...v}))),
      metas: datos.metas.filter(m => m.anio !== anio)
        .concat(metas.map(m => ({anio, ...m}))),
      control: {...datos.control, [anio]: actualizado},
    };
  }

  return {MESES, tasa, validar, estadoMeta, anios, tablaAnio, borradorDeAnio,
          validarBorrador, reemplazarAnio};
})();
</script>
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python -m pytest tests/test_indicadores_js.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add template.html tests/test_indicadores_js.py
git commit -m "feat: cálculo y validación de la cuadrícula de indicadores"
```

---

### Task 5: pestaña, vista, editor y red

**Files:**
- Modify: `template.html` — CSS (al final del `<style>`), botón de pestaña (~línea 207), `mod-views` (`render()` ~línea 1521 y funciones nuevas antes de `renderGlobal`), `mod-app` (`construirBarra` ~línea 3106)

**Interfaces:**
- Consumes: `indicadoresMod` (Task 4); contrato HTTP del script (Task 3); `DATA.indicadores` (Tasks 1–2) con `ok`, `indicadores`, `url_script`, y si `ok`: `valores`, `metas`, `control`, `generado`; si no: `error`.
- Produces: vista `'indicadores'` en `views.render()`.

- [ ] **Step 1: CSS** — añadir al final del bloque `<style>`:

```css
/* Indicadores institucionales */
.ind-barra { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0; }
.ind-barra select, .ind-barra input {
  font: inherit; font-size: 13px; padding: 4px 8px; border-radius: 6px;
  background: var(--surface); color: var(--text-primary); border: 1px solid var(--border);
}
.ind-tabla { overflow-x: auto; }
.ind-tabla th, .ind-tabla td { white-space: nowrap; vertical-align: top; }
.ind-tabla td.ind-nombre { white-space: normal; min-width: 220px; }
.ind-t { font-weight: 600; font-variant-numeric: tabular-nums; }
.ind-nd { color: var(--text-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
td.ind-sobre .ind-t { color: var(--critical); }
td.ind-dentro .ind-t { color: var(--good); }
td.ind-futuro { opacity: 0.45; }
.ind-tabla input {
  display: block; width: 72px; margin: 2px 0; padding: 3px 5px; font: inherit; font-size: 12px;
  background: var(--surface); color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px;
}
.ind-tabla input.ind-error { border-color: var(--critical); outline: 1px solid var(--critical); }
.ind-mensaje.error { color: var(--critical); }
.ind-mensaje.ok { color: var(--good); }
```

- [ ] **Step 2: botón de pestaña** — después del de vigilancia:

```html
    <button role="tab" data-view="indicadores" aria-selected="false">Indicadores</button>
```

- [ ] **Step 3: ocultar la barra de filtros en la pestaña** — en `mod-app`, dentro de `construirBarra()`, justo después de `controles.length = 0;`:

```js
    // Los indicadores no se filtran: son una cuadrícula por año. Sin esto
    // saldrían los filtros de supervisiones, que no les aplican.
    const panel = barra.closest('.panel');
    const sinFiltros = views.estado.vista === 'indicadores';
    panel.style.display = sinFiltros ? 'none' : '';
    if (sinFiltros) return;
```

- [ ] **Step 4: enrutar la vista** — en `render()` de `mod-views`, junto a las otras dos líneas de IAAS:

```js
    if (estado.vista === 'indicadores') { renderIndicadores(); return; }
```

- [ ] **Step 5: estado, red y vista** — en `mod-views`, antes del comentario `// renderGlobal, renderResponsable y renderFormulario...`:

```js
  // --- Indicadores institucionales -----------------------------------------
  // Estado propio: sobrevive a los repintados y a los cambios de pestaña. La
  // copia del build se pinta al instante; la lectura en vivo la reemplaza.
  const ind = {
    datos: {
      indicadores: DATA.indicadores.indicadores,
      valores: DATA.indicadores.ok ? DATA.indicadores.valores : [],
      metas: DATA.indicadores.ok ? DATA.indicadores.metas : [],
      control: DATA.indicadores.ok ? DATA.indicadores.control : {},
    },
    vivo: false,       // los datos vienen del script, no de la copia
    leyendo: false,    // la lectura en vivo está en curso
    pedido: false,     // la lectura en vivo se lanza una sola vez
    anio: new Date().getFullYear(),
    borrador: null,    // distinto de null mientras la cuadrícula está abierta
    errores: [],
    mensaje: null,     // {tipo: 'error' | 'ok', texto}
    guardando: false,
    clave: '',
  };
  const CLAVE_SESION = 'pci-indicadores-clave';
  // sessionStorage puede no existir o lanzar (ventana privada, bloqueo): la
  // clave solo es una comodidad, así que un fallo equivale a no tenerla.
  try { ind.clave = sessionStorage.getItem(CLAVE_SESION) || ''; } catch (e) {}
  function recordarClave(valor) {
    try {
      if (valor) sessionStorage.setItem(CLAVE_SESION, valor);
      else sessionStorage.removeItem(CLAVE_SESION);
    } catch (e) {}
  }
  const fmtInd = new Intl.NumberFormat('es', {maximumFractionDigits: 2});
  const fmtNum = x => x === null ? '—' : fmtInd.format(x);

  /** Lee el libro en vivo una vez. Si tarda más de 8 s, se queda la copia. */
  function pedirEnVivo() {
    const url = DATA.indicadores.url_script;
    if (ind.pedido || !url) return;
    ind.pedido = true;
    ind.leyendo = true;
    const corte = new AbortController();
    const reloj = setTimeout(() => corte.abort(), 8000);
    fetch(url, {signal: corte.signal})
      .then(r => r.json())
      .then(r => {
        if (!r.ok) throw new Error(r.error);
        ind.datos = {...ind.datos, valores: r.valores, metas: r.metas,
                     control: r.control};
        ind.vivo = true;
      })
      .catch(() => {})  // se queda la copia; la nota lo dice
      .finally(() => {
        clearTimeout(reloj);
        ind.leyendo = false;
        // Con la cuadrícula abierta no se repinta: se perdería el foco de lo
        // que se está escribiendo. Si el año cambió, el guardado lo detecta.
        if (estado.vista === 'indicadores' && !ind.borrador) render();
      });
  }

  function notaFuente() {
    const b = DATA.indicadores;
    if (ind.vivo) return 'Datos en vivo del libro de indicadores.';
    const copia = b.ok ? 'Copia de las ' + b.generado
                       : 'Sin copia del build (' + b.error + ')';
    return copia + (ind.leyendo ? ' · leyendo en vivo…'
                    : b.url_script ? ' · no se pudo leer en vivo.' : '.');
  }

  function guardar() {
    const r = indicadoresMod.validarBorrador(ind.borrador);
    ind.errores = r.errores;
    if (r.errores.length) {
      ind.mensaje = {tipo: 'error', texto: r.errores.length +
        ' celda(s) no son un número mayor o igual que 0. No se guardó nada.'};
      render();
      return;
    }
    if (!ind.clave) {
      ind.mensaje = {tipo: 'error', texto: 'Escribe la clave para guardar.'};
      render();
      return;
    }
    const anio = ind.borrador.anio;
    ind.guardando = true;
    ind.mensaje = null;
    render();
    fetch(DATA.indicadores.url_script, {
      method: 'POST',
      // text/plain evita el preflight de CORS, que Apps Script no responde.
      headers: {'Content-Type': 'text/plain;charset=utf-8'},
      body: JSON.stringify({clave: ind.clave, anio,
                            actualizado: ind.datos.control[anio] || '',
                            valores: r.valores, metas: r.metas}),
    })
      .then(res => res.json())
      .then(res => {
        if (!res.ok) {
          if (res.error === 'Clave incorrecta') { ind.clave = ''; recordarClave(''); }
          throw new Error(res.error);
        }
        recordarClave(ind.clave);
        ind.datos = indicadoresMod.reemplazarAnio(
          ind.datos, anio, res.valores, res.metas, res.actualizado);
        ind.borrador = null;
        ind.mensaje = {tipo: 'ok', texto: 'Guardado.'};
      })
      // El borrador se conserva: nadie pierde lo escrito por un fallo.
      .catch(err => { ind.mensaje = {tipo: 'error', texto: 'No se guardó: ' + err.message}; })
      .finally(() => { ind.guardando = false; render(); });
  }

  function boton(texto, alPulsar, deshabilitado) {
    const b = document.createElement('button');
    b.className = 'chip';
    b.type = 'button';
    b.textContent = texto;
    b.disabled = !!deshabilitado;
    b.addEventListener('click', alPulsar);
    return b;
  }

  function celdaTexto(etiqueta, texto, clase) {
    const el = document.createElement(etiqueta);
    el.textContent = texto;
    if (clase) el.className = clase;
    return el;
  }

  /** Celda de la vista: T grande y N/D debajo, coloreada frente a la meta. */
  function celdaMes(c, futuro) {
    const td = document.createElement('td');
    td.className = 'num' + (c.estado ? ' ind-' + c.estado : '') + (futuro ? ' ind-futuro' : '');
    td.append(celdaTexto('div', fmtNum(c.t), 'ind-t'));
    if (c.n !== null || c.d !== null) {
      td.append(celdaTexto('div', fmtNum(c.n) + ' / ' + fmtNum(c.d), 'ind-nd'));
    }
    return td;
  }

  function entrada(valor, conError, alEscribir, etiqueta) {
    const input = document.createElement('input');
    input.type = 'text';
    input.inputMode = 'decimal';
    input.value = valor;
    input.placeholder = etiqueta;
    input.setAttribute('aria-label', etiqueta);
    if (conError) input.classList.add('ind-error');
    input.addEventListener('input', () => {
      alEscribir(input.value);
      input.classList.toggle('ind-error', !indicadoresMod.validar(input.value).ok);
    });
    return input;
  }

  /** Celda del editor: N y D, y la T que resulta mientras se escribe. */
  function celdaEditor(id, k, mes) {
    const td = document.createElement('td');
    const celda = ind.borrador.valores[id][mes - 1];
    const conError = campo => ind.errores.some(e =>
      e.indicador === id && e.mes === mes && e.campo === campo);
    const t = celdaTexto('div', '', 'ind-nd');
    const recalcular = () => {
      const n = indicadoresMod.validar(celda.n);
      const d = indicadoresMod.validar(celda.d);
      t.textContent = n.ok && d.ok
        ? 'T ' + fmtNum(indicadoresMod.tasa(n.valor, d.valor, k)) : 'T —';
    };
    td.append(
      entrada(celda.n, conError('n'), v => { celda.n = v; recalcular(); }, 'N'),
      entrada(celda.d, conError('d'), v => { celda.d = v; recalcular(); }, 'D'),
      t);
    recalcular();
    return td;
  }

  function renderIndicadores() {
    const b = DATA.indicadores;
    pedirEnVivo();
    if (!b.ok && !b.url_script) {
      contenedor.appendChild(vacio('Indicadores no disponibles: ' + b.error));
      return;
    }
    const editando = ind.borrador !== null;
    const tarjeta = card('Indicadores institucionales de PCI',
      'T = N / D · k. Con meta, en rojo los meses que la superan y en verde ' +
      'los que no. La meta es un tope.');
    tarjeta.appendChild(celdaTexto('div', notaFuente(), 'sub'));

    const barraInd = document.createElement('div');
    barraInd.className = 'ind-barra';
    if (!editando) {
      const selector = document.createElement('select');
      selector.setAttribute('aria-label', 'Año');
      indicadoresMod.anios(ind.datos, new Date().getFullYear()).forEach(a => {
        const o = document.createElement('option');
        o.value = a;
        o.textContent = a;
        o.selected = a === ind.anio;
        selector.appendChild(o);
      });
      selector.addEventListener('change', () => { ind.anio = Number(selector.value); render(); });
      barraInd.appendChild(selector);
      if (b.url_script) {
        barraInd.appendChild(boton('Editar', () => {
          ind.borrador = indicadoresMod.borradorDeAnio(ind.datos, ind.anio);
          ind.errores = [];
          ind.mensaje = null;
          render();
        }));
      }
    } else {
      barraInd.appendChild(celdaTexto('strong', 'Editando ' + ind.borrador.anio));
      const clave = document.createElement('input');
      clave.type = 'password';
      clave.placeholder = 'Clave';
      clave.setAttribute('aria-label', 'Clave');
      clave.autocomplete = 'current-password';
      clave.value = ind.clave;
      clave.addEventListener('input', () => { ind.clave = clave.value; });
      barraInd.append(
        clave,
        boton(ind.guardando ? 'Guardando…' : 'Guardar', guardar, ind.guardando),
        boton('Cancelar', () => {
          ind.borrador = null;
          ind.errores = [];
          ind.mensaje = null;
          render();
        }, ind.guardando));
    }
    if (ind.mensaje) {
      barraInd.appendChild(celdaTexto('span', ind.mensaje.texto,
                                      'ind-mensaje ' + ind.mensaje.tipo));
    }
    tarjeta.appendChild(barraInd);

    const anio = editando ? ind.borrador.anio : ind.anio;
    const hoy = new Date();
    const mesFuturo = mes => anio > hoy.getFullYear() ||
      (anio === hoy.getFullYear() && mes > hoy.getMonth() + 1);

    const tabla = document.createElement('table');
    const cabeza = document.createElement('tr');
    cabeza.append(celdaTexto('th', 'Indicador'), celdaTexto('th', 'Meta', 'num'));
    indicadoresMod.MESES.forEach(m => cabeza.append(celdaTexto('th', m, 'num')));
    tabla.appendChild(document.createElement('thead')).appendChild(cabeza);
    const cuerpo = tabla.appendChild(document.createElement('tbody'));

    for (const fila of indicadoresMod.tablaAnio(ind.datos, anio)) {
      const id = fila.indicador.id;
      const tr = document.createElement('tr');
      const nombre = celdaTexto('td', fila.indicador.nombre, 'ind-nombre');
      nombre.title = 'N: ' + fila.indicador.numerador + '\nD: ' +
        fila.indicador.denominador + '\nk = ' + fila.indicador.k;
      nombre.appendChild(celdaTexto('div', '×' + fila.indicador.k, 'ind-nd'));
      tr.appendChild(nombre);
      if (editando) {
        const tdMeta = document.createElement('td');
        tdMeta.appendChild(entrada(ind.borrador.metas[id],
          ind.errores.some(e => e.indicador === id && e.campo === 'meta'),
          v => { ind.borrador.metas[id] = v; }, 'Meta'));
        tr.appendChild(tdMeta);
        for (let mes = 1; mes <= 12; mes++) {
          tr.appendChild(celdaEditor(id, fila.indicador.k, mes));
        }
      } else {
        tr.appendChild(celdaTexto('td', fmtNum(fila.meta), 'num'));
        fila.meses.forEach((c, i) => tr.appendChild(celdaMes(c, mesFuturo(i + 1))));
      }
      cuerpo.appendChild(tr);
    }
    const zona = document.createElement('div');
    zona.className = 'ind-tabla';
    zona.appendChild(tabla);
    tarjeta.appendChild(zona);
    contenedor.appendChild(tarjeta);
  }
```

- [ ] **Step 6: Correr toda la suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Verificación manual en el navegador**

Construir un dashboard local con datos de prueba (no toca el Sheet; `dashboard.html` está en `.gitignore`):

```bash
python - <<'EOF'
from pathlib import Path
import build_dashboard as bd
import indicadores
reg, forms = bd.load(Path("SupPCI.xlsx"))
bloque = {**indicadores.bloque_fallido("x"), "ok": True,
          "url_script": "https://example.invalid/exec",
          "valores": [{"anio": 2026, "mes": 8, "indicador": "incidencia_iaas", "n": 12, "d": 11099},
                      {"anio": 2026, "mes": 9, "indicador": "incidencia_iaas", "n": 17, "d": 1395}],
          "metas": [{"anio": 2026, "indicador": "incidencia_iaas", "meta": 1}],
          "control": {}, "generado": "2026-10-16 12:00 UTC"}
data = bd.encode(bd.clean(reg, forms, bd.cargar_nombres()), forms, institucionales=bloque)
bd.render_html(data, Path("template.html"), Path("vendor/chart.umd.min.js"), Path("dashboard.html"))
EOF
```

Abrir `dashboard.html`, pestaña «Indicadores», y comprobar:
- La barra de filtros no aparece; al volver a «Global» reaparece.
- Agosto de Incidencia de IAAS en verde (0.11 ≤ 1), septiembre en rojo (1.22 > 1); N/D debajo; noviembre y diciembre atenuados.
- La nota pasa de «leyendo en vivo…» a «no se pudo leer en vivo.» (la URL es inválida a propósito).
- Editar: escribir `-3` en una N la marca en rojo al momento; T se recalcula al escribir `1,5`.
- Guardar sin clave → «Escribe la clave para guardar.»; con clave → «No se guardó: …» y **lo escrito sigue en la cuadrícula** (Review Focus: conflicto/fallo conserva el borrador).
- Cancelar vuelve a la vista sin cambios.
- Cambiar el tema: los colores se leen en claro y oscuro.

- [ ] **Step 8: Commit**

```bash
git add template.html
git commit -m "feat: pestaña de indicadores con edición y guardado"
```

---

### Task 6: importación de la Hoja1

**Files:**
- Create: `scripts/importar_indicadores.py`
- Test: `tests/test_importar_indicadores.py`

**Interfaces:**
- Consumes: `indicadores.IDS`, `indicadores.HOJAS` (Task 1).
- Produces: `FILAS: dict[str, str]`, `leer(ruta, anio) -> (valores, metas, avisos)` donde `valores` = filas dict con claves de `HOJAS["VALORES"]`, `metas` = filas dict con claves de `HOJAS["METAS"]`; `escribir(valores, metas, destino: Path) -> None`; `main(argv=None) -> int`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_importar_indicadores.py`:

```python
"""Pruebas de la importación única de la Hoja1 del Excel de indicadores."""

import csv

import openpyxl
import pytest

import indicadores
from scripts import importar_indicadores as imp


def excel(tmp_path):
    """La forma de la Hoja1 real: meses en la fila 1 cada tres columnas, N/D/T
    en la fila 2, un indicador por fila desde la 3 y la meta en la columna W."""
    libro = openpyxl.Workbook()
    h = libro.active
    h.title = "Hoja1"
    h["A1"], h["B1"], h["E1"], h["W1"] = "KPI", "Junio", "Julio", "Meta "
    for col, letra in zip("BCDEFG", "NDTNDT"):
        h[f"{col}2"] = letra
    h["A3"], h["D3"], h["E3"], h["G3"], h["W3"] = "Incidencia de IAAS", 1.6, 10, 1.5, 15
    h["A4"], h["E4"], h["F4"], h["G4"] = ("Densidad de Incidencia de IAAS", 12,
                                          9939, "=E4/F4*1000")
    ruta = tmp_path / "ind.xlsx"
    libro.save(ruta)
    return ruta


def test_las_filas_de_la_hoja1_apuntan_a_ids_del_manifiesto():
    assert set(imp.FILAS.values()) <= set(indicadores.IDS)
    assert len(imp.FILAS) == 9


def test_leer_importa_n_y_d_y_la_meta(tmp_path):
    valores, metas, _ = imp.leer(excel(tmp_path), 2026)
    assert valores == [
        {"ANIO": 2026, "MES": 7, "INDICADOR": "incidencia_iaas",
         "NUMERADOR": 10, "DENOMINADOR": ""},
        {"ANIO": 2026, "MES": 7, "INDICADOR": "densidad_iaas",
         "NUMERADOR": 12, "DENOMINADOR": 9939},
    ]
    assert metas == [{"ANIO": 2026, "INDICADOR": "incidencia_iaas", "META": 15}]


def test_leer_avisa_de_las_t_sin_n_o_d(tmp_path):
    _, _, avisos = imp.leer(excel(tmp_path), 2026)
    assert any("incidencia_iaas" in a and "mes 6" in a for a in avisos)
    assert any("incidencia_iaas" in a and "mes 7" in a for a in avisos)
    assert not any("densidad_iaas" in a for a in avisos)


def test_leer_falla_con_una_fila_desconocida(tmp_path):
    ruta = excel(tmp_path)
    libro = openpyxl.load_workbook(ruta)
    libro["Hoja1"]["A5"] = "Indicador inventado"
    libro.save(ruta)
    with pytest.raises(SystemExit, match="Indicador inventado"):
        imp.leer(ruta, 2026)


def test_escribir_deja_un_csv_por_pestana_con_sus_cabeceras(tmp_path):
    valores, metas, _ = imp.leer(excel(tmp_path), 2026)
    imp.escribir(valores, metas, tmp_path)
    with open(tmp_path / "VALORES.csv", encoding="utf-8") as f:
        filas = list(csv.reader(f))
    assert filas[0] == indicadores.HOJAS["VALORES"]
    assert len(filas) == 3
    with open(tmp_path / "METAS.csv", encoding="utf-8") as f:
        assert next(csv.reader(f)) == indicadores.HOJAS["METAS"]
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python -m pytest tests/test_importar_indicadores.py -q`
Expected: FAIL con `ModuleNotFoundError` / `ImportError` sobre `scripts.importar_indicadores`

- [ ] **Step 3: Escribir `scripts/importar_indicadores.py`**

```python
"""Importación de una sola vez: de la Hoja1 del Excel a los CSV del libro.

Uso:
    python scripts/importar_indicadores.py "INDICADOR INSTITUCIONAL.xlsx" salida/ --anio 2026

Escribe `salida/VALORES.csv` y `salida/METAS.csv`, listos para pegar en las
pestañas del libro de indicadores. Solo se importan N y D: T se recalcula
siempre. Los meses de la Hoja1 con T escrita a mano pero sin N o sin D se
avisan por la salida de error, para cargarlos después desde la página.
"""

import argparse
import csv
import sys
import unicodedata
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import indicadores  # noqa: E402

# Etiqueta de la Hoja1 (normalizada) → id del manifiesto. La Hoja1 no usa los
# mismos nombres que la hoja de definiciones, así que no se puede derivar.
FILAS = {
    "incidencia de iaas": "incidencia_iaas",
    "densidad de incidencia de iaas": "densidad_iaas",
    "bacteriemia asociada a cateter venoso central": "bacvc",
    "bacteriemia asociada a hemodialisis": "bacteriemia_hd",
    "peritonitis asociada a dialisis peritoneal": "peritonitis_dp",
    "neumonia asociada a ventilacion mecanica": "navm",
    "infeccion del tracto urinario asociada a cateter urinario": "ituacu",
    "infeccion del sitio quirurgico": "isq",
    "colitis pseudomembranosa por c. difficile": "colitis_cdiff",
}

MESES = {m: i + 1 for i, m in enumerate([
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre"])}


def normalizar(texto):
    sin_acentos = unicodedata.normalize("NFKD", str(texto or ""))
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def _numero(valor):
    """N o D de una celda. Las fórmulas (T) no pasan por aquí."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return int(valor) if float(valor).is_integer() else valor
    return float(str(valor).replace(",", "."))


def leer(ruta, anio):
    hoja = openpyxl.load_workbook(ruta)["Hoja1"]
    cabecera = [normalizar(c.value) for c in hoja[1]]
    # Índice de la columna N de cada mes; D y T son las dos siguientes.
    columnas_mes = {i: MESES[t] for i, t in enumerate(cabecera) if t in MESES}
    col_meta = next((i for i, t in enumerate(cabecera) if t == "meta"), None)

    valores, metas, avisos = [], [], []
    for fila in hoja.iter_rows(min_row=3, values_only=True):
        etiqueta = normalizar(fila[0])
        if not etiqueta:
            continue
        if etiqueta not in FILAS:
            raise SystemExit(f"Fila desconocida en la Hoja1: {fila[0]!r}")
        ind = FILAS[etiqueta]
        for i, mes in sorted(columnas_mes.items()):
            n, d = _numero(fila[i]), _numero(fila[i + 1])
            t = fila[i + 2]
            if t is not None and (n is None or d is None):
                avisos.append(f"{ind}, mes {mes}: la Hoja1 trae T ({t}) sin N "
                              "o sin D; esa T no se importa.")
            if n is None and d is None:
                continue
            valores.append({"ANIO": anio, "MES": mes, "INDICADOR": ind,
                            "NUMERADOR": "" if n is None else n,
                            "DENOMINADOR": "" if d is None else d})
        if col_meta is not None and _numero(fila[col_meta]) is not None:
            metas.append({"ANIO": anio, "INDICADOR": ind,
                          "META": _numero(fila[col_meta])})
    valores.sort(key=lambda v: (v["MES"], indicadores.IDS.index(v["INDICADOR"])))
    return valores, metas, avisos


def escribir(valores, metas, destino):
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, filas in (("VALORES", valores), ("METAS", metas)):
        with open(destino / f"{nombre}.csv", "w", newline="", encoding="utf-8") as f:
            escritor = csv.DictWriter(f, fieldnames=indicadores.HOJAS[nombre])
            escritor.writeheader()
            escritor.writerows(filas)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("excel")
    p.add_argument("destino")
    p.add_argument("--anio", type=int, default=2026)
    args = p.parse_args(argv)
    valores, metas, avisos = leer(args.excel, args.anio)
    escribir(valores, metas, args.destino)
    for aviso in avisos:
        print(f"AVISO: {aviso}", file=sys.stderr)
    print(f"{len(valores)} valores y {len(metas)} metas escritos en {args.destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python -m pytest tests/test_importar_indicadores.py -q`
Expected: PASS

- [ ] **Step 5: Probar con el Excel real**

Run: `python scripts/importar_indicadores.py "C:/Users/Salvador/Downloads/INDICADOR INSTITUCIONAL.xlsx" "$TEMP/indicadores-csv" --anio 2026`
Expected: `19 valores y 1 metas` (agosto y septiembre de los 9 indicadores de la Hoja1, más julio de `incidencia_iaas` con N = 10 y sin D), y AVISO para junio y julio de `incidencia_iaas`. Revisar `VALORES.csv` a ojo contra la Hoja1.

- [ ] **Step 6: Commit**

```bash
git add scripts/importar_indicadores.py tests/test_importar_indicadores.py
git commit -m "feat: importación única de la Hoja1 de indicadores"
```

---

### Task 7: README y puesta en marcha

**Files:**
- Modify: `README.md` (nueva sección después de la de vigilancia de IAAS)

- [ ] **Step 1: Añadir la sección**

```markdown
## Indicadores institucionales

La pestaña "Indicadores" muestra los 10 indicadores institucionales de PCI por
mes (T = N / D · k) frente a su meta, y es la única del dashboard que se puede
editar. Los números viven en un Google Sheet propio; las definiciones, en
`indicadores.py`.

- **Ver**: cualquiera. La página lee el libro en vivo a través del Apps Script
  y, si no responde en 8 segundos, muestra la copia del último build.
- **Editar**: botón "Editar", cuadrícula de N, D y meta, y la clave del equipo
  para guardar. Si otra persona guardó el mismo año mientras tanto, el guardado
  se rechaza y hay que recargar; lo escrito no se pierde.

### Puesta en marcha (una vez)

1. Crear un Google Sheet con tres pestañas y estas cabeceras en la fila 1:
   - `VALORES`: `ANIO`, `MES`, `INDICADOR`, `NUMERADOR`, `DENOMINADOR`
   - `METAS`: `ANIO`, `INDICADOR`, `META`
   - `CONTROL`: `ANIO`, `ACTUALIZADO`

   Compartirlo como "cualquiera con el enlace puede ver".
2. En el Sheet, Extensiones → Apps Script: pegar `apps_script/indicadores.gs`.
   En Configuración del proyecto → Propiedades del script, crear `CLAVE` con la
   clave del equipo. Implementar → Nueva implementación → Aplicación web,
   "Ejecutar como: yo", "Quién tiene acceso: cualquier usuario". Copiar la URL
   que termina en `/exec`.
3. En `indicadores.py`, poner el id del Sheet en `ID_LIBRO` y la URL en
   `URL_SCRIPT`. Commit y push.
4. Importar lo que ya había en el Excel:
   `python scripts/importar_indicadores.py "INDICADOR INSTITUCIONAL.xlsx" salida/ --anio 2026`
   y pegar `salida/VALORES.csv` y `salida/METAS.csv` en sus pestañas (debajo
   de la cabecera).
5. Prueba manual: abrir la pestaña (la nota debe decir "en vivo"); guardar un
   cambio con la clave buena (se ve en el Sheet); con una clave mala (no
   escribe); abrir dos pestañas del navegador, guardar en una y luego en la
   otra (la segunda recibe el aviso de conflicto); escribir `-1` (no deja
   guardar).

Si se cambia `indicadores.gs`, hay que volver a implementarlo (Implementar →
Gestionar implementaciones → editar → versión nueva) para que la URL sirva el
código nuevo.
```

- [ ] **Step 2: Correr toda la suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: pestaña de indicadores y su puesta en marcha"
```
