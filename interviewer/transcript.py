"""Interview transcripts: written turn by turn as Markdown, and read back to resume an interview or review it.

Each transcript lives in transcripts/<interview>/ and carries HTML comments that do not show in a
Markdown preview:
- which interview folder it belongs to, and the session settings (full interview or a drill)
- when each turn started and how long it lasted, in seconds since the interview began
- how many seconds the interview has run, appended each time a session ends
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from loguru import logger

from interviewer import settings

TRANSCRIPTS_DIR = settings.project_path(os.getenv("TRANSCRIPTS_DIR", "transcripts"))

SPEAKER_LINE = re.compile(r"^\*\*(Interviewer|Candidate):\*\* ")
INTERVIEW_TAG = re.compile(r"<!-- interview: (.+?) -->")
SESSION_TAG = re.compile(r"<!-- session: (\{.*?\}) -->")
ELAPSED_TAG = re.compile(r"<!-- elapsed: (\d+(?:\.\d+)?) s -->")
TIMING_TAG = re.compile(r"\n<!-- at (\d+(?:\.\d+)?) s, (\d+(?:\.\d+)?) s(?:, pause (\d+(?:\.\d+)?) s)? -->$")


@dataclass
class Turn:
    speaker: str  # "Interviewer" or "Candidate"
    text: str
    at: float | None = None  # seconds since the interview started
    duration: float | None = None
    pause: float | None = None  # candidate only: silence between the interviewer finishing and the answer

    @property
    def line(self) -> str:
        return f"**{self.speaker}:** {self.text}"


@dataclass
class SavedTranscript:
    path: Path
    interview: str | None  # interview folder name, None for transcripts written before it was recorded
    turns: list[Turn]
    elapsed_secs: float
    session: dict = field(default_factory=dict)  # {"mode": "full"} or {"mode": "drill", "topic": ..., "minutes": ...}

    @property
    def lines(self) -> list[str]:
        return [t.line for t in self.turns]


def read_transcript(path: str | Path) -> SavedTranscript:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    interview = INTERVIEW_TAG.search(text)
    session = SESSION_TAG.search(text)
    elapsed = ELAPSED_TAG.findall(text)

    turns: list[Turn] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if match := SPEAKER_LINE.match(block):
            timing = TIMING_TAG.search(block)
            body = block[match.end() : timing.start() if timing else None]
            turn = Turn(match.group(1), body.strip())
            if timing:
                turn.at, turn.duration = float(timing.group(1)), float(timing.group(2))
                turn.pause = float(timing.group(3)) if timing.group(3) else None
            turns.append(turn)
        elif block and turns and (_open_fence(turns[-1].text) or not block.startswith(("#", "<!--"))):
            # A turn that itself contained a blank line; its timing comment ends the last paragraph. Inside a code
            # block, a paragraph starting with "#" is code (a comment, an #include), not a heading.
            timing = TIMING_TAG.search(block)
            if timing:
                block = block[: timing.start()]
                last = turns[-1]
                last.at, last.duration = float(timing.group(1)), float(timing.group(2))
                last.pause = float(timing.group(3)) if timing.group(3) else None
            turns[-1].text += "\n\n" + block.strip()

    return SavedTranscript(
        path=path,
        interview=interview.group(1) if interview else None,
        turns=turns,
        elapsed_secs=float(elapsed[-1]) if elapsed else _estimate_elapsed(path),
        session=json.loads(session.group(1)) if session else {"mode": "full"},
    )


def saved_transcripts(folder: Path, newest_first: bool = False) -> list[SavedTranscript]:
    """Every transcript in a folder, by start time. One that can't be read (hand-edited or cut off) is skipped
    with a warning instead of breaking the pages that list them."""
    result = []
    for path in sorted(folder.glob("*-transcript.md"), reverse=newest_first):
        try:
            result.append(read_transcript(path))
        except (OSError, ValueError) as e:  # ValueError covers bad JSON and bad UTF-8
            logger.warning(f"Skipping a transcript that can't be read: {path} ({e})")
    return result


def _open_fence(text: str) -> bool:
    return len(re.findall(r"^```", text, re.M)) % 2 == 1


def _estimate_elapsed(path: Path) -> float:
    """Older transcripts have no elapsed marker: use the start time in the file name and the last write."""
    try:
        started = datetime.strptime(path.name[:13], "%Y%m%d-%H%M")
    except ValueError:
        return 0.0
    return max(0.0, path.stat().st_mtime - started.timestamp())


def write_atomic(path: Path, text: str):
    """Writes through a temporary file, so a crash mid-write never leaves a cut-off report or resume."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def sibling(transcript_path: Path, kind: str, suffix: str = ".md") -> Path:
    """The report or scores file that belongs to a transcript, e.g. kind="feedback" or "scores"."""
    return transcript_path.with_name(transcript_path.name.replace("-transcript.md", f"-{kind}{suffix}"))


class Transcript:
    """Collects the interview turn by turn and appends each line to a Markdown file."""

    def __init__(self, interview: str, title: str, session: dict | None = None, resume: SavedTranscript | None = None):
        if resume:
            self.path = resume.path
            self.turns = list(resume.turns)
            self.prior_elapsed = resume.elapsed_secs
            self.session = resume.session
            return
        folder = TRANSCRIPTS_DIR / interview
        folder.mkdir(parents=True, exist_ok=True)
        self.turns = []
        self.prior_elapsed = 0.0
        self.session = session or {"mode": "full"}
        # "--" would end the HTML comment early; the JSON escape reads back as the same text.
        tag = json.dumps(self.session, ensure_ascii=False).replace("--", "-\\u002d")
        header = f"# {title}\n\n<!-- interview: {interview} -->\n\n<!-- session: {tag} -->\n\n"
        # The name starts with the start time to the minute, which is what the pages read (older names stop
        # there); seconds keep two sessions in one minute apart, and "x" never overwrites an existing file.
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for n in range(1, 100):
            self.path = folder / (f"{stamp}-transcript.md" if n == 1 else f"{stamp}-{n}-transcript.md")
            try:
                with self.path.open("x", encoding="utf-8") as f:
                    f.write(header)
                break
            except FileExistsError:
                continue

    @property
    def lines(self) -> list[str]:
        return [t.line for t in self.turns]

    def add(self, speaker: str, text: str, at: float | None = None, duration: float | None = None,
            pause: float | None = None):
        text = (text or "").strip()
        if not text:
            return
        turn = Turn(speaker, text, at, duration, pause)
        self.turns.append(turn)
        block = turn.line
        if at is not None and duration is not None:
            block += f"\n<!-- at {at:.1f} s, {duration:.1f} s" + (f", pause {pause:.1f} s" if pause is not None else "") + " -->"
        self._append(block)
        logger.info(f"[transcript] {speaker}: {text}")

    def mark_elapsed(self, secs: float):
        self._append(f"<!-- elapsed: {secs:.0f} s -->")

    def text(self) -> str:
        return "\n\n".join(self.lines)

    def _append(self, block: str):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(block + "\n\n")
