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
1. **Fix session cookie handling on mobile Safari**: Mobile login loops represent 30% of all tickets (6 total) with a 0% resolution rate, completely locking users out on iOS. One user reported the session cookie isn't sticking after 2FA, indicating a likely regression in mobile auth that needs immediate engineering attention.
2. **Overhaul CSV export logic for data integrity and limits**: CSV exports are failing in multiple ways—missing columns, garbled encoding, and a 200-row truncation limit—accounting for 4 escalated tickets. These bugs block critical financial workflows and cannot be resolved by frontline support, requiring core fixes to the export pipeline.
3. **Add idempotency to the billing upgrade process**: Duplicate billing generated 3 escalated tickets from users being double-charged for a single upgrade click. Implementing idempotency keys in the payment submission flow will prevent duplicate card charges and eliminate the need for manual billing investigations and refunds.
