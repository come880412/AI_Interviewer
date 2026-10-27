"""Loads an interview folder (config.yaml + markdown files) and renders prompt templates.

Interviews are organized by company, one subfolder per round:

    interviews/acme/company.yaml          company-wide settings (company, role_title, stt_hotwords, ...)
    interviews/acme/jd.md                 shared by every round of this company
    interviews/acme/resume.md             the resume version for this company
    interviews/acme/tech/config.yaml      this round (interviewer, round_name, duration, voice, ...)

A file is looked up in the round folder first, then the company folder (one with company.yaml);
the resume finally falls back to profile/resume.md. A single folder with a config.yaml directly under
interviews/ also works as an interview on its own.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from transcript import TRANSCRIPTS_DIR, read_transcript

ROOT = Path(__file__).parent
PROMPTS_DIR = ROOT / "prompts"
INTERVIEWS_DIR = ROOT / "interviews"
PROFILE_DIR = ROOT / "profile"

# Markdown files read from the interview folders; each becomes a template variable.
TEXT_FILES = {
    "job_description": "jd.md",
    "round_info": "round_info.md",
    "resume": "resume.md",
    "question_bank": "question_bank.md",
    "rubric": "rubric.md",  # scoring anchors for the feedback report
    "company_info": "company_info.md",  # facts the interviewer may use when answering the candidate's questions
}
NOT_PROVIDED = "(not provided)"
# Config keys the prompts need, from company.yaml or the round's config.yaml.
REQUIRED_KEYS = ["company", "role_title", "interviewer_name", "interviewer_title", "round_name"]
KNOWN_KEYS = set(REQUIRED_KEYS) | {
    "duration_minutes", "difficulty", "feedback_language", "voice", "voice_language", "voice_clone", "stt_hotwords",
    "avatar", "avatar_body", "pocket_voice", "interview_language",
}
# interview_language values, and how the prompts name each language.
LANGUAGES = {"en": "English", "zh-TW": "Mandarin Chinese (Traditional Chinese as used in Taiwan)"}
LANGUAGE_ALIASES = {"english": "en", "en-us": "en", "en-gb": "en", "zh": "zh-TW", "zh-tw": "zh-TW", "zh_tw": "zh-TW",
                    "chinese": "zh-TW", "mandarin": "zh-TW", "中文": "zh-TW"}
# The report language when neither the company nor the round sets feedback_language.
DEFAULT_FEEDBACK_LANGUAGE = {"en": "English", "zh-TW": "Traditional Chinese (Taiwan)"}


def language_code(value) -> str | None:
    """"en" or "zh-TW" for an interview_language setting (missing means English), or None if unknown."""
    text = str(value or "en").strip()
    return text if text in LANGUAGES else LANGUAGE_ALIASES.get(text.lower())
# Used when neither the round nor the company folder has its own copy.
SHARED_FILES = {"resume": PROFILE_DIR / "resume.md"}


def interview_name(folder: Path) -> str:
    """The folder's path under interviews/, e.g. "acme/tech"."""
    try:
        return Path(folder).resolve().relative_to(INTERVIEWS_DIR.resolve()).as_posix()
    except ValueError:
        return Path(folder).name


def company_dir(folder: Path) -> Path | None:
    """The company folder above a round folder, recognized by its company.yaml."""
    parent = Path(folder).parent
    return parent if (parent / "company.yaml").exists() else None


def _read_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise yaml.YAMLError(f"{path.name} must be a list of key: value settings at the top level")
    return data


def resume_layers(folder: Path) -> list[tuple[str, str, Path]]:
    """(target, level, path) for every place this interview's resume can live, most specific first.
    The first one that exists is used."""
    folder = Path(folder)
    layers = [(f"interview:{interview_name(folder)}", "interview", folder / "resume.md")]
    company = company_dir(folder)
    if company:
        layers.append((f"company:{interview_name(company)}", "company", company / "resume.md"))
    layers.append(("profile", "profile", SHARED_FILES["resume"]))
    return layers


@dataclass
class InterviewConfig:
    name: str
    variables: dict[str, str]
    voice: str = "am_michael"
    voice_language: str = "en-us"
    voice_clone: Path | None = None  # reference .wav for Pocket TTS; None = use the Kokoro voice
    pocket_voice: str | None = None  # a Pocket TTS built-in voice, e.g. "stuart_bell", used when there is no voice_clone
    stt_hotwords: list[str] = field(default_factory=list)
    duration_minutes: int = 30
    avatar: str = "david"  # web/avatars/<avatar>.glb on the video interview page
    avatar_body: str = "M"  # "M" or "F", for the avatar's posture and gestures
    language: str = "en"  # "en" or "zh-TW" (interview_language)

    @property
    def chinese(self) -> bool:
        return self.language == "zh-TW"

    @classmethod
    def load(cls, folder: str | Path) -> "InterviewConfig":
        folder = Path(folder)
        company = company_dir(folder)
        search = [folder, company] if company else [folder]

        raw = _read_yaml(company / "company.yaml") if company else {}
        own = _read_yaml(folder / "config.yaml")
        # Hotwords add up: company terms from the JD plus anything specific to this round.
        hotwords = list(dict.fromkeys([*(raw.get("stt_hotwords") or []), *(own.get("stt_hotwords") or [])]))
        raw.update(own)

        variables = {k: str(v) for k, v in raw.items() if not isinstance(v, (list, dict))}
        for key, filename in TEXT_FILES.items():
            candidates = [d / filename for d in search] + ([SHARED_FILES[key]] if key in SHARED_FILES else [])
            path = next((p for p in candidates if p.exists()), None)
            variables[key] = path.read_text(encoding="utf-8").strip() if path else NOT_PROVIDED

        language = language_code(raw.get("interview_language"))
        if not language:
            raise ValueError(f"interview_language '{raw['interview_language']}' is not one of: {', '.join(LANGUAGES)}")
        variables["interview_language"] = LANGUAGES[language]
        variables.setdefault("feedback_language", DEFAULT_FEEDBACK_LANGUAGE[language])

        voice_clone = None
        if raw.get("voice_clone"):
            voice_clone = next((d / raw["voice_clone"] for d in search if (d / raw["voice_clone"]).exists()), None)
            if not voice_clone:
                raise FileNotFoundError(f"voice_clone '{raw['voice_clone']}' was not found in {folder}")

        return cls(
            name=interview_name(folder),
            variables=variables,
            voice=raw.get("voice", "am_michael"),
            voice_language=raw.get("voice_language", "en-us"),
            voice_clone=voice_clone,
            pocket_voice=str(raw["pocket_voice"]) if raw.get("pocket_voice") else None,
            stt_hotwords=hotwords,
            duration_minutes=int(raw.get("duration_minutes", 30)),
            avatar=str(raw.get("avatar", "david")),
            avatar_body="F" if str(raw.get("avatar_body", "M")).upper().startswith("F") else "M",
            language=language,
        )

    def render(self, template_name: str, **extra: str) -> str:
        template = (PROMPTS_DIR / template_name).read_text(encoding="utf-8")
        values = {**self.variables, **extra}

        def replace(match: re.Match) -> str:
            key = match.group(1).strip()
            if key not in values:
                raise KeyError(f"Template {template_name} needs '{key}', but it is not in config.yaml")
            return values[key]

        return re.sub(r"\{\{\s*([a-z_]+)\s*\}\}", replace, template)


def rubric_areas(rubric: str) -> list[str]:
    """The scored areas of a rubric: its "## " headings."""
    return [line[3:].strip() for line in rubric.splitlines() if line.startswith("## ")]


def validate(folder: Path) -> list[dict]:
    """Problems with an interview folder, as {"level": "error" | "warning", "message": ...} in Chinese for the
    setup page. An error means the interview cannot run; a warning means it runs with less to work with."""
    folder = Path(folder)
    issues = []

    def add(level, message):
        issues.append({"level": level, "message": message})

    company = company_dir(folder)
    try:
        raw = _read_yaml(company / "company.yaml") if company else {}
        raw.update(_read_yaml(folder / "config.yaml"))
    except yaml.YAMLError as e:
        add("error", f"YAML 格式錯誤：{str(e).splitlines()[0]}")
        return issues

    for key in REQUIRED_KEYS:
        if not raw.get(key):
            add("error", f"缺少設定 {key}（放在 company.yaml 或 config.yaml）")
    for key in sorted(set(raw) - KNOWN_KEYS):
        add("warning", f"不認得的設定 {key}，可能打錯字")
    try:
        if int(raw.get("duration_minutes", 30)) <= 0:
            raise ValueError
    except (TypeError, ValueError):
        add("error", "duration_minutes 必須是正整數")
    if raw.get("difficulty", "standard") not in ("standard", "tough"):
        add("warning", "difficulty 只能是 standard 或 tough")
    language = language_code(raw.get("interview_language"))
    if not language:
        add("error", "interview_language 只能是 en（英文）或 zh-TW（中文）")
    elif language == "zh-TW" and (raw.get("voice_clone") or raw.get("pocket_voice")):
        add("warning", "Pocket TTS 不會說中文，中文面試會忽略 voice_clone / pocket_voice，改用 Kokoro 中文聲音")

    search = [folder, company] if company else [folder]
    if raw.get("voice_clone") and not any((d / raw["voice_clone"]).exists() for d in search):
        add("error", f"找不到複製聲音的音檔 {raw['voice_clone']}")
    missing = {
        "jd.md": "沒有 jd.md，面試官不知道職缺內容",
        "round_info.md": "沒有 round_info.md，面試官不知道這關考什麼",
        "question_bank.md": "沒有 question_bank.md，面試官只能自己想題目",
        "rubric.md": "沒有 rubric.md，回饋報告會改用 round_info 的面向評分，分數比較難跨場次比較",
        "company_info.md": "沒有 company_info.md，被問到公司細節時面試官只能說會再回覆",
    }
    for filename, message in missing.items():
        if not any((d / filename).exists() for d in search):
            add("warning", message)
    if not any(path.exists() for _, _, path in resume_layers(folder)):
        add("warning", "沒有履歷，面試官無法針對你的經歷提問")
    return issues


def list_interviews() -> list[str]:
    """Interview names such as "acme/tech"; anything under a folder starting with "_" (like _template) is skipped."""
    if not INTERVIEWS_DIR.is_dir():
        return []
    configs = [*INTERVIEWS_DIR.glob("*/config.yaml"), *INTERVIEWS_DIR.glob("*/*/config.yaml")]
    names = (interview_name(c.parent) for c in configs)
    return sorted(n for n in names if not any(part.startswith("_") for part in n.split("/")))


def resolve_interview(name_or_path: str) -> Path:
    for candidate in (INTERVIEWS_DIR / name_or_path, Path(name_or_path)):
        if (candidate / "config.yaml").exists():
            return candidate
    # A company name is enough when the company has a single round.
    rounds = [n for n in list_interviews() if n.startswith(name_or_path.rstrip("/") + "/")]
    if len(rounds) == 1:
        return INTERVIEWS_DIR / rounds[0]
    raise SystemExit(f"Interview '{name_or_path}' not found. Available: {', '.join(list_interviews()) or 'none'}")


def _interview_from_transcript_folder(transcript: Path) -> str | None:
    """Transcripts are saved under transcripts/<interview>/, so their folder names the interview."""
    try:
        name = transcript.resolve().parent.relative_to(TRANSCRIPTS_DIR.resolve()).as_posix()
    except ValueError:
        return None
    return name if name in list_interviews() else None


def pick_interview(requested: str | None = None, transcript: str | Path | None = None, ask: bool = True) -> Path:
    """Chooses the interview folder: explicit name, then the transcript's own, then $INTERVIEW, then
    ask in the terminal (or take the first one when ask is False)."""
    if not requested and transcript:
        requested = read_transcript(transcript).interview or _interview_from_transcript_folder(Path(transcript))
    requested = requested or os.getenv("INTERVIEW")
    if requested:
        return resolve_interview(requested)

    available = list_interviews()
    if not available:
        raise SystemExit("No interviews in interviews/. Copy interviews/_template to start one.")
    if len(available) == 1 or not ask:
        return INTERVIEWS_DIR / available[0]

    print("\nWhich interview?")
    for i, name in enumerate(available, 1):
        print(f"  {i}. {name}")
    while True:
        choice = input("Number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(available):
            return INTERVIEWS_DIR / available[int(choice) - 1]
