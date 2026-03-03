"""
Smart Assessment Models (Extended)
===================================
Extended data structures for the AI-powered assessment system.
Supplements the existing assessment.py models with:
  - AssessmentConfig:  HR-defined assessment parameters per job role
  - SmartQuestion:     Extended question schema (coding, debugging, etc.)
  - SmartSession:      Assessment session tracking with full lifecycle
  - CodeSubmission:    Code execution submission tracking
"""

from datetime import datetime
from typing import List, Dict, Optional


class AssessmentConfig:
    """
    HR / Admin defined assessment configuration for a job role.
    Controls how the question generation engine builds the assessment.
    """

    def __init__(
        self,
        title: str,
        job_role: str,
        created_by: str,
        job_id: Optional[str] = None,
        description: str = "",
        # Question type mix
        question_types: List[str] = None,
        # Difficulty distribution e.g. {"easy": 30, "medium": 50, "hard": 20}
        difficulty_mix: Dict[str, int] = None,
        # Topics to assess
        topics: List[str] = None,
        # Total number of questions
        total_questions: int = 15,
        # Duration in minutes
        duration_minutes: int = 60,
        # Time limit per question in minutes (0=no per-question limit)
        time_per_question: int = 0,
        # Passing score percentage
        passing_score: int = 70,
        # Programming language for coding questions
        coding_language: str = "python",
        # Max attempts allowed
        max_attempts: int = 1,
        # Whether to randomize question order
        randomize: bool = True,
        # Whether to show results immediately
        show_results: bool = True,
        # Whether to use AI generation vs manual question bank
        use_ai_generation: bool = True,
        # Whether to supplement with OpenTriviaDB for aptitude
        use_trivia_supplement: bool = True,
        # Experience level for difficulty calibration
        experience_level: str = "mid",
        # Tags
        tags: List[str] = None,
    ):
        self.title = title
        self.job_role = job_role
        self.created_by = created_by
        self.job_id = job_id
        self.description = description
        self.question_types = question_types or ["mcq", "coding"]
        self.difficulty_mix = difficulty_mix or {"easy": 30, "medium": 50, "hard": 20}
        self.topics = topics or ["general"]
        self.total_questions = total_questions
        self.duration_minutes = duration_minutes
        self.time_per_question = time_per_question
        self.passing_score = passing_score
        self.coding_language = coding_language
        self.max_attempts = max_attempts
        self.randomize = randomize
        self.show_results = show_results
        self.use_ai_generation = use_ai_generation
        self.use_trivia_supplement = use_trivia_supplement
        self.experience_level = experience_level
        self.tags = tags or []
        self.is_active = True
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.sessions_count = 0
        self.average_score = 0.0

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "job_role": self.job_role,
            "created_by": self.created_by,
            "job_id": self.job_id,
            "description": self.description,
            "question_types": self.question_types,
            "difficulty_mix": self.difficulty_mix,
            "topics": self.topics,
            "total_questions": self.total_questions,
            "duration_minutes": self.duration_minutes,
            "time_per_question": self.time_per_question,
            "passing_score": self.passing_score,
            "coding_language": self.coding_language,
            "max_attempts": self.max_attempts,
            "randomize": self.randomize,
            "show_results": self.show_results,
            "use_ai_generation": self.use_ai_generation,
            "use_trivia_supplement": self.use_trivia_supplement,
            "experience_level": self.experience_level,
            "tags": self.tags,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "sessions_count": self.sessions_count,
            "average_score": self.average_score,
        }


class SmartSession:
    """
    A candidate's assessment session — tracks the full lifecycle from
    question generation through submission and scoring.
    """

    def __init__(
        self,
        config_id: str,
        candidate_id: str,
        questions: List[Dict] = None,
        status: str = "pending",
    ):
        self.config_id = config_id
        self.candidate_id = candidate_id
        self.questions = questions or []
        self.status = status  # pending, in_progress, completed, abandoned, expired
        self.answers = {}          # question_id -> submitted answer
        self.time_spent = {}       # question_id -> seconds spent
        self.question_scores = {}  # question_id -> scoring result
        self.code_submissions = {} # question_id -> [{code, result, timestamp}, ...]
        self.current_question_index = 0
        self.started_at = None
        self.completed_at = None
        self.expires_at = None
        # Final results
        self.total_score = 0.0
        self.max_score = 0.0
        self.percentage = 0.0
        self.final_percentage = 0.0
        self.efficiency_bonus = 0.0
        self.passed = False
        self.verdict = "pending"
        self.type_breakdown = {}
        self.strengths = []
        self.weaknesses = []
        self.created_at = datetime.utcnow()

    def to_dict(self) -> Dict:
        return {
            "config_id": self.config_id,
            "candidate_id": self.candidate_id,
            "questions": self.questions,
            "status": self.status,
            "answers": self.answers,
            "time_spent": self.time_spent,
            "question_scores": self.question_scores,
            "code_submissions": self.code_submissions,
            "current_question_index": self.current_question_index,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "expires_at": self.expires_at,
            "total_score": self.total_score,
            "max_score": self.max_score,
            "percentage": self.percentage,
            "final_percentage": self.final_percentage,
            "efficiency_bonus": self.efficiency_bonus,
            "passed": self.passed,
            "verdict": self.verdict,
            "type_breakdown": self.type_breakdown,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "created_at": self.created_at,
        }


class CodeSubmission:
    """Individual code submission within a session."""

    def __init__(
        self,
        session_id: str,
        question_id: str,
        candidate_id: str,
        source_code: str,
        language: str,
    ):
        self.session_id = session_id
        self.question_id = question_id
        self.candidate_id = candidate_id
        self.source_code = source_code
        self.language = language
        self.submitted_at = datetime.utcnow()
        self.execution_result = {}
        self.score = 0.0
        self.passed_tests = 0
        self.total_tests = 0
        self.execution_time = "0"
        self.memory_used = 0
        self.status = "pending"  # pending, executing, completed, error

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "question_id": self.question_id,
            "candidate_id": self.candidate_id,
            "source_code": self.source_code,
            "language": self.language,
            "submitted_at": self.submitted_at,
            "execution_result": self.execution_result,
            "score": self.score,
            "passed_tests": self.passed_tests,
            "total_tests": self.total_tests,
            "execution_time": self.execution_time,
            "memory_used": self.memory_used,
            "status": self.status,
        }
