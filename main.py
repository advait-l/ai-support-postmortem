import json
import os
import re
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from html import escape

import requests


DEFAULT_ZEN_MODEL = "glm-5"
TICKETS_PATH = "tickets.json"
TRACES_PATH = "traces.jsonl"
PIPELINE_OUTPUT_PATH = "pipeline_output.json"
REPORT_PATH = "report.md"
REPORT_JSON_PATH = "report.json"
DIST_DIR = "dist"
DIST_INDEX_PATH = os.path.join(DIST_DIR, "index.html")
ENV_PATH = ".env"
ZEN_CHAT_COMPLETIONS_URL = "https://opencode.ai/zen/v1/chat/completions"
KNOWLEDGE_BASE = {
    "mobile_login_loop": {
        "title": "Mobile login loop workaround",
        "summary": "Ask the customer to clear Safari site data, disable cross-site tracking blockers for the app, and retry sign-in after closing all browser tabs.",
        "when_to_use": "Use when the customer is stuck in a sign-in loop on mobile Safari or iPad Safari.",
    },
    "password_reset": {
        "title": "Password reset troubleshooting",
        "summary": "Confirm the account email, ask the customer to check spam, and resend the reset link. If still missing after 10 minutes, escalate to identity support.",
        "when_to_use": "Use for missing password reset emails or expired reset links.",
    },
    "feature_request": {
        "title": "Feature request acknowledgement",
        "summary": "Thank the customer, confirm the request is logged, and provide a realistic statement that there is no committed ship date yet.",
        "when_to_use": "Use for requests such as dark mode or scheduled exports.",
    },
    "invoice_copy": {
        "title": "Invoice wording issue",
        "summary": "Acknowledge the typo, confirm it does not affect billing data, and note that the issue has been forwarded to the product team.",
        "when_to_use": "Use for non-blocking invoice copy or email wording issues.",
    },
    "slow_dashboard": {
        "title": "Performance troubleshooting",
        "summary": "Ask the customer to retry during a lower-traffic period, narrow to the specific report or page, and capture the timestamp for investigation.",
        "when_to_use": "Use for slow pages, report timeouts, or intermittent latency.",
    },
    "team_invites": {
        "title": "Invite flow troubleshooting",
        "summary": "Advise the customer to retry from desktop Chrome, verify the teammate email is not already pending, and capture the invite timestamp if the spinner persists.",
        "when_to_use": "Use for teammate invite failures or stuck invite modals.",
    },
    "search_accuracy": {
        "title": "Search mismatch workaround",
        "summary": "Recommend searching with the account ID or email as a temporary workaround and note that relevance tuning has been flagged internally.",
        "when_to_use": "Use when exact-name search results are poor but the account still exists.",
    },
}

CATEGORY_LABELS = {
    "mobile_login_loop": "Mobile login loop",
    "csv_export": "CSV export failures",
    "duplicate_billing": "Duplicate billing",
    "password_reset": "Password reset",
    "feature_request": "Feature requests",
    "invoice_copy": "Invoice copy issues",
    "slow_dashboard": "Slow dashboard",
    "team_invites": "Team invite failures",
    "search_accuracy": "Search accuracy",
    "other": "Other",
}

FRONTLINE_RESOLVABLE_CATEGORIES = {
    "password_reset",
    "feature_request",
    "invoice_copy",
    "slow_dashboard",
    "team_invites",
    "search_accuracy",
}

FRONTLINE_ESCALATION_CATEGORIES = {
    "mobile_login_loop",
    "csv_export",
    "duplicate_billing",
}


def load_tickets(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def append_trace(payload: dict) -> None:
    with open(TRACES_PATH, "a", encoding="utf-8") as file:
        file.write(json.dumps(payload) + "\n")


def write_pipeline_output(tickets: list[dict]) -> None:
    with open(PIPELINE_OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump(tickets, file, indent=2)


def write_text_file(path: str, content: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def write_json_file(path: str, payload: dict) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


def estimate_prompt_size(*parts: str) -> int:
    return sum(len(part.split()) for part in parts)


def load_local_env(path: str = ENV_PATH) -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue

            key, value = stripped.split("=", 1)
            cleaned_value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), cleaned_value)


def parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    return json.loads(cleaned)


def normalize_triage(ticket: dict, triage: dict) -> dict:
    text = f"{ticket['subject']}\n{ticket['body']}".lower()

    if "typo" in text or "reciept" in text or "receipt" in text:
        triage["category"] = "invoice_copy"
    elif "feature request" in text or "dark mode" in text or "schedule export" in text:
        triage["category"] = "feature_request"
    elif "invite" in text and "teammate" in text:
        triage["category"] = "team_invites"
    elif "search" in text and "account name" in text:
        triage["category"] = "search_accuracy"
    elif "slow" in text or "time out" in text or "timeout" in text:
        triage["category"] = "slow_dashboard"

    category = triage["category"]
    if category in FRONTLINE_RESOLVABLE_CATEGORIES:
        triage["resolvable"] = True
        if category == "feature_request":
            triage["reason"] = (
                "Frontline can acknowledge the request and log product feedback."
            )
        elif category == "invoice_copy":
            triage["reason"] = (
                "Frontline can confirm the typo and reassure the customer that billing data is unaffected."
            )
        elif category == "slow_dashboard":
            triage["reason"] = (
                "Frontline can provide troubleshooting steps and capture timing details for follow-up."
            )
        elif category == "team_invites":
            triage["reason"] = (
                "Frontline can offer invite troubleshooting steps and a desktop retry workaround."
            )
        elif category == "search_accuracy":
            triage["reason"] = (
                "Frontline can provide a temporary search workaround while relevance is reviewed."
            )
        elif category == "password_reset":
            triage["reason"] = (
                "Frontline can resend the reset flow and guide inbox troubleshooting."
            )
    elif category in FRONTLINE_ESCALATION_CATEGORIES:
        triage["resolvable"] = False

    return triage


def get_provider() -> dict:
    api_key = os.environ.get("OPENCODE_ZEN_API_KEY") or os.environ.get("ZEN_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENCODE_ZEN_API_KEY environment variable.")

    return {
        "type": "zen",
        "api_key": api_key,
        "base_url": os.environ.get("OPENCODE_ZEN_BASE_URL", ZEN_CHAT_COMPLETIONS_URL),
    }


def get_model_name() -> str:
    return os.environ.get("OPENCODE_ZEN_MODEL", DEFAULT_ZEN_MODEL)


def get_retry_delay_seconds(error: Exception) -> int | None:
    message = str(error)
    if "Read timed out" in message or "ConnectTimeout" in message:
        return 5

    if "429" not in message and "rate limit" not in message.lower():
        return None

    retry_patterns = [r"retry in ([0-9.]+)s", r'"retry_after"\s*:\s*([0-9.]+)']
    for pattern in retry_patterns:
        match = re.search(pattern, message)
        if match:
            return max(1, int(float(match.group(1))) + 1)

    return 30


def call_zen(provider: dict, system_prompt: str, user_prompt: str, model: str) -> str:
    response = requests.post(
        provider["base_url"],
        headers={
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        },
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"{response.status_code} {response.text}")

    data = response.json()
    return data["choices"][0]["message"]["content"]


def traced_llm_call(
    provider: dict,
    *,
    step: str,
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    metadata: dict | None = None,
) -> str:
    current_model = model or get_model_name()
    attempt = 1

    while True:
        trace_id = str(uuid.uuid4())
        started_at = time.perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            output = call_zen(provider, system_prompt, user_prompt, current_model)
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            append_trace(
                {
                    "timestamp": timestamp,
                    "trace_id": trace_id,
                    "step": step,
                    "metadata": {**(metadata or {}), "attempt": attempt},
                    "provider": provider["type"],
                    "model": current_model,
                    "prompt_tokens_estimate": estimate_prompt_size(
                        system_prompt, user_prompt
                    ),
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "response": output,
                    "latency_ms": latency_ms,
                    "status": "ok",
                }
            )
            return output
        except Exception as error:
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            append_trace(
                {
                    "timestamp": timestamp,
                    "trace_id": trace_id,
                    "step": step,
                    "metadata": {**(metadata or {}), "attempt": attempt},
                    "provider": provider["type"],
                    "model": current_model,
                    "prompt_tokens_estimate": estimate_prompt_size(
                        system_prompt, user_prompt
                    ),
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "response": None,
                    "latency_ms": latency_ms,
                    "status": "error",
                    "error": str(error),
                }
            )

            retry_delay_seconds = get_retry_delay_seconds(error)
            if retry_delay_seconds is None:
                raise

            print(
                f"[retry] {step} waiting {retry_delay_seconds}s after rate limit",
                file=sys.stderr,
            )
            time.sleep(retry_delay_seconds)
            attempt += 1


def build_triage_prompts(ticket: dict) -> tuple[str, str]:
    system_prompt = (
        "You are a support triage assistant. Classify a support ticket and return JSON only. "
        "Do not wrap the JSON in markdown fences. Assume frontline support can resolve tickets when they can provide a workaround, troubleshooting guidance, acknowledgement, or a safe next step without engineering or billing system changes."
    )
    user_prompt = (
        "Review this support ticket and classify it.\n\n"
        "Return JSON with exactly these keys:\n"
        "category: one of [mobile_login_loop, csv_export, duplicate_billing, password_reset, "
        "feature_request, invoice_copy, slow_dashboard, team_invites, search_accuracy, other]\n"
        "priority: one of [low, medium, high, urgent]\n"
        "resolvable: true or false\n"
        "reason: short string explaining why it is or is not resolvable by frontline support\n\n"
        f"Ticket ID: {ticket['id']}\n"
        f"Created At: {ticket['created_at']}\n"
        f"Customer: {ticket['customer_email']}\n"
        f"Subject: {ticket['subject']}\n"
        f"Body: {ticket['body']}"
    )
    return system_prompt, user_prompt


def build_resolution_prompts(ticket: dict, triage: dict) -> tuple[str, str]:
    system_prompt = (
        "You are a frontline support agent drafting a customer response. Use the supplied knowledge base only. "
        "Return JSON only and do not use markdown fences."
    )
    kb_entry = KNOWLEDGE_BASE[triage["category"]]
    user_prompt = (
        "Draft a support response for this ticket.\n\n"
        "Return JSON with exactly these keys:\n"
        "customer_response: a concise email-style reply\n"
        "kb_article: the knowledge base title you used\n"
        "resolution_summary: one sentence summarizing the action taken\n\n"
        "Knowledge Base Entry:\n"
        f"Title: {kb_entry['title']}\n"
        f"Summary: {kb_entry['summary']}\n"
        f"When to use: {kb_entry['when_to_use']}\n\n"
        f"Ticket ID: {ticket['id']}\n"
        f"Customer: {ticket['customer_email']}\n"
        f"Subject: {ticket['subject']}\n"
        f"Body: {ticket['body']}\n\n"
        f"Triage category: {triage['category']}\n"
        f"Priority: {triage['priority']}\n"
        f"Resolution reason: {triage['reason']}"
    )
    return system_prompt, user_prompt


def format_category(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def short_quote(text: str, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def build_ascii_sparkline(counts: list[int]) -> str:
    if not counts:
        return ""

    charset = ".:-=+*#%@"
    max_count = max(counts)
    if max_count == 0:
        return "." * len(counts)

    return "".join(
        charset[round((count / max_count) * (len(charset) - 1))] for count in counts
    )


def summarize_pipeline_output(tickets: list[dict]) -> dict:
    total_tickets = len(tickets)
    resolved_tickets = [
        ticket for ticket in tickets if ticket["result"]["status"] == "resolved"
    ]
    escalated_tickets = [
        ticket for ticket in tickets if ticket["result"]["status"] == "escalated"
    ]

    day_counts = Counter(ticket["created_at"][:10] for ticket in tickets)
    ordered_days = sorted(day_counts)
    ordered_day_counts = [day_counts[day] for day in ordered_days]
    category_counts = Counter(ticket["triage"]["category"] for ticket in tickets)

    top_recurring_issues = []
    for category, count in category_counts.most_common(3):
        matching_tickets = [
            ticket for ticket in tickets if ticket["triage"]["category"] == category
        ]
        top_recurring_issues.append(
            {
                "category": category,
                "label": format_category(category),
                "count": count,
                "resolved": sum(
                    ticket["result"]["status"] == "resolved"
                    for ticket in matching_tickets
                ),
                "escalated": sum(
                    ticket["result"]["status"] == "escalated"
                    for ticket in matching_tickets
                ),
                "example_quotes": [
                    short_quote(ticket["body"]) for ticket in matching_tickets[:2]
                ],
            }
        )

    escalation_groups = []
    escalation_counts = Counter(
        ticket["triage"]["category"] for ticket in escalated_tickets
    )
    for category, count in escalation_counts.most_common():
        matching_tickets = [
            ticket
            for ticket in escalated_tickets
            if ticket["triage"]["category"] == category
        ]
        escalation_groups.append(
            {
                "category": category,
                "label": format_category(category),
                "count": count,
                "reasons": [
                    ticket["result"]["reason"] for ticket in matching_tickets[:3]
                ],
                "example_quotes": [
                    short_quote(ticket["body"]) for ticket in matching_tickets[:2]
                ],
            }
        )

    return {
        "total_tickets": total_tickets,
        "resolved_count": len(resolved_tickets),
        "escalated_count": len(escalated_tickets),
        "resolution_rate": round((len(resolved_tickets) / total_tickets) * 100, 1)
        if total_tickets
        else 0,
        "escalation_rate": round((len(escalated_tickets) / total_tickets) * 100, 1)
        if total_tickets
        else 0,
        "category_breakdown": [
            {
                "category": category,
                "label": format_category(category),
                "count": count,
            }
            for category, count in category_counts.most_common()
        ],
        "top_recurring_issues": top_recurring_issues,
        "escalation_groups": escalation_groups,
        "sparkline": {
            "days": [day[-2:] for day in ordered_days],
            "counts": ordered_day_counts,
            "line": build_ascii_sparkline(ordered_day_counts),
        },
    }


def build_recommendations_prompt(summary: dict, tickets: list[dict]) -> tuple[str, str]:
    system_prompt = (
        "You are a senior support analyst writing product recommendations from support data. "
        "Return JSON only with a `recommendations` array of exactly 3 items. Each item must contain `title` and `reason`."
    )
    user_prompt = (
        "Use this weekly support summary and ticket output to produce exactly 3 concrete product recommendations.\n"
        "Focus on the highest-leverage fixes, not generic process advice.\n\n"
        "Weekly Summary:\n"
        + json.dumps(summary, indent=2)
        + "\n\nPipeline Output JSON:\n"
        + json.dumps(tickets, indent=2)
    )
    return system_prompt, user_prompt


def render_postmortem(summary: dict, recommendations: list[dict]) -> str:
    lines = [
        "# Weekly Support Post-Mortem",
        "",
        "## This Week at a Glance",
        f"- **Total Ticket Volume:** {summary['total_tickets']}",
        f"- **Resolution Rate:** {summary['resolution_rate']}% ({summary['resolved_count']} resolved, {summary['escalated_count']} escalated)",
        f"- **Escalation Rate:** {summary['escalation_rate']}%",
        "- **Volume by Day:**",
        f"  `{summary['sparkline']['line']}`",
        f"  Days: {' '.join(summary['sparkline']['days'])}",
        f"  Counts: {' '.join(str(count) for count in summary['sparkline']['counts'])}",
        "",
        "## Top 3 Recurring Issues",
    ]

    for index, issue in enumerate(summary["top_recurring_issues"], start=1):
        lines.append(
            f"{index}. **{issue['label']}** ({issue['count']} tickets; {issue['resolved']} resolved, {issue['escalated']} escalated)"
        )
        for quote in issue["example_quotes"]:
            lines.append(f'   - "{quote}"')

    lines.extend(["", "## What's Getting Escalated and Why"])
    for group in summary["escalation_groups"][:5]:
        lines.append(f"- **{group['label']}** ({group['count']} escalations)")
        if group["reasons"]:
            lines.append(f"  Reason: {group['reasons'][0]}")
        for quote in group["example_quotes"][:1]:
            lines.append(f'  Example: "{quote}"')

    lines.extend(["", "## Recommendations for Product Team"])
    for index, recommendation in enumerate(recommendations[:3], start=1):
        lines.append(
            f"{index}. **{recommendation['title']}**: {recommendation['reason']}"
        )

    return "\n".join(lines)


def render_report_html(summary: dict, recommendations: list[dict]) -> str:
    issue_items = []
    for issue in summary["top_recurring_issues"]:
        quotes = "".join(
            f"<li>{escape(quote)}</li>" for quote in issue["example_quotes"]
        )
        issue_items.append(
            "".join(
                [
                    '<article class="card">',
                    f"<h3>{escape(issue['label'])}</h3>",
                    f'<p class="meta">{issue["count"]} tickets, {issue["resolved"]} resolved, {issue["escalated"]} escalated</p>',
                    f"<ul>{quotes}</ul>",
                    "</article>",
                ]
            )
        )

    escalation_items = []
    for group in summary["escalation_groups"][:5]:
        reason = escape(group["reasons"][0]) if group["reasons"] else ""
        quote = escape(group["example_quotes"][0]) if group["example_quotes"] else ""
        escalation_items.append(
            "".join(
                [
                    '<article class="card">',
                    f"<h3>{escape(group['label'])}</h3>",
                    f'<p class="meta">{group["count"]} escalations</p>',
                    f"<p>{reason}</p>",
                    f"<blockquote>{quote}</blockquote>",
                    "</article>",
                ]
            )
        )

    recommendation_items = []
    for recommendation in recommendations[:3]:
        recommendation_items.append(
            "".join(
                [
                    '<article class="card recommendation">',
                    f"<h3>{escape(recommendation['title'])}</h3>",
                    f"<p>{escape(recommendation['reason'])}</p>",
                    "</article>",
                ]
            )
        )

    sparkline_days = " ".join(summary["sparkline"]["days"])
    sparkline_counts = " ".join(str(count) for count in summary["sparkline"]["counts"])

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Weekly Support Post-Mortem</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1020;
      --panel: #131a2e;
      --muted: #8d99b8;
      --text: #edf2ff;
      --accent: #7cc7ff;
      --border: #283252;
      --good: #7fe3b0;
      --warn: #ffd37a;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: linear-gradient(180deg, #0b1020 0%, #11172a 100%); color: var(--text); }}
    main {{ max-width: 980px; margin: 0 auto; padding: 40px 20px 64px; }}
    h1 {{ font-size: 2.4rem; margin: 0 0 8px; }}
    h2 {{ font-size: 1.4rem; margin: 36px 0 16px; }}
    h3 {{ margin: 0 0 8px; font-size: 1.05rem; }}
    p, li, blockquote {{ line-height: 1.55; }}
    .lede {{ color: var(--muted); max-width: 720px; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 20px; }}
    .stat, .card {{ background: rgba(19, 26, 46, 0.88); border: 1px solid var(--border); border-radius: 16px; padding: 16px; backdrop-filter: blur(6px); }}
    .stat strong {{ display: block; font-size: 1.6rem; margin-top: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
    .meta {{ color: var(--muted); font-size: 0.95rem; }}
    .sparkline {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: #0e1428; border: 1px solid var(--border); border-radius: 16px; padding: 16px; color: var(--accent); overflow-x: auto; }}
    blockquote {{ margin: 12px 0 0; padding-left: 12px; border-left: 3px solid var(--accent); color: #d7def7; }}
    .recommendation h3 {{ color: var(--warn); }}
    footer {{ margin-top: 40px; color: var(--muted); font-size: 0.92rem; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Weekly Support Post-Mortem</h1>
      <p class=\"lede\">A week of support tickets went through triage, resolve/escalate, and analysis. This static report is the deployed demo artifact.</p>
    </header>

    <section>
      <h2>This Week at a Glance</h2>
      <div class=\"stats\">
        <div class=\"stat\"><span>Total Ticket Volume</span><strong>{summary["total_tickets"]}</strong></div>
        <div class=\"stat\"><span>Resolution Rate</span><strong>{summary["resolution_rate"]}%</strong></div>
        <div class=\"stat\"><span>Escalation Rate</span><strong>{summary["escalation_rate"]}%</strong></div>
      </div>
      <div class=\"sparkline\">
        <div>Volume by day: {escape(summary["sparkline"]["line"])}</div>
        <div>Days:          {escape(sparkline_days)}</div>
        <div>Counts:        {escape(sparkline_counts)}</div>
      </div>
    </section>

    <section>
      <h2>Top 3 Recurring Issues</h2>
      <div class=\"grid\">{"".join(issue_items)}</div>
    </section>

    <section>
      <h2>What's Getting Escalated and Why</h2>
      <div class=\"grid\">{"".join(escalation_items)}</div>
    </section>

    <section>
      <h2>Recommendations for Product Team</h2>
      <div class=\"grid\">{"".join(recommendation_items)}</div>
    </section>

    <footer>Generated from local pipeline output and rendered as a static site for deployment.</footer>
  </main>
</body>
</html>
"""


def write_report_artifacts(
    summary: dict, recommendations: list[dict], report: str
) -> None:
    write_text_file(REPORT_PATH, report + "\n")
    write_json_file(
        REPORT_JSON_PATH,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "recommendations": recommendations,
            "report_markdown": report,
        },
    )
    write_text_file(DIST_INDEX_PATH, render_report_html(summary, recommendations))


def process_ticket(provider: dict, ticket: dict) -> dict:
    print(f"[triage] {ticket['id']} {ticket['subject']}")
    triage_system_prompt, triage_user_prompt = build_triage_prompts(ticket)
    triage_response = traced_llm_call(
        provider,
        step="triage",
        system_prompt=triage_system_prompt,
        user_prompt=triage_user_prompt,
        metadata={"ticket_id": ticket["id"]},
    )
    triage = parse_json_response(triage_response)
    triage = normalize_triage(ticket, triage)

    enriched_ticket = dict(ticket)
    enriched_ticket["triage"] = triage

    if triage["resolvable"] and triage["category"] in KNOWLEDGE_BASE:
        print(f"[resolve] {ticket['id']} {triage['category']}")
        resolution_system_prompt, resolution_user_prompt = build_resolution_prompts(
            ticket, triage
        )
        resolution_response = traced_llm_call(
            provider,
            step="resolve",
            system_prompt=resolution_system_prompt,
            user_prompt=resolution_user_prompt,
            metadata={"ticket_id": ticket["id"], "category": triage["category"]},
        )
        resolution = parse_json_response(resolution_response)
        enriched_ticket["result"] = {
            "status": "resolved",
            "customer_response": resolution["customer_response"],
            "kb_article": resolution["kb_article"],
            "resolution_summary": resolution["resolution_summary"],
        }
    else:
        print(f"[escalate] {ticket['id']} {triage['category']}")
        enriched_ticket["result"] = {
            "status": "escalated",
            "reason": triage["reason"],
        }

    return enriched_ticket


def build_report_from_pipeline_output(provider: dict) -> str:
    processed_tickets = load_tickets(PIPELINE_OUTPUT_PATH)
    summary = summarize_pipeline_output(processed_tickets)
    recommendations_system_prompt, recommendations_user_prompt = (
        build_recommendations_prompt(summary, processed_tickets)
    )
    recommendations_response = traced_llm_call(
        provider,
        step="recommendations",
        system_prompt=recommendations_system_prompt,
        user_prompt=recommendations_user_prompt,
        metadata={"ticket_count": len(processed_tickets), "render_only": True},
    )
    recommendations = parse_json_response(recommendations_response)["recommendations"]
    report = render_postmortem(summary, recommendations)
    write_report_artifacts(summary, recommendations, report)
    return report


def main() -> int:
    try:
        load_local_env()
        provider = get_provider()

        if len(sys.argv) > 1 and sys.argv[1] == "--render-site":
            report = build_report_from_pipeline_output(provider)
            print(report)
            return 0

        tickets = load_tickets(TICKETS_PATH)

        processed_tickets = []
        for ticket in tickets:
            processed_tickets.append(process_ticket(provider, ticket))
            write_pipeline_output(processed_tickets)

        print("[postmortem] generating weekly report")
        summary = summarize_pipeline_output(processed_tickets)
        recommendations_system_prompt, recommendations_user_prompt = (
            build_recommendations_prompt(summary, processed_tickets)
        )
        recommendations_response = traced_llm_call(
            provider,
            step="recommendations",
            system_prompt=recommendations_system_prompt,
            user_prompt=recommendations_user_prompt,
            metadata={"ticket_count": len(processed_tickets)},
        )
        recommendations = parse_json_response(recommendations_response)[
            "recommendations"
        ]
        report = render_postmortem(summary, recommendations)
        write_report_artifacts(summary, recommendations, report)
    except FileNotFoundError as error:
        print(f"Missing required file: {error.filename}", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        print(
            "Set OPENCODE_ZEN_API_KEY before running `python main.py`.", file=sys.stderr
        )
        return 1
    except json.JSONDecodeError as error:
        print(f"Failed to parse model JSON output: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Failed to run support pipeline: {error}", file=sys.stderr)
        return 1

    print()
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
