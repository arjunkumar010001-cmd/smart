"""Quick verification test for all 5 issues"""
import urllib.request
import json
import sys

BASE = 'http://127.0.0.1:5000/api'

def api(method, path, data=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f'{BASE}{path}', data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

passed = 0
failed = 0

def check(name, condition, detail=''):
    global passed, failed
    if condition:
        print(f'  PASS: {name}')
        passed += 1
    else:
        print(f'  FAIL: {name} - {detail}')
        failed += 1

# ── Login ──
print('\n=== Login Tests ===')
code, data = api('POST', '/auth/login', {'email': 'recruiter@test.com', 'password': 'password123'})
token = data.get('access_token', '')
check('Recruiter login', code == 200 and token, f'code={code}')
role = data.get('user', {}).get('role', '')
check('Role is recruiter', role == 'recruiter', f'role={role}')

# ── Issue 1: Assessment Save ──
print('\n=== Issue 1: Assessment Config Save ===')
code, data = api('POST', '/smart-assessments/configs', {
    'title': 'Verification Test Assessment',
    'job_id': 'test_verify_001',
    'job_role': 'Python Developer',
    'questions_config': {'mcq': 5, 'coding': 2},
    'duration_minutes': 60,
    'skills': ['python', 'flask']
}, token)
check('Create config (recruiter)', code in (200, 201), f'code={code} body={json.dumps(data)[:200]}')

# Get configs
code, data = api('GET', '/smart-assessments/configs', token=token)
check('List configs (recruiter)', code == 200, f'code={code}')

# ── Issue 2: Audit Routes ──
print('\n=== Issue 2: Audit / Fairness Audit ===')
code, data = api('GET', '/audit/logs?limit=5', token=token)
check('Get audit logs (recruiter)', code == 200, f'code={code} body={json.dumps(data)[:200]}')

code, data = api('GET', '/audit/report?days=30', token=token)
check('Generate audit report (recruiter)', code == 200, f'code={code} body={json.dumps(data)[:200]}')

# ── Issue 3 & 4: Resume download (needs a candidate with resume) ──
print('\n=== Issue 3 & 4: Resume/PII (structural check) ===')
# Just verify the route exists and doesn't crash for missing candidate
code, data = api('GET', '/candidates/000000000000000000000000/resume', token=token)
check('Resume route accessible', code in (404, 200, 400), f'code={code}')

# ── Assessment question routes ──
print('\n=== Additional: Assessment Question Routes ===')
code, data = api('GET', '/assessments/questions', token=token)
check('Get questions (recruiter)', code == 200, f'code={code} body={json.dumps(data)[:200]}')

# ── DSR Routes ──  
print('\n=== DSR Routes (structural check) ===')
code, data = api('GET', '/dsr/consent', token=token)
check('Get consent status', code in (200, 404), f'code={code}')

# ── Summary ──
print(f'\n{"="*50}')
print(f'Results: {passed} passed, {failed} failed out of {passed+failed}')
if failed > 0:
    sys.exit(1)
print('All checks passed!')
