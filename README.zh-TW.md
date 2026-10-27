<p align="center">
  <img src="docs/readme/banner.jpg" alt="AI 模擬面試官：把面試先講一遍" width="100%">
</p>

<p align="center"><strong>開口練的模擬面試。</strong></p>

<p align="center">一位讀過職缺描述、你的履歷和這一關資訊的語音面試官。<br>它會提問、追問、控制時間，結束後寫回饋報告。除了語言模型，其他全部在你自己的 GPU 上執行。</p>

<p align="center">
  <a href="README.md">English</a> &nbsp;·&nbsp; <strong>繁體中文</strong>
</p>

<p align="center">
  <a href="#畫面">畫面</a> &nbsp;·&nbsp;
  <a href="#三種練習方式">三種練習方式</a> &nbsp;·&nbsp;
  <a href="#面試結束之後">面試結束之後</a> &nbsp;·&nbsp;
  <a href="#面試官會做什麼">面試官會做什麼</a> &nbsp;·&nbsp;
  <a href="#運作方式">運作方式</a> &nbsp;·&nbsp;
  <a href="#開始使用">開始使用</a> &nbsp;·&nbsp;
  <a href="INSTALL.zh-TW.md">安裝指南</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Linux%20%C2%B7%20WSL2-0a84ff?style=for-the-badge&logo=linux&logoColor=white" alt="Linux 或 WSL2">
  <img src="https://img.shields.io/badge/NVIDIA-CUDA%2012-76b900?style=for-the-badge&logo=nvidia&logoColor=white" alt="NVIDIA GPU，CUDA 12">
  <img src="https://img.shields.io/badge/Python-3.10%E2%80%933.12-3776ab?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10 到 3.12">
  <img src="https://img.shields.io/badge/Interviewer-Claude-d97757?style=for-the-badge&logo=claude&logoColor=white" alt="Claude">
  <img src="https://img.shields.io/badge/Interviews-EN%20%C2%B7%20%E4%B8%AD%E6%96%87-7048e8?style=for-the-badge" alt="英文 · 中文">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="MIT 授權"></a>
</p>

---

## 畫面

<p align="center"><img src="docs/readme/interview.jpg" alt="面試頁：3D 虛擬面試官、面試官問題的字幕，以及語音辨識聽到你說的話" width="100%"></p>

> repo 附的虛構範例 [`interviews/example/`](interviews/example/)，Acme Vision 的技術面試。面試官正要進入立體視覺的題目：它說話時問題會以字幕出現，下面一行是語音辨識聽到你說的話，聽錯了當場就看得到。這些畫面裡的候選人和分數都是虛構的。

---

## 讀過答案，不等於講得出來

答案你明明知道，到了現場還是會卡住：先講了一堆背景才講到重點、忘了講讓專案亮眼的那個數字、被一個沒料到的追問問倒。

解法是把答案講出來，講給一個會追問的人聽。這個專案就是那個人，面試前一晚凌晨一點也在。它讀過 JD、你的履歷和你手上這一關的資訊；你漏了數字，它會要數字；你跳過取捨，它會問「為什麼選這個、不選另一個」。它也記得你上次哪裡答不好，換個問法再考一次。

---

## 三種練習方式

<table>
  <tr>
    <td width="38%" valign="top">
      <img src="docs/readme/modes.jpg" alt="開始練習：選面試、練習方式、專項主題、教練模式，以及最近一場的分數">
    </td>
    <td valign="top">
      <h3>1. 完整面試</h3>
      從自我介紹一路到「你有什麼問題想問我們」，照這一關的結構進行。它會控制時間，時間到自己收尾。
      <h3>2. 專項練習</h3>
      針對一個主題練 10 到 30 分鐘，從基礎問到深入的追問。主題可以選上次報告建議加強的、評分標準裡的面向，或自己輸入。
      <h3>3. 教練模式</h3>
      每答完一題就停下來：先說哪裡答得好，再指出漏掉什麼，用你自己的經驗示範更好的講法，然後請你重答一次。
      <br><br>
      每一場都可以暫停；斷線了，之後也能接著同一場繼續。
    </td>
  </tr>
</table>

---

## 面試結束之後

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/readme/report.jpg" alt="回饋報告：逐題評等與參考答案"><br>
      <strong>大約一分鐘產生回饋報告。</strong><br>
      依這一關的評分標準打分，並引用你的原話當證據；最強與最弱的時刻；每一題的評等，加上一段你講得出口、只用你真實經歷寫成的參考答案；你還沒準備到的追問；回答長度、開口前停頓和語速。
    </td>
    <td width="50%" valign="top">
      <img src="docs/readme/progress.jpg" alt="練習進度：各面向的趨勢，以及每一場的分數"><br>
      <strong>看得到的進步。</strong><br>
      每個評分面向隨場次的趨勢，加上每一場的判定和下次該練的主題。這些主題會變成專項練習的建議；下一場開始前，面試官也會讀到你的弱點，換個問法再考。
    </td>
  </tr>
</table>

---

## 面試官會做什麼

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/readme/wizard.jpg" alt="新增公司或關卡：貼上 JD 和資訊，Claude 起草設定檔"><br>
      <strong>每家公司、每一關分開準備。</strong><br>
      貼上職缺描述和你知道的這一關資訊，Claude 會依 JD 和你的履歷起草這一關的說明、題庫、評分標準和語音辨識提示詞，檢查後按「建立」。每家公司可以用自己版本的履歷。
    </td>
    <td width="50%" valign="top">
      <img src="docs/readme/notepad.jpg" alt="共用筆記板裡的一小段程式"><br>
      <strong>它看得到你寫的東西。</strong><br>
      遇到寫程式或系統設計題，在面試頁旁邊打開共用筆記板。你下次開口時，面試官就會讀到你寫的內容，並針對特定幾行追問。
    </td>
  </tr>
  <tr>
    <td valign="top">
      <img src="docs/readme/interview-zh.jpg" alt="中文面試，字幕為中文"><br>
      <strong>英文或中文面試。</strong><br>
      設定 <code>interview_language: zh-TW</code>，面試就改用中文進行：繁體中文、台灣用語，技術名詞保留英文。語音辨識、聲音、字幕和報告都會一起切換。
    </td>
    <td valign="top">
      <strong>它像面試官，不像聊天機器人。</strong>
      <ul>
        <li>一次只問一題，用簡短的口語，不會每題都誇你。</li>
        <li>回答太籠統、只說「我們」卻沒說你做了什麼、或沒講結果時，它會追問。</li>
        <li>你停下來想的時候它會等（Smart Turn v3），不會搶話；你插話時它會停下來。</li>
        <li><code>difficulty: tough</code> 會讓它更常質疑你的推論，也一直追著要數字。</li>
        <li>3D 虛擬面試官在瀏覽器裡繪製，嘴型跟著聲音動。可以用內建聲音，或複製一段你有權使用的聲音。</li>
      </ul>
    </td>
  </tr>
</table>

---

## 運作方式

<p align="center"><img src="docs/readme/how-it-works.png" alt="運作方式：瀏覽器連到本機的 Pipecat 語音流程（VAD 與 Smart Turn、Whisper 或 Parakeet、Claude、Kokoro 或 Pocket TTS）；面試結束後，逐字稿變成回饋報告、練習進度和下一場要重考的弱點" width="100%"></p>

| 環節 | 用什麼 |
|---|---|
| 語音流程 | [Pipecat](https://github.com/pipecat-ai/pipecat) 1.12，透過 WebRTC |
| 判斷輪到誰說話 | Silero VAD + Smart Turn v3，本機執行 |
| 語音辨識 | Whisper large-v3（faster-whisper）或 NVIDIA Parakeet TDT 0.6B v3，本機 GPU。可以用 `compare_stt.py` 拿你自己的聲音比較 |
| 面試官 | Claude，預設透過你的 Claude Code 登入，也可以用 Anthropic API key |
| 聲音 | Kokoro（GPU）、Pocket TTS 內建或複製聲音（CPU）、中文用 Kokoro v1.1-zh |
| 虛擬面試官 | [TalkingHead](https://github.com/met4citizen/TalkingHead) 加 [HeadAudio](https://github.com/met4citizen/HeadAudio) 嘴型同步，在瀏覽器裡執行 |

---

## 開始使用

**需要**

- Linux，或 Windows 的 WSL2
- NVIDIA GPU，6 GB 以上 VRAM，驅動支援 CUDA 12
- Python 3.10 到 3.12
- 已登入的 **Claude Code**（或 Anthropic API key）
- 耳機，避免面試官聽到自己的聲音

**接著**

```bash
./setup_gpu.sh                  # 建 venv、安裝套件、換成 GPU 版 onnxruntime
source .venv/bin/activate
source cuda_env.sh              # 讓程式找得到 CUDA 函式庫，每開一個新終端機都要跑
python download_models.py       # 下載模型（約 4 GB）並檢查 GPU
python bot.py                   # 然後打開 http://localhost:7860/
```

選範例面試、選練習方式，按「前往面試」。完整步驟和疑難排解在 **[INSTALL.zh-TW.md](INSTALL.zh-TW.md)**，所有設定在 **[docs/reference.zh-TW.md](docs/reference.zh-TW.md)**。

要準備真正的面試，在設定頁用「新增公司或關卡」，或複製 [`interviews/_template/`](interviews/_template/)。你自己的公司資料夾、履歷、逐字稿和錄音都在 `.gitignore` 裡，只會留在你的電腦上。

---

## 隱私與費用

- **會離開你電腦的東西**：只有送給 Claude 的文字，也就是面試設定檔和面試中的對話，以及寫回饋報告時的逐字稿。你的聲音和存下來的錄音都留在本機。
- **費用**：預設的 Claude Code 模式用的是你的 Claude 方案，會算進方案的用量額度；改成 `LLM_BACKEND=api` 則依 Claude API 價格按 token 計費。其他部分都免費、在本機執行。

## 已知限制

- 網頁介面只有繁體中文；面試本身可以是英文或中文。
- 在 WSL2（Ubuntu）加 NVIDIA GPU 上開發與測試，一般 Linux 應該一樣可用。不支援原生 Windows 和 macOS。
- 中文聲音是大陸口音，英文術語念得比較不自然，這是目前本機輕量模型的限制。
- 每輪時間是近似值，Whisper 也會濾掉部分「呃」「嗯」，所以贅字只能粗略判斷。
- 複製聲音時，只能用你有權使用、本人同意的聲音。

---

## 文件

- [INSTALL.zh-TW.md](INSTALL.zh-TW.md)：需求、安裝、第一場面試、疑難排解。
- [docs/reference.zh-TW.md](docs/reference.zh-TW.md)：面試資料夾、回饋報告與練習進度、斷線後接續、所有設定、中文面試、語音辨識模型，以及程式架構。

<details>
<summary><strong>程式架構</strong></summary>

```text
bot.py                語音 pipeline 主程式：計時、結束流程、專項練習與教練模式、筆記板
session_picker.py     網頁和它的 API
claude_code_llm.py    透過 Claude Code CLI 呼叫面試官，CLI 當掉時自動恢復
whisper_stt.py        Whisper 語音辨識：帶入對話上下文、過濾幻覺片段
parakeet_stt.py       Parakeet 語音辨識：每段回答結束後整段重新辨識
compare_stt.py        用你自己的錄音比較語音辨識模型
chinese.py            中文文字處理：轉繁體、空格與標點、字數
chinese_tts.py        中文面試官的聲音（Kokoro v1.1-zh）
feedback.py           回饋報告和分數
analysis.py           回答長度、停頓、語速
history.py            跨場次的弱點與問過的題目、進度資料
interview_config.py   載入面試資料夾、設定檢查、填入 prompt 模板
setup_wizard.py       新增公司或關卡：草稿與建立
resume_import.py      把上傳的履歷轉成 resume.md
prompts/              面試官、回饋報告、履歷轉換、新增關卡的 prompt 模板
interviews/           每家公司一個資料夾，每一關一個子資料夾
web/                  設定頁、面試頁、報告頁、進度頁、筆記板
tests/                自動化測試（不需要 GPU、網路或 Claude）
```

</details>
