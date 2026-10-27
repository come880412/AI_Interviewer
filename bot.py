"""AI mock interviewer: local Whisper STT -> Claude -> local Kokoro TTS, over WebRTC.

Run:  python bot.py [--interview NAME] [--resume TRANSCRIPT]    then open http://localhost:7860/
"""

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionWorkerFrame,
    LLMRunFrame,
    TTSAudioRawFrame,
)
from pipecat.metrics.metrics import TurnMetricsData
from pipecat.observers.loggers.metrics_log_observer import MetricsLogObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
    UserTurnStoppedMessage,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.kokoro.tts import KokoroTTSService
from pipecat.services.whisper.stt import Model as WhisperModel
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.utils.text.base_text_filter import BaseTextFilter
from pipecat.workers.runner import WorkerRunner

import session_picker
from chinese import tidy_spaces
from claude_code_llm import ClaudeCodeLLMService
from history import practice_history
from interview_config import InterviewConfig, interview_name, pick_interview, validate
from session_picker import ActiveSession, Selection
from transcript import Transcript, read_transcript
from stt_common import save_wav
from whisper_stt import DEFAULT_MIN_AVG_LOGPROB, InterviewWhisperSTT

load_dotenv(override=True)

LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5-5")
# "claude_code" runs Claude through your Claude Code login (no API key); "api" uses ANTHROPIC_API_KEY.
LLM_BACKEND = os.getenv("LLM_BACKEND", "claude_code").lower()
# "off" keeps replies fast; "adaptive" lets Claude think before follow-ups (better probing, slower).
THINKING = os.getenv("INTERVIEWER_THINKING", "off").lower()
# Full large-v3 handles accented English noticeably better than the distilled turbo model.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", WhisperModel.LARGE.value)
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
# Whisper segments decoded below this average log-probability are dropped as likely hallucinations.
# Lower it (e.g. -1.3) if real words go missing; dropped segments are logged.
WHISPER_MIN_AVG_LOGPROB = float(os.getenv("WHISPER_MIN_AVG_LOGPROB", str(DEFAULT_MIN_AVG_LOGPROB)))
# "whisper" (faster-whisper, takes hotwords as a prompt) or "parakeet" (NVIDIA Parakeet TDT v3: faster, and
# re-transcribes each whole answer for the transcript). Compare them on your own voice with compare_stt.py.
STT_BACKEND = os.getenv("STT_BACKEND", "whisper").lower()
# Save each answer's audio next to the transcript, for compare_stt.py. Off by default: it is your voice.
SAVE_CANDIDATE_AUDIO = os.getenv("SAVE_CANDIDATE_AUDIO", "false").lower() == "true"
AUTO_FEEDBACK = os.getenv("AUTO_FEEDBACK", "true").lower() == "true"
# Silence before Smart Turn even checks whether the candidate is done. Pipecat's 0.2s default ends the
# turn at every pause between sentences; raise it if the interviewer still cuts in, lower it for snappier replies.
CANDIDATE_PAUSE_SECS = float(os.getenv("CANDIDATE_PAUSE_SECS", "0.8"))
# The TTS voices come out around -28 LUFS, much quieter than typical speech audio; boost before sending.
VOICE_GAIN_DB = float(os.getenv("VOICE_GAIN_DB", "10"))

VOICE_LANGUAGES = {"en-us": Language.EN_US, "en-gb": Language.EN_GB}
# Traditional characters and English terms in the prompt steer Whisper toward the same in its output.
CHINESE_STT_PROMPT = "以下是一場中文技術面試的回答，夾雜英文術語，例如 GRU、MLP、INT8、latency。"
# The interviewer ends its goodbye with this token (see prompts/interviewer.md); it is never spoken.
END_TOKEN = re.compile(r"\[\[\s*END\s*\]\]")
# After the goodbye, how long to wait for the audio to finish before hanging up anyway.
END_GRACE_SECS = 20

# Only the local WebRTC transport is used; the runner serves its prebuilt UI at /client.
transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


class VolumeBoost(FrameProcessor):
    """Amplifies the interviewer's voice, with a soft limiter so loud peaks round off instead of clipping."""

    KNEE = 0.8  # samples below this level (full scale = 1.0) pass through unchanged

    def __init__(self, gain_db: float):
        super().__init__()
        self._gain = 10 ** (gain_db / 20)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame) and self._gain != 1:
            x = np.frombuffer(frame.audio, np.int16).astype(np.float32) * (self._gain / 32768)
            over = np.abs(x) > self.KNEE
            x[over] = np.sign(x[over]) * (self.KNEE + (1 - self.KNEE) * np.tanh((np.abs(x[over]) - self.KNEE) / (1 - self.KNEE)))
            frame.audio = (x * 32767).astype(np.int16).tobytes()
        await self.push_frame(frame, direction)


class EndTokenFilter(BaseTextFilter):
    """Strips the end token before speech and reports that the interviewer has said goodbye."""

    def __init__(self, on_end):
        self._on_end = on_end

    async def filter(self, text: str) -> str:
        if END_TOKEN.search(text):
            self._on_end()
            text = END_TOKEN.sub("", text)
        return text


class MicGate(FrameProcessor):
    """Drops the candidate's audio while the interview is paused, so nothing is heard or transcribed."""

    def __init__(self):
        super().__init__()
        self.closed = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if self.closed and isinstance(frame, InputAudioRawFrame):
            return
        await self.push_frame(frame, direction)


class SpeechClock(FrameProcessor):
    """Watches the interviewer's audio: whether it is speaking, and when it last stopped."""

    def __init__(self):
        super().__init__()
        self.speaking = False
        self.last_stopped: float | None = None  # time.monotonic()
        self.on_stopped = None  # async callback

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, BotStartedSpeakingFrame):
            self.speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self.speaking = False
            self.last_stopped = time.monotonic()
            if self.on_stopped:
                await self.on_stopped()
        await self.push_frame(frame, direction)


def time_checks(duration_min: int, drill: bool = False) -> list[tuple[float, str]]:
    """Returns (seconds_after_start, note) pairs that nudge Claude to keep to time."""
    wrap_at = max(duration_min * 0.75, duration_min - 7) * 60
    wrap_note = (
        "[time check] Time is running short. Finish the current question, then wrap up the drill."
        if drill
        else "[time check] Time is running short. Finish the current topic, then move on to the candidate's questions."
    )
    return [
        (duration_min * 0.5 * 60, "[time check] About half of the time has passed."),
        (wrap_at, wrap_note),
        (duration_min * 60, "[time check] Time is up. Close at the next natural point."),
    ]


COACH_MODE = (
    "\n\nCoach mode is on: the candidate wants feedback after every answer, so this overrides the rules below "
    "about never teaching, coaching, hinting, praising, or judging, and about keeping turns to three sentences. "
    "After each complete answer, step out of the interviewer role briefly and coach in plain speech, in about four "
    "to six sentences: say what worked in one sentence, name the most important thing that was missing or wrong "
    "(a technical error, a missing number or result, unclear ownership, no trade-off), then give a short model "
    "version of the key part, using the candidate's own experience from the resume where it fits. Then ask them to "
    "try that part again. After the retry, give one sentence on whether it improved and move on to the next "
    "question; do not ask for a third attempt. If the candidate is stuck, give a hint first, and the answer only if "
    "the hint does not help. When an answer is already solid, say so in one sentence and move on."
)


def language_rule(language: str) -> str:
    """The language line of the interviewer prompt."""
    if language == "zh-TW":
        return (
            "Conduct the interview in Mandarin Chinese, written in Traditional Chinese characters with the wording "
            "used in Taiwan, never Simplified Chinese or mainland-only terms. Keep technical terms, product names and "
            "acronyms in English the way Taiwanese engineers say them, for example GRU, INT8, latency, or trade-off. "
            "If the candidate switches to English, continue in Chinese."
        )
    return "Conduct the interview in English. If the candidate switches languages, continue in English."


def session_mode(session: dict, minutes: int) -> str:
    """The "Session mode" section of the interviewer prompt."""
    if session.get("mode") == "drill":
        return (
            f"This is a focused practice drill of about {minutes} minutes on: {session.get('topic')}. "
            "It replaces the interview structure below. Greet the candidate in one sentence and say you will focus "
            "on this topic today, skip self-introductions, then ask questions on this topic only, going from "
            "fundamentals to deeper follow-ups and connecting to the candidate's experience where it fits. Skip the "
            "candidate's questions section. When time is up, close in one or two sentences. The whole session is one "
            "topic, so the three-follow-up limit applies to each sub-question, not to the session: keep digging into "
            "new angles of the topic until time is up."
            + (COACH_MODE if session.get("coach") else "")
        )
    return f"This is a full mock interview of about {minutes} minutes. Follow the interview structure below."


def resume_note(transcript: Transcript, duration_min: int, passed: list[str]) -> str:
    """Tells Claude the interview was cut off, how much time is used, and everything said so far."""
    used = round(transcript.prior_elapsed / 60)
    note = (
        "[time check] The connection dropped and the candidate has rejoined the same interview. "
        f"About {used} of {duration_min} minutes have been used. Continue from where it stopped: "
        "welcome the candidate back in one short sentence without introducing yourself again. "
        "If your last question was not fully answered, ask it again; otherwise move on to the next "
        "topic you have not covered."
    )
    if passed:
        note += f"\n{passed[-1]}"
    return f"{note}\n\nTranscript so far:\n\n{transcript.text()}"


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    # Chosen on the web page at "/" (or from the command line); applies to this connection.
    selection = session_picker.selection or Selection(pick_interview(ask=False))
    cfg = InterviewConfig.load(selection.interview)
    v = cfg.variables
    # Re-read on every connection, so reconnecting again keeps extending the same transcript.
    saved = read_transcript(selection.resume) if selection.resume else None
    session = saved.session if saved else selection.session()
    drill = session.get("mode") == "drill"
    minutes = int(session.get("minutes") or cfg.duration_minutes) if drill else cfg.duration_minutes
    if saved:
        # Old transcripts estimate their length from file times, which can overshoot.
        saved.elapsed_secs = min(saved.elapsed_secs, minutes * 60)
    title = f"Mock interview: {v.get('role_title')} ({v.get('round_name')})"
    if drill:
        title += f", {'coached ' if session.get('coach') else ''}drill on {session.get('topic')}"
    transcript = Transcript(cfg.name, title, session=session, resume=saved)
    action = f"resuming at {transcript.prior_elapsed / 60:.0f} min" if saved else "new session"
    logger.info(f"Interview '{cfg.name}' ({action}, {'drill' if drill else 'full'}), transcript -> {transcript.path}")
    system_prompt = cfg.render(
        "interviewer.md",
        duration_minutes=str(minutes),
        session_mode=session_mode(session, minutes),
        practice_history=practice_history(cfg.name),
        language_rule=language_rule(cfg.language),
    )

    end_reason: str | None = None  # "interviewer" (said goodbye) or "candidate" (ended from the web page)
    end_task: asyncio.Task | None = None
    clock = SpeechClock()

    def interviewer_said_goodbye():
        nonlocal end_reason, end_task
        if end_reason:
            return
        end_reason = "interviewer"
        logger.info("Interviewer closed the interview; hanging up after the goodbye")
        end_task = asyncio.create_task(hang_up_after_goodbye())

    async def hang_up_after_goodbye():
        # Wait for the goodbye audio to finish (SpeechClock calls hang_up), or give up after a grace period.
        await asyncio.sleep(2)
        if not clock.speaking:
            await hang_up()
            return
        await asyncio.sleep(END_GRACE_SECS)
        await hang_up()

    hung_up = False

    async def hang_up():
        nonlocal hung_up
        if not hung_up:
            hung_up = True
            await worker.queue_frame(EndFrame())

    async def on_bot_stopped():
        if end_reason == "interviewer":
            await hang_up()

    clock.on_stopped = on_bot_stopped
    end_filter = EndTokenFilter(interviewer_said_goodbye)

    if STT_BACKEND == "parakeet" and cfg.chinese:
        logger.warning("Parakeet does not understand Chinese; using Whisper for this interview")
    if STT_BACKEND == "parakeet" and not cfg.chinese:
        # Imported here so the Whisper-only setup does not need onnx-asr.
        from parakeet_stt import ParakeetSTTService

        stt = ParakeetSTTService(hotwords=cfg.stt_hotwords, device=WHISPER_DEVICE)
    else:
        stt = InterviewWhisperSTT(
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
            min_avg_logprob=WHISPER_MIN_AVG_LOGPROB,
            hotword_list=cfg.stt_hotwords,
            chinese=cfg.chinese,
            settings=InterviewWhisperSTT.Settings(
                model=WHISPER_MODEL,
                language=Language.ZH if cfg.chinese else Language.EN,
                hotwords=" ".join(cfg.stt_hotwords) or None,
                # The first answer has no conversation to use as the prompt; this one sets the script and style.
                initial_prompt=CHINESE_STT_PROMPT if cfg.chinese else None,
            ),
        )
    audio_dir = transcript.path.with_name(transcript.path.name.replace("-transcript.md", "-audio"))

    if cfg.chinese:
        # Imported here so English-only setups do not need misaki and the Chinese model.
        from chinese_tts import DEFAULT_ZH_VOICE, ChineseKokoroTTSService

        if cfg.voice_clone or cfg.pocket_voice:
            logger.warning("Pocket TTS cannot speak Chinese; using the Kokoro Chinese voice instead")
        tts = ChineseKokoroTTSService(
            settings=ChineseKokoroTTSService.Settings(voice=cfg.voice if cfg.voice.startswith("z") else DEFAULT_ZH_VOICE),
            text_filters=[end_filter],
        )
    elif cfg.voice_clone or cfg.pocket_voice:
        # Imported here because it pulls in torch, which slows startup when Pocket TTS is not used.
        from pipecat.services.pocket_tts.tts import PocketTTSService

        # A reference recording to clone, or the name of one of Pocket TTS's built-in voices.
        voice = str(cfg.voice_clone.resolve()) if cfg.voice_clone else cfg.pocket_voice
        tts = PocketTTSService(
            settings=PocketTTSService.Settings(voice=voice, language=Language.EN),
            text_filters=[end_filter],
        )
    else:
        tts = KokoroTTSService(
            settings=KokoroTTSService.Settings(
                voice=cfg.voice,
                language=VOICE_LANGUAGES.get(cfg.voice_language.lower(), Language.EN_US),
            ),
            text_filters=[end_filter],
        )

    if LLM_BACKEND == "api":
        thinking = AnthropicLLMService.ThinkingConfig(
            type="adaptive" if THINKING == "adaptive" else "disabled"
        )
        llm = AnthropicLLMService(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            settings=AnthropicLLMService.Settings(
                model=LLM_MODEL,
                system_instruction=system_prompt,
                # The JD, resume and question bank are re-sent every turn; caching makes that cheap and fast.
                enable_prompt_caching=True,
                max_tokens=4096 if THINKING == "adaptive" else 600,
                thinking=thinking,
            ),
        )
    else:
        llm = ClaudeCodeLLMService(system_prompt=system_prompt, model=LLM_MODEL,
                                   stall_line="不好意思，請稍等一下。" if cfg.chinese else "Sorry, give me just a second.")

    context = LLMContext()
    # VAD detects speech; the default turn strategy adds the local Smart Turn v3 model,
    # which waits through thinking pauses instead of cutting the candidate off.
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=CANDIDATE_PAUSE_SECS))
        ),
    )

    mic_gate = MicGate()
    pipeline = Pipeline(
        [
            transport.input(),
            mic_gate,
            stt,
            user_aggregator,
            llm,
            tts,
            VolumeBoost(VOICE_GAIN_DB),
            transport.output(),
            clock,
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        # No idle timeout: a paused interview is silent on purpose. Closing the page still ends it.
        idle_timeout_secs=None,
        # Logs per-turn latency so you can see whether STT, Claude or TTS is the bottleneck.
        observers=[MetricsLogObserver(include_metrics={TurnMetricsData})],
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    timer_task: asyncio.Task | None = None
    session_started: float | None = None
    checks = time_checks(minutes, drill)
    # Time checks the earlier sessions already passed are not repeated; the latest one goes in the resume note.
    passed = [note for at, note in checks if at <= transcript.prior_elapsed]
    notepad = ""  # latest contents of the shared notepad page
    paused_since: float | None = None  # time.monotonic() when the current pause began
    paused_total = 0.0  # seconds spent paused in this session

    def now() -> float:
        """Seconds of interview time, counting earlier sessions of a resumed interview and leaving out pauses."""
        pausing = time.monotonic() - paused_since if paused_since is not None else 0.0
        return transcript.prior_elapsed + (time.monotonic() - session_started) - paused_total - pausing

    async def pause():
        nonlocal paused_since
        if paused_since is not None or end_reason:
            return
        paused_since = time.monotonic()
        mic_gate.closed = True
        await worker.queue_frame(InterruptionWorkerFrame())  # stop the interviewer mid-sentence
        logger.info("Interview paused")

    async def resume():
        nonlocal paused_since, paused_total
        if paused_since is None:
            return
        away = time.monotonic() - paused_since
        paused_total += away
        paused_since = None
        mic_gate.closed = False
        logger.info(f"Interview resumed after {away / 60:.1f} min")
        context.add_message({
            "role": "developer",
            "content": f"[time check] The candidate paused the interview for about {max(1, round(away / 60))} minute(s) "
            "and is back. Welcome them back in one short sentence, then repeat or rephrase your last question "
            "if it was not fully answered; otherwise continue with the next one.",
        })
        await worker.queue_frames([LLMRunFrame()])

    async def end_from_page():
        nonlocal end_reason
        if not end_reason:
            end_reason = "candidate"
            logger.info("Interview ended from the web page")
        await hang_up()

    def update_notepad(text: str):
        nonlocal notepad
        if text.strip() == notepad.strip():
            return
        notepad = text
        # Added silently, like time checks: Claude reads it with the candidate's next answer.
        context.add_message({"role": "developer", "content": f"[notepad] The shared notepad now contains:\n{text}"})

    async def run_timer():
        # Polls the interview clock, which stands still while paused.
        for at, note in checks:
            if at <= transcript.prior_elapsed:
                continue
            while now() < at:
                await asyncio.sleep(1)
            # Added silently: Claude sees it on its next reply and is told never to read it aloud.
            context.add_message({"role": "developer", "content": note})
            logger.info(note)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        nonlocal timer_task, session_started
        session_started = time.monotonic()
        session_picker.active = ActiveSession(
            interview=cfg.name, transcript=transcript.path, session=session, minutes=minutes,
            elapsed=now, is_paused=lambda: paused_since is not None, pause=pause, resume=resume,
            end=end_from_page, update_notepad=update_notepad,
        )
        if saved:
            logger.info("Candidate connected, resuming interview")
            opening = resume_note(transcript, minutes, passed)
            interviewer_lines = [line for line in transcript.lines if line.startswith("**Interviewer:**")]
            if interviewer_lines:
                stt.add_context(interviewer_lines[-1].removeprefix("**Interviewer:**"))
        else:
            logger.info("Candidate connected, starting interview")
            opening = "[time check] The candidate has joined. Begin the interview with your opening now."
        context.add_message({"role": "developer", "content": opening})
        await worker.queue_frames([LLMRunFrame()])
        timer_task = asyncio.create_task(run_timer())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Candidate disconnected")
        if timer_task:
            timer_task.cancel()
        await runner.cancel()

    # Turn timings for the transcript: when each turn started, how long it ran, and how long the
    # candidate paused after the interviewer finished.
    candidate_start: float | None = None
    candidate_pause: float | None = None
    interviewer_start: float | None = None

    @user_aggregator.event_handler("on_user_turn_started")
    async def on_user_turn_started(aggregator, strategy):
        nonlocal candidate_start, candidate_pause
        if session_started is None:
            return
        candidate_start = now()
        answering = transcript.turns and transcript.turns[-1].speaker == "Interviewer"
        candidate_pause = (
            time.monotonic() - clock.last_stopped if answering and clock.last_stopped and not clock.speaking else None
        )

    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(aggregator, strategy, message: UserTurnStoppedMessage):
        nonlocal candidate_start, candidate_pause
        start, pause_before = candidate_start, candidate_pause
        candidate_start = candidate_pause = None
        stopped_at = now() if session_started is not None else None
        live = message.content or ""
        text = live
        pcm = stt.turn_audio.take(live)
        # Parakeet is fast enough to hear the whole answer again in one pass, with all its context; the
        # interviewer already has the live text, so this only improves the transcript and the report.
        if pcm and stt.transcribe_turn:
            try:
                whole = await stt.transcribe_turn(pcm)
                if whole:
                    text = whole
            except Exception as e:
                logger.warning(f"Whole-answer transcription failed, keeping the live text: {e}")
        if pcm and SAVE_CANDIDATE_AUDIO:
            n = sum(1 for t in transcript.turns if t.speaker == "Candidate") + 1
            wav = audio_dir / f"answer-{n:02d}.wav"
            save_wav(wav, pcm, stt.sample_rate or 16000)
            with (audio_dir / "answers.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"file": wav.name, "live": live, "transcript": text}, ensure_ascii=False) + "\n")
        text = tidy_spaces(text)
        if start is not None and stopped_at is not None:
            transcript.add("Candidate", text, start, stopped_at - start, pause_before)
        else:
            transcript.add("Candidate", text)

    @assistant_aggregator.event_handler("on_assistant_turn_started")
    async def on_assistant_turn_started(aggregator):
        nonlocal interviewer_start
        interviewer_start = now() if session_started is not None else None

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message: AssistantTurnStoppedMessage):
        text = END_TOKEN.sub("", message.content or "").strip()
        if END_TOKEN.search(message.content or ""):
            interviewer_said_goodbye()  # in case the TTS filter never saw the token
        if interviewer_start is not None:
            transcript.add("Interviewer", text, interviewer_start, now() - interviewer_start)
        else:
            transcript.add("Interviewer", text)
        # The question is the best hint for the answer's vocabulary (e.g. "quantization-aware training").
        stt.add_context(text)

    try:
        await runner.run()
    finally:
        session_picker.active = None
        if timer_task:
            timer_task.cancel()
        if end_task:
            end_task.cancel()

    if session_started is None:
        return
    if notepad.strip():
        transcript.add("Candidate", f"[Shared notepad at the end of the session]\n```\n{notepad.strip()}\n```")
    elapsed = now()
    transcript.mark_elapsed(elapsed)

    # Ended on purpose (the interviewer said goodbye, or "end" on the web page), or ran past half time:
    # treat it as finished. Otherwise it was most likely a dropped connection.
    if not end_reason and elapsed < minutes * 60 / 2:
        session_picker.selection = Selection(selection.interview, transcript.path)
        logger.info(
            f"Session stopped at {elapsed / 60:.0f} of {minutes} min. Connect again to continue it "
            f"(or choose on the web page). For a report anyway, use the page or: python feedback.py {transcript.path}"
        )
        return

    # A finished session: the next Connect starts a new one with the same settings.
    session_picker.selection = Selection(selection.interview, None, selection.mode, selection.topic, selection.minutes,
                                         selection.coach)
    if AUTO_FEEDBACK and len(transcript.turns) >= 4:
        await session_picker.generate_report(selection.interview, transcript.path)


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import app, main

    parser = argparse.ArgumentParser(description="AI mock interviewer")
    parser.add_argument("--interview", help="interview under interviews/, e.g. example/tech (default: choose on the web page)")
    parser.add_argument("--resume", metavar="TRANSCRIPT", help="continue an interrupted interview from its transcript")
    args, _ = parser.parse_known_args()
    resume = Path(args.resume) if args.resume else None
    if resume and not resume.exists():
        raise SystemExit(f"Transcript not found: {resume}")
    session_picker.selection = Selection(pick_interview(args.interview, resume, ask=False), resume)
    session_picker.register(app)
    for issue in validate(session_picker.selection.interview):
        (logger.error if issue["level"] == "error" else logger.warning)(f"Interview setup: {issue['message']}")
    logger.info(
        f"Interview: {interview_name(session_picker.selection.interview)}" + (f", resuming {resume}" if resume else "")
        + ". Open http://localhost:7860/ to choose another interview or a transcript to resume."
    )
    main(parser)
