# PCI-STATS — Dashboard de supervisiones

Genera un dashboard HTML interactivo y autocontenido a partir de `SupPCI.xlsx`.

## Uso

Chart.js se vendoriza pero no se versiona (`vendor/*.js` está en
`.gitignore`): en un clon nuevo hay que descargarlo antes del primer build.

    curl -L https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js -o vendor/chart.umd.min.js
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

`build_dashboard.py` aborta a propósito cuando el Excel cambia de forma. El
mensaje dice qué encontró. Prefiere fallar a generar un dashboard con cifras
equivocadas. Motivos posibles:

- Falta la hoja `REGISTROS` o `FORMULARIOS`, o una columna esperada en
  cualquiera de las dos.
- Una columna de dimensión (`RESPONSABLE`, `MEDIDA`, `SUBMEDIDA`,
  `UNIDAD_SERVICIO_APLICACION`, `GRUPO_OCUPACIONAL`, `CARGO`,
  `ESTADO_VALIDACION`) trae un nulo: un nulo ahí se codificaría como una
  categoría fantasma en el JavaScript.
- Un valor nuevo en `CUMPLE_CORRECTAMENTE` (solo se interpretan `SI`, `NO` y
  nulo) o en `ESTADO_VALIDACION` (solo `Aprobado` y `En espera`).
- Un `PORCENTAJE_CUMPLIMIENTO` fuera de 0-100, o con decimales: se codifica
  con `int()` y un valor como `92.5` se truncaría en silencio.
- Un `FECHA_EVENTO` que no se puede interpretar como fecha, o fuera del
  rango 2020-01-01 hasta mañana.
- Un formulario usado en `REGISTROS` con `METODO_CUMPLIMIENTO` distinto de
  `SI_NO_NA`: ese método no calcula cumplimiento y no se puede promediar con
  los que sí.
- Un formulario usado en `REGISTROS` que no aparece en el catálogo
  `FORMULARIOS`.
- Un responsable nuevo con nombre en formato slug (falla la migración de
  acentos).
- Falta `vendor/chart.umd.min.js` — ver la sección Uso arriba.

Los nombres en formato slug se corrigen añadiéndolos a `SLUG_NAME_MAP` en
`build_dashboard.py`, con su acentuación correcta.

## Diseño

`docs/superpowers/specs/2026-08-24-dashboard-supervisiones-design.md`
