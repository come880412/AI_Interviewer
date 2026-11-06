"""Shared fixtures. Every test runs against folders under tmp_path, never the real interviews/,
profile/ or transcripts/ folders, and nothing here calls Claude or loads a speech model."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from interviewer import coding  # noqa: E402
from interviewer import history  # noqa: E402
from interviewer import config as interview_config  # noqa: E402
from interviewer import leetcode  # noqa: E402
from interviewer import transcript  # noqa: E402


@pytest.fixture(autouse=True)
def dirs(tmp_path, monkeypatch):
    """Points every module-level folder constant into tmp_path."""
    interviews = tmp_path / "interviews"
    profile = tmp_path / "profile"
    transcripts = tmp_path / "transcripts"
    for d in (interviews, profile, transcripts):
        d.mkdir()

    monkeypatch.setattr(interview_config, "INTERVIEWS_DIR", interviews)
    monkeypatch.setattr(interview_config, "PROFILE_DIR", profile)
    monkeypatch.setitem(interview_config.SHARED_FILES, "resume", profile / "resume.md")
    # TRANSCRIPTS_DIR is imported by name into several modules; patch each module's own reference.
    for module in (transcript, history, interview_config, coding):
        monkeypatch.setattr(module, "TRANSCRIPTS_DIR", transcripts)
    # Never touch the network or the real LeetCode cache; tests that need responses fake leetcode._request.
    monkeypatch.setattr(leetcode, "CACHE_DIR", tmp_path / "leetcode-cache")

    def offline(url, body=None, timeout=30):
        raise leetcode.LeetCodeError("offline in tests")

    monkeypatch.setattr(leetcode, "_request", offline)

    async def no_claude(prompt, model):
        raise RuntimeError("no Claude in tests")

    # Interview-style statements are written by Claude; tests that need a reply use fake_claude.
    monkeypatch.setattr(coding, "complete", no_claude)
    if "interviewer.server" in sys.modules:
        monkeypatch.setattr(sys.modules["interviewer.server"], "TRANSCRIPTS_DIR", transcripts)
        monkeypatch.setattr(sys.modules["interviewer.server"], "INTERVIEWS_DIR", interviews)

    monkeypatch.delenv("INTERVIEW", raising=False)
    # resolve_interview also tries the name as a path relative to the working directory.
    monkeypatch.chdir(tmp_path)
    return SimpleNamespace(root=tmp_path, interviews=interviews, profile=profile, transcripts=transcripts)


def _question(slug, number, difficulty, tags, cpp=True, paid=False, hints=(), content=None, likes=1000, dislikes=50):
    snippets = [{"langSlug": "python3", "code": f"class Solution:\n    def solve(self):\n        "}]
    if cpp:
        snippets.append({"langSlug": "cpp", "code": "class Solution {\npublic:\n    int solve() {\n        \n    }\n};"})
    return {
        "questionFrontendId": str(number), "title": slug.replace("-", " ").title(), "titleSlug": slug,
        "difficulty": difficulty, "isPaidOnly": paid, "hints": list(hints), "likes": likes, "dislikes": dislikes,
        "content": content or f"<p>Solve <code>{slug}</code>.</p><pre><strong>Input:</strong> x = 1\n<strong>Output:</strong> 2</pre>",
        "topicTags": [{"name": t.replace("-", " ").title(), "slug": t} for t in tags], "codeSnippets": snippets,
    }


# A small stand-in for LeetCode: graph/tree/linked-list problems at every difficulty, a paid one, one without a
# C++ template, a statement with markup that must be stripped, and for "interview problems only" a puzzle, a
# disliked problem, a plain counting problem (all left out) and a popular classic with generic tags (kept).
FAKE_QUESTIONS = [
    _question("number-of-islands", 200, "Medium", ["graph", "breadth-first-search"], hints=["<p>Flood fill.</p>"]),
    _question("is-graph-bipartite", 785, "Medium", ["graph"]),
    _question("lowest-common-ancestor", 236, "Medium", ["tree"]),
    _question("two-sum", 1, "Easy", ["array", "hash-table"]),
    _question("hard-tree", 2000, "Hard", ["tree"]),
    _question("paid-graph", 300, "Medium", ["graph"], paid=True),
    _question("no-cpp-graph", 400, "Medium", ["graph"], cpp=False),
    _question("reverse-linked-list", 206, "Easy", ["linked-list"],
              content='<p>Reverse it.</p><script>alert(1)</script><img src="https://assets.leetcode.com/a.png" '
                      'onerror="alert(2)"><img src="javascript:alert(3)">'),
    _question("divisor-game", 1025, "Easy", ["math", "brainteaser", "game-theory"], likes=2503, dislikes=4214),
    _question("disliked-graph", 500, "Medium", ["graph"], likes=100, dislikes=400),
    _question("count-letters", 600, "Medium", ["string", "counting"]),
    _question("spiral-matrix", 54, "Medium", ["array", "matrix"], likes=18018, dislikes=1500),
]
FAKE_RATINGS = [
    {"TitleSlug": "is-graph-bipartite", "Rating": 1625.4},
    {"TitleSlug": "lowest-common-ancestor", "Rating": 1700.0},
    {"TitleSlug": "hard-tree", "Rating": 2100.2},
    {"TitleSlug": "no-cpp-graph", "Rating": 1650.0},
    {"TitleSlug": "reverse-linked-list", "Rating": 1200.0},
]


@pytest.fixture
def fake_leetcode(monkeypatch):
    """Answers leetcode._request from FAKE_QUESTIONS and FAKE_RATINGS. calls records every request."""
    import json

    calls = []

    def request(url, body=None, timeout=30):
        calls.append((url, body))
        if url == leetcode.RATINGS_URL:
            return json.dumps(FAKE_RATINGS).encode()
        query, variables = body["query"], body["variables"]
        if "questionList" in query:
            page = FAKE_QUESTIONS[variables["skip"]: variables["skip"] + variables["limit"]]
            keys = ("questionFrontendId", "title", "titleSlug", "difficulty", "isPaidOnly", "likes", "dislikes",
                    "topicTags")
            data = {"totalNum": len(FAKE_QUESTIONS), "data": [{k: q[k] for k in keys} for q in page]}
            return json.dumps({"data": {"questionList": data}}).encode()
        match = next((q for q in FAKE_QUESTIONS if q["titleSlug"] == variables["titleSlug"]), None)
        return json.dumps({"data": {"question": match}}).encode()

    monkeypatch.setattr(leetcode, "_request", request)
    monkeypatch.setattr(leetcode, "PAGE_SIZE", 3)  # several pages, as with the real list
    return SimpleNamespace(calls=calls)


@pytest.fixture
def fake_claude(monkeypatch):
    """Answers coding's Claude calls with fake_claude.reply; prompts records every prompt."""
    state = SimpleNamespace(reply="", prompts=[])

    async def complete(prompt, model):
        state.prompts.append(prompt)
        return state.reply

    monkeypatch.setattr(coding, "complete", complete)
    return state


def write_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


COMPANY = {"company": "Acme", "role_title": "ML Engineer", "stt_hotwords": ["TensorRT", "ONNX"]}
ROUND = {"interviewer_name": "Dana", "interviewer_title": "Hiring Manager", "round_name": "HM round"}


@pytest.fixture
def make_round(dirs):
    """make_round("acme", "hm", company={...}, config={...}, files={"jd.md": "..."}, company_files={...})
    creates interviews/acme/company.yaml (unless company is None) and interviews/acme/hm/config.yaml."""

    def make(company_slug, round_slug, company=COMPANY, config=ROUND, files=None, company_files=None):
        company_dir = dirs.interviews / company_slug
        company_dir.mkdir(parents=True, exist_ok=True)
        if company is not None:
            write_yaml(company_dir / "company.yaml", company)
        for name, text in (company_files or {}).items():
            (company_dir / name).write_text(text, encoding="utf-8")
        round_dir = company_dir / round_slug
        write_yaml(round_dir / "config.yaml", config)
        for name, text in (files or {}).items():
            (round_dir / name).write_text(text, encoding="utf-8")
        return round_dir

    return make
