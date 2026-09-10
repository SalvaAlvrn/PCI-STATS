"""Vigilancia de IAAS, leída del sistema de Epidemiología en Google Sheets.

Sustituye a `kobo.py`: los dos formularios de KoboToolbox —producción e
investigación de casos— se migraron al libro «Sistema IAAS» v6.5, que ya trae
el caso normalizado en varias hojas relacionadas por `ID_CASO`.

Produce el bloque `DATA.iaas` que consume el dashboard. Vive aparte de
`build_dashboard.py` a propósito: el pipeline de supervisiones no debe cambiar
de comportamiento porque esta fuente falle o cambie de forma.

Nada que identifique a un paciente sale de aquí. El libro trae nombre,
expediente, cama, diagnóstico CIE-10 y observaciones en casi todas las hojas;
la lista blanca de cada `limpiar_*` es la que decide qué se copia, y
`CAMPOS_PROHIBIDOS` es la lista contra la que una prueba comprueba que ninguno
se cuela.
"""

import io
import re

import pandas as pd
import requests


class IaasError(Exception):
    """El libro no respondió, o sus hojas ya no tienen la forma esperada.

    No aborta el build: `build_dashboard.py` lo captura y publica el
    dashboard sin el apartado, con el motivo a la vista.
    """


ID_LIBRO = "1fpUICeal47RTZeWwpyD_gR21yjgqp26OwHd6D4-YW50"
TIMEOUT_SEGUNDOS = 60

# Hoja → columnas sin las que el apartado no se puede construir. Google
# devuelve la primera hoja del libro cuando el nombre no existe, en lugar de
# un 404: sin comprobar las cabeceras, un cambio de nombre se leería como una
# hoja de configuración vacía de casos y el apartado saldría a cero.
HOJAS = {
    "CASOS_IAAS": [
        "ID_CASO", "ID_PACIENTE", "FECHA_NOTIFICACION", "FECHA_INGRESO",
        "ORIGEN_IAAS", "DIAGNOSTICO_IAAS",
        "DEFINICION_CASO", "DISPOSITIVO_RESUMEN", "MICROORGANISMO_RESUMEN",
        "SERVICIO", "UBICACION", "CONDICION", "VIGEPES_08", "FECHA_VIGEPES_08",
        "CAUSA_RAIZ", "TIPO_INTERVENCION", "PROCEDIMIENTO_ISQ",
        "CLASIFICACION_HERIDA", "FUENTE_ORIGEN", "KOBO_UUID", "ARCHIVADO",
        "NOMBRE_PACIENTE",
    ],
    "PACIENTES": ["ID_PACIENTE", "FECHA_NACIMIENTO", "SEXO"],
    "DISPOSITIVOS": [
        "ID_CASO", "TIPO_DISPOSITIVO", "PRESENTE", "DIAS_EXPOSICION",
        "CUMPLE_BUNDLE",
    ],
    "INVESTIGACIONES": [
        "ID_CASO", "FECHA_INVESTIGACION", "FECHA_CIERRE",
        "ENFERMEDADES_CRONICAS",
    ],
    # Export crudo del formulario de Kobo, tal como quedó tras la migración.
    # Solo se usa para rescatar fechas (ver `_rescatar_fechas`).
    "KOBO_SEGUIMIENTO": ["_uuid", "Fecha de notificación", "Fecha de ingreso"],
}

# Columnas que existen en el libro y que este módulo no debe publicar jamás.
# No es lo que filtra —eso lo hacen las listas blancas de `limpiar_*`— sino la
# lista contra la que una prueba comprueba que ninguna se cuela en el HTML.
CAMPOS_PROHIBIDOS = [
    "NOMBRE_PACIENTE", "NOMBRE", "EXPEDIENTE", "FECHA_NACIMIENTO", "CAMA",
    "OBSERVACIONES", "DIAGNOSTICO_CIE10", "ID_PACIENTE", "ID_CASO",
    "CORRELATIVO", "KOBO_UUID", "RESPONSABLE_CIRUGIA", "RESPONSABLE_COLOCACION",
    "RESPONSABLE_CUIDADO", "MEDICO_TRATANTE", "PERSONAL_PCI", "MEDICAMENTOS",
    "DIAGNOSTICO_IAAS_OTRO", "MICROORGANISMO_OTRO", "LUGAR_ORIGEN_EXTRA",
]

CONFIRMADO = "Caso confirmado"
SOSPECHOSO = "Caso sospechoso"
NO_IAAS = "No IAAS"
# Si el sistema deja de escribir estas tres, todo el apartado se queda sin
# base: no es un valor más de una lista, es el eje del tablero.
DEFINICIONES = [CONFIRMADO, SOSPECHOSO, NO_IAAS]

SIN_DATO = "(Sin registrar)"
# Fila de prueba que el equipo dejó en el libro. Se compara el nombre completo
# —no «contiene TEST»— para no tirar un caso real cuyo texto lo mencione.
PACIENTE_PRUEBA = "TEST"

# Los tramos son los del informe epidemiológico, no cuartiles: se comparan
# entre periodos y con otros hospitales, así que tienen que ser fijos.
TRAMOS_EDAD = [
    (0, 1, "< 1 año"), (1, 15, "1-14"), (15, 30, "15-29"), (30, 45, "30-44"),
    (45, 60, "45-59"), (60, 75, "60-74"), (75, 200, "75+"),
]

# Dispositivos con denominador de días de exposición. El resto se cuenta, pero
# no entra en la tabla de densidad de incidencia.
DISPOSITIVOS_INVASIVOS = [
    "Ventilación Mecánica", "Catéter Venoso Central", "Catéter Urinario",
    "Catéter de Hemodiálisis", "Catéter Venoso Periférico", "Herida Quirúrgica",
]


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def _pedir(url, que):
    try:
        respuesta = requests.get(url, timeout=TIMEOUT_SEGUNDOS)
    except requests.RequestException as error:
        raise IaasError(f"No se pudo contactar con Google Sheets: {error}")
    if respuesta.status_code in (401, 403, 404):
        raise IaasError(
            f"Google Sheets respondió {respuesta.status_code} al pedir {que}. "
            "El libro dejó de existir o de ser visible con el enlace: "
            "comprueba que sigue compartido como «cualquiera con el enlace»."
        )
    if respuesta.status_code != 200:
        raise IaasError(
            f"Google Sheets respondió {respuesta.status_code} al pedir {que}."
        )
    respuesta.encoding = "utf-8"
    return respuesta.text


def indice_de_hojas(libro=ID_LIBRO):
    """Nombre de hoja → gid, leído de la portada `htmlview` del libro.

    Los gids no se escriben a mano: si alguien recrea una hoja, cambia el
    número pero no el nombre, y un gid fijo en el código empezaría a bajar la
    hoja equivocada —o ninguna— sin decir por qué.
    """
    html = _pedir(f"https://docs.google.com/spreadsheets/d/{libro}/htmlview",
                  "el índice de hojas del libro")
    indice = dict(re.findall(r'name:\s*"((?:[^"\\]|\\.)*)",\s*pageUrl:.*?gid=(\d+)',
                             html))
    if not indice:
        raise IaasError(
            "No se pudo leer el índice de hojas del libro: la portada de "
            "Google Sheets cambió de formato. Revisa `indice_de_hojas`."
        )
    return indice


def descargar_hoja(hoja, gid, libro=ID_LIBRO):
    """Devuelve una hoja del libro como DataFrame de texto.

    Se baja por `export?format=csv&gid=`, no por `gviz/tq`: la API gviz
    devuelve el libro a medias —81 de 186 casos, sin avisar de nada— y un
    apartado que se publica con un tercio de los datos es peor que uno que
    falla.
    """
    csv = _pedir(
        f"https://docs.google.com/spreadsheets/d/{libro}/export?format=csv&gid={gid}",
        f"la hoja «{hoja}»")
    try:
        tabla = pd.read_csv(io.StringIO(csv), dtype=str)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as error:
        raise IaasError(f"La hoja «{hoja}» no se pudo leer como CSV: {error}")
    return tabla.fillna("")


def descargar(libro=ID_LIBRO, hojas=None):
    """Devuelve {nombre de hoja: DataFrame} para las hojas del manifiesto."""
    nombres = list(hojas or HOJAS)
    indice = indice_de_hojas(libro)
    faltan = [n for n in nombres if n not in indice]
    if faltan:
        raise IaasError(
            f"El libro de IAAS ya no tiene estas hojas: {faltan}. Tiene "
            f"{sorted(indice)}. Si las renombraron, actualiza el manifiesto "
            "de iaas.py."
        )
    return {nombre: descargar_hoja(nombre, indice[nombre], libro)
            for nombre in nombres}


def validar(libro):
    """Comprueba que cada hoja trae las columnas del manifiesto.

    Es también la comprobación de que Google no devolvió otra hoja: cuando el
    nombre pedido no existe, la API entrega la primera del libro sin avisar.
    """
    for hoja, columnas in HOJAS.items():
        if hoja not in libro:
            raise IaasError(f"No se descargó la hoja «{hoja}».")
        faltan = [c for c in columnas if c not in libro[hoja].columns]
        if faltan:
            raise IaasError(
                f"La hoja «{hoja}» del libro de IAAS ya no tiene la forma "
                f"esperada. Faltan estas columnas: {faltan}. Si las "
                "renombraste en el sistema, actualiza el manifiesto de iaas.py."
            )
    return libro


# ---------------------------------------------------------------------------
# Conversión de valores
# ---------------------------------------------------------------------------

def texto(valor):
    """Texto recortado, con los espacios duros del sistema ya fuera."""
    return re.sub(r"\s+", " ", str(valor).replace("\xa0", " ")).strip()


def multi(valor):
    """Los campos de selección múltiple llegan como «A | B | C»."""
    return [t for t in (texto(p) for p in str(valor).split("|")) if t]


def fecha(valor):
    """Fecha del sistema (DD/MM/AAAA, con hora o sin ella) o None.

    El libro mezcla `DD/MM/AAAA`, `D/MM/AAAA` y `DD/MM/AAAA HH:MM` en la misma
    columna, y el export crudo de Kobo trae ISO. Se aceptan los dos y se
    rechaza cualquier otra cosa: una fecha mal interpretada mueve casos de mes
    sin que nada lo advierta.
    """
    crudo = texto(valor)
    if not crudo:
        return None
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", crudo)
    if iso:
        return pd.Timestamp(int(iso[1]), int(iso[2]), int(iso[3]))
    partes = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", crudo)
    if not partes:
        raise IaasError(f"El libro trae una fecha ilegible: {crudo!r}.")
    dia, mes, anio = (int(p) for p in partes.groups())
    try:
        return pd.Timestamp(anio, mes, dia)
    except ValueError:
        raise IaasError(f"El libro trae una fecha imposible: {crudo!r}.")


def _dia(momento):
    """Días desde epoch, igual que DIA en build_dashboard.py."""
    if momento is None:
        return None
    return int(momento.to_datetime64().astype("datetime64[D]").astype("int64"))


def _entre(desde, hasta):
    """Días entre dos fechas, o None si falta alguna. Negativos: None."""
    if desde is None or hasta is None:
        return None
    dias = (hasta - desde).days
    return dias if dias >= 0 else None


def _tramo_edad(nacimiento, referencia):
    if nacimiento is None or referencia is None:
        return SIN_DATO
    anios = (referencia - nacimiento).days // 365
    if anios < 0:
        return SIN_DATO
    for minimo, maximo, etiqueta in TRAMOS_EDAD:
        if minimo <= anios < maximo:
            return etiqueta
    return SIN_DATO


# ---------------------------------------------------------------------------
# Limpieza
# ---------------------------------------------------------------------------

def _rescatar_fechas(casos, kobo_crudo):
    """Rellena las fechas que la migración perdió, desde el export de Kobo.

    La migración dejó `FECHA_NOTIFICACION` y `FECHA_INGRESO` vacías en más de
    la mitad de los casos migrados; el export crudo del formulario, que está
    en el mismo libro, sí las tiene todas y se puede emparejar por `KOBO_UUID`.
    Es un parche: lo correcto es rehacer ese tramo de la migración. Mientras
    tanto, sin esto un tercio de los casos confirmados no entraría en ninguna
    serie temporal. `meta.fechas_rescatadas` deja el parche a la vista.
    """
    origen = {}
    for _, fila in kobo_crudo.iterrows():
        uuid = texto(fila.get("_uuid", ""))
        if uuid:
            origen[uuid] = (texto(fila.get("Fecha de notificación", "")),
                            texto(fila.get("Fecha de ingreso", "")))
    rescatadas = 0
    casos = casos.copy()
    for i, fila in casos.iterrows():
        uuid = texto(fila["KOBO_UUID"])
        if not uuid or uuid not in origen:
            continue
        notificacion, ingreso = origen[uuid]
        if not texto(fila["FECHA_NOTIFICACION"]) and notificacion:
            casos.at[i, "FECHA_NOTIFICACION"] = notificacion
            rescatadas += 1
        if not texto(fila["FECHA_INGRESO"]) and ingreso:
            casos.at[i, "FECHA_INGRESO"] = ingreso
    return casos, rescatadas


def _pacientes(tabla):
    """ID de paciente → (nacimiento, sexo). Ni nombre ni expediente salen."""
    salida = {}
    for _, fila in tabla.iterrows():
        clave = texto(fila["ID_PACIENTE"])
        if clave:
            salida[clave] = (fecha(fila["FECHA_NACIMIENTO"]),
                             texto(fila["SEXO"]) or SIN_DATO)
    return salida


def _investigaciones(tabla):
    """ID de caso → datos de su investigación más temprana.

    Un caso puede tener varias: la que cuenta para medir la oportunidad es la
    primera, que es cuando PCI llegó a él.
    """
    salida = {}
    for _, fila in tabla.iterrows():
        clave = texto(fila["ID_CASO"])
        if not clave:
            continue
        inicio = fecha(fila["FECHA_INVESTIGACION"])
        actual = salida.get(clave)
        if actual and actual["inicio"] and inicio and actual["inicio"] <= inicio:
            continue
        salida[clave] = {
            "inicio": inicio,
            "cierre": fecha(fila["FECHA_CIERRE"]),
            "cronicas": multi(fila["ENFERMEDADES_CRONICAS"]),
        }
    return salida


def _dispositivos(tabla):
    """ID de caso → [{tipo, dias, bundle}] con el «Sí/Si» ya unificado."""
    salida = {}
    for _, fila in tabla.iterrows():
        clave = texto(fila["ID_CASO"])
        tipo = texto(fila["TIPO_DISPOSITIVO"])
        if not clave or not tipo:
            continue
        presente = texto(fila["PRESENTE"]).lower().rstrip(".")
        if presente in ("no",):
            continue
        crudo = texto(fila["DIAS_EXPOSICION"]).replace(",", ".")
        try:
            dias = int(float(crudo)) if crudo else None
        except ValueError:
            dias = None
        # El sistema acepta «Sí» y «Si» en el mismo campo; contarlos aparte
        # partiría el cumplimiento de bundles en dos columnas.
        bundle = texto(fila["CUMPLE_BUNDLE"]).lower().rstrip(".")
        bundle = {"sí": True, "si": True, "no": False}.get(bundle)
        salida.setdefault(clave, []).append(
            {"tipo": tipo, "dias": dias, "bundle": bundle})
    return salida


def limpiar(libro):
    """Una fila por caso vigilable. Solo salen las columnas de la lista blanca.

    Lo que no está aquí no se copia: una columna nueva en el sistema no se
    publica por descuido, que es el comportamiento que hace falta por defecto
    en una página pública.
    """
    casos, rescatadas = _rescatar_fechas(
        libro["CASOS_IAAS"], libro["KOBO_SEGUIMIENTO"])
    pacientes = _pacientes(libro["PACIENTES"])
    investigaciones = _investigaciones(libro["INVESTIGACIONES"])
    dispositivos = _dispositivos(libro["DISPOSITIVOS"])

    filas = []
    descartados = 0
    personas = set()
    for _, caso in casos.iterrows():
        if texto(caso["ARCHIVADO"]).upper() == "TRUE":
            descartados += 1
            continue
        if texto(caso["NOMBRE_PACIENTE"]).upper() == PACIENTE_PRUEBA:
            descartados += 1
            continue
        clave = texto(caso["ID_CASO"])
        notificacion = fecha(caso["FECHA_NOTIFICACION"])
        ingreso = fecha(caso["FECHA_INGRESO"])
        investigacion = investigaciones.get(clave, {})
        id_paciente = texto(caso["ID_PACIENTE"])
        nacimiento, sexo = pacientes.get(id_paciente, (None, SIN_DATO))
        if id_paciente:
            personas.add(id_paciente)

        filas.append({
            "dia": _dia(notificacion),
            "definicion": texto(caso["DEFINICION_CASO"]) or SIN_DATO,
            "servicio": texto(caso["SERVICIO"]) or SIN_DATO,
            "ubicacion": texto(caso["UBICACION"]) or SIN_DATO,
            "diagnostico": texto(caso["DIAGNOSTICO_IAAS"]) or SIN_DATO,
            "origen": texto(caso["ORIGEN_IAAS"]) or SIN_DATO,
            "condicion": texto(caso["CONDICION"]) or SIN_DATO,
            "vigepes": texto(caso["VIGEPES_08"]) or SIN_DATO,
            "sexo": sexo,
            "edad": _tramo_edad(nacimiento, notificacion or ingreso),
            "fuente": texto(caso["FUENTE_ORIGEN"]) or SIN_DATO,
            "herida": texto(caso["CLASIFICACION_HERIDA"]) or SIN_DATO,
            "intervencion": texto(caso["TIPO_INTERVENCION"]) or SIN_DATO,
            "procedimiento": texto(caso["PROCEDIMIENTO_ISQ"]) or SIN_DATO,
            "microorganismos": multi(caso["MICROORGANISMO_RESUMEN"]),
            "causas": multi(caso["CAUSA_RAIZ"]),
            "cronicas": investigacion.get("cronicas", []),
            "dispositivos": dispositivos.get(clave, []),
            "investigado": bool(investigacion),
            "cerrado": investigacion.get("cierre") is not None,
            # Los tres intervalos que miden el proceso: cuánto tarda el caso en
            # detectarse, en investigarse y en llegar a VIGEPES.
            "deteccion": _entre(ingreso, notificacion),
            "a_investigacion": _entre(notificacion, investigacion.get("inicio")),
            "a_vigepes": _entre(notificacion, fecha(caso["FECHA_VIGEPES_08"])),
        })
    return filas, {"descartados": descartados, "personas": len(personas),
                   "fechas_rescatadas": rescatadas}


# ---------------------------------------------------------------------------
# Codificación
# ---------------------------------------------------------------------------

# Campos de un solo valor por caso: cada uno es una dimensión filtrable.
SIMPLES = [
    "definicion", "servicio", "ubicacion", "diagnostico", "origen",
    "condicion", "vigepes", "sexo", "edad", "fuente", "herida",
    "intervencion", "procedimiento", "mes", "semana",
]

# Campos con varios valores por caso: viajan como matriz etiqueta × caso, que
# es lo que permite filtrar y contar sin repetir la fila del caso.
MULTIPLES = {
    "microorganismo": "microorganismos",
    "causa": "causas",
    "cronica": "cronicas",
}


def _periodos(filas):
    """Mes y semana ISO de cada caso; los casos sin fecha quedan aparte."""
    meses, semanas = [], []
    for f in filas:
        if f["dia"] is None:
            meses.append(SIN_DATO)
            semanas.append(SIN_DATO)
            continue
        momento = pd.Timestamp("1970-01-01") + pd.Timedelta(days=f["dia"])
        calendario = momento.isocalendar()
        meses.append(f"{momento:%Y-%m}")
        semanas.append(f"{calendario.year}-W{calendario.week:02d}")
    return meses, semanas


def _categorico(valores):
    """(categorías ordenadas, índice por fila). Alfabético: build determinista."""
    categorias = sorted(set(valores))
    indice = {v: i for i, v in enumerate(categorias)}
    return categorias, [indice[v] for v in valores]


def construir(libro=ID_LIBRO):
    """Descarga, valida, limpia y codifica. Devuelve el bloque DATA.iaas."""
    hojas = validar(descargar(libro))
    filas, extra = limpiar(hojas)

    # Casos que existen y ninguno con definición conocida significa que la
    # lista de opciones cambió, no que no haya habido IAAS: el campo es
    # obligatorio. Sin esta comprobación el apartado publicaría un cero limpio
    # y creíble.
    if filas and not any(f["definicion"] in DEFINICIONES for f in filas):
        raise IaasError(
            f"Ninguno de los {len(filas)} casos trae una «Definición de caso» "
            f"conocida: se esperaba alguna de {DEFINICIONES}. La lista de "
            "opciones del sistema dejó de coincidir con el manifiesto de "
            "iaas.py."
        )

    meses, semanas = _periodos(filas)
    for fila, mes, semana in zip(filas, meses, semanas):
        fila["mes"] = mes
        fila["semana"] = semana

    dims = {}
    rows = {}
    for clave in SIMPLES:
        dims[clave], rows[clave] = _categorico([f[clave] for f in filas])

    for clave, campo in MULTIPLES.items():
        etiquetas = sorted({v for f in filas for v in f[campo]})
        dims[clave] = etiquetas
        indice = {v: i for i, v in enumerate(etiquetas)}
        matriz = [[0] * len(filas) for _ in etiquetas]
        for i, f in enumerate(filas):
            for valor in f[campo]:
                matriz[indice[valor]][i] = 1
        rows[clave] = matriz

    # Los dispositivos son el único bloque con denominador: días de exposición
    # por caso, no solo presencia. Van como tres matrices paralelas para poder
    # recalcular la densidad con cualquier filtro puesto.
    tipos = sorted({d["tipo"] for f in filas for d in f["dispositivos"]}
                   | set(DISPOSITIVOS_INVASIVOS))
    dims["dispositivo"] = tipos
    indice_tipo = {t: i for i, t in enumerate(tipos)}
    presente = [[0] * len(filas) for _ in tipos]
    dias_disp = [[0] * len(filas) for _ in tipos]
    bundle_si = [[0] * len(filas) for _ in tipos]
    bundle_no = [[0] * len(filas) for _ in tipos]
    for i, f in enumerate(filas):
        for d in f["dispositivos"]:
            t = indice_tipo[d["tipo"]]
            presente[t][i] = 1
            dias_disp[t][i] += d["dias"] or 0
            if d["bundle"] is True:
                bundle_si[t][i] += 1
            elif d["bundle"] is False:
                bundle_no[t][i] += 1
    rows["dispositivo"] = presente
    rows["dispositivo_dias"] = dias_disp
    rows["bundle_si"] = bundle_si
    rows["bundle_no"] = bundle_no

    rows["dia"] = [f["dia"] for f in filas]
    rows["investigado"] = [1 if f["investigado"] else 0 for f in filas]
    rows["cerrado"] = [1 if f["cerrado"] else 0 for f in filas]
    for clave in ("deteccion", "a_investigacion", "a_vigepes"):
        rows[clave] = [f[clave] for f in filas]

    dias = [f["dia"] for f in filas if f["dia"] is not None]
    confirmados = sum(1 for f in filas if f["definicion"] == CONFIRMADO)

    return {
        "ok": True,
        "dims": dims,
        "rows": rows,
        "etiquetas": {
            "confirmado": CONFIRMADO,
            "sospechoso": SOSPECHOSO,
            "no_iaas": NO_IAAS,
            "sin_dato": SIN_DATO,
            "invasivos": DISPOSITIVOS_INVASIVOS,
        },
        "meta": {
            "generado": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
            "casos": len(filas),
            "confirmados": confirmados,
            "pacientes": extra["personas"],
            "descartados": extra["descartados"],
            "fechas_rescatadas": extra["fechas_rescatadas"],
            "sin_fecha": sum(1 for f in filas if f["dia"] is None),
            "dia_min": min(dias) if dias else 0,
            "dia_max": max(dias) if dias else 0,
        },
    }
