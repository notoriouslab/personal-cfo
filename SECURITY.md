# Security Policy

## Design Principles

- **Data stays local.** No telemetry, no cloud uploads, no external APIs except optional yfinance.
- **Deterministic computation.** No AI in the analysis pipeline. Python math only.
- **Atomic writes.** All file output uses `tempfile.mkstemp()` + `os.replace()` to prevent corruption.

## Sensitive Data Handling

- `config.yaml` contains personal financial parameters and is excluded from version control via `.gitignore`.
- Financial reports and snapshots may contain asset values. Store them securely.
- The `--quiet` flag suppresses financial data from stdout (useful for cron/agent environments).
- Error messages use `Path.name` (basename only) to avoid leaking full filesystem paths.

## Input Validation

- Period format is validated (`YYYY-MM` regex) to prevent path traversal.
- Amounts are bounded (reject NaN, Inf, and values > 1 trillion).
- YAML config uses `yaml.safe_load()` (no arbitrary code execution).
- JSON parsing errors are reported to stderr (not silently swallowed).

## Exchange Rates

- Missing exchange rates produce a stderr WARNING and fall back to 1.0.
- This can cause significant calculation errors. Always configure `fx_rates` for all currencies in your data.

## Market Data

- yfinance is optional. Use `--offline` to skip all network calls.
- Market cache is stored locally in the output directory (not a shared/global location).
- Hardcoded fallback values are dated and should be periodically updated.

## Reporting Vulnerabilities

If you discover a security issue, please email the maintainer directly rather than opening a public issue.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
