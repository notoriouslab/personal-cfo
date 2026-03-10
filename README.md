# personal-cfo

> [English README](README.en.md)

CLI 優先的退休滑行路徑財務分析工具 — 銀行帳單進，財務報表出，資料留在本地。

任何 AI agent 框架都可以透過 shell 呼叫，附帶 `SKILL.md` 讓 [OpenClaw](https://openclaw.ai/) 直接整合使用。

## 它做什麼

將每月銀行帳單轉換為：
- **損益表** (8 大類 P&L)
- **資產負債表** (依風險桶位分類)
- **現金流量摘要** (營運收支)
- **市場定錨** (全球指標作為背景參考)
- **退休滑行路徑診斷** (你的退休計畫在軌道上嗎？)

## 設計理念

> 大多數人沒有毅力做財務規劃。他們靠新聞和社群媒體做決策。
> personal-cfo 不是交易工具。它是一個自動運行的月度財務體檢。

- **事後審計** — 使用滯後一個月的銀行帳單，100% 客觀
- **確定性運算** — Python 計算數字，零幻覺
- **反噪音** — 只在退休軌道偏移時提醒你，在軌道上時保持安靜

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
# 安裝核心依賴（只需 pyyaml）
pip install -r requirements.txt

# 可選：安裝即時市場數據（yfinance）
pip install -r requirements-full.txt

# 複製設定範本並編輯你的參數
cp config.example.yaml config.yaml

# 月度審計（使用 CSV）
python -m personal_cfo cfo \
  --transactions ./data/jan.csv \
  --period 2026-01

# 月度審計（使用 doc-cleaner 的 Markdown 輸出）
python -m personal_cfo cfo \
  --transactions ./statements/ \
  --period 2026-01 \
  --offline

# 退休軌道檢查（使用已儲存的快照）
python -m personal_cfo track --snapshots ./output/snapshots/
```

## 輸出範例

```
## Income Statement (損益表)

| Category | Amount (TWD) |
|----------|----------:|
| 經常性收入 (Salary/Income) | 150,000 |
| 投資收益 (Dividend/Interest) | 6,284 |
| 生活與其他 (Living/Other) | -85,000 |
| 利息支出 (Interest) | -25,000 |
| **Net Operating (營運淨利)** | **46,284** |

## Retirement Glide Path (退休軌道)

- Target Equity Ratio (目標股票比): 20.0%
- Actual Equity Ratio (實際股票比): 16.3%
- Drift (偏移): -3.7%
- Status: MINOR_DRIFT
- Equity allocation slightly off target (偏低).
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

**Fallback 模式：** 當 JSON 只有 `refined_markdown` 但沒有 `transactions[]` 時，parser 會自動從 Markdown 的 pipe table 提取交易。也就是說 doc-cleaner 的輸出可以直接使用，不需要額外處理。支援單金額欄（信用卡）和分欄收支（銀行對帳單）兩種格式。

## 設定

參見 `config.example.yaml` 取得所有選項。主要區塊：

| 區塊 | 用途 |
|------|------|
| `life_plan` | 出生年、退休年齡 |
| `glide_path` | 股票目標比例、年度遞減率、漂移閾值 |
| `manual_assets` | 不在銀行帳單中的資產（不動產等） |
| `category_rules` | 關鍵字 → 分類映射（**順序敏感**，精確的放前面） |
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

## 目標用戶

熟悉 CLI 的技術人員，想要自動化的月度財務體檢，不需要 SaaS 或資料庫。

## 安全性

參見 [SECURITY.md](SECURITY.md)。

## 貢獻

參見 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 授權

MIT
