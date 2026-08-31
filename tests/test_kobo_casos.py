"""Pruebas del formulario de casos de IAAS confirmados.

El esquema falso reproduce lo que hace peligroso al formulario real: la
etiqueta «Unidad/servicio» aparece dos veces —ubicación del paciente y lugar
de origen de la IAAS— con listas de opciones distintas.
"""

from unittest.mock import patch

import pytest

import kobo


def esquema_casos():
    return {
        "content": {
            "survey": [
                {"type": "select_one", "$autoname": "Definici_n_de_caso",
                 "$xpath": "Definici_n_de_caso", "label": ["Definición de caso"],
                 "select_from_list_name": "def"},
                {"type": "begin_group", "name": "group_lq1yf10",
                 "label": ["Datos del paciente"]},
                {"type": "text", "$autoname": "Nombre_del_paciente",
                 "$xpath": "group_lq1yf10/Nombre_del_paciente",
                 "label": ["Nombre del paciente"]},
                {"type": "text", "$autoname": "Expediente",
                 "$xpath": "group_lq1yf10/Expediente", "label": ["Expediente"]},
                {"type": "date", "$autoname": "Fecha_de_notificaci_n",
                 "$xpath": "group_lq1yf10/Fecha_de_notificaci_n",
                 "label": ["Fecha de notificación"]},
                {"type": "end_group"},
                {"type": "begin_group", "name": "ubicacion_paciente",
                 "label": ["Ubicación del paciente"]},
                {"type": "select_one", "$autoname": "Ubi1",
                 "$xpath": "ubicacion_paciente/Ubi1", "label": ["Unidad/servicio"],
                 "select_from_list_name": "unidades"},
                {"type": "select_one", "$autoname": "Ubi3",
                 "$xpath": "ubicacion_paciente/Ubi3", "label": ["Hospitalizaciones"],
                 "select_from_list_name": "hosp"},
                {"type": "select_one", "$autoname": "Ubi4",
                 "$xpath": "ubicacion_paciente/Ubi4",
                 "label": ["Unidad de Cuidados Intensivos"],
                 "select_from_list_name": "uci"},
                {"type": "end_group"},
                {"type": "begin_group", "name": "origen_iaas_intrahospitalario",
                 "label": ["Lugar de origen IAAS"]},
                # Misma etiqueta que Ubi1, otra pregunta: por eso este módulo
                # mapea por nombre y no por etiqueta.
                {"type": "select_one", "$autoname": "Unidad_servicio",
                 "$xpath": "origen_iaas_intrahospitalario/Unidad_servicio",
                 "label": ["Unidad/servicio"], "select_from_list_name": "unidades"},
                {"type": "end_group"},
            ],
            "choices": [
                {"list_name": "def", "name": "sospechoso", "label": ["Sospechoso"]},
                {"list_name": "def", "name": "confirmado", "label": ["Confirmado"]},
                {"list_name": "def", "name": "no_iaas", "label": ["No IAAS"]},
                {"list_name": "unidades", "name": "ubi1.2",
                 "label": ["Hospitalización Medicina Interna"]},
                {"list_name": "unidades", "name": "ubi1.4",
                 "label": ["Unidad de Cuidados Intensivos"]},
                {"list_name": "hosp", "name": "h1", "label": ["Pabellón histórico 1"]},
                {"list_name": "uci", "name": "u1", "label": ["UCI General"]},
            ],
        }
    }


def caso(definicion="confirmado", fecha="2026-07-01", unidad="ubi1.2",
         hosp="h1", uci=None, origen="ubi1.4"):
    envio = {
        "Definici_n_de_caso": definicion,
        "group_lq1yf10/Fecha_de_notificaci_n": fecha,
        "group_lq1yf10/Nombre_del_paciente": "PACIENTE_SINTETICO_XYZ",
        "group_lq1yf10/Expediente": "EXP-999999",
        "ubicacion_paciente/Ubi1": unidad,
        "origen_iaas_intrahospitalario/Unidad_servicio": origen,
    }
    if hosp:
        envio["ubicacion_paciente/Ubi3"] = hosp
    if uci:
        envio["ubicacion_paciente/Ubi4"] = uci
    return envio


def construir_con(envios, esquema=None):
    esquema = esquema or esquema_casos()
    with patch("kobo.descargar", return_value=(esquema, envios)):
        return kobo.construir_casos("t0ken")


def test_mapa_por_nombre_distingue_dos_preguntas_con_la_misma_etiqueta():
    mapa = kobo.mapa_por_nombre(esquema_casos())
    assert mapa["Ubi1"]["ruta"] == "ubicacion_paciente/Ubi1"
    assert (mapa["Unidad_servicio"]["ruta"]
            == "origen_iaas_intrahospitalario/Unidad_servicio")


def test_mapa_por_nombre_guarda_la_lista_de_opciones():
    mapa = kobo.mapa_por_nombre(esquema_casos())
    assert mapa["Ubi1"]["lista"] == "unidades"


def test_validar_casos_nombra_la_pregunta_que_falta():
    esquema = esquema_casos()
    esquema["content"]["survey"] = [
        c for c in esquema["content"]["survey"]
        if c.get("$autoname") != "Ubi1"
    ]
    with pytest.raises(kobo.KoboError, match="Ubi1"):
        kobo.validar_casos(esquema)


def test_validar_casos_exige_la_opcion_confirmado():
    esquema = esquema_casos()
    esquema["content"]["choices"] = [
        c for c in esquema["content"]["choices"]
        if c["name"] != "confirmado"
    ]
    with pytest.raises(kobo.KoboError, match="Confirmado"):
        kobo.validar_casos(esquema)


def test_solo_cuenta_los_casos_confirmados():
    data = construir_con([caso(), caso(definicion="sospechoso"),
                          caso(definicion="no_iaas")])
    assert data["meta"]["casos"] == 1


def test_publica_la_etiqueta_de_la_unidad_no_el_nombre_de_la_opcion():
    data = construir_con([caso()])
    assert data["dims"]["unidad"] == ["Hospitalización Medicina Interna"]


def test_el_subservicio_sale_de_la_pregunta_que_esta_contestada():
    data = construir_con([caso(hosp=None, unidad="ubi1.4", uci="u1")])
    assert data["dims"]["subservicio"] == ["UCI General"]


def test_sin_subservicio_contestado_cae_a_una_categoria_visible():
    data = construir_con([caso(hosp=None)])
    assert data["dims"]["subservicio"] == [kobo.SIN_AREA]


def test_no_publica_ningun_campo_prohibido():
    data = construir_con([caso()])
    texto = repr(data)
    assert "PACIENTE_SINTETICO_XYZ" not in texto
    assert "EXP-999999" not in texto


def test_el_area_es_la_ubicacion_del_paciente_no_el_lugar_de_origen():
    """Son dos preguntas con la misma etiqueta y respuestas distintas."""
    data = construir_con([caso(unidad="ubi1.2", origen="ubi1.4")])
    assert data["dims"]["unidad"] == ["Hospitalización Medicina Interna"]


def test_ordena_las_dimensiones_alfabeticamente():
    data = construir_con([caso(unidad="ubi1.4", hosp=None, uci="u1"), caso()])
    assert data["dims"]["unidad"] == ["Hospitalización Medicina Interna",
                                      "Unidad de Cuidados Intensivos"]


def test_deriva_el_dia_desde_epoch():
    data = construir_con([caso(fecha="1970-01-11")])
    assert data["rows"]["dia"] == [10]
    assert data["meta"]["dia_min"] == 10
    assert data["meta"]["dia_max"] == 10


def test_acepta_una_fecha_con_hora():
    data = construir_con([caso(fecha="2026-07-01T08:30:00.000-06:00")])
    assert data["meta"]["casos"] == 1


def test_rechaza_una_fecha_ilegible():
    with pytest.raises(kobo.KoboError, match="ayer"):
        construir_con([caso(fecha="ayer")])


def test_sin_envios_no_revienta():
    data = construir_con([])
    assert data["meta"]["casos"] == 0
    assert data["dims"]["unidad"] == []


def test_falla_si_hay_envios_pero_ninguno_confirmado():
    """Cero confirmados sobre envíos que existen es una lista rota, no un dato.

    Sin esta guarda el apartado publicaría un cero creíble el día que alguien
    rehaga las opciones de «Definición de caso» en Kobo.
    """
    with pytest.raises(kobo.KoboError, match="Confirmado"):
        construir_con([caso(definicion="sospechoso"),
                       caso(definicion="no_iaas")])
