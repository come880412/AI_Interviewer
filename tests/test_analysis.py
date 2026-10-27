import pytest

from analysis import answers, delivery_summary
from transcript import Turn


def I(text, at=None, duration=None):
    return Turn("Interviewer", text, at, duration)


def C(text, at=None, duration=None, pause=None):
    return Turn("Candidate", text, at, duration, pause)


def test_answers_groups_consecutive_candidate_turns():
    turns = [
        I("Q1?", 0, 5),
        C("first part", 6, 10, pause=1.0),
        C("second part here", 17, 5, pause=0.3),
        I("Q2?", 23, 3),
        C("untimed answer"),
        I("Q3?", 40, 2),
        C("short", 43, 2),
    ]
    result = answers(turns)
    assert len(result) == 2  # the untimed answer to Q2 is skipped
    a1, a3 = result
    assert a1.question == "Q1?"
    assert a1.text == "first part second part here"
    assert a1.seconds == pytest.approx(16)  # 17 + 5 - 6
    assert a1.pause == 1.0  # the pause before the first part
    assert a1.words == 5
    assert (a3.question, a3.seconds, a3.pause, a3.words) == ("Q3?", 2, None, 1)


def test_answers_before_any_question_and_mixed_timing():
    turns = [C("hello", 1, 2), I("Q", 5, 1), C("untimed start"), C("timed end", 10, 4)]
    result = answers(turns)
    assert [a.question for a in result] == ["", "Q"]
    assert result[1].text == "untimed start timed end"
    assert result[1].seconds == 4  # measured over the timed turns only
    assert answers([]) == []


def test_delivery_summary_without_timings():
    expected = "No turn timings were recorded for this transcript, so judge delivery from the text only."
    assert delivery_summary([]) == expected
    assert delivery_summary([I("Q"), C("an answer")]) == expected


def test_delivery_summary_full():
    long_answer = " ".join(["word"] * 300)  # 300 words in 150 s = 120 wpm
    turns = [
        I("Why this company?", 0, 4),
        C(long_answer, 5, 150, pause=2.0),
        I("Any questions?", 160, 2),
        C("a b c d e f g h i j", 163, 10, pause=0.5),  # 10 words in 10 s = 60 wpm
        I("Last one?", 180, 2),
        C("yes", 183, 3),  # under 15 s, no pause, too short for a rate
    ]
    text = delivery_summary(turns)
    lines = text.splitlines()
    assert lines[0] == "Answers timed: 3"
    assert lines[1] == 'Answer length: median 10 s, longest 150 s (to the question: "Why this company?")'
    assert lines[2] == "Answers over 2 minutes: 1; under 15 seconds: 2"
    assert lines[3].startswith("Speaking rate: median 90 words per minute")
    assert lines[4] == 'Pause before answering: median 1.2 s, longest 2.0 s (to the question: "Why this company?")'
    assert lines[5].startswith("Timings are approximate")


def test_delivery_summary_omits_rate_and_pause_when_unavailable():
    text = delivery_summary([I("Q", 0, 1), C("quick", 2, 5)])
    assert "Answers timed: 1" in text
    assert "Speaking rate" not in text
    assert "Pause before answering" not in text


def test_delivery_summary_truncates_long_question():
    question = "x" * 200
    text = delivery_summary([I(question, 0, 1), C("answer", 2, 5)])
    assert f'"{"x" * 120}"' in text and "x" * 121 not in text


def test_delivery_summary_zero_pause_with_missing_pause():
    turns = [I("Q1", 0, 1), C("first", 2, 5), I("Q2", 10, 1), C("second", 12, 5, pause=0.0)]
    assert "longest 0.0 s" in delivery_summary(turns)


def test_speaking_rate_counts_chinese_characters():
    turns = [
        Turn("Interviewer", "請介紹一下你的專案。", 0, 5),
        Turn("Candidate", "我做的是倉儲機器人的 CNN 偵測模型", 6, 12, pause=1.0),
    ]
    (a,) = answers(turns)
    assert a.words == 15  # fourteen characters and "CNN"
    summary = delivery_summary(turns)
    assert "units per minute, counting each Chinese character and each English word as one" in summary
