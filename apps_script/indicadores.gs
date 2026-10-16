/**
 * Indicadores institucionales de PCI: lectura y escritura del libro.
 *
 * Se pega en Extensiones → Apps Script del libro de indicadores y se despliega
 * como aplicación web («Ejecutar como: yo», «Quién tiene acceso: cualquier
 * usuario»). La clave del equipo va en Configuración del proyecto →
 * Propiedades del script → CLAVE; nunca en este archivo.
 *
 * Las funciones de validación no tocan SpreadsheetApp: tests/test_apps_script.py
 * las carga con node. La lista de ids debe coincidir con indicadores.py; esa
 * misma prueba lo comprueba.
 */

const INDICADORES = [
  'incidencia_iaas', 'densidad_iaas', 'bacvc', 'bacteriemia_hd',
  'peritonitis_dp', 'navm', 'ituacu', 'isq', 'colitis_cdiff',
  'proporcion_dispositivo',
];
const ANIO_MIN = 2020;
const ANIO_MAX = 2100;
const CABECERAS = {
  VALORES: ['ANIO', 'MES', 'INDICADOR', 'NUMERADOR', 'DENOMINADOR'],
  METAS: ['ANIO', 'INDICADOR', 'META'],
  CONTROL: ['ANIO', 'ACTUALIZADO'],
};
const MENSAJE_CONFLICTO =
  'Otra persona guardó cambios en este año; recarga para verlos';

// --- Funciones puras -------------------------------------------------------

function esNumeroValido(x) {
  return x === null || (typeof x === 'number' && isFinite(x) && x >= 0);
}

/** null si la petición es válida; si no, el motivo. No mira la clave. */
function validarPeticion(cuerpo) {
  if (!cuerpo || typeof cuerpo !== 'object') return 'Petición vacía';
  const anio = cuerpo.anio;
  if (!Number.isInteger(anio) || anio < ANIO_MIN || anio > ANIO_MAX) {
    return 'Año fuera de rango: ' + anio;
  }
  if (!Array.isArray(cuerpo.valores) || !Array.isArray(cuerpo.metas)) {
    return 'Faltan valores o metas';
  }
  const vistos = {};
  for (const v of cuerpo.valores) {
    if (!Number.isInteger(v.mes) || v.mes < 1 || v.mes > 12) {
      return 'Mes fuera de rango: ' + v.mes;
    }
    if (INDICADORES.indexOf(v.indicador) < 0) {
      return 'Indicador desconocido: ' + v.indicador;
    }
    if (!esNumeroValido(v.n) || !esNumeroValido(v.d)) {
      return 'Valor no válido en ' + v.indicador + ', mes ' + v.mes;
    }
    const clave = v.indicador + '|' + v.mes;
    if (vistos[clave]) return 'Repetido: ' + clave;
    vistos[clave] = true;
  }
  for (const m of cuerpo.metas) {
    if (INDICADORES.indexOf(m.indicador) < 0) {
      return 'Indicador desconocido: ' + m.indicador;
    }
    if (m.meta === null || !esNumeroValido(m.meta)) {
      return 'Meta no válida en ' + m.indicador;
    }
  }
  return null;
}

/** La página guarda sobre lo que leyó; si el año cambió desde entonces, no. */
function hayConflicto(control, anio, actualizado) {
  return (control[String(anio)] || '') !== (actualizado || '');
}

function aCelda(x) { return x === null ? '' : x; }
function deCelda(x) { return x === '' || x === null ? null : Number(x); }

// --- Libro -----------------------------------------------------------------

function hoja(nombre) {
  return SpreadsheetApp.getActiveSpreadsheet().getSheetByName(nombre);
}

/** Filas de datos de una pestaña, sin cabecera ni filas vacías. */
function leerFilas(nombre) {
  return hoja(nombre).getDataRange().getValues().slice(1)
    .filter(f => f[0] !== '');
}

function leerTodo() {
  const valores = leerFilas('VALORES').map(f => ({
    anio: Number(f[0]), mes: Number(f[1]), indicador: String(f[2]),
    n: deCelda(f[3]), d: deCelda(f[4]),
  }));
  const metas = leerFilas('METAS').map(f => ({
    anio: Number(f[0]), indicador: String(f[1]), meta: deCelda(f[2]),
  })).filter(m => m.meta !== null);
  const control = {};
  leerFilas('CONTROL').forEach(f => { control[String(f[0])] = String(f[1]); });
  return {valores, metas, control};
}

/** Reemplaza las filas del año `anio` de una pestaña por `nuevas`. */
function reescribir(nombre, anio, nuevas) {
  const cabecera = CABECERAS[nombre];
  const resto = leerFilas(nombre).filter(f => Number(f[0]) !== anio);
  const todas = [cabecera].concat(resto, nuevas);
  const h = hoja(nombre);
  h.clearContents();
  h.getRange(1, 1, todas.length, cabecera.length).setValues(todas);
}

function responder(objeto) {
  return ContentService.createTextOutput(JSON.stringify(objeto))
    .setMimeType(ContentService.MimeType.JSON);
}

// --- Web app ---------------------------------------------------------------

function doGet() {
  try {
    return responder(Object.assign({ok: true}, leerTodo()));
  } catch (error) {
    return responder({ok: false, error: String(error)});
  }
}

function doPost(e) {
  let cuerpo;
  try {
    cuerpo = JSON.parse(e.postData.contents);
  } catch (error) {
    return responder({ok: false, error: 'Petición ilegible'});
  }
  const clave = PropertiesService.getScriptProperties().getProperty('CLAVE');
  if (!clave || cuerpo.clave !== clave) {
    return responder({ok: false, error: 'Clave incorrecta'});
  }
  const motivo = validarPeticion(cuerpo);
  if (motivo) return responder({ok: false, error: motivo});

  const cerrojo = LockService.getScriptLock();
  if (!cerrojo.tryLock(10000)) {
    return responder({ok: false, error: 'El libro está ocupado; inténtalo de nuevo'});
  }
  try {
    const anio = cuerpo.anio;
    if (hayConflicto(leerTodo().control, anio, cuerpo.actualizado)) {
      return responder({ok: false, conflicto: true, error: MENSAJE_CONFLICTO});
    }
    reescribir('VALORES', anio, cuerpo.valores.map(v =>
      [anio, v.mes, v.indicador, aCelda(v.n), aCelda(v.d)]));
    reescribir('METAS', anio, cuerpo.metas.map(m => [anio, m.indicador, m.meta]));
    // Como texto: si Sheets convierte la marca en fecha, deja de coincidir con
    // la que la página leyó y todo guardado posterior sería un conflicto.
    hoja('CONTROL').getRange('B:B').setNumberFormat('@');
    const actualizado = new Date().toISOString();
    reescribir('CONTROL', anio, [[anio, actualizado]]);
    return responder({ok: true, anio, valores: cuerpo.valores,
                      metas: cuerpo.metas, actualizado});
  } finally {
    cerrojo.releaseLock();
  }
}
