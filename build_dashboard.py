"""Genera dashboard.html a partir de SupPCI.xlsx.

Pipeline: load -> validate -> clean -> encode -> render_html.
Ver docs/superpowers/specs/2026-08-24-dashboard-supervisiones-design.md
"""

import json
import sys
from pathlib import Path

import pandas as pd


class BuildError(Exception):
    """La estructura del Excel no es la esperada. Aborta el build."""


COLUMNAS_REGISTROS = [
    "ID_REGISTRO", "FECHA_REGISTRO", "FECHA_EVENTO", "ID_FORMULARIO",
    "VERSION_FORMULARIO", "FORMULARIO", "MEDIDA", "SUBMEDIDA", "RESPONSABLE",
    "UNIDAD_SERVICIO_APLICACION", "AREA_ESPECIFICA_APLICACION",
    "GRUPO_OCUPACIONAL", "CARGO", "NOMBRE_EVALUADO",
    "PORCENTAJE_CUMPLIMIENTO", "TOTAL_SI", "TOTAL_NO", "TOTAL_NA",
    "CUMPLE_CORRECTAMENTE", "MOTIVO_NO_CUMPLIMIENTO",
    "CONCLUSIONES_RECOMENDACIONES", "ESTADO_VALIDACION", "NIVEL_RIESGO",
]

COLUMNAS_FORMULARIOS = [
    "ID_FORMULARIO", "VERSION_FORMULARIO", "MEDIDA", "SUBMEDIDA",
    "NOMBRE_FORMULARIO", "METODO_CUMPLIMIENTO",
]

# Dos responsables quedaron con el nombre en formato slug tras la migración.
# El mapa es explícito a propósito: des-sluguificar automáticamente no puede
# recuperar la acentuación y un error silencioso crearía un responsable
# fantasma que partiría sus estadísticas en dos.
SLUG_NAME_MAP = {
    "ana_mar_a_p_rez_g_mez": "Ana María Pérez Gómez",
    "luis_fernando_l_pez_d_az": "Luis Fernando López Díaz",
}

CUMPLE_VALIDOS = {"SI", "NO"}
ESTADOS_VALIDOS = {"Aprobado", "En espera"}
METODO_SOPORTADO = "SI_NO_NA"
FECHA_MINIMA = pd.Timestamp("2020-01-01")

AREA_NULA = "(Sin área específica)"
RIESGO_NULO = "(Sin nivel de riesgo)"

# Columnas de dimensión que encode() convierte a categoría: un nulo se
# codificaría como -1 y el JavaScript lo evaluaría como índice inexistente,
# agrupando esas filas en un bucket fantasma con etiqueta undefined. AREA,
# RIESGO y MOTIVO tienen su propio nulo con significado y se rellenan en
# clean(); estas otras no deberían tener nulos y su presencia es un error de
# datos, no algo que el build deba decidir cómo rellenar.
COLUMNAS_SIN_NULOS = [
    "RESPONSABLE",
    "MEDIDA",
    "SUBMEDIDA",
    "UNIDAD_SERVICIO_APLICACION",
    "GRUPO_OCUPACIONAL",
    "CARGO",
    "ESTADO_VALIDACION",
]


def load(path):
    """Lee las hojas REGISTROS y FORMULARIOS de SupPCI.xlsx."""
    path = Path(path)
    if not path.exists():
        raise BuildError(f"El archivo {path} no existe")
    libro = pd.ExcelFile(path)
    faltantes = {"REGISTROS", "FORMULARIOS"} - set(libro.sheet_names)
    if faltantes:
        raise BuildError(f"Faltan hojas en el libro: {sorted(faltantes)}")
    registros = pd.read_excel(libro, "REGISTROS")
    formularios = pd.read_excel(libro, "FORMULARIOS")
    return registros, formularios


def _columnas_faltantes(df, esperadas, hoja):
    faltan = [c for c in esperadas if c not in df.columns]
    if faltan:
        raise BuildError(f"Faltan columnas en la hoja {hoja}: {faltan}")


def validate(registros, formularios):
    """Aborta el build si el Excel no tiene la forma que el dashboard asume."""
    _columnas_faltantes(registros, COLUMNAS_REGISTROS, "REGISTROS")
    _columnas_faltantes(formularios, COLUMNAS_FORMULARIOS, "FORMULARIOS")

    con_nulos = [c for c in COLUMNAS_SIN_NULOS if registros[c].isna().any()]
    if con_nulos:
        raise BuildError(
            f"Estas columnas no deberían tener nulos y los tienen: "
            f"{con_nulos}. Un nulo aquí se codificaría como categoría "
            "fantasma y arruinaría la agregación."
        )

    valores = set(registros["CUMPLE_CORRECTAMENTE"].dropna().unique())
    desconocidos = valores - CUMPLE_VALIDOS
    if desconocidos:
        raise BuildError(
            "CUMPLE_CORRECTAMENTE trae valores no soportados: "
            f"{sorted(desconocidos)}. El dashboard solo sabe interpretar "
            f"{sorted(CUMPLE_VALIDOS)} y nulo."
        )

    estados = set(registros["ESTADO_VALIDACION"].dropna().unique())
    estados_desconocidos = estados - ESTADOS_VALIDOS
    if estados_desconocidos:
        raise BuildError(
            "ESTADO_VALIDACION trae valores no soportados: "
            f"{sorted(estados_desconocidos)}. El dashboard solo sabe "
            f"interpretar {sorted(ESTADOS_VALIDOS)}."
        )

    pct = pd.to_numeric(registros["PORCENTAJE_CUMPLIMIENTO"], errors="coerce")
    if pct.isna().any() or ((pct < 0) | (pct > 100)).any():
        raise BuildError(
            "PORCENTAJE_CUMPLIMIENTO tiene valores no numéricos o fuera de 0-100"
        )
    if (pct % 1 != 0).any():
        raise BuildError(
            "PORCENTAJE_CUMPLIMIENTO tiene valores no enteros. encode() los "
            "trunca con int(); un valor como 92.5 debe corregirse en el "
            "origen, no redondearse en silencio."
        )

    fechas = pd.to_datetime(registros["FECHA_EVENTO"], errors="coerce")
    if fechas.isna().any():
        raise BuildError("FECHA_EVENTO tiene valores no parseables como fecha")
    tope = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    if (fechas < FECHA_MINIMA).any() or (fechas > tope).any():
        raise BuildError(
            f"FECHA_EVENTO tiene valores fuera del rango {FECHA_MINIMA.date()} "
            f"a {tope.date()}"
        )

    usados = set(registros["ID_FORMULARIO"].unique())
    metodos_usados = set(
        formularios[formularios["ID_FORMULARIO"].isin(usados)][
            "METODO_CUMPLIMIENTO"
        ].dropna()
    )
    no_soportados = metodos_usados - {METODO_SOPORTADO}
    if no_soportados:
        raise BuildError(
            f"Hay registros de formularios con METODO_CUMPLIMIENTO "
            f"{sorted(no_soportados)}. Estos formularios no calculan "
            "cumplimiento y requieren una decisión de producto antes de "
            "incluirlos; no se pueden promediar con los SI_NO_NA."
        )
    slugs = {
        nombre
        for nombre in registros["RESPONSABLE"].dropna().unique()
        if "_" in nombre and nombre == nombre.lower()
    }
    sin_mapear = slugs - set(SLUG_NAME_MAP)
    if sin_mapear:
        raise BuildError(
            f"Responsables con nombre en formato slug sin mapear: "
            f"{sorted(sin_mapear)}. Añádelos a SLUG_NAME_MAP con su nombre "
            "correcto y acentuado."
        )


def _filas_actuales(formularios):
    """Fila de cada formulario en su versión más alta del catálogo.

    El catálogo (FORMULARIOS) es la única fuente de verdad para nombre,
    versión, medida y submedida vigentes de cada ID_FORMULARIO: tiene una
    fila por versión y aquí se toma la de VERSION_FORMULARIO más alta. Esto
    es distinto de REGISTROS.FORMULARIO, que para un puñado de filas de F031
    conserva el nombre anterior a una renombrada — eso es historial de la
    migración en los registros, no una segunda versión en el catálogo, y por
    eso no se usa como fuente.
    """
    ordenado = formularios.sort_values("VERSION_FORMULARIO")
    return ordenado.groupby("ID_FORMULARIO").last()


def _nombres_actuales(formularios):
    """Nombre de cada formulario según su versión más alta en el catálogo."""
    return _filas_actuales(formularios)["NOMBRE_FORMULARIO"].to_dict()


def clean(registros, formularios):
    """Normaliza valores y deriva las columnas que el dashboard agrega."""
    df = registros.copy()

    df["RESPONSABLE"] = df["RESPONSABLE"].replace(SLUG_NAME_MAP)

    df["AREA_ESPECIFICA_APLICACION"] = (
        df["AREA_ESPECIFICA_APLICACION"].fillna(AREA_NULA)
    )
    df["MOTIVO_NO_CUMPLIMIENTO"] = df["MOTIVO_NO_CUMPLIMIENTO"].fillna("")
    df["CONCLUSIONES_RECOMENDACIONES"] = (
        df["CONCLUSIONES_RECOMENDACIONES"].fillna("")
    )
    df["NIVEL_RIESGO"] = df["NIVEL_RIESGO"].fillna(RIESGO_NULO)

    nombres = _nombres_actuales(formularios)
    df["NOMBRE_FORMULARIO_ACTUAL"] = df["ID_FORMULARIO"].map(nombres)
    sin_nombre = df["NOMBRE_FORMULARIO_ACTUAL"].isna()
    if sin_nombre.any():
        ids = sorted(df.loc[sin_nombre, "ID_FORMULARIO"].unique())
        raise BuildError(
            f"Hay registros de formularios ausentes del catálogo: {ids}"
        )

    fecha = pd.to_datetime(df["FECHA_EVENTO"])
    df["MES"] = fecha.dt.strftime("%Y-%m")
    iso = fecha.dt.isocalendar()
    df["SEMANA"] = (
        iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    )
    # Días desde epoch. El cast a datetime64[D] es independiente de la
    # unidad de la columna: pandas 3 usa datetime64[us], de modo que un
    # astype("int64") daría microsegundos, no nanosegundos.
    df["DIA"] = fecha.values.astype("datetime64[D]").astype("int64")

    df["CUMPLE"] = (
        df["CUMPLE_CORRECTAMENTE"].map({"SI": 1, "NO": 0}).fillna(-1).astype(int)
    )

    return df


# columna del DataFrame limpio -> clave de dimensión en DATA
DIMENSIONES = {
    "RESPONSABLE": "responsable",
    "ID_FORMULARIO": "formulario",
    "MEDIDA": "medida",
    "SUBMEDIDA": "submedida",
    "UNIDAD_SERVICIO_APLICACION": "unidad",
    "AREA_ESPECIFICA_APLICACION": "area",
    "GRUPO_OCUPACIONAL": "grupo",
    "CARGO": "cargo",
    "ESTADO_VALIDACION": "estado",
    "NIVEL_RIESGO": "riesgo",
    "MOTIVO_NO_CUMPLIMIENTO": "motivo",
    "MES": "mes",
    "SEMANA": "semana",
}


def encode(df, formularios):
    """Codifica el DataFrame limpio en diccionarios + columnas paralelas."""
    dims = {}
    rows = {}
    for columna, clave in DIMENSIONES.items():
        categoria = df[columna].astype("category")
        # Orden alfabético para que el archivo sea determinista entre builds.
        categoria = categoria.cat.reorder_categories(
            sorted(categoria.cat.categories)
        )
        dims[clave] = list(categoria.cat.categories)
        rows[clave] = [int(c) for c in categoria.cat.codes]

    rows["dia"] = [int(v) for v in df["DIA"]]
    rows["cumple"] = [int(v) for v in df["CUMPLE"]]
    rows["pct"] = [int(v) for v in df["PORCENTAJE_CUMPLIMIENTO"]]
    rows["si"] = [int(v) for v in df["TOTAL_SI"]]
    rows["no"] = [int(v) for v in df["TOTAL_NO"]]
    rows["na"] = [int(v) for v in df["TOTAL_NA"]]

    # nombre, versión, medida y submedida deben venir todos de la misma
    # fuente — la fila de versión más alta en el catálogo — para que no
    # puedan divergir si el catálogo alguna vez tiene una versión que
    # ningún registro usa todavía.
    filas_catalogo = _filas_actuales(formularios)
    forms = {}
    for id_form in df["ID_FORMULARIO"].unique():
        fila = filas_catalogo.loc[id_form]
        forms[id_form] = {
            "nombre": fila["NOMBRE_FORMULARIO"],
            "version": int(fila["VERSION_FORMULARIO"]),
            "medida": fila["MEDIDA"],
            "submedida": fila["SUBMEDIDA"],
        }

    # Las conclusiones solo se consultan sobre lo que falló; embeberlas todas
    # duplicaría el peso del archivo sin que nadie las lea.
    conclusiones = {
        str(i): texto
        for i, (cumple, texto) in enumerate(
            zip(df["CUMPLE"], df["CONCLUSIONES_RECOMENDACIONES"])
        )
        if cumple == 0 and texto
    }

    return {
        "dims": dims,
        "forms": forms,
        "rows": rows,
        # NOMBRE_EVALUADO tiene 2012 valores distintos sobre 2806 filas: el
        # diccionario no comprimiría nada. No es dimensión de agregación.
        "texts": {
            "evaluado": [str(v) for v in df["NOMBRE_EVALUADO"]],
            "conclusiones": conclusiones,
        },
        "meta": {
            "generado": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
            "filas": len(df),
            "dia_min": int(df["DIA"].min()),
            "dia_max": int(df["DIA"].max()),
        },
    }


def _leer_o_falla(path, ayuda=""):
    path = Path(path)
    if not path.exists():
        raise BuildError(f"No existe {path}." + (f" {ayuda}" if ayuda else ""))
    return path.read_text(encoding="utf-8")


def render_html(data, template, vendor, salida):
    """Inyecta datos y Chart.js en la plantilla. Devuelve bytes escritos."""
    html = _leer_o_falla(template)
    chartjs = _leer_o_falla(
        vendor,
        "Chart.js no viene en el repo — descárgalo con: curl -L "
        "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js "
        "-o vendor/chart.umd.min.js",
    )

    # ensure_ascii=False mantiene los acentos legibles y pesa menos que \uXXXX.
    # separators sin espacios recorta cerca de un 8% del JSON.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # </script> dentro de una cadena JSON cerraría el bloque antes de tiempo.
    payload = payload.replace("</", "<\\/")

    html = html.replace("/*__CHARTJS__*/", chartjs)
    html = html.replace("/*__DATA__*/", payload)

    salida = Path(salida)
    salida.write_text(html, encoding="utf-8")
    return len(html.encode("utf-8"))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    raiz = Path(__file__).resolve().parent
    origen = Path(argv[0]) if argv else raiz / "SupPCI.xlsx"
    salida = raiz / "dashboard.html"

    registros, formularios = load(origen)
    print(f"Leídas {len(registros)} filas de REGISTROS")

    validate(registros, formularios)

    limpio = clean(registros, formularios)
    slugs = sum(registros["RESPONSABLE"].isin(SLUG_NAME_MAP))
    areas = int(registros["AREA_ESPECIFICA_APLICACION"].isna().sum())
    print(f"Nombres normalizados: {slugs}")
    print(f"Áreas nulas rellenadas como «{AREA_NULA}»: {areas}")

    data = encode(limpio, formularios)
    escritos = render_html(
        data, raiz / "template.html", raiz / "vendor" / "chart.umd.min.js", salida
    )
    print(f"Escrito {salida} — {escritos / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
