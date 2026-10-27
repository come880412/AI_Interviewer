"""bot.py helpers. Importing bot only reads environment variables; nothing is started."""

import asyncio

import pytest

import bot
from transcript import Transcript


def test_time_checks_full_interview():
    checks = bot.time_checks(30)
    assert [at for at, _ in checks] == [900, 1380, 1800]  # half, max(75%, 7 min before the end), end
    assert "half" in checks[0][1]
    assert "candidate's questions" in checks[1][1]
    assert "Time is up" in checks[2][1]
    assert all(note.startswith("[time check]") for _, note in checks)


def test_time_checks_short_drill():
    checks = bot.time_checks(10, drill=True)
    assert [at for at, _ in checks] == [300, 450, 600]  # 75% is later than 7 minutes before the end
    assert "wrap up the drill" in checks[1][1]


def test_time_checks_are_in_order():
    for minutes in (5, 15, 30, 45, 60, 90):
        times = [at for at, _ in bot.time_checks(minutes)]
        assert times == sorted(times)


def test_session_mode():
    assert bot.session_mode({"mode": "full"}, 45) == (
        "This is a full mock interview of about 45 minutes. Follow the interview structure below.")
    assert bot.session_mode({}, 30).startswith("This is a full mock interview of about 30 minutes")
    drill = bot.session_mode({"mode": "drill", "topic": "CUDA streams"}, 15)
    assert drill.startswith("This is a focused practice drill of about 15 minutes on: CUDA streams.")
    assert "Skip the candidate's questions section" in drill
    assert "Coach mode" not in drill


def test_session_mode_coach():
    coached = bot.session_mode({"mode": "drill", "topic": "CUDA streams", "coach": True}, 15)
    assert coached.startswith("This is a focused practice drill of about 15 minutes on: CUDA streams.")
    assert "Coach mode is on" in coached
    # Coaching only applies to drills.
    assert "Coach mode" not in bot.session_mode({"mode": "full", "coach": True}, 45)


def test_selection_session_coach():
    from session_picker import Selection
    assert Selection(".", mode="drill", topic="t", minutes=10).session() == {"mode": "drill", "topic": "t", "minutes": 10}
    assert Selection(".", mode="drill", topic="t", minutes=10, coach=True).session()["coach"] is True
    assert Selection(".", coach=True).session() == {"mode": "full"}


@pytest.mark.parametrize("text, expected, ended", [
    ("Thanks, goodbye! [[END]]", "Thanks, goodbye! ", True),
    ("Bye [[ end ]]", "Bye [[ end ]]", False),  # the token is case sensitive
    ("Bye [[  END  ]] now", "Bye  now", True),
    ("Let's continue.", "Let's continue.", False),
])
def test_end_token_filter(text, expected, ended):
    calls = []
    f = bot.EndTokenFilter(lambda: calls.append(1))
    assert asyncio.run(f.filter(text)) == expected
    assert bool(calls) == ended


def test_resume_note(dirs):
    t = Transcript("acme/hm", "T")
    t.add("Interviewer", "Tell me about yourself.", at=0, duration=3)
    t.add("Candidate", "I build ML systems.", at=4, duration=10, pause=1)
    t.prior_elapsed = 15 * 60 + 40

    note = bot.resume_note(t, 30, [])
    assert note.startswith("[time check] The connection dropped")
    assert "About 16 of 30 minutes have been used." in note
    assert note.endswith("Transcript so far:\n\n**Interviewer:** Tell me about yourself.\n\n**Candidate:** I build ML systems.")

    passed = [note for at, note in bot.time_checks(30) if at <= t.prior_elapsed]
    with_check = bot.resume_note(t, 30, passed)
    assert "\n[time check] About half of the time has passed.\n\nTranscript so far:" in with_check


def test_language_rule():
    assert bot.language_rule("en") == (
        "Conduct the interview in English. If the candidate switches languages, continue in English.")
    zh = bot.language_rule("zh-TW")
    assert zh.startswith("Conduct the interview in Mandarin Chinese")
    assert "Traditional Chinese" in zh and "never Simplified" in zh
