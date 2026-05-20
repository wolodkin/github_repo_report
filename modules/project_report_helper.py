"""Project report JSON schema, validation, and Markdown rendering."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

PROJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "abstract",
        "introduction",
        "project_timeline",
        "technical_architecture",
        "development_activity_summary",
        "challenges_log",
        "results_and_outcomes",
        "discussion",
        "conclusion",
        "appendix",
    ],
    "properties": {
        "abstract": {"type": "string", "minLength": 1},
        "introduction": {"type": "string"},
        "project_timeline": {"type": "string"},
        "technical_architecture": {"type": "string"},
        "development_activity_summary": {
            "type": "object",
            "required": [
                "commits_total",
                "issues_open",
                "issues_closed",
                "branches_open",
                "branches_closed",
            ],
            "properties": {
                "commits_total": {"type": "integer", "minimum": 0},
                "issues_open": {"type": "integer", "minimum": 0},
                "issues_closed": {"type": "integer", "minimum": 0},
                "branches_open": {"type": "integer", "minimum": 0},
                "branches_closed": {"type": "integer", "minimum": 0},
            },
        },
        "challenges_log": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "title",
                    "first_observed",
                    "status",
                    "description",
                    "resolution",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "first_observed": {"type": "string"},
                    "status": {"type": "string"},
                    "description": {"type": "string"},
                    "resolution": {"type": "string"},
                },
            },
        },
        "results_and_outcomes": {"type": "string"},
        "discussion": {"type": "string"},
        "conclusion": {"type": "string"},
        "appendix": {"type": "string"},
    },
    "additionalProperties": False,
}

_validator = Draft202012Validator(PROJECT_SCHEMA)


def validate_project(data: dict[str, Any], cache_summary: dict[str, int] | None) -> list[str]:
    errors = sorted(f"{e.message} @ {list(e.path)}" for e in _validator.iter_errors(data))
    if cache_summary:
        das = data.get("development_activity_summary") or {}
        for key in (
            "commits_total",
            "issues_open",
            "issues_closed",
            "branches_open",
            "branches_closed",
        ):
            if key in cache_summary and das.get(key) != cache_summary[key]:
                errors.append(
                    f"development_activity_summary.{key} ({das.get(key)}) "
                    f"!= cache ({cache_summary[key]})"
                )
    return errors


def render_project_markdown(
    data: dict[str, Any],
    *,
    repo_display: str,
    repo_url: str,
    generated_at: str,
) -> str:
    das = data["development_activity_summary"]
    lines = [
        f"# Project Documentation — {repo_display}",
        "",
        f"**Repository:** {repo_url}  ",
        f"**Last updated:** {generated_at} (UTC)",
        "",
        "## Abstract",
        data["abstract"].strip(),
        "",
        "## Introduction",
        data["introduction"].strip(),
        "",
        "## Project Timeline",
        data["project_timeline"].strip(),
        "",
        "## Technical Architecture",
        data["technical_architecture"].strip(),
        "",
        "## Development Activity Summary",
        "| Area | Summary |",
        "|------|---------|",
        f"| Commits (total in cache) | {das['commits_total']} |",
        f"| Issues (open / closed) | {das['issues_open']} / {das['issues_closed']} |",
        f"| Branches (open / closed) | {das['branches_open']} / {das['branches_closed']} |",
        "",
        "## Challenges & Problem-Solving Log",
    ]
    for ch in data["challenges_log"]:
        lines.extend(
            [
                f"### {ch['title']}",
                f"**First observed:** {ch['first_observed']}  ",
                f"**Status:** {ch['status']}  ",
                f"**Description:** {ch['description']}",
                f"**Resolution:** {ch['resolution']}",
                "",
            ]
        )
    if not data["challenges_log"]:
        lines.append("_No challenges logged._\n")
    lines.extend(
        [
            "## Results & Outcomes",
            data["results_and_outcomes"].strip(),
            "",
            "## Discussion",
            data["discussion"].strip(),
            "",
            "## Conclusion",
            data["conclusion"].strip(),
            "",
            "## Appendix",
            data["appendix"].strip(),
            "",
        ]
    )
    return "\n".join(lines)
