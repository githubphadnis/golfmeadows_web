#!/usr/bin/env python3
"""
Universal repository crypto scanner (static, repo-only).

This tool scans source files across multiple languages for cryptography assets
and risky patterns, then maps findings to security standards/regulations and
produces JSON + HTML reports.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


EXT_LANGUAGE_MAP = {
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".groovy": "groovy",
    ".scala": "scala",
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".fs": "fsharp",
    ".swift": "swift",
    ".rs": "rust",
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".m": "objective-c",
    ".mm": "objective-c++",
}

EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    ".venv",
    "venv",
    "__pycache__",
}

ALGORITHM_HINTS = [
    "AES",
    "DES",
    "3DES",
    "DESede",
    "RC4",
    "RSA",
    "DSA",
    "EC",
    "ECDSA",
    "Ed25519",
    "Ed448",
    "SHA1",
    "SHA-1",
    "SHA256",
    "SHA-256",
    "SHA384",
    "SHA-384",
    "SHA512",
    "SHA-512",
    "MD5",
    "ChaCha20",
    "PBKDF2",
    "Argon2",
    "scrypt",
    "HMAC",
    "GCM",
    "CBC",
    "ECB",
]

PROVIDER_HINTS = [
    ("BouncyCastle", r"\borg\.bouncycastle\b"),
    ("Google Tink", r"\bcom\.google\.crypto\.tink\b"),
    ("Apache Commons Crypto", r"\borg\.apache\.commons\.crypto\b"),
    ("Conscrypt", r"\borg\.conscrypt\b"),
    ("OpenSSL", r"\bopenssl\b"),
    ("libsodium", r"\blibsodium\b"),
    ("Java JCA/JCE", r"\bjavax\.crypto\b|\bjava\.security\b"),
    ("Python cryptography", r"\bcryptography\."),
    ("PyCryptodome", r"\bCrypto\.(Cipher|Hash|Protocol|PublicKey)\b"),
    ("Go crypto stdlib", r"\bcrypto/[A-Za-z0-9_]+\b"),
    ("Node crypto", r"(require\(\s*[\"']crypto[\"']\s*\)|from\s+[\"']crypto[\"']|import\s+crypto\b|\bcrypto\.)"),
]

PRIMITIVE_HINTS = [
    "Cipher",
    "Mac",
    "Signature",
    "MessageDigest",
    "KeyFactory",
    "KeyPairGenerator",
    "KeyGenerator",
    "SecretKeyFactory",
    "SecureRandom",
    "SSLContext",
    "TrustManager",
    "HostnameVerifier",
    "X509TrustManager",
    "AES",
    "RSA",
    "HMAC",
    "PBKDF2",
    "Argon2",
]

STANDARDS_AND_REGULATIONS = [
    "NIST",
    "OWASP",
    "FIPS_140_3",
    "FedRAMP",
    "HIPAA",
    "PCI_DSS",
    "KSA_NCS",
    "GDPR",
    "EU_AI_Act",
]


@dataclass
class Rule:
    rule_id: str
    title: str
    severity: str
    confidence: str
    cwe: str
    description: str
    pattern: str
    standards_impact: dict[str, str]
    remediation: str
    languages: set[str] = field(default_factory=set)
    flags: int = re.IGNORECASE

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern, self.flags)


RULES: list[Rule] = [
    Rule(
        rule_id="CRYPTO-001",
        title="Weak hash algorithm (MD5)",
        severity="high",
        confidence="high",
        cwe="CWE-327",
        description="MD5 is considered cryptographically broken for security-sensitive use.",
        pattern=r"\b(md5|MessageDigest\.getInstance\(\s*[\"']MD5[\"']\s*\)|hashlib\.md5\s*\()",
        standards_impact={"NIST": "fail", "OWASP": "fail", "FIPS_140_3": "fail", "FedRAMP": "fail"},
        remediation="Use SHA-256 or stronger for collision/preimage resistance, or HMAC-based constructions for integrity.",
    ),
    Rule(
        rule_id="CRYPTO-002",
        title="Weak hash algorithm (SHA-1)",
        severity="high",
        confidence="medium",
        cwe="CWE-327",
        description="SHA-1 is deprecated for many signature and collision-sensitive security uses.",
        pattern=r"\b(SHA1|SHA-1|MessageDigest\.getInstance\(\s*[\"']SHA-1[\"']\s*\))",
        standards_impact={"NIST": "fail", "OWASP": "warn", "FIPS_140_3": "warn", "PCI_DSS": "warn"},
        remediation="Use SHA-256/384/512 and modern signature schemes.",
    ),
    Rule(
        rule_id="CRYPTO-003",
        title="Insecure block cipher mode (ECB)",
        severity="critical",
        confidence="high",
        cwe="CWE-327",
        description="ECB mode leaks plaintext patterns and is not semantically secure.",
        pattern=r"\bECB\b|Cipher\.getInstance\(\s*[\"'][^\"']*ECB[^\"']*[\"']\s*\)",
        standards_impact={"NIST": "fail", "OWASP": "fail", "FIPS_140_3": "fail", "KSA_NCS": "fail"},
        remediation="Use AEAD modes such as AES-GCM (or ChaCha20-Poly1305 where appropriate).",
    ),
    Rule(
        rule_id="CRYPTO-004",
        title="Weak symmetric algorithm (DES/3DES/RC4)",
        severity="critical",
        confidence="high",
        cwe="CWE-327",
        description="DES/3DES/RC4 are weak or deprecated for modern cryptographic protection.",
        pattern=r"\b(DESede|3DES|DES|RC4)\b",
        standards_impact={"NIST": "fail", "OWASP": "fail", "FIPS_140_3": "warn", "FedRAMP": "fail", "PCI_DSS": "fail"},
        remediation="Use AES-GCM or other approved modern ciphers.",
    ),
    Rule(
        rule_id="CRYPTO-005",
        title="Potential hardcoded key/secret material",
        severity="high",
        confidence="medium",
        cwe="CWE-321",
        description="Hardcoded secrets reduce key management security and rotation capability.",
        pattern=r"\b(api[_-]?key|private[_-]?key|secret|client[_-]?secret|access[_-]?token|refresh[_-]?token|password|passphrase|token|secret[_-]?key)\b\s*[:=]\s*[\"'][^\"'\n]{8,}[\"']",
        standards_impact={"OWASP": "fail", "FedRAMP": "fail", "HIPAA": "warn", "PCI_DSS": "fail", "GDPR": "warn"},
        remediation="Move keys/secrets to managed secret stores (KMS/HSM/Vault) and rotate regularly.",
    ),
    Rule(
        rule_id="CRYPTO-006",
        title="Potential static IV/nonce",
        severity="high",
        confidence="medium",
        cwe="CWE-329",
        description="Static IV/nonce can break confidentiality and authenticity guarantees.",
        pattern=r"\b(iv|nonce)\b\s*[:=]\s*[\"'][A-Za-z0-9+/=_-]{8,}[\"']",
        standards_impact={"NIST": "fail", "OWASP": "fail", "PCI_DSS": "warn", "KSA_NCS": "fail"},
        remediation="Generate unique/random IVs/nonces per encryption operation.",
    ),
    Rule(
        rule_id="CRYPTO-007",
        title="Insecure randomness source for security context",
        severity="high",
        confidence="medium",
        cwe="CWE-338",
        description="Non-cryptographic RNGs should not be used for key/nonce/token generation.",
        pattern=r"\b(Math\.random\(|new\s+Random\(|random\.random\(|rand\(\))",
        standards_impact={"NIST": "warn", "OWASP": "fail", "PCI_DSS": "warn", "KSA_NCS": "warn"},
        remediation="Use cryptographically secure RNG APIs (e.g., SecureRandom, secrets module, crypto/rand).",
    ),
    Rule(
        rule_id="CRYPTO-008",
        title="Potential trust-all TLS/certificate bypass",
        severity="critical",
        confidence="medium",
        cwe="CWE-295",
        description="Disabling certificate validation enables man-in-the-middle attacks.",
        pattern=r"(verify\s*=\s*False|InsecureSkipVerify\s*:\s*true|HostnameVerifier\s*\{[^}]*return\s+true|checkServerTrusted\s*\([^)]*\)\s*\{\s*\})",
        standards_impact={"NIST": "fail", "OWASP": "fail", "FedRAMP": "fail", "HIPAA": "fail", "PCI_DSS": "fail", "GDPR": "fail"},
        remediation="Enable strict certificate validation and hostname verification.",
        flags=re.IGNORECASE | re.DOTALL,
    ),
    Rule(
        rule_id="CRYPTO-009",
        title="Potential weak RSA key length",
        severity="high",
        confidence="medium",
        cwe="CWE-326",
        description="RSA key sizes below policy baseline are likely insufficient.",
        pattern=r"\bRSA\b[^0-9\n]{0,40}\b(512|768|1024|1536)\b|\b(512|768|1024|1536)\b[^0-9\n]{0,40}\bRSA\b",
        standards_impact={"NIST": "fail", "OWASP": "warn", "PCI_DSS": "warn", "KSA_NCS": "fail"},
        remediation="Use RSA 2048+ (or stronger alternatives such as ECC with approved curves).",
    ),
    Rule(
        rule_id="CRYPTO-010",
        title="Potential weak PBKDF2 iteration count",
        severity="medium",
        confidence="low",
        cwe="CWE-916",
        description="Low KDF iteration counts can make offline attacks easier.",
        pattern=r"(PBKDF2|pbkdf2)[^\n]{0,80}\b([1-9][0-9]{0,3})\b",
        standards_impact={"OWASP": "warn", "PCI_DSS": "warn", "KSA_NCS": "warn"},
        remediation="Use modern KDFs and tune cost factors to current guidance and threat model.",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan repositories for cryptography assets/patterns and generate compliance-oriented reports."
    )
    parser.add_argument("--target", default=".", help="Path to local repository root (default: current directory).")
    parser.add_argument(
        "--output-dir",
        default="scan_output",
        help="Directory for generated report artifacts (JSON and HTML).",
    )
    parser.add_argument(
        "--repo-url",
        default="",
        help="Optional repository URL override (if omitted, inferred from git remote).",
    )
    parser.add_argument(
        "--max-file-size-kb",
        type=int,
        default=512,
        help="Skip files larger than this size in KB (default: 512).",
    )
    parser.add_argument(
        "--exclude-path",
        action="append",
        default=[],
        help="Path prefix relative to target to exclude (repeatable).",
    )
    return parser.parse_args()


def is_github_url(target: str) -> bool:
    return bool(re.match(r"^https?://github\.com/[^/]+/[^/]+(?:\.git)?/?$", target.strip()))


def prepare_target(target_arg: str) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    target_str = target_arg.strip()
    if not is_github_url(target_str):
        return Path(target_str).resolve(), None

    temp_dir = tempfile.TemporaryDirectory(prefix="crypto-scan-")
    clone_dir = Path(temp_dir.name) / "repo"
    clone_cmd = ["git", "clone", "--depth", "1", target_str, str(clone_dir)]
    result = subprocess.run(clone_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        temp_dir.cleanup()
        raise RuntimeError(f"Failed to clone target repository URL: {target_str}\n{result.stderr.strip()}")
    return clone_dir.resolve(), temp_dir


def run_git(target: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(target), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def detect_repo_metadata(target: Path, repo_url_override: str) -> dict[str, str]:
    remote_url = repo_url_override or run_git(target, ["remote", "get-url", "origin"])
    commit_sha = run_git(target, ["rev-parse", "HEAD"])
    branch = run_git(target, ["rev-parse", "--abbrev-ref", "HEAD"])
    return {
        "repo_url": remote_url,
        "commit_sha": commit_sha,
        "branch": branch,
    }


def language_for_path(path: Path) -> str:
    return EXT_LANGUAGE_MAP.get(path.suffix.lower(), "unknown")


def should_skip_file(path: Path, max_file_size_kb: int) -> bool:
    try:
        if path.stat().st_size > max_file_size_kb * 1024:
            return True
    except OSError:
        return True
    return False


def extract_usage_details(line: str) -> dict[str, Any]:
    details: dict[str, Any] = {
        "provider": "",
        "primitive": "",
        "algorithm": "",
        "key_length": None,
        "instantiation": False,
    }

    for provider_name, provider_pattern in PROVIDER_HINTS:
        if re.search(provider_pattern, line, flags=re.IGNORECASE):
            details["provider"] = provider_name
            break

    for primitive in PRIMITIVE_HINTS:
        if re.search(rf"\b{re.escape(primitive)}\b", line):
            details["primitive"] = primitive
            break

    for alg in ALGORITHM_HINTS:
        if re.search(rf"\b{re.escape(alg)}\b", line, flags=re.IGNORECASE):
            details["algorithm"] = alg
            break

    key_len_match = re.search(r"\b(64|96|112|128|160|192|224|256|384|512|1024|1536|2048|3072|4096)\b", line)
    if key_len_match:
        details["key_length"] = int(key_len_match.group(1))

    details["instantiation"] = bool(
        re.search(r"\bnew\s+\w+|\.getInstance\s*\(|generate(Key|Secret|Pair)|KeyGenerator\.|KeyPairGenerator\.", line)
    )
    return details


def collect_provider_assets(lines: list[str], rel_file: str, language: str, repo_url: str) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        line_trimmed = line.strip()
        for provider_name, provider_pattern in PROVIDER_HINTS:
            if re.search(provider_pattern, line_trimmed, flags=re.IGNORECASE):
                details = extract_usage_details(line_trimmed)
                assets.append(
                    {
                        "type": "provider_usage",
                        "provider": provider_name,
                        "primitive": details.get("primitive", ""),
                        "algorithm": details.get("algorithm", ""),
                        "location": {
                            "repo_url": repo_url,
                            "file": rel_file,
                            "line": index,
                        },
                        "language": language,
                        "snippet": line_trimmed[:220],
                    }
                )
    return assets


def scan_file(
    path: Path,
    rel_file: str,
    language: str,
    repo_url: str,
    compiled_rules: list[tuple[Rule, re.Pattern[str]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    provider_assets: list[dict[str, Any]] = []

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings, provider_assets

    lines = text.splitlines()
    provider_assets.extend(collect_provider_assets(lines, rel_file, language, repo_url))

    for rule, pattern in compiled_rules:
        if rule.languages and language not in rule.languages:
            continue
        for match in pattern.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            line_content = lines[line_number - 1].strip() if 0 < line_number <= len(lines) else ""
            details = extract_usage_details(line_content)
            findings.append(
                {
                    "id": f"{rule.rule_id}:{rel_file}:{line_number}:{match.start()}",
                    "rule_id": rule.rule_id,
                    "title": rule.title,
                    "description": rule.description,
                    "severity": rule.severity,
                    "confidence": rule.confidence,
                    "cwe": rule.cwe,
                    "standards_impact": rule.standards_impact,
                    "location": {
                        "repo_url": repo_url,
                        "file": rel_file,
                        "line": line_number,
                    },
                    "usage": details,
                    "evidence": line_content[:300],
                    "remediation": rule.remediation,
                    "language": language,
                }
            )

    return findings, provider_assets


def iter_source_files(root: Path, max_file_size_kb: int, excluded_prefixes: list[str], excluded_paths_abs: set[Path]) -> list[Path]:
    source_files: list[Path] = []
    excluded_prefixes_norm = [p.strip("/").replace("\\", "/") for p in excluded_prefixes if p.strip()]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        current_dir = Path(dirpath)
        for file_name in filenames:
            file_path = current_dir / file_name
            file_path_resolved = file_path.resolve()
            if file_path_resolved in excluded_paths_abs:
                continue
            if should_skip_file(file_path, max_file_size_kb):
                continue
            if language_for_path(file_path) == "unknown":
                continue
            rel_file = str(file_path.relative_to(root)).replace("\\", "/")
            if any(rel_file == prefix or rel_file.startswith(f"{prefix}/") for prefix in excluded_prefixes_norm):
                continue
            source_files.append(file_path)
    return source_files


def aggregate_compatibility(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_standard: dict[str, dict[str, Any]] = {}
    for standard in STANDARDS_AND_REGULATIONS:
        by_standard[standard] = {"status": "pass", "triggered_findings": 0, "high_or_critical": 0}

    for finding in findings:
        impact = finding.get("standards_impact", {})
        sev = finding.get("severity", "").lower()
        for standard, state in impact.items():
            if standard not in by_standard:
                by_standard[standard] = {"status": "pass", "triggered_findings": 0, "high_or_critical": 0}
            by_standard[standard]["triggered_findings"] += 1
            if sev in {"high", "critical"}:
                by_standard[standard]["high_or_critical"] += 1
            current = by_standard[standard]["status"]
            if state == "fail":
                by_standard[standard]["status"] = "fail"
            elif state == "warn" and current == "pass":
                by_standard[standard]["status"] = "warn"

    return by_standard


def compute_compatibility_profiles(
    matrix: dict[str, dict[str, Any]], findings: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    critical_count = sum(1 for f in findings if str(f.get("severity", "")).lower() == "critical")
    high_count = sum(1 for f in findings if str(f.get("severity", "")).lower() == "high")

    def compatible(statuses: list[str], allow_warn: bool = False, max_critical: int = 0, max_high: int | None = None) -> bool:
        for status in statuses:
            state = matrix.get(status, {}).get("status", "pass")
            if state == "fail":
                return False
            if not allow_warn and state == "warn":
                return False
        if critical_count > max_critical:
            return False
        if max_high is not None and high_count > max_high:
            return False
        return True

    return {
        "FIPS_140_3_Compatible": {
            "compatible": compatible(["FIPS_140_3"], allow_warn=False),
            "basis": "Derived from FIPS_140_3 matrix status and high-severity crypto findings.",
        },
        "KSA_NCS_Advanced_Compatible": {
            "compatible": compatible(["KSA_NCS", "NIST", "OWASP"], allow_warn=False),
            "basis": "Derived from KSA_NCS + NIST + OWASP status with no critical crypto-risk findings.",
        },
        "FedRAMP_Compatible": {
            "compatible": compatible(["FedRAMP", "NIST"], allow_warn=False),
            "basis": "Derived from FedRAMP and NIST status with zero critical findings.",
        },
        "PCI_DSS_Compatible": {
            "compatible": compatible(["PCI_DSS"], allow_warn=True, max_critical=0),
            "basis": "Derived from PCI_DSS status and absence of critical crypto findings.",
        },
    }


def build_summary(findings: list[dict[str, Any]], provider_assets: list[dict[str, Any]], files_scanned: int) -> dict[str, Any]:
    severity_counter = Counter(f["severity"] for f in findings)
    confidence_counter = Counter(f["confidence"] for f in findings)
    language_counter = Counter(f["language"] for f in findings)
    provider_counter = Counter(asset.get("provider", "unknown") for asset in provider_assets)
    return {
        "files_scanned": files_scanned,
        "total_findings": len(findings),
        "total_provider_assets": len(provider_assets),
        "severity": dict(severity_counter),
        "confidence": dict(confidence_counter),
        "languages_with_findings": dict(language_counter),
        "providers_detected": dict(provider_counter),
    }


def write_json_report(out_path: Path, report: dict[str, Any]) -> None:
    out_path.write_text(json.dumps(report, indent=2, sort_keys=False), encoding="utf-8")


def html_escape(s: Any) -> str:
    return html.escape(str(s))


def write_html_dashboard(out_path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    findings = report["findings"]
    matrix = report["compatibility_matrix"]
    profiles = report.get("compatibility_profiles", {})

    sev_rows = "".join(
        f"<tr><td>{html_escape(k)}</td><td>{html_escape(v)}</td></tr>"
        for k, v in sorted(summary.get("severity", {}).items(), key=lambda kv: kv[0])
    )
    provider_rows = "".join(
        f"<tr><td>{html_escape(k)}</td><td>{html_escape(v)}</td></tr>"
        for k, v in sorted(summary.get("providers_detected", {}).items(), key=lambda kv: kv[0])
    )
    matrix_rows = "".join(
        (
            "<tr>"
            f"<td>{html_escape(std)}</td>"
            f"<td class='status-{html_escape(val['status'])}'>{html_escape(val['status']).upper()}</td>"
            f"<td>{html_escape(val['triggered_findings'])}</td>"
            f"<td>{html_escape(val['high_or_critical'])}</td>"
            "</tr>"
        )
        for std, val in matrix.items()
    )
    profile_rows = "".join(
        (
            "<tr>"
            f"<td>{html_escape(name)}</td>"
            f"<td class='status-{'pass' if val.get('compatible') else 'fail'}'>{'YES' if val.get('compatible') else 'NO'}</td>"
            f"<td>{html_escape(val.get('basis', ''))}</td>"
            "</tr>"
        )
        for name, val in profiles.items()
    )

    finding_rows = []
    for finding in findings:
        loc = finding.get("location", {})
        usage = finding.get("usage", {})
        finding_rows.append(
            "<tr>"
            f"<td>{html_escape(finding.get('severity', '').upper())}</td>"
            f"<td>{html_escape(finding.get('rule_id', ''))}</td>"
            f"<td>{html_escape(finding.get('title', ''))}</td>"
            f"<td>{html_escape(loc.get('file', ''))}:{html_escape(loc.get('line', ''))}</td>"
            f"<td>{html_escape(usage.get('provider', ''))}</td>"
            f"<td>{html_escape(usage.get('primitive', ''))}</td>"
            f"<td>{html_escape(usage.get('algorithm', ''))}</td>"
            f"<td>{html_escape(usage.get('key_length', ''))}</td>"
            f"<td>{html_escape(finding.get('evidence', ''))}</td>"
            "</tr>"
        )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Universal Crypto Scan Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 16px; color: #111; }}
    h1, h2 {{ margin: 0.3em 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(260px, 1fr)); gap: 18px; margin: 12px 0 20px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; font-size: 12px; vertical-align: top; }}
    th {{ background: #f4f4f4; text-align: left; }}
    .status-pass {{ color: #0a7a2d; font-weight: bold; }}
    .status-warn {{ color: #9a6700; font-weight: bold; }}
    .status-fail {{ color: #b00020; font-weight: bold; }}
    .note {{ padding: 10px; background: #f8f9fb; border: 1px solid #e5e7eb; margin: 10px 0 14px; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>Universal Crypto Scan Dashboard</h1>
  <div class="note">
    <div><strong>Repository:</strong> {html_escape(report["repository"]["repo_url"] or "unknown")}</div>
    <div><strong>Commit:</strong> {html_escape(report["repository"]["commit_sha"] or "unknown")}</div>
    <div><strong>Branch:</strong> {html_escape(report["repository"]["branch"] or "unknown")}</div>
    <div><strong>Generated:</strong> {html_escape(report["scan_metadata"]["generated_at_utc"])}</div>
    <div><strong>Disclaimer:</strong> Static repo-only scan. Results indicate likely cryptographic risk patterns, not a formal compliance certification.</div>
  </div>
  <div class="grid">
    <div>
      <h2>Summary</h2>
      <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Files scanned</td><td>{html_escape(summary.get("files_scanned", 0))}</td></tr>
        <tr><td>Total findings</td><td>{html_escape(summary.get("total_findings", 0))}</td></tr>
        <tr><td>Provider assets</td><td>{html_escape(summary.get("total_provider_assets", 0))}</td></tr>
      </table>
    </div>
    <div>
      <h2>Severity counts</h2>
      <table>
        <tr><th>Severity</th><th>Count</th></tr>
        {sev_rows}
      </table>
    </div>
    <div>
      <h2>Detected providers</h2>
      <table>
        <tr><th>Provider</th><th>Count</th></tr>
        {provider_rows}
      </table>
    </div>
    <div>
      <h2>Compatibility matrix</h2>
      <table>
        <tr><th>Framework</th><th>Status</th><th>Triggered Findings</th><th>High/Critical</th></tr>
        {matrix_rows}
      </table>
    </div>
    <div>
      <h2>Compatibility profiles</h2>
      <table>
        <tr><th>Profile</th><th>Compatible</th><th>Basis</th></tr>
        {profile_rows}
      </table>
    </div>
  </div>
  <h2>Findings</h2>
  <table>
    <tr>
      <th>Severity</th><th>Rule</th><th>Title</th><th>Location</th><th>Provider</th>
      <th>Primitive</th><th>Algorithm</th><th>Key Length</th><th>Evidence</th>
    </tr>
    {''.join(finding_rows)}
  </table>
</body>
</html>
"""

    out_path.write_text(html_doc, encoding="utf-8")


def generate_report(
    target: Path,
    output_dir: Path,
    repo_url_override: str,
    max_file_size_kb: int,
    excluded_prefixes: list[str],
) -> dict[str, Any]:
    repo_meta = detect_repo_metadata(target, repo_url_override)
    compiled_rules = [(rule, rule.compiled()) for rule in RULES]
    findings: list[dict[str, Any]] = []
    provider_assets: list[dict[str, Any]] = []
    scanner_script_path = Path(__file__).resolve()
    output_dir_resolved = output_dir.resolve()
    excluded_abs: set[Path] = {scanner_script_path}
    files = iter_source_files(
        target,
        max_file_size_kb=max_file_size_kb,
        excluded_prefixes=[*excluded_prefixes, str(output_dir_resolved.relative_to(target)) if output_dir_resolved.is_relative_to(target) else ""],
        excluded_paths_abs=excluded_abs,
    )

    for file_path in files:
        rel_file = str(file_path.relative_to(target))
        language = language_for_path(file_path)
        file_findings, file_assets = scan_file(
            file_path,
            rel_file,
            language,
            repo_url=repo_meta.get("repo_url", ""),
            compiled_rules=compiled_rules,
        )
        findings.extend(file_findings)
        provider_assets.extend(file_assets)

    summary = build_summary(findings, provider_assets, files_scanned=len(files))
    compatibility_matrix = aggregate_compatibility(findings)
    compatibility_profiles = compute_compatibility_profiles(compatibility_matrix, findings)

    findings_sorted = sorted(
        findings,
        key=lambda f: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(f.get("severity", "low"), 4),
            f.get("location", {}).get("file", ""),
            f.get("location", {}).get("line", 0),
        ),
    )

    provider_assets_sorted = sorted(
        provider_assets, key=lambda a: (a["location"]["file"], a["location"]["line"], a.get("provider", ""))
    )

    report = {
        "project": target.name,
        "repository": repo_meta,
        "scan_metadata": {
            "scanner": "universal_crypto_scanner",
            "version": "0.1.0",
            "generated_at_utc": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
            "scan_type": "static_repo_only",
        },
        "summary": summary,
        "compatibility_matrix": compatibility_matrix,
        "compatibility_profiles": compatibility_profiles,
        "limitations": [
            "Static analysis cannot prove runtime behavior (e.g., negotiated TLS ciphers, externalized key sources).",
            "Results are heuristic and intended for risk triage, not formal compliance certification.",
            "Language coverage is pattern-based and may produce false positives/negatives.",
        ],
        "findings": findings_sorted,
        "crypto_assets": provider_assets_sorted,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_report(output_dir / "crypto_scan_report.json", report)
    write_html_dashboard(output_dir / "crypto_scan_dashboard.html", report)
    return report


def main() -> int:
    args = parse_args()
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        target, temp_dir = prepare_target(args.target)
        output_dir = Path(args.output_dir).resolve()

        if not target.exists() or not target.is_dir():
            print(f"Target path does not exist or is not a directory: {target}", file=sys.stderr)
            return 2

        report = generate_report(
            target=target,
            output_dir=output_dir,
            repo_url_override=args.repo_url,
            max_file_size_kb=args.max_file_size_kb,
            excluded_prefixes=args.exclude_path,
        )
        print(f"Scan complete. Findings: {report['summary']['total_findings']}")
        print(f"JSON report: {output_dir / 'crypto_scan_report.json'}")
        print(f"HTML dashboard: {output_dir / 'crypto_scan_dashboard.html'}")
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
