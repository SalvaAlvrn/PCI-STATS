"""Pruebas del apartado de vigilancia de IAAS.

El libro falso reproduce lo que hace peligrosa a la fuente real: fechas en
tres formatos en la misma columna, «Sí» y «Si» conviviendo en el mismo campo,
casos migrados a los que la migración dejó sin fecha de notificación, y datos
de paciente en casi todas las hojas.
"""

from unittest.mock import patch

import pandas as pd
import pytest

import iaas


PACIENTE = "PACIENTE_SINTETICO_XYZ"


def hoja(filas, columnas):
    """DataFrame de texto con todas las columnas del manifiesto presentes."""
    completas = []
    for fila in filas:
        completa = {c: "" for c in columnas}
        completa.update(fila)
        completas.append(completa)
    return pd.DataFrame(completas, columns=columnas, dtype=str).fillna("")


def libro_falso(casos=None, dispositivos=None, investigaciones=None,
                kobo=None, pacientes=None):
    caso_base = {
        "ID_CASO": "C1", "ID_PACIENTE": "P1",
        "FECHA_NOTIFICACION": "05/06/2026", "FECHA_INGRESO": "01/06/2026",
        "ORIGEN_IAAS": "Extrahospitalario",
        "DIAGNOSTICO_IAAS": "Neumonía Asociada a Ventilación Mecánica",
        "DEFINICION_CASO": iaas.CONFIRMADO,
        "DISPOSITIVO_RESUMEN": "Ventilación Mecánica",
        "MICROORGANISMO_RESUMEN": "Klebsiella pneumoniae | Escherichia coli",
        "SERVICIO": "Unidad de Cuidados Intensivos", "UBICACION": "UCI General",
        "CONDICION": "Vivo", "VIGEPES_08": "Sí",
        "FECHA_VIGEPES_08": "08/06/2026",
        "CAUSA_RAIZ": "Desviaciones en medidas estándar | Condiciones ambientales",
        "TIPO_INTERVENCION": "", "PROCEDIMIENTO_ISQ": "",
        "CLASIFICACION_HERIDA": "", "FUENTE_ORIGEN": "SISTEMA",
        "KOBO_UUID": "", "ARCHIVADO": "FALSE", "NOMBRE_PACIENTE": PACIENTE,
        # Columnas que existen en el libro real y no deben salir nunca.
        "EXPEDIENTE": "EXP-999999", "CAMA": "42",
        "OBSERVACIONES": "OBSERVACION_SINTETICA_XYZ",
        "DIAGNOSTICO_CIE10": "CIE_SINTETICO_XYZ",
        # Texto libre: en el libro real hay frases enteras escritas aquí.
        "LUGAR_ORIGEN_EXTRA": "LUGAR_SINTETICO_XYZ",
    }
    columnas_casos = iaas.HOJAS["CASOS_IAAS"] + [
        "EXPEDIENTE", "CAMA", "OBSERVACIONES", "DIAGNOSTICO_CIE10",
        "LUGAR_ORIGEN_EXTRA"]
    return {
        "CASOS_IAAS": hoja(casos if casos is not None else [caso_base],
                           columnas_casos),
        "PACIENTES": hoja(
            pacientes if pacientes is not None else
            [{"ID_PACIENTE": "P1", "FECHA_NACIMIENTO": "01/01/1980",
              "SEXO": "Femenino", "NOMBRE": PACIENTE}],
            iaas.HOJAS["PACIENTES"] + ["NOMBRE"]),
        "DISPOSITIVOS": hoja(dispositivos or [], iaas.HOJAS["DISPOSITIVOS"]),
        "INVESTIGACIONES": hoja(investigaciones or [],
                                iaas.HOJAS["INVESTIGACIONES"]),
        iaas.HOJA_KOBO: hoja(kobo or [], iaas.HOJAS[iaas.HOJA_KOBO]),
    }


def construir(**kwargs):
    with patch("iaas.descargar", return_value=libro_falso(**kwargs)):
        return iaas.construir()


# --- forma de la fuente ----------------------------------------------------

def test_validar_falla_si_falta_una_columna_del_manifiesto():
    libro = libro_falso()
    libro["CASOS_IAAS"] = libro["CASOS_IAAS"].drop(columns=["DEFINICION_CASO"])
    with pytest.raises(iaas.IaasError, match="DEFINICION_CASO"):
        iaas.validar(libro)


def test_descargar_falla_con_las_hojas_a_la_vista_si_una_no_existe():
    """Google devuelve la primera hoja cuando el nombre no existe.

    Sin este control, un renombrado se leería como una hoja vacía de casos y
    el apartado saldría a cero sin decir por qué.
    """
    indice = {"CASOS_IAAS": "1", "PACIENTES": "2"}
    with patch("iaas.indice_de_hojas", return_value=indice):
        with pytest.raises(iaas.IaasError, match="DISPOSITIVOS"):
            iaas.descargar()


def test_construir_falla_si_ninguna_definicion_es_conocida():
    caso = {"ID_CASO": "C1", "DEFINICION_CASO": "Otra cosa",
            "FECHA_NOTIFICACION": "05/06/2026", "ARCHIVADO": "FALSE"}
    with pytest.raises(iaas.IaasError, match="Definición de caso"):
        construir(casos=[caso])


# --- fechas ----------------------------------------------------------------

@pytest.mark.parametrize("crudo,esperado", [
    ("05/06/2026", (2026, 6, 5)),
    ("5/6/2026", (2026, 6, 5)),
    ("05/06/2026 15:37", (2026, 6, 5)),
    ("2026-06-05", (2026, 6, 5)),
    ("2026-06-05T06:00:00.000Z", (2026, 6, 5)),
])
def test_fecha_acepta_los_formatos_que_el_libro_mezcla(crudo, esperado):
    momento = iaas.fecha(crudo)
    assert (momento.year, momento.month, momento.day) == esperado


def test_fecha_vacia_es_none_y_fecha_ilegible_falla():
    assert iaas.fecha("") is None
    with pytest.raises(iaas.IaasError):
        iaas.fecha("junio")
    with pytest.raises(iaas.IaasError, match="imposible"):
        iaas.fecha("31/02/2026")


# --- descartes -------------------------------------------------------------

def test_los_archivados_y_la_fila_de_prueba_no_cuentan():
    casos = [
        {"ID_CASO": "C1", "DEFINICION_CASO": iaas.CONFIRMADO,
         "FECHA_NOTIFICACION": "05/06/2026", "ARCHIVADO": "FALSE",
         "NOMBRE_PACIENTE": PACIENTE},
        {"ID_CASO": "C2", "DEFINICION_CASO": iaas.CONFIRMADO,
         "FECHA_NOTIFICACION": "06/06/2026", "ARCHIVADO": "TRUE",
         "NOMBRE_PACIENTE": PACIENTE},
        {"ID_CASO": "C3", "DEFINICION_CASO": iaas.CONFIRMADO,
         "FECHA_NOTIFICACION": "07/06/2026", "ARCHIVADO": "FALSE",
         "NOMBRE_PACIENTE": "TEST"},
    ]
    data = construir(casos=casos)
    assert data["meta"]["casos"] == 1
    assert data["meta"]["descartados"] == 2


def test_un_caso_cuyo_texto_menciona_test_no_se_descarta():
    casos = [{"ID_CASO": "C1", "DEFINICION_CASO": iaas.CONFIRMADO,
              "FECHA_NOTIFICACION": "05/06/2026", "ARCHIVADO": "FALSE",
              "NOMBRE_PACIENTE": "TESTA MARTINEZ"}]
    assert construir(casos=casos)["meta"]["casos"] == 1


# --- rescate de fechas -----------------------------------------------------

def test_las_fechas_que_la_migracion_perdio_se_rescatan_del_export_de_kobo():
    casos = [{"ID_CASO": "C1", "DEFINICION_CASO": iaas.CONFIRMADO,
              "FECHA_NOTIFICACION": "", "FECHA_INGRESO": "",
              "KOBO_UUID": "u-1", "ARCHIVADO": "FALSE",
              "NOMBRE_PACIENTE": PACIENTE}]
    kobo = [{"_uuid": "u-1", "Fecha de notificación": "2026-06-05",
             "Fecha de ingreso": "2026-06-01"}]
    data = construir(casos=casos, kobo=kobo)
    assert data["meta"]["fechas_rescatadas"] == 1
    assert data["meta"]["sin_fecha"] == 0
    # Ingreso rescatado también: sin él no habría intervalo de detección.
    assert data["rows"]["deteccion"] == [4]


def test_sin_export_de_kobo_el_caso_migrado_se_queda_sin_fecha():
    casos = [{"ID_CASO": "C1", "DEFINICION_CASO": iaas.CONFIRMADO,
              "FECHA_NOTIFICACION": "", "KOBO_UUID": "u-1",
              "ARCHIVADO": "FALSE", "NOMBRE_PACIENTE": PACIENTE}]
    data = construir(casos=casos)
    assert data["meta"]["sin_fecha"] == 1
    assert data["rows"]["dia"] == [None]


# --- dispositivos ----------------------------------------------------------

def test_los_dispositivos_suman_dias_y_unifican_el_si_del_bundle():
    dispositivos = [
        {"ID_CASO": "C1", "TIPO_DISPOSITIVO": "Ventilación Mecánica",
         "PRESENTE": "Sí", "DIAS_EXPOSICION": "10", "CUMPLE_BUNDLE": "Sí"},
        {"ID_CASO": "C1", "TIPO_DISPOSITIVO": "Ventilación Mecánica",
         "PRESENTE": "Si", "DIAS_EXPOSICION": "5", "CUMPLE_BUNDLE": "Si"},
        {"ID_CASO": "C1", "TIPO_DISPOSITIVO": "Catéter Urinario",
         "PRESENTE": "No", "DIAS_EXPOSICION": "99", "CUMPLE_BUNDLE": "No"},
    ]
    data = construir(dispositivos=dispositivos)
    t = data["dims"]["dispositivo"].index("Ventilación Mecánica")
    u = data["dims"]["dispositivo"].index("Catéter Urinario")
    assert data["rows"]["dispositivo_dias"][t] == [15]
    assert data["rows"]["bundle_si"][t] == [2]
    # PRESENTE=No es un dispositivo que el paciente no tenía: no aporta días.
    assert data["rows"]["dispositivo"][u] == [0]
    assert data["rows"]["dispositivo_dias"][u] == [0]


# --- codificación ----------------------------------------------------------

def test_los_campos_de_seleccion_multiple_viajan_como_matriz():
    data = construir()
    micros = data["dims"]["microorganismo"]
    assert micros == ["Escherichia coli", "Klebsiella pneumoniae"]
    assert [fila[0] for fila in data["rows"]["microorganismo"]] == [1, 1]
    assert len(data["dims"]["causa"]) == 2


def test_los_intervalos_del_proceso_salen_en_dias():
    investigaciones = [{"ID_CASO": "C1", "FECHA_INVESTIGACION": "07/06/2026",
                        "FECHA_CIERRE": "10/06/2026",
                        "ENFERMEDADES_CRONICAS": "Diabetes | Cáncer"}]
    data = construir(investigaciones=investigaciones)
    assert data["rows"]["deteccion"] == [4]          # ingreso 01/06 → notif 05/06
    assert data["rows"]["a_investigacion"] == [2]    # notif 05/06 → inv 07/06
    assert data["rows"]["a_vigepes"] == [3]          # notif 05/06 → VIGEPES 08/06
    assert data["rows"]["investigado"] == [1]
    assert data["rows"]["cerrado"] == [1]
    assert data["dims"]["cronica"] == ["Cáncer", "Diabetes"]


def test_una_fecha_posterior_al_hito_no_produce_un_intervalo_negativo():
    """Un dato invertido es un error de captura, no un intervalo de -3 días."""
    casos = [{"ID_CASO": "C1", "DEFINICION_CASO": iaas.CONFIRMADO,
              "FECHA_NOTIFICACION": "05/06/2026", "FECHA_INGRESO": "08/06/2026",
              "ARCHIVADO": "FALSE", "NOMBRE_PACIENTE": PACIENTE}]
    assert construir(casos=casos)["rows"]["deteccion"] == [None]


def test_la_edad_sale_en_tramos_y_nunca_la_fecha_de_nacimiento():
    data = construir()
    assert data["dims"]["edad"] == ["45-59"]


def test_todas_las_columnas_paralelas_tienen_la_misma_longitud():
    casos = [
        {"ID_CASO": "C1", "DEFINICION_CASO": iaas.CONFIRMADO,
         "FECHA_NOTIFICACION": "05/06/2026", "ARCHIVADO": "FALSE",
         "NOMBRE_PACIENTE": PACIENTE},
        {"ID_CASO": "C2", "DEFINICION_CASO": iaas.NO_IAAS,
         "FECHA_NOTIFICACION": "06/06/2026", "ARCHIVADO": "FALSE",
         "NOMBRE_PACIENTE": PACIENTE},
    ]
    data = construir(casos=casos)
    n = data["meta"]["casos"]
    assert n == 2
    for clave in iaas.SIMPLES + ["dia", "deteccion", "investigado"]:
        assert len(data["rows"][clave]) == n, clave
    for clave in list(iaas.MULTIPLES) + ["dispositivo", "dispositivo_dias"]:
        for fila in data["rows"][clave]:
            assert len(fila) == n, clave
    assert data["meta"]["confirmados"] == 1


# --- privacidad ------------------------------------------------------------

def test_ningun_dato_de_paciente_llega_al_bloque_publicado():
    """La prueba que sostiene la promesa de privacidad del apartado.

    El libro trae nombre, expediente, cama y diagnóstico CIE-10 en la misma
    hoja que todo lo demás: lo que protege al paciente es la lista blanca de
    `limpiar`, y esto es lo que comprueba que sigue puesta.
    """
    import json

    data = construir()
    texto = json.dumps(data, ensure_ascii=False)
    assert PACIENTE not in texto
    assert "EXP-999999" not in texto
    assert "OBSERVACION_SINTETICA_XYZ" not in texto
    assert "CIE_SINTETICO_XYZ" not in texto
    # El establecimiento de procedencia es texto libre: no se publica ninguno.
    assert "LUGAR_SINTETICO_XYZ" not in texto
    for campo in iaas.CAMPOS_PROHIBIDOS:
        assert campo not in texto, campo
