"""One-shot completions for jobs with no latency pressure (feedback report, resume import, drafts).

Uses the same backend as the interviewer: LLM_BACKEND=claude_code (default), api (Anthropic API), or openai (any
OpenAI-compatible API: OpenAI, or Ollama, LM Studio, vLLM, OpenRouter... through OPENAI_BASE_URL).
"""

import os

from anthropic import AsyncAnthropic

from interviewer import settings  # noqa: F401  (loads .env before the settings below are read)
from interviewer.claude_code import run_once

LLM_BACKEND = os.getenv("LLM_BACKEND", "claude_code").lower()


def openai_client():
    from openai import AsyncOpenAI

    # Local servers such as Ollama ignore the key but the client requires one.
    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY") or "not-needed", base_url=os.getenv("OPENAI_BASE_URL") or None)


async def complete(prompt: str, model: str) -> str:
    if LLM_BACKEND == "openai":
        # Closed here, inside the event loop that made it (asyncio.run would otherwise close the loop first).
        async with openai_client() as client:
            reply = await client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
        return reply.choices[0].message.content or ""
    if LLM_BACKEND == "api":
        client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        # No latency pressure here, so let the model think as much as it needs.
        async with client.messages.stream(
            model=model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = await stream.get_final_message()
        return "".join(block.text for block in message.content if block.type == "text")
    return await run_once(prompt, model)
