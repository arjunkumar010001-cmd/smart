"""
Code Execution Service
=======================
Two-engine strategy for code execution:

  PRIMARY:  Piston API (free, open-source, no API key needed, 30+ languages)
  FALLBACK: Judge0 API (RapidAPI — 100 calls/day free tier, or self-hosted CE)

The high-level ``execute_code()`` function automatically tries Piston first.
If Piston fails (network issue, unsupported language, etc.), it falls back to Judge0.

Free tier: Piston has no hard daily limit (rate-limited per IP).
           Judge0 RapidAPI has ~100 submissions/day free tier.
"""

import os
import time
import json
import logging
import base64
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language ID mapping (Judge0 CE language IDs)
# ---------------------------------------------------------------------------

LANGUAGE_IDS = {
    "python": 71,       # Python 3.8.1
    "python3": 71,
    "javascript": 63,   # Node.js 12.14.0
    "nodejs": 63,
    "java": 62,          # Java (OpenJDK 13.0.1)
    "c": 50,             # C (GCC 9.2.0)
    "cpp": 54,           # C++ (GCC 9.2.0)
    "c++": 54,
    "csharp": 51,        # C# (Mono 6.6.0.161)
    "c#": 51,
    "ruby": 72,          # Ruby 2.7.0
    "go": 60,            # Go 1.13.5
    "rust": 73,          # Rust 1.40.0
    "typescript": 74,    # TypeScript 3.7.4
    "php": 68,           # PHP 7.4.1
    "swift": 83,         # Swift 5.2.3
    "kotlin": 78,        # Kotlin 1.3.70
    "r": 80,             # R 4.0.0
    "sql": 82,           # SQL (SQLite 3.27.2)
}


def get_supported_languages() -> List[str]:
    """Return list of supported programming languages."""
    return sorted(set(LANGUAGE_IDS.keys()))


def get_language_id(language: str) -> Optional[int]:
    """Map language name to Judge0 language ID."""
    return LANGUAGE_IDS.get(language.lower().strip())


# ---------------------------------------------------------------------------
# Judge0 API Client
# ---------------------------------------------------------------------------

class Judge0Client:
    """
    Client for Judge0 API (RapidAPI hosted or self-hosted).

    Configuration via environment variables:
      JUDGE0_API_URL      — Base URL (default: RapidAPI Judge0 CE)
      JUDGE0_API_KEY      — RapidAPI API key
      JUDGE0_API_HOST     — RapidAPI host header
      JUDGE0_SELF_HOSTED  — Set to "true" for self-hosted (no auth headers)
    """

    def __init__(
        self,
        api_url: str = None,
        api_key: str = None,
        api_host: str = None,
        self_hosted: bool = False,
    ):
        self.api_url = (
            api_url
            or os.getenv("JUDGE0_API_URL", "https://judge0-ce.p.rapidapi.com")
        ).rstrip("/")

        self.api_key = api_key or os.getenv("JUDGE0_API_KEY", "")
        self.api_host = api_host or os.getenv(
            "JUDGE0_API_HOST", "judge0-ce.p.rapidapi.com"
        )
        self.self_hosted = self_hosted or os.getenv("JUDGE0_SELF_HOSTED", "").lower() == "true"

    # ----- helpers -----

    def _headers(self) -> Dict:
        if self.self_hosted:
            return {"Content-Type": "application/json"}
        return {
            "Content-Type": "application/json",
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": self.api_host,
        }

    @staticmethod
    def _b64encode(text: str) -> str:
        return base64.b64encode(text.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _b64decode(text: str) -> str:
        if not text:
            return ""
        try:
            return base64.b64decode(text).decode("utf-8")
        except Exception:
            return text

    # ----- submission -----

    def submit(
        self,
        source_code: str,
        language: str,
        stdin: str = "",
        expected_output: str = "",
        time_limit: float = 5.0,
        memory_limit: int = 128000,
    ) -> Optional[str]:
        """
        Submit code for execution. Returns submission token.

        Args:
            source_code: The code to execute
            language: Programming language name
            stdin: Input to provide via STDIN
            expected_output: Expected STDOUT for auto-comparison
            time_limit: CPU time limit in seconds
            memory_limit: Memory limit in KB
        """
        import requests as _requests

        lang_id = get_language_id(language)
        if not lang_id:
            logger.error("Unsupported language: %s", language)
            return None

        payload = {
            "source_code": self._b64encode(source_code),
            "language_id": lang_id,
            "stdin": self._b64encode(stdin) if stdin else "",
            "expected_output": self._b64encode(expected_output) if expected_output else "",
            "cpu_time_limit": str(time_limit),
            "memory_limit": memory_limit,
        }

        try:
            resp = _requests.post(
                f"{self.api_url}/submissions?base64_encoded=true&wait=false",
                headers=self._headers(),
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            token = resp.json().get("token")
            logger.info("Submitted code, token=%s", token)
            return token
        except Exception as exc:
            logger.error("Judge0 submit failed: %s", exc)
            return None

    def get_result(self, token: str, max_wait: int = 30) -> Dict:
        """
        Poll for submission result. Returns structured result dict.

        Polling strategy: exponential backoff up to max_wait seconds.
        """
        import requests as _requests

        url = f"{self.api_url}/submissions/{token}?base64_encoded=true&fields=*"
        elapsed = 0
        interval = 1.0

        while elapsed < max_wait:
            try:
                resp = _requests.get(url, headers=self._headers(), timeout=10)
                resp.raise_for_status()
                data = resp.json()

                status_id = data.get("status", {}).get("id", 0)

                # Status IDs: 1=In Queue, 2=Processing, 3=Accepted, 4=Wrong Answer,
                # 5=TLE, 6=Compilation Error, 7-12=Runtime errors, 13=Internal Error
                if status_id >= 3:
                    return self._format_result(data)

                time.sleep(interval)
                elapsed += interval
                interval = min(interval * 1.5, 5.0)

            except Exception as exc:
                logger.error("Judge0 poll failed: %s", exc)
                return {
                    "status": "error",
                    "status_id": -1,
                    "description": f"Polling error: {str(exc)}",
                    "stdout": "",
                    "stderr": "",
                    "compile_output": "",
                    "time": "0",
                    "memory": 0,
                }

        return {
            "status": "timeout",
            "status_id": -2,
            "description": "Polling timed out",
            "stdout": "",
            "stderr": "",
            "compile_output": "",
            "time": "0",
            "memory": 0,
        }

    def _format_result(self, data: Dict) -> Dict:
        """Normalize Judge0 response into a clean result dict."""
        status = data.get("status", {})
        return {
            "status": status.get("description", "Unknown"),
            "status_id": status.get("id", 0),
            "description": status.get("description", ""),
            "stdout": self._b64decode(data.get("stdout", "")),
            "stderr": self._b64decode(data.get("stderr", "")),
            "compile_output": self._b64decode(data.get("compile_output", "")),
            "time": data.get("time", "0"),
            "memory": data.get("memory", 0),
            "token": data.get("token", ""),
        }

    # ----- batch operations -----

    def submit_batch(
        self,
        source_code: str,
        language: str,
        test_cases: List[Dict],
        time_limit: float = 5.0,
        memory_limit: int = 128000,
    ) -> List[Optional[str]]:
        """
        Submit code against multiple test cases. Returns list of tokens.

        Args:
            test_cases: [{"input": "...", "output": "..."}, ...]
        """
        import requests as _requests

        lang_id = get_language_id(language)
        if not lang_id:
            return []

        submissions = []
        for tc in test_cases:
            submissions.append({
                "source_code": self._b64encode(source_code),
                "language_id": lang_id,
                "stdin": self._b64encode(tc.get("input", "")),
                "expected_output": self._b64encode(tc.get("output", "")),
                "cpu_time_limit": str(time_limit),
                "memory_limit": memory_limit,
            })

        try:
            resp = _requests.post(
                f"{self.api_url}/submissions/batch?base64_encoded=true",
                headers=self._headers(),
                json={"submissions": submissions},
                timeout=30,
            )
            resp.raise_for_status()
            tokens = [item.get("token") for item in resp.json()]
            return tokens
        except Exception as exc:
            logger.error("Judge0 batch submit failed: %s", exc)
            return []

    def get_batch_results(
        self, tokens: List[str], max_wait: int = 60
    ) -> List[Dict]:
        """Poll for batch results."""
        import requests as _requests

        valid_tokens = [t for t in tokens if t]
        if not valid_tokens:
            return []

        token_str = ",".join(valid_tokens)
        url = f"{self.api_url}/submissions/batch?tokens={token_str}&base64_encoded=true&fields=*"

        elapsed = 0
        interval = 1.5

        while elapsed < max_wait:
            try:
                resp = _requests.get(url, headers=self._headers(), timeout=15)
                resp.raise_for_status()
                data = resp.json()

                submissions = data.get("submissions", data) if isinstance(data, dict) else data

                all_done = all(
                    sub.get("status", {}).get("id", 0) >= 3
                    for sub in submissions
                )

                if all_done:
                    return [self._format_result(sub) for sub in submissions]

                time.sleep(interval)
                elapsed += interval
                interval = min(interval * 1.5, 5.0)

            except Exception as exc:
                logger.error("Judge0 batch poll failed: %s", exc)
                break

        # Return whatever we have
        return []


# ---------------------------------------------------------------------------
# High-level execution interface
# ---------------------------------------------------------------------------

def execute_code(
    source_code: str,
    language: str,
    test_cases: List[Dict],
    time_limit: float = 5.0,
    memory_limit: int = 128000,
) -> Dict:
    """
    Execute source code against test cases and return aggregated results.

    Strategy:
      1. Try Piston API first (free, no API key needed).
      2. If Piston fails, fall back to Judge0 (RapidAPI or self-hosted).
      3. If both fail, return a clear error.

    Args:
        source_code: Candidate's submitted code
        language: Programming language
        test_cases: [{"input": "...", "output": "..."}, ...]
        time_limit: Per-test time limit in seconds
        memory_limit: Memory limit in KB

    Returns:
        {
            "total_tests": N,
            "passed": P,
            "failed": F,
            "results": [{...}, ...],
            "overall_status": "Accepted" | "Partial" | "Failed" | "Error",
            "engine": "piston" | "judge0",
            "max_time": "0.01",
            "max_memory": 1234
        }
    """
    # ---- Engine 1: Piston (free, primary) ----
    try:
        from backend.services.piston_service import run_test_cases as piston_run

        piston_result = piston_run(
            source_code=source_code,
            language=language,
            test_cases=test_cases,
            timeout_seconds=int(time_limit),
        )

        # Check if Piston actually executed (not just returned API errors)
        if piston_result and piston_result.get("total_tests", 0) > 0:
            results_list = piston_result.get("results", [])
            # If ALL results are "error" status (e.g. 401, network failure),
            # that means Piston itself failed — fall through to Judge0
            all_engine_errors = all(
                r.get("status") == "error" for r in results_list
            ) if results_list else True

            if not all_engine_errors:
                # Piston actually ran code — use these results
                overall = piston_result["overall_status"]
                if overall == "passed":
                    overall = "Accepted"
                elif overall == "partial":
                    overall = "Partial"
                elif overall == "failed":
                    overall = "Failed"

                return {
                    "total_tests": piston_result["total_tests"],
                    "passed": piston_result["passed"],
                    "failed": piston_result["failed"],
                    "results": piston_result["results"],
                    "overall_status": overall,
                    "engine": "piston",
                    "max_time": "N/A",
                    "max_memory": 0,
                }
            else:
                logger.warning("Piston returned all errors — falling back to Judge0")

    except ImportError:
        logger.warning("Piston service not available, falling back to Judge0")
    except Exception as exc:
        logger.warning("Piston execution failed (%s), falling back to Judge0", exc)

    # ---- Engine 2: Judge0 (fallback) ----
    client = Judge0Client()

    if not client.api_key and not client.self_hosted:
        return {
            "total_tests": len(test_cases),
            "passed": 0,
            "failed": len(test_cases),
            "results": [],
            "overall_status": "Error",
            "engine": "none",
            "error": "No code execution engine available. Piston failed and Judge0 API key not configured.",
        }

    # Prefer batch API if multiple test cases
    if len(test_cases) > 1:
        tokens = client.submit_batch(
            source_code, language, test_cases, time_limit, memory_limit
        )
        if tokens:
            results = client.get_batch_results(tokens)
        else:
            results = []
    else:
        # Single test case
        results = []
        for tc in test_cases:
            token = client.submit(
                source_code, language,
                stdin=tc.get("input", ""),
                expected_output=tc.get("output", ""),
                time_limit=time_limit,
                memory_limit=memory_limit,
            )
            if token:
                result = client.get_result(token)
                results.append(result)

    # Aggregate
    passed = sum(1 for r in results if r.get("status_id") == 3)
    failed = len(results) - passed
    max_time = max((float(r.get("time", 0) or 0) for r in results), default=0)
    max_memory = max((r.get("memory", 0) or 0 for r in results), default=0)

    if passed == len(test_cases):
        overall = "Accepted"
    elif passed > 0:
        overall = "Partial"
    else:
        overall = "Failed"

    return {
        "total_tests": len(test_cases),
        "passed": passed,
        "failed": failed,
        "results": results,
        "overall_status": overall,
        "engine": "judge0",
        "max_time": f"{max_time:.3f}",
        "max_memory": max_memory,
    }
