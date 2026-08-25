"""Seguimiento al cumplimiento de la investigación de casos de IAAS.

Lee los envíos del formulario de KoboToolbox y produce el bloque `DATA.iaas`
que consume el dashboard. Vive aparte de `build_dashboard.py` a propósito: el
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


# Los envíos traen el nombre de la opción («si»), no su etiqueta («SI»).
VALORES_ITEM = {"SI": 1, "SÍ": 1, "NO": 0}
# N/A es «no aplica»: fuera del denominador, igual que un ítem sin responder.
# Contarlo como incumplimiento castigaría a quien declara que algo no aplicaba.
VALORES_NO_APLICA = {"N_A", "N/A", "NA"}


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
    esperadas = [*CAMPOS.values(), *(etiqueta for _, etiqueta in ITEMS)]
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
    campos_item = [mapa[normalizar(etiqueta)] for _, etiqueta in ITEMS]
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
        items = []
        for nombre in campos_item:
            valor = envio.get(nombre)
            if valor in (None, ""):
                items.append(None)
                continue
            texto = str(valor).strip().upper()
            if texto in VALORES_NO_APLICA:
                items.append(None)
                continue
            if texto not in VALORES_ITEM:
                raise KoboError(
                    f"Un ítem trae un valor no soportado: {texto!r}. Solo se "
                    "interpretan SI, NO y N/A."
                )
            items.append(VALORES_ITEM[texto])
        filas.append({
            "fecha": fecha,
            "responsable": str(envio.get(campo["responsable"], "")).strip(),
            "servicio": str(envio.get(campo["servicio"], "")).strip(),
            "actividades": [1 if n in declaradas else 0 for n in nombre_actividad],
            "items": items,
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
    rows["items"] = [[f["items"][j] for f in filas] for j in range(len(ITEMS))]
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
