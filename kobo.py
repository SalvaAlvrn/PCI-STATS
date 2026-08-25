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
        mapa[normalizar(etiquetas[0])] = "/".join([*grupos, nombre])
    return mapa
