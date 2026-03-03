# Wordmark Approval System

## Overview

The OCHA wordmark generator uses a Google Sheet + Google Apps Script backend to enforce an approval workflow. Users cannot download a clean wordmark without approval from the OCHA Brand and Design Unit.

### Workflow

1. **User** creates a wordmark preview on the generator page (can download a DRAFT-watermarked PNG)
2. **User** submits a request with their email
3. **BDU** receives an email notification at ochavisual@un.org with a preview image attached
4. **BDU** opens the Google Sheet and changes the status from "Pending" to "Approved" (or "Rejected")
5. **BDU** manually emails the user to inform them of the decision
6. **User** enters their Request ID + email on the generator page and downloads the clean SVG/PNG (one-time download)

---

## Current Setup

### Google Sheet

- **Name:** OCHA word mark generator approval request
- **Account:** unochavisual@gmail.com
- **URL:** https://docs.google.com/spreadsheets/d/1eEb70cPxF8dYkomCcBR6TZXy0Q7jTnDM-LxWPbAspxE/edit
- **Tab:** Requests

#### Column headers (row 1)

| A | B | C | D | E | F | G | H | I | J |
|---|---|---|---|---|---|---|---|---|---|
| Timestamp | Email | Icon | Line 1 | Line 2 | Line 3 | Layout | Request ID | Status | Downloaded At |

#### Status dropdown (column I)

Column I has a data validation dropdown with color-coded options:

| Status | Color | Meaning |
|---|---|---|
| Pending | Orange | Request submitted, awaiting review |
| Approved | Blue | Approved by BDU, user can download |
| Rejected | Red | Rejected by BDU |
| Downloaded | Grey | User has downloaded the final file |

### Apps Script

- **Account:** unochavisual@gmail.com
- **Project:** Untitled project (bound to the Google Sheet)
- **Deployment:** Wordmark approval API (Version 4)
- **Execute as:** unochavisual@gmail.com
- **Who has access:** Anyone
- **Notification email:** ochavisual@un.org (set via `NOTIFY_EMAIL` constant)

The notification email includes a PNG preview of the requested wordmark as an attachment.

### Generator HTML

The approval API URL is set in `ocha-wordmark-generator.html`:
```js
const APPROVAL_API_URL = "https://script.google.com/macros/s/AKfycbzpfHd0kMPT1UF-rifWzxFA8Te8E3QFPpDStuln2EXZp3xzJ1sFejZRqwYEedCqia9Vhw/exec";
```

---

## Day-to-Day Operations

### When a user submits a request

- A new row appears in the Google Sheet with status **Pending** (orange)
- You receive an email at ochavisual@un.org with the request details and a preview PNG attached
- The email is sent from unochavisual@gmail.com
- The user sees their **Request ID** on screen (e.g., WM-A3K7P2)

### To approve a request

1. Open the Google Sheet
2. Find the row
3. Use the Status dropdown in column I to change from **Pending** to **Approved**
4. Email the user (column B) to let them know their wordmark is ready to download

### To reject a request

1. Use the Status dropdown to change from **Pending** to **Rejected**
2. Email the user to explain why

### When the user downloads

- They enter their email + Request ID in the "Download" section of the generator
- The system verifies the request is approved and matches their email
- They download the clean SVG or PNG (no watermark)
- Status automatically changes to **Downloaded** (grey) and the timestamp is recorded in column J
- A second download attempt will be blocked

---

## Troubleshooting

**"Could not reach the approval service"**
- Verify the Web App URL in the HTML file matches the deployed URL
- Confirm the Apps Script deployment has "Who has access: Anyone"
- Check the Apps Script execution log (in the script editor) for errors

**User says they didn't get a Request ID**
- Check the Google Sheet — the row should still be there
- The Request ID is shown on screen immediately after submission

**Need to allow a second download**
- Change the status back from "Downloaded" to "Approved" using the dropdown

**Updating the Apps Script**
- After editing code in the Apps Script editor, you must deploy a new version
- Go to Deploy > Manage deployments > Edit (pencil icon) > Version: New version > Deploy

---

## Rebuilding from Scratch

If the system ever needs to be rebuilt (new account, new sheet, etc.):

1. Create a new Google Sheet with the column headers listed above
2. Add data validation on column I (Status) with the 4 dropdown options
3. Go to Extensions > Apps Script and paste the contents of `google-apps-script.js`
4. Update `NOTIFY_EMAIL` if needed
5. Deploy as a Web App (Execute as: Me, Who has access: Anyone)
6. Authorize the script when prompted (it needs access to Sheets and Mail)
7. Copy the Web App URL and update `APPROVAL_API_URL` in `ocha-wordmark-generator.html`
