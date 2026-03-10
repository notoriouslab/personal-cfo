# Contributing to personal-cfo

Thanks for your interest in contributing!

## How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Test with real or sample data:
   ```bash
   python -m personal_cfo cfo --transactions ./examples/ --period 2026-01 --offline
   ```
5. Submit a Pull Request

## Guidelines

- Keep it simple. This is a Plan B (~500 lines) tool, not an enterprise product.
- No AI dependencies in core. Computation must be deterministic.
- Atomic writes for all file output (`tempfile.mkstemp` + `os.replace`).
- No hardcoded paths. Use CLI arguments or config.
- `config.yaml` must never be committed (contains personal financial data).

## Adding Bank Support

The easiest way to support a new bank format:

1. Use [doc-cleaner](https://github.com/notoriouslab/doc-cleaner) to convert your bank PDF to Markdown+JSON
2. If the JSON categories don't match, add entries to `category_rules` in your `config.yaml`
3. If you need a new asset category mapping, open an issue

## Reporting Issues

- Include your Python version and OS
- Redact any personal financial data from logs
- Sample CSV/Markdown input (anonymized) helps a lot

## Code of Conduct

Be respectful. We're all here to make personal finance less painful.
