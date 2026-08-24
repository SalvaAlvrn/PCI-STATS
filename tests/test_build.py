from pathlib import Path

import pandas as pd
import pytest

from build_dashboard import (
    AREA_NULA,
    BuildError,
    cargar_nombres,
    clean,
    encode,
    load,
    render_html,
    validate,
)

XLSX = Path(__file__).resolve().parent.parent / "SupPCI.xlsx"
TEMPLATE = Path(__file__).resolve().parent.parent / "template.html"
VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "chart.umd.min.js"


def test_load_devuelve_registros_y_formularios():
    registros, formularios = load(XLSX)
    assert len(registros) == 2806
    assert len(formularios) == 76
    assert "CUMPLE_CORRECTAMENTE" in registros.columns
    assert "METODO_CUMPLIMIENTO" in formularios.columns


def test_load_archivo_inexistente_levanta_builderror():
    with pytest.raises(BuildError, match="no existe"):
        load(Path("no_tal_archivo.xlsx"))


def test_validate_acepta_datos_correctos(registros_ok, formularios_ok, nombres_ok):
    validate(registros_ok, formularios_ok, nombres_ok)  # no levanta


def test_validate_detecta_columna_faltante(registros_ok, formularios_ok, nombres_ok):
    sin_columna = registros_ok.drop(columns=["CUMPLE_CORRECTAMENTE"])
    with pytest.raises(BuildError, match="CUMPLE_CORRECTAMENTE"):
        validate(sin_columna, formularios_ok, nombres_ok)


def test_validate_rechaza_valor_desconocido_en_cumple(registros_ok, formularios_ok, nombres_ok):
    registros_ok.loc[0, "CUMPLE_CORRECTAMENTE"] = "PARCIAL"
    with pytest.raises(BuildError, match="PARCIAL"):
        validate(registros_ok, formularios_ok, nombres_ok)


def test_validate_rechaza_porcentaje_fuera_de_rango(registros_ok, formularios_ok, nombres_ok):
    registros_ok.loc[0, "PORCENTAJE_CUMPLIMIENTO"] = 140
    with pytest.raises(BuildError, match="PORCENTAJE_CUMPLIMIENTO"):
        validate(registros_ok, formularios_ok, nombres_ok)


def test_validate_rechaza_fecha_fuera_de_rango(registros_ok, formularios_ok, nombres_ok):
    registros_ok.loc[0, "FECHA_EVENTO"] = pd.Timestamp("1999-01-01")
    with pytest.raises(BuildError, match="FECHA_EVENTO"):
        validate(registros_ok, formularios_ok, nombres_ok)


def test_validate_avisa_de_metodo_no_soportado(registros_ok, formularios_ok, nombres_ok):
    formularios_ok.loc[0, "METODO_CUMPLIMIENTO"] = "INFORMACION"
    with pytest.raises(BuildError, match="INFORMACION"):
        validate(registros_ok, formularios_ok, nombres_ok)


def test_validate_rechaza_nulo_en_columna_de_dimension(registros_ok, formularios_ok, nombres_ok):
    registros_ok.loc[0, "GRUPO_OCUPACIONAL"] = None
    with pytest.raises(BuildError, match="GRUPO_OCUPACIONAL"):
        validate(registros_ok, formularios_ok, nombres_ok)


def test_validate_rechaza_estado_de_validacion_desconocido(
    registros_ok, formularios_ok, nombres_ok
):
    registros_ok.loc[0, "ESTADO_VALIDACION"] = "Rechazado"
    with pytest.raises(BuildError, match="Rechazado"):
        validate(registros_ok, formularios_ok, nombres_ok)


def test_validate_rechaza_porcentaje_no_entero(registros_ok, formularios_ok, nombres_ok):
    registros_ok["PORCENTAJE_CUMPLIMIENTO"] = registros_ok[
        "PORCENTAJE_CUMPLIMIENTO"
    ].astype(float)
    registros_ok.loc[0, "PORCENTAJE_CUMPLIMIENTO"] = 92.5
    with pytest.raises(BuildError, match="PORCENTAJE_CUMPLIMIENTO"):
        validate(registros_ok, formularios_ok, nombres_ok)


def test_validate_rechaza_slug_desconocido(registros_ok, formularios_ok, nombres_ok):
    registros_ok.loc[0, "RESPONSABLE"] = "pedro_nuevo_sin_mapear"
    with pytest.raises(BuildError, match="pedro_nuevo_sin_mapear"):
        validate(registros_ok, formularios_ok, nombres_ok)


def test_validate_pasa_sobre_el_excel_real():
    registros, formularios = load(XLSX)
    validate(registros, formularios, cargar_nombres())  # no levanta


def test_clean_normaliza_slug_y_respeta_los_demas(registros_ok, formularios_ok, nombres_ok):
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    nombres = set(limpio["RESPONSABLE"])
    assert "Ana María Pérez Gómez" in nombres
    assert "ana_mar_a_p_rez_g_mez" not in nombres
    assert "Ana Pérez" in nombres


def test_clean_rellena_areas_nulas_sin_perder_filas(registros_ok, formularios_ok, nombres_ok):
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    assert len(limpio) == len(registros_ok)
    assert limpio["AREA_ESPECIFICA_APLICACION"].isna().sum() == 0
    assert (limpio["AREA_ESPECIFICA_APLICACION"] == AREA_NULA).sum() == 1


def test_clean_resuelve_nombre_de_la_version_mas_reciente(
    registros_ok, formularios_ok, nombres_ok
):
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    f002 = limpio[limpio["ID_FORMULARIO"] == "F002"]
    assert set(f002["NOMBRE_FORMULARIO_ACTUAL"]) == {"Guantes"}


def test_clean_codifica_cumple_como_entero(registros_ok, formularios_ok, nombres_ok):
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    assert list(limpio["CUMPLE"]) == [1, 0, 1, -1]


def test_clean_deriva_mes_semana_y_dia(registros_ok, formularios_ok, nombres_ok):
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    assert list(limpio["MES"]) == ["2026-07", "2026-07", "2026-07", "2026-08"]
    assert limpio["SEMANA"].iloc[0] == "2026-W27"
    assert limpio["DIA"].iloc[0] == int(
        pd.Timestamp("2026-07-01").timestamp() // 86400
    )


def test_clean_sobre_el_excel_real_conserva_todas_las_filas():
    registros, formularios = load(XLSX)
    limpio = clean(registros, formularios, cargar_nombres())
    assert len(limpio) == 2806
    assert limpio["RESPONSABLE"].nunique() == 21
    assert limpio["ID_FORMULARIO"].nunique() == 47
    assert limpio["NOMBRE_FORMULARIO_ACTUAL"].nunique() == 47
    assert limpio["AREA_ESPECIFICA_APLICACION"].isna().sum() == 0


def _tasa(serie):
    """Tasa de cumplimiento sobre los registros con dictamen."""
    con_dictamen = serie[serie.isin(["SI", "NO"])]
    return (con_dictamen == "SI").sum() / len(con_dictamen)


def test_encode_construye_dimensiones_y_filas(registros_ok, formularios_ok, nombres_ok):
    data = encode(clean(registros_ok, formularios_ok, nombres_ok), formularios_ok)
    assert data["dims"]["responsable"] == [
        "Ana María Pérez Gómez",
        "Ana Pérez",
    ]
    assert len(data["rows"]["cumple"]) == 4
    assert data["rows"]["cumple"] == [1, 0, 1, -1]
    assert data["dims"]["mes"] == ["2026-07", "2026-08"]


def test_encode_es_reversible(registros_ok, formularios_ok, nombres_ok):
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    data = encode(limpio, formularios_ok)
    decodificado = [
        data["dims"]["responsable"][i] for i in data["rows"]["responsable"]
    ]
    assert decodificado == list(limpio["RESPONSABLE"])
    decodificado_area = [data["dims"]["area"][i] for i in data["rows"]["area"]]
    assert decodificado_area == list(limpio["AREA_ESPECIFICA_APLICACION"])


def test_encode_guarda_metadatos_de_formulario(registros_ok, formularios_ok, nombres_ok):
    data = encode(clean(registros_ok, formularios_ok, nombres_ok), formularios_ok)
    assert data["forms"]["F002"]["nombre"] == "Guantes"
    assert data["forms"]["F002"]["medida"] == "Medidas estándar"


def test_encode_solo_embebe_conclusiones_de_los_que_no_cumplen(
    registros_ok, formularios_ok, nombres_ok
):
    data = encode(clean(registros_ok, formularios_ok, nombres_ok), formularios_ok)
    assert list(data["texts"]["conclusiones"]) == ["1"]
    assert data["texts"]["conclusiones"]["1"] == "Reponer jabón"


def test_encode_deja_evaluado_como_texto_plano(registros_ok, formularios_ok, nombres_ok):
    data = encode(clean(registros_ok, formularios_ok, nombres_ok), formularios_ok)
    assert data["texts"]["evaluado"] == ["Juan", "Luis", "Marta", "Rosa"]
    assert "evaluado" not in data["dims"]


def test_cifra_de_control_tasa_global():
    registros, formularios = load(XLSX)
    data = encode(clean(registros, formularios, cargar_nombres()), formularios)
    cumple = data["rows"]["cumple"]
    con_dictamen = [c for c in cumple if c >= 0]
    del_pipeline = sum(con_dictamen) / len(con_dictamen)
    de_pandas = _tasa(registros["CUMPLE_CORRECTAMENTE"])
    assert del_pipeline == pytest.approx(de_pandas)


def test_cifra_de_control_tasa_por_responsable():
    registros, formularios = load(XLSX)
    limpio = clean(registros, formularios, cargar_nombres())
    data = encode(limpio, formularios)
    dims = data["dims"]["responsable"]
    filas = data["rows"]
    for indice, nombre in enumerate(dims):
        cumple = [
            c
            for fila, c in enumerate(filas["cumple"])
            if filas["responsable"][fila] == indice and c >= 0
        ]
        esperado = _tasa(
            limpio.loc[limpio["RESPONSABLE"] == nombre, "CUMPLE_CORRECTAMENTE"]
        )
        assert sum(cumple) / len(cumple) == pytest.approx(esperado), nombre


def test_cifra_de_control_tasa_por_mes():
    registros, formularios = load(XLSX)
    limpio = clean(registros, formularios, cargar_nombres())
    data = encode(limpio, formularios)
    dims = data["dims"]["mes"]
    filas = data["rows"]
    for indice, mes in enumerate(dims):
        cumple = [
            c
            for fila, c in enumerate(filas["cumple"])
            if filas["mes"][fila] == indice and c >= 0
        ]
        esperado = _tasa(limpio.loc[limpio["MES"] == mes, "CUMPLE_CORRECTAMENTE"])
        assert sum(cumple) / len(cumple) == pytest.approx(esperado), mes


def test_render_html_produce_un_archivo_sin_urls_externas(tmp_path):
    registros, formularios = load(XLSX)
    data = encode(clean(registros, formularios, cargar_nombres()), formularios)
    salida = tmp_path / "dashboard.html"
    escritos = render_html(data, TEMPLATE, VENDOR, salida)

    html = salida.read_text(encoding="utf-8")
    assert escritos == len(html.encode("utf-8"))
    assert "/*__DATA__*/" not in html
    assert "/*__CHARTJS__*/" not in html
    assert "Chart" in html
    # "Funciona sin conexión" quiere decir que nada se descarga al abrir el
    # archivo, no que la cadena "https" no aparezca en ninguna parte. Una URL
    # dentro de un comentario — el aviso de licencia MIT de Chart.js, por
    # ejemplo — no provoca ninguna petición, y borrarla para satisfacer un
    # assert incumpliría esa licencia. Se comprueban las construcciones que
    # sí provocan una descarga.
    for atributo in ('src="http', "src='http", 'href="http', "href='http"):
        assert atributo not in html, atributo
    assert "url(http" not in html
    assert "@import" not in html


def test_render_html_embebe_los_datos_reales(tmp_path):
    # No se usa un nombre literal: este mapa es el real (nombres.json, fuera
    # del repo), así que la aserción se deriva de él en vez de citarlo, para
    # que ningún nombre real quede escrito en un archivo versionado.
    registros, formularios = load(XLSX)
    nombres = cargar_nombres()
    data = encode(clean(registros, formularios, nombres), formularios)
    salida = tmp_path / "dashboard.html"
    render_html(data, TEMPLATE, VENDOR, salida)
    html = salida.read_text(encoding="utf-8")
    slug, nombre_normalizado = next(iter(nombres.items()))
    assert nombre_normalizado in html
    assert slug not in html


def test_render_html_vendor_ausente_levanta_builderror_con_instrucciones(tmp_path):
    registros, formularios = load(XLSX)
    data = encode(clean(registros, formularios, cargar_nombres()), formularios)
    salida = tmp_path / "dashboard.html"
    vendor_inexistente = tmp_path / "no_esta" / "chart.umd.min.js"
    with pytest.raises(BuildError, match="curl"):
        render_html(data, TEMPLATE, vendor_inexistente, salida)


def test_encode_toma_nombre_version_medida_y_submedida_del_catalogo(
    registros_ok, formularios_ok, nombres_ok
):
    """Las cuatro cosas vienen de la fila de versión más alta del catálogo,

    no de la fila de versión más alta entre los registros usados: si el
    catálogo tuviera una versión que ningún registro usa todavía, el header
    del formulario debe reflejarla igual.
    """
    data = encode(clean(registros_ok, formularios_ok, nombres_ok), formularios_ok)
    esperado = formularios_ok[formularios_ok["ID_FORMULARIO"] == "F002"].sort_values(
        "VERSION_FORMULARIO"
    ).iloc[-1]
    assert data["forms"]["F002"]["nombre"] == esperado["NOMBRE_FORMULARIO"]
    assert data["forms"]["F002"]["version"] == int(esperado["VERSION_FORMULARIO"])
    assert data["forms"]["F002"]["medida"] == esperado["MEDIDA"]
    assert data["forms"]["F002"]["submedida"] == esperado["SUBMEDIDA"]


def test_cargar_nombres_lee_el_mapa(tmp_path):
    ruta = tmp_path / "nombres.json"
    ruta.write_text('{"ana_p_rez": "Ana Pérez"}', encoding="utf-8")
    assert cargar_nombres(ruta) == {"ana_p_rez": "Ana Pérez"}


def test_cargar_nombres_sin_archivo_levanta_builderror(tmp_path):
    with pytest.raises(BuildError, match="nombres.json"):
        cargar_nombres(tmp_path / "no_existe.json")


def test_cargar_nombres_json_invalido_levanta_builderror(tmp_path):
    ruta = tmp_path / "nombres.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    with pytest.raises(BuildError, match="no es un JSON válido"):
        cargar_nombres(ruta)


def test_cargar_nombres_rechaza_valores_no_texto(tmp_path):
    ruta = tmp_path / "nombres.json"
    ruta.write_text('{"ana_p_rez": 3}', encoding="utf-8")
    with pytest.raises(BuildError, match="cadenas de texto"):
        cargar_nombres(ruta)


def test_el_ejemplo_versionado_es_cargable():
    ejemplo = Path(__file__).resolve().parent.parent / "nombres.json.ejemplo"
    mapa = cargar_nombres(ejemplo)
    assert mapa, "la plantilla no puede estar vacía"
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in mapa.items())
