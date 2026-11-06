"""Interview-style problem statements: Claude's rewrite and its cache, the cut-down fallback, and how the
interviewer prompt, the notepad page and the report use them. Claude and the network are faked."""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import bot
from interviewer import coding
from interviewer import leetcode
from interviewer import server
from interviewer.transcript import Transcript, read_transcript

ISLANDS = leetcode.Problem(
    id="number-of-islands", number="200", title="Number of Islands", difficulty="medium", tags=["Graph"],
    content_html="<p>Full statement.</p>",
    text=("Given an m x n 2D binary grid grid which represents a map of '1's (land) and '0's (water), return the "
          "number of islands. You may assume all four edges of the grid are all surrounded by water.\n\n"
          "Example 1:\n\nInput: grid = [[\"1\",\"0\"],[\"0\",\"1\"]]\nOutput: 2\n\n"
          "Example 2:\n\nInput: grid = [[\"1\"]]\nOutput: 1\nExplanation: One island.\n\n"
          "Constraints:\n\n- m == grid.length\n- 1 <= m, n <= 300\n\n"
          "Follow-up: Can you do it\nwithout extra space?"),
    starter={"python": "class Solution:\n    def numIslands(self, grid: List[List[str]]) -> int:\n        \n",
             "cpp": "class Solution {};\n"},
)
REWRITE = {
    "statement": "Given a grid of land and water, count the islands in grid.",
    "examples": [{"input": "grid = [[\"1\",\"0\"],[\"0\",\"1\"]]", "output": "2", "explanation": ""}],
    "left_out": ["1 <= m, n <= 300", "Cells connect horizontally or vertically, not diagonally",
                 "The grid's edges are surrounded by water"],
}
INTERVIEW = {"mode": "coding", "language": "python", "statement": "interview", "minutes": 45,
             "problems": ["number-of-islands", "is-graph-bipartite"]}


def test_cut_down_statement():
    s = coding.cut_down_statement(ISLANDS)
    assert s.statement.startswith("Given an m x n 2D binary grid") and "Example" not in s.statement
    assert s.examples == [{"input": 'grid = [["1","0"],["0","1"]]', "output": "2", "explanation": ""},
                          {"input": 'grid = [["1"]]', "output": "1", "explanation": "One island."}]
    assert s.left_out == ["m == grid.length", "1 <= m, n <= 300", "Follow-up: Can you do it without extra space?"]
    assert not s.rewritten
    assert "Constraints" not in s.text and "300" not in s.html


def test_statement_html_is_escaped():
    s = coding.InterviewStatement("Use <b>a</b> & b.", [{"input": "s = \"<\"", "output": "1"}], [], True)
    assert s.html == ("<p>Use &lt;b&gt;a&lt;/b&gt; &amp; b.</p><p><strong>Example:</strong></p><pre><strong>"
                      "Input:</strong> s = &quot;&lt;&quot;\n<strong>Output:</strong> 1</pre>")
    assert s.text == 'Use <b>a</b> & b.\n\nExample:\nInput: s = "<"\nOutput: 1'


def test_two_examples_are_numbered_and_explained():
    s = coding.InterviewStatement("Count.", [{"input": "a", "output": "1", "explanation": "One <a>."},
                                             {"input": "b", "output": "2", "explanation": ""}], [], True)
    assert "<strong>Example 1:</strong>" in s.html and "<strong>Example 2:</strong>" in s.html
    assert "<strong>Explanation:</strong> One &lt;a&gt;.</pre>" in s.html
    assert s.text == ("Count.\n\nExample 1:\nInput: a\nOutput: 1\nExplanation: One <a>.\n\n"
                      "Example 2:\nInput: b\nOutput: 2")


def test_prepare_statements_asks_claude_once_and_caches(fake_leetcode, fake_claude):
    fake_claude.reply = "Here it is:\n" + json.dumps(REWRITE)
    asyncio.run(coding.prepare_statements(["number-of-islands"]))
    prompt = fake_claude.prompts[0]
    assert "def solve(self):" in prompt and "Solve <code>" not in prompt and "Solve number-of-islands." in prompt
    s = coding.interview_statement(leetcode.problem("number-of-islands"))
    assert s.rewritten and s.statement == REWRITE["statement"] and s.left_out == REWRITE["left_out"]
    asyncio.run(coding.prepare_statements(["number-of-islands"]))
    assert len(fake_claude.prompts) == 1


def test_a_rewrite_from_the_older_prompt_is_written_again(fake_leetcode, fake_claude):
    path = leetcode.CACHE_DIR / "statements" / "number-of-islands.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"statement": "Old one.", "example": {"input": "x", "output": "1"}, "left_out": []}))
    old = coding.interview_statement(leetcode.problem("number-of-islands"))
    assert old.statement == "Old one." and old.examples == [{"input": "x", "output": "1", "explanation": ""}]
    fake_claude.reply = "{not json}"  # a failed rewrite keeps the old one
    asyncio.run(coding.prepare_statements(["number-of-islands"]))
    assert coding.interview_statement(leetcode.problem("number-of-islands")).statement == "Old one."
    fake_claude.reply = json.dumps(REWRITE)
    asyncio.run(coding.prepare_statements(["number-of-islands"]))
    assert len(fake_claude.prompts) == 2
    assert json.loads(path.read_text())["version"] == coding.STATEMENT_VERSION
    assert coding.interview_statement(leetcode.problem("number-of-islands")).statement == REWRITE["statement"]


@pytest.mark.parametrize("reply", ["Sorry, I can't.", '{"statement": "", "left_out": []}', "{not json}"])
def test_a_failed_rewrite_falls_back_to_the_cut_down_statement(fake_leetcode, fake_claude, reply):
    fake_claude.reply = reply
    asyncio.run(coding.prepare_statements(["number-of-islands"]))
    assert not (leetcode.CACHE_DIR / "statements" / "number-of-islands.json").exists()
    assert not coding.interview_statement(leetcode.problem("number-of-islands")).rewritten


def test_without_claude_the_statement_is_cut_down(fake_leetcode):
    asyncio.run(coding.prepare_statements(["number-of-islands"]))  # conftest makes Claude unavailable
    assert not coding.interview_statement(leetcode.problem("number-of-islands")).rewritten


def test_statement_style():
    assert coding.statement_style({"statement": "interview"}) == "interview"
    assert coding.statement_style({}) == "leetcode"  # sessions from before the choice
    assert coding.statement_style({"statement": "odd"}) == "leetcode"


def rewritten(fake_claude):
    fake_claude.reply = json.dumps(REWRITE)
    asyncio.run(coding.prepare_statements(["number-of-islands"]))


def test_interviewer_prompt_for_interview_style(fake_leetcode, fake_claude):
    rewritten(fake_claude)
    text = bot.session_mode(INTERVIEW, 45)
    assert "deliberately underspecified" in text and "expected to ask about what the screen leaves out" in text
    assert "they can ask you anything about the problem" in text
    assert "On the candidate's screen, and nothing else:\nGiven a grid of land and water" in text
    assert "Left out on purpose (answer truthfully when asked, never volunteer):\n- 1 <= m, n <= 300" in text
    assert "LeetCode's full statement, for you only:\nSolve number-of-islands." in text
    # The backup has no rewrite, so its brief uses the cut-down statement.
    assert "Problem 2: Is Graph Bipartite" in text


def test_interviewer_prompt_for_leetcode_style(fake_leetcode):
    text = bot.session_mode({**INTERVIEW, "statement": "leetcode"}, 45)
    assert "exactly as LeetCode publishes them" in text and "underspecified" not in text
    assert "On the candidate's screen" not in text


def test_notepad_view_for_interview_style(fake_leetcode, fake_claude):
    rewritten(fake_claude)
    view = coding.CodingSession(INTERVIEW, []).view()
    assert view["statement"] == "interview" and view["title"] == "Number Of Islands"
    assert view["html"].startswith("<p>Given a grid of land and water, count the islands in grid.</p>")
    assert not {"tags", "rating", "url", "difficulty", "leetcode_number"} & set(view)
    leetcode_view = coding.CodingSession({**INTERVIEW, "statement": "leetcode"}, []).view()
    assert leetcode_view["statement"] == "leetcode" and leetcode_view["tags"] == ["Graph", "Breadth First Search"]


def test_feedback_for_interview_style(dirs, fake_leetcode, fake_claude):
    rewritten(fake_claude)
    t = Transcript("acme/hm", "T", session=INTERVIEW)
    t.add("Interviewer", "Hi, the first problem is on your screen.")
    info = coding.feedback_session_info(read_transcript(t.path).session, [], 30)
    assert "What the candidate saw:\nGiven a grid of land and water" in info
    assert "Left out, for the candidate to ask about:\n- 1 <= m, n <= 300" in info
    assert "Score 釐清問題 by which of the left-out details" in info
    info = coding.feedback_session_info({**INTERVIEW, "statement": "leetcode"}, [], 30)
    assert "constraints included, was on the candidate's screen" in info and "What the candidate saw" not in info


@pytest.fixture
def client(make_round, dirs, monkeypatch):
    make_round("acme", "hm")
    monkeypatch.setattr(server, "ROOT", dirs.root)
    monkeypatch.setattr(server, "selection", None)
    monkeypatch.setattr(server, "active", None)
    app = FastAPI()
    server.register(app)
    return TestClient(app, base_url="http://localhost")


CHOICE = {"interview": "acme/hm", "mode": "coding", "language": "python", "minutes": 45,
          "difficulties": ["medium"], "tags": ["tree"]}


def test_choosing_an_interview_style_session_prepares_the_statement(client, fake_leetcode, fake_claude):
    fake_claude.reply = json.dumps({**REWRITE, "statement": "Find the lowest common ancestor."})
    r = client.post("/api/selection", json=CHOICE)
    assert r.status_code == 200 and r.json()["problems"] == ["lowest-common-ancestor"]
    assert server.selection.session()["statement"] == "interview"
    assert len(fake_claude.prompts) == 1
    assert (leetcode.CACHE_DIR / "statements" / "lowest-common-ancestor.json").exists()
    assert client.get("/api/interviews").json()["selected"]["statement"] == "interview"


def test_choosing_a_leetcode_style_session_skips_claude(client, fake_leetcode, fake_claude):
    r = client.post("/api/selection", json={**CHOICE, "statement": "leetcode"})
    assert r.status_code == 200 and not fake_claude.prompts
    assert server.selection.session()["statement"] == "leetcode"


def test_unknown_statement_style(client, fake_leetcode):
    r = client.post("/api/selection", json={**CHOICE, "statement": "vague"})
    assert r.status_code == 400 and "題目呈現方式" in r.json()["detail"]
