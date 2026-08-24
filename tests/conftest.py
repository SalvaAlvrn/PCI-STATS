import pandas as pd
import pytest


@pytest.fixture
def registros_ok():
    """Cuatro filas válidas: dos cumplen, una no, una sin dictamen."""
    return pd.DataFrame(
        {
            "ID_REGISTRO": ["R1", "R2", "R3", "R4"],
            "FECHA_REGISTRO": pd.to_datetime(
                ["2026-07-02", "2026-07-03", "2026-07-04", "2026-08-01"]
            ),
            "FECHA_EVENTO": pd.to_datetime(
                ["2026-07-01", "2026-07-02", "2026-07-03", "2026-08-01"]
            ),
            "ID_FORMULARIO": ["F001", "F001", "F002", "F002"],
            "VERSION_FORMULARIO": [1, 1, 2, 2],
            "FORMULARIO": ["Lavado", "Lavado", "Guantes", "Guantes"],
            "MEDIDA": ["Medidas estándar"] * 4,
            "SUBMEDIDA": ["Higiene", "Higiene", "Barreras", "Barreras"],
            "RESPONSABLE": [
                "Ana Pérez",
                "ana_mar_a_p_rez_g_mez",
                "Ana Pérez",
                "Ana Pérez",
            ],
            "UNIDAD_SERVICIO_APLICACION": ["UCI", "UCI", "Emergencia", "UCI"],
            "AREA_ESPECIFICA_APLICACION": ["Box 1", None, "Triage", "Box 2"],
            "GRUPO_OCUPACIONAL": ["Enfermería"] * 4,
            "CARGO": ["Técnico(a) operativo"] * 4,
            "NOMBRE_EVALUADO": ["Juan", "Luis", "Marta", "Rosa"],
            "PORCENTAJE_CUMPLIMIENTO": [100, 60, 100, 90],
            "TOTAL_SI": [5, 3, 4, 4],
            "TOTAL_NO": [0, 2, 0, 1],
            "TOTAL_NA": [1, 1, 2, 0],
            "TOTAL_PENDIENTES": [0, 0, 0, 0],
            "CUMPLE_CORRECTAMENTE": ["SI", "NO", "SI", None],
            "MOTIVO_NO_CUMPLIMIENTO": [None, "Sin insumos", None, None],
            "CONCLUSIONES_RECOMENDACIONES": [None, "Reponer jabón", None, None],
            "ESTADO_VALIDACION": ["Aprobado", "En espera", "En espera", "En espera"],
            "NIVEL_RIESGO": [None, "Alto", None, None],
        }
    )


@pytest.fixture
def nombres_ok():
    """Mapa de normalización con nombres ficticios."""
    return {
        "ana_mar_a_p_rez_g_mez": "Ana María Pérez Gómez",
        "luis_fernando_l_pez_d_az": "Luis Fernando López Díaz",
    }


@pytest.fixture
def formularios_ok():
    """F001 con una versión; F002 con dos y cambio de nombre entre ellas."""
    return pd.DataFrame(
        {
            "ID_FORMULARIO": ["F001", "F002", "F002"],
            "VERSION_FORMULARIO": [1, 1, 2],
            "MEDIDA": ["Medidas estándar"] * 3,
            "SUBMEDIDA": ["Higiene", "Barreras", "Barreras"],
            "NOMBRE_FORMULARIO": ["Lavado", "Guantes viejo", "Guantes"],
            "METODO_CUMPLIMIENTO": ["SI_NO_NA"] * 3,
            "ES_VERSION_ACTUAL": [True, False, True],
        }
    )
