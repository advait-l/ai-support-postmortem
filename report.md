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
  Reason: Frontline can provide troubleshooting steps such as clearing Safari cache/cookies or trying a different browser, and offer a workaround like using the native app or desktop site.
  Example: "On my iPhone in Safari I sign in, finish 2FA, and then land back on the login screen again. I tried three times and c..."
- **CSV export failures** (4 escalations)
  Reason: Issue is likely a system bug requiring engineering changes to fix; frontline cannot provide a workaround to restore data export functionality.
  Example: "Export to CSV completes but the downloaded file only has headers and no rows. This started today and blocks my financ..."
- **Duplicate billing** (3 escalations)
  Reason: Resolving a duplicate charge requires a billing system change to issue a refund or reversal.
  Example: "I upgraded once this morning but my card statement shows two charges from your company. Please confirm whether one wi..."

## Recommendations for Product Team
1. **Fix session persistence regression on mobile Safari/iOS browsers**: Mobile login loops account for 30% of all tickets (6 tickets) and 100% are escalated. Users report being redirected back to the login screen immediately after 2FA, with one noting the issue started after a recent update. Fixing this session cookie bug will eliminate the highest-volume escalation driver.
2. **Overhaul CSV export logic to resolve missing data, truncation, and encoding issues**: CSV export failures account for 20% of tickets (4 tickets) and completely block financial workflows. The issues are varied—blank files, missing columns, 200-row truncation limits, and UTF-8 encoding garbling—requiring a comprehensive engineering fix to the export logic.
3. **Implement duplicate charge prevention and enable frontline refund capabilities**: Duplicate billing accounts for 15% of tickets (3 tickets) and severely impacts customer trust. All cases are escalated because frontline support lacks billing system access to issue refunds. Adding idempotency keys to the upgrade flow will prevent double-charges, and granting refund permissions will allow immediate resolution of existing cases.
