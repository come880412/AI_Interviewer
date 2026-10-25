"""One-shot Claude completions for jobs with no latency pressure (feedback report, resume import).

Uses the same backend as the interviewer: LLM_BACKEND=claude_code (default) or api.
"""

import os

from anthropic import AsyncAnthropic

from claude_code_llm import run_once

LLM_BACKEND = os.getenv("LLM_BACKEND", "claude_code").lower()


async def complete(prompt: str, model: str) -> str:
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
