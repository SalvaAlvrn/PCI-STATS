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
