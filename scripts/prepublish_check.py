from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_NAMES = {".env", "secrets.toml"}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
SECRET_PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "Configured secret": re.compile(
        r"(?:GEMINI_API_KEY|JIRA_API_TOKEN)\s*=\s*(?!your-key|changeme|<)[A-Za-z0-9_-]{20,}",
        re.IGNORECASE,
    ),
}


def repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / path for path in result.stdout.decode("utf-8").split("\0") if path]


def main() -> int:
    failures: list[str] = []
    for path in repository_files():
        relative = path.relative_to(ROOT)
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"Forbidden publish file: {relative}")
            continue
        if path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"Possible {label} in {relative}")
    if failures:
        print("Pre-publication check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Pre-publication check passed: no forbidden databases, secret files, or key patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
