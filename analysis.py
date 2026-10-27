"""Delivery statistics from turn timings: how long answers run, how long the candidate pauses before
answering, and speaking rate. The feedback report quotes these instead of guessing from text alone.
"""

import statistics
from dataclasses import dataclass

from chinese import has_chinese, spoken_units
from transcript import Turn


@dataclass
class Answer:
    question: str
    text: str
    seconds: float
    pause: float | None
    words: int


def answers(turns: list[Turn]) -> list[Answer]:
    """Groups consecutive candidate turns (an answer split by pauses) under the question before them."""
    result: list[Answer] = []
    question = ""
    current: list[Turn] = []

    def flush():
        timed = [t for t in current if t.at is not None and t.duration is not None]
        if timed:
            seconds = timed[-1].at + timed[-1].duration - timed[0].at
            text = " ".join(t.text for t in current)
            result.append(Answer(question, text, seconds, current[0].pause, spoken_units(text)))

    for turn in turns:
        if turn.speaker == "Interviewer":
            flush()
            current = []
            question = turn.text
        else:
            current.append(turn)
    flush()
    return result


def delivery_summary(turns: list[Turn]) -> str:
    """A short plain-text summary for the feedback prompt, or a note that no timings were recorded."""
    items = [a for a in answers(turns) if a.seconds > 0]
    if not items:
        return "No turn timings were recorded for this transcript, so judge delivery from the text only."

    secs = [a.seconds for a in items]
    longest = max(items, key=lambda a: a.seconds)
    lines = [
        f"Answers timed: {len(items)}",
        f"Answer length: median {statistics.median(secs):.0f} s, longest {longest.seconds:.0f} s "
        f"(to the question: \"{longest.question[:120]}\")",
        f"Answers over 2 minutes: {sum(s > 120 for s in secs)}; under 15 seconds: {sum(s < 15 for s in secs)}",
    ]
    rates = [a.words / a.seconds * 60 for a in items if a.seconds >= 10]
    if rates:
        unit = ("units per minute, counting each Chinese character and each English word as one"
                if any(has_chinese(a.text) for a in items) else "words per minute")
        lines.append(f"Speaking rate: median {statistics.median(rates):.0f} {unit} (from the transcript, which drops some filler words)")
    paused = [a for a in items if a.pause is not None]
    pauses = [a.pause for a in paused]
    if pauses:
        slowest = max(paused, key=lambda a: a.pause)
        lines.append(
            f"Pause before answering: median {statistics.median(pauses):.1f} s, longest {slowest.pause:.1f} s "
            f"(to the question: \"{slowest.question[:120]}\")"
        )
    lines.append("Timings are approximate: an answer's end includes about a second of end-of-turn detection.")
    return "\n".join(lines)
