import re
from unittest.mock import patch

import pytest
import requests

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


# Forma real que devuelve la API de Kobo, comprobada contra el formulario en
# producción: las preguntas no traen `name` sino `$autoname`, los ítems son
# `score__row` dentro de `begin_score`, y `$xpath` ya da la ruta del envío.
ESQUEMA_KOBO = {
    "content": {
        "survey": [
            {"type": "date", "$autoname": "Fecha_de_registro",
             "$xpath": "Fecha_de_registro", "label": ["Fecha de registro"]},
            {"type": "begin_score", "$autoname": "CASOS_NUEVOS_INVESTIGADOS",
             "label": ["CASOS NUEVOS INVESTIGADOS"]},
            {"type": "score__row", "$autoname": "Se_realizo_investiga_i_n",
             "$xpath": "CASOS_NUEVOS_INVESTIGADOS/Se_realizo_investiga_i_n",
             "label": ["Se realizo investigación de un nuevo caso"]},
            {"type": "end_score"},
            {"type": "select_one", "$autoname": "Sin_xpath",
             "label": ["Pregunta sin xpath"]},
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


def test_mapa_de_campos_usa_autoname_cuando_no_hay_name():
    mapa = kobo.mapa_de_campos(ESQUEMA_KOBO)
    assert mapa["fecha de registro"] == "Fecha_de_registro"


def test_mapa_de_campos_prefiere_el_xpath_de_la_propia_api():
    mapa = kobo.mapa_de_campos(ESQUEMA_KOBO)
    assert (mapa["se realizo investigación de un nuevo caso"]
            == "CASOS_NUEVOS_INVESTIGADOS/Se_realizo_investiga_i_n")


def test_mapa_de_campos_sin_xpath_cae_al_autoname():
    mapa = kobo.mapa_de_campos(ESQUEMA_KOBO)
    assert mapa["pregunta sin xpath"] == "Sin_xpath"


def test_mapa_de_campos_no_confunde_el_grupo_de_puntuacion_con_una_pregunta():
    """`begin_score` es el contenedor de una actividad, no una pregunta."""
    mapa = kobo.mapa_de_campos(ESQUEMA_KOBO)
    assert "casos nuevos investigados" not in mapa


def test_manifiesto_declara_seis_actividades_y_tres_principales():
    assert len(kobo.ACTIVIDADES) == 6
    assert kobo.PRINCIPALES == 3
    assert kobo.ACTIVIDADES[:3] == ["CASOS NUEVOS INVESTIGADOS",
                                    "CASOS EN SEGUIMIENTO",
                                    "CIERRE DE CASOS"]


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


def esquema_completo():
    """Esquema sintético con las preguntas que el manifiesto exige.

    Incluye un ítem de puntuación aunque el apartado ya no los publique: así
    se parece a lo que devuelve Kobo y las pruebas de la lista blanca valen
    para algo.
    """
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
        {"type": "begin_score", "name": "score",
         "label": ["CASOS NUEVOS INVESTIGADOS"]},
        {"type": "score__row", "name": "i0",
         "label": ["Se realizo investigación de un nuevo caso"]},
        {"type": "end_score"},
    ]
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
        "score/i0": "si",
        "paciente": "PACIENTE_SINTETICO_XYZ",
        "expediente": "EXP-999999",
        "conclusiones": "CONCLUSION_SINTETICA_XYZ",
        "_id": 1,
        "_uuid": "uuid-1",
    }
    base.update(extra)
    return base


def limpiar_con(esquema, envios):
    """limpiar() con el mapa y las opciones del mismo esquema."""
    mapa = kobo.validar(esquema)
    return kobo.limpiar(envios, mapa, choices=kobo._choices_de_actividad(esquema))


def test_validar_devuelve_el_mapa_cuando_estan_todas_las_etiquetas():
    mapa = kobo.validar(esquema_completo())
    assert mapa[kobo.normalizar(kobo.CAMPOS["fecha"])] == "fecha"


def test_validar_nombra_la_etiqueta_que_falta():
    esquema = esquema_completo()
    esquema["content"]["survey"] = [
        c for c in esquema["content"]["survey"]
        if c.get("label", [""])[0] != kobo.CAMPOS["servicio"]
    ]
    with pytest.raises(kobo.KoboError,
                       match=re.escape(kobo.CAMPOS["servicio"][:25])):
        kobo.validar(esquema)


def test_validar_no_exige_las_preguntas_de_los_items():
    """El apartado no publica las respuestas SI/NO, así que no las valida.

    Eran 24 etiquetas de texto libre en el manifiesto: cada una, una manera
    de romper el apartado por reescribir una pregunta en Kobo.
    """
    esquema = esquema_completo()
    esquema["content"]["survey"] = [
        c for c in esquema["content"]["survey"] if c.get("type") != "score__row"
    ]
    assert kobo.validar(esquema)


def test_validar_exige_las_seis_opciones_de_produccion():
    esquema = esquema_completo()
    esquema["content"]["choices"] = esquema["content"]["choices"][:4]
    with pytest.raises(kobo.KoboError, match="Producción Reportada"):
        kobo.validar(esquema)


def test_limpiar_no_conserva_ningun_campo_prohibido():
    filas, _ = limpiar_con(esquema_completo(), [envio()])
    texto = repr(filas)
    assert "PACIENTE_SINTETICO_XYZ" not in texto
    assert "EXP-999999" not in texto
    assert "CONCLUSION_SINTETICA_XYZ" not in texto
    assert "uuid-1" not in texto
    assert set(filas[0]) == {"fecha", "responsable", "servicio", "actividades"}


def test_limpiar_no_publica_las_respuestas_si_no():
    filas, _ = limpiar_con(esquema_completo(), [envio()])
    assert "items" not in filas[0]


def test_limpiar_marca_solo_las_actividades_declaradas():
    filas, _ = limpiar_con(esquema_completo(), [envio(prod="a0 a2")])
    assert filas[0]["actividades"] == [1, 0, 1, 0, 0, 0]


def test_limpiar_cuenta_pacientes_distintos_sin_publicarlos():
    envios = [envio(expediente="A"), envio(expediente="A"), envio(expediente="B")]
    filas, pacientes = limpiar_con(esquema_completo(), envios)
    assert pacientes == 2
    assert "'A'" not in repr(filas)


def test_limpiar_rechaza_una_fecha_ilegible():
    with pytest.raises(kobo.KoboError, match="ayer"):
        limpiar_con(esquema_completo(), [envio(fecha="ayer")])


def test_construir_devuelve_una_columna_por_actividad():
    envios = [envio(prod="a0"), envio(prod="a0 a2"), envio(prod="a1")]
    with patch("kobo.descargar", return_value=(esquema_completo(), envios)):
        data = kobo.construir("t0ken")
    assert data["ok"] is True
    assert len(data["rows"]["actividades"]) == 6
    assert data["rows"]["actividades"][0] == [1, 1, 0]
    assert data["rows"]["actividades"][2] == [0, 1, 0]


def test_construir_no_publica_items_ni_tasas():
    with patch("kobo.descargar", return_value=(esquema_completo(), [envio()])):
        data = kobo.construir("t0ken")
    assert "items" not in data
    assert "items" not in data["rows"]
    assert "si" not in data["rows"]
    assert "no" not in data["rows"]


def test_construir_declara_cuantas_actividades_son_principales():
    with patch("kobo.descargar", return_value=(esquema_completo(), [envio()])):
        data = kobo.construir("t0ken")
    assert data["principales"] == 3


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
    assert data["rows"]["actividades"] == [[] for _ in range(6)]


def test_construir_falla_si_ningun_envio_declara_actividades():
    """Si nadie declara nada, el emparejamiento de opciones está roto.

    El select_multiple es obligatorio en el formulario, así que un lote de
    envíos con cero actividades no es un dato: es que los nombres de opción
    dejaron de coincidir. Sin esta guarda, el apartado se publicaría con
    todas las tarjetas a cero y nadie sabría por qué.
    """
    with patch("kobo.descargar",
               return_value=(esquema_completo(), [envio(prod=""), envio(prod="")])):
        with pytest.raises(kobo.KoboError, match="actividad"):
            kobo.construir("t0ken")
