import io
import zipfile

import pytest

import resume_import
from resume_import import ResumeImportError, extract_text

LONG_TEXT = "Jane Doe, ML Engineer. Five years of experience building inference pipelines with TensorRT."

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(paragraphs_xml: list[str]) -> bytes:
    body = "".join(f"<w:p>{p}</w:p>" for p in paragraphs_xml)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


@pytest.fixture
def resume_dirs(dirs, monkeypatch):
    monkeypatch.setattr(resume_import, "PROFILE_DIR", dirs.profile)
    monkeypatch.setattr(resume_import, "BACKUP_DIR", dirs.profile / "backups")
    monkeypatch.setattr(resume_import, "INTERVIEWS_DIR", dirs.interviews)
    return dirs


# --- extract_text ---------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["resume.txt", "Resume.MD"])
def test_extract_text_plain(name):
    assert extract_text(name, LONG_TEXT.encode("utf-8")) == LONG_TEXT


def test_extract_text_replaces_invalid_utf8():
    text = extract_text("r.txt", LONG_TEXT.encode("utf-8") + b"\xff")
    assert text.startswith(LONG_TEXT) and "�" in text


def test_extract_text_docx():
    data = make_docx([
        "<w:r><w:t>Jane Doe</w:t></w:r><w:r><w:t xml:space=\"preserve\"> - ML Engineer</w:t></w:r>",
        "<w:r><w:t>Skills:</w:t><w:tab/><w:t>TensorRT, ONNX, CUDA</w:t></w:r>",
        "<w:r><w:t>Line one</w:t><w:br/><w:t>Line two of a long experience section</w:t></w:r>",
    ])
    assert extract_text("cv.docx", data) == (
        "Jane Doe - ML Engineer\nSkills:\tTensorRT, ONNX, CUDA\nLine one\nLine two of a long experience section"
    )


def test_extract_text_bad_docx():
    with pytest.raises(ResumeImportError):
        extract_text("cv.docx", b"not a zip file at all" * 10)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("other.xml", "<x/>")
    with pytest.raises(ResumeImportError):
        extract_text("cv.docx", buf.getvalue())


@pytest.mark.parametrize("name", ["resume.rtf", "resume", "resume.doc"])
def test_extract_text_unsupported_suffix(name):
    with pytest.raises(ResumeImportError):
        extract_text(name, LONG_TEXT.encode())


def test_extract_text_too_little_text():
    with pytest.raises(ResumeImportError):
        extract_text("r.txt", b"Jane Doe\n\n   \t short")
    with pytest.raises(ResumeImportError):
        extract_text("cv.docx", make_docx(["<w:r><w:t>tiny</w:t></w:r>"]))


def test_extract_text_too_large(monkeypatch):
    monkeypatch.setattr(resume_import, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(ResumeImportError):
        extract_text("r.txt", LONG_TEXT.encode())


# --- resume_path and save -------------------------------------------------------------------------

def test_resume_path_targets(resume_dirs, make_round):
    round_dir = make_round("acme", "hm")
    assert resume_import.resume_path("profile") == resume_dirs.profile / "resume.md"
    assert resume_import.resume_path("company:acme") == resume_dirs.interviews / "acme" / "resume.md"
    assert resume_import.resume_path("interview:acme/hm") == round_dir / "resume.md"


@pytest.mark.parametrize("target", ["company:nope", "interview:acme/zz", "", "elsewhere"])
def test_resume_path_rejects_unknown_targets(resume_dirs, make_round, target):
    make_round("acme", "hm")
    with pytest.raises(ResumeImportError):
        resume_import.resume_path(target)


def test_save_writes_and_backs_up(resume_dirs):
    backups = resume_dirs.profile / "backups"
    path = resume_import.save("profile", "  first version  ")
    assert path == resume_dirs.profile / "resume.md"
    assert path.read_text(encoding="utf-8") == "first version\n"
    assert not backups.exists()  # nothing to back up the first time

    resume_import.save("profile", "second version")
    assert path.read_text(encoding="utf-8") == "second version\n"
    saved = list(backups.glob("resume-profile-*.md"))
    assert len(saved) == 1
    assert saved[0].read_text(encoding="utf-8") == "first version\n"


def test_save_to_interview_creates_file_and_labels_backup(resume_dirs, make_round):
    round_dir = make_round("acme", "hm")
    resume_import.save("interview:acme/hm", "v1")
    assert (round_dir / "resume.md").read_text(encoding="utf-8") == "v1\n"
    resume_import.save("interview:acme/hm", "v2")
    names = [p.name for p in (resume_dirs.profile / "backups").iterdir()]
    assert len(names) == 1 and names[0].startswith("resume-interview-acme-hm-")
