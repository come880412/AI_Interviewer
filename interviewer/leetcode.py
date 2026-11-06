"""Coding problems fetched from LeetCode, with difficulty ratings from zerotrac/leetcode_problem_rating.

Nothing is kept in the repository. The problem list and the ratings are cached for a week, and each problem
that was used is cached for good, so a resumed session or its report works offline:

    ~/.cache/ai-interviewer/leetcode/catalog.json       every free algorithm problem: title, difficulty, tags, likes
    ~/.cache/ai-interviewer/leetcode/ratings.json       contest problem ratings (about 1100 to 3100)
    ~/.cache/ai-interviewer/leetcode/problems/<slug>.json

The content is fetched for your own practice; LeetCode's terms apply to it.
"""

import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from interviewer import settings  # noqa: F401  (loads .env before the settings below are read)

CACHE_DIR = Path(os.getenv("LEETCODE_CACHE_DIR", Path.home() / ".cache" / "ai-interviewer" / "leetcode"))
GRAPHQL_URL = "https://leetcode.com/graphql"
RATINGS_URL = "https://raw.githubusercontent.com/zerotrac/leetcode_problem_rating/main/data.json"
HEADERS = {"Content-Type": "application/json", "Referer": "https://leetcode.com/problemset/",
           "User-Agent": "Mozilla/5.0 (ai-interviewer mock interview practice)"}
LIST_MAX_AGE = 7 * 24 * 3600  # seconds before the problem list and ratings are fetched again
PAGE_SIZE = 100  # LeetCode returns at most 100 problems per request
SNIPPETS = {"python": "python3", "cpp": "cpp"}  # our language -> LeetCode's langSlug

# "Interview problems only" leaves out problems people rate poorly (Divisor Game: 37% likes, String to Integer:
# 29%), while classic interview problems are all above 80%, and topics coding interviews almost never ask:
# puzzles, games, number theory and combinatorics, probability, geometry, and contest-only techniques.
# It also wants an algorithm or data structure tag, not only GENERIC_TAGS, which mostly mark "do what the
# statement says" problems; very popular classics such as Rotate Image and Spiral Matrix are kept anyway.
MIN_LIKE_RATIO = 0.75
GENERIC_TAGS = {"array", "string", "math", "simulation", "enumeration", "counting", "matrix", "brute-force-search"}
CLASSIC_LIKES = 6800
NON_INTERVIEW_TAGS = {
    "brainteaser", "game-theory", "minimax-algorithm", "nim-game", "impartial-game", "zero-sum-game",
    "sprague-grundy-theorem", "number-theory", "combinatorics", "primality-test", "sieve-theory",
    "prime-number-sieve", "prime-factorization", "fermats-little-theorem", "eulers-totient-function",
    "eulers-theorem", "bezouts-lemma", "extended-euclidean-algorithm", "inclusion-exclusion-principle",
    "probability-and-statistics", "rejection-sampling", "geometry", "polygons", "convex-hull", "triangulation",
    "linear-algebra", "interactive", "flow-network", "maximum-flow", "minimum-cut", "minimum-cost-flow",
    "successive-shortest-path-algorithm", "edmonds-karp-algorithm", "dinics-algorithm", "push-relabel-algorithm",
    "mpm-algorithm", "hungarian-algorithm", "matching-graph", "perfect-matching", "maximum-matching",
    "suffix-array", "suffix-automaton", "suffix-tree", "palindromic-tree", "lyndon-factorization",
    "li-chao-tree", "persistent-data-structure", "dancing-links", "algorithm-x", "sqrt-decomposition",
    "k-d-tree", "planar-graph",
}

LIST_QUERY = """query list($skip: Int, $limit: Int) {
  questionList(categorySlug: "algorithms", limit: $limit, skip: $skip, filters: {}) {
    totalNum
    data { questionFrontendId title titleSlug difficulty isPaidOnly likes dislikes topicTags { name slug } }
  }
}"""
PROBLEM_QUERY = """query problem($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionFrontendId title titleSlug difficulty isPaidOnly content hints
    topicTags { name slug } codeSnippets { langSlug code }
  }
}"""


class LeetCodeError(RuntimeError):
    pass


@dataclass
class Problem:
    id: str  # the title slug, e.g. "number-of-islands"
    number: str  # LeetCode's problem number, e.g. "200"
    title: str
    difficulty: str  # "easy", "medium" or "hard"
    tags: list[str]  # tag names, e.g. ["Array", "Breadth-First Search"]
    content_html: str  # the statement as LeetCode publishes it, sanitized for the page
    text: str  # the same statement as plain text, for the prompts
    starter: dict[str, str]  # our language -> starter code
    hints: list[str] = field(default_factory=list)  # LeetCode's own hints, often none
    rating: float | None = None  # zerotrac rating, contest problems only

    @property
    def url(self) -> str:
        return f"https://leetcode.com/problems/{self.id}/"


# ----- Network and cache -----

def _request(url: str, body: dict | None = None, timeout: int = 30) -> bytes:
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=HEADERS), timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        host = url.split("/")[2]
        raise LeetCodeError(f"連不上 {host}：{getattr(e, 'reason', e)}") from e


def _request_json(url: str, body: dict | None = None, timeout: int = 30):
    raw = _request(url, body, timeout)
    try:
        return json.loads(raw)
    except ValueError as e:  # e.g. a login, captcha or captive-portal page instead of the API's JSON
        raise LeetCodeError(f"{url.split('/')[2]} 回傳的不是預期的資料，請稍後再試。") from e


def _graphql(query: str, variables: dict) -> dict:
    reply = _request_json(GRAPHQL_URL, {"query": query, "variables": variables})
    if reply.get("errors"):
        raise LeetCodeError(f"LeetCode 回傳錯誤：{reply['errors'][0].get('message')}")
    return reply["data"]


def _cached(name: str, max_age: float | None, fetch, valid=lambda data: True):
    """Reads CACHE_DIR/name if it is fresh enough and valid(data), otherwise fetches and stores it. A stale
    copy is still used when the fetch fails, so practice keeps working offline."""
    path = CACHE_DIR / name
    if path.exists() and (max_age is None or time.time() - path.stat().st_mtime < max_age):
        data = json.loads(path.read_text(encoding="utf-8"))
        if valid(data):
            return data
    try:
        data = fetch()
    except LeetCodeError:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    # Two requests can refresh the same file at once (the setup page and bot.py); each writes its own temp file.
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return data


def _fetch_catalog() -> list[dict]:
    first = _graphql(LIST_QUERY, {"skip": 0, "limit": PAGE_SIZE})["questionList"]
    pages = [first["data"]]
    with ThreadPoolExecutor(max_workers=8) as pool:
        skips = range(PAGE_SIZE, first["totalNum"], PAGE_SIZE)
        pages += pool.map(lambda s: _graphql(LIST_QUERY, {"skip": s, "limit": PAGE_SIZE})["questionList"]["data"], skips)
    return [
        {"number": q["questionFrontendId"], "id": q["titleSlug"], "title": q["title"],
         "difficulty": q["difficulty"].lower(), "tags": [t["slug"] for t in q["topicTags"]],
         "tag_names": [t["name"] for t in q["topicTags"]], "likes": q["likes"], "dislikes": q["dislikes"]}
        for page in pages for q in page if not q["isPaidOnly"]
    ]


def catalog() -> list[dict]:
    """Every free algorithm problem: number, id (slug), title, difficulty, tags (slugs), tag names, likes and
    dislikes."""
    # A list cached before likes were recorded is fetched again.
    return _cached("catalog.json", LIST_MAX_AGE, _fetch_catalog, valid=lambda data: not data or "likes" in data[0])


def ratings() -> dict[str, float]:
    """Problem slug -> zerotrac rating."""
    return _cached("ratings.json", LIST_MAX_AGE, lambda: {
        r["TitleSlug"]: round(r["Rating"]) for r in _request_json(RATINGS_URL, timeout=60)
    })


def tags() -> list[dict]:
    """Every tag with how many free problems have it, most common first."""
    counts: dict[str, dict] = {}
    for p in catalog():
        for slug, name in zip(p["tags"], p["tag_names"]):
            counts.setdefault(slug, {"slug": slug, "name": name, "count": 0})["count"] += 1
    return sorted(counts.values(), key=lambda t: -t["count"])


def problem(slug: str) -> Problem:
    """One problem's full content; fetched once, then read from the cache."""
    raw = _cached(f"problems/{slug}.json", None, lambda: _graphql(PROBLEM_QUERY, {"titleSlug": slug})["question"])
    if not raw or raw.get("isPaidOnly") or not raw.get("content"):
        raise LeetCodeError(f"{slug} 不存在或是付費題目")
    snippets = {s["langSlug"]: s["code"] for s in raw.get("codeSnippets") or []}
    missing = [lang for lang, slug_ in SNIPPETS.items() if slug_ not in snippets]
    if missing:
        raise LeetCodeError(f"{slug} 沒有 {', '.join(missing)} 的程式範本")
    return Problem(
        id=raw["titleSlug"],
        number=raw["questionFrontendId"],
        title=raw["title"],
        difficulty=raw["difficulty"].lower(),
        tags=[t["name"] for t in raw.get("topicTags") or []],
        content_html=sanitize(raw["content"]),
        text=html_to_text(raw["content"]),
        starter={lang: snippets[slug_].rstrip() + "\n" for lang, slug_ in SNIPPETS.items()},
        hints=[html_to_text(h) for h in raw.get("hints") or []],
        rating=ratings_or_empty().get(raw["titleSlug"]),
    )


def ratings_or_empty() -> dict[str, float]:
    try:
        return ratings()
    except LeetCodeError:
        return {}


# ----- Choosing problems -----

def interview_style(entry: dict) -> bool:
    """Whether a catalog entry looks like an interview problem: an algorithm problem, well liked, and with no
    puzzle or contest-only tag."""
    tags = set(entry["tags"])
    if NON_INTERVIEW_TAGS & tags:
        return False
    if "likes" not in entry:  # a stale list from before likes were recorded
        return bool(tags - GENERIC_TAGS)
    votes = entry["likes"] + entry["dislikes"]
    if not votes or entry["likes"] / votes < MIN_LIKE_RATIO:
        return False
    return bool(tags - GENERIC_TAGS) or entry["likes"] >= CLASSIC_LIKES


def matching(difficulties: list[str], tag_slugs: list[str] | None = None, rating_range: list | None = None,
             interview_only: bool = False) -> list[dict]:
    """Catalog entries at one of the difficulties, with any of the tags (none: any tag), when a rating range
    is given a rating inside it, and with interview_only only interview-style problems. Each entry gets its
    "rating" (None for problems without one)."""
    rated = ratings_or_empty() if rating_range else {}
    low, high = rating_range or (None, None)
    wanted = set(tag_slugs or [])
    result = []
    for p in catalog():
        if p["difficulty"] not in difficulties or (wanted and not wanted & set(p["tags"])):
            continue
        if interview_only and not interview_style(p):
            continue
        rating = rated.get(p["id"])
        if rating_range and (rating is None or (low is not None and rating < low) or (high is not None and rating > high)):
            continue
        result.append({**p, "rating": rating})
    return result


# ----- HTML -----

ALLOWED_TAGS = {"p", "pre", "code", "strong", "b", "em", "i", "u", "ul", "ol", "li", "sup", "sub", "br", "img",
                "table", "thead", "tbody", "tr", "td", "th", "span", "div", "font", "blockquote"}
VOID_TAGS = {"br", "img"}


class _Sanitizer(HTMLParser):
    """Keeps formatting tags and https images, drops everything else (scripts, handlers, styles)."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.skip = 0  # inside <script> or <style>

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if self.skip or tag not in ALLOWED_TAGS:
            return
        kept = ""
        if tag == "img":
            a = dict(attrs)
            if not (a.get("src") or "").startswith("https://"):
                return
            kept = f' src="{html.escape(a["src"])}" alt="{html.escape(a.get("alt") or "")}"'
            kept += ' style="max-width: 100%; height: auto;"'
        self.out.append(f"<{tag}{kept}>")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        if not self.skip:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip:
            self.out.append(f"&#{name};")


def sanitize(text: str) -> str:
    s = _Sanitizer()
    s.feed(text)
    s.close()
    return "".join(s.out)


class _TextConverter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out: list[str] = []
        self.pre = 0

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.out.append("\n- ")
        elif tag in ("p", "div", "pre", "br", "ul", "ol"):
            self.out.append("\n")
        elif tag == "sup":
            self.out.append("^")
        elif tag == "img":
            self.out.append("[figure]")
        if tag == "pre":
            self.pre += 1

    def handle_endtag(self, tag):
        if tag == "pre":
            self.pre = max(0, self.pre - 1)
        if tag in ("p", "pre", "ul", "ol"):
            self.out.append("\n")

    def handle_data(self, data):
        self.out.append(data if self.pre else re.sub(r"\s+", " ", data))


def html_to_text(text: str) -> str:
    c = _TextConverter()
    c.feed(text)
    c.close()
    plain = "".join(c.out).replace("\xa0", " ")
    plain = re.sub(r"[ \t]+\n", "\n", plain)
    return re.sub(r"\n{3,}", "\n\n", plain).strip()
