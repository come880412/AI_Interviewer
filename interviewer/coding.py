"""LeetCode-style coding interviews: picking problems from LeetCode (see leetcode.py) by difficulty, tag and
rating, and what the interviewer, the notepad page and the feedback report need to know about them.

A coding session's settings, including the problems picked for it, are saved in the transcript like any other
session:

    {"mode": "coding", "language": "python", "difficulties": ["medium", "hard"], "tags": ["graph", "tree"],
     "rating": [1600, 1900], "interview_only": true, "statement": "interview", "minutes": 45,
     "problems": ["is-graph-bipartite", "loud-and-rich"]}

interview_only (the default) keeps to interview-style problems; see leetcode.interview_style.

statement is how the problem is shown. "interview" (the default) shows a short, underspecified version, the
way an interviewer writes a problem in a shared document: the candidate has to ask about input sizes, edge
cases and guarantees, and the interviewer answers from LeetCode's full statement. Claude writes that version
once per problem (cached in ~/.cache/ai-interviewer/leetcode/statements/). "leetcode" shows LeetCode's own
statement, constraints included.

The first problem is on the candidate's screen from the start. The second is a backup that the interviewer
shows with [[NEXT]] when the first is done and there is time left.
"""

import asyncio
import html
import json
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from interviewer import settings  # loads .env before the settings below are read
from interviewer import leetcode
from interviewer.leetcode import LeetCodeError, Problem
from interviewer.llm import complete
from interviewer.transcript import TRANSCRIPTS_DIR, Turn, read_transcript, saved_transcripts

RUBRIC_PATH = settings.ROOT / "prompts" / "coding_rubric.md"
STATEMENT_PROMPT_PATH = settings.ROOT / "prompts" / "coding_statement.md"
STATEMENT_MODEL = os.getenv("FEEDBACK_MODEL", os.getenv("LLM_MODEL", "claude-opus-5-5"))
STATEMENT_STYLES = ("interview", "leetcode")
# Saved with each rewrite; a rewrite from an older prompt is written again the next time its problem is used.
STATEMENT_VERSION = 2

LANGUAGES = {"python": "Python", "cpp": "C++"}
DIFFICULTIES = ("easy", "medium", "hard")
# The interviewer only moves on to the second problem with at least this many minutes left.
SECOND_PROBLEM_MIN_LEFT = 15
# Sessions this short are one problem with no time for the candidate's questions at the end.
SHORT_SESSION_MINUTES = 20
# Written to the transcript when the interviewer shows the next problem; also how a resumed session
# knows which problem is on screen.
SHOWN_LINE = "[Problem {number} is now on the candidate's screen: {title}]"
SHOWN_PATTERN = re.compile(r"^\[Problem (\d+) is now on the candidate's screen")
# Candidates tried when a picked problem turns out to be unusable (no Python or C++ template, for example).
MAX_TRIES = 8


def is_coding(session: dict) -> bool:
    return session.get("mode") == "coding"


def shown_count(turns: list[Turn]) -> int:
    """How many of the session's problems the candidate has seen: the first, plus one per [[NEXT]]."""
    shown = [int(m.group(1)) for t in turns if t.speaker == "Interviewer" and (m := SHOWN_PATTERN.match(t.text))]
    return max([1, *shown])


def done_problems(interview: str) -> list[str]:
    """Problems this interview's earlier coding sessions showed, oldest first."""
    done: list[str] = []
    for saved in saved_transcripts(TRANSCRIPTS_DIR / interview):
        if not is_coding(saved.session):
            continue
        for problem_id in saved.session.get("problems", [])[: shown_count(saved.turns)]:
            if problem_id not in done:
                done.append(problem_id)
    return done


def filters(session: dict) -> tuple[list[str], list[str], list | None, bool]:
    """(difficulties, tags, rating range or None, interview problems only) of a coding session."""
    return (list(session.get("difficulties") or DIFFICULTIES), list(session.get("tags") or []),
            session.get("rating") or None, session.get("interview_only", True))


def pick_problems(interview: str, difficulties: list[str], tags: list[str] | None = None,
                  rating_range: list | None = None, interview_only: bool = True,
                  rng: random.Random | None = None) -> list[str]:
    """Two problem ids for a new session, fetched so they are cached: problems not done before come first,
    and the backup shares no tag with the first when it can. Raises LeetCodeError when nothing matches."""
    rng = rng or random.Random()
    candidates = leetcode.matching(difficulties, tags, rating_range, interview_only)
    if not candidates:
        raise LeetCodeError("沒有符合條件的題目，請放寬難度、題型、rating 範圍，或取消「只出面試常見題」。")
    done = set(done_problems(interview))
    rng.shuffle(candidates)
    candidates.sort(key=lambda p: p["id"] in done)  # stable: still shuffled within each group

    picked: list[dict] = []
    for p in candidates[:MAX_TRIES]:
        try:
            leetcode.problem(p["id"])
        except LeetCodeError:
            continue
        picked.append(p)
        break
    if not picked:
        raise LeetCodeError("抓不到可用的題目內容，請稍後再試。")
    first_tags = set(picked[0]["tags"])
    rest = [p for p in candidates if p["id"] != picked[0]["id"]]
    rest.sort(key=lambda p: (p["id"] in done, bool(set(p["tags"]) & first_tags)))
    for p in rest[:MAX_TRIES]:
        try:
            leetcode.problem(p["id"])
        except LeetCodeError:
            continue
        picked.append(p)
        break
    return [p["id"] for p in picked]


def session_problems(session: dict) -> list[Problem]:
    """The session's problems, from the cache (or LeetCode if the cache was cleared)."""
    problems = []
    for problem_id in session.get("problems", []):
        try:
            problems.append(leetcode.problem(problem_id))
        except LeetCodeError:
            pass
    return problems


def language_name(session: dict) -> str:
    return LANGUAGES.get(session.get("language"), "Python")


def code_fence(session: dict) -> str:
    return session.get("language") if session.get("language") in LANGUAGES else "python"


def statement_style(session: dict) -> str:
    # Sessions from before the choice existed showed LeetCode's statement.
    return session.get("statement") if session.get("statement") in STATEMENT_STYLES else "leetcode"


# ----- Interview-style statements -----

@dataclass
class InterviewStatement:
    """The short version of a problem the candidate sees, and what it leaves out."""
    statement: str
    examples: list[dict]  # {"input": ..., "output": ..., "explanation": ... (may be empty)}
    left_out: list[str]  # details of LeetCode's statement the candidate has to ask about
    rewritten: bool  # False: LeetCode's statement cut down without Claude

    def _example_name(self, i: int) -> str:
        return f"Example {i}:" if len(self.examples) > 1 else "Example:"

    @property
    def html(self) -> str:
        parts = [f"<p>{html.escape(line)}</p>" for line in self.statement.splitlines() if line.strip()]
        for i, ex in enumerate(self.examples, 1):
            explanation = (f"\n<strong>Explanation:</strong> {html.escape(ex['explanation'])}"
                           if ex.get("explanation") else "")
            parts.append(f"<p><strong>{self._example_name(i)}</strong></p><pre><strong>Input:</strong> "
                         f"{html.escape(ex['input'])}\n<strong>Output:</strong> {html.escape(ex['output'])}"
                         f"{explanation}</pre>")
        return "".join(parts)

    @property
    def text(self) -> str:
        parts = [self.statement]
        for i, ex in enumerate(self.examples, 1):
            explanation = f"\nExplanation: {ex['explanation']}" if ex.get("explanation") else ""
            parts.append(f"{self._example_name(i)}\nInput: {ex['input']}\nOutput: {ex['output']}{explanation}")
        return "\n\n".join(parts)


def _statement_path(problem_id: str) -> Path:
    return leetcode.CACHE_DIR / "statements" / f"{problem_id}.json"


def _parse_statement(data: dict) -> InterviewStatement:
    statement = str(data["statement"]).strip()
    if not statement:
        raise ValueError("empty statement")
    # Version 1 rewrites had a single "example".
    examples = data.get("examples") or ([data["example"]] if data.get("example") else [])
    examples = [{"input": str(ex["input"]).strip(), "output": str(ex["output"]).strip(),
                 "explanation": str(ex.get("explanation") or "").strip()} for ex in examples[:2]]
    return InterviewStatement(statement, examples, [str(x).strip() for x in data.get("left_out") or []], True)


def cut_down_statement(problem: Problem) -> InterviewStatement:
    """Without Claude's rewrite: LeetCode's description and first two examples, with the constraints and the
    follow-up left out."""
    text = problem.text
    head = re.search(r"^\s*(Example\s*1\s*:|Constraints\s*:|Follow[ -]?up)", text, re.M | re.I)
    description = text[: head.start()].strip() if head else text.strip()
    examples = []
    for n in (1, 2):
        block = re.search(rf"Example\s*{n}\s*:(.*?)(?=^\s*(?:Example\s*\d+\s*:|Constraints\s*:|Follow[ -]?up)|\Z)",
                          text, re.S | re.M | re.I)
        io = block and re.search(r"Input:\s*(.*?)\s*Output:\s*(.*?)\s*(?:Explanation:\s*(.*?)\s*)?\Z",
                                 block.group(1), re.S)
        if io:
            examples.append({"input": io.group(1).strip(), "output": io.group(2).strip(),
                             "explanation": " ".join((io.group(3) or "").split())})
    left_out = []
    rules = re.search(r"Constraints\s*:(.*?)(?=^\s*Follow[ -]?up|\Z)", text, re.S | re.M | re.I)
    if rules:
        left_out += [line.strip(" -") for line in rules.group(1).splitlines() if line.strip(" -")]
    follow = re.search(r"^\s*(Follow[ -]?up.*)", text, re.S | re.M | re.I)
    if follow:
        left_out.append(" ".join(follow.group(1).split()))
    return InterviewStatement(description, examples, left_out, False)


def interview_statement(problem: Problem) -> InterviewStatement:
    """Claude's interview-style rewrite of a problem when there is one, otherwise LeetCode's statement cut down."""
    data = _saved_statement(problem.id)
    if data:
        try:
            return _parse_statement(data)
        except (ValueError, KeyError, TypeError):
            pass
    return cut_down_statement(problem)


def _saved_statement(problem_id: str) -> dict | None:
    try:
        return json.loads(_statement_path(problem_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


async def prepare_statements(problem_ids: list[str]) -> None:
    """Has Claude write the interview-style version of each problem that has none yet. A problem whose rewrite
    fails is shown cut down instead (see cut_down_statement)."""
    await asyncio.gather(*(_rewrite(problem_id) for problem_id in problem_ids))


async def _rewrite(problem_id: str):
    path = _statement_path(problem_id)
    saved = _saved_statement(problem_id)
    if saved and saved.get("version") == STATEMENT_VERSION:
        return
    try:
        problem = await asyncio.to_thread(leetcode.problem, problem_id)
        prompt = (STATEMENT_PROMPT_PATH.read_text(encoding="utf-8")
                  .replace("{signature}", problem.starter["python"].strip()).replace("{problem}", problem.text))
        reply = await complete(prompt, STATEMENT_MODEL)
        found = re.search(r"\{.*\}", reply, re.S)
        if not found:
            raise ValueError(f"no JSON in the reply: {reply[:200]}")
        data = json.loads(found.group(0))
        _parse_statement(data)
        data["version"] = STATEMENT_VERSION
    except Exception as e:
        # An older rewrite, if there is one, is still better than the cut-down statement.
        logger.warning(f"Could not write {problem_id} as an interview problem: {e}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def filters_label(session: dict) -> str:
    """For titles and logs, e.g. "Medium/Hard, graph, tree, rating 1600-1900"."""
    difficulties, tags, rating, interview_only = filters(session)
    parts = ["/".join(d.capitalize() for d in difficulties)]
    if tags:
        parts.append(", ".join(tags))
    if rating:
        parts.append(f"rating {rating[0] or ''}-{rating[1] or ''}")
    if not interview_only:
        parts.append("any problem")
    return ", ".join(parts)


def problem_heading(problem: Problem, number: int) -> str:
    rating = f", rating {problem.rating:.0f}" if problem.rating else ""
    return f"Problem {number}: {problem.title} (LeetCode #{problem.number}, {problem.difficulty}{rating})"


def problem_brief(problem: Problem, number: int, status: str, style: str = "leetcode") -> str:
    """What the interviewer is told about one problem."""
    hints = "\n".join(f"{i}. {h}" for i, h in enumerate(problem.hints, 1)) or "(LeetCode lists none)"
    statement = problem.text
    if style == "interview":
        shown = interview_statement(problem)
        left_out = "\n".join(f"- {x}" for x in shown.left_out) or "- (nothing listed; see the full statement)"
        statement = (f"On the candidate's screen, and nothing else:\n{shown.text}\n\n"
                     f"Left out on purpose (answer truthfully when asked, never volunteer):\n{left_out}\n\n"
                     f"LeetCode's full statement, for you only:\n{problem.text}")
    return (
        f'<problem number="{number}" status="{status}">\n{problem_heading(problem, number)}\n'
        f"Tags: {', '.join(problem.tags) or 'none'}\n\n{statement}\n\n"
        f"LeetCode's own hints:\n{hints}\n</problem>"
    )


def session_mode(session: dict, minutes: int, shown: int = 1) -> str:
    """The "Session mode" section of the interviewer prompt for a coding interview."""
    language = language_name(session)
    problems = session_problems(session)
    style = statement_style(session)
    short = minutes <= SHORT_SESSION_MINUTES
    briefs = []
    for number, problem in enumerate(problems, 1):
        if short and number > shown:
            break  # no time for the backup
        if number <= shown:
            status = "already on the candidate's screen"
        else:
            status = "backup, not shown yet: show it with [[NEXT]] only if there is time"
        briefs.append(problem_brief(problem, number, status, style))
    if short:
        second = ("This session is too short for a second problem: never show the backup and never write [[NEXT]]. "
                  "Spend any remaining time on follow-ups.")
    elif len(problems) > 1:
        second = (
            f"The second problem is a backup. Move on to it only after the first one is finished, including its "
            f"complexity and at least one follow-up, and only with at least {SECOND_PROBLEM_MIN_LEFT} minutes left. "
            "To show it, say one sentence telling the candidate there is another problem on their screen, and put "
            "the exact token [[NEXT]] at the very end of that message. The software removes the token and shows the "
            "problem. Never write [[NEXT]] in any other message. If there is not enough time, spend the rest on "
            "follow-ups instead."
        )
    else:
        second = "There is only one problem, so spend any remaining time on its follow-ups."
    time_rule = ("this is a short session, so leave out the candidate's questions about the team: close as soon as "
                 "the follow-up is done or time is up." if short else
                 "keep the last few minutes for the candidate's questions about the team or the work, then close.")
    opening = ("Opening, under half a minute: greet the candidate, give your name, say there is one problem on their "
               f"screen, to think out loud and write {language} in the notepad, with no running code."
               if short else
               "Opening, about one minute: greet the candidate, introduce yourself by name and role, explain the "
               f"format (one or two problems, think out loud, write {language} in the notepad, no running code), and "
               "tell them the first problem is on their screen and to take a moment to read it.")
    if style == "interview":
        opening += " Add that they can ask you anything about the problem."
        screen = ("which also shows a short, deliberately underspecified version of the current problem, the way "
                  "interviewers write problems: a short paragraph and one or two examples, with no constraints, guarantees or "
                  "edge-case rules. Each problem below lists what the candidate sees, what was left out, and "
                  "LeetCode's full statement, which is the truth for every answer you give.")
        clarify = (
            "1. Clarify. The candidate is expected to ask about what the screen leaves out, such as input sizes, "
            "value ranges, empty or edge inputs, duplicates, or what to return when there is no answer. Answer each "
            "question briefly and truthfully from the full statement, and only what was asked; for an input size, "
            "give the bound, such as \"up to about ten to the fifth\". If they state an assumption, confirm or "
            "correct it. Never list the left-out details yourself or hint at which questions to ask. If they ask "
            "about something the full statement leaves open, pick a reasonable answer and stick to it. If they move "
            "on to an approach without asking about something that matters, let them, probe it in testing with a "
            "specific input, and remember it for the evaluation. If they start coding without saying anything, let "
            "them, but ask them to talk you through their plan.")
    else:
        screen = ("which also shows the current problem's statement, examples and constraints, exactly as LeetCode "
                  "publishes them.")
        clarify = (
            "1. Clarify. Answer clarifying questions briefly and consistently with the statement and constraints. If "
            "they ask about something the statement leaves open, pick a reasonable answer and stick to it. If they "
            "start coding without saying anything, let them, but ask them to talk you through their plan.")
    return f"""This is a LeetCode-style coding interview of about {minutes} minutes. It replaces the interview structure, the follow-up policy and the rule against hints below; everything else still applies. Ignore the question_bank, and do not ask about the resume.

The candidate writes {language} in a shared notepad, {screen} There is no way to run the code: the candidate tests it by walking through examples by hand. Never read what is on the candidate's screen aloud, since they can read it; a one-sentence summary is fine.

Prepare silently before you speak: the problems below are well-known LeetCode problems. For each, work out the optimal solution and its complexity, a common slower approach, a ladder of three hints from a small nudge to the key idea (use LeetCode's own hints as part of it when there are any), the edge cases and typical bugs worth probing, and one or two follow-up questions. Keep all of it to yourself.

{opening} Skip self-introductions.

Work through each problem at the candidate's pace:
{clarify}
2. Approach. Before they code, ask for their approach and its time and space complexity. If they suggest brute force, acknowledge it and ask whether they can do better; settling for brute force is fine when they are stuck and time is short.
3. Coding. Mostly stay quiet. Notes starting with "[notepad]" show their current code, which may be half-written: do not comment on unfinished code unless they ask or say they are done. If they think out loud, reply with a very short acknowledgment or answer their question.
4. Testing. When they say they are done, ask them to walk through the code with an example. If there is a bug, do not point it out: ask what the code does for a specific input that exposes it. Probe the edge cases you prepared.
5. Complexity and follow-up. Ask for the final time and space complexity if they have not given it, then ask one follow-up question.

{second}

Hints: a real coding interviewer helps a stuck candidate, and how much help they needed is part of the evaluation. Give a hint when the candidate asks for one, says they are stuck, has been circling without progress for a while, or keeps going down a path that cannot work. Use your hint ladder in order, one step at a time and smallest first, as a nudge or a question in your own words. Never dictate code, and never reveal your prepared solution as such. Give the key idea outright only if the last hint has not helped, in about two sentences, and then let them code it. Do not hint while they are making progress, even slowly.

Talking about code: never read code aloud symbol by symbol; refer to it by what it does or by its variable and function names. Accept small syntax slips and focus on the logic, but do ask about {language} details that matter, such as integer overflow in C++ or recursion depth in Python.

Time: {time_rule}

The problems for this session:

""" + "\n\n".join(briefs)


def shown_line(problem: Problem, number: int) -> str:
    return SHOWN_LINE.format(number=number, title=problem.title)


def code_snapshot(session: dict, problem: Problem | None, number: int, code: str) -> str:
    """The candidate's code for one problem, as written to the transcript."""
    label = f"problem {number}, {problem.title}" if problem else f"problem {number}"
    return f"[Notepad: final {language_name(session)} code for {label}]\n```{code_fence(session)}\n{code.strip()}\n```"


class CodingSession:
    """The problems of one coding interview, which one is on screen, and the candidate's code for it.
    The methods return what bot.py should write to the transcript or tell the interviewer."""

    def __init__(self, session: dict, turns: list[Turn], problems: list[Problem] | None = None):
        self.session = session
        self.problems = problems if problems is not None else session_problems(session)
        # A resumed session picks up at the problem it had reached.
        self.shown = min(shown_count(turns), len(self.problems))
        self.code = ""
        # Set when a problem is shown, until the candidate speaks again. The TTS filter and the end of the
        # interviewer's turn can both see the same [[NEXT]], and moving on twice without an answer is never meant.
        self._moved_since_answer = False

    @property
    def current(self) -> Problem | None:
        return self.problems[self.shown - 1] if self.shown else None

    def answered(self):
        """The candidate spoke."""
        self._moved_since_answer = False

    def next_problem(self) -> tuple[str | None, str, str] | None:
        """[[NEXT]]: (code snapshot of the problem so far or None, transcript line, note for the interviewer),
        or None when there is no next problem or the interviewer just moved on."""
        if self._moved_since_answer or not 0 < self.shown < len(self.problems):
            return None
        if int(self.session.get("minutes") or 45) <= SHORT_SESSION_MINUTES:
            return None  # the interviewer was told there is no second problem and has no brief for it
        self._moved_since_answer = True
        snapshot = code_snapshot(self.session, self.current, self.shown, self.code) if self.code.strip() else None
        self.shown += 1
        self.code = ""
        note = f"[notepad] Problem {self.shown} is now on the candidate's screen, and the notepad has its starter code."
        return snapshot, shown_line(self.current, self.shown), note

    def update_code(self, text: str, problem_id: str | None = None) -> str | None:
        """A notepad save: the note for the interviewer, or None when nothing changed or the save belongs to a
        problem the interviewer has already moved on from."""
        if not self.current or (problem_id and problem_id != self.current.id) or text.strip() == self.code.strip():
            return None
        self.code = text
        return f"[notepad] The candidate's {language_name(self.session)} code for problem {self.shown} now reads:\n{text}"

    def final_snapshot(self) -> str | None:
        """The code on screen when the session ends, for the transcript."""
        return code_snapshot(self.session, self.current, self.shown, self.code) if self.code.strip() else None

    def view(self) -> dict:
        """What the notepad page shows."""
        problem, language = self.current, self.session.get("language", "python")
        if statement_style(self.session) == "interview":
            # Only what an interviewer would write down: no tags (they give the technique away), rating or link.
            return {
                "statement": "interview",
                "language": language,
                "language_name": language_name(self.session),
                "number": self.shown,
                "count": len(self.problems),
                "id": problem.id,
                "title": problem.title,
                "html": interview_statement(problem).html,
                "starter": problem.starter.get(language, problem.starter["python"]),
            }
        return {
            "statement": "leetcode",
            "language": language,
            "language_name": language_name(self.session),
            "number": self.shown,
            "count": len(self.problems),
            "id": problem.id,
            "title": problem.title,
            "leetcode_number": problem.number,
            "difficulty": problem.difficulty,
            "rating": problem.rating,
            "tags": problem.tags,
            "url": problem.url,
            "html": problem.content_html,
            "starter": problem.starter.get(language, problem.starter["python"]),
        }


def rubric(cfg=None) -> str:
    """The coding rubric: the round's or company's own prompts/coding_rubric.md when it has one."""
    path = cfg.prompt_path("coding_rubric.md") if cfg else RUBRIC_PATH
    return path.read_text(encoding="utf-8").strip()


def feedback_session_info(session: dict, turns: list[Turn], minutes_used: int) -> str:
    """The "Session" line of the feedback prompt: what was asked, and how to adapt the report to coding."""
    language = language_name(session)
    problems = session_problems(session)[: shown_count(turns)]
    if statement_style(session) == "interview":
        def shown(p: Problem) -> str:
            statement = interview_statement(p)
            left_out = "\n".join(f"- {x}" for x in statement.left_out) or "- (none listed)"
            return (f"What the candidate saw:\n{statement.text}\n\nLeft out, for the candidate to ask about:\n"
                    f"{left_out}\n\nLeetCode's full statement:\n{p.text}")
        clarify = (
            "The candidate saw only a short, underspecified version of each problem, as in a real interview, and "
            "was expected to ask clarifying questions. Score 釐清問題 by which of the left-out details that matter "
            "for the solution they asked about or stated as assumptions before relying on them, and in each "
            "problem's review add (e) the clarifying questions they asked and the important ones they missed.")
    else:
        def shown(p: Problem) -> str:
            return p.text
        clarify = (
            "LeetCode's full statement, constraints included, was on the candidate's screen, so score 釐清問題 only "
            "on whether they confirmed their understanding and asked about what the statement leaves open; do not "
            "count it against them that they did not ask about what was shown.")
    briefs = "\n\n".join(f'<problem number="{n}">\n{problem_heading(p, n)}\n\n{shown(p)}\n</problem>'
                         for n, p in enumerate(problems, 1))
    return (
        f"a LeetCode-style coding interview in {language}, planned for {session.get('minutes')} minutes, about "
        f"{minutes_used} minutes used. The candidate wrote code in a shared notepad with no way to run it; the "
        "transcript contains their final code for each problem as notepad snapshots. Adapt the report to a coding "
        "interview: score with the coding rubric; in the question-by-question review, treat each problem as one "
        "main question, and instead of a spoken reference answer give (a) how the candidate's approach compared "
        "with the optimal approach, (b) bugs and missed edge cases in the final code, quoting the lines, (c) a "
        f"clean optimal reference solution in {language} in a fenced code block, with its complexity, and (d) two "
        "or three sentences the candidate could have said to explain the approach. Count the hints the interviewer "
        "gave on each problem and take them into account in the scores. Do not comment on the resume or job fit. "
        f"In the scores JSON, list each problem title as a question. {clarify}\n\n"
        "Problems shown in this session:\n\n" + briefs
    )
