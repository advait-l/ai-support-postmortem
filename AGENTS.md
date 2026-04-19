# Repo Guide

## What This Repo Is
- Single-file Python app (`main.py`) that processes support tickets through an AI triage/resolve/escalate pipeline and produces a weekly post-mortem report.
- The **report** is the product. The pipeline exists only to feed it.
- `SCOPE.md` is the product boundary. Check it before adding features.

## Source Layout
- `main.py` — entire app: env loading, Zen LLM calls, deterministic fallbacks, prompts, tracing, pipeline orchestration, report rendering, eval runner, and static site generation.
- `tickets.json` — 20 seeded input tickets with deliberate recurring themes. Do not shuffle or flatten the themes unless the task explicitly requires it.
- `evals/` — named eval ticket sets (`core_recurring.json`, `escalation_heavy.json`, `frontline_resolvable.json`) plus `expectations.json` with pass/fail assertions.
- `dist/` — generated static site deployed to Vercel. `dist/index.html` is the main report; `dist/runs/` holds per-run snapshots.
- `runs/` — gitignored per-run artifact directories created at runtime. Each contains `traces.jsonl`, `pipeline_output.json`, `report.md`, `report.json`, `run.json`, and `latest-run.html`.

## Setup
- `python3 -m pip install -r requirements.txt` (only dependency is `requests`).
- Copy `.env.example` to `.env` and set `OPENCODE_ZEN_API_KEY`. Optionally set `OPENCODE_ZEN_MODEL` (default: `glm-5`).
- `.env` is loaded manually in `main.py` with no dotenv dependency.
- Always use `python3`, not `python`.

## Commands

| Command | What it does | Cost |
|---|---|---|
| `python3 -m py_compile main.py` | Syntax check, no API calls | Free |
| `python3 main.py` | Full pipeline: triage + resolve + report. Writes to `runs/`, `dist/`, and root artifacts | LLM calls if provider available; falls back to deterministic otherwise |
| `python3 main.py --eval --tickets evals` | Run all eval cases with assertion checks | Same fallback behavior |
| `python3 main.py --eval --tickets evals/core_recurring.json` | Run a single eval case | Same |
| `python3 main.py --render-site` | Re-render report from existing `pipeline_output.json` without reprocessing tickets | Minimal or no LLM calls |
| `OPENCODE_ZEN_API_KEY='' python3 main.py` | Force provider-free run using only deterministic triage/resolution | Free, fast |

### CLI flags
- `--tickets <path>` or `-t <path>` — override input tickets (file or directory for eval mode).
- `--out <dir>` or `-o <dir>` — override output directory.
- `--eval` — run in eval mode with assertion checking.
- `--render-site` — re-render from existing pipeline output.

## Architecture

### Agent Roles (all in main.py, no framework)
- **Manager** — orchestrates per-ticket flow: plans, delegates to triager/resolver, reviews routing decisions, finalizes. Visible in traces as `agent: "manager"`.
- **Triager** — classifies tickets. Uses deterministic rules first (`determine_local_triage`); falls back to LLM only for `"other"` category.
- **Resolver** — drafts customer responses. Uses local KB templates for common categories; LLM for less common resolvable ones.
- **Analyst** — generates recommendations from pipeline summary. Falls back to `draft_local_recommendations` if LLM unavailable.

### Fallback Behavior
The pipeline completes end-to-end even without a working LLM provider. Deterministic triage covers all 10 known categories. Local KB templates cover all resolvable categories. Local recommendations cover all summary shapes. This is intentional for demo reliability and eval speed.

### Tracing
- Every step records to both `traces.jsonl` (global) and `runs/<run_id>/traces.jsonl` (per-run).
- Trace entries include: `run_id`, `agent`, `step`, `parent_step`, `status`, `latency_ms`, `model`, `provider`, `prompt_tokens_estimate`.
- LLM calls go through `traced_llm_call` which handles retries with backoff on 429s and timeouts.

### Eval System
- `evals/expectations.json` maps each eval case file to expected `ticket_count`, `resolved`, `escalated`, and `top_issues_includes`.
- `_eval_target` loads expectations, runs each case, and calls `validate_eval_result` to produce `assertion_errors`.
- Exit code is non-zero if any assertion fails.

## Deployment
- Static site lives in `dist/`. Vercel project is configured to serve from this directory.
- `vercel.json` has `cleanUrls: true` and `trailingSlash: false`. No build command — Vercel serves pre-built static files.
- `netlify.toml` also configured with `publish = "dist"` as a backup.
- To update the deployed site: regenerate `dist/` locally, commit, push to `master`.

## Editing Constraints
- Keep changes in `main.py`. The repo has no package structure.
- Do not add frameworks, databases, or extra infrastructure unless the task explicitly requires it.
- `tickets.json` recurring themes are deliberately seeded for the demo story. Do not flatten them.
- Prompts for triage and resolution expect JSON-only model output. If you change prompts, preserve strict parseability.
- `.env`, `traces.jsonl`, `runs/`, and Python cache files are gitignored.

## Gotchas
- The Zen API rate-limits aggressively. A full 20-ticket run with LLM can take 1-10 minutes depending on backoff. Use `python3 -m py_compile` for fast syntax checks and provider-free runs for functional checks.
- `write_report_artifacts` writes to both the run directory and a target output directory. Passing `out_dir=None` skips the output directory write — only the run-scoped copy is created.
- `build_report_with_context` returns a tuple `(summary, recommendations, report)`, not just the report string.
- The default model is `glm-5`, not `qwen3.6-plus` (changed since earlier iterations).

## Missing Infrastructure
- No test suite, linter config, formatter config, CI workflow, or task runner. Use the direct commands above.
