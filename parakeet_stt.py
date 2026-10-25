"""Local NVIDIA Parakeet TDT 0.6B v3 speech-to-text, run with onnx-asr on the GPU.

Several times faster than Whisper large-v3 and ahead of it on the Open ASR Leaderboard, but it cannot be
prompted with hotwords, so technical terms are restored afterwards from the hotword list. Being this fast, it
also re-transcribes each whole answer in one pass for the transcript (see transcribe_turn).
"""

import asyncio
from collections.abc import AsyncGenerator

import numpy as np
from loguru import logger

from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.services.settings import STTSettings
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601

from stt_common import PARAKEET_MODEL, TurnAudio, hotword_fixer, load_parakeet
from whisper_stt import MIN_RMS


class ParakeetSTTService(SegmentedSTTService):
    """Transcribes each VAD segment with Parakeet, and keeps the answer's audio for a whole-answer pass."""

    @property
    def wants_wav_segments(self) -> bool:
        """Receive segments as raw 16-bit PCM."""
        return False

    def __init__(self, *, hotwords: list[str] | None = None, device: str = "cuda", **kwargs):
        super().__init__(settings=STTSettings(model=PARAKEET_MODEL, language=Language.EN), **kwargs)
        logger.debug("Loading Parakeet model...")
        self._model = load_parakeet(device)
        logger.debug("Loaded Parakeet model")
        self._fix = hotword_fixer(hotwords or [])
        self.turn_audio = TurnAudio()

    def can_generate_metrics(self) -> bool:
        return True

    def add_context(self, text: str):
        """Parakeet takes no prompt; kept so the pipeline can treat both STT services alike."""

    def _recognize(self, pcm: bytes) -> str:
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        return self._fix(self._model.recognize(samples, sample_rate=self.sample_rate or 16000).strip())

    async def transcribe_turn(self, pcm: bytes) -> str:
        """One pass over a whole answer, which keeps the context that per-segment transcription loses."""
        if not pcm:
            return ""
        return await asyncio.to_thread(self._recognize, pcm)

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Transcribes one VAD segment of 16-bit PCM audio."""
        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0
        if rms < MIN_RMS:
            logger.info(f"Skipped near-silent segment (RMS {rms:.0f})")
            self.turn_audio.add(audio, None)
            return

        await self.start_processing_metrics()
        try:
            text = await asyncio.to_thread(self._recognize, audio)
        except Exception as e:
            await self.stop_processing_metrics()
            self.turn_audio.add(audio, None)
            yield ErrorFrame(f"Parakeet transcription failed: {e}")
            return
        await self.stop_processing_metrics()

        # Recorded before the transcription goes out, so the answer it ends up in can find its audio.
        self.turn_audio.add(audio, text)
        if text:
            logger.debug(f"Transcription: [{text}]")
            yield TranscriptionFrame(text, self._user_id, time_now_iso8601(), Language.EN)
