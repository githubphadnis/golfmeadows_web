# Universal Crypto Scanner (Repo-Only) - Quick Start

## What this does

`scripts/universal_crypto_scanner.py` scans a local repository for cryptography assets and risky usage patterns across multiple languages.

It generates:

- JSON report: `crypto_scan_report.json`
- HTML dashboard: `crypto_scan_dashboard.html`

Outputs include:

- Finding location (file + line number)
- Usage hints (provider, primitive, algorithm, key length, instantiation hint)
- Standards/regulation compatibility matrix (heuristic mapping)

## Run

From repository root:

`python3 scripts/universal_crypto_scanner.py --target . --output-dir scan_output`

Optional:

- `--repo-url <url>` to override auto-detected git remote
- `--max-file-size-kb <n>` to tune file scan limit

## Notes and limitations

- Static repo-only scanning is heuristic and can produce false positives/negatives.
- Compatibility statuses are risk indicators, not legal/compliance certification.
- Runtime behavior and external secret-management context are out of scope for static-only analysis.
