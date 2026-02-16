// ============================================================
// OCHA Wordmark Approval — Google Apps Script
// ============================================================
// Deploy this as a Web App in Google Apps Script.
// It connects to a Google Sheet that acts as the approval ledger.
//
// SETUP:
// 1. Create a Google Sheet with these column headers in row 1:
//    A: Timestamp | B: Email | C: Icon | D: Line 1 | E: Line 2
//    F: Line 3 | G: Layout | H: Request ID | I: Status | J: Downloaded At
//
// 2. Go to Extensions > Apps Script, paste this code
// 3. Deploy > New deployment > Web app
//    - Execute as: Me
//    - Who has access: Anyone
// 4. Copy the Web App URL and paste it into the word mark generator
//    (the APPROVAL_API_URL constant)
//
// STATUS values: Pending | Approved | Downloaded | Rejected
// ============================================================

// Name of the sheet tab (default is first sheet)
const SHEET_NAME = 'Requests';

// Email address that receives notification when a new request comes in
const NOTIFY_EMAIL = 'ochavisual@un.org';

function getSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.getSheets()[0];
  }
  return sheet;
}

// Generate a short unique request ID
function generateRequestId() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // no ambiguous chars
  let id = 'WM-';
  for (let i = 0; i < 6; i++) {
    id += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return id;
}

// Handle incoming requests (both GET and POST)
function doPost(e) {
  return handleRequest(e);
}

function doGet(e) {
  return handleRequest(e);
}

function handleRequest(e) {
  // Enable CORS
  const output = ContentService.createTextOutput();
  output.setMimeType(ContentService.MimeType.JSON);

  try {
    let params;
    if (e.postData) {
      params = JSON.parse(e.postData.contents);
    } else {
      params = e.parameter;
    }

    const action = params.action;

    if (action === 'submit') {
      return output.setContent(JSON.stringify(submitRequest(params)));
    } else if (action === 'check') {
      return output.setContent(JSON.stringify(checkStatus(params)));
    } else if (action === 'download') {
      return output.setContent(JSON.stringify(markDownloaded(params)));
    } else {
      return output.setContent(JSON.stringify({ success: false, error: 'Unknown action' }));
    }
  } catch (err) {
    return output.setContent(JSON.stringify({ success: false, error: err.message }));
  }
}

// ACTION: submit — user submits a new wordmark request
function submitRequest(params) {
  const sheet = getSheet();
  const requestId = generateRequestId();
  const timestamp = new Date().toISOString();

  const email = (params.email || '').trim();
  const icon = (params.icon || '').trim();
  const line1 = (params.line1 || '').trim();
  const line2 = (params.line2 || '').trim();
  const line3 = (params.line3 || '').trim();
  const layout = (params.layout || '1').trim();

  if (!email || !icon || !line1) {
    return { success: false, error: 'Email, icon, and at least line 1 are required.' };
  }

  // Append row
  sheet.appendRow([timestamp, email, icon, line1, line2, line3, layout, requestId, 'Pending', '']);

  // Send notification email
  try {
    const subject = `Wordmark request ${requestId} from ${email}`;
    const body = [
      `New wordmark request:`,
      ``,
      `Request ID: ${requestId}`,
      `Email: ${email}`,
      `Icon: ${icon}`,
      `Layout: ${layout} line(s)`,
      `Line 1: ${line1}`,
      line2 ? `Line 2: ${line2}` : '',
      line3 ? `Line 3: ${line3}` : '',
      ``,
      `To approve, open the Google Sheet and change the Status column from "Pending" to "Approved".`,
    ].filter(Boolean).join('\n');

    MailApp.sendEmail(NOTIFY_EMAIL, subject, body);
  } catch (mailErr) {
    // Don't fail the request if email fails
    Logger.log('Email notification failed: ' + mailErr.message);
  }

  return {
    success: true,
    requestId: requestId,
    message: 'Request submitted. You will receive an email when approved.'
  };
}

// ACTION: check — user checks if their request is approved
function checkStatus(params) {
  const requestId = (params.requestId || '').trim().toUpperCase();
  const email = (params.email || '').trim().toLowerCase();

  if (!requestId || !email) {
    return { success: false, error: 'Request ID and email are required.' };
  }

  const sheet = getSheet();
  const data = sheet.getDataRange().getValues();

  // Find the row (skip header)
  for (let i = 1; i < data.length; i++) {
    const rowId = (data[i][7] || '').toString().trim().toUpperCase();
    const rowEmail = (data[i][1] || '').toString().trim().toLowerCase();

    if (rowId === requestId && rowEmail === email) {
      const status = (data[i][8] || '').toString().trim();
      return {
        success: true,
        status: status,
        canDownload: status === 'Approved'
      };
    }
  }

  return { success: false, error: 'Request not found. Check your Request ID and email.' };
}

// ACTION: download — marks the request as downloaded (one-time use)
function markDownloaded(params) {
  const requestId = (params.requestId || '').trim().toUpperCase();
  const email = (params.email || '').trim().toLowerCase();

  if (!requestId || !email) {
    return { success: false, error: 'Request ID and email are required.' };
  }

  const sheet = getSheet();
  const data = sheet.getDataRange().getValues();

  for (let i = 1; i < data.length; i++) {
    const rowId = (data[i][7] || '').toString().trim().toUpperCase();
    const rowEmail = (data[i][1] || '').toString().trim().toLowerCase();

    if (rowId === requestId && rowEmail === email) {
      const status = (data[i][8] || '').toString().trim();

      if (status === 'Downloaded') {
        return { success: false, error: 'This wordmark has already been downloaded. Contact ochavisual@un.org for another download.' };
      }

      if (status !== 'Approved') {
        return { success: false, error: 'This request is not yet approved.' };
      }

      // Mark as downloaded
      sheet.getRange(i + 1, 9).setValue('Downloaded');  // Column I (Status)
      sheet.getRange(i + 1, 10).setValue(new Date().toISOString()); // Column J (Downloaded At)

      return { success: true, canDownload: true };
    }
  }

  return { success: false, error: 'Request not found.' };
}
