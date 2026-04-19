# Repo Guide

## What This Repo Is
- Single-file Python prototype for the `SCOPE.md` demo: `python3 main.py` runs the full support pipeline and prints the markdown post-mortem.
- The product is the terminal report. Triage/resolve/escalate exists only to feed that report.

## Source Of Truth
- `SCOPE.md` is the product boundary and scope filter. Check it before adding features.
- `main.py` is the whole app: env loading, Zen calls, prompts, tracing, pipeline orchestration, and final report generation.
- `tickets.json` is the only input dataset. Keep its seeded recurring themes intact unless the task is explicitly about changing the demo story.

## Setup And Run
- Install deps with `python3 -m pip install -r requirements.txt`.
- Required env is local `.env`; `main.py` loads it manually with no dotenv dependency.
- Minimum `.env` keys are `OPENCODE_ZEN_API_KEY` and optionally `OPENCODE_ZEN_MODEL`.
- Main entrypoint is `python3 main.py` in this environment. Do not assume `python` exists.

## Verification
- Fast non-billed check: `python3 -m py_compile main.py`.
- Real end-to-end check: `python3 main.py`.
- Running the full pipeline makes many live Zen API calls and appends to `traces.jsonl`; use it intentionally.

## Runtime Behavior
- Provider is Zen-only right now. `main.py` posts to `https://opencode.ai/zen/v1/chat/completions`.
- Default model is `qwen3.6-plus` unless overridden by `OPENCODE_ZEN_MODEL`.
- Every LLM call appends a JSON line to `traces.jsonl`.
- Successful pipeline runs also overwrite `pipeline_output.json` with enriched ticket records.
- Prompts for triage and resolution expect JSON-only model output; if you change prompts, preserve strict parseability.

## Editing Constraints
- Keep changes small and centered in `main.py`; the repo does not have package structure yet.
- Do not add extra infrastructure, frameworks, or a database unless the task explicitly requires moving beyond the current scope.
- `.env`, `traces.jsonl`, and Python cache files are intentionally git-ignored.

## Missing Repo Infrastructure
- There is no test suite, linter, formatter config, CI workflow, README, or task runner in this repo today. Do not invent commands; use the direct Python commands above.
