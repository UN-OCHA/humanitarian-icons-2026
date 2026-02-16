# Wordmark Approval System — Setup Guide

## Overview

The wordmark generator uses a Google Sheet + Google Apps Script backend to enforce an approval workflow:

1. **User** creates a wordmark preview (can download a DRAFT-watermarked version)
2. **User** submits a request with their email → request lands in a Google Sheet
3. **You** review the sheet and change status from "Pending" to "Approved"
4. **User** enters their Request ID + email → downloads the clean final wordmark (one-time)

---

## Step 1: Create the Google Sheet

1. Go to [Google Sheets](https://sheets.google.com) and create a new spreadsheet
2. Rename it to **"Wordmark Approval Requests"**
3. Rename the first tab to **"Requests"**
4. In row 1, add these column headers:

| A | B | C | D | E | F | G | H | I | J |
|---|---|---|---|---|---|---|---|---|---|
| Timestamp | Email | Icon | Line 1 | Line 2 | Line 3 | Layout | Request ID | Status | Downloaded At |

5. **Bold** the header row and freeze it (View → Freeze → 1 row)
6. Optional: Add conditional formatting on column I (Status):
   - "Pending" → yellow background
   - "Approved" → green background
   - "Downloaded" → blue background
   - "Rejected" → red background

---

## Step 2: Add the Apps Script

1. In the Google Sheet, go to **Extensions → Apps Script**
2. Delete any existing code in the editor
3. Copy the entire contents of `google-apps-script.js` from this folder and paste it
4. If your notification email is different from `ochavisual@un.org`, update the `NOTIFY_EMAIL` constant at the top
5. Click **Save** (Ctrl+S)

---

## Step 3: Deploy as Web App

1. In the Apps Script editor, click **Deploy → New deployment**
2. Click the gear icon next to "Select type" and choose **Web app**
3. Settings:
   - **Description:** Wordmark approval API
   - **Execute as:** Me (your account)
   - **Who has access:** Anyone
4. Click **Deploy**
5. **Authorize** the script when prompted (it needs access to Sheets and Mail)
6. **Copy the Web App URL** — it looks like:
   ```
   https://script.google.com/macros/s/AKfycb.../exec
   ```

---

## Step 4: Connect the Word Mark Generator

1. Open `ocha-wordmark-generator.html`
2. Find the line near the top of the `<script>` section:
   ```js
   const APPROVAL_API_URL = "YOUR_GOOGLE_APPS_SCRIPT_URL_HERE";
   ```
3. Replace `YOUR_GOOGLE_APPS_SCRIPT_URL_HERE` with the Web App URL you copied

---

## How It Works (Day-to-Day)

### When a user submits a request:
- A new row appears in the Google Sheet with status **"Pending"**
- You receive an email at ochavisual@un.org with the request details
- The user sees their **Request ID** (e.g., WM-A3K7P2)

### To approve a request:
- Open the Google Sheet
- Find the row
- Change column I (Status) from **"Pending"** to **"Approved"**
- That's it! No need to generate any files.

### When the user downloads:
- They enter their email + Request ID in step 4 of the generator
- The system verifies the code is approved and linked to their email
- They download the clean SVG or PNG (no watermark)
- Status automatically changes to **"Downloaded"**
- A second download attempt will be blocked

### To reject a request:
- Change the status to **"Rejected"**
- The user will see "Request status: Rejected" when they check

---

## Troubleshooting

**"Could not reach the approval service"**
- Check the Web App URL is correct in the HTML file
- Make sure the Apps Script deployment has "Who has access: Anyone"
- Check the Apps Script execution log for errors

**User says they didn't get a Request ID**
- Check the Google Sheet — the row should still be there
- The Request ID is shown on screen immediately, the email notification is a bonus

**Need to allow a second download**
- Change the status back from "Downloaded" to "Approved"

**Updating the script**
- After editing the Apps Script, you must create a **new deployment** or update the existing one
- Go to Deploy → Manage deployments → Edit → Version: New version → Deploy
