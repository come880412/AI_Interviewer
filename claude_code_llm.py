"""Runs the interviewer brain through the Claude Code CLI instead of the Anthropic API.

Uses your Claude Code login (subscription), so no ANTHROPIC_API_KEY is needed. One `claude -p`
process stays open for the whole interview and keeps the conversation history itself; each turn
we only send the new candidate speech and time checks, and stream the reply text back.
"""

import asyncio
import glob
import json
import os
import platform
import shutil
import subprocess
import tempfile
import uuid

from loguru import logger

from pipecat.adapters.services.anthropic_adapter import AnthropicLLMAdapter
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    StartFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService
from pipecat.services.settings import LLMSettings

ON_WSL = platform.system() == "Linux" and "microsoft" in platform.release().lower()
# A CLI that sends no event for this long during a turn is treated as stuck and restarted.
EVENT_TIMEOUT_SECS = 60


def find_claude_cli() -> str:
    """CLAUDE_CODE_PATH, then `claude` on PATH, then the copy bundled with the VS Code extension."""
    path = os.getenv("CLAUDE_CODE_PATH") or shutil.which("claude")
    if path:
        return path
    home = os.path.expanduser("~")
    roots = glob.glob("/mnt/c/Users/*/.vscode/extensions") if ON_WSL else [os.path.join(home, ".vscode", "extensions")]
    found = []
    for root in roots:
        found += glob.glob(os.path.join(root, "anthropic.claude-code-*", "resources", "native-binary", "claude*"))

    def version(p: str):
        name = p.split("anthropic.claude-code-")[1].split(os.sep)[0].split("/")[0]
        return tuple(int(x) for x in name.split("-")[0].split(".") if x.isdigit())

    if not found:
        raise FileNotFoundError("Claude Code CLI not found. Install it, or set CLAUDE_CODE_PATH in .env.")
    return max(found, key=version)


def cli_path_arg(cli: str, path: str) -> str:
    """A Windows claude.exe launched from WSL needs Windows-style file paths."""
    if ON_WSL and cli.lower().endswith(".exe"):
        return subprocess.check_output(["wslpath", "-w", path], text=True).strip()
    return path


def base_cli_args(cli: str, model: str, system_prompt_file: str) -> list[str]:
    # No tools, no user settings/hooks/plugins/MCP: the interviewer only talks.
    return [
        cli, "-p",
        "--model", model,
        "--tools", "",
        "--setting-sources", "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--system-prompt-file", cli_path_arg(cli, system_prompt_file),
    ]


def write_prompt_file(text: str) -> str:
    fd, path = tempfile.mkstemp(prefix="interviewer-", suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def message_text(message) -> str:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


class ClaudeCodeLLMService(LLMService):
    """Drop-in replacement for AnthropicLLMService that talks to a persistent `claude -p` process."""

    adapter_class = AnthropicLLMAdapter

    def __init__(self, *, system_prompt: str, model: str = "claude-opus-5-5", cli_path: str | None = None,
                 stall_line: str = "Sorry, give me just a second.", **kwargs):
        # Sampling and turn-completion settings don't apply to the CLI.
        unsupported = dict.fromkeys(
            ["system_instruction", "temperature", "max_tokens", "top_p", "top_k", "frequency_penalty",
             "presence_penalty", "seed", "filter_incomplete_user_turns", "user_turn_completion_config"]
        )
        super().__init__(settings=LLMSettings(model=model, **unsupported), **kwargs)
        self._system_prompt = system_prompt
        self._stall_line = stall_line  # said aloud while a dead or stuck CLI is replaced
        self._model = model
        self._cli = cli_path or find_claude_cli()
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task | None = None
        self._events: asyncio.Queue = asyncio.Queue()
        self._prompt_file: str | None = None
        self._sent_index = 0  # context messages already handed to the CLI
        self._pending_results = 0  # turns sent whose "result" event we have not read yet
        self._spoke = False  # whether the current turn has pushed any reply text

    async def start(self, frame: StartFrame):
        await super().start(frame)
        self._prompt_file = write_prompt_file(self._system_prompt)
        await self._launch()

    async def _launch(self):
        args = base_cli_args(self._cli, self._model, self._prompt_file) + [
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        logger.info(f"{self}: starting Claude Code CLI ({self._cli})")
        self._proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tempfile.gettempdir(),  # keep project CLAUDE.md files out of the interviewer's context
            limit=2**24,
        )
        self._reader = asyncio.create_task(self._read_events())

    async def stop(self, frame: EndFrame):
        await self._shutdown()
        await super().stop(frame)

    async def cancel(self, frame: CancelFrame):
        await self._shutdown()
        await super().cancel(frame)

    async def _shutdown(self):
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.stdin.close()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError, BrokenPipeError):
                self._proc.kill()
        if self._reader:
            self._reader.cancel()
        if self._prompt_file and os.path.exists(self._prompt_file):
            os.remove(self._prompt_file)
        self._proc = None

    async def _read_events(self):
        # Runs outside the frame-processing task, so an interruption never leaves stdout half-read.
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                err = (await self._proc.stderr.read()).decode(errors="replace").strip()
                await self._events.put({"type": "eof", "stderr": err})
                return
            try:
                await self._events.put(json.loads(line))
            except json.JSONDecodeError:
                logger.debug(f"{self}: non-JSON CLI output: {line[:200]!r}")

    async def _next_event(self) -> dict:
        try:
            event = await asyncio.wait_for(self._events.get(), timeout=EVENT_TIMEOUT_SECS)
        except asyncio.TimeoutError:
            raise RuntimeError(f"Claude Code CLI sent nothing for {EVENT_TIMEOUT_SECS} s")
        if event["type"] == "eof":
            raise RuntimeError(f"Claude Code CLI exited: {event['stderr'][-1000:] or 'no stderr'}")
        return event

    async def _relaunch(self):
        """Replaces a dead or stuck CLI with a fresh one, which starts with no conversation history."""
        if self._proc and self._proc.returncode is None:
            self._proc.kill()
        if self._reader:
            self._reader.cancel()
        self._events = asyncio.Queue()
        self._pending_results = 0
        await self._launch()

    @staticmethod
    def _history(context: LLMContext, upto: int) -> str:
        """The conversation before the new input, for a fresh CLI that has not seen it."""
        names = {"user": "Candidate", "assistant": "You (interviewer)", "developer": "Software note"}
        lines = []
        for m in context.get_messages()[:upto]:
            role = m.get("role") if isinstance(m, dict) else None
            text = message_text(m).strip()
            if role in names and text:
                lines.append(f"{names[role]}: {text}")
        return "\n\n".join(lines)

    def _send(self, obj: dict):
        self._proc.stdin.write((json.dumps(obj) + "\n").encode())

    def _new_input(self, context: LLMContext) -> str:
        # The CLI remembers what it said, so only candidate speech and developer notes are new to it.
        messages = context.get_messages()
        new = messages[self._sent_index :]
        self._sent_index = len(messages)
        parts = [message_text(m) for m in new if isinstance(m, dict) and m.get("role") in ("user", "developer")]
        return "\n\n".join(p.strip() for p in parts if p and p.strip())

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMContextFrame):
            await self._process_context(frame.context)
        else:
            await self.push_frame(frame, direction)

    async def _run_turn(self, text: str):
        """Sends one input and streams the reply; self._spoke records whether any reply text was pushed."""
        # Skip what is left of a reply that was interrupted earlier.
        while self._pending_results:
            if (await self._next_event())["type"] == "result":
                self._pending_results -= 1

        await self.start_ttfb_metrics()
        self._send({"type": "user", "message": {"role": "user", "content": text}})
        await self._proc.stdin.drain()
        self._pending_results += 1

        while True:
            event = await self._next_event()
            if event["type"] == "stream_event":
                e = event["event"]
                if e.get("type") == "content_block_delta" and e["delta"].get("type") == "text_delta":
                    await self.stop_ttfb_metrics()
                    await self.push_frame(LLMTextFrame(e["delta"]["text"]))
                    self._spoke = True
            elif event["type"] == "result":
                self._pending_results -= 1
                if event.get("is_error"):
                    logger.warning(f"{self}: CLI turn ended with {event.get('subtype')}: {event.get('result')}")
                return

    async def _process_context(self, context: LLMContext):
        before = self._sent_index
        text = self._new_input(context)
        if not text:
            return

        await self.push_frame(LLMFullResponseStartFrame())
        await self.start_processing_metrics()
        self._spoke = False
        try:
            try:
                await self._run_turn(text)
            except RuntimeError as e:
                # The CLI died or hung. Cover the gap out loud, start a fresh CLI with the whole
                # conversation so far, and try once more.
                logger.warning(f"{self}: {e}; restarting the CLI and retrying once")
                if not self._spoke:
                    await self.push_frame(LLMTextFrame(self._stall_line + " "))
                await self._relaunch()
                recovery = (
                    "[software note] The interview software restarted and you lost your memory of the conversation. "
                    "Here is everything so far; continue naturally from the latest input without mentioning the restart.\n\n"
                    f"{self._history(context, before)}\n\nLatest input:\n{text}"
                )
                await self._run_turn(recovery)
        except asyncio.CancelledError:
            # The candidate interrupted: stop generating so the next turn starts promptly.
            if self._proc and self._proc.returncode is None:
                self._send({"type": "control_request", "request_id": uuid.uuid4().hex, "request": {"subtype": "interrupt"}})
            raise
        except Exception as e:
            await self.push_error(error_msg=f"Claude Code CLI error: {e}", exception=e)
        finally:
            await self.stop_processing_metrics()
            await self.push_frame(LLMFullResponseEndFrame())


async def run_once(prompt: str, model: str, system_prompt: str = "", cli_path: str | None = None) -> str:
    """One-shot completion through the CLI (used for the feedback report)."""
    cli = cli_path or find_claude_cli()
    prompt_file = write_prompt_file(system_prompt or "You are a helpful assistant.")
    try:
        proc = await asyncio.create_subprocess_exec(
            *base_cli_args(cli, model, prompt_file), "--output-format", "json",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tempfile.gettempdir(),
        )
        out, err = await proc.communicate(prompt.encode("utf-8"))
    finally:
        os.remove(prompt_file)
    if proc.returncode != 0:
        raise RuntimeError(f"Claude Code CLI failed: {err.decode(errors='replace')[-1000:] or out.decode()[-1000:]}")
    result = json.loads(out)
    if result.get("is_error"):
        raise RuntimeError(f"Claude Code CLI error: {result.get('result')}")
    return result["result"]
