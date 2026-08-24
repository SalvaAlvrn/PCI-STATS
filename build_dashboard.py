"""Genera dashboard.html a partir de SupPCI.xlsx.

Pipeline: load -> validate -> clean -> encode -> render_html.
Ver docs/superpowers/specs/2026-08-24-dashboard-supervisiones-design.md
"""

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
METODO_SOPORTADO = "SI_NO_NA"
FECHA_MINIMA = pd.Timestamp("2020-01-01")

AREA_NULA = "(Sin área específica)"


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

    valores = set(registros["CUMPLE_CORRECTAMENTE"].dropna().unique())
    desconocidos = valores - CUMPLE_VALIDOS
    if desconocidos:
        raise BuildError(
            "CUMPLE_CORRECTAMENTE trae valores no soportados: "
            f"{sorted(desconocidos)}. El dashboard solo sabe interpretar "
            f"{sorted(CUMPLE_VALIDOS)} y nulo."
        )

    pct = pd.to_numeric(registros["PORCENTAJE_CUMPLIMIENTO"], errors="coerce")
    if pct.isna().any() or ((pct < 0) | (pct > 100)).any():
        raise BuildError(
            "PORCENTAJE_CUMPLIMIENTO tiene valores no numéricos o fuera de 0-100"
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

    metodos = set(formularios["METODO_CUMPLIMIENTO"].dropna().unique())
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
    del metodos  # solo se valida sobre los métodos realmente usados

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


def _nombres_actuales(formularios):
    """Nombre de cada formulario según su versión más alta.

    F031 cambió de nombre entre versiones, de modo que ID_FORMULARIO tiene
    47 valores distintos pero FORMULARIO tiene 48. La clave es el ID.
    """
    ordenado = formularios.sort_values("VERSION_FORMULARIO")
    ultimo = ordenado.groupby("ID_FORMULARIO").last()
    return ultimo["NOMBRE_FORMULARIO"].to_dict()


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
    df["NIVEL_RIESGO"] = df["NIVEL_RIESGO"].fillna("(Sin nivel de riesgo)")

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


def encode(df):
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

    forms = {}
    for id_form, grupo in df.groupby("ID_FORMULARIO"):
        ultima = grupo.sort_values("VERSION_FORMULARIO").iloc[-1]
        forms[id_form] = {
            "nombre": ultima["NOMBRE_FORMULARIO_ACTUAL"],
            "version": int(ultima["VERSION_FORMULARIO"]),
            "medida": ultima["MEDIDA"],
            "submedida": ultima["SUBMEDIDA"],
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
