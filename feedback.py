"""Turns an interview transcript into a feedback report with Claude.

Runs automatically when an interview ends, or manually:
    python feedback.py transcripts/example/tech/20261023-2130-transcript.md
The interview folder is read from the transcript; pass a name as the second argument to override it.

Writes two files next to the transcript: *-feedback.md (the report) and *-scores.json (the structured
summary that the progress page and the next session's interviewer use).

For reports written before scores existed, extract them from the existing report without redoing it:
    python feedback.py --scores-only transcripts/example/tech/*-transcript.md
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from analysis import delivery_summary
from interview_config import InterviewConfig, pick_interview
from llm import complete
from transcript import SavedTranscript, read_transcript, sibling

load_dotenv(override=True)

FEEDBACK_MODEL = os.getenv("FEEDBACK_MODEL", os.getenv("LLM_MODEL", "claude-opus-5-5"))
SCORES_BLOCK = re.compile(r"<scores>\s*(.*?)\s*</scores>", re.DOTALL)


def session_info(saved: SavedTranscript) -> str:
    minutes = round(saved.elapsed_secs / 60)
    if saved.session.get("mode") == "drill":
        text = (f"a focused practice drill on \"{saved.session.get('topic')}\", planned for "
                f"{saved.session.get('minutes')} minutes, about {minutes} minutes used. Score only the areas this drill covered.")
        if saved.session.get("coach"):
            text += (" Coach mode was on: the interviewer gave feedback and a model answer after each answer, and the "
                     "candidate then retried. Score the candidate's first attempt at each question, and mention in the "
                     "summary whether the retries improved.")
        return text
    return f"a full mock interview, about {minutes} minutes used."


# Longer labels first so "lean no" is not read as "no"; "no hire" means "no".
VERDICT_LABEL = re.compile(r"\b(lean hire|lean no|no hire|hire|no)\b")


def normalize_scores(data: dict) -> dict:
    """Coerces a scores object into the shape history.py expects, in case the model drifted from the
    example: a verdict sentence instead of a label, scores as a name -> number map, and so on."""
    verdict = str(data.get("verdict") or "").lower()
    # The first label in a sentence is the verdict; later ones are usually caveats ("could rise to lean hire").
    match = VERDICT_LABEL.search(verdict)
    label = ("no" if match.group(1) == "no hire" else match.group(1)) if match else None
    areas = data.get("areas")
    if not isinstance(areas, list):
        scores = data.get("scores") or data.get("rubric_scores") or {}
        areas = [{"name": k, "score": v, "note": ""} for k, v in scores.items()] if isinstance(scores, dict) else []
    questions = data.get("questions") or data.get("main_questions") or []
    questions = [q if isinstance(q, dict) else {"question": str(q), "rating": None} for q in questions]
    weaknesses = [w if isinstance(w, dict) else {"topic": str(w), "detail": ""} for w in data.get("weaknesses") or []]
    return {
        "verdict": label or verdict or None,
        "areas": areas,
        "strengths": [str(s) for s in data.get("strengths") or []],
        "weaknesses": weaknesses,
        "questions": questions,
        "next_focus": [str(t) for t in data.get("next_focus") or []],
    }


def split_scores(report: str) -> tuple[str, dict | None]:
    """Separates the <scores> JSON from the Markdown report."""
    match = SCORES_BLOCK.search(report)
    if not match:
        return report.strip(), None
    body = (report[: match.start()] + report[match.end() :]).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", match.group(1).strip())
    try:
        return body, normalize_scores(json.loads(raw))
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"Could not parse the scores block ({e}); the report is saved without scores")
        return body, None


async def generate_feedback(cfg: InterviewConfig, saved: SavedTranscript) -> Path:
    prompt = cfg.render(
        "feedback.md",
        transcript="\n\n".join(saved.lines),
        feedback_language=cfg.variables.get("feedback_language", "English"),
        session_info=session_info(saved),
        delivery_stats=delivery_summary(saved.turns),
    )
    report, scores = split_scores(await complete(prompt, FEEDBACK_MODEL))
    out = sibling(saved.path, "feedback")
    out.write_text(report + "\n", encoding="utf-8")
    if scores:
        sibling(saved.path, "scores", ".json").write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


async def extract_scores(cfg: InterviewConfig, saved: SavedTranscript) -> Path | None:
    """Builds *-scores.json from an existing report, for sessions scored before the JSON existed."""
    report_path = sibling(saved.path, "feedback")
    if not report_path.exists():
        return None
    template = (Path(__file__).parent / "prompts" / "feedback.md").read_text(encoding="utf-8")
    # The example block, not the earlier sentence that mentions the tags.
    shape = re.search(r"<scores>\n\{.*?\}\n</scores>.*?\n\n.*?\n", template, re.DOTALL).group(0)
    prompt = (
        "Below are a mock interview transcript and the feedback report already written for it. Summarize the report "
        f"as JSON in exactly this shape, with text values in {cfg.variables.get('feedback_language', 'English')}:\n\n"
        f"{shape}\n\nUse these rubric area names exactly, with null for areas the report did not score:\n"
        f"{cfg.variables.get('rubric')}\n\nTake verdict, scores, strengths and weaknesses from the report; list the "
        "main questions from the transcript. Output only the <scores> block.\n\n"
        f"<report>\n{report_path.read_text(encoding='utf-8')}\n</report>\n\n<transcript>\n" + "\n\n".join(saved.lines) + "\n</transcript>"
    )
    _, scores = split_scores(await complete(prompt, FEEDBACK_MODEL))
    if not scores:
        return None
    out = sibling(saved.path, "scores", ".json")
    out.write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


async def _main():
    args = sys.argv[1:]
    scores_only = "--scores-only" in args
    args = [a for a in args if a != "--scores-only"]
    if not args:
        print("usage: python feedback.py [--scores-only] <transcript.md>... [--interview NAME]")
        sys.exit(1)
    interview = None
    if "--interview" in args:
        i = args.index("--interview")
        interview = args[i + 1]
        args = args[:i] + args[i + 2 :]
    for arg in args:
        path = Path(arg)
        cfg = InterviewConfig.load(pick_interview(interview, path))
        saved = read_transcript(path)
        if scores_only:
            out = await extract_scores(cfg, saved)
            print(f"Scores saved to {out}" if out else f"Skipped {path} (no report, or the scores could not be read)")
        else:
            print(f"Feedback saved to {await generate_feedback(cfg, saved)}")


if __name__ == "__main__":
    asyncio.run(_main())
