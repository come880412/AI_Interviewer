"""Loads the project's .env. Every module that reads a setting when it is imported imports this first, so the
settings in .env apply whichever script started Python and whatever folder it was started from."""

import os
from pathlib import Path

from dotenv import load_dotenv

# The project folder: this file is in interviewer/.
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)


def project_path(value: str | Path) -> Path:
    """A path from a setting; relative paths are relative to the project folder, not the current directory."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def whisper_device() -> tuple[str, str]:
    """(device, compute type) for faster-whisper. float16 only works on a GPU, so the CPU defaults to int8."""
    device = os.getenv("WHISPER_DEVICE", "cuda")
    return device, os.getenv("WHISPER_COMPUTE_TYPE") or ("float16" if device == "cuda" else "int8")
