/**
 * Webhook.gs
 * Receives scraped Strava activities from the Docker Scraper service
 * and appends them to the 'Data' sheet.
 */

function doPost(e) {
  try {
    const props = PropertiesService.getScriptProperties();
    const expectedSecret = props.getProperty('WEBHOOK_SECRET_KEY') || 'sleep-comp-secret-key';
    
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({
        success: false,
        error: 'No payload received'
      })).setMimeType(ContentService.MimeType.JSON);
    }

    const body = JSON.parse(e.postData.contents);
    
    // Validate secret token
    if (body.secret && body.secret !== expectedSecret) {
      return ContentService.createTextOutput(JSON.stringify({
        success: false,
        error: 'Unauthorized: Invalid secret key'
      })).setMimeType(ContentService.MimeType.JSON);
    }

    if (body.action === 'append_rows' && Array.isArray(body.rows) && body.rows.length > 0) {
      const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Data');
      const lastRow = sheet.getLastRow();
      
      const existingIds = lastRow > 1
        ? sheet.getRange(2, 1, lastRow - 1, 1).getValues().flat().map(String)
        : [];

      // Filter out duplicate rows
      const newRows = body.rows.filter(row => !existingIds.includes(String(row[0])));

      if (newRows.length > 0) {
        sheet.getRange(lastRow + 1, 1, newRows.length, newRows[0].length).setValues(newRows);
        Logger.log(`Webhook added ${newRows.length} new rows to Data sheet.`);
      }

      return ContentService.createTextOutput(JSON.stringify({
        success: true,
        addedCount: newRows.length
      })).setMimeType(ContentService.MimeType.JSON);
    }

    return ContentService.createTextOutput(JSON.stringify({
      success: true,
      addedCount: 0,
      message: 'No new rows to append'
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    Logger.log(`Webhook error: ${err.message}`);
    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      error: err.message
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  try {
    const params = e ? e.parameter : {};
    const props = PropertiesService.getScriptProperties();
    const expectedSecret = props.getProperty('WEBHOOK_SECRET_KEY') || 'sleep-comp-secret-key';

    if (params.secret && params.secret !== expectedSecret) {
      return ContentService.createTextOutput(JSON.stringify({
        success: false,
        error: 'Unauthorized: Invalid secret key'
      })).setMimeType(ContentService.MimeType.JSON);
    }

    if (params.action === 'get_ids') {
      const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Data');
      const lastRow = sheet.getLastRow();
      const existingIds = lastRow > 1
        ? sheet.getRange(2, 1, lastRow - 1, 1).getValues().flat().map(String)
        : [];

      return ContentService.createTextOutput(JSON.stringify({
        success: true,
        existingIds: existingIds
      })).setMimeType(ContentService.MimeType.JSON);
    }

    return ContentService.createTextOutput(JSON.stringify({
      status: 'ok',
      message: 'Sleep Comp Webhook is active'
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      error: err.message
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
