"""Creates a new company or round from the setup page: Claude drafts round_info.md, question_bank.md,
rubric.md, company_info.md and speech-recognition hotwords from the JD, the candidate's notes and the
resume; the candidate reviews the drafts, and create() writes the folders.

round_files() and save_round_file() let the setup page edit an existing round's files afterwards.
"""

import os
import re
from datetime import datetime
from pathlib import Path

import yaml

from interviewer import settings  # noqa: F401  (loads .env before the settings below are read)
from interviewer.config import (DEFAULT_FEEDBACK_LANGUAGE, INTERVIEWS_DIR, LANGUAGE_SPECS, LANGUAGES, OVERRIDABLE_PROMPTS,
                                PROFILE_DIR, PROMPTS_DIR, company_dir, language_code, validate)
from interviewer.llm import complete
from interviewer.transcript import write_atomic

SETUP_MODEL = os.getenv("FEEDBACK_MODEL", os.getenv("LLM_MODEL", "claude-opus-5-5"))
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DRAFT_FILES = ["round_info", "question_bank", "rubric", "company_info"]


class SetupError(ValueError):
    """A problem the person can fix, shown on the page."""


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def companies() -> list[dict]:
    """Existing company folders, with what the wizard shows when adding a round to one."""
    result = []
    for path in sorted(INTERVIEWS_DIR.glob("*/company.yaml")):
        folder = path.parent
        if folder.name.startswith("_"):
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        result.append({
            "slug": folder.name,
            "company": raw.get("company", folder.name),
            "role_title": raw.get("role_title", ""),
            "feedback_language": raw.get("feedback_language", ""),
            "jd": (folder / "jd.md").read_text(encoding="utf-8") if (folder / "jd.md").exists() else "",
            "rounds": sorted(p.parent.name for p in folder.glob("*/config.yaml")),
        })
    return result


def _resume_for(company_slug: str | None) -> str:
    for path in ([INTERVIEWS_DIR / company_slug / "resume.md"] if company_slug else []) + [PROFILE_DIR / "resume.md"]:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return "(not provided)"


async def draft(fields: dict) -> dict:
    """Asks Claude for the round files. fields: company, role_title, round_name, interviewer_name,
    interviewer_title, duration_minutes, feedback_language, jd, notes, and optionally company_slug."""
    if not fields.get("jd", "").strip():
        raise SetupError("請貼上職缺描述（JD）。")
    values = {
        "company": fields.get("company", ""),
        "role_title": fields.get("role_title", ""),
        "round_name": fields.get("round_name", ""),
        "interviewer_name": fields.get("interviewer_name") or "unknown",
        "interviewer_title": fields.get("interviewer_title") or "unknown",
        "duration_minutes": str(fields.get("duration_minutes") or 45),
        "feedback_language": _feedback_language(fields),
        "interview_language": LANGUAGES[language_code(fields.get("interview_language")) or "en"],
        "job_description": fields["jd"],
        "notes": fields.get("notes") or "(no notes)",
        "resume": _resume_for(fields.get("company_slug")),
    }
    template = (PROMPTS_DIR / "setup_draft.md").read_text(encoding="utf-8")
    prompt = re.sub(r"\{\{\s*([a-z_]+)\s*\}\}", lambda m: values.get(m.group(1), m.group(0)), template)
    text = await complete(prompt, SETUP_MODEL)

    result = {}
    for key in DRAFT_FILES + ["hotwords"]:
        match = re.search(rf"<{key}>\s*(.*?)\s*</{key}>", text, re.DOTALL)
        result[key] = match.group(1).strip() if match else ""
    if not result["round_info"] or not result["question_bank"]:
        raise SetupError("草稿產生不完整，請再按一次「產生草稿」。")
    words = [w.strip(" -,") for w in result["hotwords"].splitlines() if w.strip(" -,")]
    result["hotwords"] = list(dict.fromkeys(words))[:MAX_HOTWORDS]
    return result


# Avatars the wizard offers; config.yaml accepts any GLB in web/avatars/. Voices: any Kokoro voice that speaks
# the interview language (see config.LANGUAGE_SPECS).
AVATARS = {"david": "M", "brunette": "F"}  # file name in web/avatars/ -> avatar_body
MAX_HOTWORDS = 15  # a long list makes Whisper read the list back when it can't hear you clearly


def _feedback_language(fields: dict) -> str:
    return fields.get("feedback_language") or DEFAULT_FEEDBACK_LANGUAGE[language_code(fields.get("interview_language")) or "en"]


def _write_new(path: Path, text: str):
    """Writes a file the wizard creates; a file that is already there is the user's and stays as it is."""
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def _dump(path: Path, data: dict, header: str):
    path.write_text(header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def create(fields: dict) -> str:
    """Writes the folders and returns the new interview name, e.g. "acme/tech". For an existing company
    only the round is written; its JD and company settings stay as they are."""
    company_slug = fields.get("company_slug") or slugify(fields.get("company", ""))
    round_slug = fields.get("round_slug") or slugify(fields.get("round_name", ""))
    if not SLUG.match(company_slug or "") or not SLUG.match(round_slug or ""):
        raise SetupError("公司和關卡的資料夾名稱只能用小寫英文、數字和連字號，例如 acme、tech-screen。")
    company_dir = INTERVIEWS_DIR / company_slug
    round_dir = company_dir / round_slug
    if round_dir.exists():
        raise SetupError(f"interviews/{company_slug}/{round_slug} 已經存在，請換一個關卡名稱。")
    for key in ("round_name", "interviewer_name", "interviewer_title"):
        if not str(fields.get(key, "")).strip():
            raise SetupError("請填寫關卡名稱、面試官名字和職稱。")

    hotwords = fields.get("hotwords") or []
    new_company = not (company_dir / "company.yaml").exists()
    if new_company and (company_dir / "config.yaml").exists():
        raise SetupError(f"interviews/{company_slug}/ 已經是一場面試（單一資料夾的寫法），請換一個公司名稱。")
    if new_company:
        if not fields.get("company", "").strip() or not fields.get("role_title", "").strip():
            raise SetupError("新公司需要填寫公司名稱和職缺名稱。")
        company_dir.mkdir(parents=True, exist_ok=True)
        _dump(company_dir / "company.yaml", {
            "company": fields["company"].strip(),
            "role_title": fields["role_title"].strip(),
            "feedback_language": _feedback_language(fields),
            "stt_hotwords": hotwords,
        }, "# Company settings, shared by every round of this company (created by the setup wizard)\n")
        _write_new(company_dir / "jd.md", fields.get("jd", "").strip() + "\n")
        if fields.get("company_info", "").strip():
            _write_new(company_dir / "company_info.md", fields["company_info"].strip() + "\n")
        round_hotwords = []
    else:
        existing = (yaml.safe_load((company_dir / "company.yaml").read_text(encoding="utf-8")) or {}).get("stt_hotwords") or []
        round_hotwords = [w for w in hotwords if w not in existing]

    round_dir.mkdir(parents=True)
    config = {
        "interviewer_name": fields["interviewer_name"].strip(),
        "interviewer_title": fields["interviewer_title"].strip(),
        "round_name": fields["round_name"].strip(),
        "duration_minutes": int(fields.get("duration_minutes") or 45),
        "difficulty": fields.get("difficulty") or "standard",
    }
    language = language_code(fields.get("interview_language")) or "en"
    spoken = LANGUAGE_SPECS[language]
    voice = fields.get("voice") or ""
    voice = voice if re.fullmatch(r"[a-z]{2}_[a-z0-9_]+", voice) and voice.startswith(spoken.voice_prefixes) else spoken.voice
    if language == "en":
        config.update({"voice": voice, "voice_language": "en-gb" if voice.startswith("b") else "en-us"})
    else:
        config.update({"interview_language": language, "voice": voice})
    avatar = fields.get("avatar") if fields.get("avatar") in AVATARS else "david"
    config.update({"avatar": avatar, "avatar_body": AVATARS[avatar]})
    if round_hotwords:
        config["stt_hotwords"] = round_hotwords
    _dump(round_dir / "config.yaml", config, "# This round's settings (created by the setup wizard). Every key is explained in\n"
          "# interviews/_template/round1/config.yaml and docs/reference.md.\n")
    for key in ("round_info", "question_bank", "rubric"):
        if fields.get(key, "").strip():
            (round_dir / f"{key}.md").write_text(fields[key].strip() + "\n", encoding="utf-8")
    return f"{company_slug}/{round_slug}"


# ----- Editing an existing round -----

# Files the setup page can edit, in the order it lists them, with the level a missing file is created at.
# A round's prompts/ files replace the shared templates for that round only (see config.OVERRIDABLE_PROMPTS).
EDITABLE_FILES = {
    "config.yaml": "round",
    "round_info.md": "round",
    "question_bank.md": "round",
    "rubric.md": "round",
    "jd.md": "company",
    "company_info.md": "company",
    "company.yaml": "company",
    **{f"prompts/{name}": "round" for name in OVERRIDABLE_PROMPTS},
}


def _round_file_path(folder: Path, name: str) -> tuple[Path, str]:
    """Where this round's file is (or would be created), and at which level: "round" or "company"."""
    if name not in EDITABLE_FILES:
        raise SetupError(f"不能編輯 {name}。")
    company = company_dir(folder)
    if name == "company.yaml" and not company:
        raise SetupError("這場面試沒有公司資料夾，設定都在 config.yaml。")
    if name.startswith("prompts/") or name == "config.yaml":
        return folder / name, "round"
    if name == "company.yaml":
        return company / name, "company"
    for level, d in (("round", folder), ("company", company)):
        if d and (d / name).exists():
            return d / name, level
    level = EDITABLE_FILES[name] if company else "round"
    return (company if level == "company" else folder) / name, level


def round_files(folder: Path) -> list[dict]:
    """Every editable file of a round: its text, where it lives, and whether it exists yet. A prompt the round
    has not replaced shows the shared template, so editing starts from it."""
    result = []
    for name in EDITABLE_FILES:
        try:
            path, level = _round_file_path(folder, name)
        except SetupError:
            continue
        shared = None
        if not path.exists() and name.startswith("prompts/"):
            shared = (PROMPTS_DIR / name.split("/", 1)[1]).read_text(encoding="utf-8")
        result.append({
            "name": name,
            "level": level,
            "path": path.relative_to(INTERVIEWS_DIR.parent).as_posix(),
            "exists": path.exists(),
            "text": path.read_text(encoding="utf-8") if path.exists() else (shared or ""),
        })
    return result


def save_round_file(folder: Path, name: str, text: str) -> list[dict]:
    """Saves one of a round's files and returns the round's problems afterwards (see config.validate). The old
    version goes to profile/backups/. Empty text deletes a Markdown file or a prompt override, so the round goes
    back to having none (or to the shared prompt)."""
    path, _ = _round_file_path(folder, name)
    text = text.strip()
    if name.endswith(".yaml"):
        try:
            data = yaml.safe_load(text) if text else None
        except yaml.YAMLError as e:
            raise SetupError(f"YAML 格式錯誤：{str(e).splitlines()[0]}")
        if not isinstance(data, dict):
            raise SetupError(f"{name} 要是一份 key: value 的設定清單。")
    if name == "prompts/interviewer.md" and text:
        missing = [token for token in ("{{session_mode}}", "[[END]]") if token not in text]
        if missing:
            raise SetupError(f"自訂的面試官 prompt 少了 {'、'.join(missing)}，程式需要它們來帶入練習方式和自動掛斷。")
    if path.exists():
        backups = PROFILE_DIR / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        label = re.sub(r"[^A-Za-z0-9_.-]+", "-", path.relative_to(INTERVIEWS_DIR).as_posix())
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        (backups / f"{label}-{stamp}").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    if text:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, text + "\n")
    elif path.exists():
        path.unlink()
    return validate(folder)
