# 參考手冊

[English](reference.md) · **繁體中文** · [← 回到 README](../README.zh-TW.md)

安裝和第一場面試的步驟請看[安裝與第一場面試](../INSTALL.zh-TW.md)。

- [架構](#架構)
- [準備面試](#準備面試)
  - [更新履歷](#更新履歷)
- [Coding 面試](#coding-面試)
  - [題目從哪裡來](#題目從哪裡來)
- [回饋報告與練習進度](#回饋報告與練習進度)
- [斷線後接續](#斷線後接續)
- [調整設定](#調整設定)
- [開發](#開發)
- [專案結構](#專案結構)
- [已知限制](#已知限制)

## 架構

全本機自架的語音面試官。你用瀏覽器跟它講話，它會根據 JD 和你的回答即時追問，結束後產生回饋報告，並記住你的弱點，下一場刻意再考。

```
瀏覽器 (麥克風/喇叭)          http://localhost:7860/  設定頁：選面試、專項練習、接續、報告、進度、履歷、新增關卡
   ⇅ WebRTC                  http://localhost:7860/interview  面試頁：虛擬面試官、即時字幕
bot.py (Pipecat 1.12.0)
   ├─ Silero VAD + Smart Turn v3   本機，判斷你講完了沒、處理打斷
   ├─ Whisper large-v3 或 Parakeet 本機 GPU，語音轉文字
   ├─ Claude Opus 5.5               面試官大腦，預設透過 Claude Code CLI（不需要 API key）
   ├─ Kokoro 或 Pocket TTS          文字轉語音：Kokoro 內建聲音（GPU），或 Pocket TTS 複製聲音（CPU）
   └─ transcripts/                  逐字稿、回饋報告、分數
```

除了 Claude，其他元件全部在你的電腦上執行。

## 準備面試

repo 附了一個虛構的範例 [`interviews/example/`](../interviews/example/)（Acme Vision 電腦視覺工程師的技術面試），clone 下來就能直接試跑，也可以照著它的格式寫你自己的。你自己建立的公司資料夾只會留在本機，`.gitignore` 只追蹤 `_template/` 和 `example/`。

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

**用網頁建立（建議）**：設定頁右邊的「新增公司或關卡」分頁，貼上 JD 和你知道的這一關資訊（HR 的說明、面試官背景），按「產生草稿」。Claude 會依 JD 和你的履歷起草 round_info、題庫、評分標準、公司資訊和 Whisper 提示詞，檢查修改後按「建立」。選既有公司的話，只會新增一關，沿用公司的 JD 和設定。

**手動建立**：複製[範本](../interviews/_template/)，再把 `round1` 改成關卡名稱：

```bash
cp -r interviews/_template interviews/acme
mv interviews/acme/round1 interviews/acme/tech
```

**檔案的查找順序**：先找這一關的資料夾，再找公司資料夾，履歷最後才用 `profile/resume.md`。任何檔案都可以放在關卡資料夾裡覆蓋公司的版本。兩層的 `stt_hotwords` 會合併。

**設定檢查**：設定頁會列出每一場的問題。錯誤（例如少了面試官名字、YAML 打錯、時長不是數字）要修正才能開始；提醒（例如沒有 rubric.md）不影響開始，但報告會比較不準。`bot.py` 啟動時也會在終端機印出。

名稱以 `_` 開頭的資料夾（例如 `_template`）不會出現在選單裡。網頁上預設選的面試可以用 `python bot.py --interview acme/tech` 或 `.env` 的 `INTERVIEW=acme/tech` 指定；公司只有一關時寫公司名稱就好。

`stt_hotwords` 很值得花時間填：把 JD 裡的專有名詞、產品名、縮寫列進去，Whisper 會比較容易聽對。只放真的容易聽錯的詞：清單越長，Whisper 在聽不清楚時越容易把清單本身念出來（程式會把「連續三個詞照清單順序出現」的片段濾掉）。

### 更新履歷

在設定頁右邊的「履歷」分頁按「上傳新履歷」，選 PDF、Word（.docx）、.txt 或 .md 檔。系統會擷取文字，再請 Claude 整理成 `resume.md` 的格式（不改任何內容，只修復斷行和欄位順序，聯絡方式會拿掉），約需半分鐘到一分鐘。檢查或修改後選擇存放位置：這家公司的所有關卡（上傳時的預設）、只用在這一關、或所有公司共用（`profile/resume.md`）。舊版本會備份到 `profile/backups/`。也可以按「編輯目前履歷」直接改。掃描成圖片的 PDF 讀不到文字，請改傳 Word 或文字檔；.md 檔會直接使用。

### 客製化一關

建立之後，每一關的所有內容都能修改，不用動程式。

- **在網頁上改：** 設定頁的「編輯這一關」分頁可以編輯目前選的這一關：設定（`config.yaml`）、round_info、題庫、評分標準、JD、公司資訊、公司設定，以及下面的三個 prompt。儲存時會先檢查（YAML 格式錯誤或壞掉的 prompt 會被擋下），舊版本存到 `profile/backups/`，並顯示這一關還有哪些設定問題。下一場面試開始生效。
- **聲音和頭像：** 精靈會依面試語言列出幾種聲音，頭像有 `david`（男性外觀）和 `brunette`（女性外觀）兩種。`config.yaml` 的 `voice` 可以填任何會說這個語言的 Kokoro 聲音；`avatar` 可以是 `web/avatars/` 裡任何有 ARKit 和 Oculus viseme 表情的 GLB（`avatar_body` 設 `M` 或 `F` 配合）。
- **Coding 預設：** 在關卡的 `config.yaml` 預設這一關的 Coding 條件，設定頁選這一關時會自動帶入。每一項都可以省略，頁面上也還能再改：

  ```yaml
  coding:
    language: cpp            # python 或 cpp
    difficulties: [medium, hard]
    tags: [graph, tree]      # LeetCode 標籤的 slug
    minutes: 45              # 15、30、45 或 60
    rating: [1600, 2000]     # [下限, 上限]；不限的一邊寫 null
    statement: interview     # interview 或 leetcode
    interview_only: true
  ```

- **換掉 prompt：** 想改某一關（或整家公司）的面試官行為、報告寫法或 Coding 評分標準，就在那裡的 `prompts/` 資料夾放同名檔案：`interviews/acme/tech/prompts/interviewer.md`、`feedback.md` 或 `coding_rubric.md`（放在公司資料夾 `interviews/acme/prompts/` 就套用到每一關）。可以從 [`prompts/`](../prompts/) 複製共用版本來改，或直接用編輯分頁，它會顯示共用版本。自訂的 `interviewer.md` 必須保留 `{{session_mode}}` 和 `[[END]]` 的說明，程式靠它們帶入練習方式和自動掛斷；少了的話設定檢查會擋下來。大部分需求其實寫進 `round_info.md` 就夠了。

## Coding 面試

在設定頁的「練習方式」選 **Coding**，再設定：

- **語言和時間**：Python 或 C++；15、30、45 或 60 分鐘。15 分鐘只考一題，結尾也不留時間讓你提問；第二題要剩 15 分鐘以上才會出，所以只有較長的 session 才會遇到。
- **題目呈現**：
  - **面試風格**（預設）比較接近真實面試。筆記板上是一小段說清楚要解什麼的描述，加上一到兩個範例，就像面試官寫在共用文件上的題目。限制條件、輸入大小、題目保證（例如「答案一定存在」）、邊界情況的規定和 follow-up 都不寫，tags、rating 和 LeetCode 連結也會隱藏，因為 tags 等於直接告訴你解法方向。
  - 有疑問就直接問，或說出你的假設請面試官確認。面試官手上有完整原題和省略清單，你問到的會照實回答，沒問到的不會主動說；漏問重要條件的話，測試階段會被特定輸入追問。
  - 這個版本由 Claude 改寫，每題只在第一次使用時改寫一次，約十秒；改寫失敗時，會改成顯示 LeetCode 的描述和前兩個範例，拿掉限制條件。
  - **LeetCode 原題**：跟以前一樣顯示完整題目和限制。
- **難度**：Easy、Medium、Hard 可以複選，例如只勾 Medium 和 Hard。
- **只出面試常見題**（預設勾選）：只出考演算法、資料結構，而且評價好的題目。會排除這三類：
  - 好評率低於 75% 的題目，例如 Divisor Game、String to Integer。
  - 競賽才考的題型：腦筋急轉彎、博弈、數論、組合數學、機率、幾何、網路流、後綴結構等。
  - 只標了 Array、String、Math、Simulation、Enumeration、Counting、Matrix 的題目，這類大多是照題意模擬。不過 Rotate Image、Spiral Matrix 這類很熱門的經典題會保留。

  規則寫在 `interviewer/leetcode.py` 的 `interview_style`。取消勾選就會從全部免費題目裡挑。
- **Rating**（選填）：題目的難度分數（[zerotrac/leetcode_problem_rating](https://github.com/zerotrac/leetcode_problem_rating)，約 1100–3100）。只有週賽、雙週賽的題目才有 rating，所以填了範圍就只會出這些題目；下限或上限可以只填一個。
- **題型**：LeetCode 的標籤，例如 Graph、Tree、Linked List，可以複選，符合任一個就算；不選表示不限。預設列出最常見的 36 個，其他可以按「顯示全部」或用搜尋框找。

下方會即時顯示符合條件的題數和幾個例子。按「前往面試」時會從符合的題目裡挑兩題（第一題和備用題），挑不到或連不上 LeetCode 會直接在這裡顯示錯誤。Coding 面試沿用你選的那一關的面試官和聲音，但不看履歷和題庫，只考演算法題。

1. 按「前往面試」後，在面試頁點「打開題目與程式區」，把它跟面試頁並排放，再按「開始面試」。
2. 第一題會顯示在左邊（面試風格是簡短版；LeetCode 原題模式是原本的題目，附原題連結），右邊是 LeetCode 的程式範本。Tab 縮排四格，Enter 會保留縮排。
3. 邊寫邊講。你停止打字 2.5 秒後程式碼會同步，面試官在你下一次開口時讀到最新版本。
4. 程式不能執行，請用範例自己走一遍。面試官會照「確認需求 → 解法與複雜度 → 寫程式 → 測試 → 延伸題」的順序進行；你卡住時，他會一次給一層提示。
5. 第一題做完、而且剩下 15 分鐘以上，他會換第二題，程式區會自動切換。每一題的程式碼分開保存。

報告用 coding 專用的評分標準（[prompts/coding_rubric.md](../prompts/coding_rubric.md)）：釐清問題、解題思路、程式實作、溝通表達、測試與除錯、複雜度分析。每一題會比較你的解法和最佳解法、指出程式碼裡的 bug，並附上參考解法和可以怎麼口頭說明。面試風格的題目還會列出你問了哪些釐清問題、漏了哪些重要的。Coding 的分數不會混進一般面試的進度圖，在「練習進度」頁點「看 Coding 面試的進度」查看。

### 題目從哪裡來

題目即時從 LeetCode 抓取，不需要維護題庫。只會出免費的演算法題，付費題和沒有 Python 或 C++ 範本的題目會跳過；這一關做過的題目排在後面，第二題盡量和第一題不同題型。LeetCode 多數題目沒有公開的解法，所以提示階梯、最佳解和延伸題由面試官（Claude）依題目自己準備，LeetCode 有提供提示時也會一併參考。

抓下來的資料快取在 `~/.cache/ai-interviewer/leetcode/`（可用環境變數 `LEETCODE_CACHE_DIR` 改位置）：題目清單和 rating 每 7 天更新一次，用過的題目和它的面試風格版本（`statements/`）永久保存，所以接續中斷的面試或重新產生報告時不需要網路。連不上網路時會沿用舊的清單。題目內容只供你個人練習使用，適用 LeetCode 的使用條款。

## 回饋報告與練習進度

每場結束後，`transcripts/<公司>/<關卡>/` 會有三個檔案：

| 檔案 | 內容 |
|---|---|
| `*-transcript.md` | 逐字稿，含每一輪的開始時間和長度 |
| `*-feedback.md` | 回饋報告：依評分標準打分、最強與最弱的時刻、**逐題回顧和英文參考答案**、該準備的追問、表達分析（回答長度、開口前停頓、語速）、總體判定 |
| `*-scores.json` | 結構化分數：各面向分數、弱點、問過的題目、下次建議練的主題 |

- **學習循環**：下一場開始時，面試官會讀到之前幾場的弱點和問過的題目，換個問法重考弱點、避開重複題，但不會跟你提起之前的練習。
- **練習進度**：設定頁上方的「練習進度」顯示各面向分數隨場次的趨勢，以及每一場的判定和建議主題。
- **補產生報告**：沒有報告的逐字稿（例如中途斷線又不想接續），在設定頁「練習紀錄」那一列按「產生報告」。也可以用指令（重新產生已有的報告也用這個）：

```bash
python -m interviewer.feedback transcripts/example/tech/20261101-1930-transcript.md
python -m interviewer.feedback --scores-only transcripts/example/tech/*-transcript.md   # 從舊報告補出分數，不重寫報告
```

## 斷線後接續

網路斷掉、不小心關掉網頁，或想中途休息，都可以接著同一場繼續：

- **`bot.py` 還開著**：不到一半時間就斷線的話，在面試頁再按一次「開始面試」就會接續。要接續其他逐字稿，回到設定頁選那一份。
- **`bot.py` 已經關掉**：重新執行 `python bot.py`，在設定頁選要接續的逐字稿，或直接下 `python bot.py --resume transcripts/example/tech/20261101-1930-transcript.md`。

連線後面試官會簡短歡迎你回來，不會重新自我介紹，從中斷的地方繼續；上一題沒答完就重問。計時接著上次的進度算，逐字稿寫回同一個檔案。

結束方式決定會不會產生報告：面試官道別、或你按了「結束並產生報告」，一定會產生；直接斷線的話，超過一半時間才產生，不到一半則當成斷線，下一次按「開始面試」會自動接續。

## 調整設定

**聲音：** 在 `config.yaml` 修改 `voice`。美式男聲有 `am_michael`、`am_adam`、`am_eric`、`am_liam`、`am_onyx`、`am_fenrir`、`am_puck`、`am_echo`。英式男聲有 `bm_george`、`bm_lewis`、`bm_daniel`、`bm_fable`，用英式聲音時要把 `voice_language` 改成 `en-gb`。

**用誰的 Claude：** `.env` 的 `LLM_BACKEND=claude_code`（預設）會用你 Claude Code 的登入身分，不需要 API key，會自動找 PATH 上的 `claude` 或 VS Code 擴充套件內建的那份，找不到就設 `CLAUDE_CODE_PATH`。每輪第一個字約 2–3 秒。如果 CLI 在面試中當掉或超過 60 秒沒有回應，面試官會先說「Sorry, give me just a second」（中文面試是「不好意思，請稍等一下」），重新啟動 CLI、帶入目前為止的對話後再試一次。`bot.py` 啟動時會先確認 CLI 能回應，不行就停下來並說明原因。這個模式會忽略 `.env` 裡的 `ANTHROPIC_API_KEY`，一定用你的登入身分。改成 `LLM_BACKEND=api` 就走 `ANTHROPIC_API_KEY`。

**其他模型（OpenAI 相容）：** `LLM_BACKEND=openai` 讓面試官、報告和草稿改用任何 OpenAI 相容的 API。要設 `LLM_MODEL`（必填），用 OpenAI 就設 `OPENAI_API_KEY`，用本機伺服器就設 `OPENAI_BASE_URL`，例如 Ollama 是 `http://localhost:11434/v1`、LM Studio 是 `http://localhost:1234/v1`。時間提醒和筆記板更新會以 user 訊息送出，不支援 `developer` 角色的伺服器也能用。prompt 是針對 Claude 寫和測試的；其他模型（特別是小型本機模型）在掌握時間、自動掛斷上可能比較不可靠，而且這條路徑是用模擬伺服器測的，沒有接過真正的模型。

**沒有 NVIDIA GPU：** 設 `WHISPER_DEVICE=cpu`、較小的 `WHISPER_MODEL`（`small` 或 `medium`），並拿掉 `ONNX_PROVIDER`，詳見[沒有 GPU 的跑法](../INSTALL.zh-TW.md#沒有-gpu-的跑法)。Whisper 會自動改用 int8，除非 `WHISPER_COMPUTE_TYPE` 另外指定。

**從另一台電腦開網頁：** 伺服器只回應用 `localhost` 或 `127.0.0.1` 開的網頁，避免瀏覽器裡其他網站讀走你的履歷和逐字稿，或替你開始面試。要允許其他位址，把它寫進 `PIPECAT_ALLOWED_ORIGINS`，例如 `PIPECAT_ALLOWED_ORIGINS=http://192.168.1.5:7860`。麥克風仍然只能在 `localhost` 或 HTTPS 下使用，所以通常用 SSH 通道（`ssh -L 7860:localhost:7860 host`）比較簡單。

**Pocket TTS（內建聲音或複製聲音）：** 第一次使用要先到 https://huggingface.co/kyutai/pocket-tts 同意條款，再在 venv 裡執行 `hf auth login`，並安裝 `requirements.txt` 最後註解裡的 pocket-tts。Pocket TTS 跑在 CPU 上，每場開始時會多花約 10 秒載入。

- **內建聲音**：`config.yaml` 設 `pocket_voice: stuart_bell`。英文男聲有 `stuart_bell`、`javert`、`michael`、`paul`、`charles`、`george`、`jean`、`marius`、`peter_yearsley`、`bill_boerst`；女聲有 `alba`、`anna`、`vera`、`fantine`、`eponine`、`azelma`、`mary`、`jane`、`eve`、`caro_davy`、`cosette`。實測以 `stuart_bell`、`javert` 最清楚。
- **複製聲音**：只能用本人同意使用的聲音。準備一段 10–20 秒、只有一個人說話、沒有背景音樂的 `.wav`，放在關卡資料夾的 `voice/` 裡，`config.yaml` 設 `voice_clone: voice/xxx.wav`（會優先於 `pocket_voice`）。**錄音的音質會被一起複製**：電話、視訊會議或壓縮過的影片音訊頻寬很窄，複製出來的聲音會悶悶的。請用原始音質、寬頻（16 kHz 以上）的錄音。

**中文面試：** 在關卡的 `config.yaml`（或整家公司共用的 `company.yaml`）加上 `interview_language: zh-TW`，或在「新增公司或關卡」精靈把面試語言選成中文。中文面試會：

- 面試官用繁體中文、台灣用語提問，技術名詞保留英文（例如「你為什麼把 GRU 換成 MLP？」）。
- 語音辨識固定用 Whisper（Parakeet 不支援中文），辨識結果轉成繁體與台灣用語，例如「項目」轉成「專案」。
- 聲音改用 Kokoro v1.1-zh 中文模型，預設 `voice: zm_010`。男聲是 `zm_*`、女聲是 `zf_*`，各有幾十種可以試。Pocket TTS 不會說中文，所以 `voice_clone`、`pocket_voice` 會被忽略。第一次使用時會自動下載模型（約 380 MB），也可以先執行 `python scripts/download_models.py chinese`。
- 字幕逐字顯示，回饋報告和參考答案改用中文，語速改成「每分鐘幾個字」（一個中文字或一個英文單字算一個）。

中文聲音是大陸口音，英文術語念得普通，是目前本機輕量模型的限制。

**其他面試語言：** `interview_language` 也可以是日文、西班牙文、法文、義大利文、巴西葡萄牙文和印地文。面試官會用那個語言說話（技術名詞保留英文），Whisper 會用那個語言辨識，報告預設也用那個語言。

| `interview_language` | 預設聲音 | 其他聲音 | 備註 |
|---|---|---|---|
| `ja`（日文） | `jm_kumo` | `jf_alpha`、`jf_gongitsune`、`jf_nezumi`、`jf_tebukuro` | 發音透過 misaki 和 pyopenjtalk（已在 `requirements.txt`；`python scripts/download_models.py japanese` 會先下載 22 MB 的字典）。英文術語會帶日文腔。 |
| `es`（西班牙文） | `em_alex` | `ef_dora` | |
| `fr`（法文） | `ff_siwis` | | Kokoro 只有一個法文聲音。 |
| `it`（義大利文） | `im_nicola` | `if_sara` | |
| `pt-BR`（巴西葡萄牙文） | `pm_alex` | `pf_dora` | |
| `hi`（印地文） | `hm_omega` | `hm_psi`、`hf_alpha`、`hf_beta` | |

Parakeet 懂英文、西班牙文、法文、義大利文和葡萄牙文；其他語言就算設了 `STT_BACKEND=parakeet` 也會改用 Whisper。Pocket TTS 只會說英文。英文和中文測得最多；其他語言用「把面試官的聲音交給 Whisper 聽回來」確認過，日文和西班牙文也跑過完整面試。

**面試官搶話：** `.env` 的 `CANDIDATE_PAUSE_SECS`（預設 0.8）是你停頓多久之後才開始判斷你講完了沒。還是會被打斷就調高，嫌回應慢就調低。

**語音辨識模型：** `.env` 的 `STT_BACKEND` 可以選兩種，都在本機 GPU 上跑：

| | `whisper`（預設） | `parakeet` |
|---|---|---|
| 模型 | Whisper large-v3（faster-whisper） | NVIDIA Parakeet TDT 0.6B v3（onnx-asr） |
| 速度 | 一段約 0.5 秒 | 一段約 0.07 秒 |
| 專有名詞 | 可以用 `stt_hotwords` 提示 | 不支援提示，辨識後再依 `stt_hotwords` 修正拼寫（例如 tensor RT → TensorRT） |
| 逐字稿 | 每段停頓分開辨識 | 每段回答結束後，再把整段一次重新辨識，前後文完整 |

Parakeet 在 Open ASR Leaderboard 上比 Whisper large-v3 準，但排行榜測的大多是母語者的英文，帶口音時哪個比較準要用你自己的聲音實測：

1. `.env` 設 `SAVE_CANDIDATE_AUDIO=true`，正常面試一場。每段回答的錄音會存在逐字稿旁的 `*-audio/` 資料夾（只在本機，不會上 git）。
2. 執行 `python scripts/compare_stt.py transcripts/<公司>/<關卡>/<時間>-transcript.md`，會把每段回答分別交給 Whisper 和 Parakeet，產生 `*-stt-compare.md`，並排列出兩個模型和面試中即時辨識的結果。也可以在網址列打開 `/report?interview=<公司>/<關卡>&file=<時間>-transcript.md&kind=stt` 看。
3. 選比較貼近你實際說的話的那個，設成 `STT_BACKEND`。第一次用 Parakeet 前先執行 `python scripts/download_models.py parakeet`（約 2.5 GB）。

Whisper 的細節：`interviewer/speech/whisper_stt.py` 會把面試官剛問的問題和你前面講的話當成提示；信心太低、在念 hotwords 清單、或照抄提示的片段會被丟掉，終端機會印出 `Dropped Whisper segment`。如果真的講過的話被丟掉，把 `.env` 的 `WHISPER_MIN_AVG_LOGPROB` 調低（例如 `-1.3`）。嫌慢可以把 `WHISPER_MODEL` 改成 `deepdml/faster-whisper-large-v3-turbo-ct2`。

**難度：** `difficulty: tough` 會讓面試官更常質疑你的推論，也會追著要數字。

**追問深度和速度的取捨：** 在 `.env` 設定 `INTERVIEWER_THINKING=adaptive`（只對 `LLM_BACKEND=api` 有效），Claude 會先思考再回應，追問更犀利，但每輪會多等幾秒。

**延遲還是太高：** 可以把 `LLM_MODEL` 換成 `claude-sonnet-5-5`，即時對話用比較快的模型。`FEEDBACK_MODEL` 維持 `claude-opus-5-5`，負責回饋報告、履歷轉換和新增關卡的草稿。

## 開發

```bash
python -m pytest             # 自動化測試，不需要 GPU、網路或 Claude
```

專案用 git 管理。`transcripts/`、`profile/`、各公司資料夾裡的 `resume.md` 和 `voice/` 都是個人資料，已列入 `.gitignore`，不會被提交。

## 專案結構

```
bot.py                 即時語音面試，執行這個（python bot.py）
interviewer/           程式本體（Python 套件）
  server.py            網頁和它的 API
  config.py            載入面試資料夾、設定檢查、填入 prompt 模板
  settings.py          每個程式共用的 .env 載入；設定裡的相對路徑以專案資料夾為準
  transcript.py        寫入與讀回逐字稿
  feedback.py          回饋報告和分數（面試結束自動執行，或 python -m interviewer.feedback）
  analysis.py          從每輪時間算出回答長度、停頓、語速
  history.py           跨場次的弱點、問過的題目、進度資料
  coding.py            Coding 面試：挑題、換題、面試官和報告的說明
  leetcode.py          從 LeetCode 抓題目和 zerotrac 的 rating，快取在本機
  claude_code.py       透過 Claude Code CLI 呼叫面試官，CLI 當掉時自動恢復
  llm.py               報告、履歷轉換、草稿、題目改寫共用的一次性 Claude 呼叫
  setup_wizard.py      新增公司或關卡：草稿與建立
  resume_import.py     把上傳的履歷轉成 resume.md
  speech/
    whisper_stt.py     Whisper：帶入對話上下文、過濾幻覺片段、輸出繁體
    parakeet_stt.py    Parakeet：每段回答結束後整段重新辨識
    stt_common.py      兩種辨識共用：回答音訊、專有名詞修正、Parakeet 下載
    chinese.py         中文文字處理：轉繁體、空格與標點、字數
    chinese_tts.py     中文面試官的聲音（Kokoro v1.1-zh）
scripts/
  setup_gpu.sh         一次性安裝：venv、套件、GPU 版 onnxruntime
  cuda_env.sh          讓 pip 裝的 CUDA 函式庫被找到（每個終端機 source 一次）
  download_models.py   下載模型並檢查 GPU
  compare_stt.py       用你自己的錄音比較語音辨識模型
web/                   設定頁、面試頁、報告頁、進度頁、筆記板
prompts/               prompt 模板：面試官、報告、Coding、履歷、新增關卡
interviews/            每家公司一個資料夾、每一關一個子資料夾；_template/ 和 example/ 會進 git
profile/               你的通用履歷（不進 git）
transcripts/           逐字稿、報告、分數，依面試分資料夾（不進 git）
tests/                 自動化測試（不需要 GPU、網路或 Claude）
```

## 已知限制

- 完整的即時語音對話（含自動掛斷、筆記板傳給面試官、CLI 當掉後恢復）需要麥克風和瀏覽器，只能在你自己的機器上實際驗證；各元件和網站 API 都有測過。
- 每輪時間是近似值：回答的結束時間包含約一秒的「判斷你講完了沒」。Whisper 會濾掉部分 uh、um，所以贅字數量只能從逐字稿粗略判斷。
- 複製聲音（Pocket TTS）請只使用你有權使用、本人同意的聲音。
