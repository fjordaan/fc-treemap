// Google Apps Script — Add Tree Web App
// Deploy as: Web app → Execute as: Me → Who has access: Anyone
// After deploying, copy the web app URL into ADD_TREE_URL in index.html

const SHEET_ID = '16056CHjRL4-hbd4hbIb1czvrryGKcwMFYWCDeMDDAHM'; // Fulham Cemetery tree master sheet
const SHEET_NAME = 'trees_master';

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const ss = SpreadsheetApp.openById(SHEET_ID);
    const sheet = ss.getSheetByName(SHEET_NAME);

    // Read header row to find column positions
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const col = name => headers.indexOf(name); // 0-based

    // Build a new row matching the header columns
    const newRow = new Array(headers.length).fill('');

    // Map submitted fields to column names — adjust column names to match your sheet exactly
    if (col('Latitude')           >= 0) newRow[col('Latitude')]           = data.lat              || '';
    if (col('Longitude')          >= 0) newRow[col('Longitude')]          = data.lng              || '';
    if (col('Scientific name')    >= 0) newRow[col('Scientific name')]    = data.sci              || '';
    if (col('Common name')        >= 0) newRow[col('Common name')]        = data.common           || '';
    if (col('Tag')                >= 0) newRow[col('Tag')]                = data.tag              || '';
    if (col('Notes')              >= 0) newRow[col('Notes')]              = data.notes            || '';
    if (col('Year planted')       >= 0) newRow[col('Year planted')]       = data.year_planted     || '';
    if (col('Est. year planted')  >= 0) newRow[col('Est. year planted')]  = data.est_year_planted || '';
    if (col('Form')               >= 0) newRow[col('Form')]               = data.form_field       || '';
    if (col('Condition')          >= 0) newRow[col('Condition')]          = data.condition        || '';

    // Append the row
    sheet.appendRow(newRow);

    return ContentService
      .createTextOutput(JSON.stringify({ status: 'ok' }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: 'error', message: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// Test function — run this manually in the Apps Script editor to verify
function testDoPost() {
  const result = doPost({
    postData: {
      contents: JSON.stringify({
        lat: '51.4781234',
        lng: '-0.2012345',
        sci: 'Quercus robur',
        common: 'English oak',
        condition: 'Good',
        tag: 'New',
        notes: 'Test submission — please delete this row'
      })
    }
  });
  Logger.log(result.getContent());
}
