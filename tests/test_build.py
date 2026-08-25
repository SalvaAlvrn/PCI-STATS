from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

import requests

import build_dashboard
import kobo
from build_dashboard import (
    AREA_NULA,
    BuildError,
    cargar_nombres,
    clean,
    encode,
    load,
    render_html,
    validate,
    ID_DOCUMENTO,
    _descargar_sheet,
    _extraer_id,
)

XLSX = Path(__file__).resolve().parent.parent / "SupPCI.xlsx"
TEMPLATE = Path(__file__).resolve().parent.parent / "template.html"
VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "chart.umd.min.js"


@pytest.mark.skipif(not XLSX.exists(), reason="requiere el export local SupPCI.xlsx")
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
    # No se matchea el slug completo: el mensaje solo imprime un adelanto de
    # 4 caracteres a propósito (ver FIX 3), así que la prueba confirma que la
    # validación se disparó con la cuenta y una frase estable, no con el slug.
    with pytest.raises(BuildError, match=r"Hay 1 responsable\(s\)"):
        validate(registros_ok, formularios_ok, nombres_ok)


@pytest.mark.skipif(not XLSX.exists(), reason="requiere el export local SupPCI.xlsx")
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


@pytest.mark.skipif(not XLSX.exists(), reason="requiere el export local SupPCI.xlsx")
def test_clean_sobre_el_excel_real_conserva_todas_las_filas():
    registros, formularios = load(XLSX)
    limpio = clean(registros, formularios, cargar_nombres())
    assert len(limpio) == 2806
    assert limpio["RESPONSABLE"].nunique() == 21
    assert limpio["ID_FORMULARIO"].nunique() == 47
    assert limpio["NOMBRE_FORMULARIO_ACTUAL"].nunique() == 47
    assert limpio["AREA_ESPECIFICA_APLICACION"].isna().sum() == 0


def test_clean_colapsa_responsable_con_espacio_final(
    registros_ok, formularios_ok, nombres_ok
):
    # Misma persona que la fila 3 ("Ana Pérez"), pero con un espacio al
    # final: sin strip(), pandas los trataría como dos responsables
    # distintos y sus estadísticas se partirían en dos entradas.
    registros_ok.loc[3, "RESPONSABLE"] = "Ana Pérez "
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    nombres = set(limpio["RESPONSABLE"])
    assert "Ana Pérez" in nombres
    assert "Ana Pérez " not in nombres
    # Filas 0, 2 y 3 son la misma persona ("Ana Pérez" en la fixture base y
    # la variante con espacio final aquí): las tres deben colapsar a un solo
    # valor, no partirse en dos responsables distintos.
    assert (limpio["RESPONSABLE"] == "Ana Pérez").sum() == 3


def test_clean_normaliza_slug_con_espacios_alrededor(
    registros_ok, formularios_ok, nombres_ok
):
    registros_ok.loc[1, "RESPONSABLE"] = "  ana_mar_a_p_rez_g_mez  "
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    nombres = set(limpio["RESPONSABLE"])
    assert "Ana María Pérez Gómez" in nombres
    assert "  ana_mar_a_p_rez_g_mez  " not in nombres
    assert "ana_mar_a_p_rez_g_mez" not in nombres


def test_clean_area_solo_espacios_cae_en_area_nula(
    registros_ok, formularios_ok, nombres_ok
):
    # Una celda con solo espacios no debe convertirse en su propia categoría
    # " ": debe quedar vacía tras el strip y caer en el mismo relleno que un
    # nulo real.
    registros_ok.loc[3, "AREA_ESPECIFICA_APLICACION"] = "   "
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    assert limpio["AREA_ESPECIFICA_APLICACION"].isna().sum() == 0
    assert (limpio["AREA_ESPECIFICA_APLICACION"] == AREA_NULA).sum() == 2
    assert " " not in set(limpio["AREA_ESPECIFICA_APLICACION"])
    assert "   " not in set(limpio["AREA_ESPECIFICA_APLICACION"])


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


def test_cifra_de_control_tasa_global(libro_real):
    registros, formularios = load(libro_real)
    data = encode(clean(registros, formularios, cargar_nombres()), formularios)
    cumple = data["rows"]["cumple"]
    con_dictamen = [c for c in cumple if c >= 0]
    del_pipeline = sum(con_dictamen) / len(con_dictamen)
    de_pandas = _tasa(registros["CUMPLE_CORRECTAMENTE"])
    assert del_pipeline == pytest.approx(de_pandas)


def test_cifra_de_control_tasa_por_responsable(libro_real):
    registros, formularios = load(libro_real)
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


def test_cifra_de_control_tasa_por_mes(libro_real):
    registros, formularios = load(libro_real)
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


def test_render_html_produce_un_archivo_sin_urls_externas(tmp_path, libro_real):
    registros, formularios = load(libro_real)
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


def test_render_html_embebe_los_datos_reales(tmp_path, libro_real):
    # No se usa un nombre literal: este mapa es el real (nombres.json, fuera
    # del repo), así que la aserción se deriva de él en vez de citarlo, para
    # que ningún nombre real quede escrito en un archivo versionado.
    registros, formularios = load(libro_real)
    nombres = cargar_nombres()
    data = encode(clean(registros, formularios, nombres), formularios)
    salida = tmp_path / "dashboard.html"
    render_html(data, TEMPLATE, VENDOR, salida)
    html = salida.read_text(encoding="utf-8")
    slug, nombre_normalizado = next(iter(nombres.items()))
    assert nombre_normalizado in html
    assert slug not in html


def test_render_html_vendor_ausente_levanta_builderror_con_instrucciones(tmp_path, libro_real):
    registros, formularios = load(libro_real)
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


def test_cargar_nombres_rechaza_valores_repetidos(tmp_path):
    ruta = tmp_path / "nombres.json"
    ruta.write_text(
        '{"ana_p_rez": "Ana Pérez", "ana_p_rez_2": "Ana Pérez"}', encoding="utf-8"
    )
    with pytest.raises(BuildError, match="Ana Pérez"):
        cargar_nombres(ruta)


def test_el_ejemplo_versionado_es_cargable():
    ejemplo = Path(__file__).resolve().parent.parent / "nombres.json.ejemplo"
    mapa = cargar_nombres(ejemplo)
    assert mapa, "la plantilla no puede estar vacía"
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in mapa.items())


@pytest.mark.parametrize(
    "url",
    [
        "https://docs.google.com/spreadsheets/d/ABC123_-xyz/edit?gid=7#gid=7",
        "https://docs.google.com/spreadsheets/d/ABC123_-xyz/edit",
        "https://docs.google.com/spreadsheets/d/ABC123_-xyz",
    ],
)
def test_extraer_id_reconoce_las_formas_de_url(url):
    assert _extraer_id(url) == "ABC123_-xyz"


def test_extraer_id_rechaza_una_url_ajena():
    with pytest.raises(BuildError, match="no parece una URL de Google Sheets"):
        _extraer_id("https://example.com/algo")


def test_descargar_sheet_escribe_el_contenido(tmp_path):
    destino = tmp_path / "sheet.xlsx"
    respuesta = Mock(status_code=200, content=b"PK-contenido-binario")
    with patch("build_dashboard.requests.get", return_value=respuesta) as get:
        _descargar_sheet("ABC123", destino)
    assert destino.read_bytes() == b"PK-contenido-binario"
    assert "ABC123" in get.call_args.args[0]


def test_descargar_sheet_con_html_de_login_levanta_builderror(tmp_path):
    # Si el Sheet deja de ser público, Google responde 200 con una página de
    # inicio de sesión en vez del .xlsx. El status check por sí solo no lo
    # detecta; hace falta comprobar la firma ZIP del contenido.
    respuesta = Mock(
        status_code=200,
        content=b"<!doctype html><html><body>Inicia sesion</body></html>",
    )
    with patch("build_dashboard.requests.get", return_value=respuesta):
        with pytest.raises(BuildError, match="lectura pública"):
            _descargar_sheet("ABC123", tmp_path / "sheet.xlsx")


def test_descargar_sheet_con_http_no_exitoso_levanta_builderror(tmp_path):
    respuesta = Mock(status_code=403, content=b"")
    with patch("build_dashboard.requests.get", return_value=respuesta):
        with pytest.raises(BuildError, match="403"):
            _descargar_sheet("ABC123", tmp_path / "sheet.xlsx")


def test_descargar_sheet_sin_red_levanta_builderror(tmp_path):
    with patch(
        "build_dashboard.requests.get",
        side_effect=requests.ConnectionError("sin ruta al host"),
    ):
        with pytest.raises(BuildError, match="No se pudo contactar"):
            _descargar_sheet("ABC123", tmp_path / "sheet.xlsx")


@pytest.mark.skipif(not XLSX.exists(), reason="requiere el export local SupPCI.xlsx")
def test_load_sin_argumento_usa_el_documento_configurado():
    contenido = XLSX.read_bytes()
    respuesta = Mock(status_code=200, content=contenido)
    with patch("build_dashboard.requests.get", return_value=respuesta) as get:
        registros, formularios = load()
    assert ID_DOCUMENTO in get.call_args.args[0]
    assert len(registros) == 2806
    assert len(formularios) == 76


@pytest.mark.skipif(not XLSX.exists(), reason="requiere el export local SupPCI.xlsx")
def test_load_con_url_descarga_ese_documento():
    contenido = XLSX.read_bytes()
    respuesta = Mock(status_code=200, content=contenido)
    with patch("build_dashboard.requests.get", return_value=respuesta) as get:
        registros, _ = load("https://docs.google.com/spreadsheets/d/OTRO_ID/edit")
    assert "OTRO_ID" in get.call_args.args[0]
    assert len(registros) == 2806


@pytest.mark.skipif(not XLSX.exists(), reason="requiere el export local SupPCI.xlsx")
def test_load_con_ruta_sigue_leyendo_el_archivo():
    with patch("build_dashboard.requests.get") as get:
        registros, formularios = load(XLSX)
    get.assert_not_called()
    assert len(registros) == 2806


def test_encode_incluye_el_bloque_iaas_que_le_pasan(registros_ok, formularios_ok,
                                                    nombres_ok):
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    data = encode(limpio, formularios_ok, iaas={"ok": True, "meta": {"filas": 3}})
    assert data["iaas"]["meta"]["filas"] == 3


def test_encode_sin_iaas_deja_el_bloque_con_el_motivo(registros_ok,
                                                      formularios_ok, nombres_ok):
    limpio = clean(registros_ok, formularios_ok, nombres_ok)
    data = encode(limpio, formularios_ok,
                  iaas={"ok": False, "error": "HTTP 401"})
    assert data["iaas"]["error"] == "HTTP 401"


def test_main_publica_igual_cuando_kobo_falla(libro_real, capsys):
    """main() no escribe en disco aquí: render_html se sustituye por un espía.

    Llamar a main() de verdad sobreescribiría el dashboard.html del
    repositorio, que no es cosa de una prueba.
    """
    capturado = {}

    def espia(data, template, vendor, salida):
        capturado["data"] = data
        return 0

    with patch("build_dashboard.kobo.construir",
               side_effect=kobo.KoboError("HTTP 401")), \
         patch("build_dashboard.render_html", side_effect=espia):
        codigo = build_dashboard.main([str(libro_real)])

    assert codigo == 0
    assert capturado["data"]["iaas"]["ok"] is False
    assert capturado["data"]["iaas"]["error"] == "HTTP 401"
    salida = capsys.readouterr()
    assert "HTTP 401" in salida.out + salida.err


def test_el_html_generado_no_contiene_datos_de_paciente(tmp_path):
    """La prueba que sostiene la promesa de privacidad del apartado.

    Se construye con un envío sintético cuyos campos personales son cadenas
    inconfundibles y se comprueba que ninguna sobrevive al HTML.
    """
    from test_kobo import envio, esquema_completo

    with patch("kobo.descargar", return_value=(esquema_completo(), [envio()])):
        iaas = kobo.construir("t0ken")
    plantilla = tmp_path / "t.html"
    plantilla.write_text("<html>/*__DATA__*/ /*__CHARTJS__*/</html>", "utf-8")
    vendor = tmp_path / "chart.js"
    vendor.write_text("// chart", "utf-8")
    salida = tmp_path / "d.html"
    render_html({"iaas": iaas}, plantilla, vendor, salida)
    html = salida.read_text("utf-8")
    assert "PACIENTE_SINTETICO_XYZ" not in html
    assert "EXP-999999" not in html
    assert "CONCLUSION_SINTETICA_XYZ" not in html
