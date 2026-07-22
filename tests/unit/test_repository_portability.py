from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCANNED_PATHS = (
    "src",
    "tests",
    "configs",
    "tools",
    "analysis_modules",
    "examples",
    "scripts",
    "docs",
    "prompts",
    "workers",
)
TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".toml", ".txt"}
USER_HOME_PATTERNS = (
    re.compile("/" + r"Users/[^/\s]+/"),
    re.compile("/" + r"home/[^/\s]+/"),
    re.compile(r"[A-Za-z]:" + r"\\Users\\[^\\\s]+\\"),
)


def test_repository_assets_do_not_contain_user_home_paths() -> None:
    findings: list[str] = []
    for relative_root in SCANNED_PATHS:
        scan_root = ROOT / relative_root
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            for line_number, line in enumerate(content.splitlines(), start=1):
                if any(pattern.search(line) for pattern in USER_HOME_PATTERNS):
                    findings.append(f"{path.relative_to(ROOT)}:{line_number}")

    assert not findings, "User-specific absolute paths found: " + ", ".join(findings)
