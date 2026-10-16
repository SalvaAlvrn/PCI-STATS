"""Pruebas de la parte pura del Apps Script de indicadores.

El `.gs` no corre en CI —necesita SpreadsheetApp—, pero sus validaciones son
JavaScript sin dependencias: el archivo solo declara constantes y funciones,
así que node lo puede cargar entero y llamar a las que no tocan Google.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import indicadores

GS = Path(__file__).resolve().parent.parent / "apps_script" / "indicadores.gs"

requiere_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="requiere node")


def ejecutar(expresion):
    guion = f"{GS.read_text(encoding='utf-8')}\nconsole.log(JSON.stringify({expresion}));\n"
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, encoding="utf-8")
    if salida.returncode != 0:
        raise AssertionError(f"node falló:\n{salida.stderr}")
    return json.loads(salida.stdout)


def peticion(**cambios):
    cuerpo = {"clave": "x", "anio": 2026, "actualizado": "",
              "valores": [{"mes": 8, "indicador": "navm", "n": 8, "d": 559}],
              "metas": [{"indicador": "navm", "meta": 10}]}
    cuerpo.update(cambios)
    return json.dumps(cuerpo)


def test_los_ids_del_script_son_los_del_manifiesto():
    ids = re.search(r"const INDICADORES = \[(.*?)\];",
                    GS.read_text(encoding="utf-8"), re.S)
    assert ids, "indicadores.gs ya no declara const INDICADORES = [...]"
    assert re.findall(r"'([a-z_]+)'", ids[1]) == indicadores.IDS


@requiere_node
def test_una_peticion_correcta_no_tiene_error():
    assert ejecutar(f"validarPeticion({peticion()})") is None


@requiere_node
def test_valores_y_metas_vacios_son_validos():
    assert ejecutar(
        f"validarPeticion({peticion(valores=[{'mes': 1, 'indicador': 'navm', 'n': None, 'd': None}], metas=[])})"
    ) is None


@requiere_node
@pytest.mark.parametrize("cambios, motivo", [
    ({"anio": 2019}, "Año"),
    ({"anio": 2026.5}, "Año"),
    ({"valores": [{"mes": 13, "indicador": "navm", "n": 1, "d": 2}]}, "Mes"),
    ({"valores": [{"mes": 1, "indicador": "navmi", "n": 1, "d": 2}]}, "desconocido"),
    ({"valores": [{"mes": 1, "indicador": "navm", "n": -1, "d": 2}]}, "no válido"),
    ({"valores": [{"mes": 1, "indicador": "navm", "n": "8", "d": 2}]}, "no válido"),
    ({"valores": [{"mes": 1, "indicador": "navm", "n": 1, "d": 2},
                  {"mes": 1, "indicador": "navm", "n": 3, "d": 4}]}, "Repetido"),
    ({"metas": [{"indicador": "navm", "meta": None}]}, "Meta"),
    ({"metas": [{"indicador": "navm", "meta": -3}]}, "Meta"),
    ({"metas": "nada"}, "Faltan"),
])
def test_validar_peticion_rechaza(cambios, motivo):
    error = ejecutar(f"validarPeticion({peticion(**cambios)})")
    assert error and motivo in error


@requiere_node
def test_un_anio_nunca_guardado_no_es_conflicto():
    assert ejecutar("hayConflicto({}, 2026, '')") is False


@requiere_node
def test_misma_marca_no_es_conflicto_y_otra_si():
    marca = "2026-10-16T12:00:00.000Z"
    assert ejecutar(f"hayConflicto({{'2026': '{marca}'}}, 2026, '{marca}')") is False
    assert ejecutar(f"hayConflicto({{'2026': '{marca}'}}, 2026, '')") is True
    assert ejecutar(f"hayConflicto({{}}, 2026, '{marca}')") is True
