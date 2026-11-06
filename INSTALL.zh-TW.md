# 安裝與第一場面試

[English](INSTALL.md) · **繁體中文** · [← 回到 README](README.zh-TW.md)

## 需求

- Linux 或 Windows 的 WSL2。不支援 Windows 原生環境和 macOS：安裝腳本是 bash，GPU 套件只有 Linux 的 NVIDIA 版。
- NVIDIA GPU，6GB 以上 VRAM，驅動要支援 CUDA 12。沒有 GPU 也能跑，回應會慢一些，見[沒有 GPU 的跑法](#沒有-gpu-的跑法)。
- Python 3.10 到 3.12（還不支援 3.13），要有 venv。Ubuntu 上：`sudo apt install python3-venv`。
- 約 15GB 硬碟空間（含 CUDA 函式庫的 pip 套件約 5GB，加上模型）和 8GB 記憶體。
- 網路：面試頁從 jsDelivr CDN 載入頭像程式庫，Coding 面試從 LeetCode 抓題目。
- **Claude Code**，用你的 Claude 帳號登入；或 Anthropic API key。見下方 [Claude Code](#claude-code)。
- **耳機**：用喇叭的話，面試官可能聽到自己的聲音而打斷自己。

### Claude Code

面試官、回饋報告和新增關卡的精靈都用 Claude。預設用你的 Claude Code 登入身分，不需要 API key：

1. 照 https://claude.com/claude-code 安裝 Claude Code（測試過的版本是 Claude Code 2.1）。
2. 在終端機執行一次 `claude` 並登入，再用 `/exit` 離開。

`claude` 不在 PATH 上的話，在 `.env` 設 `CLAUDE_CODE_PATH`。在 WSL 上也會找到 Windows 上 VS Code 擴充套件內建的那份。`python bot.py` 啟動時會先確認 Claude 能回應，不行就停下來並說明原因。

面試的每一輪都是一次 Claude 請求，所以練習會算進你方案的用量上限。預設模型是 Opus；在 `.env` 設 `LLM_MODEL=claude-sonnet-5-5` 用量較少、回應也比較快。

想改用 API key：在 `.env` 設 `LLM_BACKEND=api` 和 `ANTHROPIC_API_KEY=...`。

## 安裝

```bash
./scripts/setup_gpu.sh                  # 建 venv、安裝套件、換成 GPU 版 onnxruntime
source .venv/bin/activate
source scripts/cuda_env.sh              # 讓 Whisper 找得到 CUDA 函式庫，每開一個新終端機都要跑
python scripts/download_models.py       # 下載模型（約 4GB）並檢查 GPU
```

`scripts/download_models.py` 最後會顯示 Whisper 和 Kokoro 是否成功跑在 GPU 上，以及 Kokoro 的合成速度。兩項都顯示 OK 再進下一步。

設定都在 `.env`（由 `.env.example` 複製而來，裡面有每一項的說明）。預設值適用 NVIDIA GPU 加 Claude Code 登入。

### 沒有 GPU 的跑法

全部都能在 CPU 上跑，只是比較慢：每次回應前會多幾秒，主要花在語音辨識。

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # CPU 版 onnxruntime；不用跑 setup_gpu.sh 和 cuda_env.sh
cp .env.example .env
```

接著在 `.env` 設 `WHISPER_DEVICE=cpu`、`WHISPER_MODEL=small`（`medium` 比較準、也比較慢），並刪掉 `ONNX_PROVIDER` 那一行。之後一樣執行 `python scripts/download_models.py`。

### 你的履歷

面試官會根據你的履歷問經歷。第一場面試前，先在設定頁的「履歷」分頁貼上文字，或上傳 PDF、Word 檔。沒有履歷的話，面試官只能問一般性的問題。

## 開始面試

1. 執行 `python bot.py`，用瀏覽器打開 **http://localhost:7860/**。
2. 在左邊的「開始練習」選面試，再選練習方式：
   - **完整面試**：照 round_info 的結構，從開場到你的提問。
   - **專項練習**：只針對一個主題練 10–30 分鐘。主題可以選上次報告建議加強的主題、評分面向，或自己輸入。
   - **教練模式**（專項練習裡勾選）：每答完一題，面試官馬上指出漏掉什麼、示範更好的講法，再讓你重答一次。報告只用第一次的回答評分，並說明重答有沒有進步。
   - **Coding**：LeetCode 風格的 coding 面試，用 Python 或 C++，題目依難度、題型、rating 從 LeetCode 挑。你在共用筆記板寫程式、邊寫邊講。見參考手冊的 [Coding 面試](docs/reference.zh-TW.md#coding-面試)。
   - **接續**之前中斷的逐字稿（見參考手冊的[斷線後接續](docs/reference.zh-TW.md#斷線後接續)）。也可以在右邊練習紀錄那一列按「接續」。
3. 按「前往面試」，在面試頁按「開始面試」，允許使用麥克風（見下方「虛擬面試官」）。
4. 面試官收尾、說再見後會**自動掛斷**；你中途說想結束，它也會道別後掛斷。想直接結束，按面試頁或設定頁的「結束並產生報告」。
5. 回饋報告約一分鐘內產生。設定頁右邊的「練習紀錄」每一場都有「報告」「逐字稿」連結，左邊會顯示最近一場的分數。

### 虛擬面試官

面試頁（`/interview`）會顯示一位 3D 虛擬面試官，嘴型跟著面試官的語音動，說新句子時會看向你；畫面下方有即時字幕，一行是面試官說的話，一行是「系統聽到你說」，可以當場看出語音辨識有沒有聽錯。

- 頭像在瀏覽器裡用 [TalkingHead](https://github.com/met4citizen/TalkingHead) 繪製，嘴型由 [HeadAudio](https://github.com/met4citizen/HeadAudio) 從語音即時推算，**完全不佔用伺服器的 GPU**。為了讓嘴型和聲音對齊，面試官的聲音會延遲約 0.1 秒播放。
- 頭像和嘴型檔由 `python scripts/download_models.py` 下載到 `web/avatars/`、`web/vendor/`（只下載這部分：`python scripts/download_models.py avatar`）。TalkingHead 本身和 three.js 從 jsDelivr CDN 載入，所以第一次開面試頁需要網路。
- 預設頭像是 HeadAudio 附的 `david.glb`（Ready Player Me 製作，僅供個人使用）。要換頭像，把有 ARKit 和 Oculus viseme 表情的 GLB 檔放進 `web/avatars/`，在關卡的 `config.yaml` 設 `avatar: 檔名`（不含 .glb）和 `avatar_body: M` 或 `F`。
- 頭像載入失敗（例如沒網路、沒下載頭像檔）時，面試頁仍可用純語音面試；面試頁右下角也有「純語音頁」連結，可改用 Pipecat 原本的 `/client` 頁。

### 共用筆記板

需要寫程式或畫架構時，另開 **http://localhost:7860/notepad**（設定頁上方的「共用筆記板」）。內容會在你下一次開口回答時傳給面試官，它會針對你寫的內容追問；面試結束時的最終內容也會記進逐字稿。

## 看延遲出在哪裡

`bot.py` 執行時，終端機每一輪都會印出延遲數據。各元件的延遲大概會落在：

- Whisper：GPU 上通常幾百毫秒
- Claude：首個 token 的時間，通常是最大的一塊
- Kokoro：GPU 上很快，通常不是瓶頸

如果 Kokoro 很慢，多半是它跑在 CPU 上，請參考下面的疑難排解。

## 疑難排解

**`bot.py` 啟動時停下來，說「The Claude Code CLI can't be used」：** 訊息會寫原因。「not found」：安裝 Claude Code，或在 `.env` 設 `CLAUDE_CODE_PATH`。「Not logged in」或驗證錯誤：執行 `claude` 登入。用量上限：等它重置、換小一點的模型（`LLM_MODEL=claude-sonnet-5-5`），或改用 `LLM_BACKEND=api`。

**出現 `libcudnn` 或 `libcublas` 找不到：** 這個終端機還沒跑 `source scripts/cuda_env.sh`。

**`scripts/download_models.py` 顯示 CUDAExecutionProvider 不存在：** 安裝環境裡同時有 CPU 版和 GPU 版的 onnxruntime。執行 `pip uninstall -y onnxruntime onnxruntime-gpu && pip install onnxruntime-gpu==1.24.4` 重裝。

**面試官一直打斷你：** 戴耳機。Smart Turn 會等你停頓思考，但如果喇叭的聲音被麥克風收進去，系統會以為你在講話。

**面試官等太久才回應：** 檢查延遲數據。如果是 Claude 太慢，參考參考手冊[調整設定](docs/reference.zh-TW.md#調整設定)裡「延遲還是太高」的做法。

**每次連線一開始都要等幾秒：** 這是正常的。每場開始時會重新載入 Whisper 和 Kokoro，模型已經下載過的話只要幾秒。

**面試官念出 `[time check]` 或 `[[END]]`：** 這不應該發生。請檢查 `prompts/interviewer.md` 裡 Timekeeping 和 Ending the interview 段落是否被改動。

**面試頁看不到面試官、只顯示錯誤訊息：** 先執行 `python scripts/download_models.py avatar` 下載頭像，再確認電腦連得到 cdn.jsdelivr.net。仍然不行就按「純語音頁」照常面試。

**面試官的嘴沒在動：** 確認 `web/vendor/headaudio/` 裡有三個檔案。耳機音量太小不影響嘴型，嘴型是從伺服器送來的語音算的。

**瀏覽器沒有詢問麥克風權限，或說麥克風無法使用：** 瀏覽器只允許 `http://localhost` 或 HTTPS 的網頁使用麥克風。`bot.py` 跑在另一台電腦上的話，用 SSH 通道開（`ssh -L 7860:localhost:7860 那台電腦`，再開 http://localhost:7860/），不要用 IP 位址開。

**網頁顯示「Only pages opened from this computer may use the interviewer」：** 伺服器只回應用 `localhost` 或 `127.0.0.1` 開的網頁，避免其他網站讀走你的履歷和逐字稿。如果確定要用別的位址開，把它加進 `.env` 的 `PIPECAT_ALLOWED_ORIGINS`，例如 `PIPECAT_ALLOWED_ORIGINS=http://192.168.1.5:7860`。

**Coding 模式說連不上 leetcode.com：** 題目第一次用到時從 LeetCode 抓，之後會快取在 `~/.cache/ai-interviewer/leetcode/`。檢查網路；用過的題目離線也能用。

**面試官道別後沒有掛斷：** 程式會在道別的語音播完後掛斷，最多再等 20 秒。如果完全沒掛斷，代表面試官沒有輸出結束標記，按設定頁的「結束並產生報告」即可。

---

面試資料夾怎麼寫、各項設定、中文面試、回饋報告與練習進度等其他內容，請看[參考手冊](docs/reference.zh-TW.md)。
