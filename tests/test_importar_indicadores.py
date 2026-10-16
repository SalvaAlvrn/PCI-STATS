"""Pruebas de la importación única de la Hoja1 del Excel de indicadores."""

import csv

import openpyxl
import pytest

import indicadores
from scripts import importar_indicadores as imp


def excel(tmp_path):
    """La forma de la Hoja1 real: meses en la fila 1 cada tres columnas, N/D/T
    en la fila 2, un indicador por fila desde la 3 y la meta en la columna W."""
    libro = openpyxl.Workbook()
    h = libro.active
    h.title = "Hoja1"
    h["A1"], h["B1"], h["E1"], h["W1"] = "KPI", "Junio", "Julio", "Meta "
    for col, letra in zip("BCDEFG", "NDTNDT"):
        h[f"{col}2"] = letra
    h["A3"], h["D3"], h["E3"], h["G3"], h["W3"] = "Incidencia de IAAS", 1.6, 10, 1.5, 15
    h["A4"], h["E4"], h["F4"], h["G4"] = ("Densidad de Incidencia de IAAS", 12,
                                          9939, "=E4/F4*1000")
    ruta = tmp_path / "ind.xlsx"
    libro.save(ruta)
    return ruta


def test_las_filas_de_la_hoja1_apuntan_a_ids_del_manifiesto():
    assert set(imp.FILAS.values()) <= set(indicadores.IDS)
    assert len(imp.FILAS) == 9


def test_leer_importa_n_y_d_y_la_meta(tmp_path):
    valores, metas, _ = imp.leer(excel(tmp_path), 2026)
    assert valores == [
        {"ANIO": 2026, "MES": 7, "INDICADOR": "incidencia_iaas",
         "NUMERADOR": 10, "DENOMINADOR": ""},
        {"ANIO": 2026, "MES": 7, "INDICADOR": "densidad_iaas",
         "NUMERADOR": 12, "DENOMINADOR": 9939},
    ]
    assert metas == [{"ANIO": 2026, "INDICADOR": "incidencia_iaas", "META": 15}]


def test_leer_avisa_de_las_t_sin_n_o_d(tmp_path):
    _, _, avisos = imp.leer(excel(tmp_path), 2026)
    assert any("incidencia_iaas" in a and "mes 6" in a for a in avisos)
    assert any("incidencia_iaas" in a and "mes 7" in a for a in avisos)
    assert not any("densidad_iaas" in a for a in avisos)


def test_leer_falla_con_una_fila_desconocida(tmp_path):
    ruta = excel(tmp_path)
    libro = openpyxl.load_workbook(ruta)
    libro["Hoja1"]["A5"] = "Indicador inventado"
    libro.save(ruta)
    with pytest.raises(SystemExit, match="Indicador inventado"):
        imp.leer(ruta, 2026)


def test_escribir_deja_un_csv_por_pestana_con_sus_cabeceras(tmp_path):
    valores, metas, _ = imp.leer(excel(tmp_path), 2026)
    imp.escribir(valores, metas, tmp_path)
    with open(tmp_path / "VALORES.csv", encoding="utf-8") as f:
        filas = list(csv.reader(f))
    assert filas[0] == indicadores.HOJAS["VALORES"]
    assert len(filas) == 3
    with open(tmp_path / "METAS.csv", encoding="utf-8") as f:
        assert next(csv.reader(f)) == indicadores.HOJAS["METAS"]
