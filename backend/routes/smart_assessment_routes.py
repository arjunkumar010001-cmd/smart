"""
Smart Assessment Routes
========================
AI-powered assessment endpoints for the Smart Hiring System.

Endpoints:
  HR / Admin:
    POST   /api/smart-assessments/configs              — Create assessment config
    GET    /api/smart-assessments/configs              — List configs
    GET    /api/smart-assessments/configs/<id>         — Get config detail
    PUT    /api/smart-assessments/configs/<id>         — Update config
    DELETE /api/smart-assessments/configs/<id>         — Deactivate config
    GET    /api/smart-assessments/configs/<id>/analytics — Config analytics

  Question Generation:
    POST   /api/smart-assessments/generate             — Generate questions (AI)
    GET    /api/smart-assessments/trivia               — Fetch trivia questions
    GET    /api/smart-assessments/languages             — Supported languages

  Candidate:
    GET    /api/smart-assessments/available             — List available assessments
    POST   /api/smart-assessments/sessions/<config_id>/start — Start session
    GET    /api/smart-assessments/sessions/<session_id> — Get session state
    POST   /api/smart-assessments/sessions/<session_id>/answer — Submit answer
    POST   /api/smart-assessments/sessions/<session_id>/code   — Submit code
    POST   /api/smart-assessments/sessions/<session_id>/finish — Finish & grade
    GET    /api/smart-assessments/my-sessions           — List my sessions
    GET    /api/smart-assessments/sessions/<session_id>/results — Detailed results

  HR Dashboard:
    GET    /api/smart-assessments/dashboard              — Aggregated dashboard
    GET    /api/smart-assessments/sessions/<session_id>/review — Session review
"""

import os
import random
import math
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
import logging

from backend.models.database import get_db
from backend.models.smart_assessment import AssessmentConfig, SmartSession, CodeSubmission
from backend.security.rbac import require_permission, Permissions
from backend.services.ai_question_generator import generate_questions, evaluate_answer_with_ai
from backend.services.judge0_service import execute_code, get_supported_languages
from backend.services.opentriviadb_service import fetch_trivia_questions, fetch_mixed_aptitude
from backend.services.assessment_scoring_engine import (
    score_mcq_question,
    score_coding_question,
    score_debugging_question,
    calculate_session_score,
)
from backend.services.proctoring_service import check_blacklist, ensure_session_directories, SNAPSHOTS_DIR, RECORDINGS_DIR
import subprocess
import tempfile

logger = logging.getLogger(__name__)
bp = Blueprint("smart_assessments", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_info(current_user):
    """Extract user_id and role from JWT identity."""
    if isinstance(current_user, str):
        user_id = current_user
        db = get_db()
        user = db["users"].find_one({"_id": ObjectId(user_id)})
        return user_id, user.get("role") if user else None
    return current_user.get("user_id"), current_user.get("role")


def _serialize_doc(doc):
    """Convert MongoDB doc for JSON response."""
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    for key in ("created_at", "updated_at", "started_at", "completed_at", "expires_at", "submitted_at"):
        if key in doc and hasattr(doc[key], "isoformat"):
            doc[key] = doc[key].isoformat()
    return doc


# ============================================================================
# ASSESSMENT CONFIG MANAGEMENT (HR / Admin)
# ============================================================================

@bp.route("/configs", methods=["POST"])
@jwt_required()
@require_permission(Permissions.CREATE_ASSESSMENT)
def create_config():
    """Create a new assessment configuration."""
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role not in ("company", "admin", "recruiter"):
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json()
        required = ["title", "job_role"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        cfg = AssessmentConfig(
            title=data["title"],
            job_role=data["job_role"],
            created_by=user_id,
            job_id=data.get("job_id"),
            description=data.get("description", ""),
            question_types=data.get("question_types", ["mcq", "coding"]),
            difficulty_mix=data.get("difficulty_mix", {"easy": 30, "medium": 50, "hard": 20}),
            topics=data.get("topics", ["general"]),
            total_questions=data.get("total_questions", 15),
            duration_minutes=data.get("duration_minutes", 60),
            time_per_question=data.get("time_per_question", 0),
            passing_score=data.get("passing_score", 70),
            coding_language=data.get("coding_language", "python"),
            max_attempts=data.get("max_attempts", 1),
            randomize=data.get("randomize", True),
            show_results=data.get("show_results", True),
            use_ai_generation=data.get("use_ai_generation", True),
            use_trivia_supplement=data.get("use_trivia_supplement", True),
            experience_level=data.get("experience_level", "mid"),
            tags=data.get("tags", []),
        )

        db = get_db()
        result = db["assessment_configs"].insert_one(cfg.to_dict())
        return jsonify({
            "message": "Assessment config created",
            "config_id": str(result.inserted_id),
        }), 201

    except Exception as e:
        logger.error("create_config error: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/configs", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def list_configs():
    """List assessment configurations."""
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        db = get_db()

        query = {"is_active": True}
        if role == "company":
            query["created_by"] = user_id
        elif role == "candidate":
            pass  # Candidates see all active configs

        configs = list(db["assessment_configs"].find(query).sort("created_at", -1))
        for c in configs:
            _serialize_doc(c)

        return jsonify({"configs": configs, "total": len(configs)}), 200
    except Exception as e:
        logger.error("list_configs error: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/configs/<config_id>", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def get_config(config_id):
    """Get a specific assessment configuration."""
    try:
        db = get_db()
        cfg = db["assessment_configs"].find_one({"_id": ObjectId(config_id)})
        if not cfg:
            return jsonify({"error": "Config not found"}), 404
        return jsonify({"config": _serialize_doc(cfg)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/configs/<config_id>", methods=["PUT"])
@jwt_required()
@require_permission(Permissions.EDIT_ASSESSMENT)
def update_config(config_id):
    """Update an assessment configuration."""
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role not in ("company", "admin", "recruiter"):
            return jsonify({"error": "Unauthorized"}), 403

        db = get_db()
        cfg = db["assessment_configs"].find_one({"_id": ObjectId(config_id)})
        if not cfg:
            return jsonify({"error": "Config not found"}), 404
        if role != "admin" and cfg["created_by"] != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json()
        allowed_fields = [
            "title", "description", "job_role", "job_id", "question_types",
            "difficulty_mix", "topics", "total_questions", "duration_minutes",
            "time_per_question", "passing_score", "coding_language", "max_attempts",
            "randomize", "show_results", "use_ai_generation", "use_trivia_supplement",
            "experience_level", "tags",
        ]
        updates = {k: v for k, v in data.items() if k in allowed_fields}
        updates["updated_at"] = datetime.utcnow()

        db["assessment_configs"].update_one(
            {"_id": ObjectId(config_id)}, {"$set": updates}
        )
        return jsonify({"message": "Config updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/configs/<config_id>", methods=["DELETE"])
@jwt_required()
@require_permission(Permissions.EDIT_ASSESSMENT)
def delete_config(config_id):
    """Soft-delete an assessment configuration."""
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role not in ("company", "admin", "recruiter"):
            return jsonify({"error": "Unauthorized"}), 403

        db = get_db()
        cfg = db["assessment_configs"].find_one({"_id": ObjectId(config_id)})
        if not cfg:
            return jsonify({"error": "Config not found"}), 404
        if role != "admin" and cfg["created_by"] != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        db["assessment_configs"].update_one(
            {"_id": ObjectId(config_id)}, {"$set": {"is_active": False}}
        )
        return jsonify({"message": "Config deactivated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/configs/<config_id>/analytics", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_COMPANY_ANALYTICS)
def config_analytics(config_id):
    """Get analytics for a specific assessment configuration."""
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role not in ("company", "admin", "recruiter"):
            return jsonify({"error": "Unauthorized"}), 403

        db = get_db()
        sessions = list(db["smart_sessions"].find({
            "config_id": config_id, "status": "completed"
        }))

        if not sessions:
            return jsonify({
                "total_sessions": 0, "average_score": 0, "pass_rate": 0,
                "average_time_minutes": 0, "verdict_distribution": {},
            }), 200

        total = len(sessions)
        avg_score = sum(s.get("final_percentage", 0) for s in sessions) / total
        passed = sum(1 for s in sessions if s.get("passed"))

        verdicts = {}
        for s in sessions:
            v = s.get("verdict", "unknown")
            verdicts[v] = verdicts.get(v, 0) + 1

        # Average time
        times = []
        for s in sessions:
            if s.get("started_at") and s.get("completed_at"):
                try:
                    delta = s["completed_at"] - s["started_at"]
                    times.append(delta.total_seconds() / 60)
                except:
                    pass
        avg_time = round(sum(times) / len(times), 1) if times else 0

        return jsonify({
            "total_sessions": total,
            "average_score": round(avg_score, 2),
            "pass_rate": round(passed / total * 100, 2),
            "passed_count": passed,
            "failed_count": total - passed,
            "average_time_minutes": avg_time,
            "verdict_distribution": verdicts,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================================
# QUESTION GENERATION
# ============================================================================

@bp.route("/generate", methods=["POST"])
@jwt_required()
@require_permission(Permissions.CREATE_ASSESSMENT)
def generate_ai_questions():
    """
    Generate questions using AI (Claude / GPT-4o-mini).
    Body: { count, job_role, question_type, topic, difficulty, language, used_ids }
    """
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role not in ("company", "admin", "recruiter"):
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json()
        db = get_db()

        result = generate_questions(
            db=db,
            count=data.get("count", 5),
            job_role=data.get("job_role", "Software Developer"),
            question_type=data.get("question_type", "mcq"),
            topic=data.get("topic", "general"),
            difficulty=data.get("difficulty", "medium"),
            language=data.get("language", "Python"),
            experience_level=data.get("experience_level", "mid"),
            used_ids=data.get("used_ids", []),
        )

        return jsonify(result), 200
    except Exception as e:
        logger.error("generate_ai_questions error: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/trivia", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def get_trivia():
    """Fetch trivia/aptitude questions from OpenTriviaDB."""
    try:
        count = request.args.get("count", 5, type=int)
        topic = request.args.get("topic", "general")
        difficulty = request.args.get("difficulty", "medium")

        result = fetch_trivia_questions(count=count, topic=topic, difficulty=difficulty)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/languages", methods=["GET"])
@jwt_required()
def get_languages():
    """Return supported programming languages for coding questions."""
    return jsonify({"languages": get_supported_languages()}), 200


# ============================================================================
# CANDIDATE SESSION MANAGEMENT
# ============================================================================

@bp.route("/available", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def list_available():
    """List available assessment configs for candidates.

    Bug #1 fix: also surfaces auto-assigned sessions (status='assigned')
    so candidates can see assessments linked to their job applications.
    """
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        db = get_db()

        configs = list(db["assessment_configs"].find({"is_active": True}).sort("created_at", -1))

        # Get candidate's existing sessions
        sessions = list(db["smart_sessions"].find({"candidate_id": user_id}))
        session_map = {}
        for s in sessions:
            cid = s.get("config_id")
            if not cid:
                continue
            if cid not in session_map or s.get("created_at", datetime.min) > session_map[cid].get("created_at", datetime.min):
                session_map[cid] = s

        result = []
        for cfg in configs:
            cfg_id = str(cfg["_id"])
            _serialize_doc(cfg)

            session = session_map.get(cfg_id)
            cfg["session_status"] = session["status"] if session else None
            cfg["session_score"] = session.get("final_percentage") if session else None
            cfg["session_id"] = str(session["_id"]) if session else None
            cfg["session_passed"] = session.get("passed") if session else None
            cfg["attempts_used"] = len([
                s for s in sessions
                if s.get("config_id") == cfg_id and s["status"] == "completed"
            ])
            result.append(cfg)

        return jsonify({"assessments": result, "total": len(result)}), 200
    except Exception as e:
        logger.error("list_available error: %s", e)
        return jsonify({"error": str(e)}), 500


# ─── Proctoring: Snapshot Upload ─────────────────────────────────────────

@bp.route("/proctoring/snapshot", methods=["POST"])
@jwt_required()
def upload_snapshot():
    """
    Upload a proctoring snapshot (base64 JPEG).
    - JWT validates candidate identity
    - session_id must belong to the authenticated candidate
    - Max 500KB per snapshot
    """
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role != "candidate":
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        image_data = data.get("image", "")  # base64 data URL
        reason = data.get("reason", "unknown")
        timestamp = data.get("timestamp", "")

        if not session_id or not image_data:
            return jsonify({"error": "Missing session_id or image"}), 400

        # Validate session ownership
        db = get_db()
        session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session or session.get("candidate_id") != user_id:
            return jsonify({"error": "Unauthorized — session mismatch"}), 403

        # Enforce 500KB limit on the base64 payload
        # Strip data URL prefix if present
        if "," in image_data:
            b64_str = image_data.split(",", 1)[1]
        else:
            b64_str = image_data

        byte_len = len(b64_str) * 3 // 4
        if byte_len > 500 * 1024:
            return jsonify({"error": "Snapshot exceeds 500KB limit"}), 413

        # Decode and save
        import base64
        img_bytes = base64.b64decode(b64_str)

        session_dir = os.path.join(SNAPSHOTS_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)

        safe_ts = timestamp.replace(":", "-").replace(".", "-")[:26] if timestamp else "unknown"
        filename = f"{reason}_{safe_ts}.jpg"
        filepath = os.path.join(session_dir, filename)

        with open(filepath, "wb") as f:
            f.write(img_bytes)

        logger.info("Snapshot saved: %s (%d bytes)", filepath, len(img_bytes))

        # Store snapshot reference in session doc for audit report
        db["smart_sessions"].update_one(
            {"_id": ObjectId(session_id)},
            {"$push": {"snapshots": {
                "filename": filename,
                "reason": reason,
                "timestamp": timestamp,
                "saved_at": datetime.utcnow().isoformat(),
            }}}
        )

        return jsonify({"message": "Snapshot saved", "filename": filename}), 201

    except Exception as e:
        logger.error("upload_snapshot error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/sessions/<config_id>/start", methods=["POST"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def start_session(config_id):
    """
    Start a new assessment session. Generates questions dynamically.
    """
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role != "candidate":
            return jsonify({"error": "Only candidates can start sessions"}), 403

        # ── Blacklist check ──────────────────────────────────────────────
        if check_blacklist(user_id):
            return jsonify({"error": "You are permanently banned from assessments"}), 403

        db = get_db()
        cfg = db["assessment_configs"].find_one({"_id": ObjectId(config_id)})
        if not cfg or not cfg.get("is_active"):
            return jsonify({"error": "Assessment not found or inactive"}), 404

        # Check max attempts
        completed_count = db["smart_sessions"].count_documents({
            "config_id": config_id,
            "candidate_id": user_id,
            "status": "completed",
        })
        if completed_count >= cfg.get("max_attempts", 1):
            return jsonify({"error": "Maximum attempts reached"}), 400

        # Check for existing in-progress session
        existing = db["smart_sessions"].find_one({
            "config_id": config_id,
            "candidate_id": user_id,
            "status": "in_progress",
        })
        if existing:
            _serialize_doc(existing)
            # Hide correct answers from questions
            for q in existing.get("questions", []):
                q.pop("correct_answer", None)
                q.pop("hidden_test_cases", None)
                q.pop("explanation", None)
            return jsonify({"message": "Resuming existing session", "session": existing}), 200

        # ---- Generate questions ----
        all_questions = []
        used_ids = []
        difficulty_mix = cfg.get("difficulty_mix", {"easy": 30, "medium": 50, "hard": 20})
        total = cfg.get("total_questions", 15)
        question_types = cfg.get("question_types", ["mcq"])
        topics = cfg.get("topics", ["general"])
        language = cfg.get("coding_language", "python")
        job_role = cfg.get("job_role", "Software Developer")
        experience_level = cfg.get("experience_level", "mid")

        # Calculate counts per difficulty
        difficulty_counts = {}
        for diff, pct in difficulty_mix.items():
            difficulty_counts[diff] = max(1, math.floor(total * pct / 100))

        # Adjust to match total
        total_assigned = sum(difficulty_counts.values())
        if total_assigned < total:
            difficulty_counts["medium"] = difficulty_counts.get("medium", 0) + (total - total_assigned)
        elif total_assigned > total:
            for diff in ("easy", "hard", "medium"):
                if diff in difficulty_counts and difficulty_counts[diff] > 1:
                    excess = total_assigned - total
                    reduce = min(excess, difficulty_counts[diff] - 1)
                    difficulty_counts[diff] -= reduce
                    total_assigned -= reduce
                    if total_assigned == total:
                        break

        # Distribute across question types and topics
        for difficulty, count in difficulty_counts.items():
            per_type = max(1, count // len(question_types))
            remainder = count - per_type * len(question_types)

            for i, q_type in enumerate(question_types):
                n = per_type + (1 if i < remainder else 0)
                if n <= 0:
                    continue

                topic = random.choice(topics)

                # For aptitude, try OpenTriviaDB first
                if q_type in ("aptitude",) and cfg.get("use_trivia_supplement", True):
                    trivia_result = fetch_trivia_questions(
                        count=n, topic=topic, difficulty=difficulty
                    )
                    trivia_qs = trivia_result.get("questions", [])
                    for q in trivia_qs:
                        q["points"] = {"easy": 5, "medium": 10, "hard": 15}.get(difficulty, 10)
                    all_questions.extend(trivia_qs)
                    used_ids.extend([q["id"] for q in trivia_qs])
                    n -= len(trivia_qs)

                if n > 0 and cfg.get("use_ai_generation", True):
                    gen_result = generate_questions(
                        db=db,
                        count=n,
                        job_role=job_role,
                        question_type=q_type,
                        topic=topic,
                        difficulty=difficulty,
                        language=language,
                        experience_level=experience_level,
                        used_ids=used_ids,
                    )
                    gen_qs = gen_result.get("questions", [])
                    for q in gen_qs:
                        if not q.get("points"):
                            q["points"] = {"easy": 5, "medium": 10, "hard": 15}.get(difficulty, 10)
                    all_questions.extend(gen_qs)
                    used_ids.extend([q.get("id", "") for q in gen_qs])

        # Randomize if configured
        if cfg.get("randomize", True):
            random.shuffle(all_questions)

        # Trim to total
        all_questions = all_questions[:total]

        # Create session
        session = SmartSession(
            config_id=config_id,
            candidate_id=user_id,
            questions=all_questions,
            status="in_progress",
        )
        session.started_at = datetime.utcnow()
        session.expires_at = datetime.utcnow() + timedelta(
            minutes=cfg.get("duration_minutes", 60)
        )

        session_dict = session.to_dict()
        # ── Proctoring fields ────────────────────────────────────────────
        session_dict['proctoring_events'] = []
        session_dict['proctoring_score'] = 0
        session_dict['blacklist_score'] = 0

        result = db["smart_sessions"].insert_one(session_dict)
        session_id = str(result.inserted_id)

        # Create upload directories for snapshots / recordings
        ensure_session_directories(session_id)

        # Prepare safe questions (hide answers)
        safe_questions = []
        for q in all_questions:
            safe_q = {k: v for k, v in q.items()}
            safe_q.pop("correct_answer", None)
            safe_q.pop("hidden_test_cases", None)
            safe_q.pop("explanation", None)
            safe_questions.append(safe_q)

        return jsonify({
            "message": "Assessment started",
            "session_id": session_id,
            "session": {
                "config_id": config_id,
                "title": cfg.get("title", ""),
                "duration_minutes": cfg.get("duration_minutes", 60),
                "total_questions": len(safe_questions),
                "passing_score": cfg.get("passing_score", 70),
                "started_at": session.started_at.isoformat(),
                "expires_at": session.expires_at.isoformat(),
            },
            "questions": safe_questions,
        }), 201

    except Exception as e:
        logger.error("start_session error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/sessions/<session_id>", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def get_session(session_id):
    """Get current session state."""
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        db = get_db()

        session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session:
            return jsonify({"error": "Session not found"}), 404

        # Candidates can only see their own sessions
        if role == "candidate" and session["candidate_id"] != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        _serialize_doc(session)

        # Hide answers if session is still in progress
        if session["status"] == "in_progress":
            for q in session.get("questions", []):
                q.pop("correct_answer", None)
                q.pop("hidden_test_cases", None)
                q.pop("explanation", None)

        return jsonify({"session": session}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/sessions/<session_id>/answer", methods=["POST"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def submit_answer(session_id):
    """
    Submit an answer for a non-coding question (MCQ, aptitude, logical_reasoning).
    Body: { question_id, answer, time_spent_seconds }
    """
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role != "candidate":
            return jsonify({"error": "Unauthorized"}), 403

        # ── Blacklist check ──────────────────────────────────────────────
        if check_blacklist(user_id):
            return jsonify({"error": "You are permanently banned from assessments"}), 403

        db = get_db()
        session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session or session["candidate_id"] != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if session["status"] != "in_progress":
            return jsonify({"error": "Session is not active"}), 400

        # Check expiry
        if session.get("expires_at") and datetime.utcnow() > session["expires_at"]:
            db["smart_sessions"].update_one(
                {"_id": ObjectId(session_id)},
                {"$set": {"status": "expired"}}
            )
            return jsonify({"error": "Session has expired"}), 400

        data = request.get_json()
        question_id = data.get("question_id")
        answer = data.get("answer", "")
        time_seconds = data.get("time_spent_seconds", 0)

        # Find the question
        question = None
        for q in session.get("questions", []):
            if q.get("id") == question_id:
                question = q
                break

        if not question:
            return jsonify({"error": "Question not found in session"}), 404

        # Store answer
        db["smart_sessions"].update_one(
            {"_id": ObjectId(session_id)},
            {
                "$set": {
                    f"answers.{question_id}": answer,
                    f"time_spent.{question_id}": time_seconds,
                }
            },
        )

        return jsonify({"message": "Answer recorded", "question_id": question_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/sessions/<session_id>/code", methods=["POST"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def submit_code(session_id):
    """
    Submit code for a coding/debugging question. Executes via Judge0.
    Body: { question_id, source_code, language, time_spent_seconds }
    """
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role != "candidate":
            return jsonify({"error": "Unauthorized"}), 403

        # ── Blacklist check ──────────────────────────────────────────────
        if check_blacklist(user_id):
            return jsonify({"error": "You are permanently banned from assessments"}), 403

        db = get_db()
        session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session or session["candidate_id"] != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if session["status"] != "in_progress":
            return jsonify({"error": "Session is not active"}), 400

        if session.get("expires_at") and datetime.utcnow() > session["expires_at"]:
            db["smart_sessions"].update_one(
                {"_id": ObjectId(session_id)},
                {"$set": {"status": "expired"}}
            )
            return jsonify({"error": "Session has expired"}), 400

        data = request.get_json()
        question_id = data.get("question_id")
        source_code = data.get("source_code", "")
        language = data.get("language", "python")
        time_seconds = data.get("time_spent_seconds", 0)

        # Find the question
        question = None
        for q in session.get("questions", []):
            if q.get("id") == question_id:
                question = q
                break

        if not question:
            return jsonify({"error": "Question not found in session"}), 404

        # Build test cases from examples + hidden test cases
        test_cases = []
        for ex in question.get("examples", []):
            test_cases.append({"input": ex.get("input", ""), "output": ex.get("output", "")})
        for htc in question.get("hidden_test_cases", []):
            test_cases.append({"input": htc.get("input", ""), "output": htc.get("output", "")})

        if not test_cases:
            return jsonify({"error": "No test cases available for this question"}), 400

        # Execute via Judge0
        exec_result = execute_code(
            source_code=source_code,
            language=language,
            test_cases=test_cases,
            time_limit=5.0,
            memory_limit=128000,
        )

        # Score the submission
        score_result = score_coding_question(question, exec_result)

        # Store submission
        submission = CodeSubmission(
            session_id=session_id,
            question_id=question_id,
            candidate_id=user_id,
            source_code=source_code,
            language=language,
        )
        submission.execution_result = exec_result
        submission.score = score_result["score"]
        submission.passed_tests = score_result.get("passed_tests", 0)
        submission.total_tests = score_result.get("total_tests", 0)
        submission.execution_time = score_result.get("execution_time", "0")
        submission.memory_used = score_result.get("memory_used", 0)
        submission.status = "completed"

        db["code_submissions"].insert_one(submission.to_dict())

        # Update session
        db["smart_sessions"].update_one(
            {"_id": ObjectId(session_id)},
            {
                "$set": {
                    f"answers.{question_id}": source_code,
                    f"time_spent.{question_id}": time_seconds,
                    f"question_scores.{question_id}": score_result,
                },
                "$push": {
                    f"code_submissions.{question_id}": {
                        "source_code": source_code,
                        "language": language,
                        "result": {
                            "overall_status": exec_result.get("overall_status"),
                            "passed": exec_result.get("passed"),
                            "total_tests": exec_result.get("total_tests"),
                        },
                        "score": score_result["score"],
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                },
            },
        )

        # Return result (hide hidden test case details)
        safe_result = {
            "overall_status": exec_result.get("overall_status"),
            "passed_tests": exec_result.get("passed", 0),
            "total_tests": exec_result.get("total_tests", 0),
            "execution_time": exec_result.get("max_time", "0"),
            "memory_used": exec_result.get("max_memory", 0),
            "score": score_result["score"],
            "max_score": score_result["max_score"],
            "feedback": score_result.get("feedback", ""),
        }

        # Show visible test results (only for example test cases, not hidden)
        visible_results = []
        example_count = len(question.get("examples", []))
        for i, r in enumerate(exec_result.get("results", [])):
            if i < example_count:
                visible_results.append({
                    "test_case": i + 1,
                    "status": r.get("status"),
                    "stdout": r.get("stdout", "")[:500],
                    "stderr": r.get("stderr", "")[:300],
                })
        safe_result["visible_test_results"] = visible_results

        return jsonify({
            "message": "Code submitted and executed",
            "question_id": question_id,
            "result": safe_result,
        }), 200

    except Exception as e:
        logger.error("submit_code error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/sessions/<session_id>/finish", methods=["POST"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def finish_session(session_id):
    """
    Finish the session, calculate final scores, and return results.
    """
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role != "candidate":
            return jsonify({"error": "Unauthorized"}), 403

        # ── Blacklist check ──────────────────────────────────────────────
        if check_blacklist(user_id):
            return jsonify({"error": "You are permanently banned from assessments"}), 403

        db = get_db()
        session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session or session["candidate_id"] != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if session["status"] == "completed":
            return jsonify({"error": "Session already completed"}), 400

        questions = session.get("questions", [])
        answers = session.get("answers", {})
        time_spent = session.get("time_spent", {})
        existing_scores = session.get("question_scores", {})

        # Score each unanswered/unscored question
        question_scores = {}
        for q in questions:
            q_id = q.get("id", "")
            q_type = q.get("type", "mcq")

            # Use existing code scores if available
            if q_id in existing_scores:
                question_scores[q_id] = existing_scores[q_id]
                continue

            answer = answers.get(q_id)
            if answer is None:
                # Unanswered
                question_scores[q_id] = {
                    "is_correct": False,
                    "score": 0.0,
                    "max_score": float(q.get("points", 1)),
                    "feedback": "Not answered",
                }
                continue

            if q_type in ("mcq", "aptitude", "logical_reasoning"):
                question_scores[q_id] = score_mcq_question(q, answer)
            elif q_type in ("coding", "debugging"):
                # If no score exists, the code wasn't submitted — score as 0
                question_scores[q_id] = {
                    "is_correct": False,
                    "score": 0.0,
                    "max_score": float(q.get("points", 10)),
                    "feedback": "Code was not successfully executed",
                }
            else:
                # Unknown type — try AI evaluation
                ai_result = evaluate_answer_with_ai(q, str(answer))
                question_scores[q_id] = {
                    "is_correct": ai_result.get("is_correct", False),
                    "score": float(q.get("points", 1)) * (ai_result.get("score", 0) / 100),
                    "max_score": float(q.get("points", 1)),
                    "feedback": ai_result.get("feedback", ""),
                }

        # Calculate overall session score
        cfg = db["assessment_configs"].find_one({"_id": ObjectId(session["config_id"])})
        passing_score = cfg.get("passing_score", 70) if cfg else 70
        neg_marking = cfg.get("negative_marking", False) if cfg else False
        neg_penalty = cfg.get("negative_marking_penalty", 0.5) if cfg else 0.5

        final_result = calculate_session_score(
            questions=questions,
            answers=question_scores,
            time_spent=time_spent,
            passing_score=passing_score,
            negative_marking=neg_marking,
            negative_marking_penalty=neg_penalty,
        )

        # Update session with final results
        db["smart_sessions"].update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {
                "status": "completed",
                "completed_at": datetime.utcnow(),
                "question_scores": question_scores,
                "total_score": final_result["total_score"],
                "max_score": final_result["max_score"],
                "percentage": final_result["percentage"],
                "final_percentage": final_result["final_percentage"],
                "efficiency_bonus": final_result["efficiency_bonus"],
                "passed": final_result["passed"],
                "verdict": final_result["verdict"],
                "type_breakdown": final_result["type_breakdown"],
                "strengths": final_result["strengths"],
                "weaknesses": final_result["weaknesses"],
                "penalty_applied": final_result.get("penalty_applied", 0.0),
                "negative_marking_enabled": final_result.get("negative_marking_enabled", False),
            }},
        )

        # Update config stats
        if cfg:
            db["assessment_configs"].update_one(
                {"_id": ObjectId(session["config_id"])},
                {"$inc": {"sessions_count": 1}},
            )

        # Emit session_complete so client can stop recording cleanly
        try:
            from flask import current_app
            sio = getattr(current_app, 'socketio', None)
            if sio:
                sio.emit('session_complete', {
                    'session_id': session_id,
                    'status': 'completed',
                    'score': final_result.get('percentage', 0),
                }, room=session_id)
        except Exception as e:
            logger.warning("session_complete emit failed: %s", e)

        # Send completion emails (candidate + recruiter) — never blocks response
        try:
            from backend.services.session_emails import send_session_completion_emails
            updated_session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
            send_session_completion_emails(session_id, updated_session)
        except Exception as e:
            logger.warning("completion email failed: %s", e)

        return jsonify({
            "message": "Assessment completed",
            "results": final_result,
            "question_scores": question_scores if cfg and cfg.get("show_results", True) else {},
        }), 200

    except Exception as e:
        logger.error("finish_session error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/my-sessions", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def my_sessions():
    """List all sessions for the current candidate."""
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        db = get_db()

        sessions = list(
            db["smart_sessions"]
            .find({"candidate_id": user_id})
            .sort("created_at", -1)
        )

        for s in sessions:
            _serialize_doc(s)
            # Enrich with config title
            cfg = db["assessment_configs"].find_one({"_id": ObjectId(s["config_id"])}) if s.get("config_id") else None
            s["config_title"] = cfg.get("title", "Unknown") if cfg else "Unknown"
            s["config_job_role"] = cfg.get("job_role", "") if cfg else ""
            s["duration_minutes"] = cfg.get("duration_minutes", 0) if cfg else 0
            # Enrich with job title if job-linked
            if s.get("job_id"):
                job = db["jobs"].find_one({"_id": ObjectId(s["job_id"])})
                s["job_title"] = job.get("title", "Job Application") if job else "Job Application"
            # Don't send full questions list in summary view
            s["question_count"] = len(s.pop("questions", []))
            s.pop("answers", None)
            s.pop("code_submissions", None)

        return jsonify({"sessions": sessions, "total": len(sessions)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/sessions/<session_id>/results", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def session_results(session_id):
    """Get detailed results for a completed session."""
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        db = get_db()

        session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session:
            return jsonify({"error": "Session not found"}), 404

        # Candidates see their own; company/admin see all
        if role == "candidate" and session["candidate_id"] != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if session["status"] != "completed":
            return jsonify({"error": "Session not yet completed"}), 400

        _serialize_doc(session)

        # Enrich with config info
        cfg = db["assessment_configs"].find_one({"_id": ObjectId(session["config_id"])}) if session.get("config_id") else None
        session["config_title"] = cfg.get("title", "") if cfg else ""
        session["config_job_role"] = cfg.get("job_role", "") if cfg else ""

        return jsonify({"session": session}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================================
# HR DASHBOARD
# ============================================================================

@bp.route("/dashboard", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_COMPANY_ANALYTICS)
def hr_dashboard():
    """Aggregated dashboard for HR / Admin."""
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role not in ("company", "admin", "recruiter"):
            return jsonify({"error": "Unauthorized"}), 403

        db = get_db()

        # Get configs
        config_query = {"is_active": True}
        if role in ("company", "recruiter"):
            config_query["created_by"] = user_id
        configs = list(db["assessment_configs"].find(config_query))
        config_ids = [str(c["_id"]) for c in configs]

        # Get all completed sessions for these configs
        sessions = list(db["smart_sessions"].find({
            "config_id": {"$in": config_ids},
            "status": "completed",
        }))

        total_sessions = len(sessions)
        if total_sessions == 0:
            return jsonify({
                "total_configs": len(configs),
                "total_sessions": 0,
                "average_score": 0,
                "pass_rate": 0,
                "verdict_distribution": {},
                "top_performers": [],
                "recent_sessions": [],
            }), 200

        avg_score = sum(s.get("final_percentage", 0) for s in sessions) / total_sessions
        passed = sum(1 for s in sessions if s.get("passed"))
        verdicts = {}
        for s in sessions:
            v = s.get("verdict", "unknown")
            verdicts[v] = verdicts.get(v, 0) + 1

        # Top performers (top 10 by score)
        sorted_sessions = sorted(sessions, key=lambda x: x.get("final_percentage", 0), reverse=True)
        top_performers = []
        for s in sorted_sessions[:10]:
            candidate = db["users"].find_one({"_id": ObjectId(s["candidate_id"])}) if s.get("candidate_id") else None
            top_performers.append({
                "candidate_name": candidate.get("name", "Unknown") if candidate else "Unknown",
                "candidate_email": candidate.get("email", "") if candidate else "",
                "score": s.get("final_percentage", 0),
                "verdict": s.get("verdict", ""),
                "session_id": str(s["_id"]),
                "config_id": s.get("config_id", ""),
            })

        # Recent sessions (last 20)
        recent = sorted(sessions, key=lambda x: x.get("completed_at", datetime.min), reverse=True)[:20]
        recent_sessions = []
        for s in recent:
            candidate = db["users"].find_one({"_id": ObjectId(s["candidate_id"])}) if s.get("candidate_id") else None
            cfg = next((c for c in configs if str(c["_id"]) == s.get("config_id")), None)
            recent_sessions.append({
                "session_id": str(s["_id"]),
                "candidate_name": candidate.get("name", "Unknown") if candidate else "Unknown",
                "assessment_title": cfg.get("title", "Unknown") if cfg else "Unknown",
                "score": s.get("final_percentage", 0),
                "verdict": s.get("verdict", ""),
                "completed_at": s.get("completed_at").isoformat() if hasattr(s.get("completed_at", ""), "isoformat") else str(s.get("completed_at", "")),
            })

        return jsonify({
            "total_configs": len(configs),
            "total_sessions": total_sessions,
            "average_score": round(avg_score, 2),
            "pass_rate": round(passed / total_sessions * 100, 2),
            "verdict_distribution": verdicts,
            "top_performers": top_performers,
            "recent_sessions": recent_sessions,
        }), 200

    except Exception as e:
        logger.error("hr_dashboard error: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/sessions/<session_id>/review", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_COMPANY_ANALYTICS)
def review_session(session_id):
    """HR review of a candidate's session with full details including code."""
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role not in ("company", "admin", "recruiter"):
            return jsonify({"error": "Unauthorized"}), 403

        db = get_db()
        session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session:
            return jsonify({"error": "Session not found"}), 404

        _serialize_doc(session)

        # Enrich with candidate info
        candidate = db["users"].find_one({"_id": ObjectId(session["candidate_id"])}) if session.get("candidate_id") else None
        session["candidate_name"] = candidate.get("name", "Unknown") if candidate else "Unknown"
        session["candidate_email"] = candidate.get("email", "") if candidate else ""

        # Enrich with config info
        cfg = db["assessment_configs"].find_one({"_id": ObjectId(session["config_id"])}) if session.get("config_id") else None
        session["config_title"] = cfg.get("title", "") if cfg else ""
        session["config_job_role"] = cfg.get("job_role", "") if cfg else ""

        # Get code submissions for this session
        code_subs = list(db["code_submissions"].find({"session_id": session_id}))
        for cs in code_subs:
            _serialize_doc(cs)
        session["all_code_submissions"] = code_subs

        return jsonify({"session": session}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Timer Persistence  (Candidate-only)
# ---------------------------------------------------------------------------
# The client sends remaining_seconds every 30 seconds.
# The 5-second rate limit is an ABUSE PREVENTION FLOOR — if someone discovers
# the endpoint and hammers it, they get 429.  It is NOT the expected update
# interval.  Normal client behaviour (30s) will never trigger it.

@bp.route("/sessions/<session_id>/timer", methods=["PATCH"])
@jwt_required()
def update_session_timer(session_id):
    """
    PATCH /api/smart-assessments/sessions/<session_id>/timer
    Body: { "remaining_seconds": int }
    Candidate-only. Session ownership check. 5s rate-limit floor.
    """
    try:
        db = get_db()
        current_user = get_jwt_identity()
        user_id, role = _get_user_info(current_user)

        # Candidate-only
        if role not in ("candidate", None):
            return jsonify({"error": "Candidates only"}), 403

        data = request.get_json() or {}
        remaining = data.get("remaining_seconds")
        if remaining is None or not isinstance(remaining, (int, float)) or remaining < 0:
            return jsonify({"error": "remaining_seconds must be a non-negative integer"}), 400
        remaining = int(remaining)

        session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session:
            return jsonify({"error": "Session not found"}), 404

        # Ownership check
        if str(session.get("candidate_id")) != str(user_id):
            return jsonify({"error": "Not your session"}), 403

        # Only accept updates for in-progress sessions
        if session.get("status") not in ("in_progress", "paused"):
            return jsonify({"error": "Session is not active"}), 400

        # 5-second rate limit (abuse prevention floor)
        now = datetime.utcnow()
        last_sync = session.get("last_timer_sync")
        if last_sync and (now - last_sync).total_seconds() < 5:
            return jsonify({"error": "Too many timer updates. Max 1 per 5 seconds."}), 429

        db["smart_sessions"].update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {
                "remaining_seconds": remaining,
                "last_timer_sync": now,
            }},
        )

        return jsonify({"message": "Timer synced", "remaining_seconds": remaining}), 200

    except Exception as e:
        logger.error("Timer update failed: %s", e)
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Question Review Tool  (Recruiter-only)
# ---------------------------------------------------------------------------

# Fields a recruiter is allowed to edit via the review endpoint.
# All other fields (is_active, created_at, fingerprint, etc.) are silently ignored.
EDITABLE_QUESTION_FIELDS = {
    "question_text", "options", "correct_answer",
    "difficulty", "estimated_time_minutes", "bloom_level",
}


@bp.route("/questions/review", methods=["GET"])
@jwt_required()
@require_permission(Permissions.EDIT_ASSESSMENT)
def list_questions_for_review():
    """
    GET /api/smart-assessments/questions/review
    Paginated list of AI-generated questions for recruiter review.
    Query params: page, per_page, type, difficulty, topic, status (pending|reviewed|rejected)
    """
    try:
        db = get_db()

        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))
        skip = (page - 1) * per_page

        # Build filter
        query = {}

        q_type = request.args.get("type")
        if q_type:
            query["type"] = q_type

        difficulty = request.args.get("difficulty")
        if difficulty:
            query["difficulty"] = difficulty

        topic = request.args.get("topic")
        if topic:
            query["topic"] = {"$regex": topic, "$options": "i"}

        status = request.args.get("status", "").lower()
        if status == "pending":
            query["is_active"] = True
            query["reviewed"] = {"$ne": True}
        elif status == "reviewed":
            query["reviewed"] = True
            query["is_active"] = True
        elif status == "rejected":
            query["is_active"] = False
        else:
            # Default: show active (pending + reviewed)
            pass

        total = db["ai_questions"].count_documents(query)
        questions = list(
            db["ai_questions"]
            .find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(per_page)
        )

        for q in questions:
            _serialize_doc(q)

        return jsonify({
            "questions": questions,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": math.ceil(total / per_page) if per_page > 0 else 0,
        }), 200

    except Exception as e:
        logger.error("Question review list failed: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/questions/<question_id>/review", methods=["PATCH"])
@jwt_required()
@require_permission(Permissions.EDIT_ASSESSMENT)
def review_question(question_id):
    """
    PATCH /api/smart-assessments/questions/<question_id>/review
    Actions: approve, reject, edit
    Body: { "action": "approve"|"reject"|"edit", "edits": {...} }
    edit.edits only allows whitelisted fields; all others are silently ignored.
    """
    try:
        db = get_db()
        data = request.get_json() or {}
        action = data.get("action", "").strip().lower()
        current_user = get_jwt_identity()
        user_id, _ = _get_user_info(current_user)

        if action not in ("approve", "reject", "edit"):
            return jsonify({"error": "action must be 'approve', 'reject', or 'edit'"}), 400

        question = db["ai_questions"].find_one({"id": question_id})
        if not question:
            return jsonify({"error": "Question not found"}), 404

        now = datetime.utcnow()

        if action == "approve":
            db["ai_questions"].update_one(
                {"id": question_id},
                {"$set": {
                    "reviewed": True,
                    "reviewed_by": user_id,
                    "reviewed_at": now,
                }},
            )
            return jsonify({"message": "Question approved", "question_id": question_id}), 200

        elif action == "reject":
            db["ai_questions"].update_one(
                {"id": question_id},
                {"$set": {
                    "is_active": False,
                    "rejected_by": user_id,
                    "rejected_at": now,
                }},
            )
            return jsonify({"message": "Question rejected", "question_id": question_id}), 200

        elif action == "edit":
            edits = data.get("edits", {})
            if not edits:
                return jsonify({"error": "edits dict is required for edit action"}), 400

            # Whitelist: only allow safe fields
            safe_edits = {
                k: v for k, v in edits.items()
                if k in EDITABLE_QUESTION_FIELDS
            }
            if not safe_edits:
                return jsonify({"error": "No allowed fields in edits. "
                    f"Allowed: {', '.join(sorted(EDITABLE_QUESTION_FIELDS))}"}), 400

            safe_edits["reviewed"] = True
            safe_edits["edited_by"] = user_id
            safe_edits["edited_at"] = now

            db["ai_questions"].update_one(
                {"id": question_id},
                {"$set": safe_edits},
            )
            return jsonify({
                "message": "Question updated",
                "question_id": question_id,
                "fields_updated": list(safe_edits.keys()),
            }), 200

    except Exception as e:
        logger.error("Question review action failed: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/questions/stats", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def question_bank_stats():
    """
    GET /api/smart-assessments/questions/stats
    Aggregated stats: total, reviewed, rejected, pending, by difficulty, by type.
    """
    try:
        db = get_db()
        col = db["ai_questions"]

        total = col.count_documents({})
        reviewed = col.count_documents({"reviewed": True, "is_active": True})
        rejected = col.count_documents({"is_active": False})
        pending = col.count_documents({"is_active": True, "reviewed": {"$ne": True}})

        # By difficulty
        by_difficulty = {}
        for diff in ("easy", "medium", "hard"):
            by_difficulty[diff] = col.count_documents({"difficulty": diff, "is_active": True})

        # By type
        by_type = {}
        for qt in ("coding", "mcq", "aptitude", "debugging", "logical_reasoning"):
            by_type[qt] = col.count_documents({"type": qt, "is_active": True})

        return jsonify({
            "total": total,
            "reviewed": reviewed,
            "rejected": rejected,
            "pending": pending,
            "by_difficulty": by_difficulty,
            "by_type": by_type,
        }), 200

    except Exception as e:
        logger.error("Question stats failed: %s", e)
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# PDF AUDIT REPORT
# ═══════════════════════════════════════════════════════════════════════════════

@bp.route("/sessions/<session_id>/audit-report", methods=["GET"])
@jwt_required()
def download_audit_report(session_id):
    """
    Generate and download a PDF audit report for a session.

    Query params:
      - include_pii=true — include candidate name/email (default: anonymized)

    JWT: recruiter-only (must own the job) OR admin.
    """
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role not in ("recruiter", "admin"):
            return jsonify({"error": "Unauthorized"}), 403

        db = get_db()
        session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session:
            return jsonify({"error": "Session not found"}), 404

        # Ownership check for recruiters
        if role == "recruiter":
            config = db["assessment_configs"].find_one({"_id": session.get("assessment_id") or session.get("config_id")})
            job = None
            if config and config.get("job_id"):
                job = db["jobs"].find_one({"_id": ObjectId(config["job_id"])})
            if not job or str(job.get("recruiter_id", "")) != user_id:
                return jsonify({"error": "Forbidden — you do not own this job"}), 403

        include_pii = request.args.get("include_pii", "false").lower() == "true"

        # GDPR audit trail: log PII access
        if include_pii:
            db["audit_logs"].insert_one({
                "action": "pii_report_download",
                "user_id": user_id,
                "user_role": role,
                "session_id": session_id,
                "timestamp": datetime.utcnow(),
                "ip_address": request.remote_addr,
            })
            logger.info("PII audit report access logged: user=%s session=%s", user_id, session_id)

        from backend.services.audit_report_generator import generate_audit_report
        pdf_bytes = generate_audit_report(session_id, include_pii=include_pii)

        from flask import Response
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="audit_report_{session_id[:8]}.pdf"',
            },
        )

    except ImportError as e:
        logger.error("Audit report generation failed (missing deps): %s", e)
        return jsonify({"error": str(e)}), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error("download_audit_report error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# RECORDING CHUNK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

MAX_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB per chunk


@bp.route("/proctoring/recording-chunk", methods=["POST"])
@jwt_required()
def upload_recording_chunk():
    """
    Upload a single recording chunk (WebM binary).

    Ownership: JWT candidate_id must match session.candidate_id.
    Guard: session must be in 'in_progress' status.
    """
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role != "candidate":
            return jsonify({"error": "Unauthorized"}), 403

        session_id = request.form.get("session_id")
        chunk_index = request.form.get("chunk_index")
        is_final = request.form.get("is_final", "false").lower() == "true"
        blob = request.files.get("blob")

        if not session_id or chunk_index is None or not blob:
            return jsonify({"error": "Missing session_id, chunk_index, or blob"}), 400

        chunk_index = int(chunk_index)

        # Validate session ownership + status
        db = get_db()
        session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session or session.get("candidate_id") != user_id:
            return jsonify({"error": "Unauthorized — session mismatch"}), 403

        if session.get("status") not in ("in_progress",):
            return jsonify({"error": "Session is not in progress — upload rejected"}), 400

        # Read and validate chunk size
        chunk_data = blob.read()
        if len(chunk_data) > MAX_CHUNK_SIZE:
            return jsonify({"error": f"Chunk exceeds {MAX_CHUNK_SIZE // (1024*1024)}MB limit"}), 413

        # Save chunk to disk
        mime_type = request.form.get("mime_type", "video/webm")
        container_ext = "mp4" if "mp4" in mime_type else "webm"
        session_dir = os.path.join(RECORDINGS_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)
        filename = f"chunk_{chunk_index:04d}.{container_ext}"
        filepath = os.path.join(session_dir, filename)

        with open(filepath, "wb") as f:
            f.write(chunk_data)

        # Insert into recording_chunks collection
        db["recording_chunks"].insert_one({
            "session_id": session_id,
            "chunk_index": chunk_index,
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(chunk_data),
            "is_final": is_final,
            "uploaded_at": datetime.utcnow(),
        })

        logger.info("Recording chunk saved: session=%s chunk=%d (%d bytes) final=%s",
                     session_id, chunk_index, len(chunk_data), is_final)
        return jsonify({"message": "Chunk saved", "chunk_index": chunk_index}), 201

    except Exception as e:
        logger.error("upload_recording_chunk error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/sessions/<session_id>/recording", methods=["GET"])
@jwt_required()
def download_recording(session_id):
    """
    Stream the merged recording for a session.

    Uses ffmpeg to properly concatenate WebM chunks (only chunk 0 has EBML
    header; subsequent chunks contribute cluster data only).

    Ownership: recruiter must own the job OR be admin.
    Cache: re-merge only if chunk_count changed.
    """
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role not in ("recruiter", "admin"):
            return jsonify({"error": "Unauthorized"}), 403

        db = get_db()
        session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session:
            return jsonify({"error": "Session not found"}), 404

        # Ownership check for recruiters
        if role == "recruiter":
            # Session must belong to a job owned by this recruiter
            config = db["assessment_configs"].find_one({"_id": session.get("assessment_id")})
            job = None
            if config and config.get("job_id"):
                job = db["jobs"].find_one({"_id": ObjectId(config["job_id"])})
            if not job or str(job.get("recruiter_id", "")) != user_id:
                return jsonify({"error": "Forbidden — you do not own this job"}), 403

        # Check chunks exist
        chunks = list(db["recording_chunks"].find(
            {"session_id": session_id}
        ).sort("chunk_index", 1))
        chunk_count = len(chunks)
        if chunk_count == 0:
            return jsonify({"error": "No recording available"}), 404

        total_bytes = sum(c.get("size_bytes", 0) for c in chunks)
        has_final = any(c.get("is_final") for c in chunks)

        session_dir = os.path.join(RECORDINGS_DIR, session_id)
        merged_path = os.path.join(session_dir, "merged.webm")
        cache_meta_path = os.path.join(session_dir, ".cache_meta")

        # Cache invalidation: count + total_bytes + TTL after final chunk
        need_merge = True
        if os.path.exists(merged_path) and os.path.exists(cache_meta_path):
            try:
                import json as _json
                meta = _json.loads(open(cache_meta_path).read())
                cached_count = meta.get("chunk_count", 0)
                cached_bytes = meta.get("total_bytes", 0)
                if cached_count == chunk_count and cached_bytes == total_bytes:
                    # If final chunk exists and cache is fresh, skip re-merge
                    need_merge = False
                elif not has_final:
                    # Session still in progress — check if final chunk arrived recently
                    latest_upload = max((c.get("uploaded_at", datetime.min) for c in chunks), default=datetime.min)
                    if (datetime.utcnow() - latest_upload).total_seconds() < 60:
                        need_merge = True  # Recent upload, force re-merge
            except (ValueError, OSError, KeyError):
                need_merge = True

        if need_merge:
            # Write ffmpeg concat list
            os.makedirs(session_dir, exist_ok=True)
            concat_list_path = os.path.join(session_dir, "concat_list.txt")
            with open(concat_list_path, "w") as f:
                for chunk in chunks:
                    chunk_path = os.path.join(session_dir, chunk["filename"])
                    if os.path.exists(chunk_path):
                        safe_path = chunk_path.replace("\\", "/")
                        f.write(f"file '{safe_path}'\n")

            # Run ffmpeg concat
            try:
                result = subprocess.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                     "-i", concat_list_path, "-c", "copy", merged_path],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode != 0:
                    logger.error("ffmpeg merge failed: %s", result.stderr)
                    return jsonify({"error": "Recording merge failed"}), 500
            except FileNotFoundError:
                logger.error("ffmpeg binary not found — cannot merge recording chunks")
                return jsonify({
                    "error": "Recording service unavailable — ffmpeg not installed. "
                             "Contact system administrator."
                }), 503

            # Update cache metadata (count + bytes)
            import json as _json
            with open(cache_meta_path, "w") as f:
                _json.dump({"chunk_count": chunk_count, "total_bytes": total_bytes}, f)

        # Detect container format from first chunk's mime_type
        first_mime = chunks[0].get("mime_type", "video/webm")
        is_mp4 = "mp4" in first_mime
        out_ext = "mp4" if is_mp4 else "webm"
        out_mime = "video/mp4" if is_mp4 else "video/webm"

        # Stream the merged file
        from flask import send_file
        return send_file(
            merged_path,
            mimetype=out_mime,
            as_attachment=True,
            download_name=f"recording_{session_id}.{out_ext}",
        )

    except Exception as e:
        logger.error("download_recording error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/sessions/<session_id>/recording-info", methods=["GET"])
@jwt_required()
def recording_info(session_id):
    """Metadata about the recording for the recordings tab."""
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role not in ("recruiter", "admin"):
            return jsonify({"error": "Unauthorized"}), 403

        db = get_db()

        # Ownership check for recruiters
        if role == "recruiter":
            session = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
            if not session:
                return jsonify({"error": "Session not found"}), 404
            config = db["assessment_configs"].find_one({"_id": session.get("assessment_id")})
            job = None
            if config and config.get("job_id"):
                job = db["jobs"].find_one({"_id": ObjectId(config["job_id"])})
            if not job or str(job.get("recruiter_id", "")) != user_id:
                return jsonify({"error": "Forbidden"}), 403

        chunks = list(db["recording_chunks"].find({"session_id": session_id}))
        chunk_count = len(chunks)
        total_size = sum(c.get("size_bytes", 0) for c in chunks)

        return jsonify({
            "has_recording": chunk_count > 0,
            "chunk_count": chunk_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2) if total_size else 0,
        }), 200

    except Exception as e:
        logger.error("recording_info error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


# ─── Session Filter Endpoint (for Recordings Tab) ────────────────────────────

@bp.route("/sessions", methods=["GET"])
@jwt_required()
def list_sessions():
    """
    List smart assessment sessions, filterable by candidate_id and/or
    application_id. Used by the company portal's recordings tab.

    Recruiter-only; sessions must belong to jobs owned by the recruiter.
    Admins bypass ownership check.
    """
    try:
        user_id, role = _get_user_info(get_jwt_identity())
        if role not in ("recruiter", "admin"):
            return jsonify({"error": "Unauthorized"}), 403

        db = get_db()

        # Build filter
        query = {}
        candidate_id = request.args.get("candidate_id")
        application_id = request.args.get("application_id")

        if candidate_id:
            query["candidate_id"] = candidate_id
        if application_id:
            query["application_id"] = application_id

        if not query:
            return jsonify({"error": "At least one of candidate_id or application_id is required"}), 400

        sessions = list(db["smart_sessions"].find(query).sort("started_at", -1).limit(50))

        # Ownership check for recruiters: filter to sessions whose job belongs to them
        if role == "recruiter":
            owned_sessions = []
            # Cache job lookups
            job_cache = {}
            for s in sessions:
                config = db["assessment_configs"].find_one({"_id": s.get("assessment_id")})
                if not config or not config.get("job_id"):
                    continue
                job_id = str(config["job_id"])
                if job_id not in job_cache:
                    job = db["jobs"].find_one({"_id": ObjectId(job_id)})
                    job_cache[job_id] = job
                job = job_cache[job_id]
                if job and str(job.get("recruiter_id", "")) == user_id:
                    owned_sessions.append(s)
            sessions = owned_sessions

        # Enrich with recording availability
        result = []
        for s in sessions:
            sid = str(s["_id"])
            rec_count = db["recording_chunks"].count_documents({"session_id": sid})
            result.append({
                "session_id": sid,
                "candidate_id": s.get("candidate_id"),
                "application_id": s.get("application_id"),
                "status": s.get("status"),
                "started_at": s.get("started_at", ""),
                "completed_at": s.get("completed_at", ""),
                "terminated_at": s.get("terminated_at", ""),
                "proctoring_score": s.get("proctoring_score"),
                "has_recording": rec_count > 0,
                "results": s.get("results"),
            })

        return jsonify({"sessions": result}), 200

    except Exception as e:
        logger.error("list_sessions error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500

