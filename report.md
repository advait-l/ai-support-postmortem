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
1. **Fix session persistence on mobile Safari to resolve login loops**: Mobile login loops account for 6 tickets (30% of total volume) and 100% were escalated. Users are repeatedly redirected to the login screen after 2FA on iOS/iPad Safari because the session cookie fails to stick. Fixing this will eliminate the highest-volume escalated issue.
2. **Resolve CSV export data loss, truncation, and encoding bugs**: CSV export failures generated 4 tickets (20% of total volume) with a 100% escalation rate. Exports are missing columns, truncating at 200 rows, and breaking accented characters. Fixing the export pipeline will unblock critical finance workflows and reduce engineering escalations.
3. **Implement idempotency controls in the billing upgrade flow**: Duplicate billing accounts for 3 tickets (15% of total volume) and 100% escalation. Customers are charged twice for a single upgrade click, requiring manual refund intervention. Adding idempotency keys to the upgrade endpoint will prevent double charges and eliminate this high-priority billing issue.
