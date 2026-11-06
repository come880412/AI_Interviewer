import asyncio
import sys

import pytest
from pipecat.processors.aggregators.llm_context import LLMContext

from interviewer.claude_code import ClaudeCodeLLMService, check_cli, cli_env, message_text, run_once, write_prompt_file


def context():
    return LLMContext(messages=[
        {"role": "developer", "content": "[time check] The candidate has joined."},
        {"role": "assistant", "content": [{"type": "text", "text": "Hi, I'm Dana."}, {"type": "image", "source": {}}]},
        {"role": "user", "content": "  Hello!  "},
        {"role": "system", "content": "ignored role"},
        {"role": "user", "content": "   "},  # empty after stripping
        {"role": "assistant", "content": [{"type": "text", "text": "Part one."}, {"type": "text", "text": "Part two."}]},
        {"role": "user", "content": "Latest answer."},
    ])


def test_history_formats_roles_and_skips_others():
    assert ClaudeCodeLLMService._history(context(), 6) == (
        "Software note: [time check] The candidate has joined.\n\n"
        "You (interviewer): Hi, I'm Dana.\n\n"
        "Candidate: Hello!\n\n"
        "You (interviewer): Part one.\nPart two."
    )


def test_history_stops_before_upto():
    assert ClaudeCodeLLMService._history(context(), 0) == ""
    assert ClaudeCodeLLMService._history(context(), 1) == "Software note: [time check] The candidate has joined."
    assert ClaudeCodeLLMService._history(context(), 100).endswith("Candidate: Latest answer.")


def test_message_text():
    assert message_text({"content": "plain"}) == "plain"
    assert message_text({"content": [{"type": "text", "text": "a"}, "junk", {"type": "text"}]}) == "a\n"
    assert message_text({"content": None}) == ""
    assert message_text("not a dict") == ""


def test_the_cli_never_sees_the_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-...")
    monkeypatch.setenv("OTHER_SETTING", "kept")
    env = cli_env()
    assert "ANTHROPIC_API_KEY" not in env and env["OTHER_SETTING"] == "kept"


# ----- Fake CLIs: Python scripts that speak just enough stream-json -----

ANSWER = ('print(json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", '
          '"delta": {"type": "text_delta", "text": "Hello."}}}), flush=True)\n'
          'print(json.dumps({"type": "result", "is_error": False}), flush=True)\n')


def fake_cli(tmp_path, body: str) -> str:
    path = tmp_path / "claude"
    path.write_text(f"#!{sys.executable}\nimport json, sys, time\n{body}")
    path.chmod(0o755)
    return str(path)


def service(cli: str):
    s = ClaudeCodeLLMService(system_prompt="x", cli_path=cli)
    s.pushed, s.errors, s.relaunches = [], [], 0

    async def push_frame(frame, *args):
        s.pushed.append(getattr(frame, "text", None))

    async def push_error(error_msg=None, exception=None, **kwargs):
        s.errors.append(error_msg)

    async def nothing(*args, **kwargs):
        pass

    relaunch = s._relaunch

    async def counted_relaunch():
        s.relaunches += 1
        await relaunch()

    s.push_frame, s.push_error, s._relaunch = push_frame, push_error, counted_relaunch
    s.start_ttfb_metrics = s.stop_ttfb_metrics = s.start_processing_metrics = s.stop_processing_metrics = nothing
    s._prompt_file = write_prompt_file("x")
    return s


def test_a_cli_that_died_between_turns_is_replaced(tmp_path):
    # Answers one turn, then exits: the next turn's write hits a closed pipe.
    s = service(fake_cli(tmp_path, f"sys.stdin.readline()\n{ANSWER}sys.exit(1)\n"))

    async def run():
        await s._launch()
        context = LLMContext(messages=[{"role": "user", "content": "one"}])
        await s._process_context(context)
        await s._proc.wait()
        context.add_message({"role": "user", "content": "two"})
        await s._process_context(context)
        await s._shutdown()

    asyncio.run(run())
    assert s.relaunches == 1 and not s.errors
    assert s.pushed.count("Hello.") == 2


def test_a_failed_turn_with_no_reply_is_retried_then_reported(tmp_path):
    s = service(fake_cli(tmp_path, 'for line in sys.stdin:\n'
                                   '    print(json.dumps({"type": "result", "is_error": True, "result": "Not logged in"}), flush=True)\n'))

    async def run():
        await s._launch()
        await s._process_context(LLMContext(messages=[{"role": "user", "content": "one"}]))
        await s._shutdown()

    asyncio.run(run())
    assert s.relaunches == 1
    assert len(s.errors) == 1 and "Not logged in" in s.errors[0]


def test_run_once_gives_up_on_a_hung_cli(tmp_path):
    cli = fake_cli(tmp_path, "time.sleep(30)\n")
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(run_once("hi", "model", cli_path=cli, timeout=0.5))


def test_check_cli_reports_the_problem(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_PATH", fake_cli(tmp_path, 'sys.stdin.read()\nprint("Invalid API key", file=sys.stderr)\nsys.exit(1)\n'))
    assert "Invalid API key" in check_cli("model")
    monkeypatch.setenv("CLAUDE_CODE_PATH", fake_cli(tmp_path, 'sys.stdin.read()\nprint(json.dumps({"result": "ok"}))\n'))
    assert check_cli("model") is None
