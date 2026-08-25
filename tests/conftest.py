from pathlib import Path

import pandas as pd
import pytest

import build_dashboard as bd


# Única prueba con permiso de red de toda la suite: si el export local
# SupPCI.xlsx falta (el caso normal en CI, donde el archivo está en
# .gitignore) descarga el Sheet en vivo una sola vez y comparte esa ruta
# entre todas las pruebas de la sesión. Todas las demás pruebas siguen
# mockeando requests.get.
@pytest.fixture(scope="session")
def libro_real(tmp_path_factory):
    """Ruta a un libro real: el export local si está, si no el Sheet en vivo.

    Las pruebas que lo usan comprueban invariantes que valen para cualquier
    libro válido, no cifras de un archivo concreto, así que sirve cualquiera
    de los dos. Es la única descarga de red de toda la suite y solo ocurre
    cuando el export local falta, que en la práctica es únicamente en CI.
    """
    local = Path(__file__).resolve().parent.parent / "SupPCI.xlsx"
    if local.exists():
        return local
    destino = tmp_path_factory.mktemp("libro") / "sheet.xlsx"
    return bd._descargar_sheet(bd.ID_DOCUMENTO, destino)


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
