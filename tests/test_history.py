import json

import history


def make_session(dirs, interview, stamp, scores=None, session=None, raw_scores=None):
    folder = dirs.transcripts / interview
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stamp}-transcript.md"
    tag = f"<!-- session: {json.dumps(session)} -->\n\n" if session else ""
    path.write_text(f"# T\n\n<!-- interview: {interview} -->\n\n{tag}**Interviewer:** Hi\n\n", encoding="utf-8")
    scores_path = folder / f"{stamp}-scores.json"
    if raw_scores is not None:
        scores_path.write_text(raw_scores, encoding="utf-8")
    elif scores is not None:
        scores_path.write_text(json.dumps(scores), encoding="utf-8")
    return path


def test_sessions_reads_scored_transcripts_oldest_first(dirs):
    make_session(dirs, "acme/hm", "20261002-0900", {"verdict": "lean yes"}, {"mode": "drill", "topic": "CUDA", "minutes": 10})
    make_session(dirs, "acme/hm", "20261001-1800", {"verdict": "no"})
    make_session(dirs, "acme/hm", "20261003-1000")  # no scores yet
    make_session(dirs, "acme/hm", "20261004-1000", raw_scores="{not json")
    make_session(dirs, "other/round", "20261005-1000", {"verdict": "yes"})

    result = history.sessions("acme/hm")
    assert [s["file"] for s in result] == ["20261001-1800-transcript.md", "20261002-0900-transcript.md"]
    assert result[0]["started"] == "2026-10-01 18:00"
    assert result[0]["session"] == {"mode": "full"}
    assert result[0]["verdict"] == "no"
    assert result[1]["session"] == {"mode": "drill", "topic": "CUDA", "minutes": 10}
    assert history.sessions("missing/round") == []


def test_sessions_with_unparseable_file_name(dirs):
    make_session(dirs, "acme/hm", "imported", {"verdict": "yes"})
    assert history.sessions("acme/hm")[0]["started"] == "imported-transcript"


def test_drill_suggestions_most_recent_first_without_duplicates(dirs):
    make_session(dirs, "acme/hm", "20261001-1000", {"next_focus": ["old topic", "shared"]})
    make_session(dirs, "acme/hm", "20261002-1000", {"next_focus": ["new topic", "shared"]})
    make_session(dirs, "acme/hm", "20261003-1000", {"verdict": "yes"})  # no next_focus
    assert history.drill_suggestions("acme/hm") == ["new topic", "shared", "old topic"]


def test_drill_suggestions_capped_at_eight(dirs):
    make_session(dirs, "acme/hm", "20261001-1000", {"next_focus": [f"t{i}" for i in range(12)]})
    assert history.drill_suggestions("acme/hm") == [f"t{i}" for i in range(8)]


def test_practice_history_first_session(dirs):
    assert history.practice_history("acme/hm") == "This is the candidate's first scored practice session for this round."


def test_practice_history_notes(dirs):
    make_session(dirs, "acme/hm", "20261001-1000", {
        "verdict": "lean no",
        "weaknesses": [{"topic": "Quantization"}, {"topic": "STAR structure"}],
        "questions": [{"question": "Why Acme?"}, "Tell me about a failure."],
        "next_focus": ["Quantization"],
    })
    make_session(dirs, "acme/hm", "20261002-1000", {
        "verdict": "lean yes",
        "questions": [{"question": "Why Acme?", "rating": "good"}, {"question": ""}],
    }, session={"mode": "drill", "topic": "CUDA kernels", "minutes": 15})

    text = history.practice_history("acme/hm")
    lines = text.splitlines()
    assert lines[0] == "The candidate has done 2 scored practice session(s) for this round. Most recent first:"
    assert lines[1] == "- 2026-10-02 10:00 (drill on CUDA kernels), verdict lean yes. Weak spots: none recorded"
    assert lines[2] == "- 2026-10-01 10:00 (full interview), verdict lean no. Weak spots: Quantization; STAR structure"
    assert lines[3] == "Topics the last reports said to work on: Quantization"
    assert lines[4] == "Questions already asked in earlier sessions:"
    assert lines[5:] == ["- Why Acme?", "- Tell me about a failure."]


def test_practice_history_lists_only_recent_sessions(dirs):
    for day in range(1, 6):
        make_session(dirs, "acme/hm", f"202610{day:02d}-1000", {"verdict": f"v{day}"})
    text = history.practice_history("acme/hm")
    assert "done 5 scored practice session(s)" in text
    assert "verdict v5" in text and "verdict v3" in text
    assert "verdict v2" not in text and "verdict v1" not in text
    assert "Topics the last reports" not in text and "Questions already asked" not in text
