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
1. **Fix mobile Safari session/login loop**: This is the highest volume issue, accounting for 30% of all tickets (6 tickets) with a 0% resolution rate. Users on iOS/iPad Safari are repeatedly redirected to the login screen after completing 2FA or seeing a brief flash of the dashboard, indicating a broken session cookie or authentication redirect on mobile browsers. Fixing this will drastically reduce escalations and unblock mobile users.
2. **Overhaul CSV export functionality**: CSV exports account for 20% of tickets (4 tickets) and are entirely escalated due to being unpatchable product bugs. The reported issues are varied—blank files with headers only, missing columns, encoding errors for accented characters, and a 200-row truncation limit—indicating systemic flaws in the export pipeline that require a comprehensive engineering fix rather than isolated patches.
3. **Implement idempotency keys on the billing/upgrade endpoint**: Duplicate billing accounts for 15% of tickets (3 tickets) with a 0% resolution rate, and directly impacts customer trust and finances. Users are being charged twice for a single upgrade click. Adding idempotency to the payment processing will prevent race conditions or double-clicks from creating duplicate charges and invoices.
