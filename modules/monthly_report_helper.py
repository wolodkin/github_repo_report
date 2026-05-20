"""Monthly report JSON schema, validation, and Markdown rendering."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

MONTHLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "overview",
        "weekly_breakdown",
        "cumulative_technical_progress",
        "github_trends",
        "recurring_challenges",
        "solutions_and_resolutions",
        "unresolved_carried_forward",
        "metrics",
    ],
    "properties": {
        "overview": {"type": "string", "minLength": 1},
        "weekly_breakdown": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["iso_week", "theme", "summary"],
                "properties": {
                    "iso_week": {"type": "string"},
                    "theme": {"type": "string"},
                    "summary": {"type": "string"},
                },
            },
        },
        "cumulative_technical_progress": {"type": "string"},
        "github_trends": {
            "type": "object",
            "required": ["issues", "branches"],
            "properties": {
                "issues": {
                    "type": "object",
                    "required": ["new", "closed", "open_at_month_end"],
                    "properties": {
                        "new": {"type": "integer", "minimum": 0},
                        "closed": {"type": "integer", "minimum": 0},
                        "open_at_month_end": {"type": "integer", "minimum": 0},
                    },
                },
                "branches": {
                    "type": "object",
                    "required": ["new", "closed", "open_at_month_end"],
                    "properties": {
                        "new": {"type": "integer", "minimum": 0},
                        "closed": {"type": "integer", "minimum": 0},
                        "open_at_month_end": {"type": "integer", "minimum": 0},
                    },
                },
            },
        },
        "recurring_challenges": {"type": "array", "items": {"type": "string"}},
        "solutions_and_resolutions": {"type": "string"},
        "unresolved_carried_forward": {"type": "string"},
        "metrics": {
            "type": "object",
            "required": ["commits", "weekly_reports_used"],
            "properties": {
                "commits": {"type": "integer", "minimum": 0},
                "weekly_reports_used": {"type": "integer", "minimum": 0},
            },
        },
    },
    "additionalProperties": False,
}

_validator = Draft202012Validator(MONTHLY_SCHEMA)


def validate_monthly(data: dict[str, Any]) -> list[str]:
    return sorted(f"{e.message} @ {list(e.path)}" for e in _validator.iter_errors(data))


def render_monthly_markdown(
    data: dict[str, Any],
    *,
    repo_display: str,
    month_name: str,
    year: int,
) -> str:
    gt = data["github_trends"]
    lines = [
        f"# Monthly Report — {repo_display} — {month_name} {year}",
        "",
        "## Overview",
        data["overview"].strip(),
        "",
        "## Weekly Breakdown",
    ]
    for wb in data["weekly_breakdown"]:
        lines.extend(
            [
                f"### Week {wb['iso_week']} — {wb['theme']}",
                wb["summary"].strip(),
                "",
            ]
        )
    if not data["weekly_breakdown"]:
        lines.append("_No weekly reports for this month._\n")
    lines.extend(
        [
            "## Cumulative Technical Progress",
            data["cumulative_technical_progress"].strip(),
            "",
            "## GitHub Trends (month)",
            "",
            "### Issues",
            f"- **New:** {gt['issues']['new']}",
            f"- **Closed:** {gt['issues']['closed']}",
            f"- **Open at month end:** {gt['issues']['open_at_month_end']}",
            "",
            "### Branches",
            f"- **New:** {gt['branches']['new']}",
            f"- **Closed:** {gt['branches']['closed']}",
            f"- **Open at month end:** {gt['branches']['open_at_month_end']}",
            "",
            "## Recurring Challenges",
        ]
    )
    for rc in data["recurring_challenges"]:
        lines.append(f"- {rc}")
    if not data["recurring_challenges"]:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Solutions & Resolutions",
            data["solutions_and_resolutions"].strip(),
            "",
            "## Unresolved Issues Carried Forward",
            data["unresolved_carried_forward"].strip(),
            "",
            "## Metrics",
            "| Metric | Value |",
            "|--------|------:|",
            f"| Commits (month) | {data['metrics']['commits']} |",
            f"| Weekly reports used | {data['metrics']['weekly_reports_used']} |",
            "",
        ]
    )
    return "\n".join(lines)
