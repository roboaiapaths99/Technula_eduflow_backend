import sys
import os
import re
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app import app

def get_all_routes(router_or_app, prefix=""):
    routes = []
    sub_routes = getattr(router_or_app, "routes", [])
    for r in sub_routes:
        if hasattr(r, "original_router"):
            inc_prefix = getattr(getattr(r, "include_context", None), "prefix", "") or ""
            routes.extend(get_all_routes(r.original_router, prefix=prefix + inc_prefix))
        elif hasattr(r, "router") and hasattr(r.router, "routes"):
            routes.extend(get_all_routes(r.router, prefix=prefix + (getattr(r, "path", "") or "")))
        elif hasattr(r, "routes"):
            routes.extend(get_all_routes(r, prefix=prefix + (getattr(r, "path", "") or "")))
        elif hasattr(r, "methods"):
            routes.append((list(r.methods), prefix + getattr(r, "path", "")))
    return routes

backend_routes = get_all_routes(app)
print(f"Total Backend Routes registered: {len(backend_routes)}")
for m, p in sorted(backend_routes, key=lambda x: x[1]):
    print(f"  {m} {p}")

frontend_api_path = Path(__file__).parent.parent.parent / "frontend" / "src" / "api.js"
parent_api_path = Path(__file__).parent.parent.parent / "parent_app" / "src" / "api.js"

def extract_endpoints_from_file(file_path):
    text = file_path.read_text(encoding="utf-8")
    # Replace ${...} with DUMMY_PARAM so full paths are preserved
    text_sub = re.sub(r"\$\{[^}]+\}", "TEST_PARAM", text)
    matches = re.findall(r"['`](/(?:auth|schools|admin|attendance|risk|tickets|announcements|notifications|students|dashboard|report-cards|marks|analytics|fees|timetable|calendar|leaves|homework|upload|chat|exam-sheets|certificates|ptc|parent)[^'`?\s]*)", text_sub)
    return set(matches)

fe_endpoints = extract_endpoints_from_file(frontend_api_path)
parent_endpoints = extract_endpoints_from_file(parent_api_path)

print(f"Unique endpoint paths in Frontend api.js: {len(fe_endpoints)}")
print(f"Unique endpoint paths in Parent App api.js: {len(parent_endpoints)}")

def normalize_route_pattern(r_path):
    # Handle {param:path} and {param}
    pattern = re.sub(r"\{[^}]+:path\}", r".+", r_path)
    pattern = re.sub(r"\{[^}]+\}", r"[^/]+", pattern)
    return f"^{pattern}$"

registered_patterns = [(r[1], normalize_route_pattern(r[1])) for r in backend_routes]

def check_endpoints(name, endpoints):
    print(f"\n--- Checking {name} Endpoints against Backend ---")
    missing = []
    for ep in sorted(endpoints):
        matched = False
        for original_route, pat in registered_patterns:
            if re.match(pat, ep):
                matched = True
                break
        if not matched:
            missing.append(ep)
            print(f"  [MISSING/MISMATCH] {ep}")
    if not missing:
        print(f"  [ALL MATCHED OK] All {len(endpoints)} {name} endpoints match a registered backend route!")
    else:
        print(f"  [SUMMARY] {len(missing)} out of {len(endpoints)} endpoints had mismatches.")
    return missing

fe_missing = check_endpoints("Frontend Web", fe_endpoints)
parent_missing = check_endpoints("Parent App", parent_endpoints)

print("\n--- Route Check Summary ---")
print(f"Frontend Missing Count: {len(fe_missing)}")
print(f"Parent App Missing Count: {len(parent_missing)}")
