import pytest

import interview_config as ic
from conftest import COMPANY, ROUND, write_yaml
from transcript import Transcript

ALL_FILES = {name: f"{name} text" for name in ("jd.md", "round_info.md", "question_bank.md", "rubric.md", "company_info.md")}


# --- layout and loading ---------------------------------------------------------------------------

def test_company_dir_and_interview_name(dirs, make_round):
    round_dir = make_round("acme", "hm")
    assert ic.company_dir(round_dir) == dirs.interviews / "acme"
    assert ic.interview_name(round_dir) == "acme/hm"

    solo = make_round("solo", "inner", company=None)  # parent has no company.yaml
    assert ic.company_dir(solo) is None
    assert ic.interview_name(dirs.root / "elsewhere" / "thing") == "thing"  # outside interviews/


def test_load_merges_company_and_round(dirs, make_round):
    round_dir = make_round(
        "acme", "hm",
        company={**COMPANY, "voice": "bf_emma", "duration_minutes": 60},
        config={**ROUND, "duration_minutes": 45, "voice_language": "en-gb", "stt_hotwords": ["ONNX", "QNN"]},
        files={"round_info.md": "  HM round info  \n"},
        company_files={"jd.md": "Company JD"},
    )
    cfg = ic.InterviewConfig.load(round_dir)
    assert cfg.name == "acme/hm"
    assert cfg.duration_minutes == 45  # the round overrides the company
    assert cfg.voice == "bf_emma"  # inherited from the company
    assert cfg.voice_language == "en-gb"
    assert cfg.voice_clone is None
    assert cfg.stt_hotwords == ["TensorRT", "ONNX", "QNN"]  # company first, duplicates dropped
    v = cfg.variables
    assert v["company"] == "Acme" and v["round_name"] == "HM round" and v["duration_minutes"] == "45"
    assert "stt_hotwords" not in v  # lists are not template variables
    assert v["job_description"] == "Company JD"
    assert v["round_info"] == "HM round info"
    assert v["rubric"] == ic.NOT_PROVIDED
    assert v["resume"] == ic.NOT_PROVIDED


def test_load_defaults(dirs, make_round):
    cfg = ic.InterviewConfig.load(make_round("acme", "hm", company={"company": "Acme"}))
    assert (cfg.voice, cfg.voice_language, cfg.duration_minutes) == ("am_michael", "en-us", 30)


def test_file_lookup_order_round_company_profile(dirs, make_round):
    round_dir = make_round("acme", "hm")
    company = dirs.interviews / "acme"
    (dirs.profile / "resume.md").write_text("profile resume", encoding="utf-8")
    assert ic.InterviewConfig.load(round_dir).variables["resume"] == "profile resume"

    (company / "resume.md").write_text("company resume", encoding="utf-8")
    assert ic.InterviewConfig.load(round_dir).variables["resume"] == "company resume"

    (round_dir / "resume.md").write_text("round resume", encoding="utf-8")
    assert ic.InterviewConfig.load(round_dir).variables["resume"] == "round resume"

    (company / "jd.md").write_text("company jd", encoding="utf-8")
    (round_dir / "jd.md").write_text("round jd", encoding="utf-8")
    assert ic.InterviewConfig.load(round_dir).variables["job_description"] == "round jd"


def test_only_resume_falls_back_to_profile(dirs, make_round):
    (dirs.profile / "jd.md").write_text("should not be used", encoding="utf-8")
    cfg = ic.InterviewConfig.load(make_round("acme", "hm"))
    assert cfg.variables["job_description"] == ic.NOT_PROVIDED


def test_standalone_interview_folder(dirs):
    folder = dirs.interviews / "solo"
    write_yaml(folder / "config.yaml", {**COMPANY, **ROUND, "stt_hotwords": ["A", "B", "A"]})
    cfg = ic.InterviewConfig.load(folder)
    assert cfg.name == "solo"
    assert cfg.stt_hotwords == ["A", "B"]


def test_voice_clone_found_in_company_or_missing(dirs, make_round):
    round_dir = make_round("acme", "hm", config={**ROUND, "voice_clone": "me.wav"})
    with pytest.raises(FileNotFoundError):
        ic.InterviewConfig.load(round_dir)
    (dirs.interviews / "acme" / "me.wav").write_bytes(b"RIFF")
    assert ic.InterviewConfig.load(round_dir).voice_clone == dirs.interviews / "acme" / "me.wav"


def test_render(dirs, make_round, monkeypatch):
    prompts = dirs.root / "prompts"
    prompts.mkdir()
    (prompts / "t.md").write_text("Hi {{ interviewer_name }} at {{company}}, {{extra}}.", encoding="utf-8")
    (prompts / "bad.md").write_text("{{ nope }}", encoding="utf-8")
    monkeypatch.setattr(ic, "PROMPTS_DIR", prompts)
    cfg = ic.InterviewConfig.load(make_round("acme", "hm"))
    assert cfg.render("t.md", extra="ok") == "Hi Dana at Acme, ok."
    with pytest.raises(KeyError):
        cfg.render("bad.md")


# --- listing and resolving ------------------------------------------------------------------------

def test_list_interviews_skips_underscore_parts(dirs, make_round):
    make_round("acme", "hm")
    make_round("acme", "tech")
    make_round("acme", "_draft")
    make_round("_template", "round")
    write_yaml(dirs.interviews / "solo" / "config.yaml", ROUND)
    write_yaml(dirs.interviews / "_old" / "config.yaml", ROUND)
    assert ic.list_interviews() == ["acme/hm", "acme/tech", "solo"]


def test_list_interviews_without_folder(dirs, monkeypatch):
    monkeypatch.setattr(ic, "INTERVIEWS_DIR", dirs.root / "missing")
    assert ic.list_interviews() == []


def test_resolve_interview(dirs, make_round):
    hm = make_round("acme", "hm")
    make_round("globex", "tech")
    make_round("globex", "hm")
    assert ic.resolve_interview("acme/hm") == hm
    assert ic.resolve_interview(str(hm)) == hm  # a path works too
    assert ic.resolve_interview("acme") == dirs.interviews / "acme/hm"  # the company's only round
    assert ic.resolve_interview("acme/") == dirs.interviews / "acme/hm"
    with pytest.raises(SystemExit, match="Available: acme/hm, globex/hm, globex/tech"):
        ic.resolve_interview("globex")  # two rounds: ambiguous
    with pytest.raises(SystemExit, match="not found"):
        ic.resolve_interview("nope")


def test_resolve_company_prefix_does_not_match_longer_name(dirs, make_round):
    make_round("acme-labs", "hm")
    with pytest.raises(SystemExit):
        ic.resolve_interview("acme")


def test_pick_interview_explicit_env_and_first(dirs, make_round, monkeypatch):
    make_round("acme", "hm")
    make_round("globex", "tech")
    assert ic.pick_interview("globex/tech", ask=False) == dirs.interviews / "globex/tech"
    assert ic.pick_interview(ask=False) == dirs.interviews / "acme/hm"  # first one
    monkeypatch.setenv("INTERVIEW", "globex")
    assert ic.pick_interview(ask=False) == dirs.interviews / "globex/tech"


def test_pick_interview_single_interview_does_not_ask(dirs, make_round, monkeypatch):
    make_round("acme", "hm")
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("should not ask"))
    assert ic.pick_interview() == dirs.interviews / "acme/hm"


def test_pick_interview_no_interviews(dirs):
    with pytest.raises(SystemExit):
        ic.pick_interview(ask=False)


def test_pick_interview_from_transcript_tag(dirs, make_round):
    make_round("acme", "hm")
    make_round("globex", "tech")
    t = Transcript("globex/tech", "T")
    assert ic.pick_interview(transcript=t.path, ask=False) == dirs.interviews / "globex/tech"
    # An explicit name beats the transcript.
    assert ic.pick_interview("acme/hm", transcript=t.path, ask=False) == dirs.interviews / "acme/hm"


def test_pick_interview_inferred_from_transcript_folder(dirs, make_round):
    make_round("acme", "hm")
    make_round("globex", "tech")
    old = dirs.transcripts / "globex" / "tech" / "20261001-1000-transcript.md"
    old.parent.mkdir(parents=True)
    old.write_text("# Old\n\n**Interviewer:** Hi\n\n", encoding="utf-8")  # no interview tag
    assert ic.pick_interview(transcript=old, ask=False) == dirs.interviews / "globex/tech"

    # A folder that is not an interview, or a file outside transcripts/, falls back to the first.
    stray = dirs.transcripts / "deleted" / "x-transcript.md"
    stray.parent.mkdir()
    stray.write_text("**Interviewer:** Hi\n\n", encoding="utf-8")
    assert ic.pick_interview(transcript=stray, ask=False) == dirs.interviews / "acme/hm"
    outside = dirs.root / "x-transcript.md"
    outside.write_text("**Interviewer:** Hi\n\n", encoding="utf-8")
    assert ic._interview_from_transcript_folder(outside) is None


# --- resume layers and rubric ---------------------------------------------------------------------

def test_resume_layers(dirs, make_round):
    round_dir = make_round("acme", "hm")
    assert ic.resume_layers(round_dir) == [
        ("interview:acme/hm", "interview", round_dir / "resume.md"),
        ("company:acme", "company", dirs.interviews / "acme" / "resume.md"),
        ("profile", "profile", dirs.profile / "resume.md"),
    ]
    solo = dirs.interviews / "solo"
    write_yaml(solo / "config.yaml", ROUND)
    assert [t for t, _, _ in ic.resume_layers(solo)] == ["interview:solo", "profile"]


def test_rubric_areas():
    rubric = "# Rubric\n\n## Technical depth\nanchors\n\n##  Communication  \n### Not an area\n## System design"
    assert ic.rubric_areas(rubric) == ["Technical depth", "Communication", "System design"]
    assert ic.rubric_areas("") == []


# --- validate -------------------------------------------------------------------------------------

def levels(issues, level):
    return [i["message"] for i in issues if i["level"] == level]


def test_validate_complete_interview_has_no_issues(dirs, make_round):
    round_dir = make_round("acme", "hm", company_files=ALL_FILES)
    (dirs.profile / "resume.md").write_text("resume", encoding="utf-8")
    assert ic.validate(round_dir) == []


def test_validate_missing_required_keys(dirs, make_round):
    round_dir = make_round("acme", "hm", company={"company": "Acme"}, config={"round_name": "HM"},
                           company_files=ALL_FILES)
    errors = levels(ic.validate(round_dir), "error")
    assert len(errors) == 3
    for key in ("role_title", "interviewer_name", "interviewer_title"):
        assert any(key in e for e in errors)


def test_validate_bad_yaml(dirs, make_round):
    round_dir = make_round("acme", "hm")
    (round_dir / "config.yaml").write_text("round_name: [unclosed\n", encoding="utf-8")
    issues = ic.validate(round_dir)
    assert len(issues) == 1 and issues[0]["level"] == "error" and "YAML" in issues[0]["message"]


def test_validate_unknown_key_warning(dirs, make_round):
    round_dir = make_round("acme", "hm", config={**ROUND, "interviewr_name": "typo"}, company_files=ALL_FILES)
    (dirs.profile / "resume.md").write_text("resume", encoding="utf-8")
    issues = ic.validate(round_dir)
    assert levels(issues, "error") == []
    warnings = levels(issues, "warning")
    assert len(warnings) == 1 and "interviewr_name" in warnings[0]


def test_validate_missing_optional_files_are_warnings(dirs, make_round):
    issues = ic.validate(make_round("acme", "hm"))
    assert levels(issues, "error") == []
    warnings = levels(issues, "warning")
    assert len(warnings) == 6  # five markdown files plus the resume
    for name in ALL_FILES:
        assert any(name in w for w in warnings)


def test_validate_bad_values(dirs, make_round):
    round_dir = make_round("acme", "hm", config={**ROUND, "duration_minutes": 0, "difficulty": "hard",
                                                 "voice_clone": "missing.wav"}, company_files=ALL_FILES)
    issues = ic.validate(round_dir)
    errors = levels(issues, "error")
    assert any("duration_minutes" in e for e in errors)
    assert any("missing.wav" in e for e in errors)
    assert any("difficulty" in w for w in levels(issues, "warning"))

    write_yaml(round_dir / "config.yaml", {**ROUND, "duration_minutes": "abc"})
    assert any("duration_minutes" in e for e in levels(ic.validate(round_dir), "error"))


def test_validate_non_mapping_yaml(dirs, make_round):
    round_dir = make_round("acme", "hm")
    (round_dir / "config.yaml").write_text("- round_name\n- interviewer_name\n", encoding="utf-8")
    assert levels(ic.validate(round_dir), "error")


# --- interview language ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    (None, "en"), ("", "en"), ("en", "en"), ("English", "en"),
    ("zh-TW", "zh-TW"), ("zh", "zh-TW"), ("zh-tw", "zh-TW"), ("中文", "zh-TW"),
    ("fr", None),
])
def test_language_code(value, expected):
    assert ic.language_code(value) == expected


def test_load_english_by_default(dirs, make_round):
    cfg = ic.InterviewConfig.load(make_round("acme", "hm"))
    assert cfg.language == "en" and not cfg.chinese
    assert cfg.variables["interview_language"] == "English"
    assert cfg.variables["feedback_language"] == "English"


def test_load_chinese_interview(dirs, make_round):
    cfg = ic.InterviewConfig.load(make_round("acme", "hr", config={**ROUND, "interview_language": "zh"}))
    assert cfg.language == "zh-TW" and cfg.chinese
    assert cfg.variables["interview_language"].startswith("Mandarin Chinese")
    assert cfg.variables["feedback_language"] == "Traditional Chinese (Taiwan)"


def test_load_keeps_explicit_feedback_language(dirs, make_round):
    cfg = ic.InterviewConfig.load(make_round(
        "acme", "hr", config={**ROUND, "interview_language": "zh-TW", "feedback_language": "English"}))
    assert cfg.variables["feedback_language"] == "English"


def test_load_rejects_unknown_language(dirs, make_round):
    with pytest.raises(ValueError, match="interview_language"):
        ic.InterviewConfig.load(make_round("acme", "hm", config={**ROUND, "interview_language": "fr"}))


def test_validate_language(dirs, make_round):
    bad = make_round("acme", "fr", config={**ROUND, "interview_language": "fr"}, company_files=ALL_FILES)
    assert any("interview_language" in e for e in levels(ic.validate(bad), "error"))
    cloned = make_round("acme", "zh", config={**ROUND, "interview_language": "zh-TW", "pocket_voice": "javert"},
                        company_files=ALL_FILES)
    assert any("Pocket TTS" in w for w in levels(ic.validate(cloned), "warning"))
