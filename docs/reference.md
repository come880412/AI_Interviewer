# Reference

**English** · [繁體中文](reference.zh-TW.md) · [← Back to README](../README.md)

For installation and your first interview, see [Installation and your first interview](../INSTALL.md).

The web UI is in Chinese. This page gives each UI label in Chinese with its English meaning in parentheses the first time it appears.

- [Architecture](#architecture)
- [Preparing an interview](#preparing-an-interview)
  - [Updating your resume](#updating-your-resume)
- [Feedback reports and practice progress](#feedback-reports-and-practice-progress)
- [Continuing after a disconnect](#continuing-after-a-disconnect)
- [Settings](#settings)
- [Development](#development)
- [Project structure](#project-structure)
- [Known limitations](#known-limitations)

## Architecture

A fully local, self-hosted voice interviewer. You talk to it in the browser. It asks follow-up questions in real time based on the JD and your answers. When the interview ends, it writes a feedback report. It also remembers your weak spots and tests them again on purpose in the next session.

```
Browser (mic/speakers)        http://localhost:7860/           Setup page: pick an interview, focused practice, continue, reports, progress, resume, add a round
   ⇅ WebRTC                   http://localhost:7860/interview  Interview page: virtual interviewer, live captions
bot.py (Pipecat 1.12.0)
   ├─ Silero VAD + Smart Turn v3    local; decides whether you have finished talking, handles interruptions
   ├─ Whisper large-v3 or Parakeet  local GPU; speech to text
   ├─ Claude Opus 5.5               the interviewer's brain; by default through the Claude Code CLI (no API key needed)
   ├─ Kokoro or Pocket TTS          text to speech: Kokoro built-in voices (GPU), or Pocket TTS voice cloning (CPU)
   └─ transcripts/                  transcripts, feedback reports, scores
```

Everything except Claude runs on your own computer.

## Preparing an interview

The repo includes a fictional example, [`interviews/example/`](../interviews/example/) (a technical interview for a computer vision engineer at Acme Vision). You can run it right after cloning, or follow its format to write your own. Company folders you create stay on your machine. `.gitignore` only tracks `_template/` and `example/`.

Each company has one folder, with one subfolder for each round:

```
interviews/
  acme/
    company.yaml        company, role, Whisper prompt, feedback report language
    jd.md               job description (shared by all rounds)
    company_info.md     company facts the interviewer can use when you ask it questions (confirmed facts only)
    resume.md           a resume for this company only (optional)
    tech/               one folder per round
      config.yaml       interviewer name and title, round, duration, difficulty, voice
      round_info.md     what this round evaluates, its format, the interviewer's style
      question_bank.md  questions this round may ask
      rubric.md         scoring rubric: each ## heading is one dimension, describing what a 5, 3 and 1 look like
      voice/            reference audio for voice cloning (optional)
```

**Create it in the web UI (recommended):** on the right of the setup page, open the 「新增公司或關卡」 (Add company or round) tab. Paste the JD and what you know about this round (notes from HR, the interviewer's background), then press 「產生草稿」 (Generate draft). Claude drafts round_info, the question bank, the rubric, the company info and the Whisper prompt from the JD and your resume. Review and edit them, then press 「建立」 (Create). If you pick an existing company, only a new round is added, and it reuses the company's JD and settings.

**Create it by hand:** copy the [template](../interviews/_template/), then rename `round1` to the round name:

```bash
cp -r interviews/_template interviews/acme
mv interviews/acme/round1 interviews/acme/tech
```

**File lookup order:** the round folder first, then the company folder. For the resume, `profile/resume.md` is the last fallback. Any file in the round folder overrides the company's version. `stt_hotwords` from both levels are merged.

**Config check:** the setup page lists problems for each session. Errors (for example, a missing interviewer name, a YAML typo, or a duration that is not a number) must be fixed before you can start. Warnings (for example, no rubric.md) do not block the start, but the report will be less accurate. `bot.py` also prints them in the terminal at startup.

Folders whose names start with `_` (for example `_template`) do not appear in the menu. To set the interview that the web page selects by default, use `python bot.py --interview acme/tech` or `INTERVIEW=acme/tech` in `.env`. If a company has only one round, the company name is enough.

`stt_hotwords` is worth the time to fill in. List the technical terms, product names and acronyms from the JD, and Whisper will hear them correctly more often. Only include words that are really easy to mishear. The longer the list, the more likely Whisper is to read the list itself out loud when the audio is unclear. (The code filters out segments where three words in a row appear in the same order as in the list.)

### Updating your resume

On the right of the setup page, open the 「履歷」 (Resume) tab and press 「上傳新履歷」 (Upload new resume). Pick a PDF, Word (.docx), .txt or .md file. The app extracts the text, then asks Claude to put it into the `resume.md` format. Claude does not change any content. It only fixes line breaks and section order, and removes contact details. This takes about 30 seconds to a minute. After you review or edit the result, choose where to save it: all rounds of this company (the default when uploading), only this round, or shared by all companies (`profile/resume.md`). The old version is backed up to `profile/backups/`. You can also press 「編輯目前履歷」 (Edit current resume) to edit it directly. A PDF that is a scanned image has no readable text, so upload a Word or text file instead. A .md file is used as is.

## Feedback reports and practice progress

After each session, `transcripts/<company>/<round>/` has three files:

| File | Content |
|---|---|
| `*-transcript.md` | The transcript, with the start time and length of each turn |
| `*-feedback.md` | The feedback report: scores against the rubric, strongest and weakest moments, **a question-by-question review with English reference answers**, follow-up questions to prepare for, delivery analysis (answer length, pause before speaking, speaking rate), and an overall verdict |
| `*-scores.json` | Structured scores: score per dimension, weak spots, questions asked, topics suggested for next time |

- **Learning loop:** at the start of the next session, the interviewer reads the weak spots and asked questions from earlier sessions. It tests the weak spots again with different wording and avoids repeating questions. It does not mention your earlier practice to you.
- **Practice progress:** 「練習進度」 (Practice progress) at the top of the setup page shows how each dimension's score changes across sessions, plus each session's verdict and suggested topics.
- **Generate a missing report:** for a transcript without a report (for example, the connection dropped and you do not want to continue), press 「產生報告」 (Generate report) on its row in 「練習紀錄」 (Practice history) on the setup page. You can also use the command line (this also regenerates an existing report):

```bash
python feedback.py transcripts/example/tech/20261101-1930-transcript.md
python feedback.py --scores-only transcripts/example/tech/*-transcript.md   # fill in scores from old reports without rewriting the reports
```

## Continuing after a disconnect

If the network drops, you close the page by accident, or you want a break, you can pick up the same session later:

- **`bot.py` is still running:** if the connection dropped before half the time was up, press 「開始面試」 (Start interview) again on the interview page and the session continues. To continue a different transcript, go back to the setup page and pick it.
- **`bot.py` has stopped:** run `python bot.py` again and pick the transcript to continue on the setup page, or run `python bot.py --resume transcripts/example/tech/20261101-1930-transcript.md` directly.

After you reconnect, the interviewer briefly welcomes you back. It does not introduce itself again, and it continues from where you stopped. If you had not finished the last question, it asks it again. The timer continues from where it was, and the transcript is written back to the same file.

How the session ends decides whether a report is generated. If the interviewer says goodbye, or you press 「結束並產生報告」 (End and generate report), a report is always generated. If the connection just drops, a report is generated only after more than half the time has passed. Before that, it counts as a disconnect, and the next 「開始面試」 (Start interview) continues the session automatically.

## Settings

**Voice:** change `voice` in `config.yaml`. American male voices: `am_michael`, `am_adam`, `am_eric`, `am_liam`, `am_onyx`, `am_fenrir`, `am_puck`, `am_echo`. British male voices: `bm_george`, `bm_lewis`, `bm_daniel`, `bm_fable`. For a British voice, also set `voice_language` to `en-gb`.

**Whose Claude to use:** `LLM_BACKEND=claude_code` in `.env` (the default) uses your Claude Code login and needs no API key. It looks for `claude` on PATH, or the copy bundled with the VS Code extension. If neither is found, set `CLAUDE_CODE_PATH`. The first word of each turn takes about 2–3 seconds. If the CLI crashes during the interview or does not respond for more than 60 seconds, the interviewer first says "Sorry, give me just a second" (in Chinese interviews, 「不好意思，請稍等一下」). It then restarts the CLI, passes in the conversation so far, and tries again. Set `LLM_BACKEND=api` to use `ANTHROPIC_API_KEY` instead.

**Pocket TTS (built-in voices or voice cloning):** before the first use, accept the terms at https://huggingface.co/kyutai/pocket-tts, run `uvx hf auth login`, and install pocket-tts as shown in the comment at the end of `requirements.txt`. Pocket TTS runs on the CPU and adds about 10 seconds of loading at the start of each session.

- **Built-in voices:** set `pocket_voice: stuart_bell` in `config.yaml`. English male voices: `stuart_bell`, `javert`, `michael`, `paul`, `charles`, `george`, `jean`, `marius`, `peter_yearsley`, `bill_boerst`. Female voices: `alba`, `anna`, `vera`, `fantine`, `eponine`, `azelma`, `mary`, `jane`, `eve`, `caro_davy`, `cosette`. In testing, `stuart_bell` and `javert` were the clearest.
- **Voice cloning:** only use a voice whose owner has agreed to it. Prepare a 10–20 second `.wav` with one person speaking and no background music. Put it in the round folder's `voice/`, and set `voice_clone: voice/xxx.wav` in `config.yaml` (this takes priority over `pocket_voice`). **The recording quality is cloned too.** Phone calls, video calls and compressed video audio have a narrow bandwidth, so the cloned voice sounds muffled. Use an original, wideband recording (16 kHz or higher).

**Chinese interviews:** add `interview_language: zh-TW` to the round's `config.yaml` (or to `company.yaml` to apply it to the whole company). Or choose Chinese as the interview language in the 「新增公司或關卡」 wizard. In a Chinese interview:

- The interviewer asks questions in Traditional Chinese with Taiwanese wording, and keeps technical terms in English (for example, 「你為什麼把 GRU 換成 MLP？」, "Why did you replace the GRU with an MLP?").
- Speech recognition always uses Whisper (Parakeet does not support Chinese). The recognized text is converted to Traditional Chinese and Taiwanese wording, for example 「項目」 becomes 「專案」 (both mean "project").
- The voice switches to the Kokoro v1.1-zh Chinese model, with `voice: zm_010` as the default. Male voices are `zm_*` and female voices are `zf_*`, with dozens of each to try. Pocket TTS does not speak Chinese, so `voice_clone` and `pocket_voice` are ignored. The model (about 380 MB) downloads automatically on first use, or you can run `python download_models.py chinese` beforehand.
- Captions appear character by character. The feedback report and reference answers are in Chinese. Speaking rate is measured in characters per minute (each Chinese character or English word counts as one).

The Chinese voices have a mainland China accent and pronounce English terms only passably. This is a limit of the current lightweight local models.

**The interviewer cuts in too early:** `CANDIDATE_PAUSE_SECS` in `.env` (default 0.8) is how long you must pause before the system starts deciding whether you have finished talking. If you still get interrupted, raise it. If responses feel slow, lower it.

**Speech recognition model:** `STT_BACKEND` in `.env` has two options. Both run on the local GPU:

| | `whisper` (default) | `parakeet` |
|---|---|---|
| Model | Whisper large-v3 (faster-whisper) | NVIDIA Parakeet TDT 0.6B v3 (onnx-asr) |
| Speed | about 0.5 seconds per segment | about 0.07 seconds per segment |
| Technical terms | can be hinted with `stt_hotwords` | no hinting; spelling is corrected after recognition using `stt_hotwords` (for example tensor RT → TensorRT) |
| Transcript | each pause-separated segment is recognized on its own | after each answer ends, the whole answer is recognized again in one pass, with full context |

Parakeet scores better than Whisper large-v3 on the Open ASR Leaderboard. But the leaderboard mostly tests native speakers' English. If you have an accent, test which one is more accurate with your own voice:

1. Set `SAVE_CANDIDATE_AUDIO=true` in `.env` and do a normal interview. The audio of each answer is saved in a `*-audio/` folder next to the transcript (local only, never committed to git).
2. Run `python compare_stt.py transcripts/<company>/<round>/<time>-transcript.md`. It sends each answer to both Whisper and Parakeet and writes `*-stt-compare.md`, which lists the two models' results side by side with the live recognition from the interview. You can also open `/report?interview=<company>/<round>&file=<time>-transcript.md&kind=stt` in the address bar to view it.
3. Pick the one closer to what you actually said and set it as `STT_BACKEND`. Before using Parakeet for the first time, run `python download_models.py parakeet` (about 2.5 GB).

Whisper details: `whisper_stt.py` uses the interviewer's latest question and what you said earlier as a prompt. Segments with low confidence, segments that read out the hotwords list, and segments that copy the prompt are dropped, and the terminal prints `Dropped Whisper segment`. If things you really said are dropped, lower `WHISPER_MIN_AVG_LOGPROB` in `.env` (for example to `-1.3`). If Whisper is too slow, change `WHISPER_MODEL` to `deepdml/faster-whisper-large-v3-turbo-ct2`.

**Difficulty:** `difficulty: tough` makes the interviewer challenge your reasoning more often and push you for numbers.

**Follow-up depth vs. speed:** set `INTERVIEWER_THINKING=adaptive` in `.env` (only works with `LLM_BACKEND=api`). Claude thinks before it responds, so follow-up questions are sharper, but each turn takes a few seconds longer.

**Latency is still too high:** change `LLM_MODEL` to `claude-sonnet-5-5` to use a faster model for the live conversation. Keep `FEEDBACK_MODEL` at `claude-opus-5-5`. It handles feedback reports, resume conversion and drafts for new rounds.

## Development

```bash
python -m pytest             # automated tests; no GPU, network or Claude needed
```

The project is managed with git. `transcripts/`, `profile/`, and the `resume.md` and `voice/` in each company folder are personal data. They are listed in `.gitignore` and are never committed.

## Project structure

```
bot.py                main voice pipeline: timing, ending flow, focused practice, notepad
whisper_stt.py        Whisper speech recognition: conversation context, hallucination filtering, conversion to Traditional Chinese
chinese.py            text handling for Chinese interviews: Traditional/Simplified conversion, spacing and punctuation, character counts
chinese_tts.py        the Chinese interviewer's voice (Kokoro v1.1-zh)
parakeet_stt.py       Parakeet speech recognition: re-recognizes each whole answer after it ends
stt_common.py         shared by both recognizers: answer audio, technical term correction, Parakeet model download
compare_stt.py        compares speech recognition models on your own recordings
claude_code_llm.py    calls the interviewer through the Claude Code CLI, recovers automatically if the CLI crashes
feedback.py           feedback reports and scores (runs automatically when an interview ends, or by hand)
analysis.py           computes answer length, pauses and speaking rate from turn timings
history.py            weak spots, asked questions and progress data across sessions
interview_config.py   loads interview folders, checks the config, fills in prompt templates
transcript.py         writes and reads back transcripts
session_picker.py     the setup website and its API
setup_wizard.py       adding a company or round: drafting and creating
resume_import.py      converts an uploaded resume file into resume.md
llm.py                one-off Claude calls shared by feedback reports, resume conversion and drafts
web/                  setup page, interview page (virtual interviewer), report page, progress page, notepad
download_models.py    downloads models, checks the GPU
prompts/              prompt templates for the interviewer, feedback reports, resume conversion and new rounds
profile/resume.md     general resume, used when the company or round has no version of its own
interviews/           one folder per company, one subfolder per round; _template/ is the template
transcripts/          transcripts, feedback reports and scores, in one folder per interview
tests/                automated tests
```

## Known limitations

- The full live voice conversation (including automatic hang-up, sending the notepad to the interviewer, and recovery after a CLI crash) needs a microphone and a browser, so it can only be verified by hand on your own machine. Each component and the website API are tested.
- Turn timings are approximate. The end time of an answer includes about one second spent deciding whether you have finished talking. Whisper filters out some "uh" and "um", so filler word counts from the transcript are only rough.
- For voice cloning (Pocket TTS), only use voices you have the right to use and whose owners have agreed.
