"""Downloads the local models ahead of time and checks that the GPU is usable.

Run once after setup:  source cuda_env.sh && python download_models.py
(Silero VAD and Smart Turn v3 ship inside pipecat, so they need no download.)
Only the avatar files for the video interview page:  python download_models.py avatar
"""

import os
import sys
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

ok = True

WEB = Path(__file__).parent / "web"
# HeadAudio (MIT): in-browser lip-sync from the interviewer's audio. Pinned to a commit so an upstream
# change cannot break the page; david.glb is a Ready Player Me avatar from the same repo (personal use).
HEADAUDIO = "https://cdn.jsdelivr.net/gh/met4citizen/HeadAudio@c6d8af35034068b1c98dcc0fa3ec9602d711e784"
AVATAR_FILES = {
    "dist/headaudio.min.mjs": WEB / "vendor/headaudio/headaudio.min.mjs",
    "dist/headworklet.min.mjs": WEB / "vendor/headaudio/headworklet.min.mjs",
    "dist/model-en-mixed.bin": WEB / "vendor/headaudio/model-en-mixed.bin",
    "avatars/david.glb": WEB / "avatars/david.glb",
}


def step(title):
    print(f"\n== {title}")


def download_avatar_files() -> bool:
    step("Avatar and lip-sync files for the video interview page")
    for source, target in AVATAR_FILES.items():
        if target.exists():
            print(f"already there: {target.relative_to(WEB.parent)}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(f"{HEADAUDIO}/{source}", target)
            print(f"downloaded: {target.relative_to(WEB.parent)}")
        except Exception as e:
            print(f"FAIL: {source}: {e}")
            return False
    return True


if sys.argv[1:] == ["avatar"]:
    sys.exit(0 if download_avatar_files() else 1)


step("1. Whisper STT model")
from faster_whisper import WhisperModel
from faster_whisper.utils import download_model

whisper_id = os.getenv("WHISPER_MODEL", "large-v3")
download_model(whisper_id)
print(f"downloaded: {whisper_id}")

step("2. Kokoro TTS model")
from pipecat.services.kokoro.tts import KOKORO_CACHE_DIR, _ensure_model_files

KOKORO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_ensure_model_files(KOKORO_CACHE_DIR / "kokoro-v1.0.onnx", KOKORO_CACHE_DIR / "voices-v1.0.bin")
print(f"downloaded to: {KOKORO_CACHE_DIR}")

step("3. GPU check: Whisper (CTranslate2)")
import ctranslate2

device = os.getenv("WHISPER_DEVICE", "cuda")
if device == "cuda" and ctranslate2.get_cuda_device_count() == 0:
    print("FAIL: CTranslate2 sees no CUDA device. Check the NVIDIA driver, and that you ran `source cuda_env.sh`.")
    ok = False
else:
    try:
        t = time.time()
        WhisperModel(whisper_id, device=device, compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "float16"))
        print(f"OK: Whisper loaded on {device} in {time.time() - t:.1f}s")
    except Exception as e:
        print(f"FAIL: {e}\n  If this mentions libcudnn or libcublas, run `source cuda_env.sh` first.")
        ok = False

step("4. GPU check: Kokoro (onnxruntime)")
import onnxruntime as ort

providers = ort.get_available_providers()
wanted = os.getenv("ONNX_PROVIDER")
print(f"available providers: {providers}")
if wanted and wanted not in providers:
    print(f"FAIL: ONNX_PROVIDER={wanted} is not available. Is onnxruntime-gpu installed instead of onnxruntime?")
    ok = False
else:
    from kokoro_onnx import Kokoro

    k = Kokoro(str(KOKORO_CACHE_DIR / "kokoro-v1.0.onnx"), str(KOKORO_CACHE_DIR / "voices-v1.0.bin"))
    # onnxruntime silently falls back to the CPU when a CUDA library is missing, so check what the session uses.
    used = k.sess.get_providers()
    if wanted and used[0] != wanted:
        print(f"FAIL: Kokoro session is using {used[0]}, not {wanted}. Look for 'Failed to load library' above, and run `source cuda_env.sh`.")
        ok = False
    k.create("Warm up.", voice="am_michael", lang="en-us")  # first call compiles kernels
    t = time.time()
    samples, sr = k.create("Thanks for joining today. Let's start with a quick introduction.", voice="am_michael", lang="en-us")
    took = time.time() - t
    print(f"OK: synthesized {len(samples) / sr:.1f}s of audio in {took:.2f}s ({(len(samples) / sr) / took:.0f}x real time)")

if not download_avatar_files():
    print("The voice interview still works; only the avatar on the video page is missing.")

print("\nAll set. Start the interviewer with: python bot.py" if ok else "\nSome checks failed, see README troubleshooting.")
sys.exit(0 if ok else 1)
