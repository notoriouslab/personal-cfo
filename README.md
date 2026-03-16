# personal-cfo

> [English README](README.en.md)

**Reference implementation** — 展示非專業投資人如何用確定性運算做退休軌道監控。

銀行帳單進，財務報表出，資料留在本地。Fork 後依照你的情況改 `config.yaml` 就能用。

**需要 Python 3.9+** · 屬於 notoriouslab 開源工具組的一員。

任何 AI agent 框架都可以透過 shell 呼叫，附帶 `SKILL.md` 讓 [OpenClaw](https://openclaw.ai/) 直接整合使用。

## 這不是什麼

- 不是交易工具，不會叫你買賣
- 不是 SaaS，沒有資料庫，不需要帳號
- 不是開箱即用的 app — 你需要懂 CLI，需要自己設定分類規則

## 這是什麼

一個月度財務體檢的 **框架和範本**。它展示了一種方法論：

| 特色 | 說明 |
|------|------|
| 事後審計 | 用上個月的銀行帳單，100% 客觀，沒有預測 |
| 確定性運算 | Python 算數字，零幻覺，不靠 AI 猜 |
| 退休滑行路徑 | 隨年齡自動降低股票比例的 glide path，偏離時才提醒 |
| 反噪音 | 在軌道上時保持安靜，不製造焦慮 |
| 多格式輸入 | CSV、doc-cleaner 的 Markdown+JSON、手寫 pipe table |
| 多幣別支援 | 靜態匯率設定，支援 USD/JPY/CNY/AUD 等 |
| 原子寫入 | 臨時檔 + `os.replace()`，不會產出半殘報告 |
| 離線模式 | `--offline` 跳過網路，用快取或硬編碼市場數據 |

每個人的財務狀況不同。這個工具給你一個起點和思考框架 — 你可以（也應該）根據自己的情況修改分類規則、資產配置、退休參數。

## 它產出什麼

- **損益表** (8 大類 P&L)
- **資產負債表** (依風險桶位分類)
- **現金流量摘要** (營運收支)
- **市場定錨** (全球指標作為背景參考)
- **退休滑行路徑診斷** (你的退休計畫在軌道上嗎？)

參見 `examples/sample_output/` 的完整報告範例：

![損益表 — 經常性收支分類](examples/sample_output/2026-03-16-01.png)

![關鍵指標、現金流量、市場定錨](examples/sample_output/2026-03-16-02.png)

![退休滑行路徑診斷](examples/sample_output/2026-03-16-03.png)

## 管道

懶人理財三部曲的第三環（每個工具可獨立使用）：

```
gmail-statement-fetcher  →  doc-cleaner  →  personal-cfo
(從 Gmail 下載帳單 PDF)    (PDF → Markdown)   (計算財務報表)
```

| 環 | 輸入 | 輸出 | 獨立使用 |
|----|------|------|----------|
| [gmail-statement-fetcher](https://github.com/notoriouslab/gmail-statement-fetcher) | Gmail | PDF | ✅ |
| [doc-cleaner](https://github.com/notoriouslab/doc-cleaner) | PDF/DOCX/XLSX | Markdown + JSON | ✅ |
| **personal-cfo** | CSV 或 Markdown+JSON | 財務報表 + 快照 | ✅ |

## 快速開始

```bash
git clone https://github.com/notoriouslab/personal-cfo.git
cd personal-cfo

# 安裝核心依賴（只需 pyyaml）
pip install -r requirements.txt

# 可選：安裝即時市場數據（yfinance）
pip install -r requirements-full.txt

# 複製設定範本並編輯你的參數
cp config.example.yaml config.yaml

# 用範例資料試跑
python -m personal_cfo cfo \
  --transactions ./examples/sample_transactions.csv \
  --assets ./examples/sample_assets.csv \
  --period 2026-01 --offline

# 月度審計（使用 doc-cleaner 的 Markdown 輸出）
python -m personal_cfo cfo \
  --transactions ./statements/ \
  --period 2026-01 \
  --offline

# 月度審計（自己寫的 Markdown 表格）
python -m personal_cfo cfo \
  --transactions ./my_statement.md \
  --period 2026-01 --offline

# 退休軌道檢查（使用已儲存的快照）
python -m personal_cfo track --snapshots ./output/snapshots/
```

## 輸入格式

### CSV（通用）
```csv
date,description,amount,currency,category,account
2026-01-05,Salary,150000,TWD,salary,Bank_A
2026-01-10,Mortgage,-25000,TWD,housing,Bank_B
```

### Markdown + JSON（doc-cleaner 管道）
讀取嵌入在 Markdown 文件中的 `STRUCTURED_DATA` JSON 區塊。信用卡檔案（檔名包含 `信用卡` 或 `credit`）會自動翻轉金額正負號。

**Cross-reference 模式：** 即使 JSON 有 `transactions[]`，parser 仍會比對 `refined_markdown` 的 pipe table，自動補漏（AI 生成的 JSON 不完整時）並從備註欄豐富描述。

### 純 Markdown（手寫或任何來源）
任何含 pipe table 的 `.md` 檔案都能直接使用，不需要特殊格式。Parser 透過欄位名稱（日期、摘要/說明、金額/支出/存入）自動辨識交易表。參見 `examples/sample_statement.md`。

## 設定

參見 `config.example.yaml` 取得所有選項。主要區塊：

| 區塊 | 用途 |
|------|------|
| `life_plan` | 出生年、退休年齡 |
| `glide_path` | 股票目標比例、年度遞減率、漂移閾值 |
| `manual_assets` | 不在銀行帳單中的資產（不動產等） |
| `category_rules` | 關鍵字 → 分類映射（**順序敏感**，精確的放前面） |
| `annual_expenses` | 年度費用（保險、稅），自動除以 12 計入每月損益 |
| `fx_rates` | 靜態匯率（格式：`USD_TWD: 32.0`） |

## CLI 選項

```
python -m personal_cfo cfo --help
python -m personal_cfo track --help
```

| 選項 | 說明 |
|------|------|
| `--transactions`, `-t` | 交易 CSV、Markdown 檔案或目錄 |
| `--assets`, `-a` | 資產 CSV（可選） |
| `--period`, `-p` | 期間標籤（如 `2026-01`） |
| `--config`, `-c` | 設定檔路徑（預設 `config.yaml`） |
| `--output`, `-o` | 輸出目錄 |
| `--offline` | 跳過網路（使用快取或硬編碼市場數據） |
| `--quiet`, `-q` | 只儲存檔案，不輸出到終端 |

## 使用情境範例

`examples/` 目錄包含不同生命階段的設定範本和完整的對帳單範例：

**設定範本：**

| 範本 | 情境 | 重點 |
|------|------|------|
| `config_young_professional.yaml` | 30 歲單身上班族 | 高股票比、低風險容忍、簡單分類 |
| `config_mid_career_family.yaml` | 42 歲雙薪家庭 | 房貸、保險、子女教育支出 |
| `config_pre_retirement.yaml` | 56 歲接近退休 | 防禦性配置、詳細分類、多幣別 |

**對帳單範例（虛構的小康家庭）：**

| 檔案 | 類型 | 說明 |
|------|------|------|
| `sample_bank_statement.md` | 銀行綜合對帳單 | 薪轉、房貸、存款、外幣 |
| `sample_credit_card.md` | 信用卡帳單 | 日常消費、附卡、回饋 |
| `sample_securities.md` | 證券對帳單 | ETF/個股庫存、交易明細 |
| `sample_output/` | 產出報告 | 上述三份帳單的完整分析結果 |

這些不是「最佳設定」— 是讓你理解每個參數為什麼存在，然後寫出自己的版本。

## 安全性

- 不需雲端：所有運算在本地完成，不上傳任何數據
- 原子寫入：臨時檔 + `os.replace()`，不會產出半殘報告
- 機密隔離：`config.yaml` 在 `.gitignore` 中，不會被提交
- 市場數據降級：yfinance 失敗時用快取，快取過期時用硬編碼 fallback 並警告

## AI Agent 整合

```bash
python -m personal_cfo cfo \
  --transactions ./statements/ \
  --period 2026-02 \
  --offline --quiet
```

附帶 `SKILL.md` 讓 [OpenClaw](https://openclaw.ai/) 或其他 AI agent 框架直接整合。

## 目標用戶

熟悉 CLI 的技術人員，想要自動化的月度財務體檢，不需要 SaaS 或資料庫。
也歡迎用 AI（Claude / ChatGPT）協助你根據自身情況修改 `config.yaml`。

## 貢獻

參見 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 授權

MIT
