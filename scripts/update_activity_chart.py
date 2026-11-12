#!/usr/bin/env python3
"""Generate an accessible SVG overview of the account's public GitHub activity."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
import json
import math
import os
from pathlib import Path
import sys
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "activity-breakdown.svg"
LOGIN = "9178osage"
METRICS = (
    ("Code review", "pullRequestReviewContributionsByRepository", "code_review"),
    ("Commits", "commitContributionsByRepository", "commits"),
    ("Issues", "issueContributionsByRepository", "issues"),
    ("Pull requests", "pullRequestContributionsByRepository", "pull_requests"),
)
GRAPHQL_URL = "https://api.github.com/graphql"
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      pullRequestReviewContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner isPrivate }
        contributions { totalCount }
      }
      commitContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner isPrivate }
        contributions { totalCount }
      }
      issueContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner isPrivate }
        contributions { totalCount }
      }
      pullRequestContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner isPrivate }
        contributions { totalCount }
      }
    }
  }
}
"""


def fetch_activity(token, start, end):
    payload = {
        "query": QUERY,
        "variables": {
            "login": LOGIN,
            "from": start.isoformat().replace("+00:00", "Z"),
            "to": end.isoformat().replace("+00:00", "Z"),
        },
    }
    request = Request(
        GRAPHQL_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=30) as response:
        result = json.load(response)

    if result.get("errors"):
        messages = "; ".join(error.get("message", "Unknown GraphQL error") for error in result["errors"])
        raise RuntimeError(f"GitHub GraphQL query failed: {messages}")
    user = result.get("data", {}).get("user")
    if user is None:
        raise RuntimeError(f"GitHub account not found: {LOGIN}")
    collection = user["contributionsCollection"]
    counts = {key: 0 for _, _, key in METRICS}
    repositories = defaultdict(int)
    for _, field, key in METRICS:
        for item in collection[field]:
            repository = item["repository"]
            if not repository or repository.get("isPrivate") is not False:
                continue
            value = item["contributions"]["totalCount"]
            if not isinstance(value, int) or value < 0:
                raise RuntimeError(f"Unexpected contribution count for {field}: {value!r}")
            counts[key] += value
            repositories[repository["nameWithOwner"]] += value
    return counts, dict(repositories)


def percentages(counts):
    total = sum(counts.values())
    if not total:
        return {key: 0 for _, _, key in METRICS}

    exact = {key: counts[key] * 100 / total for _, _, key in METRICS}
    result = {key: math.floor(value) for key, value in exact.items()}
    remainder = 100 - sum(result.values())
    order = {key: index for index, (_, _, key) in enumerate(METRICS)}
    for key in sorted(exact, key=lambda item: (-(exact[item] - result[item]), order[item]))[:remainder]:
        result[key] += 1
    return result


def build_svg(counts, repositories):
    shares = percentages(counts)
    total = sum(counts.values())
    details = "; ".join(
        f"{label}: {counts[key]} ({shares[key]}%)"
        for label, _, key in METRICS
    )
    top_repositories = sorted(repositories.items(), key=lambda item: (-item[1], item[0]))[:3]
    additional_repositories = max(0, len(repositories) - len(top_repositories))
    repository_summary = ", ".join(
        f"{name} ({count})" for name, count in top_repositories
    ) or "none"
    title = "GitHub activity overview"
    description = (
        f"Public contributions over the past 12 months. {details}. Total: {total}. "
        f"Top repositories by contribution count: {repository_summary}. "
        f"{additional_repositories} additional public repositories."
    )

    cx, cy, radius = 575, 258, 124
    points = {
        "code_review": (cx, cy - radius * shares["code_review"] / 100),
        "issues": (cx + radius * shares["issues"] / 100, cy),
        "pull_requests": (cx, cy + radius * shares["pull_requests"] / 100),
        "commits": (cx - radius * shares["commits"] / 100, cy),
    }
    polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in points.values())
    text = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="480" viewBox="0 0 800 480" role="img" aria-labelledby="title desc">',
        f"<title id=\"title\">{escape(title)}</title>",
        f"<desc id=\"desc\">{escape(description)}</desc>",
        '<rect width="800" height="480" rx="14" fill="#ffffff" stroke="#d0d7de"/>',
        '<text x="24" y="46" fill="#24292f" font-family="Arial, Helvetica, sans-serif" font-size="23" font-weight="700">Activity overview</text>',
        '<text x="24" y="96" fill="#57606a" font-family="Arial, Helvetica, sans-serif" font-size="18">Contributed to</text>',
        '<path d="M330 72V408" stroke="#d0d7de" stroke-width="1.5"/>',
    ]
    if top_repositories:
        for index, (repository, _) in enumerate(top_repositories):
            y = 142 + index * 46
            text.append(
                f'<text x="24" y="{y}" textLength="278" lengthAdjust="spacingAndGlyphs" fill="#0969da" font-family="Arial, Helvetica, sans-serif" font-size="19">{escape(repository)}</text>'
            )
        if additional_repositories:
            noun = "repository" if additional_repositories == 1 else "repositories"
            text.append(
                f'<text x="24" y="300" fill="#57606a" font-family="Arial, Helvetica, sans-serif" font-size="17">and {additional_repositories} other {noun}</text>'
            )
    else:
        text.extend((
            '<text x="24" y="142" fill="#57606a" font-family="Arial, Helvetica, sans-serif" font-size="17">No public repository contributions</text>',
            '<text x="24" y="168" fill="#57606a" font-family="Arial, Helvetica, sans-serif" font-size="17">in the past 12 months.</text>',
        ))
    text.extend((
        '<g stroke="#1a7f37" stroke-width="2.5" stroke-linecap="round">',
        '<path d="M440 258H710"/>',
        '<path d="M575 124V392"/>',
        '</g>',
        f'<polygon points="{polygon}" fill="#2da44e" fill-opacity="0.18" stroke="#1a7f37" stroke-width="2.5" stroke-linejoin="round"/>',
    ))
    for label, _, key in METRICS:
        x, y = points[key]
        text.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#ffffff" stroke="#1a7f37" stroke-width="3"/>'
        )
    for label, _, key in METRICS:
        label_positions = {
            "code_review": (cx, "middle", 66, 91),
            "commits": (398, "start", 252, 276),
            "issues": (752, "end", 252, 276),
            "pull_requests": (cx, "middle", 420, 444),
        }
        x, anchor, label_y, value_y = label_positions[key]
        text.extend((
            f'<text x="{x}" y="{label_y}" text-anchor="{anchor}" fill="#57606a" font-family="Arial, Helvetica, sans-serif" font-size="18">{escape(label)}</text>',
            f'<text x="{x}" y="{value_y}" text-anchor="{anchor}" fill="#1a7f37" font-family="Arial, Helvetica, sans-serif" font-size="19" font-weight="700">{shares[key]}%</text>',
        ))
    text.extend((
        '<text x="575" y="466" text-anchor="middle" fill="#6e7781" font-family="Arial, Helvetica, sans-serif" font-size="13">Public contributions · rolling 12 months</text>',
        '</svg>',
        '',
    ))
    return "\n".join(text)


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("Set GITHUB_TOKEN or GH_TOKEN to a GitHub token.")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365)
    counts, repositories = fetch_activity(token, start, end)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".svg.tmp")
    temporary.write_text(build_svg(counts, repositories), encoding="utf-8")
    temporary.replace(OUTPUT)
    print(
        f"Updated {OUTPUT.relative_to(ROOT)} with {sum(counts.values())} public "
        f"contributions across {len(repositories)} repositories."
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(f"Unable to update activity chart: {error}", file=sys.stderr)
        sys.exit(1)
