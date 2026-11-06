"""Fetching problems from LeetCode and ratings from zerotrac, the cache, filtering, and the HTML handling.
The network is faked (see fake_leetcode in conftest.py)."""

import json
import os
import time

import pytest

from interviewer import leetcode


def test_catalog_reads_every_page_and_skips_paid_problems(fake_leetcode):
    entries = leetcode.catalog()
    assert len(fake_leetcode.calls) == 4  # 12 problems, 3 per page
    slugs = [p["id"] for p in entries]
    assert "paid-graph" not in slugs and len(slugs) == 11
    islands = next(p for p in entries if p["id"] == "number-of-islands")
    assert islands == {"number": "200", "id": "number-of-islands", "title": "Number Of Islands",
                       "difficulty": "medium", "tags": ["graph", "breadth-first-search"],
                       "tag_names": ["Graph", "Breadth First Search"], "likes": 1000, "dislikes": 50}


def test_catalog_and_ratings_are_cached(fake_leetcode):
    leetcode.catalog()
    leetcode.ratings()
    count = len(fake_leetcode.calls)
    leetcode.catalog()
    assert leetcode.ratings()["is-graph-bipartite"] == 1625
    assert len(fake_leetcode.calls) == count


def test_a_stale_cache_is_refreshed(fake_leetcode):
    leetcode.catalog()
    path = leetcode.CACHE_DIR / "catalog.json"
    old = time.time() - leetcode.LIST_MAX_AGE - 60
    os.utime(path, (old, old))
    count = len(fake_leetcode.calls)
    leetcode.catalog()
    assert len(fake_leetcode.calls) > count


def test_a_stale_cache_is_used_when_offline():
    path = leetcode.CACHE_DIR / "catalog.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"id": "cached"}]), encoding="utf-8")
    old = time.time() - leetcode.LIST_MAX_AGE - 60
    os.utime(path, (old, old))
    assert leetcode.catalog() == [{"id": "cached"}]  # the conftest makes every request fail


def test_offline_without_a_cache_raises():
    with pytest.raises(leetcode.LeetCodeError, match="offline"):
        leetcode.catalog()
    assert leetcode.ratings_or_empty() == {}


def test_tags_most_common_first(fake_leetcode):
    tags = leetcode.tags()
    assert tags[0] == {"slug": "graph", "name": "Graph", "count": 4}  # the paid one is not counted
    assert {t["slug"] for t in tags} >= {"tree", "linked-list", "array"}


@pytest.mark.parametrize("difficulties, tags, rating, expected", [
    (["medium"], None, None, {"number-of-islands", "is-graph-bipartite", "lowest-common-ancestor", "no-cpp-graph",
                              "disliked-graph", "count-letters", "spiral-matrix"}),
    (["easy", "hard"], None, None, {"two-sum", "hard-tree", "reverse-linked-list", "divisor-game"}),
    (["medium", "hard"], ["tree", "linked-list"], None, {"lowest-common-ancestor", "hard-tree"}),  # any tag
    (["easy", "medium", "hard"], ["graph"], [1600, 1700], {"is-graph-bipartite", "no-cpp-graph"}),  # rated only
    (["easy", "medium", "hard"], None, [1700, None], {"lowest-common-ancestor", "hard-tree"}),  # open upper bound
    (["easy", "medium", "hard"], None, [None, 1300], {"reverse-linked-list"}),
    (["hard"], ["graph"], None, set()),
])
def test_matching(fake_leetcode, difficulties, tags, rating, expected):
    found = leetcode.matching(difficulties, tags, rating)
    assert {p["id"] for p in found} == expected
    if rating:
        assert all(p["rating"] is not None for p in found)


def test_matching_interview_problems_only(fake_leetcode):
    found = {p["id"] for p in leetcode.matching(["easy", "medium"], interview_only=True)}
    assert found == {"number-of-islands", "is-graph-bipartite", "lowest-common-ancestor", "no-cpp-graph", "two-sum",
                     "reverse-linked-list", "spiral-matrix"}
    found = {p["id"] for p in leetcode.matching(["medium"], ["graph"], interview_only=True)}
    assert "disliked-graph" not in found and "number-of-islands" in found


@pytest.mark.parametrize("entry, expected", [
    ({"tags": ["graph"], "likes": 900, "dislikes": 100}, True),
    ({"tags": ["graph"], "likes": 700, "dislikes": 300}, False),  # 70% likes
    ({"tags": ["graph"], "likes": 0, "dislikes": 0}, False),
    ({"tags": ["dynamic-programming", "game-theory"], "likes": 900, "dislikes": 10}, False),
    ({"tags": ["array", "simulation"], "likes": 900, "dislikes": 10}, False),
    ({"tags": ["array", "matrix"], "likes": 20000, "dislikes": 1000}, True),  # a classic
    ({"tags": ["graph"]}, True),  # a list cached before likes were recorded
    ({"tags": ["string"]}, False),
])
def test_interview_style(entry, expected):
    assert leetcode.interview_style(entry) is expected


def test_catalog_without_likes_is_fetched_again(fake_leetcode):
    path = leetcode.CACHE_DIR / "catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[{"id": "old", "tags": []}]', encoding="utf-8")
    assert leetcode.catalog()[0]["likes"] == 1000


def test_problem(fake_leetcode):
    p = leetcode.problem("number-of-islands")
    assert (p.id, p.number, p.title, p.difficulty) == ("number-of-islands", "200", "Number Of Islands", "medium")
    assert p.tags == ["Graph", "Breadth First Search"]
    assert p.url == "https://leetcode.com/problems/number-of-islands/"
    assert p.starter["python"].startswith("class Solution:") and p.starter["cpp"].startswith("class Solution {")
    assert p.hints == ["Flood fill."]
    assert p.text == "Solve number-of-islands.\n\nInput: x = 1\nOutput: 2"
    assert p.rating is None
    assert leetcode.problem("is-graph-bipartite").rating == 1625


def test_problems_are_cached_for_good(fake_leetcode):
    leetcode.problem("two-sum")
    path = leetcode.CACHE_DIR / "problems" / "two-sum.json"
    old = time.time() - 10 * leetcode.LIST_MAX_AGE
    os.utime(path, (old, old))
    count = len(fake_leetcode.calls)
    leetcode.problem("two-sum")
    assert len(fake_leetcode.calls) == count


@pytest.mark.parametrize("slug, message", [
    ("no-cpp-graph", "沒有 cpp 的程式範本"),
    ("paid-graph", "付費"),
    ("does-not-exist", "不存在"),
])
def test_unusable_problems(fake_leetcode, slug, message):
    with pytest.raises(leetcode.LeetCodeError, match=message):
        leetcode.problem(slug)


def test_statement_markup_is_sanitized(fake_leetcode):
    page = leetcode.problem("reverse-linked-list").content_html
    assert "<script" not in page and "alert(1)" not in page
    assert "onerror" not in page and "javascript:" not in page
    assert '<img src="https://assets.leetcode.com/a.png"' in page
    assert page.startswith("<p>Reverse it.</p>")


def test_sanitize_keeps_formatting_and_escapes_text():
    assert leetcode.sanitize('<p class="x">a &lt; b <code>x</code> <a href="javascript:x">link</a></p>') == (
        "<p>a &lt; b <code>x</code> link</p>")
    assert leetcode.sanitize("<pre>1 &lt;= n</pre><sup>4</sup>") == "<pre>1 &lt;= n</pre><sup>4</sup>"


def test_html_to_text():
    html = ("<p>Given&nbsp;<code>nums</code>.</p>\n<p><strong>Constraints:</strong></p>\n<ul>\n"
            "<li><code>1 &lt;= n &lt;= 10<sup>4</sup></code></li>\n<li>x</li>\n</ul><img src='a.png'>")
    assert leetcode.html_to_text(html) == "Given nums.\n\nConstraints:\n\n- 1 <= n <= 10^4\n- x\n[figure]"


def test_a_page_that_is_not_json_is_a_leetcode_error(monkeypatch):
    monkeypatch.setattr(leetcode, "_request", lambda *args, **kwargs: b"<html>Just a moment...</html>")
    with pytest.raises(leetcode.LeetCodeError, match="leetcode.com"):
        leetcode._graphql("query { x }", {})


def test_concurrent_cache_refreshes_do_not_collide(dirs):
    import threading
    errors = []

    def refresh(n):
        try:
            leetcode._cached("shared.json", 0, lambda: {"n": n})
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=refresh, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert not list(leetcode.CACHE_DIR.glob("*.tmp"))
