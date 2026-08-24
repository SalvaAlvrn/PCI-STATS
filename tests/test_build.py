from pathlib import Path

import pandas as pd
import pytest

from build_dashboard import AREA_NULA, BuildError, clean, load, validate

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


def test_clean_normaliza_slug_y_respeta_los_demas(registros_ok, formularios_ok):
    limpio = clean(registros_ok, formularios_ok)
    nombres = set(limpio["RESPONSABLE"])
    assert "Ana María Pérez Gómez" in nombres
    assert "ana_mar_a_p_rez_g_mez" not in nombres
    assert "Ana Pérez" in nombres


def test_clean_rellena_areas_nulas_sin_perder_filas(registros_ok, formularios_ok):
    limpio = clean(registros_ok, formularios_ok)
    assert len(limpio) == len(registros_ok)
    assert limpio["AREA_ESPECIFICA_APLICACION"].isna().sum() == 0
    assert (limpio["AREA_ESPECIFICA_APLICACION"] == AREA_NULA).sum() == 1


def test_clean_resuelve_nombre_de_la_version_mas_reciente(
    registros_ok, formularios_ok
):
    limpio = clean(registros_ok, formularios_ok)
    f002 = limpio[limpio["ID_FORMULARIO"] == "F002"]
    assert set(f002["NOMBRE_FORMULARIO_ACTUAL"]) == {"Guantes"}


def test_clean_codifica_cumple_como_entero(registros_ok, formularios_ok):
    limpio = clean(registros_ok, formularios_ok)
    assert list(limpio["CUMPLE"]) == [1, 0, 1, -1]


def test_clean_deriva_mes_semana_y_dia(registros_ok, formularios_ok):
    limpio = clean(registros_ok, formularios_ok)
    assert list(limpio["MES"]) == ["2026-07", "2026-07", "2026-07", "2026-08"]
    assert limpio["SEMANA"].iloc[0] == "2026-W27"
    assert limpio["DIA"].iloc[0] == int(
        pd.Timestamp("2026-07-01").timestamp() // 86400
    )


def test_clean_sobre_el_excel_real_conserva_todas_las_filas():
    registros, formularios = load(XLSX)
    limpio = clean(registros, formularios)
    assert len(limpio) == 2806
    assert limpio["RESPONSABLE"].nunique() == 21
    assert limpio["ID_FORMULARIO"].nunique() == 47
    assert limpio["NOMBRE_FORMULARIO_ACTUAL"].nunique() == 47
    assert limpio["AREA_ESPECIFICA_APLICACION"].isna().sum() == 0
