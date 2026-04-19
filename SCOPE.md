# AI Support Team — Weekly Post-Mortem

**Track:** MaaS (Model-as-a-Service / agentic)
**Demo length:** 3 minutes
**Build window:** 4 hours

---

## The Magic Moment

A week of support tickets goes in. A markdown post-mortem comes out that surfaces real recurring issues, escalation patterns, and concrete product recommendations — the kind a human analyst would take a day to write.

The inbox → triage → resolve/escalate pipeline exists **only to feed the post-mortem**. It is not the product. The report is the product.

---

## Scope Ladder

### ITERATION 0 — 20 min (Terminal only)
`python main.py` reads `tickets.json` (20 hardcoded tickets), sends them to an LLM with a "support analyst" prompt, and prints a markdown post-mortem to the terminal with top issues, volume, and 3 product recommendations.

**MaaS requirement:** Observability wired from minute one. Every LLM call writes a trace (Langfuse / Langsmith / Helicone / simple JSONL — pick one and commit). No bolt-on at 3 PM.

### ITERATION 1 — 1 hr (Core pipeline)
Add triage + resolve/escalate. For each ticket:
- One LLM call classifies (category, priority, resolvable?)
- If resolvable → draft response against fake KB
- If not → escalate with reason

Results append to each ticket record. Post-mortem now analyzes real pipeline output: resolution rate, escalation reasons, category breakdown. Still terminal-only. Every step traced.

### ITERATION 2 — 1 hr (L3 floor across all params — DONE BY 2:00 PM)
- **MaaS:** One full task (ingest → triage → resolve/escalate → post-mortem) completes autonomously end-to-end, visible in the observability dashboard. If not green by 2 PM, cut scope.
- **Polish the report itself** — this is where "oh, interesting" lives. Structured sections:
  - This Week at a Glance (volume, resolution rate, escalation rate)
  - Top 3 Recurring Issues (with example ticket quotes)
  - What's Getting Escalated and Why
  - Recommendations for Product Team
- ASCII sparkline for volume-by-day is fine. No charts library.
- Deploy. URL must be live. A real human outside the team must be able to see the output.

### ITERATION 3 — 1 hr (L4/L5 push — pick ONE)
- **(a) Stabilize real output (20x):** run the pipeline on 5 different seeded ticket sets, fix prompt failures, add retry/fallback on LLM errors (graceful fallback, not console.log — this is a user-facing path).
- **(b) Add missing observability features:** run diff between two weeks, alert on escalation spikes, per-category drill-down in traces.

Do not attempt both.

---

## Demo Moment (3 min)

1. `cat tickets.json | head` — "here's a week of support tickets" (15s)
2. `python main.py` — tickets stream through triage + resolve/escalate with live terminal output, traces appearing in observability dashboard on second screen (45s)
3. Post-mortem prints: clean markdown with real insights, recurring patterns, product recommendations drawn from actual ticket content (90s)
4. Scroll to "Recommendations for Product Team" — the punchline (30s)

---

## NOT BUILDING

- No auth, no users, no accounts
- No database — JSON files on disk
- No real email / Zendesk / Slack integration
- No web dashboard for the pipeline (the deployed URL shows the rendered report, nothing else)
- No multi-agent framework (LangGraph, CrewAI, etc.)
- No charts library — ASCII only
- No human-in-the-loop UI for escalations
- No ticket ingestion endpoint / inbox polling
- No notifications
- No per-customer history or context retrieval
- No mobile responsiveness
- No loading states or animations
- No multiple user types

## FAKING

- **Tickets:** 20–50 hardcoded synthetic tickets in `tickets.json`, timestamps spread across 7 days, **deliberately seeded with 2–3 recurring themes** (e.g., 6 tickets about "login loop on mobile", 4 about "export to CSV broken") so the post-mortem has a real story to surface. A boring report = dead demo.
- **Knowledge base:** hardcoded dict of 5–10 canned solutions the resolver prompt can reference.
- **Escalation:** field on the ticket + a reason string. No routing anywhere.
- **Agents:** one LLM, three system prompts (triager, resolver, analyst). No agent framework.
- **"Weekly":** the whole JSON file is the week.
- **Auth / deploy:** single-provider if any, probably none. Deploy target renders the static report.

---

## Time Checkpoints

| Time | What must be true |
|------|---|
| **12:20 PM** | Iteration 0 runs end-to-end. Terminal prints a real post-mortem. Every LLM call traced. |
| **1:00 PM** | Iteration 1 pipeline working. Triage + resolve/escalate + post-mortem all chained. |
| **2:00 PM — L3 FLOOR** | Full task completes autonomously end-to-end in observability. Deployed URL live. A real human could look at it right now. Any param not at L3 is LOCKED at L1. |
| **3:00 PM** | Stop adding features. Run the demo task twice to prove stability. Fix only what breaks. |
| **3:30 PM** | Final deploy. Bugs only, no new code. |
| **3:45 PM** | Submit. |

---

## Hard Rules

1. Iteration 0 ships before Iteration 1 starts. No exceptions.
2. Seed `tickets.json` with intentional patterns before any prompting work. Boring data = dead demo.
3. Observability is in Iteration 0, not bolted on at 3 PM.
4. If Iteration 2 polish isn't done by 2 PM, Iteration 3 is cancelled. L3 floor beats L5 spike every time.
5. No refactors. "Does it work? Does the user's path look clean in 3 minutes? Then don't touch it."
6. Polish only if it's on the user's 3-minute path. Otherwise cut.

---

## Forbidden Today

- Multi-provider OAuth
- Multiple user types
- Mobile responsiveness
- Optimizing before it works
- Custom design system
- Installing deps without a reason
- Loading states / animations on non-core surfaces
- Anything not in this document

## Shortcuts Allowed

- Hardcoded credentials
- Fake data arrays on non-core surfaces
- `console.log` for dev-path errors (NOT for the pipeline's user-facing failure path — that needs graceful fallback)
- `alert()` over toasts
- Page refresh over state management
- Desktop only
- Tailwind only, inline styles if faster
