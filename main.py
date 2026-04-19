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
MODEL_PRICING_PER_1K_TOKENS = {
    "glm-5": {"input": 0.0005, "output": 0.0015},
}
TICKETS_PATH = "tickets.json"
TRACES_PATH = "traces.jsonl"
PIPELINE_OUTPUT_PATH = "pipeline_output.json"
REPORT_PATH = "report.md"
REPORT_JSON_PATH = "report.json"
DIST_DIR = "dist"
DIST_INDEX_PATH = os.path.join(DIST_DIR, "index.html")
DIST_RUN_VIEW_PATH = os.path.join(DIST_DIR, "latest-run.html")
DIST_RUNS_DIR = os.path.join(DIST_DIR, "runs")
DIST_RUNS_INDEX_PATH = os.path.join(DIST_RUNS_DIR, "index.html")
DIST_LATEST_RUN_JSON_PATH = os.path.join(DIST_DIR, "latest-run.json")
RUNS_DIR = "runs"
EVAL_EXPECTATIONS_PATH = "expectations.json"
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


def append_trace(payload: dict, path: str = TRACES_PATH) -> None:
    with open(path, "a", encoding="utf-8") as file:
        file.write(json.dumps(payload) + "\n")


def write_pipeline_output(
    tickets: list[dict], path: str = PIPELINE_OUTPUT_PATH
) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
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


def load_json_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_jsonl_file(path: str) -> list[dict]:
    entries = []
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            entries.append(json.loads(stripped))
    return entries


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def create_run_context(kind: str = "pipeline") -> dict:
    run_id = new_run_id(kind)
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "trace_path": os.path.join(run_dir, "traces.jsonl"),
        "pipeline_output_path": os.path.join(run_dir, "pipeline_output.json"),
        "report_path": os.path.join(run_dir, "report.md"),
        "report_json_path": os.path.join(run_dir, "report.json"),
        "viewer_path": os.path.join(run_dir, "latest-run.html"),
        "manifest_path": os.path.join(run_dir, "run.json"),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "events": [],
    }


def append_run_event(context: dict, payload: dict) -> None:
    entry = {**payload, "run_id": context["run_id"]}
    context["events"].append(entry)
    append_trace(entry)
    append_trace(entry, context["trace_path"])


def record_run_step(
    context: dict,
    *,
    step: str,
    agent: str,
    status: str,
    metadata: dict | None = None,
    response: str | None = None,
    error: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    parent_step: str | None = None,
    latency_ms: float | None = None,
    prompt_tokens_estimate: int | None = None,
    response_tokens_estimate: int | None = None,
    estimated_cost_usd: float | None = None,
    system_prompt: str | None = None,
    user_prompt: str | None = None,
) -> None:
    append_run_event(
        context,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": str(uuid.uuid4()),
            "step": step,
            "agent": agent,
            "parent_step": parent_step,
            "metadata": metadata or {},
            "provider": provider,
            "model": model,
            "prompt_tokens_estimate": prompt_tokens_estimate,
            "response_tokens_estimate": response_tokens_estimate,
            "estimated_cost_usd": estimated_cost_usd,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response": response,
            "latency_ms": latency_ms,
            "status": status,
            **({"error": error} if error else {}),
        },
    )


def estimate_prompt_size(*parts: str) -> int:
    return sum(len(part.split()) for part in parts)


def estimate_llm_cost(
    model: str | None, prompt_tokens: int, response_tokens: int
) -> float | None:
    if model is None:
        return None

    pricing = MODEL_PRICING_PER_1K_TOKENS.get(model)
    if pricing is None:
        return None

    prompt_cost = (prompt_tokens / 1000) * pricing["input"]
    response_cost = (response_tokens / 1000) * pricing["output"]
    return round(prompt_cost + response_cost, 6)


def summarize_trace_entries(trace_entries: list[dict]) -> dict:
    prompt_tokens_total = 0
    response_tokens_total = 0
    total_cost_usd = 0.0
    cost_entry_count = 0

    for entry in trace_entries:
        prompt_tokens_total += int(entry.get("prompt_tokens_estimate") or 0)
        response_tokens_total += int(entry.get("response_tokens_estimate") or 0)

        estimated_cost = entry.get("estimated_cost_usd")
        if estimated_cost is not None:
            total_cost_usd += float(estimated_cost)
            cost_entry_count += 1

    return {
        "trace_count": len(trace_entries),
        "llm_prompt_tokens": prompt_tokens_total,
        "llm_response_tokens": response_tokens_total,
        "llm_total_tokens": prompt_tokens_total + response_tokens_total,
        "estimated_cost_usd": round(total_cost_usd, 6),
        "cost_entry_count": cost_entry_count,
    }


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


def determine_local_triage(ticket: dict) -> dict:
    text = f"{ticket['subject']}\n{ticket['body']}".lower()

    if any(
        phrase in text
        for phrase in [
            "login loop",
            "logging in",
            "sign in",
            "session",
            "mobile safari",
            "iphone",
            "ipad",
        ]
    ):
        return {
            "category": "mobile_login_loop",
            "priority": "high",
            "resolvable": False,
            "reason": "Persistent login loops on mobile Safari usually need engineering investigation.",
        }

    if "csv" in text or "export" in text:
        if any(
            phrase in text
            for phrase in ["blank", "missing", "garbled", "cut off", "headers", "rows"]
        ):
            return {
                "category": "csv_export",
                "priority": "high",
                "resolvable": False,
                "reason": "CSV export issues are typically product bugs that frontline support cannot patch.",
            }

    if any(
        phrase in text
        for phrase in [
            "billed twice",
            "charged twice",
            "duplicate charge",
            "duplicate charges",
        ]
    ):
        return {
            "category": "duplicate_billing",
            "priority": "high",
            "resolvable": False,
            "reason": "Duplicate billing needs billing-system investigation and refund handling.",
        }

    if "password reset" in text or ("reset" in text and "email" in text):
        return {
            "category": "password_reset",
            "priority": "high",
            "resolvable": True,
            "reason": "Frontline support can resend the reset flow and help with inbox troubleshooting.",
        }

    if any(
        phrase in text
        for phrase in [
            "dark mode",
            "feature request",
            "schedule export",
            "schedule exports",
        ]
    ):
        return {
            "category": "feature_request",
            "priority": "low",
            "resolvable": True,
            "reason": "Frontline support can acknowledge the request and log product feedback.",
        }

    if "invoice" in text or "receipt" in text or "typo" in text or "wording" in text:
        return {
            "category": "invoice_copy",
            "priority": "low",
            "resolvable": True,
            "reason": "Frontline support can confirm the typo and reassure the customer.",
        }

    if any(
        phrase in text for phrase in ["slow", "timeout", "time out", "time-out", "lag"]
    ):
        return {
            "category": "slow_dashboard",
            "priority": "high",
            "resolvable": True,
            "reason": "Frontline support can collect timing details and offer safe troubleshooting steps.",
        }

    if "invite" in text:
        return {
            "category": "team_invites",
            "priority": "medium",
            "resolvable": True,
            "reason": "Frontline support can provide invite troubleshooting and retry guidance.",
        }

    if "search" in text or "account name" in text or "relevance" in text:
        return {
            "category": "search_accuracy",
            "priority": "medium",
            "resolvable": True,
            "reason": "Frontline support can provide a temporary search workaround while relevance is reviewed.",
        }

    return {
        "category": "other",
        "priority": "medium",
        "resolvable": False,
        "reason": "Needs manual review because it does not match a known frontline pattern.",
    }


def draft_local_resolution(ticket: dict, triage: dict) -> dict:
    kb_entry = KNOWLEDGE_BASE.get(triage["category"])
    if kb_entry is None:
        return {
            "customer_response": "Thanks for the report. We are reviewing this with the appropriate team and will follow up shortly.",
            "kb_article": "Internal follow-up",
            "resolution_summary": "Logged the issue for follow-up.",
        }

    return {
        "customer_response": (
            f"Hi {ticket['customer_email']},\n\n"
            f"Thanks for reaching out. {kb_entry['summary']}\n\n"
            "Please let us know if that does not resolve the issue."
        ),
        "kb_article": kb_entry["title"],
        "resolution_summary": kb_entry["summary"],
    }


def draft_local_recommendations(summary: dict) -> list[dict]:
    recommendations = []
    issue_map = {
        "mobile_login_loop": (
            "Fix the mobile login loop",
            "Recurring mobile sign-in loops are the clearest blocker in the queue and keep reappearing across multiple tickets.",
        ),
        "csv_export": (
            "Repair CSV export reliability",
            "CSV exports are repeatedly missing rows or columns, which breaks finance workflows and looks like a product bug rather than a one-off incident.",
        ),
        "duplicate_billing": (
            "Add duplicate billing safeguards",
            "Billing complaints are high-friction escalations because customers need a refund path and immediate confirmation.",
        ),
        "slow_dashboard": (
            "Investigate dashboard latency",
            "Slow pages and timeouts are affecting report usage and should be treated as a performance regression.",
        ),
        "team_invites": (
            "Stabilize teammate invites",
            "Invite failures block onboarding and create immediate support load.",
        ),
        "search_accuracy": (
            "Improve search relevance for exact matches",
            "Exact-name searches returning the wrong records create trust issues and wasted support time.",
        ),
        "feature_request": (
            "Tighten feature-request intake",
            "Recurring feature requests point to an unmet workflow need and should be visible to product sooner.",
        ),
        "password_reset": (
            "Make password reset delivery more reliable",
            "Password reset tickets are resolvable but still indicate friction in email delivery and account access.",
        ),
        "invoice_copy": (
            "Clean up invoice email copy",
            "Invoice wording issues are minor individually but create unnecessary finance follow-up.",
        ),
    }

    for issue in summary.get("top_recurring_issues", [])[:2]:
        title, reason = issue_map.get(
            issue["category"],
            (
                f"Address {issue['label'].lower()}",
                f"{issue['label']} appears often enough to deserve a product fix.",
            ),
        )
        recommendations.append({"title": title, "reason": reason})

    if summary.get("escalation_groups"):
        top_group = summary["escalation_groups"][0]
        title, reason = issue_map.get(
            top_group["category"],
            (
                f"Reduce {top_group['label'].lower()} escalations",
                f"{top_group['label']} is showing up in escalations and should be reviewed.",
            ),
        )
        recommendations.append({"title": title, "reason": reason})

    while len(recommendations) < 3:
        recommendations.append(
            {
                "title": "Tighten frontline triage",
                "reason": "The queue has repeated support patterns that should be easier to recognize and route.",
            }
        )

    return recommendations[:3]


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
    context: dict,
    step: str,
    agent: str,
    parent_step: str | None,
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    metadata: dict | None = None,
) -> str:
    current_model = model or get_model_name()
    attempt = 1

    while True:
        started_at = time.perf_counter()
        prompt_tokens = estimate_prompt_size(system_prompt, user_prompt)

        try:
            output = call_zen(provider, system_prompt, user_prompt, current_model)
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            response_tokens = estimate_prompt_size(output)
            record_run_step(
                context,
                step=step,
                agent=agent,
                parent_step=parent_step,
                metadata={**(metadata or {}), "attempt": attempt},
                response=output,
                model=current_model,
                provider=provider.get("type"),
                latency_ms=latency_ms,
                prompt_tokens_estimate=prompt_tokens,
                response_tokens_estimate=response_tokens,
                estimated_cost_usd=estimate_llm_cost(
                    current_model, prompt_tokens, response_tokens
                ),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                status="ok",
            )
            return output
        except Exception as error:
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            record_run_step(
                context,
                step=step,
                agent=agent,
                parent_step=parent_step,
                metadata={**(metadata or {}), "attempt": attempt},
                error=str(error),
                model=current_model,
                provider=provider.get("type"),
                latency_ms=latency_ms,
                prompt_tokens_estimate=prompt_tokens,
                response_tokens_estimate=0,
                estimated_cost_usd=estimate_llm_cost(current_model, prompt_tokens, 0),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                status="error",
            )

            retry_delay_seconds = get_retry_delay_seconds(error)
            if retry_delay_seconds is None:
                raise

            print(
                f"[retry] {step} waiting {retry_delay_seconds}s after rate limit (attempt {attempt})",
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
    def _priority_badge(priority: str) -> str:
        colors = {
            "high": "#ff8d8d",
            "medium": "#ffd37a",
            "low": "#7fe3b0",
            "urgent": "#ff6b6b",
        }
        c = colors.get(priority, "#8d99b8")
        return f'<span class="badge" style="background:{c}22;color:{c};border-color:{c}44">{escape(priority.title())}</span>'

    def _severity_bar(resolved: int, escalated: int, total: int) -> str:
        if total == 0:
            return ""
        r_pct = round((resolved / total) * 100)
        e_pct = round((escalated / total) * 100)
        return (
            f'<div class="bar-track">'
            f'<div class="bar-fill resolved" style="width:{r_pct}%"></div>'
            f'<div class="bar-fill escalated" style="width:{e_pct}%;left:{r_pct}%"></div>'
            f"</div>"
            f'<div class="bar-labels"><span class="resolved-label">Resolved {resolved}</span>'
            f'<span class="escalated-label">Escalated {escalated}</span></div>'
        )

    issue_items = []
    for issue in summary["top_recurring_issues"]:
        quotes_html = "".join(
            f'<div class="quote-item">&ldquo;{escape(quote)}&rdquo;</div>'
            for quote in issue["example_quotes"]
        )
        issue_items.append(
            f'<article class="card">'
            f'<div class="card-header">'
            f'<div class="card-icon issue">&#9888;</div>'
            f'<div class="card-title"><h3>{escape(issue["label"])}</h3>'
            f'<p class="meta">{issue["count"]} tickets</p></div></div>'
            f"{_severity_bar(issue['resolved'], issue['escalated'], issue['count'])}"
            f'<div class="quotes">{quotes_html}</div>'
            f"</article>"
        )

    escalation_items = []
    escalation_icons = {
        "mobile_login_loop": "&#128274;",
        "csv_export": "&#128196;",
        "duplicate_billing": "&#128179;",
        "password_reset": "&#128272;",
        "feature_request": "&#128161;",
        "invoice_copy": "&#128203;",
        "slow_dashboard": "&#9201;",
        "team_invites": "&#128101;",
        "search_accuracy": "&#128269;",
        "other": "&#10067;",
    }
    for group in summary["escalation_groups"][:5]:
        reason = escape(group["reasons"][0]) if group["reasons"] else ""
        quote = escape(group["example_quotes"][0]) if group["example_quotes"] else ""
        icon = escalation_icons.get(group["category"], "&#9888;")
        escalation_items.append(
            f'<article class="card escalation-card">'
            f'<div class="card-header">'
            f'<div class="card-icon escalation">{icon}</div>'
            f'<div class="card-title"><h3>{escape(group["label"])}</h3>'
            f'<span class="badge" style="background:#ff8d8d22;color:#ff8d8d;border-color:#ff8d8d44">{group["count"]} escalated</span></div></div>'
            f'<p class="reason">{reason}</p>'
            f'<div class="quote-item">&ldquo;{quote}&rdquo;</div>'
            f"</article>"
        )

    recommendation_items = []
    rec_icons = ["&#127919;", "&#128640;", "&#128172;"]
    for i, recommendation in enumerate(recommendations[:3]):
        recommendation_items.append(
            f'<article class="card recommendation-card">'
            f'<div class="card-header">'
            f'<div class="card-icon recommendation">{rec_icons[i % len(rec_icons)]}</div>'
            f'<div class="card-title"><h3>{escape(recommendation["title"])}</h3></div></div>'
            f"<p>{escape(recommendation['reason'])}</p>"
            f"</article>"
        )

    counts = summary["sparkline"]["counts"]
    days = summary["sparkline"]["days"]
    max_count = max(counts) if counts else 1
    bar_height = 48
    bar_width = 100 / len(counts) if counts else 1
    sparkline_bars = ""
    for i, (day, count) in enumerate(zip(days, counts)):
        h = round((count / max_count) * bar_height) if max_count else 0
        sparkline_bars += (
            f'<div class="bar-col" style="width:{bar_width}%">'
            f'<svg viewBox="0 0 40 {bar_height}" class="bar-svg"><rect x="8" y="{bar_height - h}" width="24" height="{h}" rx="4" fill="var(--accent)" opacity="0.85"/></svg>'
            f'<span class="bar-value">{count}</span>'
            f'<span class="bar-day">{escape(day)}</span>'
            f"</div>"
        )

    category_bars = ""
    breakdown = summary.get("category_breakdown", [])
    if breakdown:
        max_cat = breakdown[0]["count"]
        for cat in breakdown[:6]:
            w = round((cat["count"] / max_cat) * 100)
            category_bars += (
                f'<div class="cat-row">'
                f'<span class="cat-label">{escape(cat["label"])}</span>'
                f'<div class="cat-bar-track"><div class="cat-bar-fill" style="width:{w}%"></div></div>'
                f'<span class="cat-count">{cat["count"]}</span>'
                f"</div>"
            )

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Weekly Support Post-Mortem</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0a0e1a;
      --surface: #111827;
      --surface-raised: #1a2238;
      --muted: #8896b3;
      --text: #e8ecf4;
      --accent: #60a5fa;
      --accent-dim: #60a5fa22;
      --border: #1e2d4a;
      --good: #34d399;
      --good-dim: #34d39922;
      --warn: #fbbf24;
      --warn-dim: #fbbf2422;
      --bad: #f87171;
      --bad-dim: #f8717122;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      min-height: 100vh;
    }}
    nav {{
      position: sticky; top: 0; z-index: 50;
      background: rgba(10, 14, 26, 0.85);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--border);
      padding: 0 24px;
    }}
    nav .nav-inner {{
      max-width: 1120px; margin: 0 auto;
      display: flex; align-items: center; justify-content: space-between;
      height: 56px;
    }}
    nav .logo {{
      font-weight: 700; font-size: 1.05rem; color: var(--text);
      display: flex; align-items: center; gap: 10px;
    }}
    nav .logo .logo-dot {{
      width: 9px; height: 9px; border-radius: 50%;
      background: var(--accent); display: inline-block;
    }}
    nav a {{
      color: var(--muted); text-decoration: none; font-size: 0.9rem;
      transition: color 0.15s;
    }}
    nav a:hover {{ color: var(--accent); }}
    .nav-button {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 8px 14px; border-radius: 999px;
      background: var(--accent-dim); border: 1px solid var(--accent)44;
      color: var(--text); text-decoration: none; font-size: 0.88rem;
      font-weight: 600;
    }}
    .nav-button:hover {{
      border-color: var(--accent);
      color: var(--text);
    }}
    nav .nav-links {{ display: flex; gap: 24px; }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 48px 24px 80px;
    }}
    .hero {{
      position: relative;
      padding: 48px 0 40px;
    }}
    .hero h1 {{
      font-size: 2.25rem; font-weight: 800; letter-spacing: -0.02em;
      background: linear-gradient(135deg, #e8ecf4 0%, #60a5fa 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    .hero .subtitle {{
      color: var(--muted); font-size: 1.05rem; margin-top: 8px; max-width: 640px;
    }}
    .hero-actions {{
      display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px;
    }}
    .hero-cta {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 10px 16px; border-radius: 999px;
      text-decoration: none; font-weight: 700; font-size: 0.92rem;
      border: 1px solid var(--border);
    }}
    .hero-cta.primary {{
      background: var(--accent); color: #08111f; border-color: var(--accent);
    }}
    .hero-cta:hover {{ transform: translateY(-1px); }}
    .section {{
      margin-top: 48px;
    }}
    .section-header {{
      display: flex; align-items: center; gap: 10px; margin-bottom: 20px;
    }}
    .section-icon {{
      width: 32px; height: 32px; border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      font-size: 1rem;
    }}
    .section-icon.glance {{ background: var(--accent-dim); }}
    .section-icon.issues {{ background: var(--bad-dim); }}
    .section-icon.escalated {{ background: var(--warn-dim); }}
    .section-icon.recs {{ background: var(--good-dim); }}
    .section-icon.breakdown {{ background: #a78bfa22; }}
    h2 {{
      font-size: 1.25rem; font-weight: 700; letter-spacing: -0.01em;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
    }}
    .stat {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 20px 24px;
      position: relative;
      overflow: hidden;
      transition: border-color 0.2s;
    }}
    .stat:hover {{ border-color: var(--accent); }}
    .stat .stat-label {{
      font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--muted); font-weight: 600;
    }}
    .stat .stat-value {{
      font-size: 2rem; font-weight: 800; margin-top: 4px; letter-spacing: -0.02em;
    }}
    .stat .stat-sub {{
      font-size: 0.82rem; color: var(--muted); margin-top: 2px;
    }}
    .stat.good .stat-value {{ color: var(--good); }}
    .stat.bad .stat-value {{ color: var(--bad); }}
    .stat.accent .stat-value {{ color: var(--accent); }}
    .stat .stat-glow {{
      position: absolute; top: -20px; right: -20px; width: 80px; height: 80px;
      border-radius: 50%; filter: blur(30px); opacity: 0.15;
    }}
    .stat.good .stat-glow {{ background: var(--good); }}
    .stat.bad .stat-glow {{ background: var(--bad); }}
    .stat.accent .stat-glow {{ background: var(--accent); }}
    .sparkline {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 24px;
      margin-top: 16px;
    }}
    .sparkline-header {{
      font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--muted); font-weight: 600; margin-bottom: 16px;
    }}
    .bar-chart {{
      display: flex; align-items: flex-end; gap: 4px;
    }}
    .bar-col {{
      display: flex; flex-direction: column; align-items: center;
      gap: 4px;
    }}
    .bar-value {{ font-size: 0.75rem; color: var(--muted); font-weight: 600; }}
    .bar-day {{ font-size: 0.72rem; color: var(--muted); }}
    .bar-svg {{ display: block; }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 20px;
      transition: border-color 0.2s, transform 0.15s;
    }}
    .card:hover {{ border-color: rgba(96, 165, 250, 0.3); transform: translateY(-1px); }}
    .card-header {{
      display: flex; align-items: flex-start; gap: 12px; margin-bottom: 14px;
    }}
    .card-icon {{
      width: 36px; height: 36px; border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-size: 1.1rem; flex-shrink: 0;
    }}
    .card-icon.issue {{ background: var(--bad-dim); }}
    .card-icon.escalation {{ background: var(--warn-dim); }}
    .card-icon.recommendation {{ background: var(--good-dim); }}
    .card-title h3 {{
      font-size: 1rem; font-weight: 700; margin-bottom: 2px;
    }}
    .card-title .meta {{
      font-size: 0.82rem; color: var(--muted);
    }}
    .badge {{
      display: inline-block; font-size: 0.72rem; font-weight: 600;
      padding: 2px 8px; border-radius: 6px; border: 1px solid;
      text-transform: uppercase; letter-spacing: 0.04em;
    }}
    .bar-track {{
      height: 6px; background: var(--surface-raised); border-radius: 3px;
      position: relative; overflow: hidden; margin: 10px 0;
    }}
    .bar-fill {{
      position: absolute; top: 0; height: 100%; border-radius: 3px;
    }}
    .bar-fill.resolved {{ background: var(--good); left: 0; }}
    .bar-fill.escalated {{ background: var(--bad); }}
    .bar-labels {{
      display: flex; justify-content: space-between;
      font-size: 0.75rem; color: var(--muted);
    }}
    .quotes {{
      margin-top: 12px;
      display: flex; flex-direction: column; gap: 6px;
    }}
    .quote-item {{
      font-size: 0.88rem; color: #b4bdd4; padding-left: 12px;
      border-left: 2px solid var(--accent); line-height: 1.5;
    }}
    .reason {{
      font-size: 0.92rem; color: var(--muted); margin-bottom: 10px;
    }}
    .escalation-card .quote-item {{
      border-left-color: var(--warn);
    }}
    .recommendation-card .card-title h3 {{
      color: var(--good);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 14px;
    }}
    .cat-section {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 24px;
    }}
    .cat-row {{
      display: flex; align-items: center; gap: 10px; margin-bottom: 8px;
    }}
    .cat-label {{
      font-size: 0.82rem; color: var(--text); min-width: 140px; text-align: right;
    }}
    .cat-bar-track {{
      flex: 1; height: 8px; background: var(--surface-raised); border-radius: 4px;
      overflow: hidden;
    }}
    .cat-bar-fill {{
      height: 100%; border-radius: 4px;
      background: linear-gradient(90deg, var(--accent), #a78bfa);
      transition: width 0.4s ease;
    }}
    .cat-count {{
      font-size: 0.82rem; color: var(--muted); font-weight: 700; min-width: 24px;
    }}
    footer {{
      margin-top: 56px;
      padding-top: 24px;
      border-top: 1px solid var(--border);
      color: var(--muted);
      font-size: 0.82rem;
    }}
  </style>
</head>
<body>
  <nav>
    <div class="nav-inner">
      <div class="logo"><span class="logo-dot"></span>Post-Mortem</div>
      <div class="nav-links">
        <a href="/runs/" class="nav-button">Run History</a>
      </div>
    </div>
  </nav>

  <main>
    <div class="hero">
      <h1>Weekly Support Post-Mortem</h1>
      <p class="subtitle">Automated triage, resolution, and escalation analysis for the past week of support tickets.</p>
      <div class="hero-actions">
        <a href="/runs/" class="hero-cta primary">Open Run History</a>
      </div>
    </div>

    <section class="section">
      <div class="section-header">
        <div class="section-icon glance">&#128202;</div>
        <h2>This Week at a Glance</h2>
      </div>
      <div class="stats">
        <div class="stat accent">
          <div class="stat-glow"></div>
          <div class="stat-label">Total Volume</div>
          <div class="stat-value">{summary["total_tickets"]}</div>
          <div class="stat-sub">tickets processed</div>
        </div>
        <div class="stat good">
          <div class="stat-glow"></div>
          <div class="stat-label">Resolution Rate</div>
          <div class="stat-value">{summary["resolution_rate"]}%</div>
          <div class="stat-sub">{summary["resolved_count"]} resolved</div>
        </div>
        <div class="stat bad">
          <div class="stat-glow"></div>
          <div class="stat-label">Escalation Rate</div>
          <div class="stat-value">{summary["escalation_rate"]}%</div>
          <div class="stat-sub">{summary["escalated_count"]} escalated</div>
        </div>
      </div>
      <div class="sparkline">
        <div class="sparkline-header">Daily Ticket Volume</div>
        <div class="bar-chart">{sparkline_bars}</div>
      </div>
    </section>

    <section class="section">
      <div class="section-header">
        <div class="section-icon breakdown">&#128202;</div>
        <h2>Category Breakdown</h2>
      </div>
      <div class="cat-section">{category_bars}</div>
    </section>

    <section class="section">
      <div class="section-header">
        <div class="section-icon issues">&#9888;</div>
        <h2>Top Recurring Issues</h2>
      </div>
      <div class="grid">{"".join(issue_items)}</div>
    </section>

    <section class="section">
      <div class="section-header">
        <div class="section-icon escalated">&#128293;</div>
        <h2>What's Getting Escalated</h2>
      </div>
      <div class="grid">{"".join(escalation_items)}</div>
    </section>

    <section class="section">
      <div class="section-header">
        <div class="section-icon recs">&#127919;</div>
        <h2>Recommendations</h2>
      </div>
      <div class="grid">{"".join(recommendation_items)}</div>
    </section>

    <footer>Generated from local pipeline output and rendered as a static site for deployment.</footer>
  </main>
</body>
</html>
"""


def render_run_detail_html(manifest: dict, trace_entries: list[dict]) -> str:
    run_id = manifest["run_id"]
    run_kind = run_id.split("-", 1)[0]
    status_counts = Counter(entry.get("status", "unknown") for entry in trace_entries)
    agent_counts = Counter(entry.get("agent", "unknown") for entry in trace_entries)
    trace_summary = summarize_trace_entries(trace_entries)

    def _status_color(s: str) -> str:
        colors = {"ok": "#34d399", "fallback": "#fbbf24", "error": "#f87171"}
        return colors.get(s, "#8896b3")

    def _status_badge(s: str) -> str:
        c = _status_color(s)
        return f'<span class="badge" style="background:{c}22;color:{c};border-color:{c}44">{escape(s)}</span>'

    def _agent_badge(a: str) -> str:
        return f'<span class="badge agent">{escape(a)}</span>'

    def _mini_chip(label: str, value: str, tone: str = "") -> str:
        tone_class = f" {tone}" if tone else ""
        return (
            f'<span class="mini-chip{tone_class}">'
            f'<span class="mini-chip-label">{escape(label)}</span>'
            f'<span class="mini-chip-value">{escape(value)}</span>'
            f"</span>"
        )

    def _preview(value: object, limit: int = 220) -> str:
        if value is None:
            return ""
        text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        text = " ".join(str(text).split())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    trace_rows = []
    for entry in trace_entries:
        metadata = entry.get("metadata") or {}
        step = str(entry.get("step", ""))
        parent = entry.get("parent_step")
        error = entry.get("error")

        step_short = step.split(":")[-1] if ":" in step else step[:24]
        if len(step) > 24:
            step_short += "..."

        latency = entry.get("latency_ms")
        latency_str = f"{latency:.1f}ms" if latency is not None else "-"
        ticket_id = metadata.get("ticket_id")
        prompt_tokens = entry.get("prompt_tokens_estimate")
        response_tokens = entry.get("response_tokens_estimate")
        estimated_cost = entry.get("estimated_cost_usd")

        extras = []
        if ticket_id:
            extras.append(_mini_chip("Ticket", str(ticket_id)))
        if prompt_tokens is not None:
            extras.append(_mini_chip("Prompt tokens", str(prompt_tokens)))
        if response_tokens is not None:
            extras.append(_mini_chip("Response tokens", str(response_tokens)))
        if estimated_cost is not None:
            extras.append(_mini_chip("Est. cost", f"${float(estimated_cost):.4f}"))

        agent_name = str(entry.get("agent", "unknown"))
        status_name = str(entry.get("status", "unknown"))
        agent_badge_html = _agent_badge(agent_name)
        status_badge_html = _status_badge(status_name)
        timestamp_html = escape(str(entry.get("timestamp", "unknown"))[:19])
        provider_html = escape(str(entry.get("provider") or "local"))
        model_html = escape(str(entry.get("model") or "-"))
        parent_html = escape(str(parent or "-"))
        metadata_html = escape(json.dumps(metadata, sort_keys=True, indent=2))
        system_prompt = entry.get("system_prompt")
        user_prompt = entry.get("user_prompt")
        response = entry.get("response")
        prompt_text = ""
        if system_prompt or user_prompt:
            prompt_text = (system_prompt or "") + (
                "\n\n" + user_prompt if user_prompt else ""
            )
        prompt_block = ""
        if system_prompt or user_prompt:
            prompt_block = (
                f'<div class="raw-block">'
                f'<div class="raw-label">Prompts</div>'
                f"<pre>{escape(_preview(prompt_text, 1200))}</pre>"
                f"</div>"
            )
        response_block = ""
        if response:
            response_block = (
                f'<div class="raw-block">'
                f'<div class="raw-label">Response</div>'
                f"<pre>{escape(_preview(response, 1200))}</pre>"
                f"</div>"
            )
        error_block = ""
        if error:
            error_block = (
                f'<div class="raw-block error">'
                f'<div class="raw-label">Error</div>'
                f"<pre>{escape(error)}</pre>"
                f"</div>"
            )

        search_blob = " ".join(
            part
            for part in [
                step,
                str(ticket_id or ""),
                agent_name,
                status_name,
                str(metadata),
                str(parent or ""),
            ]
            if part
        ).lower()

        trace_rows.append(
            f'<details class="trace-card" data-agent="{escape(agent_name)}" data-status="{escape(status_name)}" data-search="{escape(search_blob)}">'
            f'<summary class="trace-summary">'
            f'<div class="trace-summary-main">'
            f"{agent_badge_html}"
            f"{status_badge_html}"
            f'<span class="step">{escape(step_short)}</span>'
            f"</div>"
            f'<div class="trace-summary-meta">'
            f"<span>{timestamp_html}</span>"
            f"<span>{escape(latency_str)}</span>"
            f"{''.join(extras)}"
            f"</div>"
            f"</summary>"
            f'<div class="trace-body">'
            f'<div class="trace-body-row">'
            f'<div class="detail"><span class="label">Parent</span><code>{parent_html}</code></div>'
            f'<div class="detail"><span class="label">Provider</span><code>{provider_html}</code></div>'
            f'<div class="detail"><span class="label">Model</span><code>{model_html}</code></div>'
            f"</div>"
            f'<div class="raw-block">'
            f'<div class="raw-label">Metadata</div>'
            f"<pre>{metadata_html}</pre>"
            f"</div>"
            f"{prompt_block}"
            f"{response_block}"
            f"{error_block}"
            f"</div>"
            f"</details>"
        )

    summary_cards = [
        f'<div class="stat"><span class="stat-label">Run Type</span><span class="stat-value">{escape(run_kind)}</span></div>',
        f'<div class="stat"><span class="stat-label">Tickets</span><span class="stat-value">{escape(str(manifest.get("ticket_count", "?")))}</span></div>',
        f'<div class="stat good"><span class="stat-label">Resolved</span><span class="stat-value">{escape(str(manifest.get("resolved", "?")))}</span></div>',
        f'<div class="stat bad"><span class="stat-label">Escalated</span><span class="stat-value">{escape(str(manifest.get("escalated", "?")))}</span></div>',
        f'<div class="stat accent"><span class="stat-label">LLM Tokens</span><span class="stat-value">{trace_summary["llm_total_tokens"]}</span></div>',
        f'<div class="stat accent"><span class="stat-label">Est. Cost</span><span class="stat-value">${trace_summary["estimated_cost_usd"]:.4f}</span></div>',
    ]

    trace_meta_chips = [
        _mini_chip("Trace events", str(len(trace_entries)), "accent"),
        _mini_chip("Errors", str(status_counts.get("error", 0)), "bad"),
        _mini_chip("Prompt tokens", str(trace_summary["llm_prompt_tokens"]), "accent"),
        _mini_chip(
            "Response tokens", str(trace_summary["llm_response_tokens"]), "accent"
        ),
        _mini_chip(
            "Est. cost", f"${trace_summary['estimated_cost_usd']:.4f}", "accent"
        ),
    ]
    trace_meta_chips.extend(
        _mini_chip(agent, str(count)) for agent, count in sorted(agent_counts.items())
    )
    trace_meta_chips.extend(
        _mini_chip(status, str(count))
        for status, count in sorted(status_counts.items())
    )

    artifact_links = []
    artifact_prefix = "../"
    report_snapshot = manifest.get("artifacts", {}).get("report_snapshot")
    traces_snapshot = manifest.get("artifacts", {}).get("traces_snapshot")
    manifest_snapshot = manifest.get("artifacts", {}).get("manifest_snapshot")
    if report_snapshot:
        artifact_links.append(
            f'<a href="{artifact_prefix}{escape(report_snapshot)}" class="artifact-link">&#128196; Report</a>'
        )
    if traces_snapshot:
        artifact_links.append(
            f'<a href="{artifact_prefix}{escape(traces_snapshot)}" class="artifact-link">&#128196; Traces</a>'
        )
    if manifest_snapshot:
        artifact_links.append(
            f'<a href="{artifact_prefix}{escape(manifest_snapshot)}" class="artifact-link">&#128196; Manifest</a>'
        )

    agent_options = ['<option value="all">All agents</option>']
    agent_options.extend(
        f'<option value="{escape(agent)}">{escape(agent.title())}</option>'
        for agent in sorted(agent_counts)
    )
    status_options = ['<option value="all">All statuses</option>']
    status_options.extend(
        f'<option value="{escape(status)}">{escape(status.title())}</option>'
        for status in sorted(status_counts)
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(run_id)} Observability</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0a0e1a;
      --surface: #111827;
      --surface-raised: #1a2238;
      --muted: #8896b3;
      --text: #e8ecf4;
      --accent: #60a5fa;
      --border: #1e2d4a;
      --good: #34d399;
      --bad: #f87171;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      min-height: 100vh;
    }}
    nav {{
      position: sticky; top: 0; z-index: 50;
      background: rgba(10, 14, 26, 0.85);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--border);
      padding: 0 24px;
    }}
    nav .nav-inner {{
      max-width: 1120px; margin: 0 auto;
      display: flex; align-items: center; justify-content: space-between;
      height: 56px;
    }}
    nav .logo {{
      font-weight: 700; font-size: 1.05rem; color: var(--text);
      display: flex; align-items: center; gap: 10px;
    }}
    nav .logo .logo-dot {{
      width: 9px; height: 9px; border-radius: 50%;
      background: var(--accent); display: inline-block;
    }}
    nav a {{
      color: var(--muted); text-decoration: none; font-size: 0.9rem;
      transition: color 0.15s;
    }}
    nav a:hover {{ color: var(--accent); }}
    nav .nav-links {{ display: flex; gap: 24px; }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 48px 24px 80px;
    }}
    .back-nav {{
      display: flex; gap: 16px; margin-bottom: 24px;
    }}
    .back-nav a {{
      color: var(--muted); font-size: 0.9rem;
    }}
    .back-nav a:hover {{ color: var(--accent); }}
    .hero h1 {{
      font-size: 1.5rem; font-weight: 700;
      font-family: ui-monospace, SFMono-Regular, monospace;
      margin-bottom: 8px;
    }}
    .hero .subtitle {{
      color: var(--muted); font-size: 0.95rem;
    }}
    .section {{
      margin-top: 36px;
    }}
    .section-header {{
      font-size: 1rem; font-weight: 700;
      margin-bottom: 14px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
    }}
    .stat {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      text-align: center;
    }}
    .stat.good .stat-value {{ color: var(--good); }}
    .stat.bad .stat-value {{ color: var(--bad); }}
    .stat-label {{
      display: block; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
      color: var(--muted); margin-bottom: 4px;
    }}
    .stat-value {{
      display: block; font-size: 1.5rem; font-weight: 800;
    }}
    .meta-row {{
      display: flex; flex-wrap: wrap; gap: 12px; margin-top: 16px;
      font-size: 0.85rem; color: var(--muted);
    }}
    .filters {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px;
      margin-top: 16px;
    }}
    .filter-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
    }}
    .filter-card label {{
      display: block; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
      color: var(--muted); margin-bottom: 8px;
    }}
    .filter-card select,
    .filter-card input {{
      width: 100%;
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      padding: 10px 12px;
      font-size: 0.88rem;
    }}
    .filter-card input::placeholder {{ color: var(--muted); }}
    .artifact-links {{
      display: flex; gap: 10px; flex-wrap: wrap;
    }}
    .artifact-link {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 8px 14px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text); text-decoration: none; font-size: 0.85rem;
      transition: border-color 0.15s;
    }}
    .artifact-link:hover {{ border-color: var(--accent); }}
    .trace-list {{
      display: flex; flex-direction: column; gap: 10px;
    }}
    .trace-card.is-hidden {{ display: none; }}
    .trace-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      transition: border-color 0.15s;
      overflow: hidden;
    }}
    .trace-card:hover {{ border-color: var(--accent); }}
    .trace-card[open] {{
      border-color: rgba(96, 165, 250, 0.45);
    }}
    .trace-card > summary {{
      list-style: none;
      cursor: pointer;
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 16px;
    }}
    .trace-card > summary::-webkit-details-marker {{ display: none; }}
    .trace-summary-main {{
      display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
      min-width: 0;
    }}
    .trace-summary-meta {{
      display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px;
      color: var(--muted); font-size: 0.78rem;
      text-align: right;
    }}
    .trace-summary-meta span {{
      font-family: ui-monospace, SFMono-Regular, monospace;
    }}
    .trace-body {{
      border-top: 1px solid var(--border);
      padding: 14px 16px 16px;
      display: grid;
      gap: 12px;
    }}
    .trace-body-row {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px;
    }}
    .mini-chip {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 4px 8px; border-radius: 999px; border: 1px solid var(--border);
      background: var(--surface-raised);
      color: var(--text); font-size: 0.72rem;
    }}
    .mini-chip.accent {{ border-color: var(--accent)44; background: var(--accent)18; }}
    .mini-chip.bad {{ border-color: var(--bad)44; background: var(--bad)18; }}
    .mini-chip-label {{
      color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em;
      font-size: 0.65rem;
    }}
    .mini-chip-value {{ font-weight: 700; }}
    .badge {{
      display: inline-block; font-size: 0.7rem; font-weight: 600;
      padding: 3px 8px; border-radius: 6px; border: 1px solid;
      text-transform: uppercase; letter-spacing: 0.04em;
    }}
    .badge.agent {{
      background: var(--accent)22; color: var(--accent); border-color: var(--accent)44;
    }}
    .step {{
      font-size: 0.85rem; font-weight: 600;
      font-family: ui-monospace, SFMono-Regular, monospace;
    }}
    .detail {{
      font-size: 0.8rem; display: flex; align-items: center; gap: 8px;
    }}
    .detail .label {{
      color: var(--muted); font-weight: 600; min-width: 64px;
    }}
    .detail code {{
      font-family: ui-monospace, SFMono-Regular, monospace;
      font-size: 0.75rem; background: var(--surface-raised);
      padding: 2px 6px; border-radius: 4px;
      word-break: break-all;
    }}
    .raw-block {{
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
    }}
    .raw-block.error {{
      border-color: var(--bad)44;
    }}
    .raw-label {{
      font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--muted); font-weight: 700; margin-bottom: 8px;
    }}
    .raw-block pre {{
      white-space: pre-wrap; word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, monospace;
      font-size: 0.75rem; line-height: 1.5; color: var(--text);
    }}
    .raw-block.error pre {{
      color: var(--bad);
    }}
  </style>
</head>
<body>
  <nav>
    <div class="nav-inner">
      <div class="logo"><span class="logo-dot"></span>Post-Mortem</div>
      <div class="nav-links">
        <a href="./index.html">Run History</a>
        <a href="../index.html">Latest Report</a>
      </div>
    </div>
  </nav>

  <main>
    <div class="back-nav">
      <a href="./index.html">&#8592; Runs</a>
      <a href="../index.html">&#8592; Report</a>
    </div>

    <div class="hero">
      <h1>{escape(run_id)}</h1>
      <p class="subtitle">Observability trace details for this pipeline run.</p>
    </div>

    <section class="section">
      <div class="section-header">Summary</div>
      <div class="stats">{"".join(summary_cards)}</div>
      <div class="meta-row">
        <span>Started: {escape(str(manifest.get("started_at", "unknown"))[:19])}</span>
        <span>Finished: {escape(str(manifest.get("finished_at", "unknown"))[:19])}</span>
        {"<span>Case: " + escape(str(manifest.get("case"))) + "</span>" if manifest.get("case") else ""}
      </div>
    </section>

    <section class="section">
      <div class="section-header">Artifacts</div>
      <div class="artifact-links">{"".join(artifact_links) or '<span class="muted">No artifacts available.</span>'}</div>
    </section>

    <section class="section">
      <div class="section-header">Trace Overview</div>
      <div class="meta-row">{"".join(trace_meta_chips) or '<span class="muted">No trace events.</span>'}</div>
      <div class="filters">
        <div class="filter-card">
          <label for="agent-filter">Agent</label>
          <select id="agent-filter">{"".join(agent_options)}</select>
        </div>
        <div class="filter-card">
          <label for="status-filter">Status</label>
          <select id="status-filter">{"".join(status_options)}</select>
        </div>
        <div class="filter-card">
          <label for="trace-search">Search</label>
          <input id="trace-search" type="search" placeholder="ticket id, step, parent step">
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-header">Trace Timeline (<span id="trace-visible-count">{len(trace_entries)}</span> / {len(trace_entries)} events, collapsed by default)</div>
      <div class="trace-list">{"".join(trace_rows) or '<span class="muted">No trace events recorded for this run.</span>'}</div>
    </section>
  </main>
  <script>
    const agentFilter = document.getElementById('agent-filter');
    const statusFilter = document.getElementById('status-filter');
    const traceSearch = document.getElementById('trace-search');
    const visibleCount = document.getElementById('trace-visible-count');
    const traceCards = Array.from(document.querySelectorAll('.trace-card'));

    function applyTraceFilters() {{
      const agentValue = agentFilter ? agentFilter.value : 'all';
      const statusValue = statusFilter ? statusFilter.value : 'all';
      const searchValue = traceSearch ? traceSearch.value.trim().toLowerCase() : '';
      let shown = 0;

      traceCards.forEach((card) => {{
        const matchesAgent = agentValue === 'all' || card.dataset.agent === agentValue;
        const matchesStatus = statusValue === 'all' || card.dataset.status === statusValue;
        const matchesSearch = !searchValue || (card.dataset.search || '').includes(searchValue);
        const isVisible = matchesAgent && matchesStatus && matchesSearch;

        card.classList.toggle('is-hidden', !isVisible);
        if (isVisible) {{
          shown += 1;
        }}
      }});

      if (visibleCount) {{
        visibleCount.textContent = String(shown);
      }}
    }}

    if (agentFilter) {{
      agentFilter.addEventListener('change', applyTraceFilters);
    }}
    if (statusFilter) {{
      statusFilter.addEventListener('change', applyTraceFilters);
    }}
    if (traceSearch) {{
      traceSearch.addEventListener('input', applyTraceFilters);
    }}

    applyTraceFilters();
  </script>
</body>
</html>
"""


def render_runs_index_html(manifests: list[dict]) -> str:
    def _kind_icon(k: str) -> str:
        icons = {"pipeline": "&#128230;", "eval": "&#128203;", "render": "&#127912;"}
        return icons.get(k, "&#9881;")

    def _kind_color(k: str) -> str:
        colors = {"pipeline": "#60a5fa", "eval": "#a78bfa", "render": "#34d399"}
        return colors.get(k, "#8896b3")

    def _format_cost(value: object) -> str:
        if value in (None, ""):
            return "-"

        try:
            return f"${float(value):.4f}"
        except (TypeError, ValueError):
            return "-"

    def _format_int(value: object) -> str:
        if value in (None, ""):
            return "-"

        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return "-"

    total_runs = len(manifests)
    total_traces = sum(int(manifest.get("trace_count") or 0) for manifest in manifests)
    total_estimated_cost = sum(
        float(manifest.get("estimated_cost_usd") or 0.0) for manifest in manifests
    )
    max_estimated_cost = max(
        (float(manifest.get("estimated_cost_usd") or 0.0) for manifest in manifests),
        default=0.0,
    )
    pipeline_runs = sum(
        1
        for manifest in manifests
        if str(manifest.get("run_id", "")).startswith("pipeline-")
    )

    cards = []
    for manifest in manifests:
        run_id = manifest["run_id"]
        run_kind = run_id.split("-", 1)[0]
        ticket_count = manifest.get("ticket_count", "?")
        resolved = manifest.get("resolved", "?")
        escalated = manifest.get("escalated", "?")
        trace_count = manifest.get("trace_count", "?")
        llm_total_tokens = manifest.get("llm_total_tokens")
        estimated_cost_usd = manifest.get("estimated_cost_usd")
        cost_entry_count = int(manifest.get("cost_entry_count") or 0)
        started_at = manifest.get("started_at", "unknown")
        finished_at = manifest.get("finished_at", "unknown")
        case_name = manifest.get("case")
        icon = _kind_icon(run_kind)
        color = _kind_color(run_kind)

        duration = ""
        if started_at != "unknown" and finished_at != "unknown":
            try:
                from datetime import datetime, timezone

                start = datetime.fromisoformat(started_at.replace("+00:00", ""))
                end = datetime.fromisoformat(finished_at.replace("+00:00", ""))
                duration_ms = (end - start).total_seconds() * 1000
                if duration_ms < 1000:
                    duration = f"{duration_ms:.0f}ms"
                else:
                    duration = f"{duration_ms / 1000:.1f}s"
            except Exception:
                pass

        run_badges = [
            f'<span class="run-badge"><span class="run-badge-label">LLM tokens</span><span class="run-badge-value">{_format_int(llm_total_tokens)}</span></span>',
            f'<span class="run-badge"><span class="run-badge-label">Est. cost</span><span class="run-badge-value">{_format_cost(estimated_cost_usd)}</span></span>',
        ]
        if cost_entry_count == 0:
            run_badges.append(
                '<span class="run-badge muted"><span class="run-badge-label">Mode</span><span class="run-badge-value">Local fallback</span></span>'
            )

        cards.append(
            f'<article class="run-card" style="--kind-color:{color}">'
            f'<div class="run-header">'
            f'<div class="run-icon">{icon}</div>'
            f'<div class="run-title">'
            f"<h3>{escape(run_id)}</h3>"
            f'<span class="run-kind" style="color:{color}">{run_kind}</span>'
            f"</div></div>"
            f'<div class="run-stats">'
            f'<div class="run-stat"><span class="run-stat-label">Tickets</span><span class="run-stat-value">{ticket_count}</span></div>'
            f'<div class="run-stat"><span class="run-stat-label">Resolved</span><span class="run-stat-value resolved">{resolved}</span></div>'
            f'<div class="run-stat"><span class="run-stat-label">Escalated</span><span class="run-stat-value escalated">{escalated}</span></div>'
            f'<div class="run-stat"><span class="run-stat-label">Traces</span><span class="run-stat-value">{trace_count}</span></div>'
            f"</div>"
            f'<div class="run-meta">'
            f"<span>Started: {escape(str(started_at)[:19])}</span>"
            f"<span>{duration}</span>"
            f"</div>"
            + f'<div class="run-badges">{"".join(run_badges)}</div>'
            + (
                f'<div class="run-case">Case: {escape(case_name)}</div>'
                if case_name
                else ""
            )
            + f'<a href="./{escape(run_id)}/" class="run-link">View Details &#8594;</a>'
            + f"</article>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Run History</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0a0e1a;
      --surface: #111827;
      --surface-raised: #1a2238;
      --muted: #8896b3;
      --text: #e8ecf4;
      --accent: #60a5fa;
      --border: #1e2d4a;
      --good: #34d399;
      --bad: #f87171;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      min-height: 100vh;
    }}
    nav {{
      position: sticky; top: 0; z-index: 50;
      background: rgba(10, 14, 26, 0.85);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--border);
      padding: 0 24px;
    }}
    nav .nav-inner {{
      max-width: 1120px; margin: 0 auto;
      display: flex; align-items: center; justify-content: space-between;
      height: 56px;
    }}
    nav .logo {{
      font-weight: 700; font-size: 1.05rem; color: var(--text);
      display: flex; align-items: center; gap: 10px;
    }}
    nav .logo .logo-dot {{
      width: 9px; height: 9px; border-radius: 50%;
      background: var(--accent); display: inline-block;
    }}
    nav a {{
      color: var(--muted); text-decoration: none; font-size: 0.9rem;
      transition: color 0.15s;
    }}
    nav a:hover {{ color: var(--accent); }}
    nav .nav-links {{ display: flex; gap: 24px; }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 48px 24px 80px;
    }}
    .hero {{
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 32px;
    }}
    .hero h1 {{
      font-size: 2rem; font-weight: 800; letter-spacing: -0.02em;
    }}
    .hero .subtitle {{
      color: var(--muted); font-size: 0.95rem;
    }}
    .hero-stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
      margin-top: 24px;
      margin-bottom: 28px;
    }}
    .hero-stat {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px 16px;
    }}
    .hero-stat-label {{
      display: block; font-size: 0.72rem; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.05em;
    }}
    .hero-stat-value {{
      display: block; font-size: 1.35rem; font-weight: 800; margin-top: 4px;
    }}
    .back-link {{
      color: var(--accent); text-decoration: none; font-size: 0.9rem;
      display: flex; align-items: center; gap: 6px;
    }}
    .back-link:hover {{ text-decoration: underline; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 16px;
    }}
    .run-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 20px;
      transition: border-color 0.2s, transform 0.15s;
    }}
    .run-card:hover {{
      border-color: var(--kind-color);
      transform: translateY(-2px);
    }}
    .run-header {{
      display: flex; align-items: center; gap: 14px; margin-bottom: 16px;
    }}
    .run-icon {{
      width: 40px; height: 40px; border-radius: 10px;
      background: color-mix(in srgb, var(--kind-color) 15%, transparent);
      display: flex; align-items: center; justify-content: center;
      font-size: 1.2rem;
    }}
    .run-title h3 {{
      font-size: 0.9rem; font-weight: 700;
      font-family: ui-monospace, SFMono-Regular, monospace;
      letter-spacing: -0.02em;
    }}
    .run-kind {{
      font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
      font-weight: 600;
    }}
    .run-stats {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      margin-bottom: 14px;
    }}
    .run-stat {{
      text-align: center;
      padding: 8px;
      background: var(--surface-raised);
      border-radius: 8px;
    }}
    .run-stat-label {{
      display: block; font-size: 0.68rem; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.04em;
    }}
    .run-stat-value {{
      display: block; font-size: 1.1rem; font-weight: 700;
    }}
    .run-stat-value.resolved {{ color: var(--good); }}
    .run-stat-value.escalated {{ color: var(--bad); }}
    .run-meta {{
      display: flex; justify-content: space-between;
      font-size: 0.78rem; color: var(--muted);
      margin-bottom: 10px;
    }}
    .run-badges {{
      display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;
    }}
    .run-badge {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 5px 9px; border-radius: 999px;
      background: var(--surface-raised); border: 1px solid var(--border);
      font-size: 0.72rem;
    }}
    .run-badge.muted {{
      color: var(--muted);
    }}
    .run-badge-label {{
      color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em;
      font-size: 0.64rem;
    }}
    .run-badge-value {{
      font-weight: 700;
    }}
    .run-case {{
      font-size: 0.82rem; color: var(--accent);
      padding: 6px 10px; background: var(--accent);
      background: color-mix(in srgb, var(--accent) 15%, transparent);
      border-radius: 6px; display: inline-block; margin-bottom: 12px;
    }}
    .run-link {{
      display: block; text-align: center;
      padding: 10px; background: var(--surface-raised);
      border-radius: 8px; color: var(--text);
      text-decoration: none; font-weight: 600; font-size: 0.9rem;
      transition: background 0.15s;
    }}
    .run-link:hover {{
      background: color-mix(in srgb, var(--accent) 20%, var(--surface-raised));
    }}
    .empty {{ color: var(--muted); text-align: center; padding: 60px 0; }}
  </style>
</head>
<body>
  <nav>
    <div class="nav-inner">
      <div class="logo"><span class="logo-dot"></span>Post-Mortem</div>
      <div class="nav-links">
        <a href="../index.html">Latest Report</a>
      </div>
    </div>
  </nav>

  <main>
    <div class="hero">
      <div>
        <h1>Run History</h1>
        <p class="subtitle">Recent pipeline and eval runs with observability data.</p>
      </div>
      <a href="../index.html" class="back-link">&#8592; Back to Report</a>
    </div>
    <div class="hero-stats">
      <div class="hero-stat"><span class="hero-stat-label">Recent Runs</span><span class="hero-stat-value">{total_runs}</span></div>
      <div class="hero-stat"><span class="hero-stat-label">Pipeline Runs</span><span class="hero-stat-value">{pipeline_runs}</span></div>
      <div class="hero-stat"><span class="hero-stat-label">Trace Events</span><span class="hero-stat-value">{total_traces}</span></div>
      <div class="hero-stat"><span class="hero-stat-label">Total Est. Cost</span><span class="hero-stat-value">{_format_cost(total_estimated_cost)}</span></div>
      <div class="hero-stat"><span class="hero-stat-label">Max Run Cost</span><span class="hero-stat-value">{_format_cost(max_estimated_cost)}</span></div>
    </div>
    <div class="grid">{"".join(cards) if cards else '<div class="empty">No run snapshots available yet.</div>'}</div>
  </main>
</body>
</html>
"""


def publish_run_snapshot(context: dict, manifest: dict) -> None:
    if not os.path.exists(context["viewer_path"]):
        return

    run_id = context["run_id"]
    detail_html = os.path.join(DIST_RUNS_DIR, run_id, "index.html")
    report_snapshot_html = os.path.join(DIST_RUNS_DIR, f"{run_id}-report.html")
    snapshot_json = os.path.join(DIST_RUNS_DIR, f"{run_id}.json")
    traces_snapshot_json = os.path.join(DIST_RUNS_DIR, f"{run_id}.traces.json")

    with open(context["viewer_path"], "r", encoding="utf-8") as file:
        viewer_html = file.read()

    trace_entries = []
    if os.path.exists(context["trace_path"]):
        trace_entries = load_jsonl_file(context["trace_path"])

    trace_summary = summarize_trace_entries(trace_entries)

    manifest = {
        **manifest,
        **trace_summary,
        "artifacts": {
            **(manifest.get("artifacts") or {}),
            "report_snapshot": f"{run_id}-report.html",
            "manifest_snapshot": f"{run_id}.json",
            "traces_snapshot": f"{run_id}.traces.json",
        },
    }

    write_text_file(detail_html, render_run_detail_html(manifest, trace_entries))
    write_text_file(report_snapshot_html, viewer_html)
    write_json_file(snapshot_json, manifest)
    write_json_file(traces_snapshot_json, {"run_id": run_id, "traces": trace_entries})
    write_json_file(DIST_LATEST_RUN_JSON_PATH, manifest)

    manifests = []
    if os.path.isdir(DIST_RUNS_DIR):
        for name in sorted(os.listdir(DIST_RUNS_DIR), reverse=True):
            if not name.endswith(".json") or name.endswith(".traces.json"):
                continue
            try:
                manifests.append(load_json_file(os.path.join(DIST_RUNS_DIR, name)))
            except Exception:
                continue

    manifests.sort(key=lambda item: item.get("finished_at", ""), reverse=True)
    write_text_file(DIST_RUNS_INDEX_PATH, render_runs_index_html(manifests[:10]))


def load_eval_expectations(target_dir: str) -> dict:
    expectations_path = os.path.join(target_dir, EVAL_EXPECTATIONS_PATH)
    if not os.path.exists(expectations_path):
        return {}

    return load_json_file(expectations_path)


def validate_eval_result(case_name: str, result: dict, expectations: dict) -> list[str]:
    expected = expectations.get(case_name)
    if expected is None:
        return []

    errors = []

    if result.get("ticket_count") != expected.get("ticket_count"):
        errors.append(
            f"ticket_count expected {expected.get('ticket_count')} got {result.get('ticket_count')}"
        )

    if result.get("resolved") != expected.get("resolved"):
        errors.append(
            f"resolved expected {expected.get('resolved')} got {result.get('resolved')}"
        )

    if result.get("escalated") != expected.get("escalated"):
        errors.append(
            f"escalated expected {expected.get('escalated')} got {result.get('escalated')}"
        )

    actual_top_issues = result.get("top_issues", [])
    for issue in expected.get("top_issues_includes", []):
        if issue not in actual_top_issues:
            errors.append(f"missing expected top issue: {issue}")

    return errors


def write_report_artifacts(
    context: dict | None,
    summary: dict,
    recommendations: list[dict],
    report: str,
    out_dir: str | None = None,
) -> None:
    html = render_report_html(summary, recommendations)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "recommendations": recommendations,
        "report_markdown": report,
    }

    if context:
        write_text_file(context["report_path"], report + "\n")
        write_json_file(context["report_json_path"], payload)
        write_text_file(context["viewer_path"], html)

    if out_dir is None:
        return

    write_text_file(os.path.join(out_dir, "report.md"), report + "\n")
    write_json_file(os.path.join(out_dir, "report.json"), payload)
    write_text_file(os.path.join(out_dir, "index.html"), html)
    write_text_file(os.path.join(out_dir, "latest-run.html"), html)


def process_ticket_with_context(
    context: dict,
    provider: dict | None,
    ticket: dict,
) -> dict:
    parent_step = f"ticket:{ticket['id']}"
    record_run_step(
        context,
        step=parent_step,
        agent="manager",
        parent_step=None,
        metadata={"ticket_id": ticket["id"], "action": "plan"},
        status="ok",
    )

    print(f"[triage] {ticket['id']} {ticket['subject']}")

    triage = determine_local_triage(ticket)
    if triage["category"] == "other":
        if provider:
            try:
                triage_system_prompt, triage_user_prompt = build_triage_prompts(ticket)
                triage_response = traced_llm_call(
                    provider,
                    context=context,
                    step=f"{parent_step}:triage",
                    agent="triager",
                    parent_step=parent_step,
                    system_prompt=triage_system_prompt,
                    user_prompt=triage_user_prompt,
                    metadata={"ticket_id": ticket["id"]},
                )
                triage = parse_json_response(triage_response)
                triage = normalize_triage(ticket, triage)
            except Exception as error:
                record_run_step(
                    context,
                    step=f"{parent_step}:triage",
                    agent="triager",
                    parent_step=parent_step,
                    metadata={
                        "ticket_id": ticket["id"],
                        "fallback": True,
                        "reason": str(error),
                    },
                    status="fallback",
                )
                triage = determine_local_triage(ticket)
                triage["reason"] = (
                    f"LLM unavailable; using deterministic fallback. Original: {error}"
                )
        else:
            record_run_step(
                context,
                step=f"{parent_step}:triage",
                agent="triager",
                parent_step=parent_step,
                metadata={"ticket_id": ticket["id"], "mode": "local"},
                status="ok",
            )

    record_run_step(
        context,
        step=f"{parent_step}:route",
        agent="manager",
        parent_step=parent_step,
        metadata={
            "ticket_id": ticket["id"],
            "category": triage["category"],
            "resolvable": triage["resolvable"],
        },
        status="ok",
    )

    enriched_ticket = dict(ticket)
    enriched_ticket["triage"] = triage

    if triage["resolvable"] and triage["category"] in KNOWLEDGE_BASE:
        print(f"[resolve] {ticket['id']} {triage['category']}")
        resolution = draft_local_resolution(ticket, triage)

        if provider and triage["category"] not in (
            "password_reset",
            "feature_request",
            "invoice_copy",
        ):
            try:
                resolution_system_prompt, resolution_user_prompt = (
                    build_resolution_prompts(ticket, triage)
                )
                resolution_response = traced_llm_call(
                    provider,
                    context=context,
                    step=f"{parent_step}:resolve",
                    agent="resolver",
                    parent_step=parent_step,
                    system_prompt=resolution_system_prompt,
                    user_prompt=resolution_user_prompt,
                    metadata={
                        "ticket_id": ticket["id"],
                        "category": triage["category"],
                    },
                )
                resolution = parse_json_response(resolution_response)
            except Exception:
                pass

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

    record_run_step(
        context,
        step=f"{parent_step}:finalize",
        agent="manager",
        parent_step=parent_step,
        metadata={
            "ticket_id": ticket["id"],
            "result": enriched_ticket["result"]["status"],
        },
        status="ok",
    )

    return enriched_ticket


def build_report_with_context(
    context: dict,
    provider: dict | None,
    processed_tickets: list[dict],
) -> tuple[dict, list[dict], str]:
    summary = summarize_pipeline_output(processed_tickets)
    recommendations_system_prompt, recommendations_user_prompt = (
        build_recommendations_prompt(summary, processed_tickets)
    )

    recommendations = None
    if provider:
        try:
            recommendations_response = traced_llm_call(
                provider,
                context=context,
                step="recommendations",
                agent="analyst",
                parent_step=None,
                system_prompt=recommendations_system_prompt,
                user_prompt=recommendations_user_prompt,
                metadata={"ticket_count": len(processed_tickets)},
            )
            recommendations = parse_json_response(recommendations_response)[
                "recommendations"
            ]
        except Exception as error:
            record_run_step(
                context,
                step="recommendations",
                agent="analyst",
                parent_step=None,
                metadata={"fallback": True, "reason": str(error)},
                status="fallback",
            )

    if recommendations is None:
        recommendations = draft_local_recommendations(summary)
        record_run_step(
            context,
            step="recommendations:local",
            agent="analyst",
            parent_step=None,
            metadata={"mode": "local"},
            status="ok",
        )

    report = render_postmortem(summary, recommendations)
    return summary, recommendations, report


def _parse_cli(argv: list[str]) -> dict:
    args = {"tickets": TICKETS_PATH, "out": None, "eval": False, "render_site": False}
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg in ("--tickets", "-t"):
            i += 1
            if i < len(argv):
                args["tickets"] = argv[i]
        elif arg in ("--out", "-o"):
            i += 1
            if i < len(argv):
                args["out"] = argv[i]
        elif arg == "--eval":
            args["eval"] = True
        elif arg == "--render-site":
            args["render_site"] = True
        i += 1
    return args


def _eval_run(
    provider: dict | None,
    tickets_path: str,
    out_dir: str | None = None,
    case_name: str | None = None,
) -> dict:
    tickets = load_tickets(tickets_path)
    context = create_run_context("eval")
    run_dir = context["run_dir"]
    print(f"[manager] run_id={context['run_id']}")

    processed_tickets: list[dict] = []
    for ticket in tickets:
        processed_tickets.append(process_ticket_with_context(context, provider, ticket))

    write_pipeline_output(processed_tickets, context["pipeline_output_path"])
    summary, recommendations, report = build_report_with_context(
        context, provider, processed_tickets
    )
    write_report_artifacts(context, summary, recommendations, report, run_dir)

    result = {
        "run_id": context["run_id"],
        "started_at": context["started_at"],
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "ticket_count": len(processed_tickets),
        "resolved": sum(
            1 for t in processed_tickets if t["result"]["status"] == "resolved"
        ),
        "escalated": sum(
            1 for t in processed_tickets if t["result"]["status"] == "escalated"
        ),
        "top_issues": [i["label"] for i in summary.get("top_recurring_issues", [])[:3]],
        "ok": True,
        **({"case": case_name} if case_name else {}),
    }
    write_json_file(context["manifest_path"], result)
    write_json_file(os.path.join(RUNS_DIR, "latest.json"), result)
    publish_run_snapshot(context, result)

    if out_dir:
        write_pipeline_output(
            processed_tickets, os.path.join(out_dir, "pipeline_output.json")
        )
        write_report_artifacts(context, summary, recommendations, report, out_dir)

    return result


def _eval_target(
    provider: dict | None,
    tickets_target: str,
    out_dir: str | None = None,
) -> dict:
    if os.path.isdir(tickets_target):
        expectations = load_eval_expectations(tickets_target)
        cases = []
        for name in sorted(os.listdir(tickets_target)):
            if not name.endswith(".json") or name == EVAL_EXPECTATIONS_PATH:
                continue

            case_path = os.path.join(tickets_target, name)
            case_out_dir = (
                os.path.join(out_dir, os.path.splitext(name)[0]) if out_dir else None
            )
            case_result = _eval_run(provider, case_path, case_out_dir, case_name=name)
            assertion_errors = validate_eval_result(name, case_result, expectations)
            case_result["assertion_errors"] = assertion_errors
            case_result["ok"] = case_result["ok"] and not assertion_errors
            cases.append(case_result)

        return {
            "suite": tickets_target,
            "case_count": len(cases),
            "ok": all(case["ok"] for case in cases),
            "cases": cases,
        }

    return _eval_run(provider, tickets_target, out_dir)


def main() -> int:
    args = _parse_cli(sys.argv)
    try:
        load_local_env()
    except Exception:
        pass

    try:
        provider = get_provider()
    except RuntimeError:
        provider = None

    if args["render_site"]:
        try:
            processed_tickets = load_tickets(PIPELINE_OUTPUT_PATH)
        except Exception as error:
            print(f"Failed to load pipeline output: {error}", file=sys.stderr)
            return 1

        context = create_run_context("render")
        summary, recommendations, report = build_report_with_context(
            context, provider, processed_tickets
        )
        write_report_artifacts(
            context,
            summary,
            recommendations,
            report,
            context["run_dir"],
        )
        write_report_artifacts(
            context,
            summary,
            recommendations,
            report,
            args["out"] or DIST_DIR,
        )
        manifest = {
            "run_id": context["run_id"],
            "started_at": context["started_at"],
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "ticket_count": len(processed_tickets),
            "artifacts": {
                "report_md": context["report_path"],
                "report_json": context["report_json_path"],
                "viewer": context["viewer_path"],
            },
        }
        write_json_file(context["manifest_path"], manifest)
        write_json_file(os.path.join(RUNS_DIR, "latest.json"), manifest)
        publish_run_snapshot(context, manifest)
        print(report)
        return 0

    if args["eval"]:
        result = _eval_target(provider, args["tickets"], args["out"])
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    context = create_run_context("pipeline")
    print(f"[manager] Starting pipeline; run_id={context['run_id']}")
    tickets = load_tickets(args["tickets"])
    print(f"[manager] Loaded {len(tickets)} tickets")

    processed_tickets: list[dict] = []
    for ticket in tickets:
        processed_tickets.append(process_ticket_with_context(context, provider, ticket))

    write_pipeline_output(processed_tickets, context["pipeline_output_path"])
    write_pipeline_output(processed_tickets, PIPELINE_OUTPUT_PATH)

    print("[manager] Generating report")
    summary, recommendations, report = build_report_with_context(
        context, provider, processed_tickets
    )
    write_report_artifacts(
        context, summary, recommendations, report, context["run_dir"]
    )
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
    write_report_artifacts(context, summary, recommendations, report, DIST_DIR)
    if args["out"]:
        write_report_artifacts(context, summary, recommendations, report, args["out"])

    manifest = {
        "run_id": context["run_id"],
        "started_at": context["started_at"],
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "ticket_count": len(processed_tickets),
        "resolved": sum(
            1 for t in processed_tickets if t["result"]["status"] == "resolved"
        ),
        "escalated": sum(
            1 for t in processed_tickets if t["result"]["status"] == "escalated"
        ),
        "artifacts": {
            "pipeline_output": context["pipeline_output_path"],
            "report_md": context["report_path"],
            "report_json": context["report_json_path"],
            "viewer": context["viewer_path"],
        },
    }
    write_json_file(context["manifest_path"], manifest)
    write_json_file(os.path.join(RUNS_DIR, "latest.json"), manifest)
    publish_run_snapshot(context, manifest)

    print()
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
