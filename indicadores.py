"""Indicadores institucionales de PCI: el libro que se edita desde el dashboard.

A diferencia del resto de fuentes, este libro lo escribe la propia página a
través de un Apps Script (`apps_script/indicadores.gs`). El build solo lo lee,
por CSV público como el libro de IAAS, y deja una copia en `DATA.indicadores`
para cuando la lectura en vivo no responda.

Las definiciones de los indicadores viven aquí y no en el libro: el libro
guarda solo números, así que nadie rompe un indicador editando un texto.
"""

import math

import pandas as pd

import iaas

# Se rellenan en la puesta en marcha (sección 12 del diseño). La URL del
# script es pública por naturaleza: la página la necesita para leer y guardar.
ID_LIBRO = ""
URL_SCRIPT = ""

INDICADORES = [
    {"id": "incidencia_iaas", "nombre": "Tasa de Incidencia de IAAS",
     "numerador": "Casos nuevos (excluyendo Hemodiálisis y Diálisis Peritoneal, "
                  "Colitis Pseudomembranosa e ISQ)",
     "denominador": "Ingresos hospitalarios", "k": 100},
    {"id": "densidad_iaas", "nombre": "Densidad de Incidencia de IAAS",
     "numerador": "Casos nuevos (excluyendo Hemodiálisis y Diálisis Peritoneal, "
                  "Colitis Pseudomembranosa)",
     "denominador": "Días-paciente", "k": 1000},
    {"id": "bacvc",
     "nombre": "Densidad de Incidencia de Bacteriemia Asociada a Catéter "
               "Venoso Central",
     "numerador": "Casos nuevos de BACVC",
     "denominador": "Días de mantenimiento de CVC", "k": 1000},
    {"id": "bacteriemia_hd",
     "nombre": "Incidencia de Bacteriemia Asociada a Hemodiálisis",
     "numerador": "Casos nuevos de bacteriemia asociada a catéter de "
                  "hemodiálisis",
     "denominador": "Procedimientos de hemodiálisis", "k": 100},
    {"id": "peritonitis_dp",
     "nombre": "Incidencia de Peritonitis Asociada a Diálisis Peritoneal",
     "numerador": "Casos nuevos de peritonitis asociada a DP",
     "denominador": "Procedimientos de diálisis peritoneal", "k": 100},
    {"id": "navm",
     "nombre": "Densidad de Incidencia de Neumonía Asociada a Ventilación "
               "Mecánica",
     "numerador": "Casos nuevos de NAVM",
     "denominador": "Días de ventilación mecánica invasiva", "k": 1000},
    {"id": "ituacu",
     "nombre": "Densidad de Incidencia de ITU Asociada a Catéter Urinario",
     "numerador": "Casos nuevos de ITUACU",
     "denominador": "Días de catéter urinario", "k": 1000},
    {"id": "isq", "nombre": "Incidencia de Infección del Sitio Quirúrgico",
     "numerador": "Casos nuevos de ISQ IAAS",
     "denominador": "Procedimientos quirúrgicos", "k": 100},
    {"id": "colitis_cdiff",
     "nombre": "Incidencia de Colitis Pseudomembranosa por C. difficile",
     "numerador": "Casos nuevos de colitis pseudomembranosa",
     "denominador": "Egresos hospitalarios", "k": 100},
    {"id": "proporcion_dispositivo",
     "nombre": "Proporción por tipo de infección relacionada a dispositivo",
     "numerador": "IAAS a desagregar del periodo (BACVC, ITUACU, NAVMI, ISQ)",
     "denominador": "Total de IAAS del periodo", "k": 100},
]
IDS = [i["id"] for i in INDICADORES]

HOJAS = {
    "VALORES": ["ANIO", "MES", "INDICADOR", "NUMERADOR", "DENOMINADOR"],
    "METAS": ["ANIO", "INDICADOR", "META"],
    "CONTROL": ["ANIO", "ACTUALIZADO"],
}

ANIO_MIN, ANIO_MAX = 2020, 2100


class IndicadoresError(Exception):
    pass


def _ahora():
    return pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")


def numero(valor, donde):
    """Número ≥ 0 de una celda, o None si está vacía.

    Google exporta el CSV con el separador decimal de la configuración
    regional del libro: «1,5» es tan válido como «1.5». Con punto y coma a la
    vez («1.234,5») no se adivina cuál es el decimal: se rechaza.
    """
    t = iaas.texto(valor)
    if t == "":
        return None
    if "," in t and "." not in t:
        t = t.replace(",", ".")
    try:
        x = float(t)
    except ValueError:
        raise IndicadoresError(f"{donde}: «{valor}» no es un número.")
    if math.isnan(x) or math.isinf(x) or x < 0:
        raise IndicadoresError(f"{donde}: «{valor}» no es un número ≥ 0.")
    return int(x) if x.is_integer() else x


def _entero(valor, donde, minimo, maximo, que):
    x = numero(valor, donde)
    if x is None or not float(x).is_integer() or not minimo <= x <= maximo:
        raise IndicadoresError(
            f"{donde}: {que} «{valor}» fuera de rango ({minimo}–{maximo}).")
    return int(x)


def _indicador(valor, donde):
    t = iaas.texto(valor)
    if t not in IDS:
        raise IndicadoresError(
            f"{donde}: «{t}» no es un indicador conocido. Ids válidos: {IDS}.")
    return t


def _vacia(fila, columnas):
    return all(iaas.texto(fila[c]) == "" for c in columnas)


def descargar(libro=None):
    """{pestaña: DataFrame de texto} para las tres pestañas del libro."""
    libro = libro or ID_LIBRO
    if not libro:
        raise IndicadoresError(
            "El libro de indicadores aún no está configurado: falta ID_LIBRO "
            "en indicadores.py.")
    try:
        indice = iaas.indice_de_hojas(libro)
        faltan = [h for h in HOJAS if h not in indice]
        if faltan:
            raise IndicadoresError(
                f"El libro de indicadores no tiene estas pestañas: {faltan}. "
                f"Tiene {sorted(indice)}.")
        return {h: iaas.descargar_hoja(h, indice[h], libro) for h in HOJAS}
    except iaas.IaasError as error:
        raise IndicadoresError(f"Libro de indicadores: {error}") from error


def limpiar(libro):
    """(valores, metas, control) validados a partir de las tres pestañas."""
    for hoja, columnas in HOJAS.items():
        faltan = [c for c in columnas if c not in libro[hoja].columns]
        if faltan:
            raise IndicadoresError(
                f"La pestaña «{hoja}» del libro de indicadores no tiene estas "
                f"columnas: {faltan}.")

    # Fila 1 del Sheet es la cabecera: la fila i del DataFrame es la i + 2.
    valores, vistos = [], set()
    for i, fila in libro["VALORES"].iterrows():
        if _vacia(fila, HOJAS["VALORES"]):
            continue
        donde = f"VALORES fila {i + 2}"
        anio = _entero(fila["ANIO"], donde, ANIO_MIN, ANIO_MAX, "año")
        mes = _entero(fila["MES"], donde, 1, 12, "mes")
        ind = _indicador(fila["INDICADOR"], donde)
        if (anio, mes, ind) in vistos:
            raise IndicadoresError(
                f"{donde}: {ind} de {mes}/{anio} está repetido.")
        vistos.add((anio, mes, ind))
        valores.append({"anio": anio, "mes": mes, "indicador": ind,
                        "n": numero(fila["NUMERADOR"], donde),
                        "d": numero(fila["DENOMINADOR"], donde)})
    valores.sort(key=lambda v: (v["anio"], v["mes"], IDS.index(v["indicador"])))

    metas, vistas = [], set()
    for i, fila in libro["METAS"].iterrows():
        if _vacia(fila, HOJAS["METAS"]):
            continue
        donde = f"METAS fila {i + 2}"
        anio = _entero(fila["ANIO"], donde, ANIO_MIN, ANIO_MAX, "año")
        ind = _indicador(fila["INDICADOR"], donde)
        if (anio, ind) in vistas:
            raise IndicadoresError(f"{donde}: la meta de {ind} en {anio} está repetida.")
        vistas.add((anio, ind))
        meta = numero(fila["META"], donde)
        if meta is not None:
            metas.append({"anio": anio, "indicador": ind, "meta": meta})
    metas.sort(key=lambda m: (m["anio"], IDS.index(m["indicador"])))

    control = {}
    for i, fila in libro["CONTROL"].iterrows():
        if _vacia(fila, HOJAS["CONTROL"]):
            continue
        donde = f"CONTROL fila {i + 2}"
        anio = _entero(fila["ANIO"], donde, ANIO_MIN, ANIO_MAX, "año")
        control[str(anio)] = iaas.texto(fila["ACTUALIZADO"])
    return valores, metas, control


def _base():
    return {"indicadores": INDICADORES, "url_script": URL_SCRIPT}


def construir(libro=None):
    """Descarga y valida el libro. Devuelve el bloque DATA.indicadores."""
    valores, metas, control = limpiar(descargar(libro))
    return {"ok": True, **_base(), "valores": valores, "metas": metas,
            "control": control, "generado": _ahora()}


def bloque_fallido(error):
    """Bloque sin copia del libro. Conserva el manifiesto y la URL del script:
    la página puede seguir leyendo en vivo aunque el build no pudiera."""
    return {"ok": False, "error": str(error), "fecha": _ahora(), **_base()}
