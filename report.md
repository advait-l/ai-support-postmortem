# Weekly Support Post-Mortem

## This Week at a Glance
- **Total Ticket Volume:** 20
- **Resolution Rate:** 35.0% (7 resolved, 13 escalated)
- **Escalation Rate:** 65.0%
- **Volume by Day:**
  `@@@@@@*`
  Days: 12 13 14 15 16 17 18
  Counts: 3 3 3 3 3 3 2

## Top 3 Recurring Issues
1. **Mobile login loop** (6 tickets; 0 resolved, 6 escalated)
   - "On my iPhone in Safari I sign in, finish 2FA, and then land back on the login screen again. I tried three times and c..."
   - "After I enter the texted verification code on mobile Safari, the page flashes and sends me back to sign in. Desktop C..."
2. **CSV export failures** (4 tickets; 0 resolved, 4 escalated)
   - "Export to CSV completes but the downloaded file only has headers and no rows. This started today and blocks my financ..."
   - "The CSV file downloads, but several columns including customer name are empty even though they appear in the web table."
3. **Duplicate billing** (3 tickets; 0 resolved, 3 escalated)
   - "I upgraded once this morning but my card statement shows two charges from your company. Please confirm whether one wi..."
   - "Our admin only clicked upgrade once, but we have two invoice emails and two identical card charges. Please fix this b..."

## What's Getting Escalated and Why
- **Mobile login loop** (6 escalations)
  Reason: Persistent login loops on mobile Safari usually need engineering investigation.
  Example: "On my iPhone in Safari I sign in, finish 2FA, and then land back on the login screen again. I tried three times and c..."
- **CSV export failures** (4 escalations)
  Reason: CSV export issues are typically product bugs that frontline support cannot patch.
  Example: "Export to CSV completes but the downloaded file only has headers and no rows. This started today and blocks my financ..."
- **Duplicate billing** (3 escalations)
  Reason: Duplicate billing needs billing-system investigation and refund handling.
  Example: "I upgraded once this morning but my card statement shows two charges from your company. Please confirm whether one wi..."

## Recommendations for Product Team
1. **Fix mobile Safari session persistence after 2FA authentication**: Mobile login loops account for 30% of all tickets (6/20) and 100% were escalated with zero resolutions. Users consistently report completing 2FA on iOS Safari but immediately losing the session and redirecting back to sign-in. One user notes this started after a recent update, pointing to a regression in cookie handling—likely Safari ITP blocking the session cookie or a SameSite/Secure attribute misconfiguration on the auth token. Fixing this single issue would eliminate the largest ticket category and meaningfully reduce the 65% escalation rate.
2. **Overhaul the CSV export pipeline to address missing data, truncation, and encoding**: CSV export failures represent 20% of tickets (4/20) with zero resolutions, and the reports reveal at least four distinct bugs: headers-only output with no rows, empty columns that display correctly in-app, garbled accented characters from encoding mismatches, and a hard truncation at 200 rows. These are not edge cases—they block finance workflows entirely. The export pipeline needs a coordinated engineering fix covering data serialization, column mapping, UTF-8 encoding, and pagination limits.
3. **Add request idempotency to the plan upgrade flow to prevent duplicate charges**: Duplicate billing accounts for 15% of tickets (3/20), all escalated, and customers report being charged twice from a single upgrade click. This indicates the payment endpoint lacks idempotency—likely a race condition or double-submit from the frontend with no deduplication key. Adding an idempotency token to the upgrade request and server-side deduplication check would prevent the double charge, eliminate the refund-handling escalations, and restore trust in the billing system.
