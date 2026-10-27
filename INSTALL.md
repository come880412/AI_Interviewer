# Installation and your first interview

**English** · [繁體中文](INSTALL.zh-TW.md) · [← Back to README](README.md)

The web UI is in Chinese. This guide gives each UI label in Chinese with its English meaning in parentheses the first time it appears.

## Requirements

- Linux, or WSL2 on Windows. Native Windows has not been tested, and `cuda_env.sh` is a bash script.
- An NVIDIA GPU. 6GB or more VRAM is recommended, and the driver must support CUDA 12.
- Python 3.10 to 3.12.
- A Claude Code login (the default), or an Anthropic API key.
- **Headphones.** With speakers, the interviewer may hear its own voice and interrupt itself.

## Installation

```bash
./setup_gpu.sh                  # create the venv, install packages, switch to the GPU build of onnxruntime
nano .env                       # if you use the API, set ANTHROPIC_API_KEY
source .venv/bin/activate
source cuda_env.sh              # lets Whisper find the CUDA libraries; run it in every new terminal
python download_models.py       # download the models (about 4GB) and check the GPU
```

At the end, `download_models.py` shows whether Whisper and Kokoro run on the GPU, and how fast Kokoro synthesizes speech. Go on to the next step only when both show OK.

## Starting an interview

1. Run `python bot.py` and open **http://localhost:7860/** in your browser.
2. On the left, under 「開始練習」 (Start practicing), pick an interview. Then pick a practice mode:
   - **完整面試** (Full interview): follows the structure in round_info, from the opening to your questions for the interviewer.
   - **專項練習** (Focused practice): 10–30 minutes on a single topic. The topic can be one that the last report suggested you work on, a rubric dimension, or one you type in.
   - **教練模式** (Coach mode, a checkbox under 專項練習): after each answer, the interviewer points out what you missed and shows a better way to say it. Then you answer again. The report scores only your first answer, and says whether the second try improved.
   - **接續** (Continue) a transcript that was cut off earlier (see [Continuing after a disconnect](docs/reference.md#continuing-after-a-disconnect) in the reference). You can also press 「接續」 on that session's row in 「練習紀錄」 (Practice history) on the right.
3. Press 「前往面試」 (Go to interview). On the interview page, press 「開始面試」 (Start interview) and allow microphone access (see [Virtual interviewer](#virtual-interviewer) below).
4. When the interviewer wraps up and says goodbye, the call **hangs up automatically**. If you say partway through that you want to stop, it also says goodbye and hangs up. To end right away, press 「結束並產生報告」 (End and generate report) on the interview page or the setup page.
5. The feedback report is ready in about a minute. In 「練習紀錄」 on the right of the setup page, each session has 「報告」 (Report) and 「逐字稿」 (Transcript) links. The left side shows the scores of the most recent session.

### Virtual interviewer

The interview page (`/interview`) shows a 3D virtual interviewer. Its mouth moves with the interviewer's voice, and it looks at you when it starts a new sentence. Live captions run along the bottom of the page. One line shows what the interviewer says. The other line, 「系統聽到你說」 (What the system heard you say), shows what speech recognition heard, so you can spot recognition errors on the spot.

- The avatar is rendered in the browser with [TalkingHead](https://github.com/met4citizen/TalkingHead). [HeadAudio](https://github.com/met4citizen/HeadAudio) works out the mouth shapes from the voice in real time, so **it uses no server GPU at all**. To keep the mouth in sync with the sound, the interviewer's voice plays about 0.1 seconds late.
- `python download_models.py` downloads the avatar and lip-sync files to `web/avatars/` and `web/vendor/`. To download only these, run `python download_models.py avatar`. TalkingHead itself and three.js load from the jsDelivr CDN, so the first time you open the interview page you need an internet connection.
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

**`libcudnn` or `libcublas` not found:** this terminal has not run `source cuda_env.sh` yet.

**`download_models.py` says CUDAExecutionProvider does not exist:** both the CPU and GPU builds of onnxruntime are installed. Reinstall with `pip uninstall -y onnxruntime onnxruntime-gpu && pip install onnxruntime-gpu==1.24.4`.

**The interviewer keeps interrupting you:** wear headphones. Smart Turn waits while you pause to think. But if the microphone picks up sound from the speakers, the system thinks you are talking.

**The interviewer takes too long to respond:** check the latency numbers. If Claude is slow, see "Latency is still too high" under [Settings](docs/reference.md#settings) in the reference.

**Every connection starts with a wait of a few seconds:** this is normal. Whisper and Kokoro reload at the start of each session. If the models are already downloaded, this takes only a few seconds.

**The interviewer reads out `[time check]` or `[[END]]`:** this should not happen. Check whether the Timekeeping and Ending the interview sections in `prompts/interviewer.md` were changed.

**The interview page shows only an error message and no interviewer:** first run `python download_models.py avatar` to download the avatar. Then make sure your computer can reach cdn.jsdelivr.net. If it still does not work, press 「純語音頁」 and do the interview as usual.

**The interviewer's mouth does not move:** make sure `web/vendor/headaudio/` contains three files. Low headphone volume does not affect the mouth. The mouth shapes are computed from the voice audio that the server sends.

**The interviewer does not hang up after saying goodbye:** the app hangs up after the goodbye audio finishes playing, and waits at most 20 more seconds. If it never hangs up, the interviewer did not output the end marker. Press 「結束並產生報告」 on the setup page.

---

For how to write interview folders, settings, Chinese interviews, feedback reports, practice progress, and more, see the [reference](docs/reference.md).
