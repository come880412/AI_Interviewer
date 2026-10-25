"""Creates a new company or round from the setup page: Claude drafts round_info.md, question_bank.md,
rubric.md, company_info.md and speech-recognition hotwords from the JD, the candidate's notes and the
resume; the candidate reviews the drafts, and create() writes the folders.
"""

import os
import re
from pathlib import Path

import yaml

from interview_config import INTERVIEWS_DIR, PROFILE_DIR, PROMPTS_DIR
from llm import complete

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
            "feedback_language": raw.get("feedback_language", "Traditional Chinese (Taiwan)"),
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
        "feedback_language": fields.get("feedback_language") or "Traditional Chinese (Taiwan)",
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
    result["hotwords"] = [w.strip(" -,") for w in result["hotwords"].splitlines() if w.strip(" -,")]
    return result


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
    if new_company:
        if not fields.get("company", "").strip() or not fields.get("role_title", "").strip():
            raise SetupError("新公司需要填寫公司名稱和職缺名稱。")
        company_dir.mkdir(parents=True, exist_ok=True)
        _dump(company_dir / "company.yaml", {
            "company": fields["company"].strip(),
            "role_title": fields["role_title"].strip(),
            "feedback_language": fields.get("feedback_language") or "Traditional Chinese (Taiwan)",
            "stt_hotwords": hotwords,
        }, "# 公司層級設定：這家公司每一關共用（由網頁精靈建立）\n")
        (company_dir / "jd.md").write_text(fields.get("jd", "").strip() + "\n", encoding="utf-8")
        if fields.get("company_info", "").strip():
            (company_dir / "company_info.md").write_text(fields["company_info"].strip() + "\n", encoding="utf-8")
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
        "voice": fields.get("voice") or "am_michael",
        "voice_language": "en-gb" if (fields.get("voice") or "").startswith("b") else "en-us",
    }
    if round_hotwords:
        config["stt_hotwords"] = round_hotwords
    _dump(round_dir / "config.yaml", config, "# 這一關的設定（由網頁精靈建立）\n")
    for key in ("round_info", "question_bank", "rubric"):
        if fields.get(key, "").strip():
            (round_dir / f"{key}.md").write_text(fields[key].strip() + "\n", encoding="utf-8")
    return f"{company_slug}/{round_slug}"
