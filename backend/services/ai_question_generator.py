"""
AI-Powered Question Generation Engine
======================================
Generates high-quality, unique assessment questions using:
  - Primary:   Groq API (LLaMA 3 / Mixtral) — completely free, no credit card
  - Fallback1: Anthropic Claude for best quality (if key configured)
  - Fallback2: OpenAI GPT-4o-mini for budget fallback (if key configured)

Supports question types: coding, mcq, aptitude, debugging, logical_reasoning
Caches generated questions in MongoDB for reuse and deduplication.
Includes experience-level calibration, executable test cases, cost guards.
"""

import os
import json
import uuid
import logging
import hashlib
from datetime import datetime, date
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cost guard — daily call limits per provider
# ---------------------------------------------------------------------------
_daily_call_counts: Dict[str, Dict[str, int]] = {}   # {"2026-02-22": {"groq": 5, ...}}

DAILY_LIMITS = {
    "groq": int(os.getenv("GROQ_DAILY_LIMIT", "500")),
    "claude": int(os.getenv("CLAUDE_DAILY_LIMIT", "50")),
    "openai": int(os.getenv("OPENAI_DAILY_LIMIT", "50")),
}


def _check_rate_limit(provider: str) -> bool:
    """Return True if the provider is within its daily budget."""
    today = str(date.today())
    if today not in _daily_call_counts:
        _daily_call_counts.clear()
        _daily_call_counts[today] = {}
    count = _daily_call_counts[today].get(provider, 0)
    return count < DAILY_LIMITS.get(provider, 100)


def _record_call(provider: str) -> None:
    today = str(date.today())
    if today not in _daily_call_counts:
        _daily_call_counts.clear()
        _daily_call_counts[today] = {}
    _daily_call_counts[today][provider] = _daily_call_counts[today].get(provider, 0) + 1


# ---------------------------------------------------------------------------
# System prompt — NO JSON comments, real test cases, experience calibration
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert technical assessment designer for a hiring platform.
Your job is to generate high-quality, unique assessment questions for candidates
based on the provided parameters.

You must always respond in strict JSON format only. No extra text. No explanation.
No comments inside the JSON (JSON does not support comments).

Rules:
- Never repeat a question that has been used before (a list of used question IDs may be provided).
- Adjust complexity based on BOTH the difficulty level AND the experience level:
    * "fresher" + "easy" = basic fundamentals and simple syntax
    * "fresher" + "hard" = tricky edge cases but still foundational
    * "senior" + "easy" = straightforward but real-world scenario
    * "senior" + "hard" = system design patterns, concurrency, optimization
- For coding questions, include:
    * problem statement, input/output format, constraints
    * at least 2 visible examples with input and expected output
    * at least 2 hidden test cases with EXACT executable stdin and expected stdout
      (these will be fed directly to a code execution engine — they must be precise)
    * starter_code as a function signature
- For debugging questions, provide broken code and include test cases
  in the same format as coding questions.
- For MCQ / aptitude / logical_reasoning questions, include 4 options with
  exactly one correct answer and a brief explanation.
- Every question MUST have a unique "id" field starting with "aiq_".
- Always tag each question with: topic, difficulty, type, estimated_time_minutes.

Respond with ONLY this JSON structure (no markdown fences, no comments):

{
  "questions": [
    {
      "id": "aiq_<unique_hex>",
      "type": "coding | mcq | aptitude | debugging | logical_reasoning",
      "topic": "string",
      "difficulty": "easy | medium | hard",
      "estimated_time_minutes": 10,
      "question": "full question text",
      "input_format": "description of input (coding/debugging only)",
      "output_format": "description of output (coding/debugging only)",
      "constraints": "constraints text (coding/debugging only)",
      "examples": [
        {"input": "exact stdin", "output": "exact expected stdout"}
      ],
      "hidden_test_cases": [
        {"input": "exact stdin", "output": "exact expected stdout"}
      ],
      "starter_code": "function signature (coding/debugging only)",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "correct_answer": "A",
      "explanation": "why the answer is correct"
    }
  ]
}

Fields for coding/debugging: id, type, topic, difficulty, estimated_time_minutes, question, input_format, output_format, constraints, examples, hidden_test_cases, starter_code.
Fields for mcq/aptitude/logical_reasoning: id, type, topic, difficulty, estimated_time_minutes, question, options, correct_answer, explanation.
Omit irrelevant fields per type (do NOT include null or empty arrays for unused fields)."""


def _build_user_prompt(
    count: int,
    job_role: str,
    question_type: str,
    topic: str,
    difficulty: str,
    language: str = "Python",
    experience_level: str = "mid",
    used_ids: List[str] = None,
) -> str:
    """Build the dynamic user prompt for the AI model."""

    used_block = ""
    if used_ids:
        used_block = f"\n- Already used question IDs (DO NOT reuse these): {json.dumps(used_ids)}"

    lang_line = ""
    if question_type in ("coding", "debugging"):
        lang_line = (
            f"\n- Programming language: {language}"
            f"\n- For hidden_test_cases, provide EXACT stdin/stdout pairs that "
            f"can be piped directly into the program. The candidate's code will "
            f"read from stdin and print to stdout."
        )

    return (
        f"Generate {count} assessment question(s) with the following parameters:\n"
        f"- Role: {job_role}\n"
        f"- Experience level: {experience_level} (fresher / mid / senior)\n"
        f"- Type: {question_type}\n"
        f"- Topic: {topic}\n"
        f"- Difficulty: {difficulty}"
        f"{lang_line}"
        f"{used_block}\n\n"
        "Calibrate the difficulty for the experience level. "
        "A 'hard' question for a fresher is NOT the same as a 'hard' question for a senior developer.\n\n"
        "Respond ONLY with the JSON object. No markdown fences. No commentary."
    )


# ---------------------------------------------------------------------------
# Provider: Groq — FREE tier, primary generator
# ---------------------------------------------------------------------------

def _generate_with_groq(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
) -> Optional[Dict]:
    """Call Groq API (free LLaMA 3 / Mixtral) and return parsed JSON."""
    try:
        import requests as _requests

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "temperature": 0.7,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        resp = _requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()

        body = resp.json()
        text = body["choices"][0]["message"]["content"]
        return _parse_json_response(text)
    except Exception as exc:
        logger.error("Groq generation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Provider: Claude (Anthropic) — paid, fallback #1
# ---------------------------------------------------------------------------

def _generate_with_claude(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
) -> Optional[Dict]:
    """Call Anthropic Claude API and return parsed JSON."""
    try:
        import requests as _requests

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": "claude-sonnet-4-6-20250514",
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        resp = _requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()

        body = resp.json()
        text = body["content"][0]["text"]
        return _parse_json_response(text)
    except Exception as exc:
        logger.error("Claude generation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Provider: GPT-4o-mini (OpenAI) — paid, fallback #2
# ---------------------------------------------------------------------------

def _generate_with_openai(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
) -> Optional[Dict]:
    """Call OpenAI GPT-4o-mini API and return parsed JSON."""
    try:
        import requests as _requests

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o-mini",
            "temperature": 0.7,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        resp = _requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()

        body = resp.json()
        text = body["choices"][0]["message"]["content"]
        return _parse_json_response(text)
    except Exception as exc:
        logger.error("OpenAI generation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Shared JSON parsing (strips markdown fences, comments, etc.)
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> Optional[Dict]:
    """Clean and parse JSON from an LLM response."""
    text = text.strip()
    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()

    # Remove any // comments that LLMs sometimes sneak in
    import re
    text = re.sub(r'//[^\n]*', '', text)
    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed: %s — text: %s", exc, text[:300])
        return None


# ---------------------------------------------------------------------------
# Uniqueness enforcement
# ---------------------------------------------------------------------------

def _enforce_unique_ids(questions: List[Dict], used_ids: List[str]) -> List[Dict]:
    """
    Guarantee every question has a truly unique ID.
    AI-generated IDs can collide — this re-mints any duplicates.
    """
    seen = set(used_ids)
    for q in questions:
        qid = q.get("id", "")
        if not qid or qid in seen:
            q["id"] = f"aiq_{uuid.uuid4().hex[:12]}"
        seen.add(q["id"])
    return questions


# ---------------------------------------------------------------------------
# Fallback question generator (static, no API needed)
# ---------------------------------------------------------------------------

def _generate_fallback_questions(
    count: int,
    question_type: str,
    topic: str,
    difficulty: str,
    language: str = "python",
) -> List[Dict]:
    """
    Last-resort static question generator when ALL APIs fail.
    Returns basic but valid questions so the assessment can still proceed.
    """
    questions = []
    for i in range(count):
        qid = f"fallback_{uuid.uuid4().hex[:10]}"
        if question_type in ("coding", "debugging"):
            questions.append({
                "id": qid,
                "type": question_type,
                "topic": topic,
                "difficulty": difficulty,
                "estimated_time_minutes": {"easy": 5, "medium": 10, "hard": 15}.get(difficulty, 10),
                "question": f"Write a {language} function that takes a list of integers and returns the {'sum' if i % 3 == 0 else 'maximum' if i % 3 == 1 else 'sorted version'} of the list.",
                "input_format": "First line: N (number of elements). Second line: N space-separated integers.",
                "output_format": "Single line with the result.",
                "constraints": "1 <= N <= 1000, -10^6 <= element <= 10^6",
                "examples": [
                    {"input": "5\n1 2 3 4 5", "output": "15" if i % 3 == 0 else "5" if i % 3 == 1 else "1 2 3 4 5"},
                    {"input": "3\n-1 0 1", "output": "0" if i % 3 == 0 else "1" if i % 3 == 1 else "-1 0 1"},
                ],
                "hidden_test_cases": [
                    {"input": "1\n42", "output": "42"},
                    {"input": "4\n3 1 4 1", "output": "9" if i % 3 == 0 else "4" if i % 3 == 1 else "1 1 3 4"},
                ],
                "starter_code": f"def solve(nums):\n    # Your code here\n    pass",
                "source": "fallback",
            })
        else:
            questions.append({
                "id": qid,
                "type": question_type,
                "topic": topic,
                "difficulty": difficulty,
                "estimated_time_minutes": {"easy": 2, "medium": 3, "hard": 5}.get(difficulty, 3),
                "question": f"What is the time complexity of {'binary search' if i % 4 == 0 else 'merge sort' if i % 4 == 1 else 'hash table lookup' if i % 4 == 2 else 'BFS traversal'}?",
                "options": [
                    "A. O(1)",
                    "B. O(log n)",
                    "C. O(n)",
                    "D. O(n log n)",
                ],
                "correct_answer": "B" if i % 4 == 0 else "D" if i % 4 == 1 else "A" if i % 4 == 2 else "C",
                "explanation": "Standard time complexity for this algorithm.",
                "source": "fallback",
            })
    return questions


# ---------------------------------------------------------------------------
# Question bank cache helpers (MongoDB)
# ---------------------------------------------------------------------------

def _question_fingerprint(q: Dict) -> str:
    """Deterministic hash of a question to detect duplicates."""
    raw = json.dumps(
        {k: q.get(k) for k in ("question", "type", "topic", "difficulty")},
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _fetch_cached_questions(
    db,
    job_role: str,
    question_type: str,
    topic: str,
    difficulty: str,
    used_ids: List[str],
    count: int,
) -> List[Dict]:
    """Try to pull enough unused questions from the AI question bank."""
    try:
        query = {
            "source": {"$in": ["ai_generated", "groq", "claude", "openai"]},
            "job_role": job_role,
            "type": question_type,
            "topic": topic,
            "difficulty": difficulty,
            "is_active": True,
        }
        if used_ids:
            query["id"] = {"$nin": used_ids}

        cached = list(
            db["ai_questions"]
            .find(query)
            .sort("usage_count", 1)
            .limit(count)
        )
        return cached
    except Exception as exc:
        logger.error("Cache lookup failed: %s", exc)
        return []


def _cache_questions(db, questions: List[Dict], job_role: str, source: str) -> None:
    """Store freshly generated questions for future reuse."""
    try:
        docs = []
        for q in questions:
            fp = _question_fingerprint(q)
            # Skip if exact duplicate already exists
            if db["ai_questions"].find_one({"fingerprint": fp}):
                continue
            doc = {**q}
            doc["source"] = source
            doc["job_role"] = job_role
            doc["fingerprint"] = fp
            doc["is_active"] = True
            doc["usage_count"] = 0
            doc["created_at"] = datetime.utcnow()
            docs.append(doc)

        if docs:
            db["ai_questions"].insert_many(docs, ordered=False)
    except Exception as exc:
        logger.warning("Cache write failed (non-fatal): %s", exc)


def _increment_usage(db, question_ids: List[str]) -> None:
    """Bump usage_count for served questions."""
    try:
        if question_ids:
            db["ai_questions"].update_many(
                {"id": {"$in": question_ids}},
                {"$inc": {"usage_count": 1}},
            )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_questions(
    db,
    count: int,
    job_role: str,
    question_type: str,
    topic: str,
    difficulty: str,
    language: str = "Python",
    experience_level: str = "mid",
    used_ids: List[str] = None,
    groq_api_key: str = None,
    anthropic_api_key: str = None,
    openai_api_key: str = None,
) -> Dict:
    """
    Main entry point — generate assessment questions.

    Strategy:
      1. Look in MongoDB cache for unused questions matching criteria.
      2. If not enough, call Groq (free) → Claude → GPT (fallbacks).
      3. If ALL APIs fail, use static fallback questions.
      4. Enforce unique IDs on every question.
      5. Cache the new questions for future sessions.
      6. Return the final question set.

    Returns:
        {"questions": [...], "source": "cache"|"groq"|"claude"|"openai"|"fallback"|"mixed", "count": N}
    """
    used_ids = used_ids or []

    # Step 1 — check cache
    cached = _fetch_cached_questions(
        db, job_role, question_type, topic, difficulty, used_ids, count
    )

    if len(cached) >= count:
        served = cached[:count]
        served = _enforce_unique_ids(served, used_ids)
        _increment_usage(db, [q["id"] for q in served])
        for q in served:
            q.pop("_id", None)
            q.pop("fingerprint", None)
            q.pop("job_role", None)
        return {"questions": served, "source": "cache", "count": len(served)}

    # Step 2 — generate with AI (waterfall: Groq → Claude → OpenAI)
    need = count - len(cached)
    all_used = used_ids + [q["id"] for q in cached]

    user_prompt = _build_user_prompt(
        need, job_role, question_type, topic, difficulty, language,
        experience_level, all_used
    )

    result = None
    source = "unknown"

    # Try Groq first (FREE)
    groq_key = groq_api_key or os.getenv("GROQ_API_KEY", "")
    if groq_key and _check_rate_limit("groq"):
        result = _generate_with_groq(SYSTEM_PROMPT, user_prompt, groq_key)
        if result:
            source = "groq"
            _record_call("groq")

    # Fallback 1: Claude (PAID — only if Groq failed)
    if not result:
        api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if api_key and _check_rate_limit("claude"):
            logger.info("Groq unavailable, falling back to Claude (PAID)")
            result = _generate_with_claude(SYSTEM_PROMPT, user_prompt, api_key)
            if result:
                source = "claude"
                _record_call("claude")

    # Fallback 2: OpenAI (PAID — only if both above failed)
    if not result:
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        if api_key and _check_rate_limit("openai"):
            logger.info("Claude unavailable, falling back to OpenAI (PAID)")
            result = _generate_with_openai(SYSTEM_PROMPT, user_prompt, api_key)
            if result:
                source = "openai"
                _record_call("openai")

    # Step 3 — if ALL APIs failed, use static fallback
    if not result or "questions" not in result:
        logger.warning("All AI providers failed — using static fallback questions")
        generated = _generate_fallback_questions(
            need, question_type, topic, difficulty, language
        )
        source = "fallback"
    else:
        generated = result["questions"]

    # Step 4 — enforce unique IDs
    generated = _enforce_unique_ids(generated, all_used)

    # Step 5 — cache new questions (skip fallback)
    if source != "fallback":
        _cache_questions(db, generated, job_role, source)

    # Merge cached + generated
    combined = []
    for q in cached:
        q.pop("_id", None)
        q.pop("fingerprint", None)
        q.pop("job_role", None)
        combined.append(q)
    combined.extend(generated)
    combined = _enforce_unique_ids(combined, used_ids)

    _increment_usage(db, [q["id"] for q in combined])

    final_source = "mixed" if cached else source
    return {"questions": combined[:count], "source": final_source, "count": min(len(combined), count)}


def evaluate_answer_with_ai(
    question: Dict,
    answer: str,
    groq_api_key: str = None,
    anthropic_api_key: str = None,
) -> Dict:
    """
    Use AI to evaluate a subjective or partial answer.
    Tries Groq (free) first, then Claude if configured.

    Returns: {"score": 0-100, "feedback": "...", "is_correct": bool}
    """
    eval_prompt = (
        "You are an expert evaluator. Grade the following answer.\n\n"
        f"Question: {question.get('question', '')}\n"
        f"Expected behavior / Correct answer: {question.get('correct_answer', question.get('explanation', 'N/A'))}\n"
        f"Candidate's answer: {answer}\n\n"
        "Respond ONLY in JSON (no comments, no markdown):\n"
        '{"score": <0-100>, "feedback": "<brief feedback>", "is_correct": <true or false>}'
    )

    # Try Groq first
    groq_key = groq_api_key or os.getenv("GROQ_API_KEY", "")
    if groq_key and _check_rate_limit("groq"):
        try:
            import requests as _requests
            resp = _requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    "max_tokens": 512,
                    "messages": [{"role": "user", "content": eval_prompt}],
                },
                timeout=30,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            _record_call("groq")
            parsed = _parse_json_response(text)
            if parsed:
                return parsed
        except Exception as exc:
            logger.error("Groq evaluation failed: %s", exc)

    # Fallback: Claude
    api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if api_key and _check_rate_limit("claude"):
        try:
            import requests as _requests
            resp = _requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6-20250514",
                    "max_tokens": 512,
                    "messages": [{"role": "user", "content": eval_prompt}],
                },
                timeout=30,
            )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"]
            _record_call("claude")
            parsed = _parse_json_response(text)
            if parsed:
                return parsed
        except Exception as exc:
            logger.error("Claude evaluation failed: %s", exc)

    return {"score": 0, "feedback": "AI evaluation unavailable — all providers failed", "is_correct": False}
