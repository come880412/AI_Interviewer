from pipecat.processors.aggregators.llm_context import LLMContext

from claude_code_llm import ClaudeCodeLLMService, message_text


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
