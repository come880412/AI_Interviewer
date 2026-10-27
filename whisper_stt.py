"""Local Whisper STT tuned for spoken interview answers.

Pipecat's WhisperSTTService transcribes each VAD segment on its own, so every pause in an answer
restarts the model with no context, and on unclear audio Whisper tends to read its hotwords prompt
back (one transcript had "QNX TensorRT ONNX INT8s" out of nowhere, four hotwords in list order).
This subclass feeds the recent conversation in as the prompt and drops segments that look like
hallucinations instead of speech.
"""

import asyncio
import re
from collections.abc import AsyncGenerator

import numpy as np
from loguru import logger

from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.utils.time import time_now_iso8601
from pipecat.utils.types import assert_given

from chinese import chinese_punctuation, tidy_spaces, to_traditional
from stt_common import TurnAudio, hotword_fixer

# About 100 tokens of recent conversation. Whisper's prompt window is 223 tokens, shared with hotwords.
CONTEXT_CHARS = 400
# faster-whisper's own threshold for a failed decode; segments still below it after the
# temperature fallback are usually guesses rather than speech.
DEFAULT_MIN_AVG_LOGPROB = -1.0
# This many hotwords in a row, in the same order as the list, is Whisper reading its prompt back.
HOTWORD_ECHO_RUN = 3
# A segment whose word trigrams mostly appear in the context prompt is Whisper copying the prompt.
# It also drops the candidate repeating the question nearly word for word, which costs little.
CONTEXT_COPY_RATIO = 0.8
CONTEXT_COPY_MIN_WORDS = 6
# RMS of 16-bit samples (about -55 dBFS). Quieter segments are not speech, and Whisper fills
# silence with its prompt or with subtitle credits, so they are not transcribed at all.
MIN_RMS = 60

WORD = re.compile(r"[a-z0-9]+")
# For copy detection Chinese characters count as words, since Chinese has no spaces between words.
TOKEN = re.compile(r"[a-z0-9]+|[㐀-鿿豈-﫿]")
# Credits from Whisper's subtitle training data; it emits these on silence with high confidence.
SUBTITLE_CREDITS = re.compile(
    r"\b(subtitles?|transcription|translation|transcribed|captions?|captioning)\s+by\b"
    r"|thanks? (you )?for watching|please subscribe|amara\.org"
    # The Chinese ones: subtitle credits, "like and subscribe", "thanks for watching", streaming channel names.
    r"|字幕由|字幕志[愿願]者|中文字幕|[点點][赞贊]|[订訂][阅閱][转轉]發|打[赏賞]|明[镜鏡]|[感谢謝]+[观觀]看|[独獨][播]",
    re.IGNORECASE,
)


class InterviewWhisperSTT(WhisperSTTService):
    """WhisperSTTService that carries conversation context across segments and filters hallucinations."""

    def __init__(self, *, min_avg_logprob: float = DEFAULT_MIN_AVG_LOGPROB, hotword_list: list[str] | None = None,
                 chinese: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._min_avg_logprob = min_avg_logprob
        self._chinese = chinese  # Mandarin: convert to Taiwan Traditional and join pieces without spaces
        self._context = ""
        self._hotword_seq = WORD.findall((assert_given(self._settings.hotwords) or "").lower())
        self._fix = hotword_fixer(hotword_list or [])
        self.turn_audio = TurnAudio()

    # Whisper is too slow to re-transcribe whole answers during the interview; see parakeet_stt.py.
    transcribe_turn = None

    def add_context(self, text: str):
        """Appends what was just said, by either side, to the prompt for the next segment."""
        text = " ".join((text or "").split())
        if text:
            self._context = f"{self._context} {text}"[-CONTEXT_CHARS:].lstrip()

    def _echoes_hotwords(self, text: str) -> bool:
        words = WORD.findall(text.lower())
        h, n = self._hotword_seq, HOTWORD_ECHO_RUN

        def same(word: str, hotword: str) -> bool:
            # Prefix match catches plurals ("INT8s"), but only for hotwords long enough not to
            # match ordinary words ("go" would match "good").
            return word == hotword or (len(hotword) >= 3 and word.startswith(hotword))

        return any(
            all(same(words[i + k], h[j + k]) for k in range(n))
            for i in range(len(words) - n + 1)
            for j in range(len(h) - n + 1)
        )

    def _copies_context(self, text: str) -> bool:
        words = TOKEN.findall(text.lower())
        if len(words) < CONTEXT_COPY_MIN_WORDS:
            return False
        ctx = TOKEN.findall(self._context.lower())
        ctx_grams = {tuple(ctx[i : i + 3]) for i in range(len(ctx) - 2)}
        grams = [tuple(words[i : i + 3]) for i in range(len(words) - 2)]
        return sum(g in ctx_grams for g in grams) / len(grams) >= CONTEXT_COPY_RATIO

    def _reject_reason(self, segment, no_speech_max: float | None) -> str | None:
        if no_speech_max is not None and segment.no_speech_prob >= no_speech_max:
            return f"no speech {segment.no_speech_prob:.2f}"
        if segment.avg_logprob < self._min_avg_logprob:
            return f"low confidence {segment.avg_logprob:.2f}"
        if self._echoes_hotwords(segment.text):
            return "repeats the hotword list"
        if SUBTITLE_CREDITS.search(segment.text):
            return "subtitle credit"
        if self._copies_context(segment.text):
            return "copies the context prompt"
        return None

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Transcribes one VAD segment of 16-bit PCM audio."""
        if not self._model:
            yield ErrorFrame("Whisper model not available")
            return

        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0
        if rms < MIN_RMS:
            logger.info(f"Skipped near-silent Whisper segment (RMS {rms:.0f})")
            self.turn_audio.add(audio, None)
            return

        await self.start_processing_metrics()

        audio_float = samples / 32768.0
        language = assert_given(self._settings.language)
        prompt = self._context or assert_given(self._settings.initial_prompt)

        def transcribe():
            # faster-whisper decodes lazily while the generator is consumed, so consume it
            # here in the worker thread; iterating on the event loop would stall the audio.
            segments, _ = self._model.transcribe(
                audio_float,
                language=language,
                hotwords=assert_given(self._settings.hotwords),
                initial_prompt=prompt,
            )
            return list(segments)

        segments = await asyncio.to_thread(transcribe)

        no_speech_max = assert_given(self._settings.no_speech_prob)
        kept = []
        for segment in segments:
            reason = self._reject_reason(segment, no_speech_max)
            if reason:
                logger.info(f"Dropped Whisper segment ({reason}): [{segment.text.strip()}]")
            else:
                kept.append(segment.text.strip())
        text = " ".join(kept)
        if self._chinese:
            text = tidy_spaces(chinese_punctuation(to_traditional(text)))
        text = self._fix(text)

        await self.stop_processing_metrics()

        # Recorded before the transcription goes out, so the answer it ends up in can find its audio.
        self.turn_audio.add(audio, text)
        if text:
            self.add_context(text)
            await self._handle_transcription(text, True, language)
            logger.debug(f"Transcription: [{text}]")
            yield TranscriptionFrame(text, self._user_id, time_now_iso8601(), language)
