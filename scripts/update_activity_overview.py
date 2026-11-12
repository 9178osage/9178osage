#!/usr/bin/env python3
"""Update the profile's Markdown-only public contribution overview."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
LOGIN = "9178osage"
START = "<!-- activity-overview:start -->"
END = "<!-- activity-overview:end -->"
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
        repository { nameWithOwner url isPrivate }
        contributions { totalCount }
      }
      commitContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner url isPrivate }
        contributions { totalCount }
      }
      issueContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner url isPrivate }
        contributions { totalCount }
      }
      pullRequestContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner url isPrivate }
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

    counts = {key: 0 for _, _, key in METRICS}
    repositories = {}
    collection = user["contributionsCollection"]
    for _, field, key in METRICS:
        for item in collection[field]:
            repository = item["repository"]
            if not repository or repository.get("isPrivate") is not False:
                continue
            count = item["contributions"]["totalCount"]
            if not isinstance(count, int) or count < 0:
                raise RuntimeError(f"Unexpected contribution count for {field}: {count!r}")
            name = repository["nameWithOwner"]
            url = repository["url"]
            parsed_url = urlsplit(url)
            if parsed_url.scheme != "https" or parsed_url.netloc != "github.com":
                raise RuntimeError(f"Unexpected public repository URL: {url!r}")
            counts[key] += count
            repositories.setdefault(name, {"url": url, "count": 0})["count"] += count
    return counts, repositories


def calculate_percentages(counts):
    total = sum(counts.values())
    if total == 0:
        return {key: 0 for _, _, key in METRICS}

    exact = {key: counts[key] * 100 / total for _, _, key in METRICS}
    result = {key: int(value) for key, value in exact.items()}
    remainder = 100 - sum(result.values())
    order = {key: index for index, (_, _, key) in enumerate(METRICS)}
    for key in sorted(exact, key=lambda item: (-(exact[item] - result[item]), order[item]))[:remainder]:
        result[key] += 1
    return result


def render_activity(counts, repositories):
    shares = calculate_percentages(counts)
    ranked = sorted(
        repositories.items(),
        key=lambda item: (-item[1]["count"], item[0]),
    )
    top = ranked[:3]
    links = [
        f"[{name}]({quote(details['url'], safe=':/')})"
        for name, details in top
    ]
    if links:
        contribution_line = "**Contributed to:** " + " · ".join(links)
        additional = len(ranked) - len(top)
        if additional:
            noun = "repository" if additional == 1 else "repositories"
            contribution_line += f" · and {additional} other public {noun}"
    else:
        contribution_line = "**Contributed to:** No public repositories in this period."

    rows = [
        "",
        "**Public activity · rolling 12 months**",
        "",
        "| Contribution type | Count | Share |",
        "| --- | ---: | ---: |",
    ]
    rows.extend(
        f"| {label} | {counts[key]} | {shares[key]}% |"
        for label, _, key in METRICS
    )
    return "\n".join([contribution_line, *rows])


def update_readme(activity):
    text = README.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1:
        raise RuntimeError("README must contain exactly one activity overview marker pair.")
    start = text.index(START) + len(START)
    end = text.index(END)
    if end <= start:
        raise RuntimeError("README activity overview markers are out of order.")
    updated = text[:start] + "\n" + activity + "\n" + text[end:]
    README.write_text(updated, encoding="utf-8")


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("Set GITHUB_TOKEN or GH_TOKEN to a GitHub token.")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365)
    counts, repositories = fetch_activity(token, start, end)
    update_readme(render_activity(counts, repositories))
    print(
        f"Updated the text overview with {sum(counts.values())} public contributions "
        f"across {len(repositories)} repositories."
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(f"Unable to update activity overview: {error}", file=sys.stderr)
        sys.exit(1)
