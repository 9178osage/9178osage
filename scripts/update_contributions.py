#!/usr/bin/env python3
"""Generate a local GitHub contribution activity card from public GraphQL data."""

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "github-contributions-2026.svg"
LOGIN = "9178osage"

GRAPHQL_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            color
          }
        }
      }
      commitContributionsByRepository(maxRepositories: 100) {
        contributions {
          totalCount
        }
        repository {
          nameWithOwner
          isPrivate
        }
      }
      issueContributionsByRepository(maxRepositories: 100) {
        contributions {
          totalCount
        }
        repository {
          nameWithOwner
          isPrivate
        }
      }
      pullRequestContributionsByRepository(maxRepositories: 100) {
        contributions {
          totalCount
        }
        repository {
          nameWithOwner
          isPrivate
        }
      }
    }
  }
}
"""

LEVEL_COLORS = (
    "#ebedf0",
    "#9be9a8",
    "#40c463",
    "#30a14e",
    "#216e39",
)


def fetch_contributions(login, year):
    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("GitHub CLI (gh) is required")

    now = datetime.now(timezone.utc)
    from_time = f"{year}-01-01T00:00:00Z"
    if year < now.year:
        to_time = f"{year + 1}-01-01T00:00:00Z"
    elif year == now.year:
        to_time = (now + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    else:
        to_time = f"{year + 1}-01-01T00:00:00Z"

    result = subprocess.run(
        [
            gh,
            "api",
            "graphql",
            "-f",
            f"query={GRAPHQL_QUERY}",
            "-f",
            f"login={login}",
            "-f",
            f"from={from_time}",
            "-f",
            f"to={to_time}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown GitHub CLI error"
        raise RuntimeError(detail)

    payload = json.loads(result.stdout)
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False))
    user = payload.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user not found: {login}")
    return user["contributionsCollection"]


def safe_color(color):
    return color if color in LEVEL_COLORS else "#ebedf0"


def percent(numerator, denominator):
    if denominator <= 0:
        return "0%"
    value = numerator * 100 / denominator
    if value >= 10:
        return f"{value:.0f}%"
    if value >= 1:
        return f"{value:.1f}%"
    return f"{value:.1f}%"


def month_positions(weeks, year):
    positions = {}
    for week_index, week in enumerate(weeks):
        for day in week["contributionDays"]:
            day_date = date.fromisoformat(day["date"])
            if day_date.year == year and day_date.month not in positions:
                positions[day_date.month] = week_index
    return positions


def repository_names(collection):
    names = []
    for item in collection:
        if item["repository"].get("isPrivate"):
            continue
        name = item["repository"]["nameWithOwner"].split("/", 1)[-1]
        if name not in names:
            names.append(name)
    return names


def build_svg(collection, year):
    calendar = collection["contributionCalendar"]
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    commits = collection["totalCommitContributions"]
    issues = collection["totalIssueContributions"]
    pull_requests = collection["totalPullRequestContributions"]
    reviews = collection["totalPullRequestReviewContributions"]

    month_names = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    months = month_positions(weeks, year)

    repo_names = repository_names(collection["commitContributionsByRepository"])
    top_repos = repo_names[:3]
    remaining_repos = max(0, len(repo_names) - len(top_repos))
    activity_total = commits + issues + pull_requests + reviews

    commit_percent = percent(commits, activity_total)
    pull_request_percent = percent(pull_requests, activity_total)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1120 430" role="img"',
        '  aria-labelledby="contribution-title contribution-desc">',
        f'  <title id="contribution-title">{total:,} contributions in {year}</title>',
        (
            '  <desc id="contribution-desc">'
            f"A yearly GitHub contribution heatmap and activity overview for {year}. "
            f"{commits:,} commits, {issues:,} issues, "
            f"{pull_requests:,} pull requests, and {reviews:,} code reviews."
            "</desc>"
        ),
        "  <style>",
        "    .card { fill:#ffffff; stroke:#d0d7de; }",
        "    .panel { fill:#f6f8fa; stroke:#d8dee4; }",
        "    .text { fill:#24292f; }",
        "    .muted { fill:#57606a; }",
        "    .link { fill:#0969da; }",
        "    .divider { stroke:#d8dee4; }",
        "    .axis { stroke:#a2a2a2; }",
        "    @media (prefers-color-scheme: dark) {",
        "      .card { fill:#0d1117; stroke:#30363d; }",
        "      .panel { fill:#161b22; stroke:#30363d; }",
        "      .text { fill:#c9d1d9; }",
        "      .muted { fill:#8b949e; }",
        "      .link { fill:#58a6ff; }",
        "      .divider { stroke:#30363d; }",
        "    }",
        "  </style>",
        '  <rect class="card" x="14" y="14" width="1092" height="402" rx="8"/>',
        f'  <text class="text" x="34" y="50" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="24" font-weight="600">{total:,} contributions in {year}</text>',
        '  <rect class="panel" x="34" y="76" width="1052" height="204" rx="6"/>',
    ]

    grid_x = 82
    grid_y = 126
    pitch = 17

    for month_index, month_name in enumerate(month_names, start=1):
        week_index = months.get(month_index)
        if week_index is None:
            continue
        month_x = grid_x + week_index * pitch
        lines.append(
            f'  <text class="text" x="{month_x}" y="102" '
            'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" '
            f'font-size="14" font-weight="600">{month_name}</text>'
        )

    for label, row in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
        label_y = grid_y + row * pitch + 11
        lines.append(
            f'  <text class="muted" x="44" y="{label_y}" '
            'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" '
            f'font-size="13" font-weight="600">{label}</text>'
        )

    for week_index, week in enumerate(weeks):
        for day_index, day in enumerate(week["contributionDays"]):
            day_date = date.fromisoformat(day["date"])
            if day_date.year != year:
                continue
            cell_x = grid_x + week_index * pitch
            cell_y = grid_y + day_index * pitch
            color = safe_color(day["color"])
            lines.append(
                f'  <rect x="{cell_x}" y="{cell_y}" width="12" height="12" rx="2" '
                f'fill="{color}"/>'
            )

    legend_y = 257
    lines.extend(
        [
            f'  <text class="link" x="34" y="{legend_y}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="13">View on GitHub</text>',
            f'  <text class="muted" x="890" y="{legend_y}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="13">Less</text>',
        ]
    )
    for index, color in enumerate(LEVEL_COLORS):
        square_x = 932 + index * 21
        lines.append(
            f'  <rect x="{square_x}" y="{legend_y - 12}" width="12" height="12" rx="2" fill="{color}"/>'
        )
    lines.append(
        f'  <text class="muted" x="1042" y="{legend_y}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="13">More</text>'
    )

    lines.append(
        '  <line class="divider" x1="34" y1="292" x2="1086" y2="292"/>'
    )
    lines.extend(
        [
            f'  <text class="text" x="34" y="322" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="17" font-weight="600">Activity overview</text>',
            f'  <text class="muted" x="34" y="350" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14">Contributed to</text>',
        ]
    )

    repo_y = 374
    for repo_name in top_repos:
        lines.append(
            f'  <text class="link" x="34" y="{repo_y}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="15" font-weight="600">{escape(repo_name)}</text>'
        )
        repo_y += 21
    if remaining_repos:
        lines.append(
            f'  <text class="muted" x="34" y="{repo_y}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="13">and {remaining_repos} other repositories</text>'
        )

    lines.extend(
        [
            f'  <text class="muted" x="790" y="322" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="16" font-weight="600">Contribution mix</text>',
            '  <line class="axis" x1="650" y1="374" x2="1034" y2="374" stroke-width="2"/>',
            '  <line class="axis" x1="842" y1="334" x2="842" y2="414" stroke-width="2"/>',
            '  <circle cx="842" cy="374" r="5" fill="#30a14e" stroke="#216e39" stroke-width="2"/>',
            f'  <text class="muted" x="650" y="358" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14">{commit_percent}</text>',
            f'  <text class="text" x="650" y="395" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14">Commits: {commits:,}</text>',
            f'  <text class="muted" x="950" y="358" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14">Issues: {issues:,}</text>',
            f'  <text class="muted" x="820" y="333" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="13">Code review: {reviews:,}</text>',
            f'  <text class="muted" x="820" y="410" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="13">Pull requests: {pull_requests:,} ({pull_request_percent})</text>',
        ]
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", default=LOGIN)
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    try:
        collection = fetch_contributions(args.login, args.year)
    except (RuntimeError, json.JSONDecodeError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_svg(collection, args.year), encoding="utf-8")
    total = collection["contributionCalendar"]["totalContributions"]
    print(f"OK {args.login}: {total:,} contributions in {args.year}; wrote {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
