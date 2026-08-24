# PCI-STATS — Dashboard de supervisiones

Genera un dashboard HTML interactivo y autocontenido a partir de `SupPCI.xlsx`.

## Uso

    python build_dashboard.py

Escribe `dashboard.html` en la raíz del repositorio. El archivo no necesita
conexión ni servidor: se abre con doble clic y se puede enviar por correo.

Para usar otro libro:

    python build_dashboard.py ruta/al/otro.xlsx

## Qué contiene el dashboard

- **Global** — comparación entre responsables, evolución mensual y mapa de
  calor de submedida por mes.
- **Por responsable** — volumen por mes y por semana, evolución del
  cumplimiento contra la referencia del conjunto, y desglose por medida,
  submedida, unidad/servicio, área específica, grupo ocupacional y cargo.
- **Por formulario** — evolución, desgloses, estado de validación, nivel de
  riesgo, motivos de no cumplimiento y la tabla de registros individuales.

Los filtros de la barra superior afectan a las tres vistas a la vez.

## Métrica

La tasa de cumplimiento es el porcentaje de supervisiones con
`CUMPLE_CORRECTAMENTE = SI` sobre las que tienen dictamen. Los registros sin
dictamen se excluyen del denominador y se reportan por separado; nunca cuentan
como incumplimiento.

## Pruebas

    python -m pytest tests/ -v

Y abrir `tests/test_agg.html` en el navegador para las pruebas de agregación.

## Si el build falla

`build_dashboard.py` aborta a propósito cuando el Excel cambia de forma:
columna faltante, un valor nuevo en `CUMPLE_CORRECTAMENTE`, un porcentaje
fuera de 0-100, un formulario con `METODO_CUMPLIMIENTO` distinto de
`SI_NO_NA`, o un responsable nuevo con nombre en formato slug. El mensaje dice
qué encontró. Prefiere fallar a generar un dashboard con cifras equivocadas.

Los nombres en formato slug se corrigen añadiéndolos a `SLUG_NAME_MAP` en
`build_dashboard.py`, con su acentuación correcta.

## Diseño

`docs/superpowers/specs/2026-08-24-dashboard-supervisiones-design.md`
