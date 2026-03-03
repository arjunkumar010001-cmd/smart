"""
OpenTriviaDB Integration Service
==================================
Fetches free aptitude / general knowledge questions from the Open Trivia Database.
  - Completely free, no API key required
  - Provides MCQ questions across 24 categories
  - Supplements AI-generated questions for aptitude/verbal reasoning

API: https://opentdb.com/api.php
"""

import html
import uuid
import random
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category mapping (OpenTriviaDB category IDs)
# ---------------------------------------------------------------------------

CATEGORIES = {
    "general_knowledge": 9,
    "science_computers": 18,
    "science_mathematics": 19,
    "science_nature": 17,
    "science_gadgets": 30,
    "geography": 22,
    "history": 23,
    "politics": 24,
    "mythology": 20,
    "entertainment_books": 10,
    "entertainment_film": 11,
    "entertainment_music": 12,
    "sports": 21,
    "art": 25,
    "animals": 27,
    "vehicles": 28,
}

# Map assessment topics to OpenTriviaDB categories
TOPIC_CATEGORY_MAP = {
    "general": 9,
    "general_knowledge": 9,
    "verbal_reasoning": 9,
    "logical_reasoning": 19,
    "mathematics": 19,
    "math": 19,
    "probability": 19,
    "statistics": 19,
    "quantitative": 19,
    "computers": 18,
    "computer_science": 18,
    "science": 17,
    "geography": 22,
    "history": 23,
    "current_affairs": 24,
}

DIFFICULTY_MAP = {
    "easy": "easy",
    "medium": "medium",
    "hard": "hard",
}


def _decode_html(text: str) -> str:
    """Decode HTML entities in OpenTriviaDB responses."""
    return html.unescape(text)


def fetch_trivia_questions(
    count: int = 5,
    topic: str = "general",
    difficulty: str = "medium",
) -> Dict:
    """
    Fetch questions from OpenTriviaDB.

    Args:
        count: Number of questions (max 50 per request)
        topic: Topic name (mapped to category)
        difficulty: easy / medium / hard

    Returns:
        {
            "questions": [...],
            "source": "opentriviadb",
            "count": N
        }
    """
    try:
        import requests as _requests

        category_id = TOPIC_CATEGORY_MAP.get(topic.lower(), 9)
        otdb_difficulty = DIFFICULTY_MAP.get(difficulty.lower(), "medium")

        url = "https://opentdb.com/api.php"
        params = {
            "amount": min(count, 50),
            "category": category_id,
            "difficulty": otdb_difficulty,
            "type": "multiple",  # Always get MCQ for consistency
        }

        resp = _requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("response_code") != 0:
            logger.warning("OpenTriviaDB returned code %s", data.get("response_code"))
            # Code 1 = no results for this query, try without filters
            if data.get("response_code") == 1:
                params.pop("category", None)
                params.pop("difficulty", None)
                resp = _requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                if data.get("response_code") != 0:
                    return {"questions": [], "source": "opentriviadb", "count": 0}

        questions = []
        for item in data.get("results", []):
            q_text = _decode_html(item["question"])
            correct = _decode_html(item["correct_answer"])
            incorrects = [_decode_html(a) for a in item["incorrect_answers"]]

            # Build options with labels
            all_answers = incorrects + [correct]
            random.shuffle(all_answers)
            labels = ["A", "B", "C", "D"]
            options = [f"{labels[i]}. {ans}" for i, ans in enumerate(all_answers)]

            # Find correct label
            correct_label = labels[all_answers.index(correct)]

            # Map difficulty to estimated time
            time_map = {"easy": 2, "medium": 3, "hard": 5}

            question = {
                "id": f"otdb_{uuid.uuid4().hex[:10]}",
                "type": "aptitude",
                "topic": topic,
                "difficulty": difficulty,
                "estimated_time_minutes": time_map.get(difficulty, 3),
                "question": q_text,
                "options": options,
                "correct_answer": correct_label,
                "explanation": f"The correct answer is {correct}.",
                "source": "opentriviadb",
                "category": _decode_html(item.get("category", "")),
            }
            questions.append(question)

        return {
            "questions": questions,
            "source": "opentriviadb",
            "count": len(questions),
        }

    except Exception as exc:
        logger.error("OpenTriviaDB fetch failed: %s", exc)
        return {"questions": [], "source": "opentriviadb", "count": 0, "error": str(exc)}


def fetch_mixed_aptitude(
    count: int = 10,
    difficulty: str = "medium",
    topics: List[str] = None,
) -> Dict:
    """
    Fetch a mix of aptitude questions across multiple topics.

    Args:
        count: Total questions desired
        difficulty: Difficulty level
        topics: List of topics to mix (default: general + math + computers)

    Returns:
        {"questions": [...], "source": "opentriviadb", "count": N}
    """
    if not topics:
        topics = ["general", "mathematics", "computers"]

    per_topic = max(1, count // len(topics))
    remainder = count - per_topic * len(topics)

    all_questions = []
    for i, topic in enumerate(topics):
        n = per_topic + (1 if i < remainder else 0)
        result = fetch_trivia_questions(count=n, topic=topic, difficulty=difficulty)
        all_questions.extend(result.get("questions", []))

    random.shuffle(all_questions)

    return {
        "questions": all_questions[:count],
        "source": "opentriviadb",
        "count": min(len(all_questions), count),
    }
