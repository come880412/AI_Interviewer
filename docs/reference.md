# Reference

**English** · [繁體中文](reference.zh-TW.md) · [← Back to README](../README.md)

For installation and your first interview, see [Installation and your first interview](../INSTALL.md).

The web UI is in Chinese. This page gives each UI label in Chinese with its English meaning in parentheses the first time it appears.

- [Architecture](#architecture)
- [Preparing an interview](#preparing-an-interview)
  - [Updating your resume](#updating-your-resume)
- [Coding interviews](#coding-interviews)
  - [Where the problems come from](#where-the-problems-come-from)
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

**Create it in the web UI (recommended):** on the right of the setup page, open the 「新增公司或關卡」 (Add company or round) tab. Paste the JD and what you know about this round (notes from HR, the interviewer's background), then pick the interviewer's voice and avatar and press 「產生草稿」 (Generate draft). Claude drafts round_info, the question bank, the rubric, the company info and the Whisper prompt from the JD and your resume. Review and edit them, then press 「建立」 (Create). If you pick an existing company, only a new round is added, and it reuses the company's JD and settings.

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

### Customizing a round

Everything about a round can be changed after it is created, without touching the code.

- **In the web UI:** the 「編輯這一關」 (Edit this round) tab on the setup page edits the selected round's files: its settings (`config.yaml`), round_info, question bank, rubric, JD, company info and company settings, plus the three prompts below. Saving checks the file (a YAML typo or a broken prompt is refused), keeps the old version in `profile/backups/`, and shows the round's remaining setup problems. Changes apply from the next session.
- **Voice and avatar:** the wizard offers several voices for the interview language and two avatars, `david` (male look) and `brunette` (female look). In `config.yaml`, `voice` takes any Kokoro voice that speaks the language, and `avatar` any GLB in `web/avatars/` with ARKit and Oculus viseme blend shapes (set `avatar_body: M` or `F` to match).
- **Coding defaults:** a round's `config.yaml` can preset the coding filters that the setup page shows for it. Every key is optional, and you can still change them on the page:

  ```yaml
  coding:
    language: cpp            # python or cpp
    difficulties: [medium, hard]
    tags: [graph, tree]      # LeetCode tag slugs
    minutes: 45              # 15, 30, 45 or 60
    rating: [1600, 2000]     # [low, high]; null for no bound
    statement: interview     # interview or leetcode
    interview_only: true
  ```

- **Replacing a prompt:** to change how the interviewer behaves, how the report is written, or how coding sessions are scored for one round (or a whole company), put a file with the same name in a `prompts/` folder there: `interviews/acme/tech/prompts/interviewer.md`, `feedback.md` or `coding_rubric.md` (in the company folder, `interviews/acme/prompts/`, it applies to every round). Start from a copy of the shared file in [`prompts/`](../prompts/), or from the editor tab, which shows the shared version. A custom `interviewer.md` must keep `{{session_mode}}` and the `[[END]]` instructions, which the app relies on for practice modes and hanging up; the config check refuses one without them. For most changes, describing what you want in `round_info.md` is enough.

## Coding interviews

On the start page, choose **Coding** under 練習方式 (practice mode), then set:

- **Language and length**: Python or C++; 15, 30, 45 or 60 minutes. 15 minutes is one problem with no time for your questions at the end; the second problem needs at least 15 minutes left, so it only comes up in longer sessions.
- **題目呈現 (how the problem is shown)**:
  - **面試風格 (interview style)**, the default, works like a real interview. The notepad shows a short paragraph that says exactly what to solve, with one or two examples, the way an interviewer writes a problem in a shared document. Constraints, input sizes, guarantees ("exactly one answer exists"), edge-case rules and follow-ups are left out, and so are the tags, rating and LeetCode link, since tags give the technique away. Ask about what matters, or state an assumption and have the interviewer confirm it. The interviewer has LeetCode's full statement and a list of what was left out, answers truthfully only what you ask, and does not volunteer anything. If you skip something that matters, it comes back in testing as a specific input. Claude writes this version once per problem (about ten seconds, the first time a problem is used); if that fails, LeetCode's description and first two examples are shown without the constraints.
  - **LeetCode 原題 (LeetCode statement)** shows the full statement with constraints, as before.
- **難度 (difficulty)**: any combination of Easy, Medium and Hard, for example Medium and Hard only.
- **只出面試常見題 (interview problems only)**, on by default: algorithm and data-structure problems people rate well. It leaves out problems under 75% likes (Divisor Game, String to Integer), puzzle and contest-only topics (brainteasers, games, number theory, combinatorics, probability, geometry, network flow, suffix structures and the like), and problems tagged only Array, String, Math, Simulation, Enumeration, Counting or Matrix, which are mostly "do what the statement says"; very popular classics such as Rotate Image and Spiral Matrix stay in. The rules are in `interviewer/leetcode.py` (`interview_style`). Untick it to draw from every free problem.
- **Rating** (optional): the problem's difficulty score from [zerotrac/leetcode_problem_rating](https://github.com/zerotrac/leetcode_problem_rating), roughly 1100 to 3100. Only weekly and biweekly contest problems have a rating, so a range limits the pick to those; you can give just a lower or just an upper bound.
- **題型 (tags)**: LeetCode tags such as Graph, Tree or Linked List. Pick several; a problem with any of them counts. None means any tag. The 36 most common are listed; 顯示全部 (show all) or the search box finds the rest.

The panel shows how many problems match, with a few examples. 前往面試 (go to the interview) picks two of them (the first problem and a backup); if nothing matches or LeetCode cannot be reached, the error appears right there. A coding interview uses the selected round's interviewer and voice, but not the resume or question bank: it is algorithm problems only.

1. After 前往面試 (go to the interview), click 打開題目與程式區 (open the problem and code area) on the interview page, put it next to the interview page, then click 開始面試 (start).
2. The first problem appears on the left (the short version in interview style; LeetCode's own statement with a link to it in LeetCode style), and the code area on the right starts with LeetCode's code template. Tab indents four spaces and Enter keeps the indentation.
3. Think out loud as you write. Your code syncs 2.5 seconds after you stop typing, and the interviewer reads the latest version the next time you speak.
4. The code cannot be run, so walk through examples by hand. The interviewer goes from clarifying questions to approach and complexity, coding, testing and a follow-up, and gives one hint at a time when you are stuck.
5. When the first problem is done with at least 15 minutes left, it moves on to a second one and the code area switches. Each problem keeps its own code.

The report uses a coding rubric ([prompts/coding_rubric.md](../prompts/coding_rubric.md)): clarifying the problem, problem solving, coding, communication, testing and debugging, and complexity analysis. For each problem it compares your approach with the optimal one, points out bugs in your code, and gives a reference solution and how you could have explained it. In interview style it also lists the clarifying questions you asked and the important ones you missed. Coding scores stay out of the interview progress charts; on the progress page, click 看 Coding 面試的進度 (coding progress).

### Where the problems come from

Problems are fetched from LeetCode as needed; there is no problem bank to maintain. Only free algorithm problems are used, and problems without a Python or C++ template are skipped. Problems you have done for this round come last, and the second problem has different tags from the first when possible. Most LeetCode problems have no public solution, so the interviewer (Claude) prepares the hint ladder, the optimal solution and the follow-ups itself, using LeetCode's hints too when a problem has them.

Everything fetched is cached in `~/.cache/ai-interviewer/leetcode/` (set `LEETCODE_CACHE_DIR` to move it): the problem list and ratings are refreshed every 7 days, and problems that were used are kept, along with their interview-style versions (`statements/`), so continuing an interrupted session or regenerating its report works offline. Without a network connection the old list is used. The content is for your own practice, and LeetCode's terms apply to it.

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
python -m interviewer.feedback transcripts/example/tech/20261101-1930-transcript.md
python -m interviewer.feedback --scores-only transcripts/example/tech/*-transcript.md   # fill in scores from old reports without rewriting the reports
```

## Continuing after a disconnect

If the network drops, you close the page by accident, or you want a break, you can pick up the same session later:

- **`bot.py` is still running:** if the connection dropped before half the time was up, press 「開始面試」 (Start interview) again on the interview page and the session continues. To continue a different transcript, go back to the setup page and pick it.
- **`bot.py` has stopped:** run `python bot.py` again and pick the transcript to continue on the setup page, or run `python bot.py --resume transcripts/example/tech/20261101-1930-transcript.md` directly.

After you reconnect, the interviewer briefly welcomes you back. It does not introduce itself again, and it continues from where you stopped. If you had not finished the last question, it asks it again. The timer continues from where it was, and the transcript is written back to the same file.

How the session ends decides whether a report is generated. If the interviewer says goodbye, or you press 「結束並產生報告」 (End and generate report), a report is always generated. If the connection just drops, a report is generated only after more than half the time has passed. Before that, it counts as a disconnect, and the next 「開始面試」 (Start interview) continues the session automatically.

## Settings

**Voice:** change `voice` in `config.yaml`. American male voices: `am_michael`, `am_adam`, `am_eric`, `am_liam`, `am_onyx`, `am_fenrir`, `am_puck`, `am_echo`. British male voices: `bm_george`, `bm_lewis`, `bm_daniel`, `bm_fable`. For a British voice, also set `voice_language` to `en-gb`.

**Whose Claude to use:** `LLM_BACKEND=claude_code` in `.env` (the default) uses your Claude Code login and needs no API key. It looks for `claude` on PATH, or the copy bundled with the VS Code extension. If neither is found, set `CLAUDE_CODE_PATH`. The first word of each turn takes about 2–3 seconds. If the CLI crashes during the interview or does not respond for more than 60 seconds, the interviewer first says "Sorry, give me just a second" (in Chinese interviews, 「不好意思，請稍等一下」). It then restarts the CLI, passes in the conversation so far, and tries again. `bot.py` checks at startup that the CLI answers and stops with the reason if it doesn't. This backend ignores any `ANTHROPIC_API_KEY` in `.env`, so it always uses your login. Set `LLM_BACKEND=api` to use `ANTHROPIC_API_KEY` instead.

**Other models (OpenAI-compatible):** `LLM_BACKEND=openai` runs the interviewer, reports and drafts on any OpenAI-compatible API. Set `LLM_MODEL` (required), and `OPENAI_API_KEY` for OpenAI or `OPENAI_BASE_URL` for a local server, such as `http://localhost:11434/v1` for Ollama or `http://localhost:1234/v1` for LM Studio. Time checks and notepad updates are sent as user messages, so servers that don't accept the `developer` role work too. The prompts are written and tested for Claude; other models, especially small local ones, may keep time or hang up less reliably, and the plumbing was tested against a mock server rather than a real model.

**Without an NVIDIA GPU:** set `WHISPER_DEVICE=cpu` and a smaller `WHISPER_MODEL` (`small` or `medium`), and remove `ONNX_PROVIDER`; see [Running without a GPU](../INSTALL.md#running-without-a-gpu). Whisper then uses int8 unless `WHISPER_COMPUTE_TYPE` says otherwise.

**Opening the pages from another computer:** the server answers only pages opened as `localhost` or `127.0.0.1`, so that other websites open in your browser can't read your resume and transcripts or start sessions. To allow another address, list it in `PIPECAT_ALLOWED_ORIGINS`, e.g. `PIPECAT_ALLOWED_ORIGINS=http://192.168.1.5:7860`. The microphone still needs `localhost` or HTTPS, so an SSH tunnel (`ssh -L 7860:localhost:7860 host`) is usually simpler.

**Pocket TTS (built-in voices or voice cloning):** before the first use, accept the terms at https://huggingface.co/kyutai/pocket-tts, run `hf auth login` in the venv, and install pocket-tts as shown in the comment at the end of `requirements.txt`. Pocket TTS runs on the CPU and adds about 10 seconds of loading at the start of each session.

- **Built-in voices:** set `pocket_voice: stuart_bell` in `config.yaml`. English male voices: `stuart_bell`, `javert`, `michael`, `paul`, `charles`, `george`, `jean`, `marius`, `peter_yearsley`, `bill_boerst`. Female voices: `alba`, `anna`, `vera`, `fantine`, `eponine`, `azelma`, `mary`, `jane`, `eve`, `caro_davy`, `cosette`. In testing, `stuart_bell` and `javert` were the clearest.
- **Voice cloning:** only use a voice whose owner has agreed to it. Prepare a 10–20 second `.wav` with one person speaking and no background music. Put it in the round folder's `voice/`, and set `voice_clone: voice/xxx.wav` in `config.yaml` (this takes priority over `pocket_voice`). **The recording quality is cloned too.** Phone calls, video calls and compressed video audio have a narrow bandwidth, so the cloned voice sounds muffled. Use an original, wideband recording (16 kHz or higher).

**Chinese interviews:** add `interview_language: zh-TW` to the round's `config.yaml` (or to `company.yaml` to apply it to the whole company). Or choose Chinese as the interview language in the 「新增公司或關卡」 wizard. In a Chinese interview:

- The interviewer asks questions in Traditional Chinese with Taiwanese wording, and keeps technical terms in English (for example, 「你為什麼把 GRU 換成 MLP？」, "Why did you replace the GRU with an MLP?").
- Speech recognition always uses Whisper (Parakeet does not support Chinese). The recognized text is converted to Traditional Chinese and Taiwanese wording, for example 「項目」 becomes 「專案」 (both mean "project").
- The voice switches to the Kokoro v1.1-zh Chinese model, with `voice: zm_010` as the default. Male voices are `zm_*` and female voices are `zf_*`, with dozens of each to try. Pocket TTS does not speak Chinese, so `voice_clone` and `pocket_voice` are ignored. The model (about 380 MB) downloads automatically on first use, or you can run `python scripts/download_models.py chinese` beforehand.
- Captions appear character by character. The feedback report and reference answers are in Chinese. Speaking rate is measured in characters per minute (each Chinese character or English word counts as one).

The Chinese voices have a mainland China accent and pronounce English terms only passably. This is a limit of the current lightweight local models.

**Other interview languages:** `interview_language` also takes Japanese, Spanish, French, Italian, Brazilian Portuguese and Hindi. The interviewer speaks the language (keeping technical terms in English), Whisper listens for it, and the report defaults to it.

| `interview_language` | Default voice | Other voices | Notes |
|---|---|---|---|
| `ja` (Japanese) | `jm_kumo` | `jf_alpha`, `jf_gongitsune`, `jf_nezumi`, `jf_tebukuro` | Pronunciation through misaki and pyopenjtalk (in `requirements.txt`; `python scripts/download_models.py japanese` fetches its 22 MB dictionary). English terms are read with a Japanese accent. |
| `es` (Spanish) | `em_alex` | `ef_dora` | |
| `fr` (French) | `ff_siwis` | | Kokoro has one French voice. |
| `it` (Italian) | `im_nicola` | `if_sara` | |
| `pt-BR` (Brazilian Portuguese) | `pm_alex` | `pf_dora` | |
| `hi` (Hindi) | `hm_omega` | `hm_psi`, `hf_alpha`, `hf_beta` | |

Parakeet understands English, Spanish, French, Italian and Portuguese; for the other languages Whisper is used even with `STT_BACKEND=parakeet`. Pocket TTS only speaks English. English and Mandarin are the most tested; the others were checked by having the interviewer's voice transcribed back by Whisper, and a full interview was run in Japanese and Spanish.

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
2. Run `python scripts/compare_stt.py transcripts/<company>/<round>/<time>-transcript.md`. It sends each answer to both Whisper and Parakeet and writes `*-stt-compare.md`, which lists the two models' results side by side with the live recognition from the interview. You can also open `/report?interview=<company>/<round>&file=<time>-transcript.md&kind=stt` in the address bar to view it.
3. Pick the one closer to what you actually said and set it as `STT_BACKEND`. Before using Parakeet for the first time, run `python scripts/download_models.py parakeet` (about 2.5 GB).

Whisper details: `interviewer/speech/whisper_stt.py` uses the interviewer's latest question and what you said earlier as a prompt. Segments with low confidence, segments that read out the hotwords list, and segments that copy the prompt are dropped, and the terminal prints `Dropped Whisper segment`. If things you really said are dropped, lower `WHISPER_MIN_AVG_LOGPROB` in `.env` (for example to `-1.3`). If Whisper is too slow, change `WHISPER_MODEL` to `deepdml/faster-whisper-large-v3-turbo-ct2`.

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
bot.py                 the live voice interview: run this (python bot.py)
interviewer/           the app's Python package
  server.py            the web pages and their API
  config.py            loads interview folders, checks settings, fills prompt templates
  settings.py          loads .env for every script; relative paths are relative to the project folder
  transcript.py        writes and reads back transcripts
  feedback.py          reports and scores (automatic after an interview, or python -m interviewer.feedback)
  analysis.py          answer length, pauses and speaking rate from turn timings
  history.py           weak spots, asked questions and progress data across sessions
  coding.py            coding interviews: picking and switching problems, interviewer and report briefs
  leetcode.py          fetches LeetCode problems and zerotrac ratings, cached locally
  claude_code.py       the interviewer through the Claude Code CLI, with recovery if the CLI crashes
  llm.py               one-off Claude calls for reports, resume conversion, drafts and problem rewrites
  setup_wizard.py      drafts and creates a new company or round
  resume_import.py     turns an uploaded resume into resume.md
  speech/
    whisper_stt.py     Whisper: conversation context, hallucination filters, Traditional Chinese output
    parakeet_stt.py    Parakeet: re-transcribes each whole answer after it ends
    stt_common.py      shared by both: answer audio, technical-term fixes, Parakeet download
    chinese.py         Mandarin text: Traditional conversion, spacing and punctuation, character counts
    chinese_tts.py     the Mandarin voice (Kokoro v1.1-zh)
scripts/
  setup_gpu.sh         one-time setup: venv, packages, GPU onnxruntime
  cuda_env.sh          makes the pip-installed CUDA libraries visible (source it in each terminal)
  download_models.py   downloads the models and checks the GPU
  compare_stt.py       compares speech-recognition models on your own recordings
web/                   setup page, interview page, report, progress, notepad
prompts/               prompt templates: interviewer, report, coding, resume, new rounds
interviews/            one folder per company, one subfolder per round; _template/ and example/ are shared
profile/               your general resume (not in git)
transcripts/           transcripts, reports and scores, one folder per interview (not in git)
tests/                 automated tests (no GPU, network or Claude needed)
```

## Known limitations

- The full live voice conversation (including automatic hang-up, sending the notepad to the interviewer, and recovery after a CLI crash) needs a microphone and a browser, so it can only be verified by hand on your own machine. Each component and the website API are tested.
- Turn timings are approximate. The end time of an answer includes about one second spent deciding whether you have finished talking. Whisper filters out some "uh" and "um", so filler word counts from the transcript are only rough.
- For voice cloning (Pocket TTS), only use voices you have the right to use and whose owners have agreed.
