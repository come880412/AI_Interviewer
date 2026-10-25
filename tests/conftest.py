"""Shared fixtures. Every test runs against folders under tmp_path, never the real interviews/,
profile/ or transcripts/ folders, and nothing here calls Claude or loads a speech model."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import history  # noqa: E402
import interview_config  # noqa: E402
import transcript  # noqa: E402


@pytest.fixture(autouse=True)
def dirs(tmp_path, monkeypatch):
    """Points every module-level folder constant into tmp_path."""
    interviews = tmp_path / "interviews"
    profile = tmp_path / "profile"
    transcripts = tmp_path / "transcripts"
    for d in (interviews, profile, transcripts):
        d.mkdir()

    monkeypatch.setattr(interview_config, "INTERVIEWS_DIR", interviews)
    monkeypatch.setattr(interview_config, "PROFILE_DIR", profile)
    monkeypatch.setitem(interview_config.SHARED_FILES, "resume", profile / "resume.md")
    # TRANSCRIPTS_DIR is imported by name into several modules; patch each module's own reference.
    for module in (transcript, history, interview_config):
        monkeypatch.setattr(module, "TRANSCRIPTS_DIR", transcripts)
    if "session_picker" in sys.modules:
        monkeypatch.setattr(sys.modules["session_picker"], "TRANSCRIPTS_DIR", transcripts)
        monkeypatch.setattr(sys.modules["session_picker"], "INTERVIEWS_DIR", interviews)

    monkeypatch.delenv("INTERVIEW", raising=False)
    # resolve_interview also tries the name as a path relative to the working directory.
    monkeypatch.chdir(tmp_path)
    return SimpleNamespace(root=tmp_path, interviews=interviews, profile=profile, transcripts=transcripts)


def write_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


COMPANY = {"company": "Acme", "role_title": "ML Engineer", "stt_hotwords": ["TensorRT", "ONNX"]}
ROUND = {"interviewer_name": "Dana", "interviewer_title": "Hiring Manager", "round_name": "HM round"}


@pytest.fixture
def make_round(dirs):
    """make_round("acme", "hm", company={...}, config={...}, files={"jd.md": "..."}, company_files={...})
    creates interviews/acme/company.yaml (unless company is None) and interviews/acme/hm/config.yaml."""

    def make(company_slug, round_slug, company=COMPANY, config=ROUND, files=None, company_files=None):
        company_dir = dirs.interviews / company_slug
        company_dir.mkdir(parents=True, exist_ok=True)
        if company is not None:
            write_yaml(company_dir / "company.yaml", company)
        for name, text in (company_files or {}).items():
            (company_dir / name).write_text(text, encoding="utf-8")
        round_dir = company_dir / round_slug
        write_yaml(round_dir / "config.yaml", config)
        for name, text in (files or {}).items():
            (round_dir / name).write_text(text, encoding="utf-8")
        return round_dir

    return make
