"""Weekly report JSON schema, validation, and Markdown rendering."""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator

WEEKLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "summary",
        "commits",
        "github_activity",
        "technical_work",
        "challenges",
        "open_issues",
        "notes",
    ],
    "properties": {
        "summary": {"type": "string", "minLength": 1},
        "commits": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["date", "author", "message"],
                "properties": {
                    "date": {"type": "string"},
                    "author": {"type": "string"},
                    "message": {"type": "string"},
                },
            },
        },
        "github_activity": {
            "type": "object",
            "required": ["issues", "branches"],
            "properties": {
                "issues": {
                    "type": "object",
                    "required": ["new", "open", "closed", "notes"],
                    "properties": {
                        "new": {"type": "integer", "minimum": 0},
                        "open": {"type": "integer", "minimum": 0},
                        "closed": {"type": "integer", "minimum": 0},
                        "notes": {"type": "string"},
                    },
                },
                "branches": {
                    "type": "object",
                    "required": ["new", "open", "closed", "notes"],
                    "properties": {
                        "new": {"type": "integer", "minimum": 0},
                        "open": {"type": "integer", "minimum": 0},
                        "closed": {"type": "integer", "minimum": 0},
                        "notes": {"type": "string"},
                    },
                },
            },
        },
        "technical_work": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["topic", "body"],
                "properties": {"topic": {"type": "string"}, "body": {"type": "string"}},
            },
        },
        "challenges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "description", "context", "solution"],
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "context": {"type": "string"},
                    "solution": {"type": "string"},
                },
            },
        },
        "open_issues": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "additionalProperties": False,
}

_validator = Draft202012Validator(WEEKLY_SCHEMA)


def validate_weekly(data: dict[str, Any], *, had_commits: bool) -> list[str]:
    errors = sorted(f"{e.message} @ {list(e.path)}" for e in _validator.iter_errors(data))
    summary = data.get("summary")
    if had_commits:
        if not isinstance(summary, str):
            errors.append("summary must be a string when commits exist")
        elif not summary.strip():
            errors.append("summary must not be empty when commits exist")
    return errors


def render_weekly_markdown(
    data: dict[str, Any],
    *,
    repo_display: str,
    iso_week: str,
    year: int,
    week_start: str,
    week_end: str,
) -> str:
    ga = data["github_activity"]
    lines = [
        f"# Weekly Report — {repo_display} — Week {iso_week}, {year} "
        f"({week_start} to {week_end})",
        "",
        "## Summary",
        data["summary"].strip(),
        "",
        "## Commits",
        "| Date (UTC) | Author | Message |",
        "|------------|--------|---------|",
    ]
    for row in data["commits"]:
        msg = row["message"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['date'][:10]} | {row['author']} | {msg} |")
    lines.extend(
        [
            "",
            "## GitHub Activity",
            "",
            "### Issues",
            "| Category | Count | Notes |",
            "|----------|------:|-------|",
            f"| New (created this week) | {ga['issues']['new']} | {ga['issues']['notes']} |",
            f"| Open (still open at week end) | {ga['issues']['open']} | |",
            f"| Closed (closed this week) | {ga['issues']['closed']} | |",
            "",
            "### Branches",
            "| Category | Count | Notes |",
            "|----------|------:|-------|",
            f"| New (first seen this week) | {ga['branches']['new']} | {ga['branches']['notes']} |",
            f"| Open (active at week end) | {ga['branches']['open']} | |",
            f"| Closed (merged/deleted this week) | {ga['branches']['closed']} | |",
            "",
            "## Technical Work",
        ]
    )
    for tw in data["technical_work"]:
        lines.extend([f"### {tw['topic']}", tw["body"].strip(), ""])
    if not data["technical_work"]:
        lines.append("_No technical work sections._\n")
    lines.append("## Challenges & Problems")
    for ch in data["challenges"]:
        lines.extend(
            [
                f"### {ch['title']}",
                f"**Description:** {ch['description']}",
                f"**Context:** {ch['context']}",
                f"**Solution:** {ch['solution']}",
                "",
            ]
        )
    if not data["challenges"]:
        lines.append("_None identified._\n")
    lines.append("## Open Issues")
    for item in data["open_issues"]:
        lines.append(f"- {item}")
    if not data["open_issues"]:
        lines.append("- None")
    lines.extend(["", "## Notes", data["notes"].strip(), ""])
    return "\n".join(lines)


def schema_description() -> str:
    return json.dumps(WEEKLY_SCHEMA, indent=2)
