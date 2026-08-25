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
