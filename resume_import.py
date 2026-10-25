"""Turns an uploaded resume (PDF, Word, text or Markdown) into the plain-text resume.md the prompts use.

Text is extracted locally, then Claude rewrites it into a fixed layout without changing any facts.
Saving keeps the previous version in profile/backups/.
"""

import io
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from interview_config import INTERVIEWS_DIR, PROFILE_DIR, PROMPTS_DIR, list_interviews, resume_layers
from llm import complete

RESUME_MODEL = os.getenv("FEEDBACK_MODEL", os.getenv("LLM_MODEL", "claude-opus-5-5"))
BACKUP_DIR = PROFILE_DIR / "backups"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED = (".pdf", ".docx", ".txt", ".md")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ResumeImportError(ValueError):
    """A problem the person can fix, such as an unsupported or image-only file."""


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    except PyPdfError:
        raise ResumeImportError("這個 PDF 打不開，可能已損毀。請重新匯出一次，或改上傳 Word 檔。")


def _docx_text(data: bytes) -> str:
    try:
        xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        raise ResumeImportError("這個 .docx 檔打不開。請用 Word 重新存一次，或改上傳 PDF。")
    paragraphs = []
    for p in ElementTree.fromstring(xml).iter(f"{W}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{W}t":
                parts.append(node.text or "")
            elif node.tag == f"{W}tab":
                parts.append("\t")
            elif node.tag in (f"{W}br", f"{W}cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise ResumeImportError(f"不支援 {suffix or '這種'} 檔案。請上傳 PDF、.docx、.txt 或 .md。")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ResumeImportError("檔案超過 10 MB。")
    if suffix == ".pdf":
        text = _pdf_text(data)
    elif suffix == ".docx":
        text = _docx_text(data)
    else:
        text = data.decode("utf-8", errors="replace")
    if len(re.sub(r"\s", "", text)) < 50:
        raise ResumeImportError("這個檔案幾乎讀不到文字。如果是掃描的 PDF，請改上傳 Word 或文字檔。")
    return text


async def convert(filename: str, data: bytes) -> str:
    """Returns the resume in the standard layout. Markdown uploads are taken as already formatted."""
    text = extract_text(filename, data)
    if filename.lower().endswith(".md"):
        return text.strip()
    template = (PROMPTS_DIR / "resume_import.md").read_text(encoding="utf-8")
    result = await complete(template.replace("{{resume_text}}", text), RESUME_MODEL)
    # Models occasionally wrap the answer in a code fence despite the instructions.
    return re.sub(r"^```[a-z]*\n|\n```$", "", result.strip()).strip()


def resume_path(target: str) -> Path:
    """target is "profile", "company:<company>" or "interview:<company>/<round>" (see resume_layers)."""
    if target == "profile":
        return PROFILE_DIR / "resume.md"
    for name in list_interviews():
        for layer_target, _, path in resume_layers(INTERVIEWS_DIR / name):
            if layer_target == target:
                return path
    raise ResumeImportError(f"找不到存放位置：{target}")


def save(target: str, text: str) -> Path:
    path = resume_path(target)
    if path.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        label = re.sub(r"[^A-Za-z0-9_-]+", "-", target).strip("-")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        (BACKUP_DIR / f"resume-{label}-{stamp}.md").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path
