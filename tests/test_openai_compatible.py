"""LLM_BACKEND=openai: messages any OpenAI-compatible server accepts, and one-shot completions."""

import asyncio
from types import SimpleNamespace

from interviewer import llm
from interviewer.openai_compatible import OpenAICompatibleLLMService, merge_consecutive


def test_merge_consecutive():
    messages = [
        {"role": "system", "content": "You are Alex."},
        {"role": "user", "content": "[time check] The candidate has joined."},
        {"role": "user", "content": "Hi."},
        {"role": "assistant", "content": "Hello."},
        {"role": "user", "content": [{"type": "text", "text": "multimodal"}]},  # not plain text: kept apart
        {"role": "user", "content": "Plain."},
    ]
    assert merge_consecutive(messages) == [
        {"role": "system", "content": "You are Alex."},
        {"role": "user", "content": "[time check] The candidate has joined.\n\nHi."},
        {"role": "assistant", "content": "Hello."},
        {"role": "user", "content": [{"type": "text", "text": "multimodal"}]},
        {"role": "user", "content": "Plain."},
    ]


def test_developer_notes_go_out_as_user_messages():
    service = OpenAICompatibleLLMService(api_key="x", settings=OpenAICompatibleLLMService.Settings(model="m"))
    assert service.supports_developer_role is False
    params = service.build_chat_completion_params({"messages": [
        {"role": "user", "content": "[time check] 5 minutes left."}, {"role": "user", "content": "Done."}]})
    assert params["model"] == "m" and params["stream"] is True
    assert params["messages"] == [{"role": "user", "content": "[time check] 5 minutes left.\n\nDone."}]


def test_complete_with_the_openai_backend(monkeypatch):
    sent = {}

    class Completions:
        async def create(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="the report"))])

    class Client:
        chat = SimpleNamespace(completions=Completions())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            sent["closed"] = True

    monkeypatch.setattr(llm, "LLM_BACKEND", "openai")
    monkeypatch.setattr(llm, "openai_client", Client)
    assert asyncio.run(llm.complete("Write the report.", "qwen3:32b")) == "the report"
    assert sent == {"model": "qwen3:32b", "messages": [{"role": "user", "content": "Write the report."}], "closed": True}


def test_openai_client_reads_the_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = llm.openai_client()
    assert str(client.base_url).startswith("http://localhost:11434/v1") and client.api_key == "not-needed"
