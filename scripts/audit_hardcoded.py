import os
import re
from pathlib import Path

root = Path(r"c:\Users\roboa\OneDrive\Desktop\insights")

patterns = [
    ("Hardcoded Array of Objects", re.compile(r"const\s+[A-Z0-9_]+\s*=\s*\[\s*\{")),
    ("Hardcoded Campus Code", re.compile(r"['\"](DELH01|ALPH01|STXA01|BETA01|SCH-)['\"]")),
    ("Hardcoded Grade Fallback", re.compile(r"(\|\|\s*['\"]10['\"]|grade\s*===\s*['\"]10['\"])")),
    ("Hardcoded Section Fallback", re.compile(r"(\|\|\s*['\"]A['\"]|section\s*===\s*['\"]A['\"])")),
    ("Hardcoded Credentials", re.compile(r"['\"](Admin@123|Teacher@123|SuperAdmin@123|Pass@123)['\"]")),
    ("Hardcoded Phone", re.compile(r"['\"](9876543210|9876543211|9999999999|1234567890)['\"]")),
    ("Hardcoded Email", re.compile(r"['\"][a-zA-Z0-9._%+-]+@example\.com['\"]")),
    ("Hardcoded Sample Date", re.compile(r"['\"]202[0-9]-[0-1][0-9]-[0-3][0-9]['\"]")),
    ("Hardcoded Student Name", re.compile(r"['\"](Aarav|Kavita|Deepak|Meera|Arjun|Sunil|Priya|Rajesh Sharma)['\"]", re.IGNORECASE)),
]

results = []
skip_dirs = {"node_modules", ".git", "dist", ".gemini", "brain", "venv", ".venv", "__pycache__", "scripts", ".expo"}

for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in skip_dirs]
    for fn in filenames:
        ext = os.path.splitext(fn)[1]
        if ext not in [".js", ".jsx", ".py"]:
            continue
        p = Path(dirpath) / fn
        rel = str(p.relative_to(root))
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            for name, pat in patterns:
                if pat.search(line):
                    results.append((rel, idx, name, line.strip()))

print(f"=== TOTAL HARDCODED OCCURRENCES: {len(results)} ===")
for r in results:
    print(f"[{r[0]}:{r[1]}] ({r[2]}) -> {r[3][:110]}")
