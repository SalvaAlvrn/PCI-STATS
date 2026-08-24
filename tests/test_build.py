from pathlib import Path

import pandas as pd
import pytest

from build_dashboard import BuildError, load, validate

XLSX = Path(__file__).resolve().parent.parent / "SupPCI.xlsx"


def test_load_devuelve_registros_y_formularios():
    registros, formularios = load(XLSX)
    assert len(registros) == 2806
    assert len(formularios) == 76
    assert "CUMPLE_CORRECTAMENTE" in registros.columns
    assert "METODO_CUMPLIMIENTO" in formularios.columns


def test_load_archivo_inexistente_levanta_builderror():
    with pytest.raises(BuildError, match="no existe"):
        load(Path("no_tal_archivo.xlsx"))


def test_validate_acepta_datos_correctos(registros_ok, formularios_ok):
    validate(registros_ok, formularios_ok)  # no levanta


def test_validate_detecta_columna_faltante(registros_ok, formularios_ok):
    sin_columna = registros_ok.drop(columns=["CUMPLE_CORRECTAMENTE"])
    with pytest.raises(BuildError, match="CUMPLE_CORRECTAMENTE"):
        validate(sin_columna, formularios_ok)


def test_validate_rechaza_valor_desconocido_en_cumple(registros_ok, formularios_ok):
    registros_ok.loc[0, "CUMPLE_CORRECTAMENTE"] = "PARCIAL"
    with pytest.raises(BuildError, match="PARCIAL"):
        validate(registros_ok, formularios_ok)


def test_validate_rechaza_porcentaje_fuera_de_rango(registros_ok, formularios_ok):
    registros_ok.loc[0, "PORCENTAJE_CUMPLIMIENTO"] = 140
    with pytest.raises(BuildError, match="PORCENTAJE_CUMPLIMIENTO"):
        validate(registros_ok, formularios_ok)


def test_validate_rechaza_fecha_fuera_de_rango(registros_ok, formularios_ok):
    registros_ok.loc[0, "FECHA_EVENTO"] = pd.Timestamp("1999-01-01")
    with pytest.raises(BuildError, match="FECHA_EVENTO"):
        validate(registros_ok, formularios_ok)


def test_validate_avisa_de_metodo_no_soportado(registros_ok, formularios_ok):
    formularios_ok.loc[0, "METODO_CUMPLIMIENTO"] = "INFORMACION"
    with pytest.raises(BuildError, match="INFORMACION"):
        validate(registros_ok, formularios_ok)


def test_validate_rechaza_slug_desconocido(registros_ok, formularios_ok):
    registros_ok.loc[0, "RESPONSABLE"] = "pedro_nuevo_sin_mapear"
    with pytest.raises(BuildError, match="pedro_nuevo_sin_mapear"):
        validate(registros_ok, formularios_ok)


def test_validate_pasa_sobre_el_excel_real():
    registros, formularios = load(XLSX)
    validate(registros, formularios)  # no levanta
