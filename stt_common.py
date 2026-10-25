"""Pieces shared by the speech-to-text services: collecting a whole answer's audio, restoring the spelling of
technical terms, saving audio, and loading the Parakeet model.
"""

import re
import wave
from pathlib import Path

PARAKEET_MODEL = "nemo-parakeet-tdt-0.6b-v3"
PARAKEET_REPO = "istupakov/parakeet-tdt-0.6b-v3-onnx"
# A plain folder, not the Hugging Face cache: onnxruntime refuses external weight files reached through the
# cache's symlinks ("External data path ... escapes model directory").
PARAKEET_DIR = Path.home() / ".cache" / "ai-interviewer" / "parakeet-tdt-0.6b-v3"


class TurnAudio:
    """The audio behind each transcribed piece of the candidate's speech.

    A finished answer is matched to its audio by text, not by timing: the next piece can already be
    transcribed by the time the answer's event handler runs, and must stay with the next answer.
    """

    def __init__(self):
        self._pending = bytearray()  # segments that produced no text yet (silent or dropped)
        self._pieces: list[tuple[str, bytes]] = []

    def add(self, pcm: bytes, text: str | None):
        """Records one VAD segment and the text it produced, if any. Segments without text join the next
        piece, so a model under comparison still gets to hear speech the live model dropped."""
        self._pending.extend(pcm)
        if text:
            self._pieces.append((" ".join(text.split()), bytes(self._pending)))
            self._pending.clear()

    def take(self, answer: str) -> bytes:
        """The audio of the pieces that make up this answer (its text as the aggregator joined them)."""
        answer = " ".join((answer or "").split())
        pcm = bytearray()
        while self._pieces and self._pieces[0][0] in answer:
            pcm.extend(self._pieces.pop(0)[1])
        return bytes(pcm)


def hotword_fixer(hotwords: list[str]):
    """Returns a function that restores hotwords split or re-cased by speech recognition, such as
    "tensor RT" or "Tensor-RT" back to "TensorRT". Only hotwords of four or more letters are restored, so short
    ones cannot rewrite ordinary words."""
    patterns = []
    for word in hotwords:
        letters = re.sub(r"[^A-Za-z0-9]", "", word)
        if len(letters) < 4:
            continue
        # Every character in order, optionally separated by a space or hyphen, as a whole word.
        body = r"[\s-]?".join(re.escape(c) for c in letters)
        patterns.append((re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE), word))

    def fix(text: str) -> str:
        for pattern, word in patterns:
            text = pattern.sub(word, text)
        return text

    return fix


def save_wav(path: Path, pcm: bytes, sample_rate: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)


def download_parakeet() -> Path:
    from huggingface_hub import snapshot_download

    # Full-precision weights only; the int8 copies are not used on the GPU.
    snapshot_download(PARAKEET_REPO, local_dir=PARAKEET_DIR, allow_patterns=["*.json", "*.txt", "nemo128.onnx",
                      "encoder-model.onnx", "encoder-model.onnx.data", "decoder_joint-model.onnx"])
    return PARAKEET_DIR


def load_parakeet(device: str = "cuda"):
    import onnx_asr

    if not (PARAKEET_DIR / "encoder-model.onnx").exists():
        download_parakeet()
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if device == "cuda" else ["CPUExecutionProvider"]
    return onnx_asr.load_model(PARAKEET_MODEL, PARAKEET_DIR, providers=providers)
