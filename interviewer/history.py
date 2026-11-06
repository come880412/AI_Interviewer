"""Practice history across sessions of one interview, read from the *-scores.json files the feedback
step writes next to each transcript. It feeds two things: a note for the interviewer about earlier weak
spots and questions already asked, and the progress page.
"""

import json
from datetime import datetime
from pathlib import Path

from interviewer import coding
from interviewer.transcript import TRANSCRIPTS_DIR, read_transcript, sibling

# How far back the interviewer looks.
RECENT_SESSIONS = 3
MAX_QUESTIONS = 30


def sessions(interview: str) -> list[dict]:
    """Every scored session of this interview, oldest first."""
    result = []
    for transcript in sorted((TRANSCRIPTS_DIR / interview).glob("*-transcript.md")):
        scores_path = sibling(transcript, "scores", ".json")
        if not scores_path.exists():  # checked first: reading every transcript would be slow
            continue
        try:
            scores = json.loads(scores_path.read_text(encoding="utf-8"))
            saved = read_transcript(transcript)
        except (OSError, ValueError):  # a broken file is skipped, not allowed to break the page
            continue
        try:
            started = datetime.strptime(transcript.name[:13], "%Y%m%d-%H%M").strftime("%Y-%m-%d %H:%M")
        except ValueError:
            started = transcript.stem
        result.append({
            "file": transcript.name,
            "started": started,
            "session": saved.session,
            **scores,
        })
    return result


def _interview_sessions(interview: str) -> list[dict]:
    """Full interviews and drills. Coding interviews have their own rubric and history (coding_history)."""
    return [s for s in sessions(interview) if not coding.is_coding(s["session"])]


def drill_suggestions(interview: str) -> list[str]:
    """Topics the latest reports said to practice next, most recent first, without duplicates."""
    topics: list[str] = []
    for s in reversed(_interview_sessions(interview)):
        for topic in s.get("next_focus", []):
            if topic not in topics:
                topics.append(topic)
    return topics[:8]


def practice_history(interview: str) -> str:
    """Plain-text notes for the interviewer prompt."""
    past = _interview_sessions(interview)
    if not past:
        return "This is the candidate's first scored practice session for this round."

    lines = [f"The candidate has done {len(past)} scored practice session(s) for this round. Most recent first:"]
    for s in reversed(past[-RECENT_SESSIONS:]):
        mode = s["session"].get("mode", "full")
        coached = "coached " if s["session"].get("coach") else ""
        label = f"{coached}drill on {s['session'].get('topic')}" if mode == "drill" else "full interview"
        weak = "; ".join(w.get("topic", "") for w in s.get("weaknesses", [])) or "none recorded"
        lines.append(f"- {s['started']} ({label}), verdict {s.get('verdict', 'unknown')}. Weak spots: {weak}")

    focus = drill_suggestions(interview)
    if focus:
        lines.append("Topics the last reports said to work on: " + "; ".join(focus))

    asked: list[str] = []
    for s in reversed(past):
        for q in s.get("questions", []):
            text = q.get("question", "") if isinstance(q, dict) else str(q)
            if text and text not in asked:
                asked.append(text)
    if asked:
        lines.append("Questions already asked in earlier sessions:")
        lines += [f"- {q}" for q in asked[:MAX_QUESTIONS]]
    return "\n".join(lines)


def coding_history(interview: str) -> str:
    """Plain-text notes for the interviewer prompt of a coding interview. The software picks the problems, so
    these notes are about how the candidate tends to work, not which problems to ask."""
    past = [s for s in sessions(interview) if coding.is_coding(s["session"])]
    if not past:
        return "This is the candidate's first scored coding practice session."
    lines = [f"The candidate has done {len(past)} scored coding practice session(s). Most recent first:"]
    for s in reversed(past[-RECENT_SESSIONS:]):
        label = f"{coding.language_name(s['session'])}, {coding.filters_label(s['session'])}"
        weak = "; ".join(w.get("topic", "") for w in s.get("weaknesses", [])) or "none recorded"
        lines.append(f"- {s['started']} ({label}), verdict {s.get('verdict', 'unknown')}. Weak spots: {weak}")
    focus = []
    for s in reversed(past):
        focus += [t for t in s.get("next_focus", []) if t not in focus]
    if focus:
        lines.append("Habits the last reports said to work on, which you should give the candidate a chance to show: "
                     + "; ".join(focus[:6]))
    return "\n".join(lines)
