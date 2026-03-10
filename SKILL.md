---
name: personal-cfo
description: CLI-first retirement glide path financial analyzer
version: 0.1.0
metadata:
  openclaw:
    emoji: "\U0001F4CA"
    homepage: https://github.com/notoriouslab/personal-cfo
    requires:
      bins: ["python3"]
      pip: ["pyyaml"]
---

# personal-cfo

Turns bank statements (CSV or Markdown+JSON) into financial three-statements plus retirement glide path diagnosis.

## Commands

### Monthly Financial Audit (CFO mode)

```bash
# From CSV
python -m personal_cfo cfo --transactions ./data.csv --period 2026-01 --config config.yaml --offline

# From doc-cleaner Markdown directory
python -m personal_cfo cfo --transactions ./statements/ --period 2026-01 --config config.yaml --offline --quiet
```

### Retirement Track Check

```bash
python -m personal_cfo track --snapshots ./output/snapshots/ --config config.yaml
```

### Full Pipeline (with gmail-statement-fetcher + doc-cleaner)

```bash
# Step 1: Fetch bank PDFs from Gmail
python fetcher.py --output-dir ./downloads

# Step 2: Convert to Markdown + JSON
python cleaner.py --input ./downloads --ai gemini --output-dir ./cleaned

# Step 3: Compute financial reports
python -m personal_cfo cfo --transactions ./cleaned --period 2026-01 --offline
```

## Output

- `financial_report_{period}.md` — Full financial report (IS + BS + CF + market + glide path)
- `snapshots/{period}_asset_snapshot.json` — Asset snapshot for track mode

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (no data, invalid config, etc.) |

## Notes

- Requires `config.yaml` (copy from `config.example.yaml`)
- Use `--offline` to skip yfinance market data fetch
- Use `--quiet` to suppress stdout (agent-friendly)
- Output is deterministic Markdown — no AI, no hallucination
