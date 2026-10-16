"""Importación de una sola vez: de la Hoja1 del Excel a los CSV del libro.

Uso:
    python scripts/importar_indicadores.py "INDICADOR INSTITUCIONAL.xlsx" salida/ --anio 2026

Escribe `salida/VALORES.csv` y `salida/METAS.csv`, listos para pegar en las
pestañas del libro de indicadores. Solo se importan N y D: T se recalcula
siempre. Los meses de la Hoja1 con T escrita a mano pero sin N o sin D se
avisan por la salida de error, para cargarlos después desde la página.
"""

import argparse
import csv
import sys
import unicodedata
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import indicadores  # noqa: E402

# Etiqueta de la Hoja1 (normalizada) → id del manifiesto. La Hoja1 no usa los
# mismos nombres que la hoja de definiciones, así que no se puede derivar.
FILAS = {
    "incidencia de iaas": "incidencia_iaas",
    "densidad de incidencia de iaas": "densidad_iaas",
    "bacteriemia asociada a cateter venoso central": "bacvc",
    "bacteriemia asociada a hemodialisis": "bacteriemia_hd",
    "peritonitis asociada a dialisis peritoneal": "peritonitis_dp",
    "neumonia asociada a ventilacion mecanica": "navm",
    "infeccion del tracto urinario asociada a cateter urinario": "ituacu",
    "infeccion del sitio quirurgico": "isq",
    "colitis pseudomembranosa por c. difficile": "colitis_cdiff",
}

MESES = {m: i + 1 for i, m in enumerate([
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre"])}


def normalizar(texto):
    sin_acentos = unicodedata.normalize("NFKD", str(texto or ""))
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def _numero(valor):
    """N o D de una celda. Las fórmulas (T) no pasan por aquí."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return int(valor) if float(valor).is_integer() else valor
    return float(str(valor).replace(",", "."))


def leer(ruta, anio):
    hoja = openpyxl.load_workbook(ruta)["Hoja1"]
    cabecera = [normalizar(c.value) for c in hoja[1]]
    # Índice de la columna N de cada mes; D y T son las dos siguientes.
    columnas_mes = {i: MESES[t] for i, t in enumerate(cabecera) if t in MESES}
    col_meta = next((i for i, t in enumerate(cabecera) if t == "meta"), None)

    valores, metas, avisos = [], [], []
    for fila in hoja.iter_rows(min_row=3, values_only=True):
        etiqueta = normalizar(fila[0])
        if not etiqueta:
            continue
        if etiqueta not in FILAS:
            raise SystemExit(f"Fila desconocida en la Hoja1: {fila[0]!r}")
        ind = FILAS[etiqueta]
        for i, mes in sorted(columnas_mes.items()):
            n, d = _numero(fila[i]), _numero(fila[i + 1])
            t = fila[i + 2]
            if t is not None and (n is None or d is None):
                avisos.append(f"{ind}, mes {mes}: la Hoja1 trae T ({t}) sin N "
                              "o sin D; esa T no se importa.")
            if n is None and d is None:
                continue
            valores.append({"ANIO": anio, "MES": mes, "INDICADOR": ind,
                            "NUMERADOR": "" if n is None else n,
                            "DENOMINADOR": "" if d is None else d})
        if col_meta is not None and _numero(fila[col_meta]) is not None:
            metas.append({"ANIO": anio, "INDICADOR": ind,
                          "META": _numero(fila[col_meta])})
    valores.sort(key=lambda v: (v["MES"], indicadores.IDS.index(v["INDICADOR"])))
    return valores, metas, avisos


def escribir(valores, metas, destino):
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, filas in (("VALORES", valores), ("METAS", metas)):
        with open(destino / f"{nombre}.csv", "w", newline="", encoding="utf-8") as f:
            escritor = csv.DictWriter(f, fieldnames=indicadores.HOJAS[nombre])
            escritor.writeheader()
            escritor.writerows(filas)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("excel")
    p.add_argument("destino")
    p.add_argument("--anio", type=int, default=2026)
    args = p.parse_args(argv)
    valores, metas, avisos = leer(args.excel, args.anio)
    escribir(valores, metas, args.destino)
    for aviso in avisos:
        print(f"AVISO: {aviso}", file=sys.stderr)
    print(f"{len(valores)} valores y {len(metas)} metas escritos en {args.destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
