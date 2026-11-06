# Installation and your first interview

**English** · [繁體中文](INSTALL.zh-TW.md) · [← Back to README](README.md)

The web UI is in Chinese. This guide gives each UI label in Chinese with its English meaning in parentheses the first time it appears.

## Requirements

- Linux, or WSL2 on Windows. Native Windows and macOS are not supported: the setup scripts are bash, and the GPU packages are for NVIDIA on Linux.
- An NVIDIA GPU with 6GB or more VRAM, and a driver that supports CUDA 12. No GPU? See [Running without a GPU](#running-without-a-gpu): it works, with slower replies.
- Python 3.10 to 3.12 (not 3.13 yet), with venv. On Ubuntu: `sudo apt install python3-venv`.
- About 15GB of free disk space (about 5GB of pip packages with the CUDA libraries, plus the models) and 8GB of RAM.
- An internet connection: the interview page loads its avatar library from the jsDelivr CDN, and coding interviews fetch problems from LeetCode.
- **Claude Code**, signed in with your Claude account, or an Anthropic API key. See [Claude Code](#claude-code) below.
- **Headphones.** With speakers, the interviewer may hear its own voice and interrupt itself.

### Claude Code

The interviewer, the feedback report and the setup wizard run on Claude. By default they use your Claude Code login, so no API key is needed:

1. Install Claude Code by following https://claude.com/claude-code. Tested with Claude Code 2.1.
2. Run `claude` once in a terminal and sign in, then leave with `/exit`.

If `claude` is not on your PATH, set `CLAUDE_CODE_PATH` in `.env`. On WSL, the copy that comes with the VS Code extension on Windows is found too. When `python bot.py` starts, it checks that Claude answers, and stops with an explanation if it doesn't.

Every turn of the interview is one Claude request, so practice counts against your plan's usage limits. The default model is Opus; setting `LLM_MODEL=claude-sonnet-5-5` in `.env` uses less and replies faster.

To use an API key instead, set `LLM_BACKEND=api` and `ANTHROPIC_API_KEY=...` in `.env`.

## Installation

```bash
./scripts/setup_gpu.sh                  # create the venv, install packages, switch to the GPU build of onnxruntime
source .venv/bin/activate
source scripts/cuda_env.sh              # lets Whisper find the CUDA libraries; run it in every new terminal
python scripts/download_models.py       # download the models (about 4GB) and check the GPU
```

At the end, `scripts/download_models.py` shows whether Whisper and Kokoro run on the GPU, and how fast Kokoro synthesizes speech. Go on to the next step only when both show OK.

The settings are in `.env` (created from `.env.example`, which explains each one). The defaults suit an NVIDIA GPU and a Claude Code login.

### Running without a GPU

Everything also runs on the CPU, more slowly: expect a few extra seconds before each reply, mostly from speech recognition.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # the CPU build of onnxruntime; skip setup_gpu.sh and cuda_env.sh
cp .env.example .env
```

Then in `.env`, set `WHISPER_DEVICE=cpu` and `WHISPER_MODEL=small` (`medium` is more accurate and slower), and delete the `ONNX_PROVIDER` line. Run `python scripts/download_models.py` as usual.

### Your resume

The interviewer asks about your experience from your resume. Before the first interview, add it on the setup page under 「履歷」 (Resume): paste the text or upload a PDF or Word file. Without one, the interviewer can only ask general questions.

## Starting an interview

1. Run `python bot.py` and open **http://localhost:7860/** in your browser.
2. On the left, under 「開始練習」 (Start practicing), pick an interview. Then pick a practice mode:
   - **完整面試** (Full interview): follows the structure in round_info, from the opening to your questions for the interviewer.
   - **專項練習** (Focused practice): 10–30 minutes on a single topic. The topic can be one that the last report suggested you work on, a rubric dimension, or one you type in.
   - **教練模式** (Coach mode, a checkbox under 專項練習): after each answer, the interviewer points out what you missed and shows a better way to say it. Then you answer again. The report scores only your first answer, and says whether the second try improved.
   - **Coding**: a LeetCode-style coding interview in Python or C++, with problems picked from LeetCode by difficulty, topic and rating. You write code in the shared notepad and explain it out loud. See [Coding interviews](docs/reference.md#coding-interviews) in the reference.
   - **接續** (Continue) a transcript that was cut off earlier (see [Continuing after a disconnect](docs/reference.md#continuing-after-a-disconnect) in the reference). You can also press 「接續」 on that session's row in 「練習紀錄」 (Practice history) on the right.
3. Press 「前往面試」 (Go to interview). On the interview page, press 「開始面試」 (Start interview) and allow microphone access (see [Virtual interviewer](#virtual-interviewer) below).
4. When the interviewer wraps up and says goodbye, the call **hangs up automatically**. If you say partway through that you want to stop, it also says goodbye and hangs up. To end right away, press 「結束並產生報告」 (End and generate report) on the interview page or the setup page.
5. The feedback report is ready in about a minute. In 「練習紀錄」 on the right of the setup page, each session has 「報告」 (Report) and 「逐字稿」 (Transcript) links. The left side shows the scores of the most recent session.

### Virtual interviewer

The interview page (`/interview`) shows a 3D virtual interviewer. Its mouth moves with the interviewer's voice, and it looks at you when it starts a new sentence. Live captions run along the bottom of the page. One line shows what the interviewer says. The other line, 「系統聽到你說」 (What the system heard you say), shows what speech recognition heard, so you can spot recognition errors on the spot.

- The avatar is rendered in the browser with [TalkingHead](https://github.com/met4citizen/TalkingHead). [HeadAudio](https://github.com/met4citizen/HeadAudio) works out the mouth shapes from the voice in real time, so **it uses no server GPU at all**. To keep the mouth in sync with the sound, the interviewer's voice plays about 0.1 seconds late.
- `python scripts/download_models.py` downloads the avatar and lip-sync files to `web/avatars/` and `web/vendor/`. To download only these, run `python scripts/download_models.py avatar`. TalkingHead itself and three.js load from the jsDelivr CDN, so the first time you open the interview page you need an internet connection.
- The default avatar is `david.glb`, which comes with HeadAudio (made with Ready Player Me, for personal use only). To use a different avatar, put a GLB file with ARKit and Oculus viseme blend shapes in `web/avatars/`. Then in the round's `config.yaml`, set `avatar: <file name>` (without .glb) and `avatar_body: M` or `F`.
- If the avatar fails to load (for example, no internet, or the avatar files were not downloaded), you can still do a voice-only interview on the interview page. The lower right corner of the interview page also has a 「純語音頁」 (Voice-only page) link to Pipecat's original `/client` page.

### Shared notepad

When you need to write code or sketch an architecture, open **http://localhost:7860/notepad** in another tab (「共用筆記板」 (Shared notepad) at the top of the setup page). The notepad content goes to the interviewer the next time you start answering, and the interviewer asks follow-up questions about what you wrote. The final content at the end of the interview is also saved in the transcript.

## Finding where the latency comes from

While `bot.py` runs, the terminal prints latency numbers for every turn. Typical numbers for each component:

- Whisper: usually a few hundred milliseconds on the GPU.
- Claude: the time to first token. This is usually the largest part.
- Kokoro: fast on the GPU. Usually not the bottleneck.

If Kokoro is slow, it is most likely running on the CPU. See Troubleshooting below.

## Troubleshooting

**`bot.py` stops with "The Claude Code CLI can't be used":** the message says why. "not found": install Claude Code, or set `CLAUDE_CODE_PATH` in `.env`. "Not logged in" or an authentication error: run `claude` and sign in. A usage limit: wait for it to reset, use a smaller model (`LLM_MODEL=claude-sonnet-5-5`), or switch to `LLM_BACKEND=api`.

**`libcudnn` or `libcublas` not found:** this terminal has not run `source scripts/cuda_env.sh` yet.

**`scripts/download_models.py` says CUDAExecutionProvider does not exist:** both the CPU and GPU builds of onnxruntime are installed. Reinstall with `pip uninstall -y onnxruntime onnxruntime-gpu && pip install onnxruntime-gpu==1.24.4`.

**The interviewer keeps interrupting you:** wear headphones. Smart Turn waits while you pause to think. But if the microphone picks up sound from the speakers, the system thinks you are talking.

**The interviewer takes too long to respond:** check the latency numbers. If Claude is slow, see "Latency is still too high" under [Settings](docs/reference.md#settings) in the reference.

**Every connection starts with a wait of a few seconds:** this is normal. Whisper and Kokoro reload at the start of each session. If the models are already downloaded, this takes only a few seconds.

**The interviewer reads out `[time check]` or `[[END]]`:** this should not happen. Check whether the Timekeeping and Ending the interview sections in `prompts/interviewer.md` were changed.

**The interview page shows only an error message and no interviewer:** first run `python scripts/download_models.py avatar` to download the avatar. Then make sure your computer can reach cdn.jsdelivr.net. If it still does not work, press 「純語音頁」 and do the interview as usual.

**The interviewer's mouth does not move:** make sure `web/vendor/headaudio/` contains three files. Low headphone volume does not affect the mouth. The mouth shapes are computed from the voice audio that the server sends.

**The browser doesn't ask for the microphone, or says it isn't available:** browsers only allow the microphone on `http://localhost` or HTTPS. If `bot.py` runs on another computer, open the page through an SSH tunnel (`ssh -L 7860:localhost:7860 that-computer`, then http://localhost:7860/) rather than by its IP address.

**A page says "Only pages opened from this computer may use the interviewer":** the server only answers pages opened as `localhost` or `127.0.0.1`, so that other websites can't read your resume and transcripts. To open it under another address on purpose, add it to `PIPECAT_ALLOWED_ORIGINS` in `.env`, e.g. `PIPECAT_ALLOWED_ORIGINS=http://192.168.1.5:7860`.

**Coding mode says it can't reach leetcode.com:** problems come from LeetCode the first time they are used and are cached after that (in `~/.cache/ai-interviewer/leetcode/`). Check your connection; problems already used keep working offline.

**The interviewer does not hang up after saying goodbye:** the app hangs up after the goodbye audio finishes playing, and waits at most 20 more seconds. If it never hangs up, the interviewer did not output the end marker. Press 「結束並產生報告」 on the setup page.

---

For how to write interview folders, settings, Chinese interviews, feedback reports, practice progress, and more, see the [reference](docs/reference.md).
