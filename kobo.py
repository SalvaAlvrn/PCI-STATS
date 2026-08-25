"""Seguimiento de la investigación de casos de IAAS.

Lee los envíos del formulario de KoboToolbox y produce el bloque `DATA.iaas`
que consume el dashboard: qué actividad declaró cada envío, quién y dónde.

Las respuestas SI/NO de cada actividad se leen en Kobo pero no se publican:
el apartado mide producción, no cumplimiento. Vive aparte de `build_dashboard.py` a propósito: el
pipeline de supervisiones no debe cambiar de comportamiento porque esta fuente
falle o cambie de forma.
"""

import re
import unicodedata

import pandas as pd
import requests


class KoboError(Exception):
    """Kobo no respondió, o su formulario ya no tiene la forma esperada.

    No aborta el build: `build_dashboard.py` lo captura y publica el
    dashboard sin los datos, con el motivo a la vista.
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
# jamás. No es lo que filtra —eso lo hace la lista blanca de `limpiar`— sino
# la lista contra la que una prueba comprueba que ninguno se cuela.
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

# Las tres primeras son las actividades que el apartado destaca; las otras
# tres se monitorean, pero no compiten con ellas por el espacio.
PRINCIPALES = 3

def normalizar(texto):
    """Etiqueta comparable: sin espacios duros, sin dobles espacios, en minúsculas.

    Kobo conserva los saltos de línea y los `\\xa0` que el autor del
    formulario pegó sin querer. Comparar etiquetas en crudo fallaría por
    diferencias que nadie ve al leerlas.
    """
    texto = unicodedata.normalize("NFKC", str(texto)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", texto).strip().lower()


def mapa_de_campos(esquema):
    """Etiqueta normalizada → nombre XML, con el prefijo de grupo incluido.

    Los envíos traen las preguntas de un grupo bajo `grupo/pregunta`, así que
    el nombre suelto no basta para leerlos.
    """
    survey = esquema.get("content", {}).get("survey")
    if not survey:
        raise KoboError(
            "El esquema del formulario llegó sin «content.survey». "
            "Comprueba el asset uid."
        )
    mapa = {}
    grupos = []
    for campo in survey:
        tipo = campo.get("type")
        # Las actividades del formulario son grupos de puntuación
        # (`begin_score`), no `begin_group`: sus ítems son `score__row`. El
        # contenedor no es una pregunta y no entra en el mapa.
        if tipo in ("begin_group", "begin_score", "begin_repeat"):
            grupos.append(campo.get("name") or campo.get("$autoname", ""))
            continue
        if tipo in ("end_group", "end_score", "end_repeat"):
            if grupos:
                grupos.pop()
            continue
        etiquetas = campo.get("label") or []
        # Kobo solo escribe `name` cuando quien diseñó el formulario lo puso a
        # mano; el resto de preguntas viajan con `$autoname`, que es el nombre
        # que acaba en los envíos.
        nombre = campo.get("name") or campo.get("$autoname")
        if not etiquetas or not nombre:
            continue
        # `$xpath` ya trae la ruta completa tal como aparece en el envío.
        # Cuando está, se usa: es la respuesta de la propia API en lugar de
        # una ruta reconstruida por nosotros.
        ruta = campo.get("$xpath") or "/".join([*grupos, nombre])
        mapa[normalizar(etiquetas[0])] = ruta
    return mapa


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
    # La API pagina los envíos; `next` trae ya formada la URL de la página
    # siguiente. Se sigue hasta que viene nula.
    while url:
        pagina = _pedir(url, token)
        envios.extend(pagina.get("results", []))
        url = pagina.get("next")
    return esquema, envios


def _choices_de_actividad(esquema):
    """Etiqueta normalizada → nombre de opción, para «Producción Reportada»."""
    salida = {}
    for opcion in esquema.get("content", {}).get("choices", []):
        etiquetas = opcion.get("label") or []
        if etiquetas and opcion.get("name"):
            salida[normalizar(etiquetas[0])] = opcion["name"]
    return salida


def validar(esquema):
    """Comprueba que el formulario tiene la forma del manifiesto.

    Devuelve el mapa etiqueta→nombre para que quien valida y quien limpia no
    puedan acabar usando mapas distintos.
    """
    mapa = mapa_de_campos(esquema)
    esperadas = list(CAMPOS.values())
    faltan = [e for e in esperadas if normalizar(e) not in mapa]
    if faltan:
        raise KoboError(
            "El formulario de Kobo ya no tiene la forma esperada. No se "
            f"encontraron estas preguntas: {faltan}. Si las renombraste en "
            "Kobo, actualiza el manifiesto de kobo.py."
        )
    choices = _choices_de_actividad(esquema)
    faltan_actividades = [a for a in ACTIVIDADES if normalizar(a) not in choices]
    if faltan_actividades:
        raise KoboError(
            "Faltan opciones de «Producción Reportada» en el formulario: "
            f"{faltan_actividades}."
        )
    return mapa


def limpiar(envios, mapa, choices=None):
    """Aplica la lista blanca. Devuelve (filas, pacientes distintos).

    Lo que no está en la lista blanca no se copia: un campo nuevo en Kobo no
    se publica por descuido, que es el comportamiento que hace falta por
    defecto en una página pública.
    """
    choices = choices or {}
    nombre_actividad = [choices.get(normalizar(a), a) for a in ACTIVIDADES]
    campo = {clave: mapa[normalizar(etiqueta)] for clave, etiqueta in CAMPOS.items()}
    # El expediente se lee para contar personas distintas y se descarta con el
    # envío: no entra en `filas` ni, por tanto, en el HTML. El nombre del
    # campo sale del mapa, no de una cadena adivinada.
    campo_expediente = mapa.get(normalizar("Expediente"))

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
        filas.append({
            "fecha": fecha,
            "responsable": str(envio.get(campo["responsable"], "")).strip(),
            "servicio": str(envio.get(campo["servicio"], "")).strip(),
            "actividades": [1 if n in declaradas else 0 for n in nombre_actividad],
        })
        if campo_expediente:
            expediente = str(envio.get(campo_expediente, "")).strip()
            if expediente:
                expedientes.add(expediente)
    return filas, len(expedientes)


def construir(token, servidor=KOBO_SERVIDOR, uid=KOBO_ASSET_UID):
    """Descarga, valida, limpia y codifica. Devuelve el bloque DATA.iaas."""
    esquema, envios = descargar(token, servidor, uid)
    mapa = validar(esquema)
    filas, pacientes = limpiar(envios, mapa, choices=_choices_de_actividad(esquema))

    fechas = (pd.to_datetime([f["fecha"] for f in filas])
              if filas else pd.DatetimeIndex([]))
    meses = [f"{d:%Y-%m}" for d in fechas]
    semanas = [f"{c.year}-W{c.week:02d}" for c in (d.isocalendar() for d in fechas)]
    # Días desde epoch, igual que DIA en build_dashboard.py: el cast a
    # datetime64[D] no depende de la unidad de la columna.
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

    # Cero actividades declaradas sobre envíos que existen significa que los
    # nombres de opción dejaron de emparejar, no que nadie trabajara: el
    # campo es obligatorio en el formulario. Sin esta comprobación el
    # apartado se publicaría entero a cero sin decir por qué.
    if filas and not any(any(f["actividades"]) for f in filas):
        raise KoboError(
            f"Ninguno de los {len(filas)} envíos declara actividad alguna en "
            "«Producción Reportada». Las opciones del formulario dejaron de "
            "coincidir con el manifiesto de kobo.py."
        )

    rows["dia"] = dias
    rows["actividades"] = [
        [f["actividades"][a] for f in filas] for a in range(len(ACTIVIDADES))
    ]

    return {
        "ok": True,
        "dims": dims,
        "actividades": list(ACTIVIDADES),
        "principales": PRINCIPALES,
        "rows": rows,
        "meta": {
            "generado": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
            "filas": len(filas),
            "pacientes": pacientes,
            "dia_min": min(dias) if dias else 0,
            "dia_max": max(dias) if dias else 0,
        },
    }
