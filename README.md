# github_repo_report

Sync configured GitHub repositories into cumulative JSON snapshots, then generate **weekly**, **monthly**, and **project** reports via an OpenRouter-compatible API.

## Setup

Use your **system Python 3** (no project virtualenv required):

```bash
pip install --user -r requirements.txt   # once: jsonschema
python3 main.py sync
```

Edit [`config.json`](config.json) (paths, `github_repos`, AI model). API keys (not committed):

- `api_keys/openrouter.txt` — OpenRouter for report generation (**required for remote endpoints**)
- `api_keys/github.txt` — optional; improves rate limits / private repos
- Local Ollama endpoints (`http://localhost:11434/...`) can run **without** API keys.
  - You can set `url` either to the host (`http://localhost:11434`) or directly to `http://localhost:11434/api/chat`.
 
Security policy: AI and GitHub keys are read from configured key files only (no environment-variable fallback).

## Usage

```bash
python3 main.py          # default: reports
python3 main.py sync      # Phase 1: fetch & merge GitHub data → github_current_state/
python3 main.py reports   # Phase 2–4 in order: weekly → monthly → project (if new final monthly)
python3 main.py all       # sync + reports (recommended full run)
python3 main.py weekly    # only missing weekly reports
python3 main.py monthly   # only missing monthly reports (needs weeklies)
python3 main.py project   # project doc (needs at least one final monthly per repo)
```

**`reports` / `all` order:** (1) all missing **weekly** reports, (2) **monthly** reports where weeklies exist, (3) **project** report only for repos where a **final** monthly (`YYYY-MM.md`, not `_current`) was **created in that run**.

At runtime, the app logs one readable line with the active AI model and endpoint URL.

Exit code `0` only if all repos in the command succeed.

## Output layout

Roots come from `config.json` → `paths.weekly_report`, `paths.monthly_report`, `paths.project_report` (e.g. `reports/weekly_report/`). Each repo gets a **subfolder named after the repo only** (`de_nbi`, `BITS`):

| Config path | Example file |
|-------------|----------------|
| `paths.weekly_report` + `{repo}/` | `2026-05-week_20.md` or `2026-05-week_20_current.md` |
| `paths.monthly_report` + `{repo}/` | `2026-05.md` or `2026-05_current.md` |
| `paths.project_report` + `{repo}/` | `de_nbi.md` or `de_nbi_current.md` |
| `paths.github_current_state` | `{owner}_{repo}_{hash}_state.json` (unchanged) |

- **Weekly `YYYY-MM`:** month with the most commits in that ISO week (tie: earliest commit in the week).
- **Final** reports: written when the ISO week / calendar month is complete; not overwritten.
- **`_current`:** in-progress period; one draft per period; old drafts removed before rewrite and when the final file exists.
- **AI endpoint errors:** report generation for that repo is aborted with a warning; files created in that failed run are rolled back (no partial new reports left behind for that repo).

**Note:** Older runs used names like `week_2026-W09.md` under `owner_repo` folders. Re-run `python3 main.py weekly` (and monthly/project) to produce files with the new layout, or delete orphaned old reports manually.

## Configuration highlights

| Key | Purpose |
|-----|---------|
| `paths.github_current_state` | Snapshot directory (fallback: `./github_current_state/`) |
| `paths.num_ctx` (per model) | Context window size (`num_ctx`); used client-side for prompt sizing on OpenRouter |
| `prompts_and_templates` | Prompt files; Markdown is rendered from validated JSON in code |

See [`project_plan.md`](project_plan.md) for architecture and JSON schemas.

## License

See [`LICENSE`](LICENSE).
