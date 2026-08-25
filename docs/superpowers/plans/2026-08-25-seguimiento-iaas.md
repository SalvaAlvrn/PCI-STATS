# Seguimiento al cumplimiento de la investigación de casos de IAAS — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir al dashboard una pestaña "Investigación de IAAS" alimentada desde la API de KoboToolbox, con cumplimiento y producción, sin publicar un solo dato de paciente.

**Architecture:** Un módulo `kobo.py` independiente hace su propio load/validate/clean/encode y devuelve el bloque `DATA.iaas`; `build_dashboard.py` lo llama desde un único punto de `main()`, dentro de un `try/except` que, si Kobo falla, publica igual con el motivo escrito en la pestaña. En el navegador, `agg` pasa a ser la fábrica `crearAgg(dataset)` para que la vista nueva reutilice la agregación existente en lugar de duplicarla.

**Tech Stack:** Python 3.12, pandas 3.0.3, requests 2.34.0, pytest 9.1.1; JavaScript sin dependencias salvo Chart.js 4.4.1 vendorizado.

**Spec:** `docs/superpowers/specs/2026-08-25-seguimiento-iaas-design.md`

## Global Constraints

- **Lista blanca, nunca lista negra.** Solo `Fecha de registro`, `Responsable de investigación`, `Servicio al que pertenece la investigación`, `Producción Reportada/*` y los 24 ítems SI/NO llegan al HTML. Todo lo demás se descarta en `kobo.py` antes de calcular nada.
- **Nunca al HTML:** `Nombre del paciente`, `Expediente`, `CONCLUSIONES`, `Responsable de reporte`, `_uuid`, `meta/rootUuid`, `_id`, `_notes`, `_tags`, `_submitted_by`, `start`, `end`.
- **Ningún fallo de Kobo aborta el build.** Red, HTTP, timeout, token ausente o cambio de forma producen `DATA.iaas = {"error": "<motivo>", "fecha": "<intento>"}`, un aviso en stderr y una anotación `::warning` en el workflow.
- **Ninguna prueba toca la red.** `requests.get` se mockea siempre.
- `KOBO_SERVIDOR = "kf.kobotoolbox.org"`, `KOBO_ASSET_UID = "aefXsYwJo5RsrZYfaCEcva"`, timeout 60 s.
- El token sale solo de la variable de entorno `KOBO_TOKEN`. Nunca de un archivo del árbol de trabajo, nunca en un mensaje de error, nunca en un `print`.
- Tasa de cumplimiento ponderada por volumen: `Σ SI / Σ (SI+NO)`. Ítem sin responder = no aplica, fuera del denominador.
- Los mensajes de error se escriben en español, como el resto del proyecto. El código y los commits, en inglés.

## Desviación del spec, decidida al planificar

El spec pedía un KPI "pacientes distintos" en la fila de KPIs. Un KPI reactivo a los filtros exigiría publicar un identificador de paciente por fila —aunque fuera un número opaco— y eso permite encadenar fecha + servicio + responsable para reidentificar a alguien en un hospital pequeño. En su lugar: `meta.pacientes` es un único número global, calculado en Python, y se muestra como nota fija bajo los KPIs ("Sobre el periodo completo: 75 pacientes distintos"), no como KPI filtrable. El HTML no lleva ninguna columna de paciente.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `kobo.py` (nuevo) | Manifiesto, descarga, validación de forma, lista blanca y codificación de `DATA.iaas` |
| `tests/test_kobo.py` (nuevo) | Pruebas del módulo con respuestas sintéticas de la API |
| `build_dashboard.py` | Un punto de llamada en `main()` y el `try/except` que decide publicar sin datos |
| `tests/test_build.py` | Prueba de extremo a extremo de que ningún dato personal llega al HTML |
| `template.html` | `crearAgg`, agregador de IAAS, pestaña, barra de filtros por vista y las siete tarjetas |
| `tests/test_agg.html` | Copias de los módulos bajo prueba y sus aserciones |
| `.github/workflows/publicar.yml` | Secret `KOBO_TOKEN` y anotación de aviso |
| `README.md` | El apartado nuevo, el secret y qué pasa si Kobo falla |

Nota sobre `tests/test_agg.html`: el harness **duplica a mano** el código de `mod-store` y `mod-agg` copiándolo de `template.html`. No hay ninguna prueba que verifique que las dos copias coinciden. Cada task que toque un módulo del harness debe editar **las dos copias**.

Para correr el harness sin navegador durante la implementación:

```bash
cat > /tmp/correr_agg.mjs <<'FIN'
import {readFileSync} from 'node:fs';
const html = readFileSync(process.argv[2], 'utf8');
const bloques = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m => m[1]);
let salida = [];
const nodo = () => ({className: '', set textContent(v) { salida.push(v); }, appendChild() {}});
globalThis.document = {createElement: nodo, getElementById: () => ({appendChild() {}})};
new Function(bloques.join('\n'))();
console.log(salida.join('\n'));
process.exit(salida.some(l => l.startsWith('FALLA')) ? 1 : 0);
FIN
node /tmp/correr_agg.mjs tests/test_agg.html | tail -3
```

---

### Task 1: Manifiesto y mapa etiqueta → nombre XML

El export de Kobo trae etiquetas; la API devuelve nombres XML. Esta task escribe el manifiesto (la forma que el formulario debe tener) y la función que empareja etiquetas con nombres leyendo el esquema del formulario.

**Files:**
- Create: `kobo.py`
- Test: `tests/test_kobo.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `class KoboError(Exception)`
  - `ACTIVIDADES: list[str]` — 6 etiquetas, orden fijo
  - `ITEMS: list[tuple[str, str]]` — 24 pares `(actividad, etiqueta_item)`
  - `CAMPOS: dict[str, str]` — etiquetas de fecha, responsable y servicio
  - `normalizar(texto: str) -> str`
  - `mapa_de_campos(esquema: dict) -> dict[str, str]` — etiqueta normalizada → nombre XML con su prefijo de grupo

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kobo.py
import pytest

import kobo


ESQUEMA_MINIMO = {
    "content": {
        "survey": [
            {"type": "date", "name": "Fecha_de_registro",
             "label": ["Fecha de registro"]},
            {"type": "begin_group", "name": "grupo1", "label": ["Grupo"]},
            {"type": "select_one", "name": "item_a",
             "label": ["Se realizo investigación\xa0 de un nuevo caso"]},
            {"type": "end_group"},
        ],
        "choices": [],
    }
}


def test_normalizar_colapsa_espacios_duros_y_dobles():
    assert kobo.normalizar("Se  realizó\xa0el cierre ") == "se realizó el cierre"


def test_mapa_de_campos_usa_la_etiqueta_normalizada_como_clave():
    mapa = kobo.mapa_de_campos(ESQUEMA_MINIMO)
    assert mapa["fecha de registro"] == "Fecha_de_registro"


def test_mapa_de_campos_antepone_el_grupo_al_nombre():
    mapa = kobo.mapa_de_campos(ESQUEMA_MINIMO)
    assert mapa["se realizo investigación de un nuevo caso"] == "grupo1/item_a"


def test_manifiesto_declara_seis_actividades_y_veinticuatro_items():
    assert len(kobo.ACTIVIDADES) == 6
    assert len(kobo.ITEMS) == 24
    assert {a for a, _ in kobo.ITEMS} == set(kobo.ACTIVIDADES)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_kobo.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'kobo'`

- [ ] **Step 3: Write minimal implementation**

```python
# kobo.py
"""Seguimiento al cumplimiento de la investigación de casos de IAAS.

Lee los envíos del formulario de KoboToolbox y produce el bloque `DATA.iaas`
que consume el dashboard. Vive aparte de `build_dashboard.py` a propósito: el
pipeline de supervisiones no debe cambiar de comportamiento porque esta fuente
falle o cambie de forma.
"""

import re
import unicodedata


class KoboError(Exception):
    """Kobo no respondió, o su formulario ya no tiene la forma esperada.

    No aborta el build: `build_dashboard.py` lo captura y publica el
    dashboard sin la pestaña, con el motivo a la vista.
    """


KOBO_SERVIDOR = "kf.kobotoolbox.org"
KOBO_ASSET_UID = "aefXsYwJo5RsrZYfaCEcva"
TIMEOUT_SEGUNDOS = 60

CAMPOS = {
    "fecha": "Fecha de registro",
    "responsable": "Responsable de investigación",
    "servicio": "Servicio al que pertenece la investigación",
    "actividades": "Producción Reportada",
}

# Campos que existen en el formulario y que este módulo no debe publicar
# jamás. No se usa para filtrar —el filtro es la lista blanca de `limpiar`—
# sino para que una prueba pueda comprobar que ninguno se cuela.
CAMPOS_PROHIBIDOS = [
    "Nombre del paciente",
    "Expediente",
    "CONCLUSIONES",
    "Responsable de reporte",
]

ACTIVIDADES = [
    "CASOS NUEVOS INVESTIGADOS",
    "CASOS EN SEGUIMIENTO",
    "CIERRE DE CASOS",
    "SERVICIOS VISITADOS",
    "EXPEDIENTES REVISADOS",
    "ENTREVISTAS REALIZADAS",
]

# (actividad, etiqueta del ítem). El orden manda: es el que se publica y el
# que ve quien lee la tabla de ítems.
ITEMS = [
    ("CASOS NUEVOS INVESTIGADOS", "Se realizo investigación de un nuevo caso"),
    ("CASOS NUEVOS INVESTIGADOS", "La investigación fue iniciada oportunamente"),
    ("CASOS EN SEGUIMIENTO", "Se realizó seguimiento a los casos programados para el día"),
    ("CASOS EN SEGUIMIENTO", "Se verificó la evolución clínica del paciente"),
    ("CASOS EN SEGUIMIENTO", "Se documentó la evolución del caso en el formulario de investigación"),
    ("CASOS EN SEGUIMIENTO", "Se documentó la evolución clínica y epidemiológica del caso en seguimiento"),
    ("CIERRE DE CASOS", "Se realizo cierre de caso"),
    ("CIERRE DE CASOS", "El caso cumple con los criterios establecidos para su cierre"),
    ("CIERRE DE CASOS", "Se documentó la clasificación final del caso"),
    ("CIERRE DE CASOS", "Se registró la fecha de cierre de investigación"),
    ("CIERRE DE CASOS", "El cierre fue documentado conforme a la normativa institucional"),
    ("SERVICIOS VISITADOS", "Se realizaron las visitas programadas a los servicios"),
    ("SERVICIOS VISITADOS", "Se verificó el estado clínico del paciente en el área de hospitalización"),
    ("SERVICIOS VISITADOS", "Se realizaron la visita donde se encuentra ubicado el paciente"),
    ("SERVICIOS VISITADOS", "Se evaluó el cumplimiento de las medidas de prevención y control de infecciones relacionadas con el caso"),
    ("EXPEDIENTES REVISADOS", "Se revisó el expediente clínico completo del paciente"),
    ("EXPEDIENTES REVISADOS", "Se revisaron los factores de riesgo asociados al desarrollo de IAAS"),
    ("EXPEDIENTES REVISADOS", "Se revisaron los resultados de laboratorio y cultivos microbiológicos disponibles"),
    ("EXPEDIENTES REVISADOS", "Se revisó el tratamiento antimicrobiano indicado y su evolución"),
    ("EXPEDIENTES REVISADOS", "La revisión permitió identificar factores de riesgos o hallazgos relevantes"),
    ("ENTREVISTAS REALIZADAS", "Se entrevistó al paciente o familiar respnsable"),
    ("ENTREVISTAS REALIZADAS", "Se entrevistó al personal de salud involucrado en la atención del paciente"),
    ("ENTREVISTAS REALIZADAS", "Se identificaron posibles factores contribuyentes mediante la entrevista"),
    ("ENTREVISTAS REALIZADAS", "La información obtenida contribuyó a la investigación"),
]


def normalizar(texto):
    """Etiqueta comparable: sin espacios duros, sin dobles espacios, en minúsculas.

    Kobo guarda los saltos de línea y los `\\xa0` que el autor del formulario
    pegó sin querer, y el export los conserva. Comparar etiquetas en crudo
    fallaría por diferencias que nadie ve al leerlas.
    """
    texto = unicodedata.normalize("NFKC", str(texto)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", texto).strip().lower()


def mapa_de_campos(esquema):
    """Etiqueta normalizada → nombre XML, con el prefijo de grupo incluido.

    Los envíos vienen con las preguntas de un grupo bajo `grupo/pregunta`,
    así que el nombre suelto no basta para leerlos.
    """
    survey = esquema.get("content", {}).get("survey")
    if not survey:
        raise KoboError(
            "El esquema del formulario llegó sin `content.survey`. "
            "Comprueba el asset uid."
        )
    mapa = {}
    grupos = []
    for campo in survey:
        tipo = campo.get("type")
        if tipo == "begin_group":
            grupos.append(campo.get("name", ""))
            continue
        if tipo == "end_group":
            if grupos:
                grupos.pop()
            continue
        etiquetas = campo.get("label") or []
        nombre = campo.get("name")
        if not etiquetas or not nombre:
            continue
        ruta = "/".join([*grupos, nombre])
        mapa[normalizar(etiquetas[0])] = ruta
    return mapa
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_kobo.py -v`
Expected: PASS, 4 pruebas

- [ ] **Step 5: Commit**

```bash
git add kobo.py tests/test_kobo.py
git commit -m "feat: add the Kobo form manifest and label-to-name mapping"
```

---

### Task 2: Descarga desde la API

**Files:**
- Modify: `kobo.py`
- Test: `tests/test_kobo.py`

**Interfaces:**
- Consumes: `KoboError`, `KOBO_SERVIDOR`, `KOBO_ASSET_UID`, `TIMEOUT_SEGUNDOS` (Task 1)
- Produces:
  - `descargar(token, servidor=KOBO_SERVIDOR, uid=KOBO_ASSET_UID) -> tuple[dict, list[dict]]` — devuelve `(esquema, envios)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kobo.py — añadir
from unittest.mock import patch

import requests


class RespuestaFalsa:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def test_descargar_sigue_la_paginacion_hasta_agotarla():
    pagina2 = {"results": [{"_id": 2}], "next": None}
    pagina1 = {"results": [{"_id": 1}], "next": "https://kf/api/v2/x?start=1"}
    respuestas = [RespuestaFalsa(ESQUEMA_MINIMO), RespuestaFalsa(pagina1),
                  RespuestaFalsa(pagina2)]
    with patch("kobo.requests.get", side_effect=respuestas):
        esquema, envios = kobo.descargar("t0ken")
    assert esquema == ESQUEMA_MINIMO
    assert [e["_id"] for e in envios] == [1, 2]


def test_descargar_manda_el_token_en_la_cabecera():
    llamadas = []

    def falsa(url, headers=None, timeout=None):
        llamadas.append(headers)
        return RespuestaFalsa(
            ESQUEMA_MINIMO if "data" not in url else {"results": [], "next": None}
        )

    with patch("kobo.requests.get", side_effect=falsa):
        kobo.descargar("t0ken")
    assert llamadas[0]["Authorization"] == "Token t0ken"


def test_descargar_sin_token_levanta_koboerror():
    with pytest.raises(kobo.KoboError, match="KOBO_TOKEN"):
        kobo.descargar("")


def test_descargar_con_401_explica_que_es_el_token():
    with patch("kobo.requests.get", return_value=RespuestaFalsa({}, 401)):
        with pytest.raises(kobo.KoboError, match="401"):
            kobo.descargar("malo")


def test_descargar_no_repite_el_token_en_el_mensaje_de_error():
    with patch("kobo.requests.get", return_value=RespuestaFalsa({}, 401)):
        with pytest.raises(kobo.KoboError) as error:
            kobo.descargar("secreto-de-verdad")
    assert "secreto-de-verdad" not in str(error.value)


def test_descargar_convierte_el_fallo_de_red_en_koboerror():
    with patch("kobo.requests.get",
               side_effect=requests.RequestException("sin ruta al host")):
        with pytest.raises(kobo.KoboError, match="sin ruta al host"):
            kobo.descargar("t0ken")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_kobo.py -v`
Expected: FAIL con `AttributeError: module 'kobo' has no attribute 'descargar'`

- [ ] **Step 3: Write minimal implementation**

```python
# kobo.py — añadir el import arriba
import requests

# ...y estas funciones al final


def _pedir(url, token):
    try:
        respuesta = requests.get(
            url,
            headers={"Authorization": f"Token {token}"},
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.RequestException as error:
        raise KoboError(f"No se pudo contactar con KoboToolbox: {error}")
    if respuesta.status_code == 401:
        raise KoboError(
            "KoboToolbox respondió 401: el token de KOBO_TOKEN no es válido "
            "o ha caducado."
        )
    if respuesta.status_code != 200:
        raise KoboError(
            f"KoboToolbox respondió {respuesta.status_code} al pedir {url}."
        )
    try:
        return respuesta.json()
    except ValueError as error:
        raise KoboError(f"KoboToolbox devolvió algo que no es JSON: {error}")


def descargar(token, servidor=KOBO_SERVIDOR, uid=KOBO_ASSET_UID):
    """Devuelve (esquema, envíos). El token nunca aparece en los errores."""
    if not token:
        raise KoboError(
            "Falta el token de la API: define KOBO_TOKEN en el entorno "
            "(en CI, como secret del repositorio)."
        )
    base = f"https://{servidor}/api/v2/assets/{uid}"
    esquema = _pedir(f"{base}.json", token)

    envios = []
    url = f"{base}/data.json"
    # La API pagina los envíos; `next` trae la URL de la página siguiente ya
    # formada. Se sigue hasta que viene nula.
    while url:
        pagina = _pedir(url, token)
        envios.extend(pagina.get("results", []))
        url = pagina.get("next")
    return esquema, envios
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_kobo.py -v`
Expected: PASS, 10 pruebas

- [ ] **Step 5: Commit**

```bash
git add kobo.py tests/test_kobo.py
git commit -m "feat: download the Kobo schema and paginated submissions"
```

---

### Task 3: Validación de forma y lista blanca

Es la task que sostiene la promesa de privacidad. Si algo de aquí se hace mal, se publican datos de pacientes.

**Files:**
- Modify: `kobo.py`
- Test: `tests/test_kobo.py`

**Interfaces:**
- Consumes: `mapa_de_campos`, `ACTIVIDADES`, `ITEMS`, `CAMPOS`, `normalizar`, `KoboError`
- Produces:
  - `validar(esquema) -> dict[str, str]` — devuelve el mapa etiqueta→nombre ya comprobado
  - `limpiar(envios, mapa) -> tuple[list[dict], int]` — devuelve `(filas, pacientes_distintos)`; cada fila es `{"fecha": "YYYY-MM-DD", "responsable": str, "servicio": str, "actividades": [0|1]*6, "items": [1|0|None]*24}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kobo.py — añadir

def esquema_completo():
    """Esquema sintético con todas las etiquetas que el manifiesto exige."""
    survey = [
        {"type": "date", "name": "fecha", "label": [kobo.CAMPOS["fecha"]]},
        {"type": "select_one", "name": "resp",
         "label": [kobo.CAMPOS["responsable"]]},
        {"type": "select_one", "name": "serv",
         "label": [kobo.CAMPOS["servicio"]]},
        {"type": "select_multiple", "name": "prod",
         "label": [kobo.CAMPOS["actividades"]]},
        {"type": "text", "name": "paciente", "label": ["Nombre del paciente"]},
        {"type": "text", "name": "expediente", "label": ["Expediente"]},
        {"type": "text", "name": "conclusiones", "label": ["CONCLUSIONES"]},
    ]
    for i, (_, etiqueta) in enumerate(kobo.ITEMS):
        survey.append({"type": "select_one", "name": f"i{i}", "label": [etiqueta]})
    choices = [
        {"list_name": "prod", "name": f"a{i}", "label": [a]}
        for i, a in enumerate(kobo.ACTIVIDADES)
    ]
    return {"content": {"survey": survey, "choices": choices}}


def envio(**extra):
    base = {
        "fecha": "2026-07-21",
        "resp": "Ana Investigadora",
        "serv": "Nefrología",
        "prod": "a0",
        "i0": "SI",
        "i1": "NO",
        "paciente": "PACIENTE_SINTETICO_XYZ",
        "expediente": "EXP-999999",
        "conclusiones": "CONCLUSION_SINTETICA_XYZ",
        "_id": 1,
        "_uuid": "uuid-1",
    }
    base.update(extra)
    return base


def test_validar_devuelve_el_mapa_cuando_estan_todas_las_etiquetas():
    mapa = kobo.validar(esquema_completo())
    assert mapa[kobo.normalizar(kobo.CAMPOS["fecha"])] == "fecha"


def test_validar_nombra_la_etiqueta_que_falta():
    esquema = esquema_completo()
    esquema["content"]["survey"] = [
        c for c in esquema["content"]["survey"]
        if c["label"][0] != kobo.ITEMS[3][1]
    ]
    with pytest.raises(kobo.KoboError, match=kobo.ITEMS[3][1][:25]):
        kobo.validar(esquema)


def test_limpiar_no_conserva_ningun_campo_prohibido():
    mapa = kobo.validar(esquema_completo())
    filas, _ = kobo.limpiar([envio()], mapa)
    texto = repr(filas)
    assert "PACIENTE_SINTETICO_XYZ" not in texto
    assert "EXP-999999" not in texto
    assert "CONCLUSION_SINTETICA_XYZ" not in texto
    assert "uuid-1" not in texto
    assert set(filas[0]) == {"fecha", "responsable", "servicio",
                             "actividades", "items"}


def test_limpiar_marca_solo_las_actividades_declaradas():
    mapa = kobo.validar(esquema_completo())
    filas, _ = kobo.limpiar([envio(prod="a0 a2")], mapa)
    assert filas[0]["actividades"] == [1, 0, 1, 0, 0, 0]


def test_limpiar_deja_en_none_los_items_sin_responder():
    mapa = kobo.validar(esquema_completo())
    filas, _ = kobo.limpiar([envio()], mapa)
    assert filas[0]["items"][0] == 1
    assert filas[0]["items"][1] == 0
    assert filas[0]["items"][2] is None


def test_limpiar_cuenta_pacientes_distintos_sin_publicarlos():
    mapa = kobo.validar(esquema_completo())
    envios = [envio(expediente="A"), envio(expediente="A"), envio(expediente="B")]
    filas, pacientes = kobo.limpiar(envios, mapa)
    assert pacientes == 2
    assert "A" not in repr(filas)


def test_limpiar_rechaza_un_valor_desconocido_en_un_item():
    mapa = kobo.validar(esquema_completo())
    with pytest.raises(kobo.KoboError, match="QUIZÁS"):
        kobo.limpiar([envio(i0="QUIZÁS")], mapa)


def test_limpiar_rechaza_una_fecha_ilegible():
    mapa = kobo.validar(esquema_completo())
    with pytest.raises(kobo.KoboError, match="ayer"):
        kobo.limpiar([envio(fecha="ayer")], mapa)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_kobo.py -v`
Expected: FAIL con `AttributeError: module 'kobo' has no attribute 'validar'`

- [ ] **Step 3: Write minimal implementation**

```python
# kobo.py — añadir

VALORES_ITEM = {"SI": 1, "SÍ": 1, "NO": 0}


def validar(esquema):
    """Comprueba que el formulario tiene la forma del manifiesto.

    Devuelve el mapa etiqueta→nombre para que quien valida y quien limpia no
    puedan usar mapas distintos.
    """
    mapa = mapa_de_campos(esquema)
    esperadas = [*CAMPOS.values(), *(etiqueta for _, etiqueta in ITEMS)]
    faltan = [e for e in esperadas if normalizar(e) not in mapa]
    if faltan:
        raise KoboError(
            "El formulario de Kobo ya no tiene la forma esperada. No se "
            f"encontraron estas preguntas: {faltan}. Si las renombraste en "
            "Kobo, actualiza el manifiesto de kobo.py."
        )
    faltan_actividades = [
        a for a in ACTIVIDADES if normalizar(a) not in _choices_de_actividad(esquema)
    ]
    if faltan_actividades:
        raise KoboError(
            "Faltan opciones de «Producción Reportada» en el formulario: "
            f"{faltan_actividades}."
        )
    return mapa


def _choices_de_actividad(esquema):
    """Etiqueta normalizada → nombre de opción, para «Producción Reportada»."""
    salida = {}
    for opcion in esquema.get("content", {}).get("choices", []):
        etiquetas = opcion.get("label") or []
        if etiquetas and opcion.get("name"):
            salida[normalizar(etiquetas[0])] = opcion["name"]
    return salida


def limpiar(envios, mapa, choices=None):
    """Aplica la lista blanca. Devuelve (filas, pacientes distintos).

    Lo que no está en la lista blanca no se copia: un campo nuevo en Kobo no
    se publica por descuido, que es el comportamiento que queremos por
    defecto en una página pública.
    """
    choices = choices or {}
    nombre_actividad = [choices.get(normalizar(a), a) for a in ACTIVIDADES]
    campo = {clave: mapa[normalizar(etiqueta)] for clave, etiqueta in CAMPOS.items()}
    campos_item = [mapa[normalizar(etiqueta)] for _, etiqueta in ITEMS]

    filas = []
    expedientes = set()
    for envio in envios:
        crudo = str(envio.get(campo["fecha"], "")).strip()
        fecha = crudo[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
            raise KoboError(
                f"Un envío trae una fecha de registro ilegible: {crudo!r}."
            )
        declaradas = str(envio.get(campo["actividades"], "")).split()
        items = []
        for nombre in campos_item:
            valor = envio.get(nombre)
            if valor in (None, ""):
                items.append(None)
                continue
            texto = str(valor).strip().upper()
            if texto not in VALORES_ITEM:
                raise KoboError(
                    f"Un ítem trae un valor no soportado: {texto!r}. Solo se "
                    "interpretan SI y NO."
                )
            items.append(VALORES_ITEM[texto])
        filas.append({
            "fecha": fecha,
            "responsable": str(envio.get(campo["responsable"], "")).strip(),
            "servicio": str(envio.get(campo["servicio"], "")).strip(),
            "actividades": [1 if n in declaradas else 0 for n in nombre_actividad],
            "items": items,
        })
        # El expediente se lee para contar personas distintas y se descarta
        # con el envío: no entra en `filas` ni, por tanto, en el HTML. El
        # nombre del campo sale del mapa, no de una cadena adivinada.
        campo_exp = mapa.get(normalizar("Expediente"))
        expediente = str(envio.get(campo_exp, "")).strip() if campo_exp else ""
        if expediente:
            expedientes.add(expediente)
    return filas, len(expedientes)
```

Nota para quien implementa: sin `choices`, el nombre de la opción cae de vuelta a la etiqueta (`"CASOS NUEVOS INVESTIGADOS"`), y el envío sintético usa el nombre de opción `"a0"`. Las pruebas que comprueban actividades declaradas deben llamar así:

```python
esquema = esquema_completo()
mapa = kobo.validar(esquema)
filas, _ = kobo.limpiar([envio(prod="a0 a2")], mapa,
                        choices=kobo._choices_de_actividad(esquema))
```

Escribe esas llamadas con `choices` desde el principio: las de arriba están abreviadas.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_kobo.py -v`
Expected: PASS, 18 pruebas

- [ ] **Step 5: Commit**

```bash
git add kobo.py tests/test_kobo.py
git commit -m "feat: validate the Kobo form shape and apply the field allowlist"
```

---

### Task 4: Codificación de `DATA.iaas`

**Files:**
- Modify: `kobo.py`
- Test: `tests/test_kobo.py`

**Interfaces:**
- Consumes: `descargar`, `validar`, `limpiar`
- Produces:
  - `construir(token, servidor=KOBO_SERVIDOR, uid=KOBO_ASSET_UID) -> dict` — el bloque `DATA.iaas` completo

Forma exacta del bloque, que la Task 7 consume:

```json
{
  "ok": true,
  "dims": {"responsable": [...], "servicio": [...], "mes": [...], "semana": [...]},
  "actividades": ["CASOS NUEVOS INVESTIGADOS", "..."],
  "items": [{"titulo": "...", "actividad": 0}, "..."],
  "rows": {
    "dia": [20655, ...],
    "responsable": [0, ...], "servicio": [2, ...],
    "mes": [0, ...], "semana": [1, ...],
    "actividades": [[1, 0, ...], ...],
    "items": [[1, null, ...], ...],
    "si": [3, ...], "no": [1, ...]
  },
  "meta": {"generado": "...", "filas": 155, "pacientes": 75,
           "dia_min": 20635, "dia_max": 20690}
}
```

`rows.actividades[a][i]` y `rows.items[j][i]` son columnas paralelas: el índice exterior es la actividad o el ítem, el interior el envío. Es el mismo esquema que `DATA.rows` para supervisiones.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kobo.py — añadir

def test_construir_devuelve_columnas_paralelas_por_item():
    with patch("kobo.descargar",
               return_value=(esquema_completo(), [envio(), envio(i0="NO")])):
        data = kobo.construir("t0ken")
    assert data["ok"] is True
    assert len(data["rows"]["items"]) == 24
    assert data["rows"]["items"][0] == [1, 0]


def test_construir_cuenta_si_y_no_por_envio():
    with patch("kobo.descargar", return_value=(esquema_completo(), [envio()])):
        data = kobo.construir("t0ken")
    # El envío sintético responde i0=SI e i1=NO; el resto queda sin responder.
    assert data["rows"]["si"] == [1]
    assert data["rows"]["no"] == [1]


def test_construir_ordena_las_dimensiones_alfabeticamente():
    envios = [envio(resp="Zulema"), envio(resp="Ana")]
    with patch("kobo.descargar", return_value=(esquema_completo(), envios)):
        data = kobo.construir("t0ken")
    assert data["dims"]["responsable"] == ["Ana", "Zulema"]
    assert data["rows"]["responsable"] == [1, 0]


def test_construir_deriva_mes_semana_y_dia():
    with patch("kobo.descargar",
               return_value=(esquema_completo(), [envio(fecha="2026-07-21")])):
        data = kobo.construir("t0ken")
    assert data["dims"]["mes"] == ["2026-07"]
    assert data["dims"]["semana"] == ["2026-W30"]
    assert data["rows"]["dia"] == [20655]


def test_construir_publica_el_recuento_de_pacientes_pero_no_los_expedientes():
    envios = [envio(expediente="EXP-1"), envio(expediente="EXP-2")]
    with patch("kobo.descargar", return_value=(esquema_completo(), envios)):
        data = kobo.construir("t0ken")
    assert data["meta"]["pacientes"] == 2
    assert "EXP-1" not in repr(data)


def test_construir_sin_envios_no_revienta():
    with patch("kobo.descargar", return_value=(esquema_completo(), [])):
        data = kobo.construir("t0ken")
    assert data["meta"]["filas"] == 0
    assert data["rows"]["items"] == [[] for _ in range(24)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_kobo.py -v`
Expected: FAIL con `AttributeError: module 'kobo' has no attribute 'construir'`

- [ ] **Step 3: Write minimal implementation**

```python
# kobo.py — añadir el import arriba
import pandas as pd

# ...y al final


def construir(token, servidor=KOBO_SERVIDOR, uid=KOBO_ASSET_UID):
    """Descarga, valida, limpia y codifica. Devuelve el bloque DATA.iaas."""
    esquema, envios = descargar(token, servidor, uid)
    mapa = validar(esquema)
    filas, pacientes = limpiar(
        envios, mapa, choices=_choices_de_actividad(esquema)
    )

    fechas = pd.to_datetime([f["fecha"] for f in filas]) if filas else pd.DatetimeIndex([])
    meses = [f"{d:%Y-%m}" for d in fechas]
    iso = [d.isocalendar() for d in fechas]
    semanas = [f"{c.year}-W{c.week:02d}" for c in iso]
    dias = [int(d.to_datetime64().astype("datetime64[D]").astype("int64"))
            for d in fechas]

    dims = {}
    rows = {}
    for clave, valores in (
        ("responsable", [f["responsable"] for f in filas]),
        ("servicio", [f["servicio"] for f in filas]),
        ("mes", meses),
        ("semana", semanas),
    ):
        # Orden alfabético para que el archivo sea determinista entre builds,
        # igual que en encode() de build_dashboard.py.
        categorias = sorted(set(valores))
        indice = {v: i for i, v in enumerate(categorias)}
        dims[clave] = categorias
        rows[clave] = [indice[v] for v in valores]

    rows["dia"] = dias
    rows["actividades"] = [
        [f["actividades"][a] for f in filas] for a in range(len(ACTIVIDADES))
    ]
    rows["items"] = [
        [f["items"][j] for f in filas] for j in range(len(ITEMS))
    ]
    rows["si"] = [sum(1 for v in f["items"] if v == 1) for f in filas]
    rows["no"] = [sum(1 for v in f["items"] if v == 0) for f in filas]

    return {
        "ok": True,
        "dims": dims,
        "actividades": list(ACTIVIDADES),
        "items": [
            {"titulo": etiqueta, "actividad": ACTIVIDADES.index(actividad)}
            for actividad, etiqueta in ITEMS
        ],
        "rows": rows,
        "meta": {
            "generado": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
            "filas": len(filas),
            "pacientes": pacientes,
            "dia_min": min(dias) if dias else 0,
            "dia_max": max(dias) if dias else 0,
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_kobo.py -v`
Expected: PASS, 24 pruebas

- [ ] **Step 5: Commit**

```bash
git add kobo.py tests/test_kobo.py
git commit -m "feat: encode the IAAS submissions into the DATA.iaas block"
```

---

### Task 5: Enganche en `build_dashboard.py`, sin abortar el build

**Files:**
- Modify: `build_dashboard.py:493-525` (la función `main`)
- Modify: `build_dashboard.py:395` (firma de `encode`)
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `kobo.construir`, `kobo.KoboError`
- Produces: `encode(df, formularios, iaas=None)` — el bloque `DATA` con la clave `"iaas"` añadida

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build.py — añadir arriba
from unittest.mock import patch

import kobo


def test_encode_incluye_el_bloque_iaas_que_le_pasan(registros_ok, formularios_ok,
                                                    nombres_ok):
    limpio = bd.clean(registros_ok, formularios_ok, nombres_ok)
    data = bd.encode(limpio, formularios_ok, iaas={"ok": True, "meta": {"filas": 3}})
    assert data["iaas"]["meta"]["filas"] == 3


def test_encode_sin_iaas_deja_el_bloque_con_el_motivo(registros_ok,
                                                      formularios_ok, nombres_ok):
    limpio = bd.clean(registros_ok, formularios_ok, nombres_ok)
    data = bd.encode(limpio, formularios_ok,
                     iaas={"ok": False, "error": "HTTP 401"})
    assert data["iaas"]["error"] == "HTTP 401"


def test_main_publica_igual_cuando_kobo_falla(libro_real, capsys):
    """main() no escribe en disco aquí: render_html se sustituye por un espía.

    Llamar a main() de verdad sobreescribiría el dashboard.html del
    repositorio, que no es cosa de una prueba.
    """
    capturado = {}

    def espia(data, template, vendor, salida):
        capturado["data"] = data
        return 0

    with patch("build_dashboard.kobo.construir",
               side_effect=kobo.KoboError("HTTP 401")),          patch("build_dashboard.render_html", side_effect=espia):
        codigo = bd.main([str(libro_real)])

    assert codigo == 0
    assert capturado["data"]["iaas"]["ok"] is False
    assert capturado["data"]["iaas"]["error"] == "HTTP 401"
    salida = capsys.readouterr()
    assert "HTTP 401" in salida.out + salida.err


def test_el_html_generado_no_contiene_datos_de_paciente(tmp_path, libro_real):
    """La prueba que sostiene la promesa de privacidad del apartado.

    Se construye con un envío sintético cuyos campos personales son cadenas
    inconfundibles y se comprueba que ninguna sobrevive al HTML.
    """
    from tests.test_kobo import envio, esquema_completo

    with patch("kobo.descargar",
               return_value=(esquema_completo(), [envio()])):
        iaas = kobo.construir("t0ken")
    data = {"iaas": iaas}
    salida = tmp_path / "d.html"
    plantilla = tmp_path / "t.html"
    plantilla.write_text("<html>/*__DATA__*/ /*__CHARTJS__*/</html>", "utf-8")
    vendor = tmp_path / "chart.js"
    vendor.write_text("// chart", "utf-8")
    bd.render_html(data, plantilla, vendor, salida)
    html = salida.read_text("utf-8")
    assert "PACIENTE_SINTETICO_XYZ" not in html
    assert "EXP-999999" not in html
    assert "CONCLUSION_SINTETICA_XYZ" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_build.py -v -k "iaas or paciente or kobo"`
Expected: FAIL con `TypeError: encode() got an unexpected keyword argument 'iaas'`

- [ ] **Step 3: Write minimal implementation**

```python
# build_dashboard.py — import arriba
import kobo

# encode(): cambiar la firma y añadir la clave al diccionario devuelto
def encode(df, formularios, iaas=None):
    ...
    return {
        "dims": dims,
        "forms": forms,
        "rows": rows,
        "iaas": iaas or {"ok": False, "error": "No se consultó KoboToolbox."},
        ...
    }


# main(): entre clean() y encode()
    # Kobo es una fuente secundaria: si falla, el dashboard de supervisiones
    # se publica igual. El fallo no se esconde —va a stderr y el workflow lo
    # convierte en una anotación—, y la pestaña muestra el motivo.
    try:
        iaas = kobo.construir(os.environ.get("KOBO_TOKEN", ""))
        print(f"IAAS: {iaas['meta']['filas']} envíos, "
              f"{iaas['meta']['pacientes']} pacientes distintos")
    except kobo.KoboError as error:
        iaas = {
            "ok": False,
            "error": str(error),
            "fecha": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
        }
        print(f"AVISO: no se pudo construir el apartado de IAAS: {error}",
              file=sys.stderr)

    data = encode(limpio, formularios, iaas=iaas)
```

Añade `import os` arriba si no está.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ -q`
Expected: PASS, toda la suite

- [ ] **Step 5: Commit**

```bash
git add build_dashboard.py tests/test_build.py
git commit -m "feat: fold the IAAS block into the build without failing it"
```

---

### Task 6: `crearAgg(dataset)` — refactor mecánico

**Files:**
- Modify: `template.html` (bloque `mod-agg`)
- Modify: `tests/test_agg.html` (la copia de `mod-agg` y sus aserciones)

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `crearAgg(dataset)` devuelve `{kpis, rateBy, series, heatmap, tasaDe, totalDe}` operando sobre `dataset.rows` y `dataset.dims`.

- [ ] **Step 1: Write the failing test**

```javascript
// tests/test_agg.html — añadir junto a las aserciones de agg
const aggAlterno = crearAgg({
  dims: DATA.dims,
  rows: DATA.rows
});
check('crearAgg devuelve un agregador equivalente',
      aggAlterno.kpis(todas).tasa, agg.kpis(todas).tasa);
check('crearAgg no comparte estado entre instancias',
      aggAlterno.rateBy(todas, 'responsable').length,
      agg.rateBy(todas, 'responsable').length);
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node /tmp/correr_agg.mjs tests/test_agg.html`
Expected: FAIL con `crearAgg is not defined`

- [ ] **Step 3: Write minimal implementation**

En `template.html` y en `tests/test_agg.html`, cambiar la cabecera y el cierre del módulo:

```javascript
// Antes:
// const agg = (() => {
//   const r = DATA.rows;

// Después:
function crearAgg(dataset) {
  const r = dataset.rows;
  const DIMS = dataset.dims;
  // ...cuerpo idéntico, salvo que las referencias a DATA.dims pasan a DIMS...
  return {kpis, rateBy, series, heatmap, tasaDe, totalDe};
}
const agg = crearAgg(DATA);
```

Dentro del cuerpo hay tres usos de `DATA.dims` (`kpis` lee `DATA.dims.estado`, `rateBy` lee `DATA.dims[dimKey]`, `heatmap` lee las etiquetas): sustituir los tres por `DIMS`. No cambia ninguna otra línea.

- [ ] **Step 4: Run test to verify it passes**

Run: `node /tmp/correr_agg.mjs tests/test_agg.html | tail -1`
Expected: `39 pasan, 0 fallan`

- [ ] **Step 5: Commit**

```bash
git add template.html tests/test_agg.html
git commit -m "refactor: turn agg into a crearAgg(dataset) factory"
```

---

### Task 7: Agregador de IAAS

**Files:**
- Modify: `template.html` (módulo nuevo `mod-iaas`, después de `mod-agg`)
- Modify: `tests/test_agg.html` (copia del módulo y aserciones)

**Interfaces:**
- Consumes: `DATA.iaas`
- Produces: `crearIaas(iaas)` devuelve `{filasActivas, kpis, porActividad, porItem, porDim, series}`
  - `filasActivas(filtros)` — `filtros` es `{desde, hasta, responsable, servicio, actividad}`, cada uno `null` o índice
  - `kpis(filas)` → `{registros, si, no, tasa, respondidos}`
  - `porActividad(filas)` → `[{idx, label, registros, si, no, tasa}]`
  - `porItem(filas)` → `[{idx, titulo, actividad, si, no, respondidos, tasa}]`, ordenado por `no` descendente
  - `porDim(filas, clave)` → `[{idx, label, registros, si, no, tasa}]`
  - `series(filas, periodo)` → `{labels, volumen, tasa}`

- [ ] **Step 1: Write the failing test**

```javascript
// tests/test_agg.html — añadir un DATA.iaas sintético antes de las aserciones
const IAAS = {
  ok: true,
  dims: {responsable: ['Ana', 'Beto'], servicio: ['UCI', 'Nefrología'],
         mes: ['2026-07', '2026-08'], semana: ['2026-W30', '2026-W31']},
  actividades: ['NUEVOS', 'SEGUIMIENTO'],
  items: [{titulo: 'Item A', actividad: 0}, {titulo: 'Item B', actividad: 0},
          {titulo: 'Item C', actividad: 1}],
  rows: {
    dia:        [20655, 20656, 20690],
    responsable:[0, 1, 0],
    servicio:   [0, 0, 1],
    mes:        [0, 0, 1],
    semana:     [0, 0, 1],
    actividades: [[1, 1, 0], [0, 0, 1]],
    items: [[1, 0, null], [1, 1, null], [null, null, 0]],
    si: [2, 1, 0],
    no: [0, 1, 1]
  },
  meta: {filas: 3, pacientes: 2, dia_min: 20655, dia_max: 20690}
};
const iaas = crearIaas(IAAS);
const todasIaas = iaas.filasActivas({desde: null, hasta: null, responsable: null,
                                     servicio: null, actividad: null});

check('iaas filasActivas sin filtros', todasIaas, [0, 1, 2]);
check('iaas filtro por responsable',
      iaas.filasActivas({desde: null, hasta: null, responsable: 0,
                         servicio: null, actividad: null}), [0, 2]);
check('iaas filtro por actividad usa el booleano de la fila',
      iaas.filasActivas({desde: null, hasta: null, responsable: null,
                         servicio: null, actividad: 1}), [2]);
check('iaas kpis tasa ponderada', iaas.kpis(todasIaas).tasa, 3 / 5);
check('iaas kpis respondidos', iaas.kpis(todasIaas).respondidos, 5);
check('iaas porActividad tasa de NUEVOS', iaas.porActividad(todasIaas)[0].tasa,
      3 / 4);
check('iaas porItem ordena los incumplimientos primero',
      iaas.porItem(todasIaas).map(e => e.titulo),
      ['Item A', 'Item C', 'Item B']);
check('iaas porItem ignora los no respondidos',
      iaas.porItem(todasIaas)[2].respondidos, 2);
check('iaas porDim por servicio',
      iaas.porDim(todasIaas, 'servicio').map(e => e.label), ['UCI', 'Nefrología']);
check('iaas series por mes', iaas.series(todasIaas, 'mes').volumen, [2, 1]);
```

Aritmética de las cifras esperadas, para poder verificarlas a mano:

- Filas 0, 1 y 2 responden `si=2/no=0`, `si=1/no=1` y `si=0/no=1`. Global: **3 SI sobre 5 respondidos**.
- Actividad NUEVOS: la declaran las filas 0 y 1, y sus ítems son A `[1, 0, null]` y B `[1, 1, null]`. Sobre esas dos filas: 3 SI y 1 NO, **3/4**. El ítem C no pertenece a esta actividad y no entra.
- `porItem` ordena por `no` descendente; A y C empatan a 1 `NO`, y desempata el volumen respondido (A tiene 2, C tiene 1). De ahí `['Item A', 'Item C', 'Item B']`.

- [ ] **Step 2: Run test to verify it fails**

Run: `node /tmp/correr_agg.mjs tests/test_agg.html`
Expected: FAIL con `crearIaas is not defined`

- [ ] **Step 3: Write minimal implementation**

```javascript
<script id="mod-iaas">
/** Agregación del apartado de IAAS.
 *
 * Vive aparte de `crearAgg` porque el esquema es distinto: aquí cada envío
 * tiene N ítems SI/NO y un vector de actividades declaradas, no un único
 * dictamen. Lo que sí comparte es el criterio: un ítem sin responder no
 * cuenta en el denominador.
 */
function crearIaas(iaas) {
  const r = iaas.rows;
  const n = iaas.meta.filas;

  function tasaDe(si, no) {
    return si + no === 0 ? null : si / (si + no);
  }

  function filasActivas(f) {
    const out = [];
    for (let i = 0; i < n; i++) {
      if (f.desde !== null && r.dia[i] < f.desde) continue;
      if (f.hasta !== null && r.dia[i] > f.hasta) continue;
      if (f.responsable !== null && r.responsable[i] !== f.responsable) continue;
      if (f.servicio !== null && r.servicio[i] !== f.servicio) continue;
      if (f.actividad !== null && r.actividades[f.actividad][i] !== 1) continue;
      out.push(i);
    }
    return out;
  }

  function kpis(filas) {
    let si = 0, no = 0;
    for (const i of filas) { si += r.si[i]; no += r.no[i]; }
    return {registros: filas.length, si, no, respondidos: si + no,
            tasa: tasaDe(si, no)};
  }

  function porActividad(filas) {
    return iaas.actividades.map((label, a) => {
      let si = 0, no = 0, registros = 0;
      const suyos = iaas.items
        .map((it, j) => (it.actividad === a ? j : -1))
        .filter(j => j >= 0);
      for (const i of filas) {
        if (r.actividades[a][i] !== 1) continue;
        registros++;
        for (const j of suyos) {
          const v = r.items[j][i];
          if (v === 1) si++;
          else if (v === 0) no++;
        }
      }
      return {idx: a, label, registros, si, no, tasa: tasaDe(si, no)};
    });
  }

  function porItem(filas) {
    const salida = iaas.items.map((it, j) => {
      let si = 0, no = 0;
      for (const i of filas) {
        const v = r.items[j][i];
        if (v === 1) si++;
        else if (v === 0) no++;
      }
      return {idx: j, titulo: it.titulo,
              actividad: iaas.actividades[it.actividad],
              si, no, respondidos: si + no, tasa: tasaDe(si, no)};
    });
    // Los incumplimientos primero: es lo que se va a mirar. A igualdad de
    // NO, manda el volumen respondido.
    salida.sort((a, b) => b.no - a.no || b.respondidos - a.respondidos);
    return salida;
  }

  function porDim(filas, clave) {
    const etiquetas = iaas.dims[clave];
    const acc = new Map();
    for (const i of filas) {
      const idx = r[clave][i];
      let e = acc.get(idx);
      if (!e) { e = {idx, label: etiquetas[idx], registros: 0, si: 0, no: 0};
                acc.set(idx, e); }
      e.registros++;
      e.si += r.si[i];
      e.no += r.no[i];
    }
    const salida = [...acc.values()];
    for (const e of salida) e.tasa = tasaDe(e.si, e.no);
    salida.sort((a, b) => a.idx - b.idx);
    return salida;
  }

  function series(filas, periodo) {
    const etiquetas = iaas.dims[periodo];
    const vol = etiquetas.map(() => 0);
    const si = etiquetas.map(() => 0);
    const no = etiquetas.map(() => 0);
    for (const i of filas) {
      const k = r[periodo][i];
      vol[k]++; si[k] += r.si[i]; no[k] += r.no[i];
    }
    return {labels: etiquetas, volumen: vol,
            tasa: etiquetas.map((_, k) => tasaDe(si[k], no[k]))};
  }

  return {filasActivas, kpis, porActividad, porItem, porDim, series, tasaDe};
}
</script>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node /tmp/correr_agg.mjs tests/test_agg.html | tail -1`
Expected: `49 pasan, 0 fallan`

- [ ] **Step 5: Commit**

```bash
git add template.html tests/test_agg.html
git commit -m "feat: add the IAAS aggregation module"
```

---

### Task 8: Pestaña y barra de filtros por vista

**Files:**
- Modify: `template.html:134-138` (los botones de pestaña)
- Modify: `template.html` (módulo `app`: `construirBarra`, `pintarChips`, `pestanas`)
- Modify: `template.html` (`views.render`)

**Interfaces:**
- Consumes: `crearIaas` (Task 7)
- Produces: `views.estado.vista === 'iaas'` renderiza la vista nueva; `app` reconstruye la barra al cambiar de pestaña.

- [ ] **Step 1: Write the failing test**

Esta task es DOM puro y el harness JS no lo alcanza. La comprobación es manual y queda escrita aquí como guion exacto, a ejecutar en el paso 4:

```javascript
// En la consola del dashboard construido:
document.querySelectorAll('.tabs button').length            // 4
document.querySelector('[data-view="iaas"]').click();
document.querySelectorAll('#filters select').length          // 3
document.querySelector('#view h2').textContent               // no vacío
document.querySelector('[data-view="global"]').click();
document.querySelectorAll('#filters select').length          // 6
```

- [ ] **Step 2: Verificar que hoy falla**

Run: abrir `dashboard.html` y ejecutar la primera línea.
Expected: `3`, no `4`.

- [ ] **Step 3: Write minimal implementation**

En el HTML, añadir el botón:

```html
    <button role="tab" data-view="iaas" aria-selected="false">Investigación de IAAS</button>
```

En `app`, separar la barra en dos constructores y reconstruirla al cambiar de pestaña:

```javascript
  const FILTROS_IAAS = ['responsable', 'servicio', 'actividad'];
  const ETIQUETAS_IAAS = {responsable: 'Responsable', servicio: 'Servicio',
                          actividad: 'Actividad'};

  function opcionesIaas(clave) {
    if (clave === 'actividad') return DATA.iaas.actividades;
    return DATA.iaas.dims[clave];
  }

  function selectorIaas(clave) {
    const label = document.createElement('label');
    label.textContent = ETIQUETAS_IAAS[clave];
    const sel = document.createElement('select');
    const todos = document.createElement('option');
    todos.value = '';
    todos.textContent = 'Todos';
    sel.appendChild(todos);
    opcionesIaas(clave).forEach((valor, i) => {
      const op = document.createElement('option');
      op.value = String(i);
      op.textContent = valor;
      sel.appendChild(op);
    });
    sel.addEventListener('change', () => {
      storeIaas.set(clave, sel.value === '' ? null : Number(sel.value));
    });
    sel.dataset.clave = clave;
    label.appendChild(sel);
    return label;
  }

  function construirBarra() {
    barra.replaceChildren();
    zonaChips.replaceChildren();
    if (views.estado.vista === 'iaas') {
      if (!DATA.iaas.ok) return;            // sin datos no hay nada que filtrar
      barra.append(fechaIaas('desde', 'Desde'), fechaIaas('hasta', 'Hasta'));
      FILTROS_IAAS.forEach(k => barra.appendChild(selectorIaas(k)));
      barra.appendChild(botonLimpiar(() => storeIaas.clearAll()));
      return;
    }
    barra.append(fecha('desde', 'Desde'), fecha('hasta', 'Hasta'));
    store.dimsFiltrables.forEach(k => barra.appendChild(selector(k)));
    barra.appendChild(botonLimpiar(() => store.clearAll()));
  }
```

`botonLimpiar(alLimpiar)` extrae el botón que hoy está inline en `construirBarra`: crea el `button.chip`, vacía los controles de la barra y llama a `alLimpiar`. `fechaIaas` es `fecha` con `DATA.iaas.meta` en lugar de `DATA.meta` para `min`/`max` y con `storeIaas.set`.

`storeIaas` es un store mínimo, hermano del existente:

```javascript
const storeIaas = (() => {
  const filters = {desde: null, hasta: null, responsable: null,
                   servicio: null, actividad: null};
  const oyentes = [];
  function set(clave, valor) { filters[clave] = valor; emit(); }
  function clear(clave) { filters[clave] = null; emit(); }
  function clearAll() {
    Object.keys(filters).forEach(k => { filters[k] = null; });
    emit();
  }
  function onChange(fn) { oyentes.push(fn); }
  function emit() { oyentes.forEach(fn => fn()); }
  return {filters, set, clear, clearAll, onChange, emit};
})();
```

En `pestanas()`, tras fijar `views.estado.vista`, llamar a `construirBarra()` antes de `views.render()`.

En `views.render()`, la vista de IAAS no pasa por `store.activeRows()`:

```javascript
    if (estado.vista === 'iaas') { renderIaas(); return; }
    const filas = store.activeRows();
```

- [ ] **Step 4: Ejecutar el guion de comprobación**

Run: `python build_dashboard.py SupPCI.xlsx` (o el Sheet), abrir `dashboard.html` y pegar el guion del paso 1.
Expected: los cinco valores del guion.

- [ ] **Step 5: Commit**

```bash
git add template.html
git commit -m "feat: add the IAAS tab with its own filter bar"
```

---

### Task 9: Las siete tarjetas de la vista

**Files:**
- Modify: `template.html` (función `renderIaas` dentro del módulo `views`)

**Interfaces:**
- Consumes: `crearIaas`, `storeIaas`, `card`, `kpi`, `conTabla`, `zonaDe`, `plot`, `charts.*`, `agg.totalDe`
- Produces: `renderIaas()`

- [ ] **Step 1: Escribir el guion de comprobación**

```javascript
// Con la pestaña de IAAS activa:
document.querySelectorAll('#view .card h2').length                  // 6
[...document.querySelectorAll('#view .card')].every(c =>
  !c.querySelector('canvas') ||
  [...c.querySelectorAll('button')].some(b => b.textContent === 'Ver tabla'))  // true
document.querySelector('#view .card table tfoot')                    // no null
```

- [ ] **Step 2: Verificar que hoy falla**

Expected: `0` tarjetas — `renderIaas` aún no existe.

- [ ] **Step 3: Write minimal implementation**

```javascript
  function renderIaas() {
    if (!DATA.iaas.ok) {
      const aviso = vacio(
        'Datos de Kobo no disponibles: ' + DATA.iaas.error +
        (DATA.iaas.fecha ? ' (último intento: ' + DATA.iaas.fecha + ')' : ''));
      contenedor.appendChild(aviso);
      return;
    }
    const filas = iaas.filasActivas(storeIaas.filters);
    if (!filas.length) {
      contenedor.appendChild(vacio('Sin registros para estos filtros.'));
      return;
    }
    const k = iaas.kpis(filas);

    const fila = document.createElement('div');
    fila.className = 'kpis';
    fila.style.marginBottom = '16px';
    fila.append(
      kpi('Registros', charts.num(k.registros)),
      kpi('Cumplimiento', charts.pct(k.tasa)),
      kpi('Ítems respondidos', charts.num(k.respondidos)),
      kpi('Ítems en NO', charts.num(k.no))
    );
    contenedor.appendChild(fila);

    // Los pacientes distintos no son filtrables: contarlos por filtro
    // exigiría publicar un identificador por fila, y eso permite reidentificar
    // a una persona cruzando fecha, servicio y responsable. Se publica solo
    // el total del periodo.
    const nota = document.createElement('div');
    nota.className = 'sub';
    nota.style.marginBottom = '16px';
    nota.textContent = 'Sobre el periodo completo: ' +
      charts.num(DATA.iaas.meta.pacientes) + ' pacientes distintos.';
    contenedor.appendChild(nota);

    const porAct = iaas.porActividad(filas);
    const tAct = card('Cumplimiento por actividad', null);
    conTabla(tAct,
      [{titulo: 'Actividad'}, {titulo: 'Registros', num: true, formato: charts.num},
       {titulo: 'Tasa', num: true, formato: charts.pct}],
      porAct.map(e => [e.label, e.registros, e.tasa]),
      zona => {
        const caja = document.createElement('div');
        caja.className = 'plot';
        caja.style.height = Math.max(140, porAct.length * 24 + 40) + 'px';
        const lienzo = document.createElement('canvas');
        caja.appendChild(lienzo);
        zona.appendChild(caja);
        charts.bars(lienzo, {
          labels: porAct.map(e => `${e.label} (${e.registros})`),
          values: porAct.map(e => e.tasa),
          extra: porAct.map(e => `${e.si} de ${e.si + e.no} ítems respondidos`),
          formato: charts.pct
        });
      });
    contenedor.appendChild(tAct);

    const porIt = iaas.porItem(filas);
    const sumaIt = agg.totalDe(porIt.map(e => ({si: e.si, no: e.no,
                                                total: e.respondidos})));
    const tItems = card('Ítems',
                        'Ordenados por incumplimientos: lo que hay que mirar va arriba.');
    charts.tabla(zonaDe(tItems),
      [{titulo: 'Ítem'}, {titulo: 'Actividad'},
       {titulo: 'Respondidos', num: true, formato: charts.num},
       {titulo: 'NO', num: true, formato: charts.num},
       {titulo: 'Tasa', num: true, formato: charts.pct}],
      porIt.map(e => [e.titulo, e.actividad, e.respondidos, e.no, e.tasa]),
      {total: [`Total (${porIt.length} ítems)`, '', sumaIt.total, undefined,
               sumaIt.tasa]});
    contenedor.appendChild(tItems);

    const tProd = card('Producción por actividad', null);
    conTabla(tProd,
      [{titulo: 'Actividad'}, {titulo: 'Registros', num: true, formato: charts.num}],
      porAct.map(e => [e.label, e.registros]),
      zona => charts.columns(plot(zona, 'i-prod'), {
        labels: porAct.map(e => e.label),
        values: porAct.map(e => e.registros),
        formato: charts.num
      }));
    contenedor.appendChild(tProd);

    const rejilla = document.createElement('div');
    rejilla.className = 'grid-2';
    for (const [clave, titulo] of [['responsable', 'Por responsable'],
                                   ['servicio', 'Por servicio']]) {
      const datos = iaas.porDim(filas, clave);
      const suma = agg.totalDe(datos.map(e => ({si: e.si, no: e.no,
                                                total: e.registros})));
      const tarjeta = card(titulo, null);
      charts.tabla(zonaDe(tarjeta),
        [{titulo}, {titulo: 'Registros', num: true, formato: charts.num},
         {titulo: 'Tasa', num: true, formato: charts.pct}],
        datos.map(e => [e.label, e.registros, e.tasa]),
        {total: [`Total (${suma.n})`, suma.total, suma.tasa]});
      rejilla.appendChild(tarjeta);
    }
    contenedor.appendChild(rejilla);

    const s = iaas.series(filas, 'mes');
    const tEvo = card('Evolución mensual', null);
    conTabla(tEvo,
      [{titulo: 'Mes'}, {titulo: 'Registros', num: true, formato: charts.num},
       {titulo: 'Tasa', num: true, formato: charts.pct}],
      s.labels.map((l, i) => [l, s.volumen[i], s.tasa[i]]),
      zona => charts.line(plot(zona, 'i-evo'), {
        labels: s.labels,
        series: [{label: 'Cumplimiento', data: s.tasa,
                  color: charts.token('series-1')}]
      }));
    contenedor.appendChild(tEvo);
  }
```

Y arriba del módulo `views`, junto al resto de constantes:

```javascript
  const iaas = DATA.iaas.ok ? crearIaas(DATA.iaas) : null;
```

Enganchar el repintado: `storeIaas.onChange(() => { pintarChipsIaas(); views.render(); });` en el arranque de `app`.

- [ ] **Step 4: Ejecutar el guion de comprobación**

Run: reconstruir, abrir el dashboard, pestaña de IAAS, pegar el guion del paso 1.
Expected: `6`, `true`, un nodo `<tfoot>`.

- [ ] **Step 5: Commit**

```bash
git add template.html
git commit -m "feat: render the IAAS view cards"
```

---

### Task 10: Workflow, README y publicación

**Files:**
- Modify: `.github/workflows/publicar.yml`
- Modify: `README.md`

- [ ] **Step 1: Pasar el token al build y convertir el aviso en anotación**

```yaml
      - name: Construir desde el Sheet en vivo
        # Aborta si el documento cambió de forma. La URL conserva entonces
        # la última versión buena. KOBO_TOKEN es opcional: si falta o falla,
        # el dashboard se publica sin el apartado de IAAS y el paso siguiente
        # marca el run.
        run: python build_dashboard.py 2> >(tee construccion.err >&2)
        env:
          KOBO_TOKEN: ${{ secrets.KOBO_TOKEN }}

      - name: Avisar si el apartado de IAAS no se pudo construir
        if: always()
        run: |
          if grep -q "^AVISO:" construccion.err 2>/dev/null; then
            echo "::warning::$(grep '^AVISO:' construccion.err | head -1)"
          fi
```

- [ ] **Step 2: Documentar en el README**

Añadir tras la sección "Actualizar los datos publicados":

```markdown
## El apartado de investigación de IAAS

La pestaña "Investigación de IAAS" se alimenta del formulario de KoboToolbox
`aefXsYwJo5RsrZYfaCEcva` en `kf.kobotoolbox.org`, leído en cada ejecución del
workflow.

Necesita el secret **`KOBO_TOKEN`** (Settings → Secrets and variables →
Actions) con un token de la API de Kobo. Sin él, o si Kobo no responde, el
dashboard **se publica igual**: la pestaña muestra el motivo y el run queda
marcado con un aviso en Actions. Nunca se publica un dashboard a medias sin
que se sepa por qué.

Del formulario solo se publican fecha, responsable, servicio, actividades
declaradas y las 24 respuestas SI/NO. El nombre del paciente, el expediente,
las conclusiones y el responsable de reporte no salen del proceso de
construcción: `kobo.py` los descarta al cargar, con una lista blanca, y una
prueba comprueba que no aparecen en el HTML generado.
```

- [ ] **Step 3: Verificar la suite completa**

Run: `python -m pytest tests/ -q && node /tmp/correr_agg.mjs tests/test_agg.html | tail -1`
Expected: todas las pruebas de pytest en verde y `49 pasan, 0 fallan`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/publicar.yml README.md
git commit -m "feat: wire KOBO_TOKEN into the workflow and document the section"
```

- [ ] **Step 5: Primera ejecución real**

Requiere que el secret `KOBO_TOKEN` exista. Empujar, lanzar **Run workflow**
(nunca "Re-run jobs": reutiliza el run y sube un segundo artefacto
`github-pages`, que hace fallar a `deploy-pages`), y comprobar en la página
publicada que la pestaña trae datos y no un aviso de error.

---

## Trabajo de seguimiento, fuera de este plan

- Fijar los nombres XML en el manifiesto tras la primera ejecución con token,
  para que renombrar una etiqueta en Kobo deje de romper el emparejamiento.
  Requiere añadir a `kobo.py` un `--volcar-esquema` que imprima el mapa real.
- Una prueba que verifique que las copias de los módulos en `tests/test_agg.html`
  siguen coincidiendo con `template.html`. Hoy la divergencia solo se detecta
  leyendo.
