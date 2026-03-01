"""
Assessment Scoring Engine
==========================
Comprehensive scoring for all question types:
  - MCQ / Aptitude: Direct option matching
  - Coding:         Judge0 test case pass/fail + efficiency bonus
  - Debugging:      Judge0 execution of fixed code
  - Logical Reasoning: Option matching with explanation credit
  - Short Answer:   AI-assisted partial credit evaluation

Produces detailed score breakdowns per question and overall.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Score calculation constants
# ---------------------------------------------------------------------------

# Weights for different question types in overall score
TYPE_WEIGHTS = {
    "coding": 1.5,       # Coding questions are worth more
    "debugging": 1.3,
    "mcq": 1.0,
    "aptitude": 1.0,
    "logical_reasoning": 1.0,
}

# Efficiency bonus thresholds (percentage of time limit used)
EFFICIENCY_BONUS = {
    0.25: 15,  # Used ≤25% of time → +15% bonus
    0.50: 10,  # Used ≤50% of time → +10% bonus
    0.75: 5,   # Used ≤75% of time → +5% bonus
}

# Coding partial credit (per test case proportion)
CODING_PARTIAL_CREDIT = True


def score_mcq_question(
    question: Dict,
    answer: str,
) -> Dict:
    """
    Score a multiple-choice / aptitude / logical_reasoning question.

    Returns:
        {
            "is_correct": bool,
            "score": float (0 or points),
            "max_score": float,
            "feedback": str
        }
    """
    correct = question.get("correct_answer", "").strip().upper()
    submitted = answer.strip().upper() if answer else ""

    # Handle both "A" and "A. Whatever" formats
    if len(submitted) > 1 and submitted[1] == ".":
        submitted = submitted[0]
    if len(correct) > 1 and correct[1] == ".":
        correct = correct[0]

    is_correct = submitted == correct
    points = question.get("points", 1)

    return {
        "is_correct": is_correct,
        "score": float(points) if is_correct else 0.0,
        "max_score": float(points),
        "feedback": question.get("explanation", "") if not is_correct else "Correct!",
    }


def score_coding_question(
    question: Dict,
    execution_result: Dict,
) -> Dict:
    """
    Score a coding question based on Judge0 execution results.

    Args:
        question: The question definition with test cases
        execution_result: Result from judge0_service.execute_code()

    Returns:
        {
            "is_correct": bool,
            "score": float,
            "max_score": float,
            "passed_tests": int,
            "total_tests": int,
            "execution_time": str,
            "memory_used": int,
            "test_results": [...],
            "feedback": str
        }
    """
    total_tests = execution_result.get("total_tests", 0)
    passed = execution_result.get("passed", 0)
    points = question.get("points", 10)

    if total_tests == 0:
        return {
            "is_correct": False,
            "score": 0.0,
            "max_score": float(points),
            "passed_tests": 0,
            "total_tests": 0,
            "execution_time": "0",
            "memory_used": 0,
            "test_results": [],
            "feedback": execution_result.get("error", "No test cases executed"),
        }

    # Calculate score
    if passed == total_tests:
        score = float(points)
        is_correct = True
        feedback = f"All {total_tests} test cases passed!"
    elif CODING_PARTIAL_CREDIT and passed > 0:
        # Partial credit: proportional to tests passed
        score = round(float(points) * (passed / total_tests), 2)
        is_correct = False
        feedback = f"Passed {passed}/{total_tests} test cases. Partial credit awarded."
    else:
        score = 0.0
        is_correct = False
        # Provide helpful error info
        results = execution_result.get("results", [])
        error_msg = ""
        for r in results:
            if r.get("stderr"):
                error_msg = r["stderr"][:200]
                break
            if r.get("compile_output"):
                error_msg = r["compile_output"][:200]
                break
        feedback = f"Failed all test cases. {error_msg}".strip()

    return {
        "is_correct": is_correct,
        "score": score,
        "max_score": float(points),
        "passed_tests": passed,
        "total_tests": total_tests,
        "execution_time": execution_result.get("max_time", "0"),
        "memory_used": execution_result.get("max_memory", 0),
        "test_results": execution_result.get("results", []),
        "feedback": feedback,
        "overall_status": execution_result.get("overall_status", "Unknown"),
    }


def score_debugging_question(
    question: Dict,
    execution_result: Dict,
) -> Dict:
    """
    Score a debugging question — same as coding but the candidate fixes broken code.
    Uses the same scoring logic as coding questions.
    """
    return score_coding_question(question, execution_result)


def calculate_efficiency_bonus(
    time_spent_seconds: int,
    time_limit_seconds: int,
) -> float:
    """
    Calculate time-efficiency bonus percentage.

    Args:
        time_spent_seconds: Actual time spent
        time_limit_seconds: Allocated time limit

    Returns:
        Bonus percentage (0-15)
    """
    if time_limit_seconds <= 0:
        return 0.0

    ratio = time_spent_seconds / time_limit_seconds
    for threshold, bonus in sorted(EFFICIENCY_BONUS.items()):
        if ratio <= threshold:
            return float(bonus)
    return 0.0


# ---------------------------------------------------------------------------
# Session-level scoring
# ---------------------------------------------------------------------------

def calculate_session_score(
    questions: List[Dict],
    answers: Dict[str, Dict],
    time_spent: Dict[str, int],
    passing_score: float = 70.0,
    negative_marking: bool = False,
    negative_marking_penalty: float = 0.5,
) -> Dict:
    """
    Calculate overall session score from individual question scores.

    Args:
        questions: List of question definitions (with 'id', 'type', 'points')
        answers: Dict mapping question_id -> scoring result from score_*_question
        time_spent: Dict mapping question_id -> seconds spent
        passing_score: Minimum percentage to pass
        negative_marking: If True, apply penalty for wrong answers
        negative_marking_penalty: Fraction of points deducted for wrong answers
            (e.g. 0.5 = deduct half the question's points)

    Negative-marking rules:
        - MCQ/aptitude/logical_reasoning: -penalty if is_correct == False AND
          the candidate actually submitted an answer (unanswered → 0, no penalty)
        - Coding/debugging: penalty ONLY when score == 0 (complete failure).
          Partial scores (e.g. 1/20 test cases pass) get partial credit, no deduction.

    Returns:
        {
            "total_score": float,
            "max_score": float,
            "percentage": float,
            "passed": bool,
            "efficiency_bonus": float,
            "final_percentage": float,
            "penalty_applied": float,   # total points deducted (0.0 if disabled)
            "time_analysis": {...},
            "type_breakdown": {...},
            "strengths": [...],
            "weaknesses": [...],
            "verdict": "pass" | "review" | "fail"
        }
    """
    total_score = 0.0
    max_score = 0.0
    total_time = 0
    total_penalty = 0.0
    type_scores = {}

    MCQ_TYPES = {"mcq", "aptitude", "logical_reasoning"}
    CODE_TYPES = {"coding", "debugging"}

    for q in questions:
        q_id = q.get("id", "")
        q_type = q.get("type", "mcq")
        q_points = q.get("points", 1)
        weight = TYPE_WEIGHTS.get(q_type, 1.0)

        weighted_max = q_points * weight
        max_score += weighted_max

        result = answers.get(q_id, {})
        raw_score = result.get("score", 0.0)
        weighted_score = raw_score * weight
        penalty = 0.0

        # ── Negative marking ────────────────────────────────────────
        if negative_marking and result:
            # Only penalize if the candidate actually submitted an answer.
            # An empty result dict means unanswered → no penalty.
            is_wrong = not result.get("is_correct", False)

            if q_type in MCQ_TYPES and is_wrong:
                # MCQ: penalize wrong answers (not unanswered)
                penalty = q_points * negative_marking_penalty * weight
                total_penalty += penalty

            elif q_type in CODE_TYPES and raw_score == 0.0 and is_wrong:
                # Coding/debugging: penalize ONLY on complete failure (score == 0).
                # Partial credit (score > 0) is NOT penalized.
                penalty = q_points * negative_marking_penalty * weight
                total_penalty += penalty

        total_score += weighted_score - penalty

        t = time_spent.get(q_id, 0)
        total_time += t

        # Track per-type performance
        if q_type not in type_scores:
            type_scores[q_type] = {"earned": 0.0, "max": 0.0, "count": 0, "correct": 0, "penalties": 0.0}
        type_scores[q_type]["earned"] += weighted_score - penalty
        type_scores[q_type]["max"] += weighted_max
        type_scores[q_type]["count"] += 1
        type_scores[q_type]["penalties"] += penalty
        if result.get("is_correct"):
            type_scores[q_type]["correct"] += 1

    # Clamp total_score to 0 (can't go negative)
    total_score = max(0.0, total_score)

    # Base percentage
    percentage = round((total_score / max_score * 100) if max_score > 0 else 0, 2)

    # Efficiency bonus
    total_time_limit = sum(
        q.get("estimated_time_minutes", 5) * 60 for q in questions
    )
    eff_bonus = calculate_efficiency_bonus(total_time, total_time_limit)
    final_percentage = min(100.0, round(percentage + eff_bonus, 2))

    # Strengths / weaknesses
    strengths = []
    weaknesses = []
    type_breakdown = {}

    for q_type, data in type_scores.items():
        pct = round((data["earned"] / data["max"] * 100) if data["max"] > 0 else 0, 1)
        type_breakdown[q_type] = {
            "score": round(data["earned"], 2),
            "max_score": round(data["max"], 2),
            "percentage": pct,
            "questions": data["count"],
            "correct": data["correct"],
            "penalties": round(data["penalties"], 2),
        }
        if pct >= 80:
            strengths.append(q_type)
        elif pct < 50:
            weaknesses.append(q_type)

    # Verdict
    if final_percentage >= passing_score:
        verdict = "pass"
    elif final_percentage >= passing_score * 0.8:
        verdict = "review"
    else:
        verdict = "fail"

    passed = final_percentage >= passing_score

    return {
        "total_score": round(total_score, 2),
        "max_score": round(max_score, 2),
        "percentage": percentage,
        "passed": passed,
        "efficiency_bonus": eff_bonus,
        "final_percentage": final_percentage,
        "penalty_applied": round(total_penalty, 2),
        "negative_marking_enabled": negative_marking,
        "time_analysis": {
            "total_seconds": total_time,
            "total_minutes": round(total_time / 60, 1),
            "allocated_minutes": round(total_time_limit / 60, 1),
            "efficiency_ratio": round(total_time / total_time_limit, 2) if total_time_limit > 0 else 0,
        },
        "type_breakdown": type_breakdown,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "verdict": verdict,
    }
