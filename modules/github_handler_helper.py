"""GitHub REST API helpers."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from modules.common_helper import read_api_key_file, utc_now_iso

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


def github_token(config: dict[str, Any]) -> str | None:
    paths = config.get("paths") or {}
    token_file = paths.get("github_token_file")
    if token_file:
        return read_api_key_file(str(token_file))
    return os.environ.get("GITHUB_TOKEN")


def github_request(
    path: str,
    *,
    token: str | None = None,
    params: dict[str, str] | None = None,
) -> Any:
    url = API_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github_repo_report",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code} for {path}: {body}") from exc


def fetch_all_commits(owner: str, repo: str, token: str | None) -> list[dict[str, Any]]:
    commits: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = github_request(
            f"/repos/{owner}/{repo}/commits",
            token=token,
            params={"per_page": "100", "page": str(page)},
        )
        if not batch:
            break
        for item in batch:
            commit = item.get("commit") or {}
            author = commit.get("author") or {}
            commits.append(
                {
                    "sha": item["sha"],
                    "date": author.get("date", ""),
                    "author": (author.get("name") or "unknown"),
                    "message": commit.get("message") or "",
                }
            )
        if len(batch) < 100:
            break
        page += 1
    return commits


def fetch_all_issues(owner: str, repo: str, token: str | None) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = github_request(
            f"/repos/{owner}/{repo}/issues",
            token=token,
            params={"state": "all", "per_page": "100", "page": str(page)},
        )
        if not batch:
            break
        for item in batch:
            if "pull_request" in item:
                continue
            issues.append(
                {
                    "number": item["number"],
                    "state": item.get("state", "open"),
                    "created_at": item.get("created_at", ""),
                    "closed_at": item.get("closed_at"),
                    "updated_at": item.get("updated_at", ""),
                    "title": item.get("title", ""),
                    "labels": [lb.get("name", "") for lb in item.get("labels", [])],
                }
            )
        if len(batch) < 100:
            break
        page += 1
    return issues


def fetch_branch_names(owner: str, repo: str, token: str | None) -> list[str]:
    names: list[str] = []
    page = 1
    while True:
        batch = github_request(
            f"/repos/{owner}/{repo}/branches",
            token=token,
            params={"per_page": "100", "page": str(page)},
        )
        if not batch:
            break
        names.extend(b["name"] for b in batch if b.get("name"))
        if len(batch) < 100:
            break
        page += 1
    return names


def fetch_project_remark(
    owner: str,
    repo: str,
    filename: str,
    token: str | None,
) -> dict[str, Any]:
    path = urllib.parse.quote(filename, safe="")
    try:
        data = github_request(
            f"/repos/{owner}/{repo}/contents/{path}",
            token=token,
        )
        import base64

        content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        return {"found": True, "content": content, "fetched_at": utc_now_iso()}
    except RuntimeError as exc:
        if "404" in str(exc):
            return {"found": False, "content": "", "fetched_at": utc_now_iso(), "error": "not_found"}
        raise


def merge_commits(existing: list[dict], new_items: list[dict]) -> list[dict]:
    by_sha = {c["sha"]: c for c in existing if c.get("sha")}
    for c in new_items:
        if c.get("sha"):
            by_sha[c["sha"]] = c
    return sorted(by_sha.values(), key=lambda x: x.get("date", ""))


def merge_issues(existing: list[dict], new_items: list[dict]) -> list[dict]:
    now = utc_now_iso()
    by_num: dict[int, dict] = {i["number"]: dict(i) for i in existing if i.get("number") is not None}
    for item in new_items:
        num = item["number"]
        prev = by_num.get(num)
        if prev is None:
            item = {**item, "first_seen_at": now}
        else:
            item = {**prev, **item}
            item.setdefault("first_seen_at", prev.get("first_seen_at", now))
        by_num[num] = item
    return sorted(by_num.values(), key=lambda x: x["number"])


def merge_branches(
    existing: list[dict],
    remote_names: list[str],
) -> list[dict]:
    now = utc_now_iso()
    by_name = {b["name"]: dict(b) for b in existing if b.get("name")}
    remote_set = set(remote_names)
    for name in remote_names:
        if name not in by_name:
            by_name[name] = {
                "name": name,
                "status": "open",
                "first_seen_at": now,
                "closed_at": None,
            }
        else:
            by_name[name]["status"] = "open"
            by_name[name]["closed_at"] = None
    for name, branch in list(by_name.items()):
        if name not in remote_set and branch.get("status") == "open":
            branch["status"] = "closed"
            branch["closed_at"] = branch.get("closed_at") or now
    return sorted(by_name.values(), key=lambda x: x["name"])
