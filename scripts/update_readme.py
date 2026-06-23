#!/usr/bin/env python3
"""
Scrapes shane.logsdon.io for recent articles and updates the Writing
section of README.md between <!-- BLOG-START --> and <!-- BLOG-END --> markers.

Run manually or via GitHub Actions on a schedule.
"""

import re
import sys
from datetime import datetime
from urllib.request import urlopen, Request
from html.parser import HTMLParser

SITE_URL = "https://shane.logsdon.io"
ARTICLES_URL = f"{SITE_URL}/articles/"
HOMEPAGE_URL = SITE_URL
README_PATH = "README.md"
MARKER_START = "<!-- BLOG-START -->"
MARKER_END = "<!-- BLOG-END -->"
POST_LIMIT = 5


class ArticleParser(HTMLParser):
    """
    Parses HTML from shane.logsdon.io/articles/ and the homepage.
    Looks for <h3> or <h2> elements containing anchor tags whose href
    matches /articles/<category>/<slug>/.
    """

    def __init__(self):
        super().__init__()
        self.articles = []
        self._in_heading = False
        self._in_time = False
        self._current_href = None
        self._current_title = None
        self._current_date_str = None
        self._current_datetime = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("h2", "h3"):
            self._in_heading = True
            self._current_href = None
            self._current_title = None
        if self._in_heading and tag == "a":
            href = attrs.get("href", "")
            if re.match(r"/articles/[^/]+/[^/]+/", href):
                self._current_href = href
        if tag == "time":
            self._in_time = True
            dt = attrs.get("datetime", "")
            if dt:
                try:
                    self._current_datetime = datetime.fromisoformat(dt[:10])
                    self._current_date_str = self._current_datetime.strftime("%b %d, %Y")
                except ValueError:
                    pass

    def handle_endtag(self, tag):
        if tag in ("h2", "h3"):
            if self._current_href and self._current_title:
                self.articles.append({
                    "title": self._current_title.strip(),
                    "url": f"{SITE_URL}{self._current_href}",
                    "date_str": self._current_date_str or "",
                    "date": self._current_datetime,
                })
            self._in_heading = False
            self._current_href = None
            self._current_title = None
        if tag == "time":
            self._in_time = False

    def handle_data(self, data):
        if self._in_heading and self._current_href:
            self._current_title = (self._current_title or "") + data


def fetch_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": "github-actions-readme-updater/1.0"})
    with urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def deduplicate(articles: list) -> list:
    seen = set()
    out = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            out.append(a)
    return out


def fetch_articles() -> list:
    articles = []

    # Try the articles index page first
    try:
        html = fetch_html(ARTICLES_URL)
        parser = ArticleParser()
        parser.feed(html)
        articles.extend(parser.articles)
    except Exception as e:
        print(f"Warning: could not fetch {ARTICLES_URL}: {e}", file=sys.stderr)

    # Also check homepage — it often features the most recent posts
    try:
        html = fetch_html(HOMEPAGE_URL)
        parser = ArticleParser()
        parser.feed(html)
        articles.extend(parser.articles)
    except Exception as e:
        print(f"Warning: could not fetch {HOMEPAGE_URL}: {e}", file=sys.stderr)

    articles = deduplicate(articles)

    # Sort: articles with dates newest-first, then undated ones
    dated = sorted(
        [a for a in articles if a["date"]],
        key=lambda a: a["date"],
        reverse=True,
    )
    undated = [a for a in articles if not a["date"]]

    return (dated + undated)[:POST_LIMIT]


def format_post_line(article: dict) -> str:
    date = f" — {article['date_str']}" if article["date_str"] else ""
    return f"- [{article['title']}]({article['url']}){date}"


def update_readme(posts: list[str]) -> bool:
    """
    Replaces the content between BLOG-START and BLOG-END markers.
    Returns True if the file was changed.
    """
    with open(README_PATH) as f:
        original = f.read()

    block = "\n".join(posts)
    updated = re.sub(
        rf"{re.escape(MARKER_START)}.*?{re.escape(MARKER_END)}",
        f"{MARKER_START}\n{block}\n{MARKER_END}",
        original,
        flags=re.DOTALL,
    )

    if updated == original:
        return False

    with open(README_PATH, "w") as f:
        f.write(updated)

    return True


def main():
    articles = fetch_articles()

    if not articles:
        print("No articles found — README unchanged.")
        return

    lines = [format_post_line(a) for a in articles]
    changed = update_readme(lines)

    if changed:
        print(f"Updated README with {len(lines)} posts:")
        for line in lines:
            print(f"  {line}")
    else:
        print("README already up to date.")


if __name__ == "__main__":
    main()
