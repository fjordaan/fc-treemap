/**
 * Fulham Cemetery tree map — combined Apps Script Web App
 *
 * Ported from park-treemap's apps-script.gs, adapted to this project's sheet
 * (tab "trees_master", "Tag"/"Photo" columns, per-row formulas) and to photos
 * being Google Photos URLs only — there is no file upload or GitHub storage.
 *
 * Handles these browser actions via a single Web App URL:
 *   1. action: 'feedback'       → appends a row to the Feedback sheet
 *   2. action: 'validateToken'  → checks a contributor token (enrolment)
 *   3. action: 'addTree'        → appends a tree row, fills its formulas, sorts the sheet
 *   4. action: 'editTree'       → updates editable fields of an existing tree row
 *   5. action: 'deleteTree'     → removes a tree's row
 *   6. action: 'repositionTree' → updates the Latitude and Longitude of a tree
 *   7. action: 'appendPhotos'   → adds Google Photos URLs to a tree's Photo cell
 *   8. action: 'removePhoto'    → strips one URL from a tree's Photo cell
 *   9. action: 'reorderPhotos'  → rewrites the order of a tree's Photo cell
 *
 * Every tree/photo action also appends a row to the History sheet (created
 * on first use) — see appendHistory().
 *
 * SETUP
 * -----
 * 1. In script.google.com create a new project and paste this entire file.
 * 2. Project Settings → Script Properties — add:
 *      CONTRIBUTOR_TOKEN  (a long random password; the magic enrolment link
 *                          is the map URL + ?enrol=<this token>)
 *    If CONTRIBUTOR_TOKEN is unset, every request is accepted (open mode).
 * 3. Deploy → New deployment → type "Web app":
 *      Execute as: Me
 *      Who has access: Anyone
 * 4. Copy the deployment URL into APPS_SCRIPT_URL in index.html.
 *
 * After editing this file later, use Deploy → Manage deployments → Edit →
 * Version: New version, so the /exec URL stays the same.
 */

const SHEET_ID       = '16056CHjRL4-hbd4hbIb1czvrryGKcwMFYWCDeMDDAHM'; // Fulham Cemetery tree master sheet
const TREES_SHEET    = 'trees_master';
const FEEDBACK_SHEET = 'Feedback';
const HISTORY_SHEET  = 'History';
const FIRST_DATA_ROW = 2; // row 1 is the header; formulas are per-row, so every data row sorts

// Appends a row whose first cell is the current time, displayed in the
// format the Feedback tab already uses (e.g. 2026-11-10 13:28:48).
function appendTimestampedRow(sheet, values) {
  sheet.appendRow([new Date()].concat(values));
  sheet.getRange(sheet.getLastRow(), 1).setNumberFormat('yyyy-mm-dd hh:mm:ss');
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// Trusted-contributor check. Returns a response to return early, or null
// when the request is allowed to proceed.
//   • If the CONTRIBUTOR_TOKEN Script Property is unset → all submissions
//     are accepted (open mode).
//   • If it is set → the request's `token` field must match exactly.
function requireContributorToken(data) {
  const expected = PropertiesService.getScriptProperties()
    .getProperty('CONTRIBUTOR_TOKEN');
  if (!expected) return null;
  if (!data.token || data.token !== expected) {
    return jsonResponse({ status: 'error', message: 'Not authorised' });
  }
  return null;
}

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    switch (data.action) {
      case 'feedback':       return handleFeedback(data);
      case 'validateToken':  return requireContributorToken(data) || jsonResponse({ status: 'ok' });
      case 'addTree':        return requireContributorToken(data) || handleAddTree(data);
      case 'editTree':       return requireContributorToken(data) || handleEditTree(data);
      case 'deleteTree':     return requireContributorToken(data) || handleDeleteTree(data);
      case 'repositionTree': return requireContributorToken(data) || handleRepositionTree(data);
      case 'appendPhotos':   return requireContributorToken(data) || handleAppendPhotos(data);
      case 'removePhoto':    return requireContributorToken(data) || handleRemovePhoto(data);
      case 'reorderPhotos':  return requireContributorToken(data) || handleReorderPhotos(data);
      default:               return jsonResponse({ status: 'error', message: 'Unknown action: ' + data.action });
    }
  } catch (err) {
    Logger.log('doPost error: ' + err);
    return jsonResponse({ status: 'error', message: String(err && err.message || err) });
  }
}

// Visiting the Web App URL in a browser returns a simple OK, to sanity-check
// that the deployment is reachable.
function doGet() {
  return jsonResponse({ status: 'ok', message: 'Fulham Cemetery tree map Apps Script is running.' });
}

function treesSheet() {
  const sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(TREES_SHEET);
  if (!sheet) throw new Error('Sheet "' + TREES_SHEET + '" not found');
  return sheet;
}

function headersOf(sheet) {
  return sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
}

// ── Feedback ──────────────────────────────────────────────────────────────────
function handleFeedback(data) {
  const ss = SpreadsheetApp.openById(SHEET_ID);
  let sheet = ss.getSheetByName(FEEDBACK_SHEET);
  if (!sheet) {
    sheet = ss.insertSheet(FEEDBACK_SHEET);
    sheet.appendRow(['Timestamp', 'Ref', 'Tree', 'Comment']);
  }
  appendTimestampedRow(sheet, [data.ref || '', data.tree || '', data.comment || '']);
  return jsonResponse({ status: 'ok' });
}

// ── History log ───────────────────────────────────────────────────────────────
// A static, append-only log. Every mutation below writes its own row at the
// moment it happens. `count` is only meaningful for 'appendPhotos'; leave it
// undefined elsewhere.
//
// `prevRef` is only meaningful for 'repositionTree' (Ref is lat/lng-derived,
// so moving a tree changes it) — it records the Ref this tree had *before*
// this particular move. Combined with handleRepositionTree's forward-rewrite
// of this row's own 'Ref' column on every later move of the same tree,
// `prevRef` always resolves to the tree's *current* Ref in a single lookup,
// however many times it's moved since — see resolveStaleRef() in index.html,
// which a stale shared/bookmarked tree URL falls back to.
function appendHistory(action, ref, treeLabel, count, prevRef) {
  const ss = SpreadsheetApp.openById(SHEET_ID);
  let sheet = ss.getSheetByName(HISTORY_SHEET);
  if (!sheet) {
    sheet = ss.insertSheet(HISTORY_SHEET);
    sheet.appendRow(['Timestamp', 'Action', 'Ref', 'Tree', 'Count', 'Prev Ref']);
  } else {
    // Sheets created before 'Prev Ref' existed — add the column in place so
    // existing rows and their positions are undisturbed.
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    if (headers.indexOf('Prev Ref') === -1) {
      sheet.getRange(1, headers.length + 1).setValue('Prev Ref');
    }
  }
  appendTimestampedRow(sheet, [action, ref || '', treeLabel || '', count || '', prevRef || '']);
}

// ── Locate a tree row ─────────────────────────────────────────────────────────
// Returns { rowNum, photoCol } if the tree is found, null if not, or
// { error } if the sheet is missing a required column.
function findTreeRow(sheet, ref) {
  const headers  = headersOf(sheet);
  const refCol   = headers.indexOf('Ref') + 1;
  const photoCol = headers.indexOf('Photo') + 1;
  if (!refCol || !photoCol) return { error: 'Ref or Photo column not found' };
  const lastRow = sheet.getLastRow();
  if (lastRow < FIRST_DATA_ROW) return null;
  const refs = sheet.getRange(FIRST_DATA_ROW, refCol, lastRow - FIRST_DATA_ROW + 1, 1).getValues();
  for (let i = 0; i < refs.length; i++) {
    if (String(refs[i][0]) === String(ref)) {
      return { rowNum: i + FIRST_DATA_ROW, photoCol: photoCol };
    }
  }
  return null;
}

// Used right after handleAddTree appends and sorts, to find the new row and
// read back the Ref its formula has just computed.
function findTreeRowByLatLng(sheet, lat, lng) {
  const headers = headersOf(sheet);
  const latCol = headers.indexOf('Latitude') + 1;
  const lngCol = headers.indexOf('Longitude') + 1;
  const refCol = headers.indexOf('Ref') + 1;
  if (!latCol || !lngCol || !refCol) return null;
  const lastRow = sheet.getLastRow();
  if (lastRow < FIRST_DATA_ROW) return null;
  const vals = sheet.getRange(FIRST_DATA_ROW, 1, lastRow - FIRST_DATA_ROW + 1, sheet.getLastColumn()).getValues();
  for (let i = 0; i < vals.length; i++) {
    if (parseFloat(vals[i][latCol - 1]) === parseFloat(lat) &&
        parseFloat(vals[i][lngCol - 1]) === parseFloat(lng)) {
      return { rowNum: i + FIRST_DATA_ROW, refCol: refCol };
    }
  }
  return null;
}

function splitPhotos(cellValue) {
  const s = String(cellValue || '').trim();
  return s ? s.split(',').map(p => p.trim()).filter(Boolean) : [];
}

// ── Add tree ──────────────────────────────────────────────────────────────────
function handleAddTree(data) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet   = treesSheet();
    const headers = headersOf(sheet);
    const col = name => headers.indexOf(name); // 0-based; -1 if missing

    const lat = parseFloat(data.lat);
    const lng = parseFloat(data.lng);
    if (isNaN(lat) || isNaN(lng)) return jsonResponse({ status: 'error', message: 'Invalid lat/lng' });

    const row = new Array(headers.length).fill('');
    const set = (colName, value) => {
      const i = col(colName);
      if (i >= 0) row[i] = value || '';
    };
    set('Latitude',          lat);
    set('Longitude',         lng);
    set('Scientific name',   data.sci);
    set('Common name',       data.common);
    set('Tag',               data.tag);
    set('Notes',             data.notes);
    set('Year planted',      data.year_planted);
    set('Est. year planted', data.est_year_planted);
    set('Form',              data.form_field);
    set('Condition',         data.condition);
    set('Photo',             data.photos);

    // Formula columns (Ref, Map link, Treemap link, Est. age, …) are per-row
    // formulas. Copy every formula from the current last row into the new
    // one in R1C1 form, so its relative references point at the new row.
    // Only cells the new row leaves blank are filled.
    const templateRow = sheet.getLastRow();
    const templateFormulas = templateRow >= FIRST_DATA_ROW
      ? sheet.getRange(templateRow, 1, 1, headers.length).getFormulasR1C1()[0]
      : [];

    sheet.appendRow(row);
    const newRowNum = sheet.getLastRow();
    templateFormulas.forEach((f, i) => {
      if (f && row[i] === '') sheet.getRange(newRowNum, i + 1).setFormulaR1C1(f);
    });

    // Sort by Scientific name, then FCF number.
    const sciCol = col('Scientific name');
    const fcfCol = col('FCF number');
    if (sciCol >= 0 && sheet.getLastRow() > FIRST_DATA_ROW) {
      const sortSpec = [{ column: sciCol + 1, ascending: true }];
      if (fcfCol >= 0) sortSpec.push({ column: fcfCol + 1, ascending: true });
      sheet.getRange(FIRST_DATA_ROW, 1, sheet.getLastRow() - FIRST_DATA_ROW + 1, sheet.getLastColumn())
           .sort(sortSpec);
    }

    // Locate the new row by its own Lat/Lng (stable wherever the sort moved
    // it) to read the Ref the History entry should link to.
    SpreadsheetApp.flush();
    const found  = findTreeRowByLatLng(sheet, lat, lng);
    const newRef = found ? sheet.getRange(found.rowNum, found.refCol).getValue() : '';
    appendHistory('addTree', newRef, data.tree);

    return jsonResponse({ status: 'ok', ref: newRef });
  } finally {
    lock.releaseLock();
  }
}

// ── Edit an existing tree ─────────────────────────────────────────────────────
// Updates the editable fields of a tree row identified by Ref. Never touches
// Ref, Latitude, Longitude, Photo, or the formula columns. No re-sort.
function handleEditTree(data) {
  if (!data.ref) return jsonResponse({ status: 'error', message: 'Missing ref' });
  const sheet   = treesSheet();
  const headers = headersOf(sheet);
  const row = findTreeRow(sheet, data.ref);
  if (row && row.error) return jsonResponse({ status: 'error', message: row.error });
  if (!row) return jsonResponse({ status: 'error', message: 'Tree not found: ' + data.ref });
  const set = (colName, value) => {
    const i = headers.indexOf(colName);
    if (i >= 0 && value !== undefined) sheet.getRange(row.rowNum, i + 1).setValue(value || '');
  };
  set('Scientific name',   data.sci);
  set('Common name',       data.common);
  set('Short name',        data.short_name);
  set('Other names',       data.other_names);
  set('Tag',               data.tag);
  set('Notes',             data.notes);
  set('Year planted',      data.year_planted);
  set('Est. year planted', data.est_year_planted);
  set('Year died',         data.year_died);
  set('Form',              data.form_field);
  set('Condition',         data.condition);
  appendHistory('editTree', data.ref, data.tree);
  return jsonResponse({ status: 'ok' });
}

// ── Reposition a tree (update Latitude / Longitude only) ─────────────────────
function handleRepositionTree(data) {
  if (!data.ref || data.lat === undefined || data.lng === undefined) {
    return jsonResponse({ status: 'error', message: 'Missing ref, lat, or lng' });
  }
  const lat = parseFloat(data.lat);
  const lng = parseFloat(data.lng);
  if (isNaN(lat) || isNaN(lng)) return jsonResponse({ status: 'error', message: 'Invalid lat/lng' });
  const ss      = SpreadsheetApp.openById(SHEET_ID);
  const sheet   = treesSheet();
  const headers = headersOf(sheet);
  const row = findTreeRow(sheet, data.ref);
  if (row && row.error) return jsonResponse({ status: 'error', message: row.error });
  if (!row) return jsonResponse({ status: 'error', message: 'Tree not found: ' + data.ref });
  const set = (colName, value) => {
    const i = headers.indexOf(colName);
    if (i >= 0) sheet.getRange(row.rowNum, i + 1).setValue(value);
  };
  set('Latitude',  lat);
  set('Longitude', lng);

  // Ref is derived from Lat/Lng, so this tree's Ref just changed. Flush,
  // then re-read it at the same row.
  SpreadsheetApp.flush();
  const refCol = headers.indexOf('Ref') + 1;
  const newRef = refCol ? sheet.getRange(row.rowNum, refCol).getValue() : '';

  // Keep this tree's History chain linked: rewrite every History row that
  // recorded the pre-move Ref to the new one.
  const historySheet = ss.getSheetByName(HISTORY_SHEET);
  if (historySheet && newRef) {
    const hLastRow = historySheet.getLastRow();
    if (hLastRow > 1) {
      const hHeaders = historySheet.getRange(1, 1, 1, historySheet.getLastColumn()).getValues()[0];
      const hRefCol = hHeaders.indexOf('Ref') + 1;
      if (hRefCol) {
        const hRefs = historySheet.getRange(2, hRefCol, hLastRow - 1, 1).getValues();
        for (let i = 0; i < hRefs.length; i++) {
          if (String(hRefs[i][0]) === String(data.ref)) {
            historySheet.getRange(i + 2, hRefCol).setValue(newRef);
          }
        }
      }
    }
  }

  appendHistory('repositionTree', newRef, data.tree, undefined, data.ref);
  return jsonResponse({ status: 'ok', ref: newRef });
}

// ── Delete a tree ─────────────────────────────────────────────────────────────
// Removes the row. Google Photos images are left where they are — only their
// reference in the sheet disappears along with the row.
function handleDeleteTree(data) {
  if (!data.ref) return jsonResponse({ status: 'error', message: 'Missing ref' });
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet = treesSheet();
    const row = findTreeRow(sheet, data.ref);
    if (row && row.error) return jsonResponse({ status: 'error', message: row.error });
    if (!row) return jsonResponse({ status: 'error', message: 'Tree not found: ' + data.ref });
    sheet.deleteRow(row.rowNum);
    appendHistory('deleteTree', data.ref, data.tree);
    return jsonResponse({ status: 'ok' });
  } finally {
    lock.releaseLock();
  }
}

// ── Append photos to an existing tree ─────────────────────────────────────────
// data.urls are Google Photos image URLs. Wrapped in a script lock so two
// simultaneous changes to the same tree can't lose data.
function handleAppendPhotos(data) {
  if (!data.ref || !Array.isArray(data.urls) || data.urls.length === 0) {
    return jsonResponse({ status: 'error', message: 'Missing ref or urls' });
  }
  // Commas separate photos in the cell, so a URL can't contain one.
  if (data.urls.some(u => typeof u !== 'string' || !/^https:\/\//.test(u) || u.indexOf(',') !== -1)) {
    return jsonResponse({ status: 'error', message: 'Invalid photo URL' });
  }
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet = treesSheet();
    const row = findTreeRow(sheet, data.ref);
    if (row && row.error) return jsonResponse({ status: 'error', message: row.error });
    if (!row) return jsonResponse({ status: 'error', message: 'Tree not found: ' + data.ref });
    const cell = sheet.getRange(row.rowNum, row.photoCol);
    const next = splitPhotos(cell.getValue()).concat(data.urls).join(',');
    cell.setValue(next);
    appendHistory('appendPhotos', data.ref, data.tree, data.urls.length);
    return jsonResponse({ status: 'ok', photos: next });
  } finally {
    lock.releaseLock();
  }
}

// ── Remove a photo from a tree ────────────────────────────────────────────────
// Strips the URL from the Photo cell. The image itself stays in Google Photos.
function handleRemovePhoto(data) {
  if (!data.ref || !data.url) return jsonResponse({ status: 'error', message: 'Missing ref or url' });
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet = treesSheet();
    const row = findTreeRow(sheet, data.ref);
    if (row && row.error) return jsonResponse({ status: 'error', message: row.error });
    if (!row) return jsonResponse({ status: 'error', message: 'Tree not found: ' + data.ref });
    const cell = sheet.getRange(row.rowNum, row.photoCol);
    const existing = splitPhotos(cell.getValue());
    if (existing.indexOf(data.url) === -1) {
      return jsonResponse({ status: 'error', message: 'Photo list changed — please reopen and try again' });
    }
    const next = existing.filter(p => p !== data.url).join(',');
    cell.setValue(next);
    appendHistory('removePhoto', data.ref, data.tree);
    return jsonResponse({ status: 'ok', photos: next });
  } finally {
    lock.releaseLock();
  }
}

// ── Reorder an existing tree's photos ─────────────────────────────────────────
// Rewrites the Photo cell to data.order, which must be exactly a permutation
// of what's there now — this guards against a stale client silently losing
// or duplicating a photo.
function handleReorderPhotos(data) {
  if (!data.ref || !Array.isArray(data.order) || data.order.length === 0) {
    return jsonResponse({ status: 'error', message: 'Missing ref or order' });
  }
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet = treesSheet();
    const row = findTreeRow(sheet, data.ref);
    if (row && row.error) return jsonResponse({ status: 'error', message: row.error });
    if (!row) return jsonResponse({ status: 'error', message: 'Tree not found: ' + data.ref });
    const cell = sheet.getRange(row.rowNum, row.photoCol);
    const existing = splitPhotos(cell.getValue());
    const sameSet = existing.length === data.order.length &&
      existing.slice().sort().join('\u0000') === data.order.slice().sort().join('\u0000');
    if (!sameSet) {
      return jsonResponse({ status: 'error', message: 'Photo list changed — please reopen and try again' });
    }
    const next = data.order.join(',');
    cell.setValue(next);
    appendHistory('reorderPhotos', data.ref, data.tree);
    return jsonResponse({ status: 'ok', photos: next });
  } finally {
    lock.releaseLock();
  }
}
