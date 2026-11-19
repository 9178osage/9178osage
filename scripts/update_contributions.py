#!/usr/bin/env python3
"""Generate the 2026 GitHub contribution heatmap asset."""

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys


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
    }
  }
}
"""

LEVEL_COLORS = ("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39")


def fetch_contributions(login, year):
    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("GitHub CLI (gh) is required")

    now = datetime.now(timezone.utc)
    from_time = f"{year}-01-01T00:00:00Z"
    to_time = (
        f"{year + 1}-01-01T00:00:00Z"
        if year <= now.year
        else f"{year + 1}-01-01T00:00:00Z"
    )
    if year == now.year:
        to_time = (now + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")

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


def month_positions(weeks, year):
    positions = {}
    for week_index, week in enumerate(weeks):
        for day in week["contributionDays"]:
            day_date = date.fromisoformat(day["date"])
            if day_date.year == year and day_date.month not in positions:
                positions[day_date.month] = week_index
    return positions


def safe_color(color):
    return color if color in LEVEL_COLORS else "#ebedf0"


def build_heatmap_svg(collection, year):
    calendar = collection["contributionCalendar"]
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    months = month_positions(weeks, year)
    month_names = (
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1120 300" role="img"',
        '  aria-labelledby="contribution-title contribution-desc">',
        f'  <title id="contribution-title">{total:,} contributions in {year}</title>',
        f'  <desc id="contribution-desc">Monthly GitHub contribution heatmap for {year}.</desc>',
        "  <style>",
        "    .card { fill:#ffffff; stroke:#d0d7de; }",
        "    .text { fill:#24292f; }",
        "    .muted { fill:#57606a; }",
        "    @media (prefers-color-scheme: dark) {",
        "      .card { fill:#0d1117; stroke:#30363d; }",
        "      .text { fill:#c9d1d9; }",
        "      .muted { fill:#8b949e; }",
        "    }",
        "  </style>",
        '  <rect class="card" x="14" y="14" width="1092" height="272" rx="8"/>',
        f'  <text class="text" x="34" y="50" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="24" font-weight="600">{total:,} contributions in {year}</text>',
    ]

    grid_x = 82
    grid_y = 94
    pitch = 17

    for month_index, month_name in enumerate(month_names, start=1):
        week_index = months.get(month_index)
        if week_index is not None:
            month_x = grid_x + week_index * pitch
            lines.append(
                f'  <text class="text" x="{month_x}" y="78" '
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
            lines.append(
                f'  <rect x="{cell_x}" y="{cell_y}" width="12" height="12" rx="2" '
                f'fill="{safe_color(day["color"])}"/>'
            )

    legend_y = 234
    lines.extend(
        [
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
    output.write_text(build_heatmap_svg(collection, args.year), encoding="utf-8")
    total = collection["contributionCalendar"]["totalContributions"]
    commits = collection["totalCommitContributions"]
    issues = collection["totalIssueContributions"]
    pull_requests = collection["totalPullRequestContributions"]
    reviews = collection["totalPullRequestReviewContributions"]
    print(
        f"OK {args.login}: {total:,} contributions in {args.year}; "
        f"{commits:,} commits, {issues:,} issues, "
        f"{pull_requests:,} pull requests, {reviews:,} reviews"
    )
    print(f"Wrote {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
