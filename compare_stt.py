"""Compares speech-to-text models on your own recorded answers.

Set SAVE_CANDIDATE_AUDIO=true in .env, do an interview, then:
    python compare_stt.py transcripts/acme/tech/20261101-1930-transcript.md
    python compare_stt.py transcripts/acme/tech/20261101-1930-transcript.md --models whisper parakeet whisper-turbo

Writes *-stt-compare.md next to the transcript: for each answer, what was transcribed live during the
interview and what each model hears when given the whole answer at once. Read them against what you
remember saying; the model that gets your technical terms and accent right is the one to set as STT_BACKEND.
"""

import argparse
import gc
import json
import os
import time
import wave
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

from interview_config import InterviewConfig, pick_interview
from stt_common import hotword_fixer, load_parakeet
from transcript import sibling

load_dotenv(override=True)

DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_MODELS = {
    "whisper": os.getenv("WHISPER_MODEL", "large-v3"),
    "whisper-turbo": "deepdml/faster-whisper-large-v3-turbo-ct2",
}
LABELS = {"whisper": "Whisper large-v3", "whisper-turbo": "Whisper large-v3-turbo", "parakeet": "Parakeet TDT 0.6B v3"}


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1:
            raise ValueError(f"{path.name}: expected 16 kHz mono audio")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def transcribe_all(name: str, audio: list[np.ndarray], hotwords: list[str]) -> tuple[list[str], float]:
    """Returns each answer's text and the total transcription time in seconds (model loading excluded)."""
    fix = hotword_fixer(hotwords)
    if name == "parakeet":
        model = load_parakeet(DEVICE)
        model.recognize(audio[0][:16000])  # warm-up
        start = time.time()
        texts = [fix(model.recognize(a).strip()) for a in audio]
    else:
        from faster_whisper import WhisperModel

        model = WhisperModel(WHISPER_MODELS[name], device=DEVICE, compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "float16"))
        start = time.time()
        texts = []
        for a in audio:
            segments, _ = model.transcribe(a, language="en", hotwords=" ".join(hotwords) or None)
            texts.append(fix(" ".join(s.text.strip() for s in segments)))
    took = time.time() - start
    del model
    gc.collect()  # free the GPU before loading the next model
    return texts, took


def main():
    parser = argparse.ArgumentParser(description="Compare speech-to-text models on recorded answers")
    parser.add_argument("transcript", help="a transcript recorded with SAVE_CANDIDATE_AUDIO=true")
    parser.add_argument("--models", nargs="+", default=["whisper", "parakeet"], choices=sorted(LABELS))
    args = parser.parse_args()

    transcript = Path(args.transcript)
    audio_dir = transcript.with_name(transcript.name.replace("-transcript.md", "-audio"))
    index = audio_dir / "answers.jsonl"
    if not index.exists():
        raise SystemExit(f"No recorded answers in {audio_dir}. Set SAVE_CANDIDATE_AUDIO=true in .env and do an interview first.")
    answers = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
    audio = [read_wav(audio_dir / a["file"]) for a in answers]
    hotwords = InterviewConfig.load(pick_interview(None, transcript)).stt_hotwords
    seconds = sum(len(a) for a in audio) / 16000
    print(f"{len(answers)} answers, {seconds / 60:.1f} min of audio")

    results, timings = {}, {}
    for name in args.models:
        print(f"Transcribing with {LABELS[name]}...")
        results[name], timings[name] = transcribe_all(name, audio, hotwords)
        print(f"  {timings[name]:.1f} s ({seconds / max(timings[name], 1e-6):.0f}x real time)")

    lines = [
        f"# 語音辨識比較：{transcript.name}",
        "",
        f"{len(answers)} 段回答，共 {seconds / 60:.1f} 分鐘。「即時」是面試中實際用的辨識結果；其他欄是把整段回答一次交給該模型的結果。",
        "",
        "| 模型 | 辨識時間 | 速度 |",
        "|---|---|---|",
    ]
    lines += [f"| {LABELS[n]} | {timings[n]:.1f} 秒 | {seconds / max(timings[n], 1e-6):.0f} 倍即時 |" for n in args.models]
    for i, (answer, a) in enumerate(zip(answers, audio), 1):
        lines += ["", f"## 回答 {i}（{len(a) / 16000:.0f} 秒）", "", f"- **即時**：{answer['live']}"]
        lines += [f"- **{LABELS[n]}**：{results[n][i - 1]}" for n in args.models]
    out = sibling(transcript, "stt-compare")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
