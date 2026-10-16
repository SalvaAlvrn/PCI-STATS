"""Pruebas de `mod-indicadores`, el cálculo y la validación de la cuadrícula.

El bloque vive en `template.html` y se extrae tal cual, como en
`tests/test_vigilancia_js.py`, para que la prueba no se quede atrás del
template.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parent.parent / "template.html"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="requiere node para ejecutar el módulo")

IND = [{"id": "incidencia_iaas", "k": 100}, {"id": "navm", "k": 1000}]


def ejecutar(expresion, datos=None):
    html = TEMPLATE.read_text(encoding="utf-8")
    bloque = re.search(r'<script id="mod-indicadores">(.*?)</script>', html, re.S)
    assert bloque, "template.html ya no trae el bloque «mod-indicadores»"
    guion = (f"{bloque[1]}\nconst m = indicadoresMod;\n"
             f"const datos = {json.dumps(datos)};\n"
             f"console.log(JSON.stringify({expresion}));\n")
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, encoding="utf-8")
    if salida.returncode != 0:
        raise AssertionError(f"node falló:\n{salida.stderr}")
    return json.loads(salida.stdout)


def datos(valores=(), metas=(), control=None):
    return {"indicadores": IND, "valores": list(valores),
            "metas": list(metas), "control": control or {}}


def test_tasa_es_n_entre_d_por_k():
    assert ejecutar("m.tasa(12, 11099, 100)") == pytest.approx(0.10812, rel=1e-3)


@pytest.mark.parametrize("n, d", [("null", "10"), ("3", "null"), ("3", "0")])
def test_tasa_vacia_sin_n_sin_d_o_con_d_cero(n, d):
    assert ejecutar(f"m.tasa({n}, {d}, 100)") is None


@pytest.mark.parametrize("texto, valor", [
    ("", None), ("   ", None), ("12", 12), (" 12 ", 12), ("1,5", 1.5),
    ("1.5", 1.5), ("0", 0)])
def test_validar_acepta(texto, valor):
    assert ejecutar(f"m.validar({json.dumps(texto)})") == {"ok": True, "valor": valor}


@pytest.mark.parametrize("texto", ["-2", "abc", "1.234,5", "1e3", "1,2,3"])
def test_validar_rechaza(texto):
    assert ejecutar(f"m.validar({json.dumps(texto)}).ok") is False


def test_estado_meta_es_un_tope():
    assert ejecutar("[m.estadoMeta(2, 1.5), m.estadoMeta(1.5, 1.5), "
                    "m.estadoMeta(1, 1.5), m.estadoMeta(null, 1.5), "
                    "m.estadoMeta(2, null)]") == ["sobre", "dentro", "dentro", None, None]


def test_anios_junta_los_que_tienen_datos_y_el_actual():
    d = datos(valores=[{"anio": 2025, "mes": 1, "indicador": "navm", "n": 1, "d": 2}],
              metas=[{"anio": 2027, "indicador": "navm", "meta": 1}])
    assert ejecutar("m.anios(datos, 2026)", d) == [2025, 2026, 2027]


def test_tabla_anio_calcula_t_y_compara_con_la_meta():
    d = datos(valores=[{"anio": 2026, "mes": 8, "indicador": "incidencia_iaas",
                        "n": 3, "d": 100}],
              metas=[{"anio": 2026, "indicador": "incidencia_iaas", "meta": 2}])
    fila = ejecutar("m.tablaAnio(datos, 2026)[0]", d)
    assert fila["meta"] == 2
    assert len(fila["meses"]) == 12
    assert fila["meses"][7] == {"n": 3, "d": 100, "t": 3, "estado": "sobre"}
    assert fila["meses"][0] == {"n": None, "d": None, "t": None, "estado": None}


def test_borrador_y_validacion_ida_y_vuelta():
    d = datos(valores=[{"anio": 2026, "mes": 8, "indicador": "navm", "n": 8, "d": 559}],
              metas=[{"anio": 2026, "indicador": "navm", "meta": 1.5}])
    r = ejecutar("m.validarBorrador(m.borradorDeAnio(datos, 2026))", d)
    assert r == {"errores": [],
                 "valores": [{"mes": 8, "indicador": "navm", "n": 8, "d": 559}],
                 "metas": [{"indicador": "navm", "meta": 1.5}]}


def test_validar_borrador_marca_cada_celda_mal_escrita():
    r = ejecutar("""(() => {
        const b = m.borradorDeAnio(datos, 2026);
        b.valores.navm[0] = {n: '-1', d: '10'};
        b.valores.navm[1] = {n: '2', d: 'abc'};
        b.metas.navm = 'x';
        return m.validarBorrador(b);
    })()""", datos())
    assert [(e["indicador"], e["mes"], e["campo"]) for e in r["errores"]] == [
        ("navm", 1, "n"), ("navm", 2, "d"), ("navm", None, "meta")]


def test_validar_borrador_omite_los_meses_completamente_vacios():
    r = ejecutar("m.validarBorrador(m.borradorDeAnio(datos, 2026))", datos())
    assert r["valores"] == [] and r["metas"] == []


def test_reemplazar_anio_solo_toca_ese_anio():
    d = datos(valores=[{"anio": 2025, "mes": 1, "indicador": "navm", "n": 1, "d": 2},
                       {"anio": 2026, "mes": 1, "indicador": "navm", "n": 9, "d": 9}],
              control={"2025": "a"})
    r = ejecutar("m.reemplazarAnio(datos, 2026, "
                 "[{mes: 2, indicador: 'navm', n: 3, d: 4}], [], 'b')", d)
    assert r["valores"] == [
        {"anio": 2025, "mes": 1, "indicador": "navm", "n": 1, "d": 2},
        {"anio": 2026, "mes": 2, "indicador": "navm", "n": 3, "d": 4}]
    assert r["control"] == {"2025": "a", "2026": "b"}
    assert r["indicadores"] == IND


def test_el_borrador_guarda_la_marca_del_anio_que_se_empezo_a_editar():
    """Si la lectura en vivo llega con la cuadrícula abierta, el guardado debe
    seguir enviando la marca de los datos sobre los que se escribió: con la
    nueva, el script no vería el conflicto y pisaría los cambios de otro."""
    d = datos(control={"2026": "copia"})
    assert ejecutar("m.borradorDeAnio(datos, 2026).actualizado", d) == "copia"
    assert ejecutar("m.borradorDeAnio(datos, 2025).actualizado", d) == ""
