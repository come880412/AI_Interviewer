import os
import re
from datetime import datetime
from pathlib import Path

import pytest

import transcript
from transcript import SavedTranscript, Transcript, Turn, _estimate_elapsed, read_transcript, sibling


def test_new_transcript_writes_header_and_tags(dirs):
    t = Transcript("acme/hm", "Mock interview: ML Engineer", session={"mode": "full"})
    assert t.path.parent == dirs.transcripts / "acme" / "hm"
    assert re.fullmatch(r"\d{8}-\d{4}-transcript\.md", t.path.name)
    text = t.path.read_text(encoding="utf-8")
    assert text.startswith("# Mock interview: ML Engineer\n\n")
    assert "<!-- interview: acme/hm -->" in text
    assert '<!-- session: {"mode": "full"} -->' in text
    assert t.prior_elapsed == 0.0
    assert t.turns == []


def test_default_session_is_full(dirs):
    t = Transcript("acme/hm", "T")
    assert t.session == {"mode": "full"}
    assert read_transcript(t.path).session == {"mode": "full"}


def test_round_trip_with_timings(dirs):
    t = Transcript("acme/hm", "T", session={"mode": "drill", "topic": "CUDA", "minutes": 15})
    t.add("Interviewer", "Tell me about yourself.", at=0.0, duration=4.24)
    t.add("Candidate", "I build ML systems.", at=5.0, duration=12.36, pause=0.84)
    t.add("Candidate", "No timing on this one.")
    t.add("Interviewer", "Timed without pause.", at=20, duration=3)
    t.mark_elapsed(123.4)

    saved = read_transcript(t.path)
    assert saved.path == t.path
    assert saved.interview == "acme/hm"
    assert saved.session == {"mode": "drill", "topic": "CUDA", "minutes": 15}
    assert saved.elapsed_secs == 123.0  # written with no decimals
    assert [(x.speaker, x.text) for x in saved.turns] == [
        ("Interviewer", "Tell me about yourself."),
        ("Candidate", "I build ML systems."),
        ("Candidate", "No timing on this one."),
        ("Interviewer", "Timed without pause."),
    ]
    first, answer, untimed, last = saved.turns
    assert (first.at, first.duration, first.pause) == (0.0, 4.2, None)
    assert (answer.at, answer.duration, answer.pause) == (5.0, 12.4, 0.8)
    assert (untimed.at, untimed.duration, untimed.pause) == (None, None, None)
    assert (last.at, last.duration, last.pause) == (20.0, 3.0, None)
    assert saved.lines == t.lines


def test_timing_comment_format(dirs):
    t = Transcript("acme/hm", "T")
    t.add("Candidate", "Answer.", at=61.25, duration=9.0, pause=1.5)
    assert "**Candidate:** Answer.\n<!-- at 61.2 s, 9.0 s, pause 1.5 s -->\n\n" in t.path.read_text(encoding="utf-8")


def test_add_ignores_empty_text_and_strips(dirs):
    t = Transcript("acme/hm", "T")
    t.add("Candidate", "   ")
    t.add("Candidate", None)
    t.add("Candidate", "  hello  ")
    assert t.lines == ["**Candidate:** hello"]
    assert t.text() == "**Candidate:** hello"
    assert [x.text for x in read_transcript(t.path).turns] == ["hello"]


def test_text_joins_lines(dirs):
    t = Transcript("acme/hm", "T")
    t.add("Interviewer", "Q?")
    t.add("Candidate", "A.")
    assert t.text() == "**Interviewer:** Q?\n\n**Candidate:** A."


def test_multi_paragraph_turn_round_trip(dirs):
    t = Transcript("acme/hm", "T")
    t.add("Interviewer", "First paragraph.\n\nSecond paragraph.\n\nThird.")
    t.add("Candidate", "Short answer.")
    saved = read_transcript(t.path)
    assert [x.text for x in saved.turns] == ["First paragraph.\n\nSecond paragraph.\n\nThird.", "Short answer."]


def test_multi_paragraph_timed_turn_round_trip(dirs):
    t = Transcript("acme/hm", "T")
    t.add("Interviewer", "Part one.\n\nPart two?", at=1.0, duration=6.0)
    turn = read_transcript(t.path).turns[0]
    assert turn.text == "Part one.\n\nPart two?"
    assert (turn.at, turn.duration) == (1.0, 6.0)


def test_session_topic_with_double_dash(dirs):
    session = {"mode": "drill", "topic": "C++ --flags --> and {braces} — 中文", "minutes": 10}
    t = Transcript("acme/hm", "T", session=session)
    raw = t.path.read_text(encoding="utf-8")
    comment = re.search(r"<!-- session: (.*?) -->", raw).group(1)
    assert "--" not in comment  # would end the HTML comment early
    assert read_transcript(t.path).session == session


def test_resume_continues_same_file(dirs):
    t = Transcript("acme/hm", "Title", session={"mode": "drill", "topic": "x", "minutes": 20})
    t.add("Interviewer", "Q1", at=0, duration=2)
    t.add("Candidate", "A1", at=3, duration=4, pause=1)
    t.mark_elapsed(300)

    saved = read_transcript(t.path)
    resumed = Transcript("ignored", "Ignored title", session={"mode": "full"}, resume=saved)
    assert resumed.path == t.path
    assert resumed.prior_elapsed == 300.0
    assert resumed.session == {"mode": "drill", "topic": "x", "minutes": 20}
    assert resumed.lines == saved.lines
    assert resumed.turns is not saved.turns  # a copy, not the same list

    resumed.add("Interviewer", "Q2", at=301, duration=2)
    resumed.mark_elapsed(420)

    again = read_transcript(t.path)
    assert [x.text for x in again.turns] == ["Q1", "A1", "Q2"]
    assert again.elapsed_secs == 420.0
    raw = t.path.read_text(encoding="utf-8")
    assert raw.count("# Title") == 1 and "Ignored title" not in raw
    assert not (dirs.transcripts / "ignored").exists()


def test_last_elapsed_tag_wins(dirs):
    t = Transcript("acme/hm", "T")
    t.mark_elapsed(100)
    t.mark_elapsed(250.6)
    assert read_transcript(t.path).elapsed_secs == 251.0


def test_old_format_without_tags(dirs):
    path = dirs.transcripts / "acme" / "20261023-2130-transcript.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Mock interview\n\n**Interviewer:** Hi there.\n\n**Candidate:** Hello.\n\nSecond paragraph.\n\n",
                    encoding="utf-8")
    started = datetime(2026, 10, 23, 21, 30).timestamp()
    os.utime(path, (started + 600, started + 600))

    saved = read_transcript(path)
    assert saved.interview is None
    assert saved.session == {"mode": "full"}
    assert saved.elapsed_secs == pytest.approx(600)
    assert [(x.speaker, x.text) for x in saved.turns] == [
        ("Interviewer", "Hi there."), ("Candidate", "Hello.\n\nSecond paragraph.")]
    assert all(x.at is None and x.duration is None for x in saved.turns)


def test_headings_and_comments_are_not_turn_text(dirs):
    path = dirs.transcripts / "x-transcript.md"
    path.write_text("# Title\n\n**Interviewer:** Q\n\n## A heading\n\n<!-- elapsed: 12 s -->\n\n", encoding="utf-8")
    saved = read_transcript(path)
    assert [x.text for x in saved.turns] == ["Q"]
    assert saved.elapsed_secs == 12.0


def test_estimate_elapsed_bad_name_and_future_start(tmp_path):
    bad = tmp_path / "notes-transcript.md"
    bad.write_text("x", encoding="utf-8")
    assert _estimate_elapsed(bad) == 0.0

    future = tmp_path / "20991231-2359-transcript.md"
    future.write_text("x", encoding="utf-8")
    assert _estimate_elapsed(future) == 0.0  # never negative


def test_sibling():
    p = Path("transcripts/acme/hm/20261023-2130-transcript.md")
    assert sibling(p, "feedback") == p.with_name("20261023-2130-feedback.md")
    assert sibling(p, "scores", ".json") == p.with_name("20261023-2130-scores.json")


def test_turn_and_saved_lines():
    turns = [Turn("Interviewer", "Q"), Turn("Candidate", "A")]
    saved = SavedTranscript(path=Path("x"), interview=None, turns=turns, elapsed_secs=0)
    assert saved.lines == ["**Interviewer:** Q", "**Candidate:** A"]
    assert saved.session == {}


def test_patched_transcripts_dir_is_used(dirs):
    assert transcript.TRANSCRIPTS_DIR == dirs.transcripts
