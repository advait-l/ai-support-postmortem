# Weekly Support Post-Mortem

## This Week at a Glance
- **Total Ticket Volume:** 17
- **Resolution Rate:** 29.4% (5 resolved, 12 escalated)
- **Escalation Rate:** 70.6%
- **Volume by Day:**
  `@@@@@*`
  Days: 12 13 14 15 16 17
  Counts: 3 3 3 3 3 2

## Top 3 Recurring Issues
1. **Mobile login loop** (5 tickets; 0 resolved, 5 escalated)
   - "On my iPhone in Safari I sign in, finish 2FA, and then land back on the login screen again. I tried three times and c..."
   - "After I enter the texted verification code on mobile Safari, the page flashes and sends me back to sign in. Desktop C..."
2. **CSV export failures** (4 tickets; 0 resolved, 4 escalated)
   - "Export to CSV completes but the downloaded file only has headers and no rows. This started today and blocks my financ..."
   - "The CSV file downloads, but several columns including customer name are empty even though they appear in the web table."
3. **Duplicate billing** (3 tickets; 0 resolved, 3 escalated)
   - "I upgraded once this morning but my card statement shows two charges from your company. Please confirm whether one wi..."
   - "Our admin only clicked upgrade once, but we have two invoice emails and two identical card charges. Please fix this b..."

## What's Getting Escalated and Why
- **Mobile login loop** (5 escalations)
  Reason: Frontline can provide troubleshooting steps such as clearing Safari cache/cookies or trying a different browser, and offer a workaround like using the native app or desktop site.
  Example: "On my iPhone in Safari I sign in, finish 2FA, and then land back on the login screen again. I tried three times and c..."
- **CSV export failures** (4 escalations)
  Reason: Issue is likely a system bug requiring engineering changes to fix; frontline cannot provide a workaround to restore data export functionality.
  Example: "Export to CSV completes but the downloaded file only has headers and no rows. This started today and blocks my financ..."
- **Duplicate billing** (3 escalations)
  Reason: Resolving a duplicate charge requires a billing system change to issue a refund or reversal.
  Example: "I upgraded once this morning but my card statement shows two charges from your company. Please confirm whether one wi..."

## Recommendations for Product Team
1. **Prioritize mobile session stability**: Mobile login-loop issues remain the highest recurring engineering-facing failure and block core usage.
2. **Repair CSV export reliability**: Blank files, missing columns, encoding bugs, and truncation make exports untrustworthy for finance workflows.
3. **Reduce avoidable support load with frontline-safe fixes**: Feature requests, search issues, and invite problems now have workable responses and should stay out of engineering queues when possible.
