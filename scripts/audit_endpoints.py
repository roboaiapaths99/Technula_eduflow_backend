import os
import re
import json

with open('openapi_paths.json', encoding='utf-8') as f:
    api_paths = json.load(f)

# Normalize api paths for regex matching (replace {param} with [^/]+)
patterns = []
for p in api_paths:
    regex_p = '^' + re.sub(r'\{[^}]+\}', '[^/]+', p) + '$'
    patterns.append((p, re.compile(regex_p)))

def find_api_calls(folder):
    calls = []
    str_regex = re.compile(r"['\"`](/(?:auth|schools|admin|students|dashboard|insights|teacher|attendance|risk|tickets|announcements|notifications|report-cards|parent|admin-stats|marks|analytics|fees|timetable|calendar|leaves|homework|upload|chat|risk-cases|exam-sheets|certificates|ptc|diary|superadmin|parent-codes|subscription|gate-passes|visitor-logs|datesheets|almanac|holidays|gallery|activities|parent-profile|branding|birthday|broadcast|reports|realtime)[^'\"`?]*)")
    
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.endswith(('.js', '.jsx')):
                fp = os.path.join(root, file)
                with open(fp, encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    for match in str_regex.finditer(content):
                        calls.append((os.path.relpath(fp, folder), match.group(1)))
    return calls

fe_calls = find_api_calls('../frontend/src')
pa_calls = find_api_calls('../parent_app/src')

print(f'Total FE URL literals found: {len(fe_calls)}')
print(f'Total Parent App URL literals found: {len(pa_calls)}')

unmatched = []
for file, url in fe_calls + pa_calls:
    # strip template literal ${...}
    clean_url = re.sub(r'\$\{[^}]+\}', 'testparam', url)
    # also strip trailing slashes or normalize
    matched = any(p[1].match(clean_url) or p[1].match(clean_url.rstrip('/')) or p[1].match(clean_url + '/') for p in patterns)
    if not matched:
        unmatched.append((file, url))

print(f'Unmatched URLs count: {len(set(unmatched))}')
for f, u in sorted(set(unmatched)):
    print(f'  [{f}] -> {u}')
