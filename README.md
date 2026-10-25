# AI 模擬面試官

全本機自架的語音面試官。你用瀏覽器跟它講話，它會根據 JD 和你的回答即時追問，結束後產生回饋報告，並記住你的弱點，下一場刻意再考。

```
瀏覽器 (麥克風/喇叭)          http://localhost:7860/  設定頁：選面試、專項練習、接續、報告、進度、履歷、新增關卡
   ⇅ WebRTC                  http://localhost:7860/client  面試頁
bot.py (Pipecat 1.12.0)
   ├─ Silero VAD + Smart Turn v3   本機，判斷你講完了沒、處理打斷
   ├─ faster-whisper large-v3      本機 GPU，語音轉文字
   ├─ Claude Opus 5.5               面試官大腦，預設透過 Claude Code CLI（不需要 API key）
   ├─ Kokoro 或 Pocket TTS          文字轉語音：Kokoro 內建聲音（GPU），或 Pocket TTS 複製聲音（CPU）
   └─ transcripts/                  逐字稿、回饋報告、分數
```

除了 Claude，其他元件全部在你的電腦上執行。

## 需求

- Linux 或 Windows 的 WSL2（Windows 原生環境沒測過，`cuda_env.sh` 是 bash 腳本）
- NVIDIA GPU，建議 6GB 以上 VRAM，驅動要支援 CUDA 12
- Python 3.10 到 3.12
- Claude Code 登入（預設），或 Anthropic API key
- **耳機**：用喇叭的話，面試官可能聽到自己的聲音而打斷自己

## 安裝

```bash
./setup_gpu.sh                  # 建 venv、安裝套件、換成 GPU 版 onnxruntime
nano .env                       # 用 API 的話填入 ANTHROPIC_API_KEY
source .venv/bin/activate
source cuda_env.sh              # 讓 Whisper 找得到 CUDA 函式庫，每開一個新終端機都要跑
python download_models.py       # 下載模型（約 4GB）並檢查 GPU
```

`download_models.py` 最後會顯示 Whisper 和 Kokoro 是否成功跑在 GPU 上，以及 Kokoro 的合成速度。兩項都顯示 OK 再進下一步。

## 開始面試

1. 執行 `python bot.py`，用瀏覽器打開 **http://localhost:7860/**。
2. 選面試，再選起點：
   - **開始新的完整面試**：照 round_info 的結構，從開場到你的提問。
   - **專項練習**：只針對一個主題練 10–30 分鐘。主題可以選評分面向、上次報告建議加強的主題，或自己輸入。
   - **接續**之前的逐字稿（見下一節）。
3. 按「前往面試」，在面試頁按「開始面試」，允許使用麥克風（見下方「虛擬面試官」）。
4. 面試官收尾、說再見後會**自動掛斷**；你中途說想結束，它也會道別後掛斷。想直接結束，到設定頁按「結束並產生報告」。
5. 回饋報告約一分鐘內產生。設定頁每份逐字稿旁有「看回饋報告」「看逐字稿」連結。

### 虛擬面試官

面試頁（`/interview`）會顯示一位 3D 虛擬面試官，嘴型跟著面試官的語音動，說新句子時會看向你；畫面下方有即時字幕，一行是面試官說的話，一行是「系統聽到你說」，可以當場看出語音辨識有沒有聽錯。

- 頭像在瀏覽器裡用 [TalkingHead](https://github.com/met4citizen/TalkingHead) 繪製，嘴型由 [HeadAudio](https://github.com/met4citizen/HeadAudio) 從語音即時推算，**完全不佔用伺服器的 GPU**。為了讓嘴型和聲音對齊，面試官的聲音會延遲約 0.1 秒播放。
- 頭像和嘴型檔由 `python download_models.py` 下載到 `web/avatars/`、`web/vendor/`（只下載這部分：`python download_models.py avatar`）。TalkingHead 本身和 three.js 從 jsDelivr CDN 載入，所以第一次開面試頁需要網路。
- 預設頭像是 HeadAudio 附的 `david.glb`（Ready Player Me 製作，僅供個人使用）。要換頭像，把有 ARKit 和 Oculus viseme 表情的 GLB 檔放進 `web/avatars/`，在關卡的 `config.yaml` 設 `avatar: 檔名`（不含 .glb）和 `avatar_body: M` 或 `F`。
- 頭像載入失敗（例如沒網路、沒下載頭像檔）時，面試頁仍可用純語音面試；面試頁右下角也有「純語音頁」連結，可改用 Pipecat 原本的 `/client` 頁。

### 共用筆記板

需要寫程式或畫架構時，另開 **http://localhost:7860/notepad**（設定頁上方的「共用筆記板」）。內容會在你下一次開口回答時傳給面試官，它會針對你寫的內容追問；面試結束時的最終內容也會記進逐字稿。

## 回饋報告與練習進度

每場結束後，`transcripts/<公司>/<關卡>/` 會有三個檔案：

| 檔案 | 內容 |
|---|---|
| `*-transcript.md` | 逐字稿，含每一輪的開始時間和長度 |
| `*-feedback.md` | 回饋報告：依評分標準打分、最強與最弱的時刻、**逐題回顧和英文參考答案**、該準備的追問、表達分析（回答長度、開口前停頓、語速）、總體判定 |
| `*-scores.json` | 結構化分數：各面向分數、弱點、問過的題目、下次建議練的主題 |

- **學習循環**：下一場開始時，面試官會讀到之前幾場的弱點和問過的題目，換個問法重考弱點、避開重複題，但不會跟你提起之前的練習。
- **練習進度**：設定頁上方的「練習進度」顯示各面向分數隨場次的趨勢，以及每一場的判定和建議主題。
- **補產生報告**：沒有報告的逐字稿（例如中途斷線又不想接續），在設定頁按「產生回饋報告」。也可以用指令：

```bash
python feedback.py transcripts/example/tech/20261101-1930-transcript.md
python feedback.py --scores-only transcripts/example/tech/*-transcript.md   # 從舊報告補出分數，不重寫報告
```

## 斷線後接續

網路斷掉、不小心關掉網頁，或想中途休息，都可以接著同一場繼續：

- **`bot.py` 還開著**：不到一半時間就斷線的話，直接再按 Connect 就會接續。要接續其他逐字稿，回到設定頁選那一份。
- **`bot.py` 已經關掉**：重新執行 `python bot.py`，在設定頁選要接續的逐字稿，或直接下 `python bot.py --resume transcripts/example/tech/20261101-1930-transcript.md`。

連線後面試官會簡短歡迎你回來，不會重新自我介紹，從中斷的地方繼續；上一題沒答完就重問。計時接著上次的進度算，逐字稿寫回同一個檔案。

結束方式決定會不會產生報告：面試官道別、或你按了「結束並產生報告」，一定會產生；直接斷線的話，超過一半時間才產生，不到一半則當成斷線，下一次 Connect 自動接續。

## 準備面試

repo 附了一個虛構的範例 `interviews/example/`（Acme Vision 電腦視覺工程師的技術面試），clone 下來就能直接試跑，也可以照著它的格式寫你自己的。你自己建立的公司資料夾只會留在本機，`.gitignore` 只追蹤 `_template/` 和 `example/`。

每家公司一個資料夾，裡面每一關再各一個子資料夾：

```
interviews/
  acme/
    company.yaml        公司、職缺、Whisper 提示詞、回饋報告語言
    jd.md               職缺描述（每一關共用）
    company_info.md     你問面試官問題時，它能用的公司資訊（只寫確定的事實）
    resume.md           這家公司專用的履歷（選用）
    tech/               一關一個資料夾
      config.yaml       面試官名字和職稱、關卡、時長、難度、聲音
      round_info.md     這關評估什麼、形式、面試官的風格
      question_bank.md  這關可能被問的題目
      rubric.md         評分標準：每個 ## 標題是一個面向，寫出 5、3、1 分的樣子
      voice/            複製聲音用的參考音檔（選用）
```

**用網頁建立（建議）**：設定頁最下面的「新增公司或關卡」，貼上 JD 和你知道的這一關資訊（HR 的說明、面試官背景），按「產生草稿」。Claude 會依 JD 和你的履歷起草 round_info、題庫、評分標準、公司資訊和 Whisper 提示詞，檢查修改後按「建立」。選既有公司的話，只會新增一關，沿用公司的 JD 和設定。

**手動建立**：複製範本，再把 `round1` 改成關卡名稱：

```bash
cp -r interviews/_template interviews/acme
mv interviews/acme/round1 interviews/acme/tech
```

**檔案的查找順序**：先找這一關的資料夾，再找公司資料夾，履歷最後才用 `profile/resume.md`。任何檔案都可以放在關卡資料夾裡覆蓋公司的版本。兩層的 `stt_hotwords` 會合併。

**設定檢查**：設定頁會列出每一場的問題。錯誤（例如少了面試官名字、YAML 打錯、時長不是數字）要修正才能開始；提醒（例如沒有 rubric.md）不影響開始，但報告會比較不準。`bot.py` 啟動時也會在終端機印出。

名稱以 `_` 開頭的資料夾（例如 `_template`）不會出現在選單裡。網頁上預設選的面試可以用 `python bot.py --interview acme/tech` 或 `.env` 的 `INTERVIEW=acme/tech` 指定；公司只有一關時寫公司名稱就好。

`stt_hotwords` 很值得花時間填：把 JD 裡的專有名詞、產品名、縮寫列進去，Whisper 會比較容易聽對。只放真的容易聽錯的詞：清單越長，Whisper 在聽不清楚時越容易把清單本身念出來（程式會把「連續三個詞照清單順序出現」的片段濾掉）。

### 更新履歷

在設定頁的「履歷」區塊按「上傳新履歷」，選 PDF、Word（.docx）、.txt 或 .md 檔。系統會擷取文字，再請 Claude 整理成 `resume.md` 的格式（不改任何內容，只修復斷行和欄位順序，聯絡方式會拿掉），約需半分鐘到一分鐘。檢查或修改後選擇存放位置：這家公司的所有關卡（上傳時的預設）、只用在這一關、或所有公司共用（`profile/resume.md`）。舊版本會備份到 `profile/backups/`。也可以按「編輯目前履歷」直接改。掃描成圖片的 PDF 讀不到文字，請改傳 Word 或文字檔；.md 檔會直接使用。

## 調整設定

**聲音：** 在 `config.yaml` 修改 `voice`。美式男聲有 `am_michael`、`am_adam`、`am_eric`、`am_liam`、`am_onyx`、`am_fenrir`、`am_puck`、`am_echo`。英式男聲有 `bm_george`、`bm_lewis`、`bm_daniel`、`bm_fable`，用英式聲音時要把 `voice_language` 改成 `en-gb`。

**用誰的 Claude：** `.env` 的 `LLM_BACKEND=claude_code`（預設）會用你 Claude Code 的登入身分，不需要 API key，會自動找 PATH 上的 `claude` 或 VS Code 擴充套件內建的那份，找不到就設 `CLAUDE_CODE_PATH`。每輪第一個字約 2–3 秒。如果 CLI 在面試中當掉或超過 60 秒沒有回應，面試官會先說「Sorry, give me just a second」，重新啟動 CLI、帶入目前為止的對話後再試一次。改成 `LLM_BACKEND=api` 就走 `ANTHROPIC_API_KEY`。

**複製聲音：** 只能用本人同意使用的聲音。準備一段 10–20 秒、只有一個人說話、沒有背景音樂的 `.wav`，放在關卡資料夾的 `voice/` 裡，`config.yaml` 設 `voice_clone: voice/xxx.wav`。第一次使用要先到 https://huggingface.co/kyutai/pocket-tts 同意條款，再執行 `uvx hf auth login`，並安裝 `requirements.txt` 最後註解裡的 pocket-tts。Pocket TTS 跑在 CPU 上，每場開始時會多花約 10 秒載入。

**面試官搶話：** `.env` 的 `CANDIDATE_PAUSE_SECS`（預設 0.8）是你停頓多久之後才開始判斷你講完了沒。還是會被打斷就調高，嫌回應慢就調低。

**語音辨識準確度：** 預設用 Whisper `large-v3` 完整版，聽有口音的英文比 turbo 版準，但比較吃 VRAM（約 3–4 GB），每段也會慢一些。嫌慢可以在 `.env` 把 `WHISPER_MODEL` 改回 `deepdml/faster-whisper-large-v3-turbo-ct2`。`whisper_stt.py` 會把面試官剛問的問題和你前面講的話當成提示；信心太低、在念 hotwords 清單、或照抄提示的片段會被丟掉，終端機會印出 `Dropped Whisper segment`。如果真的講過的話被丟掉，把 `.env` 的 `WHISPER_MIN_AVG_LOGPROB` 調低（例如 `-1.3`）。

**難度：** `difficulty: tough` 會讓面試官更常質疑你的推論，也會追著要數字。

**追問深度和速度的取捨：** 在 `.env` 設定 `INTERVIEWER_THINKING=adaptive`（只對 `LLM_BACKEND=api` 有效），Claude 會先思考再回應，追問更犀利，但每輪會多等幾秒。

**延遲還是太高：** 可以把 `LLM_MODEL` 換成 `claude-sonnet-5-5`，即時對話用比較快的模型。`FEEDBACK_MODEL` 維持 `claude-opus-5-5`，負責回饋報告、履歷轉換和新增關卡的草稿。

## 看延遲出在哪裡

`bot.py` 執行時，終端機每一輪都會印出延遲數據。各元件的延遲大概會落在：

- Whisper：GPU 上通常幾百毫秒
- Claude：首個 token 的時間，通常是最大的一塊
- Kokoro：GPU 上很快，通常不是瓶頸

如果 Kokoro 很慢，多半是它跑在 CPU 上，請參考下面的疑難排解。

## 疑難排解

**出現 `libcudnn` 或 `libcublas` 找不到：** 這個終端機還沒跑 `source cuda_env.sh`。

**`download_models.py` 顯示 CUDAExecutionProvider 不存在：** 安裝環境裡同時有 CPU 版和 GPU 版的 onnxruntime。執行 `pip uninstall -y onnxruntime onnxruntime-gpu && pip install onnxruntime-gpu==1.24.4` 重裝。

**面試官一直打斷你：** 戴耳機。Smart Turn 會等你停頓思考，但如果喇叭的聲音被麥克風收進去，系統會以為你在講話。

**面試官等太久才回應：** 檢查延遲數據。如果是 Claude 太慢，參考上面「延遲還是太高」的做法。

**每次連線一開始都要等幾秒：** 這是正常的。每場開始時會重新載入 Whisper 和 Kokoro，模型已經下載過的話只要幾秒。

**面試官念出 `[time check]` 或 `[[END]]`：** 這不應該發生。請檢查 `prompts/interviewer.md` 裡 Timekeeping 和 Ending the interview 段落是否被改動。

**面試頁看不到面試官、只顯示錯誤訊息：** 先執行 `python download_models.py avatar` 下載頭像，再確認電腦連得到 cdn.jsdelivr.net。仍然不行就按「純語音頁」照常面試。

**面試官的嘴沒在動：** 確認 `web/vendor/headaudio/` 裡有三個檔案。耳機音量太小不影響嘴型，嘴型是從伺服器送來的語音算的。

**面試官道別後沒有掛斷：** 程式會在道別的語音播完後掛斷，最多再等 20 秒。如果完全沒掛斷，代表面試官沒有輸出結束標記，按設定頁的「結束並產生報告」即可。

## 開發

```bash
pytest                       # 自動化測試，不需要 GPU、網路或 Claude
```

專案用 git 管理。`transcripts/`、`profile/`、各公司資料夾裡的 `resume.md` 和 `voice/` 都是個人資料，已列入 `.gitignore`，不會被提交。

## 專案結構

```
bot.py                語音 pipeline 主程式：計時、結束流程、專項練習、筆記板
whisper_stt.py        Whisper 語音辨識：帶入對話上下文、過濾幻覺片段
claude_code_llm.py    透過 Claude Code CLI 呼叫面試官，CLI 當掉時自動恢復
feedback.py           回饋報告和分數（面試結束自動執行，也可手動執行）
analysis.py           從每輪時間算出回答長度、停頓、語速
history.py            跨場次的弱點、問過的題目、進度資料
interview_config.py   載入面試資料夾、設定檢查、填入 prompt 模板
transcript.py         寫入與讀回逐字稿
session_picker.py     設定網站和它的 API
setup_wizard.py       新增公司或關卡：草稿與建立
resume_import.py      把上傳的履歷檔轉成 resume.md
llm.py                回饋報告、履歷轉換、草稿共用的一次性 Claude 呼叫
web/                  設定頁、面試頁（虛擬面試官）、報告頁、進度頁、筆記板
download_models.py    下載模型、檢查 GPU
prompts/              面試官、回饋報告、履歷轉換、新增關卡的 prompt 模板
profile/resume.md     通用履歷，公司或關卡沒有自己的版本時使用
interviews/           每家公司一個資料夾、每一關一個子資料夾；_template/ 是範本
transcripts/          逐字稿、回饋報告、分數，依面試分資料夾
tests/                自動化測試
```

## 已知限制

- 完整的即時語音對話（含自動掛斷、筆記板傳給面試官、CLI 當掉後恢復）需要麥克風和瀏覽器，只能在你自己的機器上實際驗證；各元件和網站 API 都有測過。
- 每輪時間是近似值：回答的結束時間包含約一秒的「判斷你講完了沒」。Whisper 會濾掉部分 uh、um，所以贅字數量只能從逐字稿粗略判斷。
- 複製聲音（Pocket TTS）請只使用你有權使用、本人同意的聲音。
