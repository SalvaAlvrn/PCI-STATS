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
        if c["label"][0] != kobo.ITEMS[3][1]
    ]
    with pytest.raises(kobo.KoboError, match=re.escape(kobo.ITEMS[3][1][:25])):
        kobo.validar(esquema)


def test_limpiar_no_conserva_ningun_campo_prohibido():
    filas, _ = limpiar_con(esquema_completo(), [envio()])
    texto = repr(filas)
    assert "PACIENTE_SINTETICO_XYZ" not in texto
    assert "EXP-999999" not in texto
    assert "CONCLUSION_SINTETICA_XYZ" not in texto
    assert "uuid-1" not in texto
    assert set(filas[0]) == {"fecha", "responsable", "servicio",
                             "actividades", "items"}


def test_limpiar_marca_solo_las_actividades_declaradas():
    filas, _ = limpiar_con(esquema_completo(), [envio(prod="a0 a2")])
    assert filas[0]["actividades"] == [1, 0, 1, 0, 0, 0]


def test_limpiar_deja_en_none_los_items_sin_responder():
    filas, _ = limpiar_con(esquema_completo(), [envio()])
    assert filas[0]["items"][0] == 1
    assert filas[0]["items"][1] == 0
    assert filas[0]["items"][2] is None


def test_limpiar_cuenta_pacientes_distintos_sin_publicarlos():
    envios = [envio(expediente="A"), envio(expediente="A"), envio(expediente="B")]
    filas, pacientes = limpiar_con(esquema_completo(), envios)
    assert pacientes == 2
    assert "'A'" not in repr(filas)


def test_limpiar_rechaza_un_valor_desconocido_en_un_item():
    with pytest.raises(kobo.KoboError, match="QUIZÁS"):
        limpiar_con(esquema_completo(), [envio(i0="QUIZÁS")])


def test_limpiar_rechaza_una_fecha_ilegible():
    with pytest.raises(kobo.KoboError, match="ayer"):
        limpiar_con(esquema_completo(), [envio(fecha="ayer")])


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
