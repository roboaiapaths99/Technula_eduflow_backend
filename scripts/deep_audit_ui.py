import os
import re
from pathlib import Path

repo_root = Path(r"c:\Users\roboa\OneDrive\Desktop\insights")

def scan_files():
    issues = []
    
    # 1. Search for suspicious onClick / onPress
    suspicious_handlers = [
        r'onClick\s*=\s*\{\s*\(\s*\)\s*=>\s*\{\s*\}\s*\}',
        r'onPress\s*=\s*\{\s*\(\s*\)\s*=>\s*\{\s*\}\s*\}',
        r'onClick\s*=\s*\{\s*\(\s*\)\s*=>\s*console\.',
        r'onPress\s*=\s*\{\s*\(\s*\)\s*=>\s*console\.',
        r'coming soon',
        r'not implemented',
    ]

    # 2. Hardcoded mocks
    mock_keywords = [
        r'Delhi Public International School',
        r'Aarav Patel',
        r'Sunita Rao',
        r'mock',
        r'dummy',
    ]

    for base_dir in [repo_root / "frontend" / "src", repo_root / "parent_app" / "src"]:
        for p in base_dir.rglob("*.[j|t]s*"):
            if "node_modules" in p.parts:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            lines = text.splitlines()

            for i, line in enumerate(lines, 1):
                for pat in suspicious_handlers:
                    if re.search(pat, line, re.IGNORECASE):
                        issues.append((str(p.relative_to(repo_root)), i, f"Suspicious Handler: {pat}", line.strip()))
                
                for kw in mock_keywords:
                    if re.search(kw, line, re.IGNORECASE):
                        # filter out seed or legitimate test references if any
                        issues.append((str(p.relative_to(repo_root)), i, f"Hardcoded String: {kw}", line.strip()))

    print(f"Total UI Audit Findings: {len(issues)}")
    for f, ln, desc, content in issues:
        print(f"[{f}:{ln}] {desc} -> {content[:100]}")

if __name__ == "__main__":
    scan_files()
