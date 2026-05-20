"""Filter cache data by ISO week or calendar month (UTC)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from modules.common_helper import iso_week_bounds, iso_week_label, parse_date, parse_iso_datetime


def commits_in_week(commits: list[dict], iso_week: str) -> list[dict]:
    start, end = iso_week_bounds(iso_week)
    out = []
    for c in commits:
        d = parse_date(c.get("date", ""))
        if start <= d <= end:
            out.append(c)
    return out


def commits_in_month(commits: list[dict], year: int, month: int) -> list[dict]:
    out = []
    for c in commits:
        d = parse_date(c.get("date", ""))
        if d.year == year and d.month == month:
            out.append(c)
    return out


def _in_range(dt_str: str, start: date, end: date) -> bool:
    if not dt_str:
        return False
    d = parse_iso_datetime(dt_str).date()
    return start <= d <= end


def issue_buckets_for_week(issues: list[dict], iso_week: str) -> dict[str, Any]:
    start, end = iso_week_bounds(iso_week)
    new_l, open_l, closed_l = [], [], []
    for i in issues:
        created = i.get("created_at", "")
        closed = i.get("closed_at")
        state = i.get("state", "open")
        if _in_range(created, start, end):
            new_l.append(i)
        if state == "open":
            open_l.append(i)
        elif closed and _in_range(closed, start, end):
            closed_l.append(i)
    return {
        "new": new_l,
        "open": open_l,
        "closed": closed_l,
        "counts": {"new": len(new_l), "open": len(open_l), "closed": len(closed_l)},
    }


def branch_buckets_for_week(branches: list[dict], iso_week: str) -> dict[str, Any]:
    start, end = iso_week_bounds(iso_week)
    new_l, open_l, closed_l = [], [], []
    for b in branches:
        fs = b.get("first_seen_at", "")
        ca = b.get("closed_at")
        status = b.get("status", "open")
        if fs and _in_range(fs, start, end):
            new_l.append(b)
        if status == "open":
            open_l.append(b)
        elif ca and _in_range(ca, start, end):
            closed_l.append(b)
    return {
        "new": new_l,
        "open": open_l,
        "closed": closed_l,
        "counts": {"new": len(new_l), "open": len(open_l), "closed": len(closed_l)},
    }


def issue_buckets_for_month(issues: list[dict], year: int, month: int) -> dict[str, Any]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    new_l, closed_l, open_end = [], [], []
    for i in issues:
        created = i.get("created_at", "")
        closed = i.get("closed_at")
        state = i.get("state", "open")
        if _in_range(created, start, end):
            new_l.append(i)
        if closed and _in_range(closed, start, end):
            closed_l.append(i)
        if state == "open":
            open_end.append(i)
    return {
        "new": len(new_l),
        "closed": len(closed_l),
        "open_at_month_end": len(open_end),
    }


def branch_buckets_for_month(branches: list[dict], year: int, month: int) -> dict[str, Any]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    new_l, closed_l, open_end = 0, 0, 0
    for b in branches:
        fs = b.get("first_seen_at", "")
        ca = b.get("closed_at")
        status = b.get("status", "open")
        if fs and _in_range(fs, start, end):
            new_l += 1
        if ca and _in_range(ca, start, end):
            closed_l += 1
        if status == "open":
            open_end += 1
    return {"new": new_l, "closed": closed_l, "open_at_month_end": open_end}


def weeks_in_month(commits: list[dict], year: int, month: int) -> list[str]:
    weeks: set[str] = set()
    for c in commits:
        if not c.get("date"):
            continue
        d = parse_date(c["date"])
        if d.year == year and d.month == month:
            weeks.add(iso_week_label(d))
    return sorted(weeks)


def weeks_with_commits(commits: list[dict]) -> list[str]:
    weeks: set[str] = set()
    for c in commits:
        if c.get("date"):
            weeks.add(iso_week_label(parse_date(c["date"])))
    return sorted(weeks)


def months_with_commits(commits: list[dict]) -> list[tuple[int, int]]:
    months: set[tuple[int, int]] = set()
    for c in commits:
        if c.get("date"):
            d = parse_date(c["date"])
            months.add((d.year, d.month))
    return sorted(months)
