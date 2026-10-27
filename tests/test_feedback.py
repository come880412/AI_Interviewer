from pathlib import Path

import pytest

import feedback
from transcript import SavedTranscript

EMPTY = {"areas": [], "strengths": [], "weaknesses": [], "questions": [], "next_focus": []}


def test_split_scores_valid_json():
    report = ('Report body.\n\n<scores>\n{"verdict": "lean hire", "areas": [{"name": "Depth", "score": 3, "note": "ok"}],'
              ' "strengths": ["clear"], "weaknesses": [{"topic": "STAR", "detail": "rambling"}],'
              ' "questions": [{"question": "Why us?", "rating": "good"}], "next_focus": ["STAR"]}\n</scores>\n')
    body, scores = feedback.split_scores(report)
    assert body == "Report body."
    assert scores == {
        "verdict": "lean hire",
        "areas": [{"name": "Depth", "score": 3, "note": "ok"}],
        "strengths": ["clear"],
        "weaknesses": [{"topic": "STAR", "detail": "rambling"}],
        "questions": [{"question": "Why us?", "rating": "good"}],
        "next_focus": ["STAR"],
    }


def test_split_scores_json_inside_code_fence():
    report = '# Report\n\n<scores>\n```json\n{"verdict": "lean no"}\n```\n</scores>\n\nTrailing note.'
    body, scores = feedback.split_scores(report)
    assert scores == {"verdict": "lean no", **EMPTY}
    assert body.startswith("# Report") and body.endswith("Trailing note.") and "<scores>" not in body

    _, plain_fence = feedback.split_scores('<scores>```\n{"verdict": "hire"}\n```</scores>')
    assert plain_fence["verdict"] == "hire"


@pytest.mark.parametrize("block", ["{not json}", "[1, 2, 3]", '"just a string"'])
def test_split_scores_invalid_json(block):
    body, scores = feedback.split_scores(f"Body\n<scores>{block}</scores>")
    assert body == "Body"
    assert scores is None


def test_split_scores_without_block():
    assert feedback.split_scores("  Just a report.  \n") == ("Just a report.", None)


# --- normalize_scores -----------------------------------------------------------------------------

@pytest.mark.parametrize("verdict, label", [
    ("lean no", "lean no"),
    ("Lean Hire", "lean hire"),
    ("Overall: lean no, mostly because of depth.", "lean no"),
    ("hire", "hire"),
    ("No.", "no"),
    ("borderline", "borderline"),  # unknown text is kept, lower-cased
    ("", None),
])
def test_normalize_verdict(verdict, label):
    assert feedback.normalize_scores({"verdict": verdict})["verdict"] == label


def test_normalize_missing_verdict():
    assert feedback.normalize_scores({}) == {"verdict": None, **EMPTY}


def test_normalize_no_hire_sentence():
    assert feedback.normalize_scores({"verdict": "No hire: not enough depth"})["verdict"] == "no"


def test_normalize_drifted_shapes():
    scores = feedback.normalize_scores({
        "verdict": "lean hire",
        "scores": {"Depth": 3, "Communication": None},
        "strengths": ["clear", 5],
        "weaknesses": ["STAR structure", {"topic": "CUDA", "detail": "x"}],
        "main_questions": ["Why us?", {"question": "Q2", "rating": "partial"}],
        "next_focus": ["STAR", 1],
    })
    assert scores["areas"] == [{"name": "Depth", "score": 3, "note": ""},
                               {"name": "Communication", "score": None, "note": ""}]
    assert scores["strengths"] == ["clear", "5"]
    assert scores["weaknesses"] == [{"topic": "STAR structure", "detail": ""}, {"topic": "CUDA", "detail": "x"}]
    assert scores["questions"] == [{"question": "Why us?", "rating": None}, {"question": "Q2", "rating": "partial"}]
    assert scores["next_focus"] == ["STAR", "1"]

    assert feedback.normalize_scores({"rubric_scores": {"A": 4}})["areas"] == [{"name": "A", "score": 4, "note": ""}]
    assert feedback.normalize_scores({"scores": [1, 2]})["areas"] == []


# --- session_info ---------------------------------------------------------------------------------

def saved(session, elapsed):
    return SavedTranscript(path=Path("x-transcript.md"), interview="acme/hm", turns=[], elapsed_secs=elapsed,
                           session=session)


def test_session_info_full():
    assert feedback.session_info(saved({"mode": "full"}, 1830)) == "a full mock interview, about 30 minutes used."
    assert feedback.session_info(saved({}, 0)) == "a full mock interview, about 0 minutes used."


def test_session_info_drill():
    text = feedback.session_info(saved({"mode": "drill", "topic": "CUDA streams", "minutes": 15}, 600))
    assert text.startswith('a focused practice drill on "CUDA streams", planned for 15 minutes, about 10 minutes used.')
    assert "Score only the areas this drill covered." in text
    assert "Coach mode" not in text


def test_session_info_coached_drill():
    text = feedback.session_info(saved({"mode": "drill", "topic": "CUDA streams", "minutes": 15, "coach": True}, 600))
    assert "Score the candidate's first attempt at each question" in text
