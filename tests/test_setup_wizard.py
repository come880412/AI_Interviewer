import pytest
import yaml

from interviewer import config as interview_config
from interviewer import setup_wizard
from conftest import write_yaml
from interviewer.setup_wizard import SetupError, create, slugify


@pytest.fixture(autouse=True)
def wizard_dirs(dirs, monkeypatch):
    monkeypatch.setattr(setup_wizard, "INTERVIEWS_DIR", dirs.interviews)
    monkeypatch.setattr(setup_wizard, "PROFILE_DIR", dirs.profile)
    return dirs


def fields(**overrides):
    base = {
        "company": "Acme Robotics",
        "role_title": "ML Engineer",
        "round_name": "Tech Screen",
        "interviewer_name": " Dana ",
        "interviewer_title": "Staff Engineer",
        "duration_minutes": "40",
        "feedback_language": "English",
        "jd": "  The JD.  ",
        "company_info": "Founded in 2010.",
        "round_info": "Coding and ML fundamentals.",
        "question_bank": "1. Explain backprop.",
        "rubric": "",
        "hotwords": ["TensorRT", "ONNX"],
    }
    base.update(overrides)
    return base


def read_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name, slug", [
    ("Acme Vision", "acme-vision"),
    ("Acme Robotics, Inc.", "acme-robotics-inc"),
    ("  Tech Screen #2 ", "tech-screen-2"),
    ("HM -- round", "hm-round"),
    ("台積電", ""),
    ("", ""),
])
def test_slugify(name, slug):
    assert slugify(name) == slug


def test_create_new_company(wizard_dirs):
    name = create(fields())
    assert name == "acme-robotics/tech-screen"
    company = wizard_dirs.interviews / "acme-robotics"
    round_dir = company / "tech-screen"

    assert read_yaml(company / "company.yaml") == {
        "company": "Acme Robotics", "role_title": "ML Engineer", "feedback_language": "English",
        "stt_hotwords": ["TensorRT", "ONNX"],
    }
    assert (company / "jd.md").read_text(encoding="utf-8") == "The JD.\n"
    assert (company / "company_info.md").read_text(encoding="utf-8") == "Founded in 2010.\n"

    config = read_yaml(round_dir / "config.yaml")
    assert config == {
        "interviewer_name": "Dana", "interviewer_title": "Staff Engineer", "round_name": "Tech Screen",
        "duration_minutes": 40, "difficulty": "standard", "voice": "am_michael", "voice_language": "en-us",
        "avatar": "david", "avatar_body": "M",
    }  # hotwords live in company.yaml only
    assert (round_dir / "round_info.md").exists() and (round_dir / "question_bank.md").exists()
    assert not (round_dir / "rubric.md").exists()  # empty drafts are not written

    # The result is a working interview for the rest of the app.
    assert name in interview_config.list_interviews()
    cfg = interview_config.InterviewConfig.load(round_dir)
    assert cfg.stt_hotwords == ["TensorRT", "ONNX"] and cfg.duration_minutes == 40
    assert [i for i in interview_config.validate(round_dir) if i["level"] == "error"] == []


def test_create_with_explicit_slugs_and_british_voice(wizard_dirs):
    name = create(fields(company_slug="acme", round_slug="hm", voice="bf_emma", duration_minutes=None))
    assert name == "acme/hm"
    config = read_yaml(wizard_dirs.interviews / "acme" / "hm" / "config.yaml")
    assert config["voice"] == "bf_emma" and config["voice_language"] == "en-gb"
    assert config["duration_minutes"] == 45


@pytest.mark.parametrize("language, voice, avatar, expected", [
    ("en", "af_heart", "brunette", {"voice": "af_heart", "voice_language": "en-us", "avatar": "brunette", "avatar_body": "F"}),
    ("en", "zf_001", "nobody", {"voice": "am_michael", "avatar": "david", "avatar_body": "M"}),  # not offered: defaults
    ("zh-TW", "zf_001", "brunette", {"voice": "zf_001", "interview_language": "zh-TW", "avatar_body": "F"}),
    ("zh-TW", "af_heart", "david", {"voice": "zm_010", "avatar": "david"}),  # an English voice can't speak Mandarin
    ("ja", "jf_alpha", "brunette", {"voice": "jf_alpha", "interview_language": "ja"}),
    ("es", "am_michael", "david", {"voice": "em_alex", "interview_language": "es"}),
    ("pt-BR", "pf_dora", "david", {"voice": "pf_dora", "interview_language": "pt-BR"}),
])
def test_chosen_voice_and_avatar(wizard_dirs, language, voice, avatar, expected):
    create(fields(interview_language=language, voice=voice, avatar=avatar))
    config = read_yaml(wizard_dirs.interviews / "acme-robotics" / "tech-screen" / "config.yaml")
    assert expected.items() <= config.items()


def test_files_written_by_the_wizard_have_english_comments(wizard_dirs):
    create(fields())
    for path in (wizard_dirs.interviews / "acme-robotics" / "company.yaml",
                 wizard_dirs.interviews / "acme-robotics" / "tech-screen" / "config.yaml"):
        assert path.read_text(encoding="utf-8").isascii()


def test_draft_keeps_a_short_hotword_list(monkeypatch):
    import asyncio
    words = "\n".join(f"Term{i}" for i in range(40)) + "\nTerm1"
    reply = f"<round_info>info</round_info><question_bank>q</question_bank><hotwords>{words}</hotwords>"

    async def complete(prompt, model):
        return reply

    monkeypatch.setattr(setup_wizard, "complete", complete)
    result = asyncio.run(setup_wizard.draft({"jd": "A JD.", "interview_language": "en"}))
    assert result["hotwords"] == [f"Term{i}" for i in range(setup_wizard.MAX_HOTWORDS)]


def test_add_round_to_existing_company_keeps_only_new_hotwords(wizard_dirs):
    company = wizard_dirs.interviews / "acme"
    write_yaml(company / "company.yaml", {"company": "Acme", "role_title": "MLE", "stt_hotwords": ["TensorRT"]})
    (company / "jd.md").write_text("original jd\n", encoding="utf-8")
    before = (company / "company.yaml").read_text(encoding="utf-8")

    name = create(fields(company_slug="acme", company="", role_title="", round_name="HM", jd="new jd",
                         hotwords=["TensorRT", "CUDA", "QNN"]))
    assert name == "acme/hm"
    assert (company / "company.yaml").read_text(encoding="utf-8") == before
    assert (company / "jd.md").read_text(encoding="utf-8") == "original jd\n"
    assert read_yaml(company / "hm" / "config.yaml")["stt_hotwords"] == ["CUDA", "QNN"]


def test_add_round_without_new_hotwords(wizard_dirs):
    write_yaml(wizard_dirs.interviews / "acme" / "company.yaml", {"company": "Acme", "stt_hotwords": ["A"]})
    create(fields(company_slug="acme", round_slug="hm", hotwords=["A"]))
    assert "stt_hotwords" not in read_yaml(wizard_dirs.interviews / "acme" / "hm" / "config.yaml")


def test_existing_round_is_rejected(wizard_dirs):
    create(fields(company_slug="acme", round_slug="hm"))
    with pytest.raises(SetupError):
        create(fields(company_slug="acme", round_slug="hm"))


@pytest.mark.parametrize("overrides", [
    {"company": "!!!"},  # slugifies to nothing
    {"company_slug": "Acme Corp"},
    {"round_slug": "-hm"},
    {"round_slug": "hm_2"},
    {"round_name": "", "round_slug": None},
])
def test_bad_slug_is_rejected(wizard_dirs, overrides):
    with pytest.raises(SetupError):
        create(fields(**overrides))
    assert list(wizard_dirs.interviews.iterdir()) == []


@pytest.mark.parametrize("overrides", [
    {"interviewer_name": "  "},
    {"interviewer_title": ""},
    {"round_name": "", "round_slug": "hm"},
    {"role_title": ""},  # needed for a new company
])
def test_missing_fields_are_rejected(wizard_dirs, overrides):
    with pytest.raises(SetupError):
        create(fields(**overrides))
    assert list(wizard_dirs.interviews.iterdir()) == []


def test_companies_listing(wizard_dirs):
    create(fields(company_slug="acme", round_slug="hm"))
    create(fields(company_slug="acme", round_slug="tech"))
    write_yaml(wizard_dirs.interviews / "_template" / "company.yaml", {"company": "Template"})
    result = setup_wizard.companies()
    assert len(result) == 1
    assert result[0]["slug"] == "acme" and result[0]["company"] == "Acme Robotics"
    assert result[0]["rounds"] == ["hm", "tech"]
    assert result[0]["jd"] == "The JD.\n"


def test_a_new_company_never_overwrites_files_already_in_its_folder(wizard_dirs):
    folder = wizard_dirs.interviews / "acme-robotics"
    folder.mkdir()
    (folder / "jd.md").write_text("My edited JD.", encoding="utf-8")
    create(fields())
    assert (folder / "jd.md").read_text(encoding="utf-8") == "My edited JD."
    assert (folder / "company_info.md").exists()  # new files are still written


def test_a_single_folder_interview_is_not_turned_into_a_company(wizard_dirs):
    folder = wizard_dirs.interviews / "acme-robotics"
    folder.mkdir()
    (folder / "config.yaml").write_text("company: Acme\n", encoding="utf-8")
    with pytest.raises(SetupError, match="已經是一場面試"):
        create(fields())
    assert not (folder / "tech-screen").exists()


@pytest.mark.parametrize("language, expected", [("en", "English"), ("zh-TW", "Traditional Chinese (Taiwan)")])
def test_report_language_follows_the_interview_language_by_default(wizard_dirs, language, expected):
    create(fields(feedback_language="", interview_language=language))
    assert read_yaml(wizard_dirs.interviews / "acme-robotics" / "company.yaml")["feedback_language"] == expected
