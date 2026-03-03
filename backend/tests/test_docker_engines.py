"""Quick check that Piston and Judge0 Docker containers are working."""
import requests, json

print("=== PISTON (localhost:2000) ===")
try:
    r = requests.get("http://localhost:2000/api/v2/runtimes", timeout=30)
    runtimes = r.json()
    langs = [rt["language"] for rt in runtimes]
    print(f"  Status: {r.status_code} OK")
    print(f"  Runtimes: {len(runtimes)} => {', '.join(langs)}")

    # Execute Python
    r2 = requests.post("http://localhost:2000/api/v2/execute", json={
        "language": "python",
        "version": "3.10.0",
        "files": [{"content": "print(42)"}],
    }, timeout=15)
    out = r2.json().get("run", {}).get("stdout", "").strip()
    print(f"  Python print(42) -> '{out}' [{'PASS' if out=='42' else 'FAIL'}]")

    # Execute Python with stdin
    r3 = requests.post("http://localhost:2000/api/v2/execute", json={
        "language": "python",
        "version": "3.10.0",
        "files": [{"content": "n=int(input())\nprint(n*2)"}],
        "stdin": "21",
    }, timeout=15)
    out2 = r3.json().get("run", {}).get("stdout", "").strip()
    print(f"  Python stdin 21*2 -> '{out2}' [{'PASS' if out2=='42' else 'FAIL'}]")

    # Execute JavaScript
    if "javascript" in langs:
        r4 = requests.post("http://localhost:2000/api/v2/execute", json={
            "language": "javascript",
            "version": "18.15.0",
            "files": [{"content": "console.log(7*6)"}],
        }, timeout=15)
        out3 = r4.json().get("run", {}).get("stdout", "").strip()
        print(f"  JS 7*6 -> '{out3}' [{'PASS' if out3=='42' else 'FAIL'}]")

except Exception as e:
    print(f"  ERROR: {e}")

print()
print("=== JUDGE0 (localhost:2358) ===")
try:
    r5 = requests.get("http://localhost:2358/system_info", timeout=15)
    print(f"  Status: {r5.status_code} OK")
    info = r5.json()
    for k in ["queue", "cpu", "memory"]:
        if k in info:
            print(f"  {k}: {info[k]}")
except Exception as e:
    print(f"  ERROR: {e}")

print()
print("=== GROQ API ===")
try:
    import os
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("GROQ_API_KEY", "")
    r6 = requests.post("https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile",
              "messages": [{"role": "user", "content": "Reply with only: OK"}],
              "max_tokens": 5},
        timeout=15)
    if r6.status_code == 200:
        msg = r6.json()["choices"][0]["message"]["content"]
        print(f"  Groq API: {r6.status_code} -> '{msg}' [PASS]")
    else:
        print(f"  Groq API: {r6.status_code} [{r6.text[:100]}]")
except Exception as e:
    print(f"  ERROR: {e}")

print()
print("=== ALL ENGINES CHECKED ===")
