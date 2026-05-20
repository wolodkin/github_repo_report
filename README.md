# github_repo_report

Tooling to pull structured data from configured GitHub repositories and generate **weekly**, **monthly**, and **project** reports using an AI API (for example OpenRouter). Paths, repo list, model settings, and prompt/template pairs are driven by **`config.json`**.

## Status

- **Design:** See [`project_plan.md`](project_plan.md) for the phased plan (Phase 1: GitHub REST API snapshots per repo under `paths.github_current_state`; later: analytics and AI reports using `prompts_and_templates`).
- **Implementation:** [`main.py`](main.py) is a placeholder; wiring of the handler, snapshot writes, and report generation is still to be done.

## Features (target)

- Maintain a list of GitHub repos in configuration; refresh **JSON snapshots** per repo (commits, branches, issues, optional project remark file via Contents API).
- Use **prompts** and **templates** from [`prompts/`](prompts/) and [`templates/`](templates/) to drive AI-generated reports.
- Optional **AI debug** storage of raw model responses (see `ai:config` → `ai_debug` in `config.json`).

## Configuration

Edit **`config.json`** at the project root:

| Area | Purpose |
|------|--------|
| `github_repos` | Repository URLs (`https://github.com/...` or `git@github.com:...`). |
| `paths.github_current_state` | Directory for per-repo JSON snapshots. |
| `paths.project_remark_and_log_file_name` | File name (e.g. `project_remark.txt`) fetched per repo for the snapshot. |
| `paths.weekly_report` / `monthly_report` / `project_report` | Output locations for generated reports. |
| `ai:config` | Active model, URL, **`num_ctx`** (context window size, Ollama-native), temperature, timeout. No `max_tokens` / `response_format`. OpenRouter: use `num_ctx` client-side for prompt sizing only. |
| `prompts_and_templates` | Maps each report type to a prompt file and a template file. |

API keys are **not** committed: point `api_key_file` (under each model in `ai_model_config`) to a local file (e.g. `api_keys/openrouter.txt`).

## Repository layout

```
config.json          # Paths, repos, AI and prompt/template mapping
main.py              # Entry point (to be implemented)
project_plan.md      # Architecture and Phase 1 data-flow notes
prompts/             # LLM instructions per report type
templates/           # Structure / placeholders for rendered reports
```

## Requirements

- **Planned baseline (API-only):** Python 3, HTTPS access to GitHub; a **token** for private repos or higher rate limits (see `project_plan.md`).
- **Reports:** Depends on chosen stack (e.g. HTTP client for OpenAI-compatible chat completions).

## License

See [`LICENSE`](LICENSE).
