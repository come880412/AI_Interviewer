"""The interviewer's Japanese voice: Kokoro v1.0's Japanese voices (jf_*, jm_*) with misaki's Japanese G2P.

Pipecat's KokoroTTSService phonemizes with espeak-ng, which cannot read kanji, so the text is turned into
phonemes first with misaki (pyopenjtalk; its dictionary downloads on first use, about 22 MB). English terms
inside Japanese sentences, such as INT8, come through as katakana readings.
Install with: pip install "misaki[ja]"
"""

from collections.abc import AsyncGenerator

import numpy as np

from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.kokoro.tts import KokoroTTSService
from pipecat.utils.tracing.service_decorators import traced_tts
from pipecat.utils.types import assert_given, require_given

DEFAULT_JA_VOICE = "jm_kumo"


def japanese_g2p():
    """misaki's Japanese G2P, or a clear error when the optional package is missing."""
    try:
        from misaki import ja
    except ImportError as e:
        raise RuntimeError('Japanese interviews need misaki\'s Japanese G2P: pip install "misaki[ja]"') from e
    g2p = ja.JAG2P(version="pyopenjtalk")

    def phonemes(text: str) -> str:
        # misaki returns the phonemes followed by a pitch string of the same length.
        both, _ = g2p(text)
        return both[: len(both) // 2]

    return phonemes


class JapaneseKokoroTTSService(KokoroTTSService):
    """KokoroTTSService that speaks Japanese from misaki's phonemes."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._phonemes = japanese_g2p()

    def phonemes(self, text: str) -> str:
        return self._phonemes(text)

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        try:
            await self.start_tts_usage_metrics(text)
            phonemes = self.phonemes(text)
            if not phonemes.strip():
                return
            voice = require_given(self._settings.voice, "Kokoro TTS voice")
            speed = assert_given(self._settings.speed)
            stream = self._kokoro.create_stream(phonemes, voice=voice, lang="ja", speed=speed, is_phonemes=True)
            async for samples, sample_rate in stream:
                await self.stop_ttfb_metrics()
                audio = (samples * 32767).astype(np.int16).tobytes()
                audio = await self._resampler.resample(audio, sample_rate, self.sample_rate)
                yield TTSAudioRawFrame(audio=audio, sample_rate=self.sample_rate, num_channels=1, context_id=context_id)
        except Exception as e:
            yield ErrorFrame(error=f"Japanese Kokoro TTS failed: {e}")
        finally:
            await self.stop_ttfb_metrics()
