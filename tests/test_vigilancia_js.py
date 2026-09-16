"""Pruebas de `cuota` y `confirmacion`, las dos métricas sin denominador.

El módulo `mod-vigilancia` vive dentro de `template.html` y se ejecuta en el
navegador. Aquí se extrae ese bloque tal cual y se corre con node, en vez de
copiarlo a un `test_*.html` como hizo `tests/test_agg.html`: una copia a mano
se queda atrás en cuanto alguien toca el template y nadie se entera.

Las dos funciones publican números que se parecen a una tasa de incidencia sin
serlo —no hay denominador de pacientes en ninguna parte del libro— así que lo
que más se prueba aquí es cuándo se niegan a dar un número: servicios con pocos
casos, meses en curso y series demasiado cortas.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parent.parent / "template.html"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="requiere node para ejecutar el módulo"
)


def _modulo(nombre="mod-vigilancia"):
    """El cuerpo de un bloque `<script id=...>` de la plantilla."""
    html = TEMPLATE.read_text(encoding="utf-8")
    bloque = re.search(
        rf'<script id="{nombre}">(.*?)</script>', html, re.S)
    assert bloque, f"template.html ya no trae el bloque «{nombre}»"
    return bloque[1]


def ejecutar(dataset, expresion):
    """Evalúa `expresion` sobre `crearVigilancia(dataset)` y devuelve el JSON.

    `vig` es el dataset y `v` el módulo ya construido, que es como los llama
    el propio dashboard.
    """
    guion = (
        f"{_modulo()}\n"
        f"const vig = {json.dumps(dataset)};\n"
        "const v = crearVigilancia(vig);\n"
        f"console.log(JSON.stringify({expresion}));\n"
    )
    salida = subprocess.run(
        ["node", "-e", guion], capture_output=True, text=True, encoding="utf-8")
    if salida.returncode != 0:
        raise AssertionError(f"node falló:\n{salida.stderr}")
    return json.loads(salida.stdout)


CONFIRMADO = "Caso confirmado"
SOSPECHOSO = "Caso sospechoso"
NO_IAAS = "No IAAS"
SIN_DATO = "(Sin registrar)"


def dataset(casos, meses):
    """Dataset mínimo con las dimensiones que las dos funciones necesitan.

    `casos` es una lista de (servicio, procedimiento, definicion, mes). El
    resto de columnas que el módulo espera van a cero: no intervienen en
    `cuota` ni en `confirmacion`, pero `crearVigilancia` las lee al construirse.
    """
    servicios = sorted({c[0] for c in casos})
    procedimientos = sorted({c[1] for c in casos})
    definiciones = [CONFIRMADO, SOSPECHOSO, NO_IAAS]
    n = len(casos)
    indice = lambda lista, v: lista.index(v)
    return {
        "dims": {
            "servicio": servicios,
            "procedimiento": procedimientos,
            "definicion": definiciones,
            "mes": meses,
            "ubicacion": [SIN_DATO], "diagnostico": [SIN_DATO],
            "origen": [SIN_DATO], "condicion": [SIN_DATO], "sexo": [SIN_DATO],
            "vigepes": [SIN_DATO], "edad": [SIN_DATO], "fuente": [SIN_DATO],
            "herida": [SIN_DATO], "intervencion": [SIN_DATO],
            "semana": [SIN_DATO],
            "microorganismo": [], "dispositivo": [], "causa": [], "cronica": [],
        },
        "rows": {
            "servicio": [indice(servicios, c[0]) for c in casos],
            "procedimiento": [indice(procedimientos, c[1]) for c in casos],
            "definicion": [indice(definiciones, c[2]) for c in casos],
            "mes": [indice(meses, c[3]) for c in casos],
            "ubicacion": [0] * n, "diagnostico": [0] * n, "origen": [0] * n,
            "condicion": [0] * n, "sexo": [0] * n, "vigepes": [0] * n,
            "edad": [0] * n, "fuente": [0] * n, "herida": [0] * n,
            "intervencion": [0] * n, "semana": [0] * n,
            "microorganismo": [], "dispositivo": [], "causa": [], "cronica": [],
            "dispositivo_dias": [], "bundle_si": [], "bundle_no": [],
            "dia": [None] * n,
            "investigado": [0] * n, "cerrado": [0] * n,
            "deteccion": [None] * n, "a_investigacion": [None] * n,
            "a_vigepes": [None] * n,
        },
        "etiquetas": {
            "confirmado": CONFIRMADO, "sospechoso": SOSPECHOSO,
            "no_iaas": NO_IAAS, "sin_dato": SIN_DATO, "invasivos": [],
        },
        "meta": {"casos": n},
    }


def caso(servicio, definicion=CONFIRMADO, mes="2026-08", procedimiento=SIN_DATO):
    return (servicio, procedimiento, definicion, mes)


TODAS = "[...vig.rows.dia.keys()]"


# ---------------------------------------------------------------------------
# Tasa de confirmación: confirmados sobre notificados de la misma etiqueta
# ---------------------------------------------------------------------------

def test_confirmacion_cuenta_notificados_y_confirmados_por_servicio():
    datos = dataset(
        [caso("UCI"), caso("UCI"), caso("UCI", SOSPECHOSO),
         caso("Cirugía"), caso("Cirugía", NO_IAAS)],
        ["2026-08"])
    salida = ejecutar(datos, f"v.confirmacion({TODAS}, 'servicio')")
    por_label = {e["label"]: e for e in salida}
    assert por_label["UCI"]["notificados"] == 3
    assert por_label["UCI"]["confirmados"] == 2
    assert por_label["UCI"]["tasa"] == pytest.approx(2 / 3)
    assert por_label["Cirugía"]["tasa"] == pytest.approx(0.5)


def test_confirmacion_tasa_cero_es_cero_y_no_ausencia_de_dato():
    """Un servicio que notifica y no confirma nada vale 0, no null."""
    datos = dataset(
        [caso("Emergencia", NO_IAAS), caso("Emergencia", SOSPECHOSO)],
        ["2026-08"])
    salida = ejecutar(datos, f"v.confirmacion({TODAS}, 'servicio')")
    assert salida[0]["tasa"] == 0


def test_confirmacion_marca_las_etiquetas_bajo_el_minimo():
    """Con menos de 5 notificados el porcentaje engaña: 1 de 1 no es 100%."""
    datos = dataset(
        [caso("UCI") for _ in range(5)] + [caso("Nefrología")],
        ["2026-08"])
    salida = ejecutar(datos, f"v.confirmacion({TODAS}, 'servicio')")
    por_label = {e["label"]: e for e in salida}
    assert por_label["UCI"]["suficiente"] is True
    assert por_label["Nefrología"]["suficiente"] is False


def test_confirmacion_ordena_las_etiquetas_escasas_al_final():
    datos = dataset(
        [caso("Nefrología")] + [caso("UCI", NO_IAAS) for _ in range(5)],
        ["2026-08"])
    salida = ejecutar(datos, f"v.confirmacion({TODAS}, 'servicio')")
    # UCI tiene tasa 0 y Nefrología 100%, pero Nefrología no llega al mínimo.
    assert [e["label"] for e in salida] == ["UCI", "Nefrología"]


def test_confirmacion_funciona_igual_sobre_procedimiento():
    datos = dataset(
        [caso("UCI", procedimiento="Laparotomía"),
         caso("UCI", NO_IAAS, procedimiento="Laparotomía"),
         caso("Cirugía", procedimiento="Osteosíntesis")],
        ["2026-08"])
    salida = ejecutar(datos, f"v.confirmacion({TODAS}, 'procedimiento')")
    por_label = {e["label"]: e for e in salida}
    assert por_label["Laparotomía"]["notificados"] == 2
    assert por_label["Osteosíntesis"]["confirmados"] == 1


def test_confirmacion_sin_casos_no_divide_por_cero():
    datos = dataset([caso("UCI")], ["2026-08"])
    assert ejecutar(datos, "v.confirmacion([], 'servicio')") == []


def test_confirmacion_deja_fuera_la_etiqueta_sin_registrar():
    """«(Sin registrar)» no es una categoría que se pueda comparar.

    En procedimiento son los casos que no fueron quirúrgicos —tres de cada
    cuatro— y encabezarían la tabla como si «no operado» fuese un tipo de
    operación con su propia tasa.
    """
    datos = dataset(
        [caso("UCI", procedimiento="Laparotomía"),
         caso("UCI", NO_IAAS, procedimiento="Laparotomía")] +
        [caso("UCI", procedimiento=SIN_DATO) for _ in range(20)],
        ["2026-08"])
    salida = ejecutar(datos, f"v.confirmacion({TODAS}, 'procedimiento')")
    assert [e["label"] for e in salida] == ["Laparotomía"]


def test_cuota_deja_fuera_la_etiqueta_sin_registrar():
    casos = []
    for mes in ("2026-06", "2026-07", "2026-08"):
        casos += [caso("UCI", mes=mes) for _ in range(6)]
        casos += [caso(SIN_DATO, mes=mes) for _ in range(6)]
    salida = ejecutar(dataset(casos, ["2026-06", "2026-07", "2026-08"]),
                      f"v.cuota({TODAS}, 'servicio')")
    assert [e["label"] for e in salida] == ["UCI"]
    # La cuota sigue calculándose sobre todos los confirmados del mes: UCI
    # aporta 6 de los 12, no 6 de 6.
    assert salida[0]["cuota"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Cuota del mes frente a la media de los meses anteriores
# ---------------------------------------------------------------------------

def _tres_meses():
    """UCI estable en el 25%; Medicina Interna se dispara en agosto.

    Junio y julio: 24 confirmados cada uno —6 de UCI (25%), 6 de Medicina
    (25%) y 12 de Cirugía (50%)—. Agosto: 24 confirmados, 6 de UCI (25%), 18
    de Medicina (75%) y ninguno de Cirugía.

    Todos los servicios pasan el mínimo de 5 casos salvo Cirugía en agosto,
    que cae a cero: los recuentos están por encima del umbral a propósito,
    para que lo que se pruebe aquí sea el cálculo y no el silencio.
    """
    casos = []
    for mes in ("2026-06", "2026-07"):
        casos += [caso("UCI", mes=mes) for _ in range(6)]
        casos += [caso("Medicina Interna", mes=mes) for _ in range(6)]
        casos += [caso("Cirugía", mes=mes) for _ in range(12)]
    casos += [caso("UCI", mes="2026-08") for _ in range(6)]
    casos += [caso("Medicina Interna", mes="2026-08") for _ in range(18)]
    return dataset(casos, ["2026-06", "2026-07", "2026-08"])


def test_cuota_compara_el_ultimo_mes_con_la_media_de_los_previos():
    salida = ejecutar(_tres_meses(), f"v.cuota({TODAS}, 'servicio')")
    por_label = {e["label"]: e for e in salida}
    medicina = por_label["Medicina Interna"]
    assert medicina["casos"] == 18
    assert medicina["cuota"] == pytest.approx(0.75)
    assert medicina["habitual"] == pytest.approx(0.25)
    assert medicina["delta"] == pytest.approx(0.5)


def test_cuota_de_un_servicio_estable_no_tiene_delta():
    salida = ejecutar(_tres_meses(), f"v.cuota({TODAS}, 'servicio')")
    por_label = {e["label"]: e for e in salida}
    assert por_label["UCI"]["delta"] == pytest.approx(0)


def test_cuota_de_un_servicio_que_desaparece_da_cuota_cero():
    """Cirugía notificó en junio y julio y nada en agosto: es una caída real."""
    salida = ejecutar(_tres_meses(), f"v.cuota({TODAS}, 'servicio')")
    por_label = {e["label"]: e for e in salida}
    assert por_label["Cirugía"]["casos"] == 0
    assert por_label["Cirugía"]["cuota"] == 0
    assert por_label["Cirugía"]["delta"] == pytest.approx(-0.5)


def test_cuota_calla_la_senal_si_el_servicio_no_llega_al_minimo():
    """Con 4 casos en el mes, la cuota baila demasiado para leerla como señal."""
    casos = []
    for mes in ("2026-06", "2026-07"):
        casos += [caso("UCI", mes=mes) for _ in range(5)]
    casos += [caso("UCI", mes="2026-08") for _ in range(4)]
    salida = ejecutar(dataset(casos, ["2026-06", "2026-07", "2026-08"]),
                      f"v.cuota({TODAS}, 'servicio')")
    assert salida[0]["casos"] == 4
    assert salida[0]["suficiente"] is False
    assert salida[0]["delta"] is None


def test_cuota_calla_la_senal_con_menos_de_dos_meses_previos():
    """Un solo mes anterior no es «lo habitual» de nadie."""
    casos = [caso("UCI", mes="2026-07") for _ in range(6)]
    casos += [caso("UCI", mes="2026-08") for _ in range(6)]
    salida = ejecutar(dataset(casos, ["2026-07", "2026-08"]),
                      f"v.cuota({TODAS}, 'servicio')")
    assert salida[0]["delta"] is None
    assert salida[0]["habitual"] is None


def test_cuota_sin_meses_previos_devuelve_lista_vacia():
    datos = dataset([caso("UCI") for _ in range(6)], ["2026-08"])
    assert ejecutar(datos, f"v.cuota({TODAS}, 'servicio')") == []


def test_cuota_solo_mira_los_confirmados():
    """Los sospechosos y los descartados no entran en el reparto del mes."""
    casos = []
    for mes in ("2026-06", "2026-07"):
        casos += [caso("UCI", mes=mes) for _ in range(5)]
        casos += [caso("Cirugía", mes=mes) for _ in range(5)]
    casos += [caso("UCI", mes="2026-08") for _ in range(5)]
    casos += [caso("Cirugía", NO_IAAS, mes="2026-08") for _ in range(20)]
    salida = ejecutar(dataset(casos, ["2026-06", "2026-07", "2026-08"]),
                      f"v.cuota({TODAS}, 'servicio')")
    por_label = {e["label"]: e for e in salida}
    assert por_label["UCI"]["cuota"] == 1
    assert por_label["Cirugía"]["casos"] == 0


def test_cuota_ignora_los_casos_sin_mes():
    """«(Sin registrar)» no es un periodo: no puede ser el último mes."""
    casos = []
    for mes in ("2026-06", "2026-07", "2026-08"):
        casos += [caso("UCI", mes=mes) for _ in range(5)]
    casos += [caso("UCI", mes=SIN_DATO) for _ in range(50)]
    salida = ejecutar(dataset(casos, ["2026-06", "2026-07", "2026-08", SIN_DATO]),
                      f"v.cuota({TODAS}, 'servicio')")
    assert salida[0]["mes"] == "2026-08"
    assert salida[0]["casos"] == 5


def test_cuota_avisa_de_que_el_mes_en_curso_va_a_medias():
    """Igual que `variacion`: un mes incompleto siempre parece una caída."""
    from datetime import date
    hoy = date.today().strftime("%Y-%m")
    casos = [caso("UCI", mes="2026-01") for _ in range(6)]
    casos += [caso("UCI", mes="2026-02") for _ in range(6)]
    casos += [caso("UCI", mes=hoy) for _ in range(6)]
    salida = ejecutar(dataset(casos, ["2026-01", "2026-02", hoy]),
                      f"v.cuota({TODAS}, 'servicio')")
    assert salida[0]["enCurso"] is True


def test_cuota_ordena_por_delta_descendente():
    """Lo que más se ha salido de su patrón va arriba, que es lo que se busca."""
    salida = ejecutar(_tres_meses(), f"v.cuota({TODAS}, 'servicio')")
    assert [e["label"] for e in salida][0] == "Medicina Interna"
    assert [e["label"] for e in salida][-1] == "Cirugía"
