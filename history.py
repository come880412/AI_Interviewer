"""Practice history across sessions of one interview, read from the *-scores.json files the feedback
step writes next to each transcript. It feeds two things: a note for the interviewer about earlier weak
spots and questions already asked, and the progress page.
"""

import json
from datetime import datetime
from pathlib import Path

from transcript import TRANSCRIPTS_DIR, read_transcript, sibling

# How far back the interviewer looks.
RECENT_SESSIONS = 3
MAX_QUESTIONS = 30


def sessions(interview: str) -> list[dict]:
    """Every scored session of this interview, oldest first."""
    result = []
    for transcript in sorted((TRANSCRIPTS_DIR / interview).glob("*-transcript.md")):
        scores_path = sibling(transcript, "scores", ".json")
        if not scores_path.exists():
            continue
        try:
            scores = json.loads(scores_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        try:
            started = datetime.strptime(transcript.name[:13], "%Y%m%d-%H%M").strftime("%Y-%m-%d %H:%M")
        except ValueError:
            started = transcript.stem
        result.append({
            "file": transcript.name,
            "started": started,
            "session": read_transcript(transcript).session,
            **scores,
        })
    return result


def drill_suggestions(interview: str) -> list[str]:
    """Topics the latest reports said to practice next, most recent first, without duplicates."""
    topics: list[str] = []
    for s in reversed(sessions(interview)):
        for topic in s.get("next_focus", []):
            if topic not in topics:
                topics.append(topic)
    return topics[:8]


def practice_history(interview: str) -> str:
    """Plain-text notes for the interviewer prompt."""
    past = sessions(interview)
    if not past:
        return "This is the candidate's first scored practice session for this round."

    lines = [f"The candidate has done {len(past)} scored practice session(s) for this round. Most recent first:"]
    for s in reversed(past[-RECENT_SESSIONS:]):
        mode = s["session"].get("mode", "full")
        label = f"drill on {s['session'].get('topic')}" if mode == "drill" else "full interview"
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
