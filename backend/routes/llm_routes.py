"""
LLM API routes: job description, resume summary, interview questions, rejection email.
Migrated from v1 (smart-hiring-system) into v2 enterprise codebase.
"""

import logging
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId

from backend.models.database import get_db
from backend.services.llm_service import LLMService
from backend.utils.rbac_decorator import require_permission

logger = logging.getLogger(__name__)

bp = Blueprint("llm", __name__, url_prefix="/api/llm")
llm_service = LLMService()


def _user_id_and_role():
    identity = get_jwt_identity()
    if identity is None:
        return None, None
    if isinstance(identity, dict):
        return identity.get("user_id"), identity.get("role")
    claims = get_jwt() or {}
    return identity, claims.get("role")


@bp.route("/generate-job-description", methods=["POST"])
@jwt_required()
@require_permission("JOB_CREATE")
def generate_job_description():
    """Generate job description using AI. Body: job_title, skills[], experience_level, optional company_culture, benefits[]."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400
    for f in ("job_title", "skills", "experience_level"):
        if f not in data:
            return jsonify({"success": False, "error": f"Missing {f}"}), 400
    if data["experience_level"] not in ("entry", "mid", "senior", "lead"):
        return jsonify({"success": False, "error": "Invalid experience level"}), 400
    if not isinstance(data["skills"], list) or len(data["skills"]) == 0:
        return jsonify({"success": False, "error": "Skills must be a non-empty array"}), 400
    try:
        result = llm_service.generate_job_description(
            job_title=data["job_title"],
            skills=data["skills"],
            experience_level=data["experience_level"],
            company_culture=data.get("company_culture"),
            benefits=data.get("benefits"),
        )
        return jsonify({"success": True, "data": result}), 200
    except Exception as e:
        logger.exception("Job description generation failed: %s", e)
        return jsonify({"success": False, "error": "Generation failed, please try again"}), 500


@bp.route("/summarize-resume/<candidate_id>", methods=["GET"])
@jwt_required()
@require_permission("CANDIDATE_VIEW")
def summarize_resume(candidate_id):
    """Generate AI summary of candidate resume. Query: max_words (default 150)."""
    max_words = request.args.get("max_words", 150, type=int)
    try:
        db = get_db()
        try:
            cid = ObjectId(candidate_id)
            candidate = db["candidates"].find_one({"_id": cid})
        except Exception:
            candidate = db["candidates"].find_one({"user_id": candidate_id})
        if not candidate:
            return jsonify({"success": False, "error": "Candidate not found"}), 404
        resume_text = candidate.get("resume_text") or (candidate.get("parsed_resume") or {}).get("raw_text") or ""
        if not resume_text:
            return jsonify({"success": False, "error": "No resume text available"}), 404
        if "ai_summary" in candidate:
            created = candidate["ai_summary"].get("created_at")
            if created and created > datetime.utcnow() - timedelta(days=30):
                return jsonify({"success": True, "data": candidate["ai_summary"]}), 200
        result = llm_service.summarize_resume(resume_text, max_words=max_words)
        ai_summary = {**result, "created_at": datetime.utcnow(), "max_words": max_words}
        db["candidates"].update_one(
            {"_id": candidate["_id"]} if candidate.get("_id") else {"user_id": candidate_id},
            {"$set": {"ai_summary": ai_summary}},
        )
        return jsonify({"success": True, "data": ai_summary}), 200
    except Exception as e:
        logger.exception("Resume summarization failed: %s", e)
        return jsonify({"success": False, "error": "Summarization failed"}), 500


@bp.route("/generate-interview-questions", methods=["POST"])
@jwt_required()
@require_permission("SCHEDULE_INTERVIEW")
def generate_interview_questions():
    """Generate interview questions. Body: job_id, candidate_id, optional num_questions."""
    data = request.get_json()
    if not data or not all(k in data for k in ("job_id", "candidate_id")):
        return jsonify({"success": False, "error": "Missing job_id or candidate_id"}), 400
    try:
        db = get_db()
        job = db["jobs"].find_one({"_id": ObjectId(data["job_id"])})
        try:
            candidate = db["candidates"].find_one({"_id": ObjectId(data["candidate_id"])})
        except Exception:
            candidate = db["candidates"].find_one({"user_id": data["candidate_id"]})
        if not job or not candidate:
            return jsonify({"success": False, "error": "Job or candidate not found"}), 404
        job_skills = job.get("required_skills") or []
        candidate_skills = candidate.get("skills") or (candidate.get("parsed_resume") or {}).get("skills") or []
        role_level = job.get("experience_required")
        if isinstance(role_level, (int, float)):
            role_level = "senior" if role_level >= 5 else "mid" if role_level >= 2 else "entry"
        else:
            role_level = str(role_level or "mid").lower()
        num_questions = min(20, max(1, data.get("num_questions", 8)))
        result = llm_service.generate_interview_questions(
            job_skills=job_skills,
            candidate_skills=candidate_skills,
            role_level=role_level,
            num_questions=num_questions,
        )
        return jsonify({"success": True, "data": result}), 200
    except Exception as e:
        logger.exception("Question generation failed: %s", e)
        return jsonify({"success": False, "error": "Generation failed"}), 500


@bp.route("/draft-rejection-email", methods=["POST"])
@jwt_required()
@require_permission("CANDIDATE_EDIT")
def draft_rejection_email():
    """Generate rejection email. Body: candidate_id, job_id, reason (optional)."""
    data = request.get_json()
    if not data or not all(k in data for k in ("candidate_id", "job_id")):
        return jsonify({"success": False, "error": "Missing candidate_id or job_id"}), 400
    try:
        db = get_db()
        user = db["users"].find_one({"_id": ObjectId(data["candidate_id"])})
        job = db["jobs"].find_one({"_id": ObjectId(data["job_id"])})
        if not user or not job:
            return jsonify({"success": False, "error": "Candidate or job not found"}), 404
        candidate_name = user.get("full_name") or user.get("name") or user.get("email", "Candidate")
        reason = data.get("reason", "other_candidates")
        if reason not in ("other_candidates", "skills_gap", "experience_level"):
            reason = "other_candidates"
        result = llm_service.draft_rejection_email(
            candidate_name=candidate_name,
            job_title=job.get("title", "Position"),
            reason=reason,
        )
        return jsonify({"success": True, "data": result}), 200
    except Exception as e:
        logger.exception("Rejection email draft failed: %s", e)
        return jsonify({"success": False, "error": "Drafting failed"}), 500
