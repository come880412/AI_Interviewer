"""The interviewer on any OpenAI-compatible API (LLM_BACKEND=openai): OpenAI, or a local server such as Ollama,
LM Studio or vLLM through OPENAI_BASE_URL.

Time checks and notepad updates reach the interviewer as "developer" messages, which many local servers and chat
templates reject; they are sent as user messages instead, merged with the candidate's words, since some templates
also require user and assistant turns to alternate.
"""

from pipecat.services.openai.llm import OpenAILLMService


def merge_consecutive(messages: list[dict]) -> list[dict]:
    """Joins neighboring messages from the same role into one, when both are plain text."""
    merged: list[dict] = []
    for m in messages:
        last = merged[-1] if merged else None
        if (last and last.get("role") == m.get("role") and isinstance(last.get("content"), str)
                and isinstance(m.get("content"), str) and set(last) == set(m) == {"role", "content"}):
            merged[-1] = {"role": m["role"], "content": f"{last['content']}\n\n{m['content']}"}
        else:
            merged.append(dict(m))
    return merged


class OpenAICompatibleLLMService(OpenAILLMService):
    supports_developer_role = False

    def build_chat_completion_params(self, params_from_context) -> dict:
        params = super().build_chat_completion_params(params_from_context)
        params["messages"] = merge_consecutive(list(params["messages"]))
        return params
