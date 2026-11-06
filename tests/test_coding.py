"""Coding interviews: picking LeetCode problems, the interviewer and feedback prompts, history, and the setup
and notepad pages' API. The network is faked (see fake_leetcode in conftest.py)."""

import asyncio
import json
import random
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import bot
from interviewer import coding
from interviewer import feedback
from interviewer import history
from interviewer import leetcode
from interviewer import server
from interviewer.server import ActiveSession, Selection
from interviewer.transcript import Transcript, Turn, read_transcript

ALL = ["easy", "medium", "hard"]


def problem(pid, title=None, tags=("Graph",), hints=()):
    return leetcode.Problem(
        id=pid, number="7", title=title or pid.title(), difficulty="medium", tags=list(tags),
        content_html="<p>Do it.</p>", text=f"Statement of {pid}.\n\nExample 1:\nInput: x = 1\nOutput: 2",
        starter={"python": "class Solution:\n    pass\n", "cpp": "class Solution {};\n"}, hints=list(hints),
        rating=1650,
    )


def coding_transcript(interview, problems, shown=1, stamp=None):
    """A saved coding session that showed the first `shown` of `problems`."""
    t = Transcript(interview, "T", session={"mode": "coding", "language": "python", "difficulties": ["medium"],
                                             "tags": [], "rating": None, "minutes": 45, "problems": problems})
    t.add("Interviewer", "Hi, the first problem is on your screen.")
    for n in range(2, shown + 1):
        t.add("Interviewer", coding.SHOWN_LINE.format(number=n, title=problems[n - 1]))
    if stamp:
        t.path.rename(t.path.with_name(f"{stamp}-transcript.md"))
    return t


# ----- Picking problems -----

def test_pick_problems_matches_the_filters(dirs, fake_leetcode):
    for seed in range(10):
        first, backup = coding.pick_problems("acme/hm", ["medium", "hard"], ["tree"], rng=random.Random(seed))
        assert {first, backup} == {"lowest-common-ancestor", "hard-tree"}


def test_pick_problems_skips_problems_without_a_template(dirs, fake_leetcode):
    for seed in range(10):
        picked = coding.pick_problems("acme/hm", ["medium"], ["graph"], [1600, 1700], rng=random.Random(seed))
        assert picked == ["is-graph-bipartite"]  # no-cpp-graph matches but has no C++ template


def test_pick_problems_prefers_unseen_and_a_different_tag_for_the_backup(dirs, fake_leetcode):
    coding_transcript("acme/hm", ["number-of-islands", "two-sum"], shown=2, stamp="20261001-1000")
    coding_transcript("acme/hm", ["is-graph-bipartite", "hard-tree"], shown=1, stamp="20261002-1000")
    assert coding.done_problems("acme/hm") == ["number-of-islands", "two-sum", "is-graph-bipartite"]
    for seed in range(10):
        first, backup = coding.pick_problems("acme/hm", ["medium"], ["graph", "tree"], rng=random.Random(seed))
        assert first == "lowest-common-ancestor"  # the only medium graph/tree problem not done yet
        assert backup in ("number-of-islands", "is-graph-bipartite")


def test_pick_problems_backup_avoids_the_first_problems_tags(dirs, fake_leetcode):
    for seed in range(10):
        first, backup = coding.pick_problems("acme/hm", ["easy"], rng=random.Random(seed))
        assert {first, backup} == {"two-sum", "reverse-linked-list"}


def test_pick_problems_interview_problems_only(dirs, fake_leetcode):
    for seed in range(10):
        picked = coding.pick_problems("acme/hm", ["easy"], ["math"], interview_only=False, rng=random.Random(seed))
        assert picked == ["divisor-game"]
    with pytest.raises(leetcode.LeetCodeError, match="只出面試常見題"):
        coding.pick_problems("acme/hm", ["easy"], ["math"])


def test_pick_problems_with_nothing_matching(dirs, fake_leetcode):
    with pytest.raises(leetcode.LeetCodeError, match="沒有符合條件的題目"):
        coding.pick_problems("acme/hm", ["hard"], ["graph"])


def test_pick_problems_offline(dirs):
    with pytest.raises(leetcode.LeetCodeError, match="offline"):
        coding.pick_problems("acme/hm", ALL)


def test_shown_count():
    assert coding.shown_count([]) == 1
    turns = [Turn("Interviewer", "Hi"), Turn("Interviewer", coding.SHOWN_LINE.format(number=2, title="X"))]
    assert coding.shown_count(turns) == 2
    assert coding.shown_count([Turn("Candidate", coding.SHOWN_LINE.format(number=2, title="X"))]) == 1


def test_filters_and_label():
    session = {"difficulties": ["medium", "hard"], "tags": ["graph", "tree"], "rating": [1600, None]}
    assert coding.filters(session) == (["medium", "hard"], ["graph", "tree"], [1600, None], True)
    assert coding.filters({}) == (ALL, [], None, True)
    assert coding.filters_label(session) == "Medium/Hard, graph, tree, rating 1600-"
    assert coding.filters_label({**session, "interview_only": False}).endswith("rating 1600-, any problem")


# ----- Prompts -----

def test_session_mode_for_coding(dirs, fake_leetcode):
    session = {"mode": "coding", "language": "cpp", "minutes": 45,
               "problems": ["number-of-islands", "is-graph-bipartite"]}
    text = bot.session_mode(session, 45)
    assert text.startswith("This is a LeetCode-style coding interview of about 45 minutes.")
    assert "writes C++" in text and "integer overflow in C++" in text
    assert "Prepare silently" in text and "ladder of three hints" in text
    assert "[[NEXT]]" in text and f"at least {coding.SECOND_PROBLEM_MIN_LEFT} minutes left" in text
    assert '<problem number="1" status="already on the candidate\'s screen">' in text
    assert "Problem 1: Number Of Islands (LeetCode #200, medium)" in text
    assert "LeetCode's own hints:\n1. Flood fill." in text
    assert "Problem 2: Is Graph Bipartite (LeetCode #785, medium, rating 1625)" in text
    assert "LeetCode's own hints:\n(LeetCode lists none)" in text
    assert '<problem number="2" status="backup, not shown yet' in text
    assert bot.session_mode(session, 45, shown=2).count("already on the candidate's screen") == 2


def test_session_mode_with_one_problem(dirs, fake_leetcode):
    text = bot.session_mode({"mode": "coding", "language": "python", "problems": ["two-sum"]}, 30)
    assert "Never write [[NEXT]]" not in text and "only one problem" in text


def test_session_mode_short_session(dirs, fake_leetcode):
    session = {"mode": "coding", "language": "python", "minutes": 15,
               "problems": ["number-of-islands", "is-graph-bipartite"]}
    text = bot.session_mode(session, 15)
    assert "too short for a second problem" in text and "leave out the candidate's questions" in text
    assert "one problem on their screen" in text and "one or two problems" not in text
    assert "Problem 1: Number Of Islands" in text and "Is Graph Bipartite" not in text
    assert "candidate's questions about the team or the work" in bot.session_mode(session, 30)


def test_time_checks_coding():
    assert "Do not start another problem" in bot.time_checks(45, coding=True)[1][1]
    assert bot.time_checks(45, coding=True)[1][1].endswith("move on to the candidate's questions.")
    assert bot.time_checks(15, coding=True)[1][1].endswith("then close.")


@pytest.mark.parametrize("text, expected, nexted, ended", [
    ("Let's try another one, it's on your screen. [[NEXT]]", "Let's try another one, it's on your screen. ", True, False),
    ("That's all for today, bye! [[END]]", "That's all for today, bye! ", False, True),
    ("Okay, keep going.", "Okay, keep going.", False, False),
])
def test_end_token_filter_next(text, expected, nexted, ended):
    nexts, ends = [], []
    f = bot.EndTokenFilter(lambda: ends.append(1), lambda: nexts.append(1))
    assert asyncio.run(f.filter(text)) == expected
    assert bool(nexts) == nexted and bool(ends) == ended


def test_selection_session_coding():
    s = Selection(Path("."), mode="coding", minutes=45, language="cpp", difficulties=["hard"], tags=["graph"],
                  rating=[1600, 1900], problems=["a", "b"])
    assert s.session() == {"mode": "coding", "language": "cpp", "difficulties": ["hard"], "tags": ["graph"],
                           "rating": [1600, 1900], "interview_only": True, "statement": "interview", "minutes": 45,
                           "problems": ["a", "b"]}
    assert Selection(Path("."), mode="coding", minutes=30).session()["difficulties"] == ALL
    assert "problems" not in Selection(Path("."), mode="coding", minutes=30).session()


# ----- The session on screen -----

PROBLEMS = [problem("a", "Alpha"), problem("b", "Beta"), problem("c", "Gamma")]
SESSION = {"mode": "coding", "language": "python", "problems": ["a", "b"]}


def test_coding_session_moves_to_the_next_problem():
    state = coding.CodingSession(SESSION, [], PROBLEMS[:2])
    view = state.view()
    assert (view["id"], view["number"], view["count"], view["leetcode_number"]) == ("a", 1, 2, "7")
    assert view["url"] == "https://leetcode.com/problems/a/" and view["html"] == "<p>Do it.</p>"

    assert state.update_code("x = 1", "a").startswith("[notepad] The candidate's Python code for problem 1 now reads:")
    snapshot, line, note = state.next_problem()
    assert snapshot == "[Notepad: final Python code for problem 1, Alpha]\n```python\nx = 1\n```"
    assert line == "[Problem 2 is now on the candidate's screen: Beta]"
    assert "Problem 2 is now on the candidate's screen" in note
    assert (state.shown, state.current.id, state.code) == (2, "b", "")


def test_a_short_session_never_moves_to_the_backup_problem():
    state = coding.CodingSession({**SESSION, "minutes": 15}, [], PROBLEMS[:2])
    assert state.next_problem() is None and state.shown == 1
    assert coding.CodingSession({**SESSION, "minutes": 30}, [], PROBLEMS[:2]).next_problem()


def test_coding_session_moves_once_per_answer():
    state = coding.CodingSession(SESSION, [], PROBLEMS)
    assert state.next_problem()
    assert state.next_problem() is None  # the TTS filter and the end of the turn saw the same [[NEXT]]
    state.answered()
    assert state.next_problem() and state.shown == 3
    state.answered()
    assert state.next_problem() is None


def test_coding_session_ignores_stale_and_unchanged_saves():
    state = coding.CodingSession(SESSION, [], PROBLEMS[:2])
    assert state.update_code("x = 1") is not None
    assert state.update_code("x = 1 ", "a") is None
    state.next_problem()
    assert state.update_code("late edit to problem 1", "a") is None
    assert state.final_snapshot() is None
    state.update_code("y = 2", "b")
    assert state.final_snapshot().startswith("[Notepad: final Python code for problem 2, Beta]")


def test_coding_session_resumes_on_the_problem_it_reached():
    turns = [Turn("Interviewer", coding.SHOWN_LINE.format(number=2, title="Beta"))]
    assert coding.CodingSession(SESSION, turns, PROBLEMS[:2]).current.id == "b"
    gone = coding.CodingSession(SESSION, turns, [])
    assert gone.current is None and gone.update_code("x") is None and gone.final_snapshot() is None


def test_coding_session_loads_its_problems_from_the_cache(dirs, fake_leetcode):
    state = coding.CodingSession({"mode": "coding", "problems": ["two-sum", "hard-tree"]}, [])
    assert [p.id for p in state.problems] == ["two-sum", "hard-tree"]
    count = len(fake_leetcode.calls)
    coding.CodingSession({"mode": "coding", "problems": ["two-sum", "hard-tree"]}, [])
    assert len(fake_leetcode.calls) == count


# ----- Feedback and history -----

def test_feedback_for_coding(dirs, fake_leetcode):
    t = coding_transcript("acme/hm", ["number-of-islands", "two-sum"], shown=1)
    saved = read_transcript(t.path)
    saved.elapsed_secs = 40 * 60
    info = feedback.session_info(saved)
    assert info.startswith("a LeetCode-style coding interview in Python, planned for 45 minutes, about 40 minutes used.")
    assert "Problem 1: Number Of Islands (LeetCode #200, medium)" in info
    assert "Two Sum" not in info  # the backup was never shown
    assert "clean optimal reference solution in Python" in info
    assert feedback.session_rubric(None, saved) == coding.rubric()


def test_a_round_can_use_its_own_coding_rubric(dirs, make_round, fake_leetcode):
    from interviewer.config import InterviewConfig
    round_dir = make_round("acme", "hm")
    (round_dir / "prompts").mkdir()
    (round_dir / "prompts" / "coding_rubric.md").write_text("## Speed\n- 5: fast\n\n## Clarity\n- 5: clear", encoding="utf-8")
    cfg = InterviewConfig.load(round_dir)
    saved = read_transcript(coding_transcript("acme/hm", ["number-of-islands"], shown=1).path)
    assert feedback.session_rubric(cfg, saved).startswith("## Speed")
    plain = InterviewConfig.load(make_round("beta", "hm"))
    assert feedback.session_rubric(plain, saved) == coding.rubric()


def scored(dirs, interview, stamp, session, scores):
    folder = dirs.transcripts / interview
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stamp}-transcript.md"
    path.write_text(f"# T\n\n<!-- session: {json.dumps(session)} -->\n\n**Interviewer:** Hi\n\n", encoding="utf-8")
    (folder / f"{stamp}-scores.json").write_text(json.dumps(scores), encoding="utf-8")


CODING = {"mode": "coding", "language": "cpp", "difficulties": ["medium", "hard"], "tags": ["graph"], "rating": None}


def test_coding_sessions_stay_out_of_the_interview_history(dirs):
    scored(dirs, "acme/hm", "20261001-1000", {"mode": "full"},
           {"verdict": "lean no", "weaknesses": [{"topic": "STAR"}], "next_focus": ["behavioral stories"]})
    scored(dirs, "acme/hm", "20261002-1000", CODING,
           {"verdict": "lean hire", "weaknesses": [{"topic": "testing"}], "next_focus": ["dry-run the code"]})
    assert history.drill_suggestions("acme/hm") == ["behavioral stories"]
    notes = history.practice_history("acme/hm")
    assert "1 scored practice session(s)" in notes and "testing" not in notes
    coding_notes = history.coding_history("acme/hm")
    assert "(C++, Medium/Hard, graph), verdict lean hire. Weak spots: testing" in coding_notes
    assert "dry-run the code" in coding_notes and "behavioral" not in coding_notes


def test_coding_history_first_session(dirs):
    assert history.coding_history("acme/hm") == "This is the candidate's first scored coding practice session."


# ----- Setup and notepad pages -----

@pytest.fixture
def client(make_round, dirs, monkeypatch):
    make_round("acme", "hm")
    # The interview list shows resume paths relative to the project folder; here that is tmp_path.
    monkeypatch.setattr(server, "ROOT", dirs.root)
    monkeypatch.setattr(server, "selection", None)
    monkeypatch.setattr(server, "active", None)
    app = FastAPI()
    server.register(app)
    return TestClient(app, base_url="http://localhost")


CHOICE = {"interview": "acme/hm", "mode": "coding", "language": "cpp", "minutes": 60,
          "difficulties": ["medium", "hard"], "tags": ["tree"]}


def test_coding_options(client, fake_leetcode):
    o = client.get("/api/coding/options").json()
    assert o["languages"] == coding.LANGUAGES and o["difficulties"] == ALL
    assert o["tags"][0] == {"slug": "graph", "name": "Graph", "count": 4}
    assert o["rating"] == {"min": 1200, "max": 2100, "count": 5}


def test_coding_options_offline(client):
    r = client.get("/api/coding/options")
    assert r.status_code == 502 and "offline" in r.json()["detail"]


def test_coding_match(client, fake_leetcode):
    m = client.post("/api/coding/match", json={"difficulties": ["medium", "hard"], "tags": ["tree"]}).json()
    assert m["count"] == 2 and {s["title"] for s in m["sample"]} == {"Lowest Common Ancestor", "Hard Tree"}
    m = client.post("/api/coding/match", json={"difficulties": ALL, "rating_min": 1650}).json()
    assert m["count"] == 3
    m = client.post("/api/coding/match", json={"difficulties": ["medium"], "tags": ["graph"]}).json()
    assert m["count"] == 3  # interview problems only by default: disliked-graph is left out
    m = client.post("/api/coding/match", json={"difficulties": ["medium"], "tags": ["graph"], "interview_only": False})
    assert m.json()["count"] == 4


def test_choose_a_coding_interview_picks_the_problems(client, fake_leetcode):
    r = client.post("/api/selection", json={**CHOICE, "rating_min": 1650, "rating_max": None})
    assert r.status_code == 200
    s = server.selection
    assert (s.mode, s.language, s.difficulties, s.tags, s.rating, s.minutes) == (
        "coding", "cpp", ["medium", "hard"], ["tree"], [1650, None], 60)
    assert set(s.problems) == {"lowest-common-ancestor", "hard-tree"} and r.json()["problems"] == s.problems
    selected = client.get("/api/interviews").json()["selected"]
    assert selected["difficulties"] == ["medium", "hard"] and selected["rating"] == [1650, None]
    assert s.interview_only and selected["interview_only"] is True


def test_choose_a_coding_interview_with_any_problem(client, fake_leetcode):
    r = client.post("/api/selection", json={**CHOICE, "difficulties": ["easy"], "tags": ["math"],
                                            "interview_only": False})
    assert r.status_code == 200 and r.json()["problems"] == ["divisor-game"]
    assert server.selection.session()["interview_only"] is False
    r = client.post("/api/selection", json={**CHOICE, "difficulties": ["easy"], "tags": ["math"]})
    assert r.status_code == 400 and "只出面試常見題" in r.json()["detail"]


@pytest.mark.parametrize("change, message", [
    ({"language": "rust"}, "程式語言"),
    ({"difficulties": []}, "難度至少要選一個"),
    ({"difficulties": ["brutal"]}, "難度至少要選一個"),
    ({"rating_min": 2000, "rating_max": 1500}, "下限不能大於上限"),
    ({"rating_min": 9000}, "0 到 4000"),
    ({"minutes": 5}, "15 到 120"),
    ({"difficulties": ["hard"], "tags": ["graph"]}, "沒有符合條件的題目"),
])
def test_coding_selection_is_validated(client, fake_leetcode, change, message):
    r = client.post("/api/selection", json={**CHOICE, **change})
    assert r.status_code == 400 and message in r.json()["detail"]
    assert server.selection is None


def test_choose_a_coding_interview_offline(client):
    r = client.post("/api/selection", json=CHOICE)
    assert r.status_code == 400 and "offline" in r.json()["detail"]


def test_coding_view_and_notepad(client, dirs, monkeypatch):
    assert client.get("/api/coding").json() == {"active": False}
    notes = []

    async def noop():
        pass

    state = coding.CodingSession(SESSION, [], PROBLEMS[:2])
    monkeypatch.setattr(server, "active", ActiveSession(
        interview="acme/hm", transcript=dirs.transcripts / "acme/hm/20261029-1000-transcript.md",
        session=SESSION, minutes=45, elapsed=lambda: 0.0, is_paused=lambda: False, pause=noop,
        resume=noop, end=noop, update_notepad=lambda text, problem=None: notes.append((text, problem)),
        coding=state.view,
    ))
    j = client.get("/api/coding").json()
    assert j["active"] and j["id"] == "a" and j["file"] == "20261029-1000-transcript.md"
    assert j["html"] == "<p>Do it.</p>" and j["starter"] == "class Solution:\n    pass\n"
    assert client.post("/api/notepad", json={"text": "def f(): pass", "problem": "a"}).status_code == 200
    assert notes == [("def f(): pass", "a")]


def test_progress_separates_coding_sessions(client, dirs):
    scored(dirs, "acme/hm", "20261001-1000", {"mode": "full"}, {"verdict": "lean no"})
    scored(dirs, "acme/hm", "20261002-1000", CODING, {"verdict": "hire"})
    interview = client.get("/api/progress", params={"interview": "acme/hm"}).json()
    assert [s["verdict"] for s in interview["sessions"]] == ["lean no"] and interview["coding_sessions"] == 1
    coded = client.get("/api/progress", params={"interview": "acme/hm", "kind": "coding"}).json()
    assert [s["verdict"] for s in coded["sessions"]] == ["hire"]
    assert coded["areas"] == ["釐清問題", "解題思路", "程式實作", "溝通表達", "測試與除錯", "複雜度分析"]
