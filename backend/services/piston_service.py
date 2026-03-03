"""
Piston Code Execution Service
==============================
Free, open-source code execution engine — no API key required.
Primary replacement for Judge0 (which has a 100 calls/day free tier limit).

Docs: https://github.com/engineer-man/piston

IMPORTANT — PUBLIC API RESTRICTION (as of Feb 2026):
  The hosted API at emkc.org is now whitelist-only. To use Piston you must
  either request whitelist access on the Piston Discord, or self-host:

      docker run -d --name piston -p 2000:2000 ghcr.io/engineer-man/piston

  Then set PISTON_API_URL=http://localhost:2000/api/v2 in your .env.

If Piston is unavailable the system falls back to Judge0 automatically.
Supports 30+ languages.
"""

import os
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Piston API endpoint — default points to local self-hosted instance
# (public emkc.org API is whitelist-only since Feb 2026)
PISTON_API_URL = os.getenv("PISTON_API_URL", "http://localhost:2000/api/v2")

# ---------------------------------------------------------------------------
# Language mapping — Piston uses language names + version
# ---------------------------------------------------------------------------
# Map common language names to Piston's expected format
PISTON_LANGUAGES = {
    "python": {"language": "python", "version": "3.10.0"},
    "python3": {"language": "python", "version": "3.10.0"},
    "javascript": {"language": "javascript", "version": "18.15.0"},
    "nodejs": {"language": "javascript", "version": "18.15.0"},
    "java": {"language": "java", "version": "15.0.2"},
    "c": {"language": "c", "version": "10.2.0"},
    "cpp": {"language": "c++", "version": "10.2.0"},
    "c++": {"language": "c++", "version": "10.2.0"},
    "csharp": {"language": "csharp.net", "version": "5.0.201"},
    "c#": {"language": "csharp.net", "version": "5.0.201"},
    "go": {"language": "go", "version": "1.16.2"},
    "golang": {"language": "go", "version": "1.16.2"},
    "rust": {"language": "rust", "version": "1.68.2"},
    "ruby": {"language": "ruby", "version": "3.0.1"},
    "php": {"language": "php", "version": "8.2.3"},
    "typescript": {"language": "typescript", "version": "5.0.3"},
    "swift": {"language": "swift", "version": "5.3.3"},
    "kotlin": {"language": "kotlin", "version": "1.8.20"},
    "scala": {"language": "scala", "version": "3.2.2"},
    "bash": {"language": "bash", "version": "5.2.0"},
    "r": {"language": "r", "version": "4.1.1"},
    "perl": {"language": "perl", "version": "5.36.0"},
    "lua": {"language": "lua", "version": "5.4.4"},
    "haskell": {"language": "haskell", "version": "9.0.1"},
}


def _get_piston_lang(language: str) -> Optional[Dict]:
    """Resolve a language name to Piston's language + version."""
    key = language.lower().strip()
    return PISTON_LANGUAGES.get(key)


def get_supported_languages() -> List[str]:
    """Return list of supported language names."""
    return sorted(set(PISTON_LANGUAGES.keys()))


def list_runtimes() -> List[Dict]:
    """Fetch available runtimes from the Piston API."""
    try:
        import requests
        resp = requests.get(f"{PISTON_API_URL}/runtimes", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Failed to fetch Piston runtimes: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Single code execution
# ---------------------------------------------------------------------------

def execute_code_piston(
    source_code: str,
    language: str,
    stdin: str = "",
    timeout_seconds: int = 10,
    memory_limit: int = 256_000_000,  # 256 MB in bytes
) -> Dict:
    """
    Execute code using the Piston API.

    Args:
        source_code: The code to execute.
        language: Programming language name (e.g., "python", "javascript").
        stdin: Standard input to feed the program.
        timeout_seconds: Max execution time in seconds.
        memory_limit: Max memory in bytes (Piston may not enforce on public API).

    Returns:
        {
            "status": "success" | "error" | "timeout" | "runtime_error",
            "stdout": "...",
            "stderr": "...",
            "exit_code": 0,
            "execution_time_ms": 123,
            "language": "python",
            "version": "3.10.0"
        }
    """
    import requests

    lang_info = _get_piston_lang(language)
    if not lang_info:
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"Unsupported language: {language}. Supported: {', '.join(get_supported_languages())}",
            "exit_code": -1,
            "execution_time_ms": 0,
            "language": language,
            "version": "unknown",
        }

    payload = {
        "language": lang_info["language"],
        "version": lang_info["version"],
        "files": [{"content": source_code}],
        "stdin": stdin,
        "run_timeout": timeout_seconds * 1000,  # Piston expects milliseconds
        "compile_timeout": 10000,
        "run_memory_limit": memory_limit,
    }

    try:
        start_time = time.time()
        resp = requests.post(
            f"{PISTON_API_URL}/execute",
            json=payload,
            timeout=max(timeout_seconds + 5, 30),
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        if resp.status_code == 429:
            return {
                "status": "error",
                "stdout": "",
                "stderr": "Rate limited by Piston API. Please try again shortly.",
                "exit_code": -1,
                "execution_time_ms": elapsed_ms,
                "language": lang_info["language"],
                "version": lang_info["version"],
            }

        resp.raise_for_status()
        data = resp.json()

        run = data.get("run", {})
        compile_result = data.get("compile", {})

        # Check for compilation errors first
        if compile_result and compile_result.get("code") and compile_result["code"] != 0:
            return {
                "status": "compile_error",
                "stdout": compile_result.get("stdout", ""),
                "stderr": compile_result.get("stderr", "Compilation failed"),
                "exit_code": compile_result.get("code", -1),
                "execution_time_ms": elapsed_ms,
                "language": lang_info["language"],
                "version": data.get("version", lang_info["version"]),
            }

        # Check for timeout signal
        if run.get("signal") == "SIGKILL":
            return {
                "status": "timeout",
                "stdout": run.get("stdout", ""),
                "stderr": run.get("stderr", "Execution timed out"),
                "exit_code": run.get("code", -1),
                "execution_time_ms": elapsed_ms,
                "language": lang_info["language"],
                "version": data.get("version", lang_info["version"]),
            }

        exit_code = run.get("code", -1)
        status = "success" if exit_code == 0 else "runtime_error"

        return {
            "status": status,
            "stdout": run.get("stdout", ""),
            "stderr": run.get("stderr", ""),
            "exit_code": exit_code,
            "execution_time_ms": elapsed_ms,
            "language": lang_info["language"],
            "version": data.get("version", lang_info["version"]),
        }

    except Exception as exc:
        logger.error("Piston execution failed: %s", exc)
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"Execution engine error: {str(exc)}",
            "exit_code": -1,
            "execution_time_ms": 0,
            "language": language,
            "version": "unknown",
        }


# ---------------------------------------------------------------------------
# Batch test case execution (run code against multiple stdin/stdout pairs)
# ---------------------------------------------------------------------------

def run_test_cases(
    source_code: str,
    language: str,
    test_cases: List[Dict],
    timeout_seconds: int = 10,
) -> Dict:
    """
    Run code against a list of test cases sequentially.

    Args:
        source_code: The candidate's code.
        language: Programming language.
        test_cases: List of {"input": "stdin_value", "output": "expected_stdout"}.
        timeout_seconds: Max execution time per test case.

    Returns:
        {
            "total_tests": N,
            "passed": P,
            "failed": F,
            "results": [
                {
                    "test_index": 0,
                    "input": "...",
                    "expected_output": "...",
                    "actual_output": "...",
                    "passed": true/false,
                    "status": "success" | "error" | ...
                    "execution_time_ms": 123,
                    "stderr": "..."
                }
            ],
            "overall_status": "passed" | "partial" | "failed"
        }
    """
    results = []
    passed = 0
    total = len(test_cases)

    for idx, tc in enumerate(test_cases):
        stdin_val = tc.get("input", tc.get("stdin", ""))
        expected = tc.get("output", tc.get("expected_output", "")).strip()

        exec_result = execute_code_piston(
            source_code=source_code,
            language=language,
            stdin=stdin_val,
            timeout_seconds=timeout_seconds,
        )

        actual = exec_result.get("stdout", "").strip()
        is_pass = (exec_result["status"] == "success" and actual == expected)

        if is_pass:
            passed += 1

        results.append({
            "test_index": idx,
            "input": stdin_val,
            "expected_output": expected,
            "actual_output": actual,
            "passed": is_pass,
            "status": exec_result["status"],
            "execution_time_ms": exec_result.get("execution_time_ms", 0),
            "stderr": exec_result.get("stderr", ""),
        })

    failed = total - passed
    if passed == total:
        overall = "passed"
    elif passed > 0:
        overall = "partial"
    else:
        overall = "failed"

    return {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "results": results,
        "overall_status": overall,
    }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def health_check() -> Dict:
    """Quick health check — run a simple Python program."""
    result = execute_code_piston(
        source_code='print("piston_ok")',
        language="python",
        stdin="",
        timeout_seconds=5,
    )
    is_healthy = (
        result["status"] == "success"
        and "piston_ok" in result.get("stdout", "")
    )
    return {
        "healthy": is_healthy,
        "engine": "piston",
        "api_url": PISTON_API_URL,
        "result": result,
    }
