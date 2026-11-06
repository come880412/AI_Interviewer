"""The setup website at http://localhost:7860/, served next to Pipecat's /client page.

- Choose the interview, full interview or focused drill, or a transcript to resume; the choice applies
  to the next connection at /client.
- See the session in progress, end it, and share a notepad with the interviewer (/notepad).
- Read reports and transcripts (/report), generate a missing report, and follow progress (/progress).
- Import a resume, and create a new company or round with Claude's drafts.
"""

import asyncio
import html
import os
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import markdown
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

from interviewer import coding
from interviewer import leetcode
from interviewer import resume_import
from interviewer import setup_wizard
from interviewer.feedback import generate_feedback
from interviewer.history import drill_suggestions, sessions
from interviewer.config import (
    INTERVIEWS_DIR,
    ROOT,
    InterviewConfig,
    interview_name,
    list_interviews,
    resume_layers,
    rubric_areas,
    validate,
)
from interviewer.transcript import TRANSCRIPTS_DIR, read_transcript, saved_transcripts, sibling

WEB = ROOT / "web"


@dataclass
class Selection:
    interview: Path
    resume: Path | None = None  # transcript to continue; None starts a new session
    mode: str = "full"  # "full" interview, a focused "drill", or a LeetCode-style "coding" interview
    topic: str | None = None  # drill topic
    minutes: int | None = None  # drill or coding length
    coach: bool = False  # drill with feedback and a model answer after every answer
    language: str = "python"  # coding: one of coding.LANGUAGES
    difficulties: list[str] | None = None  # coding: some of coding.DIFFICULTIES (None: all)
    tags: list[str] | None = None  # coding: LeetCode tag slugs, any of which may match (None: any tag)
    rating: list | None = None  # coding: [min, max] zerotrac rating, either may be None; None: no limit
    interview_only: bool = True  # coding: only interview-style problems (leetcode.interview_style)
    statement: str = "interview"  # coding: one of coding.STATEMENT_STYLES
    problems: list[str] | None = None  # coding: picked on the setup page; bot.py picks them if missing

    def session(self) -> dict:
        if self.mode == "drill":
            session = {"mode": "drill", "topic": self.topic, "minutes": self.minutes}
            if self.coach:
                session["coach"] = True
            return session
        if self.mode == "coding":
            session = {"mode": "coding", "language": self.language,
                       "difficulties": self.difficulties or list(coding.DIFFICULTIES), "tags": self.tags or [],
                       "rating": self.rating, "interview_only": self.interview_only, "statement": self.statement,
                       "minutes": self.minutes}
            if self.problems:
                session["problems"] = list(self.problems)
            return session
        return {"mode": "full"}


@dataclass
class ActiveSession:
    """The interview running right now, so the page can show it, end it, and feed it the notepad."""
    interview: str
    transcript: Path
    session: dict
    minutes: int
    elapsed: Callable[[], float]  # seconds of interview time so far, pauses left out
    is_paused: Callable[[], bool]
    pause: Callable[[], Awaitable[None]]
    resume: Callable[[], Awaitable[None]]
    end: Callable[[], Awaitable[None]]
    update_notepad: Callable[..., None]  # (text, problem id or None)
    coding: Callable[[], dict] | None = None  # coding interviews: the problem on screen, for the notepad page


# What the next connection runs. bot.py sets it at startup and after each session.
selection: Selection | None = None
active: ActiveSession | None = None
# Reports being generated, and the last error per transcript, keyed by transcript path.
generating: set[str] = set()
report_errors: dict[str, str] = {}
_tasks: set[asyncio.Task] = set()


async def generate_report(folder: Path, transcript_path: Path):
    key = str(transcript_path)
    if key in generating:
        return
    generating.add(key)
    report_errors.pop(key, None)
    try:
        logger.info(f"Generating feedback report for {transcript_path}, this can take a minute...")
        out = await generate_feedback(InterviewConfig.load(folder), read_transcript(transcript_path))
        logger.info(f"Feedback report saved to {out}")
    except Exception as e:
        logger.exception("Feedback failed")
        report_errors[key] = str(e)
    finally:
        generating.discard(key)


class SelectionRequest(BaseModel):
    interview: str
    resume: str | None = None  # transcript file name inside transcripts/<interview>/
    mode: str = "full"
    topic: str | None = None
    minutes: int | None = None
    coach: bool = False
    language: str = "python"
    difficulties: list[str] = ["easy", "medium", "hard"]
    tags: list[str] = []
    rating_min: int | None = None
    rating_max: int | None = None
    interview_only: bool = True
    statement: str = "interview"


class CodingFilters(BaseModel):
    difficulties: list[str] = ["easy", "medium", "hard"]
    tags: list[str] = []
    rating_min: int | None = None
    rating_max: int | None = None
    interview_only: bool = True


def _check_coding_filters(f) -> tuple[list[str], list[str], list | None, bool]:
    """Validated (difficulties, tags, rating range or None, interview problems only), or an HTTP 400."""
    difficulties = [d for d in coding.DIFFICULTIES if d in f.difficulties]
    if not difficulties or len(difficulties) != len(set(f.difficulties)):
        raise HTTPException(400, "難度至少要選一個，只能是 easy、medium、hard。")
    for value in (f.rating_min, f.rating_max):
        if value is not None and not 0 <= value <= 4000:
            raise HTTPException(400, "rating 要在 0 到 4000 之間。")
    if f.rating_min is not None and f.rating_max is not None and f.rating_min > f.rating_max:
        raise HTTPException(400, "rating 下限不能大於上限。")
    rating = [f.rating_min, f.rating_max] if f.rating_min is not None or f.rating_max is not None else None
    return difficulties, list(dict.fromkeys(f.tags)), rating, f.interview_only


class ResumeSaveRequest(BaseModel):
    target: str  # "profile", "company:<company>" or "interview:<company>/<round>"
    text: str


class TranscriptRef(BaseModel):
    interview: str
    file: str


class RoundFileRequest(BaseModel):
    interview: str
    name: str  # one of setup_wizard.EDITABLE_FILES
    text: str


class NotepadRequest(BaseModel):
    text: str
    problem: str | None = None  # coding interviews: the problem id the page was showing


def _transcript_path(interview: str, file: str) -> Path:
    """Only a bare file name inside a known interview's transcript folder is accepted."""
    if interview not in list_interviews():
        raise HTTPException(404, f"找不到面試：{interview}")
    path = TRANSCRIPTS_DIR / interview / Path(file).name
    if not path.exists() or not path.name.endswith("-transcript.md"):
        raise HTTPException(404, f"找不到逐字稿：{file}")
    return path


def _started(path: Path) -> str:
    try:
        return datetime.strptime(path.name[:13], "%Y%m%d-%H%M").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return path.stem


def _resume_layers(folder: Path) -> list[dict]:
    """Every place this interview's resume can be saved, most specific first, and which one is in use."""
    layers, in_use = [], False
    for target, level, path in resume_layers(folder):
        layer = {"target": target, "level": level, "path": path.relative_to(ROOT).as_posix(), "exists": path.exists()}
        if path.exists() and not in_use:
            in_use = layer["in_use"] = True
            text = path.read_text(encoding="utf-8").strip()
            layer["updated"] = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            layer["first_line"] = text.splitlines()[0] if text else ""
        layers.append(layer)
    return layers


def _transcripts(cfg: InterviewConfig) -> list[dict]:
    items = []
    for saved in saved_transcripts(TRANSCRIPTS_DIR / cfg.name, newest_first=True):
        path = saved.path
        if not saved.turns:
            continue
        minutes = int(saved.session.get("minutes") or cfg.duration_minutes)
        interviewer = [t.text for t in saved.turns if t.speaker == "Interviewer"]
        items.append({
            "file": path.name,
            "started": _started(path),
            "session": saved.session,
            "planned_minutes": minutes,
            "turns": len(saved.turns),
            "minutes": round(min(saved.elapsed_secs, minutes * 60) / 60),
            "has_feedback": sibling(path, "feedback").exists(),
            "has_scores": sibling(path, "scores", ".json").exists(),
            "generating": str(path) in generating,
            "report_error": report_errors.get(str(path)),
            "active": bool(active and active.transcript == path),
            "last_question": interviewer[-1] if interviewer else "",
        })
    return items


def _active_info() -> dict | None:
    if not active:
        return None
    return {
        "interview": active.interview,
        "file": active.transcript.name,
        "session": active.session,
        "minutes": active.minutes,
        "elapsed": round(active.elapsed()),
        "paused": active.is_paused(),
    }


LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")


def _markdown(text: str, extensions: list[str]) -> str:
    """Markdown to HTML, with any raw HTML shown as text: reports and transcripts hold what the model wrote and
    what the candidate said or pasted, and "vector<int>" in an answer must not turn into a tag."""
    md = markdown.Markdown(extensions=extensions)
    md.preprocessors.deregister("html_block")
    md.inlinePatterns.deregister("html")
    return md.convert(text)


def _render_markdown(text: str) -> str:
    """Markdown to HTML. Python-Markdown only starts a list after a blank line, but reports often put a
    list right under a bold label ("**Strongest**" then "1. ..."), so add the blank line first."""
    lines: list[str] = []
    for line in text.splitlines():
        if LIST_ITEM.match(line) and lines and lines[-1].strip() and not LIST_ITEM.match(lines[-1]):
            lines.append("")
        lines.append(line)
    return _markdown("\n".join(lines), ["tables", "fenced_code", "sane_lists"])


def _report_page(title: str, body_html: str, back: str = "/") -> HTMLResponse:
    template = (WEB / "report.html").read_text(encoding="utf-8")
    page = template.replace("<!--TITLE-->", html.escape(title)).replace("<!--BACK-->", back).replace("<!--CONTENT-->", body_html)
    return HTMLResponse(page)


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def allowed_hosts() -> set[str]:
    """Hosts the pages may be opened from: this machine, plus the hosts in PIPECAT_ALLOWED_ORIGINS (e.g.
    "http://192.168.1.5:7860" to use the interviewer from another computer)."""
    extra = {urlsplit(o.strip()).hostname for o in os.getenv("PIPECAT_ALLOWED_ORIGINS", "").split(",") if o.strip()}
    return LOCAL_HOSTS | (extra - {None})


def register(app: FastAPI):
    """Adds the pages and their API. Must run before the runner adds its own "/" redirect."""

    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.middleware("http")
    async def local_only(request, call_next):
        # The pages hold resumes and transcripts. Pipecat's runner allows every origin, so without this any
        # website open in the browser could call the API; checking Host as well stops DNS rebinding.
        hosts = allowed_hosts()
        host = urlsplit("//" + request.headers.get("host", "")).hostname
        origin = request.headers.get("origin")
        if host not in hosts or (origin and urlsplit(origin).hostname not in hosts):
            logger.warning(f"Refused a request from host {host!r}, origin {origin!r}; see PIPECAT_ALLOWED_ORIGINS")
            return JSONResponse({"detail": "Only pages opened from this computer may use the interviewer."}, 403)
        return await call_next(request)

    @app.middleware("http")
    async def revalidate_site_files(request, call_next):
        # Make the browser check for updated pages and styles instead of reusing a stale cached copy.
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/") and not path.startswith(("/static/avatars/", "/static/vendor/")) or path in ("/", "/interview", "/progress", "/notepad"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/", include_in_schema=False)
    async def page():
        return FileResponse(WEB / "index.html")

    @app.get("/progress", include_in_schema=False)
    async def progress_page():
        return FileResponse(WEB / "progress.html")

    @app.get("/notepad", include_in_schema=False)
    async def notepad_page():
        return FileResponse(WEB / "notepad.html")

    @app.get("/interview", include_in_schema=False)
    async def interview_page():
        return FileResponse(WEB / "interview.html")

    @app.get("/api/interview-view")
    async def interview_view():
        """Who the video page shows: the interviewer of the next (or running) session and their avatar."""
        folder = selection.interview if selection else None
        if active:
            folder = INTERVIEWS_DIR / active.interview
        if not folder:
            raise HTTPException(404, "還沒有選面試。")
        cfg = InterviewConfig.load(folder)
        v = cfg.variables
        avatar = WEB / "avatars" / f"{Path(cfg.avatar).stem}.glb"
        session = active.session if active else (selection.session() if selection and not selection.resume else {"mode": "full"})
        return {
            "interviewer_name": v.get("interviewer_name", ""),
            "interviewer_title": v.get("interviewer_title", ""),
            "company": v.get("company", ""),
            "round": v.get("round_name", ""),
            "session": session,
            "resuming": bool(selection and selection.resume and not active),
            "avatar_url": f"/static/avatars/{avatar.name}" if avatar.exists() else None,
            "avatar_body": cfg.avatar_body,
            "lipsync_ready": (WEB / "vendor" / "headaudio" / "headaudio.min.mjs").exists(),
        }

    # ----- Interviews and sessions -----

    @app.get("/api/interviews")
    async def interviews():
        result = []
        for name in list_interviews():
            folder = INTERVIEWS_DIR / name
            issues = validate(folder)
            entry = {"name": name, "issues": issues, "company": name, "role": "", "round": "", "duration": 0,
                     "resume_layers": [], "transcripts": [], "drill_topics": []}
            if not any(i["level"] == "error" for i in issues):
                try:
                    cfg = InterviewConfig.load(folder)
                except Exception as e:  # a broken config should not take the whole page down
                    issues.append({"level": "error", "message": f"讀取設定失敗：{e}"})
                else:
                    v = cfg.variables
                    topics = rubric_areas(v.get("rubric", ""))
                    topics += [t for t in drill_suggestions(name) if t not in topics]
                    scored = sessions(name)
                    latest = None
                    if scored:
                        s = scored[-1]
                        latest = {"started": s["started"], "session": s["session"], "verdict": s.get("verdict"),
                                  "areas": s.get("areas", []), "file": s["file"]}
                    entry.update({
                        "company": v.get("company", ""),
                        "role": v.get("role_title", ""),
                        "round": v.get("round_name", ""),
                        "interviewer": f"{v.get('interviewer_name', '')}, {v.get('interviewer_title', '')}".strip(", "),
                        "latest": latest,
                        "scored_sessions": len(scored),
                        "duration": cfg.duration_minutes,
                        "resume_layers": _resume_layers(folder),
                        "transcripts": _transcripts(cfg),
                        "drill_topics": topics,
                        "suggested_topics": drill_suggestions(name),
                        "coding_defaults": cfg.coding,
                    })
            result.append(entry)
        current = None
        if selection:
            current = {
                "interview": interview_name(selection.interview),
                "resume": selection.resume.name if selection.resume else None,
                "mode": selection.mode, "topic": selection.topic, "minutes": selection.minutes,
                "coach": selection.coach, "language": selection.language, "difficulties": selection.difficulties,
                "tags": selection.tags, "rating": selection.rating, "interview_only": selection.interview_only,
                "statement": selection.statement,
            }
        return {"selected": current, "active": _active_info(), "interviews": result}

    @app.get("/api/status")
    async def status():
        return {"active": _active_info(), "generating": sorted(generating)}

    @app.post("/api/selection")
    async def choose(req: SelectionRequest):
        global selection
        if req.interview not in list_interviews():
            raise HTTPException(404, f"找不到面試：{req.interview}")
        folder = INTERVIEWS_DIR / req.interview
        errors = [i["message"] for i in validate(folder) if i["level"] == "error"]
        if errors:
            raise HTTPException(400, "這個面試的設定有問題：" + "；".join(errors))
        resume = _transcript_path(req.interview, req.resume) if req.resume else None
        if req.mode == "drill" and not resume:
            if not (req.topic or "").strip():
                raise HTTPException(400, "專項練習需要選一個主題。")
            if not req.minutes or not 3 <= req.minutes <= 120:
                raise HTTPException(400, "練習時間要在 3 到 120 分鐘之間。")
        mode = req.mode if req.mode in ("full", "drill", "coding") else "full"
        new = Selection(folder, resume, mode, (req.topic or "").strip() or None, req.minutes,
                        req.coach and mode == "drill", req.language)
        if mode == "coding" and not resume:
            if req.language not in coding.LANGUAGES:
                raise HTTPException(400, f"程式語言只能是：{', '.join(coding.LANGUAGES.values())}")
            if not req.minutes or not 15 <= req.minutes <= 120:
                raise HTTPException(400, "Coding 面試時間要在 15 到 120 分鐘之間。")
            if req.statement not in coding.STATEMENT_STYLES:
                raise HTTPException(400, "題目呈現方式只能是面試風格或 LeetCode 原題。")
            new.statement = req.statement
            new.difficulties, new.tags, new.rating, new.interview_only = _check_coding_filters(req)
            # Picked here, so a network problem or an empty filter shows up on this page, not mid-interview.
            try:
                new.problems = await asyncio.to_thread(coding.pick_problems, req.interview, new.difficulties,
                                                       new.tags, new.rating, new.interview_only)
            except leetcode.LeetCodeError as e:
                raise HTTPException(400, str(e))
            if new.statement == "interview":
                await coding.prepare_statements(new.problems)
        selection = new
        return {"ok": True, "problems": selection.problems}

    @app.post("/api/session/end")
    async def end_session():
        if not active:
            raise HTTPException(409, "目前沒有進行中的面試。")
        await active.end()
        return {"ok": True}

    @app.post("/api/session/pause")
    async def pause_session():
        if not active:
            raise HTTPException(409, "目前沒有進行中的面試。")
        await active.pause()
        return {"ok": True, "paused": active.is_paused()}

    @app.post("/api/session/resume")
    async def resume_session():
        if not active:
            raise HTTPException(409, "目前沒有進行中的面試。")
        await active.resume()
        return {"ok": True, "paused": active.is_paused()}

    @app.post("/api/notepad")
    async def notepad(req: NotepadRequest):
        if not active:
            raise HTTPException(409, "目前沒有進行中的面試，筆記會在面試開始後才傳給面試官。")
        active.update_notepad(req.text[:20000], req.problem)
        return {"ok": True}

    @app.get("/api/coding")
    async def coding_problem():
        """The coding problem on the candidate's screen, or {"active": false} outside a coding interview."""
        if not active or not active.coding:
            return {"active": False}
        # The page keeps each problem's code per session, keyed by the transcript file.
        return {"active": True, **active.coding(), "file": active.transcript.name}

    @app.get("/api/coding/options")
    async def coding_options():
        """Languages, difficulties, LeetCode's tags and the rating range, for the setup page. The first call
        fetches the problem list from LeetCode (a few seconds); later ones read the cache."""
        try:
            tags, rated = await asyncio.to_thread(lambda: (leetcode.tags(), leetcode.ratings_or_empty()))
        except leetcode.LeetCodeError as e:
            raise HTTPException(502, str(e))
        values = sorted(rated.values())
        return {
            "languages": coding.LANGUAGES,
            "difficulties": list(coding.DIFFICULTIES),
            "tags": tags,
            "rating": {"min": values[0], "max": values[-1], "count": len(values)} if values else None,
        }

    @app.post("/api/coding/match")
    async def coding_match(f: CodingFilters):
        """How many problems the filters leave, with a few examples."""
        try:
            found = await asyncio.to_thread(leetcode.matching, *_check_coding_filters(f))
        except leetcode.LeetCodeError as e:
            raise HTTPException(502, str(e))
        sample = random.sample(found, min(4, len(found)))
        return {"count": len(found), "sample": [{"title": p["title"], "difficulty": p["difficulty"],
                                                 "rating": p["rating"]} for p in sample]}

    # ----- Reports and progress -----

    @app.post("/api/feedback")
    async def request_feedback(ref: TranscriptRef):
        path = _transcript_path(ref.interview, ref.file)
        if active and active.transcript == path:
            raise HTTPException(409, "這場面試還在進行中，結束後會自動產生報告。")
        task = asyncio.create_task(generate_report(INTERVIEWS_DIR / ref.interview, path))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return {"ok": True}

    @app.get("/report", include_in_schema=False)
    async def report(interview: str, file: str, kind: str = "feedback"):
        path = _transcript_path(interview, file)
        title = f"{interview} · {_started(path)}"
        if kind == "transcript":
            saved = read_transcript(path)
            body = "\n\n".join(saved.lines)
            return _report_page(f"逐字稿 · {title}", _markdown(body, ["fenced_code"]))
        if kind == "stt":
            compare = sibling(path, "stt-compare")
            if not compare.exists():
                raise HTTPException(404, "這場還沒有語音辨識比較，請先執行 compare_stt.py。")
            return _report_page(f"語音辨識比較 · {title}", _render_markdown(compare.read_text(encoding="utf-8")))
        report_path = sibling(path, "feedback")
        if not report_path.exists():
            raise HTTPException(404, "這場還沒有回饋報告。")
        body = _render_markdown(report_path.read_text(encoding="utf-8"))
        return _report_page(f"回饋報告 · {title}", body)

    @app.get("/api/progress")
    async def progress(interview: str, kind: str = "interview"):
        """kind: "interview" for full interviews and drills, "coding" for coding interviews, which use their own rubric."""
        if interview not in list_interviews():
            raise HTTPException(404, f"找不到面試：{interview}")
        cfg = InterviewConfig.load(INTERVIEWS_DIR / interview)
        want_coding = kind == "coding"
        scored = sessions(interview)
        return {
            "interview": interview,
            "kind": "coding" if want_coding else "interview",
            "company": cfg.variables.get("company", ""),
            "round": cfg.variables.get("round_name", ""),
            "areas": rubric_areas(coding.rubric(cfg) if want_coding else cfg.variables.get("rubric", "")),
            "sessions": [s for s in scored if coding.is_coding(s["session"]) == want_coding],
            "coding_sessions": sum(1 for s in scored if coding.is_coding(s["session"])),
        }

    # ----- Resume -----

    @app.get("/api/resume")
    async def get_resume(target: str = "profile"):
        try:
            path = resume_import.resume_path(target)
        except resume_import.ResumeImportError as e:
            raise HTTPException(404, str(e))
        return {"text": path.read_text(encoding="utf-8") if path.exists() else ""}

    @app.post("/api/resume/convert")
    async def convert_resume(file: UploadFile = File(...)):
        data = await file.read()
        try:
            text = await resume_import.convert(file.filename or "", data)
        except resume_import.ResumeImportError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            logger.exception("Resume conversion failed")
            raise HTTPException(500, f"轉換失敗：{e}")
        return {"text": text}

    @app.post("/api/resume")
    async def save_resume(req: ResumeSaveRequest):
        if not req.text.strip():
            raise HTTPException(400, "履歷內容是空的。")
        try:
            path = resume_import.save(req.target, req.text)
        except resume_import.ResumeImportError as e:
            raise HTTPException(404, str(e))
        logger.info(f"Resume saved to {path}")
        return {"ok": True}

    # ----- Editing a round's files -----

    @app.get("/api/round-files")
    async def get_round_files(interview: str):
        if interview not in list_interviews():
            raise HTTPException(404, f"找不到面試：{interview}")
        return {"files": setup_wizard.round_files(INTERVIEWS_DIR / interview)}

    @app.post("/api/round-files")
    async def save_round_file(req: RoundFileRequest):
        if req.interview not in list_interviews():
            raise HTTPException(404, f"找不到面試：{req.interview}")
        try:
            issues = setup_wizard.save_round_file(INTERVIEWS_DIR / req.interview, req.name, req.text)
        except setup_wizard.SetupError as e:
            raise HTTPException(400, str(e))
        logger.info(f"Saved {req.name} of {req.interview}")
        return {"ok": True, "issues": issues}

    # ----- New company or round -----

    @app.get("/api/companies")
    async def companies():
        return {"companies": setup_wizard.companies()}

    @app.post("/api/setup/draft")
    async def setup_draft(fields: dict):
        try:
            return await setup_wizard.draft(fields)
        except setup_wizard.SetupError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            logger.exception("Setup draft failed")
            raise HTTPException(500, f"產生草稿失敗：{e}")

    @app.post("/api/setup/create")
    async def setup_create(fields: dict):
        try:
            name = setup_wizard.create(fields)
        except setup_wizard.SetupError as e:
            raise HTTPException(400, str(e))
        logger.info(f"Created interview {name}")
        return {"ok": True, "interview": name}
