#!/usr/bin/env python3
"""Check this profile's local links/assets; optionally check HTTPS availability."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("README.md", "README.zh-CN.md", "README.ja.md")
PROJECTS = (
    "Weather Observation Station · 稲葉曇",
    "小辫子酱 · Codex Desktop Pet",
)
SUPPORT = "If you enjoy my projects, feel free to support me."
ALLOWED_TAGS = {"p", "strong", "a", "img", "h1", "em", "br", "sub", "details", "summary"}


class ProfileHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.errors = []
        self.disclosures = []
        self.detail_stack = []
        self.in_summary = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in ALLOWED_TAGS:
            self.errors.append(f"Unexpected HTML element: {tag}")
        if any(name == "style" or name.startswith("on") for name in attrs):
            self.errors.append(f"Inline CSS or event handler on {tag}")
        if tag == "img" and not (attrs.get("alt") or "").strip():
            self.errors.append("Image is missing alternative text")
        if tag == "details":
            if self.detail_stack:
                self.errors.append("Language disclosures must not be nested")
            disclosure = {"attrs": attrs, "label": "", "summaries": 0}
            self.disclosures.append(disclosure)
            self.detail_stack.append(disclosure)
        elif tag == "summary":
            if not self.detail_stack or self.in_summary:
                self.errors.append("Summary must belong to one language disclosure")
            else:
                self.detail_stack[-1]["summaries"] += 1
                self.in_summary = True
        for attr in ("href", "src"):
            if attr in attrs:
                self.links.append(attrs[attr] or "")

    def handle_data(self, data):
        if self.in_summary and self.detail_stack:
            self.detail_stack[-1]["label"] += data

    def handle_endtag(self, tag):
        if tag == "summary":
            if not self.in_summary:
                self.errors.append("Unmatched closing summary")
            self.in_summary = False
        elif tag == "details":
            if not self.detail_stack:
                self.errors.append("Unmatched closing details")
            else:
                disclosure = self.detail_stack.pop()
                if disclosure["summaries"] != 1:
                    self.errors.append("Each language disclosure needs exactly one summary")
            if self.in_summary:
                self.errors.append("Summary must close before its details")
                self.in_summary = False

    def close(self):
        super().close()
        if self.detail_stack or self.in_summary:
            self.errors.append("Unclosed language disclosure or summary")


def check_inline_languages(text, html):
    errors = []
    languages = (("🇨🇳 简体中文", False), ("🇯🇵 日本語", False), ("🇺🇸 English", True))
    actual = tuple(
        (item["label"].strip(), "open" in item["attrs"])
        for item in html.disclosures
    )
    if actual != languages:
        errors.append("language disclosures must be 🇨🇳 简体中文, 🇯🇵 日本語, 🇺🇸 English; only English open")
    bodies = re.findall(
        r"<details\b[^>]*>\s*<summary>.*?</summary>\s*\n(.*?)\n</details>",
        text, re.DOTALL,
    )
    if len(bodies) != len(languages):
        errors.append("language disclosures must contain three complete Markdown bodies")
        return errors
    for body, source_name in zip(bodies, ("README.zh-CN.md", "README.ja.md")):
        source = ROOT / source_name
        if not source.is_file():
            continue  # The regular document check reports missing sources.
        standalone = re.sub(
            r"\A\s*(?:<p\b[^>]*>\s*<img\b[^>]*>\s*</p>\s*)?<h1\b[^>]*>.*?</h1>\s*", "",
            source.read_text(encoding="utf-8"), count=1, flags=re.DOTALL,
        )
        if body.strip() != standalone.strip():
            errors.append(f"inline language content differs from {source_name}")
    return errors


def heading_ids(text):
    ids, counts = set(), {}
    for heading in re.findall(r"^#{1,6} (.+)$", text, re.MULTILINE):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-").strip("-")
        count = counts.get(slug, 0)
        ids.add(f"{slug}-{count}" if count else slug)
        counts[slug] = count + 1
    return ids


def check_local():
    errors, external = [], set()
    documents = [ROOT / name for name in PROFILES]
    documents.extend(sorted((ROOT / "docs").glob("*.md")))
    for path in documents:
        if not path.is_file():
            errors.append(f"Missing document: {path.name}")
            continue
        text = path.read_text(encoding="utf-8")
        html = ProfileHTML()
        html.feed(text)
        html.close()
        if path.name in PROFILES:
            if re.match(r"\s*(?:`{3,}|~{3,})", text):
                errors.append(f"{path.name}: profile starts with a code fence; remove the outer wrapper")
            errors.extend(f"{path.name}: {error}" for error in html.errors)
            if path.name == "README.md":
                errors.extend(f"{path.name}: {error}" for error in check_inline_languages(text, html))
            if SUPPORT not in text:
                errors.append(f"{path.name}: missing exact support sentence")
            projects = re.findall(r"^### \d{2} / (.+)$", text, re.MULTILINE)
            expected_projects = PROJECTS * 3 if path.name == "README.md" else PROJECTS
            if tuple(projects) != expected_projects:
                errors.append(f"{path.name}: featured projects/order changed")
            for alt in re.findall(r"!\[([^\]]*)\]\(", text):
                if not alt.strip():
                    errors.append(f"{path.name}: empty Markdown image alt")
        links = html.links + re.findall(r"\]\(([^)\s]+)\)", text)
        for link in links:
            parts = urlsplit(link)
            if parts.scheme == "https":
                external.add(link)
                continue
            if parts.scheme == "mailto":
                if parts.path != "throne-uplift.3b@icloud.com":
                    errors.append(f"{path.name}: unexpected email address")
                continue
            if parts.scheme or parts.netloc:
                errors.append(f"{path.name}: unsupported URL: {link}")
                continue
            if path.name == "README.md" and Path(unquote(parts.path)).name in PROFILES:
                errors.append(f"{path.name}: language navigation must stay inline: {link}")
            target = (path.parent / unquote(parts.path)).resolve() if parts.path else path
            if not target.is_relative_to(ROOT) or not target.is_file():
                errors.append(f"{path.name}: missing/out-of-repository target: {link}")
            elif parts.fragment and target.suffix == ".md":
                ids = heading_ids(target.read_text(encoding="utf-8"))
                if unquote(parts.fragment) not in ids:
                    errors.append(f"{path.name}: missing heading: {link}")

    # Validate any SVG assets added to the profile.
    assets = sorted((ROOT / "assets").glob("*.svg"))
    for path in assets:
        try:
            svg = ET.parse(path).getroot()
        except ET.ParseError as error:
            errors.append(f"{path.name}: invalid XML: {error}")
            continue
        if "viewBox" not in svg.attrib:
            errors.append(f"{path.name}: missing scalable viewBox")
        ns = {"svg": "http://www.w3.org/2000/svg"}
        if svg.find("svg:title", ns) is None or svg.find("svg:desc", ns) is None:
            errors.append(f"{path.name}: missing accessible title/description")
        for element in svg.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag in {"script", "foreignObject", "image", "iframe"}:
                errors.append(f"{path.name}: unexpected SVG element: {tag}")
            for name, value in element.attrib.items():
                if name.startswith("on") or name.endswith("href"):
                    errors.append(f"{path.name}: unexpected active/external attribute: {name}")
                if re.search(r"url\(\s*[^#]", value):
                    errors.append(f"{path.name}: nonlocal SVG resource")
        style = "".join(svg.itertext())
        if "@import" in style or "https://" in style:
            errors.append(f"{path.name}: external SVG dependency")
        if "@keyframes" in style and "prefers-reduced-motion: no-preference" not in style:
            errors.append(f"{path.name}: animation lacks reduced-motion handling")
        if path.stat().st_size > 30_000:
            errors.append(f"{path.name}: exceeds the 30 KB artwork budget")
    return errors, external, len(documents), len(assets)


def check_url(url):
    result = subprocess.run(
        [
            "curl", "--head", "--location", "--silent", "--show-error",
            "--connect-timeout", "10", "--max-time", "30",
            "--output", "/dev/null", "--write-out", "%{http_code}", url,
        ],
        capture_output=True, text=True, check=False,
    )
    status = result.stdout.strip()
    ok = result.returncode == 0 and status.isdigit() and 200 <= int(status) < 300
    detail = status if result.returncode == 0 else result.stderr.strip()
    return ok, f"{'OK' if ok else 'FAIL'} {detail} {url}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="Also check HTTPS links with curl HEAD")
    args = parser.parse_args()
    errors, external, documents, assets = check_local()
    for error in errors:
        print(f"FAIL {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"OK {documents} Markdown documents, {assets} SVG assets, local links and headings")
    if args.online:
        if not shutil.which("curl"):
            print("FAIL curl is required for --online", file=sys.stderr)
            return 1
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(check_url, sorted(external)))
        for _, message in results:
            print(message)
        if not all(ok for ok, _ in results):
            return 1
        print(f"OK {len(results)} unique HTTPS links")
    else:
        print("External links not checked; run with --online to check availability.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
