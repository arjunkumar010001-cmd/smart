"""Install language runtimes in Piston container."""
import requests

URL = "http://localhost:2000/api/v2"
HEADERS = {"Content-Type": "application/json"}

# First list ALL available packages
print("Available packages:")
r = requests.get(f"{URL}/packages", timeout=10)
pkgs = r.json()
languages_available = set()
for p in pkgs:
    lang = p["language"]
    ver = p["language_version"]
    installed = p.get("installed", False)
    tag = " [INSTALLED]" if installed else ""
    print(f"  {lang} {ver}{tag}")
    languages_available.add(lang)

print(f"\nTotal available: {len(pkgs)} packages across {len(languages_available)} languages")
print(f"Languages: {sorted(languages_available)}")
print()

# Install the ones we want
TO_INSTALL = [
    ("python", "3.10.0"),
    ("java", "15.0.2"),
]

# Also try any available version if exact not found
for lang, ver in TO_INSTALL:
    matches = [p for p in pkgs if p["language"] == lang]
    if not matches:
        print(f"  [{lang}] not available - skipping")
        continue
    # Pick the requested version or first available
    exact = [p for p in matches if p["language_version"] == ver]
    if exact:
        pkg = exact[0]
    else:
        pkg = matches[0]
        print(f"  [{lang}] version {ver} not available, using {pkg['language_version']}")
    
    if pkg.get("installed"):
        print(f"  [{lang} {pkg['language_version']}] already installed")
        continue

    actual_ver = pkg["language_version"]
    print(f"  Installing {lang} {actual_ver} ...")
    r2 = requests.post(f"{URL}/packages/{lang}/{actual_ver}", headers=HEADERS, json={}, timeout=300)
    if r2.status_code == 200:
        print(f"  [{lang} {actual_ver}] INSTALLED OK")
    else:
        print(f"  [{lang} {actual_ver}] FAILED: {r2.status_code} {r2.text[:200]}")

print()
# Verify
r3 = requests.get(f"{URL}/runtimes", timeout=5)
runtimes = r3.json()
print(f"Total runtimes installed: {len(runtimes)}")
for rt in runtimes:
    print(f"  {rt['language']} {rt['version']}")
