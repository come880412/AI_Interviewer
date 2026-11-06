"""Editing an existing round's files from the setup page: which files, where they live, saving with a backup,
and refusing edits that would break the interview."""

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interviewer import server, setup_wizard
from interviewer.config import InterviewConfig
from interviewer.setup_wizard import SetupError, round_files, save_round_file


@pytest.fixture(autouse=True)
def wizard_dirs(dirs, monkeypatch):
    monkeypatch.setattr(setup_wizard, "INTERVIEWS_DIR", dirs.interviews)
    monkeypatch.setattr(setup_wizard, "PROFILE_DIR", dirs.profile)
    return dirs


def by_name(folder):
    return {f["name"]: f for f in round_files(folder)}


def test_lists_every_file_where_it_lives(make_round):
    round_dir = make_round("acme", "hm", files={"round_info.md": "Round format"}, company_files={"jd.md": "The JD"})
    files = by_name(round_dir)
    assert list(files) == list(setup_wizard.EDITABLE_FILES)
    assert files["round_info.md"] == {"name": "round_info.md", "level": "round", "path": "interviews/acme/hm/round_info.md",
                                      "exists": True, "text": "Round format"}
    assert files["jd.md"]["level"] == "company" and files["jd.md"]["text"] == "The JD"
    assert files["company_info.md"]["path"] == "interviews/acme/company_info.md" and not files["company_info.md"]["exists"]
    assert files["question_bank.md"]["path"] == "interviews/acme/hm/question_bank.md"
    # A prompt the round has not replaced starts from the shared template.
    prompt = files["prompts/interviewer.md"]
    assert not prompt["exists"] and "{{session_mode}}" in prompt["text"]


def test_a_single_folder_interview_has_no_company_file(dirs):
    folder = dirs.interviews / "solo"
    folder.mkdir()
    (folder / "config.yaml").write_text("company: Solo\n", encoding="utf-8")
    files = by_name(folder)
    assert "company.yaml" not in files and files["jd.md"]["path"] == "interviews/solo/jd.md"


def test_save_writes_backs_up_and_reports_problems(dirs, make_round):
    round_dir = make_round("acme", "hm", files={"question_bank.md": "Old questions"})
    issues = save_round_file(round_dir, "question_bank.md", "  New questions  ")
    assert (round_dir / "question_bank.md").read_text(encoding="utf-8") == "New questions\n"
    backups = list((dirs.profile / "backups").iterdir())
    assert len(backups) == 1 and backups[0].name.startswith("acme-hm-question_bank.md-")
    assert backups[0].read_text(encoding="utf-8") == "Old questions"
    assert any("jd.md" in i["message"] for i in issues)  # the round's other problems come back with the save


def test_save_config_changes_the_interview(make_round):
    round_dir = make_round("acme", "hm")
    config = yaml.safe_load((round_dir / "config.yaml").read_text(encoding="utf-8"))
    config.update({"duration_minutes": 20, "coding": {"language": "cpp"}})
    save_round_file(round_dir, "config.yaml", yaml.safe_dump(config))
    cfg = InterviewConfig.load(round_dir)
    assert cfg.duration_minutes == 20 and cfg.coding == {"language": "cpp"}


@pytest.mark.parametrize("name, text, message", [
    ("config.yaml", "interviewer_name: [unclosed", "YAML 格式錯誤"),
    ("config.yaml", "- just a list", "key: value"),
    ("prompts/interviewer.md", "Be nice.", "{{session_mode}}"),
    ("secrets.txt", "x", "不能編輯"),
    ("../../etc/passwd", "x", "不能編輯"),
])
def test_save_refuses_what_would_break_the_interview(make_round, name, text, message):
    round_dir = make_round("acme", "hm")
    before = (round_dir / "config.yaml").read_text(encoding="utf-8")
    with pytest.raises(SetupError, match=message.replace("{", r"\{").replace("}", r"\}").replace("[", r"\[")):
        save_round_file(round_dir, name, text)
    assert (round_dir / "config.yaml").read_text(encoding="utf-8") == before


def test_prompt_override_round_trip(make_round, monkeypatch):
    round_dir = make_round("acme", "hm")
    custom = "You are {{interviewer_name}}. {{session_mode}} Say [[END]] when done."
    save_round_file(round_dir, "prompts/interviewer.md", custom)
    cfg = InterviewConfig.load(round_dir)
    assert cfg.render("interviewer.md", session_mode="MODE") == "You are Dana. MODE Say [[END]] when done.\n"
    save_round_file(round_dir, "prompts/interviewer.md", "   ")  # empty: back to the shared prompt
    assert not (round_dir / "prompts" / "interviewer.md").exists()
    assert "{{session_mode}}" in by_name(round_dir)["prompts/interviewer.md"]["text"]


def test_api(make_round, dirs, monkeypatch):
    make_round("acme", "hm")
    monkeypatch.setattr(server, "selection", None)
    monkeypatch.setattr(server, "active", None)
    app = FastAPI()
    server.register(app)
    client = TestClient(app, base_url="http://localhost")
    files = client.get("/api/round-files", params={"interview": "acme/hm"}).json()["files"]
    assert files[0]["name"] == "config.yaml"
    r = client.post("/api/round-files", json={"interview": "acme/hm", "name": "rubric.md", "text": "## Clarity"})
    assert r.status_code == 200 and r.json()["ok"]
    assert (dirs.interviews / "acme" / "hm" / "rubric.md").read_text(encoding="utf-8") == "## Clarity\n"
    r = client.post("/api/round-files", json={"interview": "acme/hm", "name": "config.yaml", "text": "a: [b"})
    assert r.status_code == 400 and "YAML" in r.json()["detail"]
    assert client.get("/api/round-files", params={"interview": "nope/x"}).status_code == 404
