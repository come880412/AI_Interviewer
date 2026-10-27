"""The interviewer's Mandarin voice: Kokoro v1.1-zh.

It needs misaki's Chinese G2P instead of the espeak-ng phonemes Pipecat's KokoroTTSService uses (espeak reads
Chinese badly). English terms inside Chinese sentences go through espeak-ng's English voice, the same way the
English interviewer is phonemized.
"""

import urllib.request
from collections.abc import AsyncGenerator
from pathlib import Path

import numpy as np
from loguru import logger

from pipecat.audio.utils import create_stream_resampler
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.kokoro.tts import KokoroTTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language
from pipecat.utils.tracing.service_decorators import traced_tts
from pipecat.utils.types import require_given

from chinese import to_simplified

KOKORO_ZH_DIR = Path.home() / ".cache" / "ai-interviewer" / "kokoro-v1.1-zh"
KOKORO_ZH_FILES = {
    "kokoro-v1.1-zh.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.1-zh.onnx",
    "voices-v1.1-zh.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.1-zh.bin",
    # The v1.1 vocabulary differs from the v1.0 one kokoro-onnx ships with.
    "config.json": "https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/resolve/main/config.json",
}
# A male Mandarin voice; the voices file has zf_* (female) and zm_* (male) voices.
DEFAULT_ZH_VOICE = "zm_010"


def download_kokoro_zh() -> Path:
    KOKORO_ZH_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in KOKORO_ZH_FILES.items():
        target = KOKORO_ZH_DIR / name
        if not target.exists():
            logger.info(f"Downloading {url}")
            partial = target.with_suffix(target.suffix + ".part")
            urllib.request.urlretrieve(url, partial)
            partial.rename(target)
    return KOKORO_ZH_DIR


class ChineseKokoroTTSService(TTSService):
    """Kokoro v1.1-zh with misaki's Chinese G2P. Downloads the model on first use."""

    Settings = KokoroTTSSettings
    _settings: Settings

    def __init__(self, *, settings: Settings | None = None, **kwargs):
        default_settings = self.Settings(model=None, voice=DEFAULT_ZH_VOICE, language=Language.ZH, speed=1.0)
        if settings is not None:
            default_settings.apply_update(settings)
        super().__init__(push_start_frame=True, push_stop_frames=True, settings=default_settings, **kwargs)

        from kokoro_onnx import Kokoro
        from misaki import zh

        folder = download_kokoro_zh()
        self._kokoro = Kokoro(str(folder / "kokoro-v1.1-zh.onnx"), str(folder / "voices-v1.1-zh.bin"),
                              vocab_config=str(folder / "config.json"))
        voice = require_given(self._settings.voice, "Kokoro TTS voice")
        if voice not in self._kokoro.voices:
            raise ValueError(f"Kokoro voice '{voice}' is not in the Chinese voices file; use a zm_* or zf_* voice")
        english = self._kokoro.tokenizer
        self._g2p = zh.ZHG2P(version="1.1", en_callable=lambda text: english.phonemize(text, "en-us"))
        self._resampler = create_stream_resampler()

    def can_generate_metrics(self) -> bool:
        return True

    def phonemes(self, text: str) -> str:
        phonemes, _ = self._g2p(to_simplified(text))
        return phonemes or ""

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        try:
            await self.start_tts_usage_metrics(text)
            phonemes = self.phonemes(text)
            if not phonemes.strip():
                return
            voice = require_given(self._settings.voice, "Kokoro TTS voice")
            # The v1.1-zh export takes an integer speed.
            stream = self._kokoro.create_stream(phonemes, voice=voice, speed=1, is_phonemes=True)
            async for samples, sample_rate in stream:
                await self.stop_ttfb_metrics()
                audio = (samples * 32767).astype(np.int16).tobytes()
                audio = await self._resampler.resample(audio, sample_rate, self.sample_rate)
                yield TTSAudioRawFrame(audio=audio, sample_rate=self.sample_rate, num_channels=1, context_id=context_id)
        except Exception as e:
            yield ErrorFrame(error=f"Chinese Kokoro TTS failed: {e}")
        finally:
            await self.stop_ttfb_metrics()
