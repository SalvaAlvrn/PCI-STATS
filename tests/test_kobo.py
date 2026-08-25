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
