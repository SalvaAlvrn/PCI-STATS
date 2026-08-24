"""Genera dashboard.html a partir de SupPCI.xlsx.

Pipeline: load -> validate -> clean -> encode -> render_html.
Ver docs/superpowers/specs/2026-08-24-dashboard-supervisiones-design.md
"""

from pathlib import Path

import pandas as pd


class BuildError(Exception):
    """La estructura del Excel no es la esperada. Aborta el build."""


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
