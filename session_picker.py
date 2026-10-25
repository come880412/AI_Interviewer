"""The setup website at http://localhost:7860/, served next to Pipecat's /client page.

- Choose the interview, full interview or focused drill, or a transcript to resume; the choice applies
  to the next connection at /client.
- See the session in progress, end it, and share a notepad with the interviewer (/notepad).
- Read reports and transcripts (/report), generate a missing report, and follow progress (/progress).
- Import a resume, and create a new company or round with Claude's drafts.
"""

import asyncio
import html
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import markdown
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

import resume_import
import setup_wizard
from feedback import generate_feedback
from history import drill_suggestions, sessions
from interview_config import (
    INTERVIEWS_DIR,
    ROOT,
    InterviewConfig,
    interview_name,
    list_interviews,
    resume_layers,
    rubric_areas,
    validate,
)
from transcript import TRANSCRIPTS_DIR, read_transcript, sibling

WEB = ROOT / "web"


@dataclass
class Selection:
    interview: Path
    resume: Path | None = None  # transcript to continue; None starts a new session
    mode: str = "full"  # "full" interview or a focused "drill"
    topic: str | None = None  # drill topic
    minutes: int | None = None  # drill length

    def session(self) -> dict:
        if self.mode == "drill":
            return {"mode": "drill", "topic": self.topic, "minutes": self.minutes}
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
    update_notepad: Callable[[str], None]


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


class ResumeSaveRequest(BaseModel):
    target: str  # "profile", "company:<company>" or "interview:<company>/<round>"
    text: str


class TranscriptRef(BaseModel):
    interview: str
    file: str


class NotepadRequest(BaseModel):
    text: str


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
    for path in sorted((TRANSCRIPTS_DIR / cfg.name).glob("*-transcript.md"), reverse=True):
        saved = read_transcript(path)
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


def _render_markdown(text: str) -> str:
    """Markdown to HTML. Python-Markdown only starts a list after a blank line, but reports often put a
    list right under a bold label ("**Strongest**" then "1. ..."), so add the blank line first."""
    lines: list[str] = []
    for line in text.splitlines():
        if LIST_ITEM.match(line) and lines and lines[-1].strip() and not LIST_ITEM.match(lines[-1]):
            lines.append("")
        lines.append(line)
    return markdown.markdown("\n".join(lines), extensions=["tables", "fenced_code", "sane_lists"])


def _report_page(title: str, body_html: str, back: str = "/") -> HTMLResponse:
    template = (WEB / "report.html").read_text(encoding="utf-8")
    page = template.replace("<!--TITLE-->", html.escape(title)).replace("<!--BACK-->", back).replace("<!--CONTENT-->", body_html)
    return HTMLResponse(page)


def register(app: FastAPI):
    """Adds the pages and their API. Must run before the runner adds its own "/" redirect."""

    app.mount("/static", StaticFiles(directory=WEB), name="static")

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
                    })
            result.append(entry)
        current = None
        if selection:
            current = {
                "interview": interview_name(selection.interview),
                "resume": selection.resume.name if selection.resume else None,
                "mode": selection.mode, "topic": selection.topic, "minutes": selection.minutes,
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
        selection = Selection(folder, resume, req.mode if req.mode in ("full", "drill") else "full",
                              (req.topic or "").strip() or None, req.minutes)
        return {"ok": True}

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
        active.update_notepad(req.text[:20000])
        return {"ok": True}

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
            return _report_page(f"逐字稿 · {title}", markdown.markdown(body, extensions=["fenced_code"]))
        report_path = sibling(path, "feedback")
        if not report_path.exists():
            raise HTTPException(404, "這場還沒有回饋報告。")
        body = _render_markdown(report_path.read_text(encoding="utf-8"))
        return _report_page(f"回饋報告 · {title}", body)

    @app.get("/api/progress")
    async def progress(interview: str):
        if interview not in list_interviews():
            raise HTTPException(404, f"找不到面試：{interview}")
        cfg = InterviewConfig.load(INTERVIEWS_DIR / interview)
        return {
            "interview": interview,
            "company": cfg.variables.get("company", ""),
            "round": cfg.variables.get("round_name", ""),
            "areas": rubric_areas(cfg.variables.get("rubric", "")),
            "sessions": sessions(interview),
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
