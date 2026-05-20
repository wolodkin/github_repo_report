"""Shared configuration, paths, dates, and completion results."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or (PROJECT_ROOT / "config.json")
    with config_path.open(encoding="utf-8") as f:
        return json.load(f)


def resolve_path(config_value: str, *, create: bool = False) -> Path:
    """Resolve config path relative to project root (leading / is not filesystem root)."""
    raw = (config_value or "").strip()
    if not raw:
        raise ValueError("Empty path in config")
    p = Path(raw.lstrip("/"))
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_github_current_state(config: dict[str, Any]) -> Path:
    paths = config.get("paths") or {}
    default = PROJECT_ROOT / "github_current_state"
    configured = paths.get("github_current_state")
    if not configured:
        default.mkdir(parents=True, exist_ok=True)
        logger.info("Using default github_current_state: %s", default)
        return default
    try:
        resolved = resolve_path(str(configured), create=True)
        if resolved.exists() and os_access_writable(resolved):
            logger.info("Using configured github_current_state: %s", resolved)
            return resolved
    except OSError as exc:
        logger.warning("Configured github_current_state unusable (%s); using default", exc)
    default.mkdir(parents=True, exist_ok=True)
    logger.info("Using fallback github_current_state: %s", default)
    return default


def os_access_writable(path: Path) -> bool:
    try:
        test = path / ".write_test"
        test.write_text("", encoding="utf-8")
        test.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    url = repo_url.strip()
    if url.startswith("git@"):
        # git@github.com:owner/repo.git
        match = re.match(r"git@[^:]+:([^/]+)/([^/]+?)(?:\.git)?$", url)
        if not match:
            raise ValueError(f"Cannot parse git SSH URL: {repo_url}")
        return match.group(1), match.group(2).removesuffix(".git")
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Cannot parse repository URL: {repo_url}")
    owner, name = parts[0], parts[1]
    return owner, name.removesuffix(".git")


def repo_slug(repo_url: str) -> str:
    owner, name = parse_repo_url(repo_url)
    return f"{owner}_{name}"


def safe_filename(repo_url: str, suffix: str = "_state") -> str:
    owner, name = parse_repo_url(repo_url)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{owner}_{name}")
    digest = hashlib.sha256(repo_url.encode()).hexdigest()[:8]
    return f"{slug}_{digest}{suffix}.json"


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def read_api_key_file(rel_path: str) -> str | None:
    path = PROJECT_ROOT / rel_path.lstrip("/")
    if not path.is_file():
        return None
    token = path.read_text(encoding="utf-8").strip()
    return token or None


@dataclass
class RepoResult:
    url: str
    ok: bool
    error: str | None = None
    artifacts: list[str] = field(default_factory=list)


@dataclass
class CompletionResult:
    ok: bool
    repos: list[RepoResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_repo(self, result: RepoResult) -> None:
        self.repos.append(result)
        if not result.ok:
            self.ok = False
            if result.error:
                self.errors.append(f"{result.url}: {result.error}")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_datetime(value: str) -> datetime:
    v = value.replace("Z", "+00:00")
    return datetime.fromisoformat(v).astimezone(timezone.utc)


def parse_date(value: str) -> date:
    if "T" in value:
        return parse_iso_datetime(value).date()
    return date.fromisoformat(value[:10])


def iso_week_label(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def iso_week_bounds(iso_week: str) -> tuple[date, date]:
    year_s, week_s = iso_week.split("-W")
    # Monday of ISO week
    start = date.fromisocalendar(int(year_s), int(week_s), 1)
    end = date.fromisocalendar(int(year_s), int(week_s), 7)
    return start, end


def is_week_complete(iso_week: str, today: date | None = None) -> bool:
    today = today or datetime.now(timezone.utc).date()
    _, end = iso_week_bounds(iso_week)
    return today > end


def is_month_complete(year: int, month: int, today: date | None = None) -> bool:
    today = today or datetime.now(timezone.utc).date()
    if today.year > year:
        return True
    if today.year < year:
        return False
    if today.month > month:
        return True
    return False


def month_label(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def month_name(year: int, month: int) -> str:
    return datetime(year, month, 1, tzinfo=timezone.utc).strftime("%B")
