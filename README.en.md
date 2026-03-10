# personal-cfo

> [繁體中文 README](README.md)

CLI-first retirement glide path financial analyzer — bank statements in, financial reports out, your data stays local.

Any AI agent framework can call it via shell. Includes `SKILL.md` for direct [OpenClaw](https://openclaw.ai/) integration.

## What It Does

Turns your monthly bank statements into:
- **Income Statement** (8-category P&L)
- **Balance Sheet** (assets vs liabilities by risk bucket)
- **Cash Flow Summary** (operating inflow/outflow)
- **Market Anchors** (global indicators for context)
- **Retirement Glide Path Diagnosis** (are you on track?)

## Philosophy

> Most people don't have the discipline for financial planning. They make decisions based on news and social media.
> personal-cfo is not a trading tool. It's a monthly financial checkup that runs itself.

- **Post-hoc audit** — uses bank statements with a 1-month delay, 100% objective
- **Deterministic computation** — Python calculates the numbers, zero hallucination
- **Anti-noise** — only alerts you when your retirement track drifts, stays silent when on track

## Pipeline

Part of the lazy finance trilogy (each works independently):

```
gmail-statement-fetcher  →  doc-cleaner  →  personal-cfo
(fetch bank PDFs)           (PDF→Markdown)   (compute reports)
```

| Ring | Input | Output | Standalone |
|------|-------|--------|------------|
| [gmail-statement-fetcher](https://github.com/notoriouslab/gmail-statement-fetcher) | Gmail | PDF | Yes |
| [doc-cleaner](https://github.com/notoriouslab/doc-cleaner) | PDF/DOCX/XLSX | Markdown + JSON | Yes |
| **personal-cfo** | CSV or Markdown+JSON | Financial reports + snapshots | Yes |

## Quick Start

```bash
# Install core dependency (pyyaml only)
pip install -r requirements.txt

# Optional: live market data
pip install -r requirements-full.txt

# Copy and edit config
cp config.example.yaml config.yaml

# Monthly audit (CSV input)
python -m personal_cfo cfo \
  --transactions ./data/jan.csv \
  --period 2026-01

# Monthly audit (doc-cleaner Markdown output)
python -m personal_cfo cfo \
  --transactions ./statements/ \
  --period 2026-01 \
  --offline

# Retirement track check (from saved snapshots)
python -m personal_cfo track --snapshots ./output/snapshots/
```

## Sample Output

```
## Income Statement

| Category | Amount (TWD) |
|----------|----------:|
| Salary/Income | 150,000 |
| Dividend/Interest | 6,284 |
| Living/Other | -85,000 |
| Interest | -25,000 |
| **Net Operating** | **46,284** |

## Retirement Glide Path

- Target Equity Ratio: 20.0%
- Actual Equity Ratio: 16.3%
- Drift: -3.7%
- Status: MINOR_DRIFT
```

## Input Formats

### CSV (universal)
```csv
date,description,amount,currency,category,account
2026-01-05,Salary,150000,TWD,salary,Bank_A
2026-01-10,Mortgage,-25000,TWD,housing,Bank_B
```

### Markdown + JSON (from doc-cleaner pipeline)
Reads `STRUCTURED_DATA` JSON blocks embedded in Markdown files. Credit card files (filename contains `credit`) are automatically sign-flipped.

**Fallback mode:** When the JSON contains `refined_markdown` but no `transactions[]` array, the parser automatically extracts transactions from pipe tables in the markdown. This means doc-cleaner output works directly — no extra processing step needed. Supports both single-amount tables (credit cards) and split debit/credit columns (bank statements).

## Configuration

See `config.example.yaml` for all options:

| Section | Purpose |
|---------|---------|
| `life_plan` | Birth year, retirement age |
| `glide_path` | Equity target, annual derisking rate, drift thresholds |
| `manual_assets` | Assets not in bank statements (real estate, etc.) |
| `category_rules` | Keyword → category mapping (**order matters**, specific first) |
| `fx_rates` | Static exchange rates (format: `USD_TWD: 32.0`) |

## CLI Options

```
python -m personal_cfo cfo --help
python -m personal_cfo track --help
```

| Option | Description |
|--------|-------------|
| `--transactions`, `-t` | Transaction CSV files, Markdown files, or directory |
| `--assets`, `-a` | Assets CSV file (optional) |
| `--period`, `-p` | Period label (e.g. `2026-01`) |
| `--config`, `-c` | Config file path (default: `config.yaml`) |
| `--output`, `-o` | Output directory |
| `--offline` | Skip network calls (use cached/hardcoded market data) |
| `--quiet`, `-q` | Only save files, no stdout |

## Security

See [SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
