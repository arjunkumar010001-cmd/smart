"""
Interview Scheduling Routes
REST API endpoints for scheduling, managing, and tracking interviews.

Blueprint prefix (registered in app.py): /api/interviews
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId

from backend.models.database import get_db
from backend.services.interview_scheduling_service import (
    InterviewSchedulingService,
    InterviewServiceError,
)
from backend.security.rbac import require_permission, require_role, Permissions

logger = logging.getLogger(__name__)

bp = Blueprint("interviews", __name__)
interview_service = InterviewSchedulingService()


def _user_id_and_role():
    """Return (user_id str, role str). Handles identity as dict or string."""
    identity = get_jwt_identity()
    if identity is None:
        return None, None
    if isinstance(identity, dict):
        return str(identity.get("user_id", "")), identity.get("role")
    claims = get_jwt() or {}
    return str(identity), claims.get("role")


@bp.route("/schedule", methods=["POST"])
@jwt_required()
@require_permission(Permissions.MANAGE_APPLICATIONS)
def schedule_interview():
    """
    Schedule an interview for a shortlisted application.

    Request body:
        application_id: str (required)
        scheduled_at: str (ISO datetime, e.g. 2026-03-05T14:00:00Z)
        duration_minutes: int (30, 45, 60, or 90)
        panel: list of { user_id, email, name [, role] }
        notes: str (optional)

    Returns:
        201: { success: true, data: { ... } }
        400: validation error
        404: application not found
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body required"}), 400

        application_id = data.get("application_id")
        scheduled_at_raw = data.get("scheduled_at")
        duration_minutes = data.get("duration_minutes", 60)
        panel = data.get("panel", [])
        notes = data.get("notes", "")

        if not application_id:
            return jsonify({"success": False, "error": "Missing application_id"}), 400
        if not scheduled_at_raw:
            return jsonify({"success": False, "error": "Missing scheduled_at"}), 400

        try:
            scheduled_at = datetime.fromisoformat(scheduled_at_raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid datetime format. Use ISO format."}), 400

        try:
            duration_minutes = int(duration_minutes)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "duration_minutes must be 30, 45, 60, or 90"}), 400

        if not isinstance(panel, list):
            panel = []

        # If no panel specified, use the current recruiter
        if not panel:
            user_id, role = _user_id_and_role()
            db = get_db()
            recruiter = db["users"].find_one({"_id": ObjectId(user_id)})
            if recruiter:
                panel = [{
                    "user_id": user_id,
                    "email": recruiter.get("email", ""),
                    "name": recruiter.get("full_name", "Recruiter"),
                    "role": "interviewer",
                }]

        # Validate panel members
        for i, p in enumerate(panel):
            if not isinstance(p, dict) or not p.get("user_id"):
                return jsonify({"success": False, "error": f"Invalid panel member at index {i}"}), 400
            panel[i] = {
                "user_id": str(p["user_id"]),
                "email": (p.get("email") or "").strip(),
                "name": (p.get("name") or "").strip() or "Interviewer",
                "role": p.get("role", "interviewer"),
            }

        result = interview_service.schedule_interview(
            application_id=application_id,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,
            panel_members=panel,
            notes=notes,
        )
        return jsonify({"success": True, "data": result}), 201

    except InterviewServiceError as e:
        msg = str(e)
        if "not found" in msg.lower():
            return jsonify({"success": False, "error": msg}), 404
        return jsonify({"success": False, "error": msg}), 400
    except Exception as e:
        logger.exception("schedule_interview failed")
        return jsonify({"success": False, "error": "An error occurred while scheduling the interview"}), 500


@bp.route("/<interview_id>", methods=["GET"])
@jwt_required()
def get_interview(interview_id):
    """Get interview details by ID."""
    result = interview_service.get_interview(interview_id)
    if not result:
        return jsonify({"success": False, "error": "Interview not found"}), 404
    return jsonify({"success": True, "data": result}), 200


@bp.route("/<interview_id>/reschedule", methods=["POST"])
@jwt_required()
@require_permission(Permissions.MANAGE_APPLICATIONS)
def reschedule_interview(interview_id):
    """
    Reschedule an interview.

    Request body:
        scheduled_at: str (ISO datetime)
        duration_minutes: int (optional)

    Returns:
        200: { success: true, data: <interview> }
    """
    try:
        data = request.get_json() or {}
        scheduled_at_raw = data.get("scheduled_at")
        if not scheduled_at_raw:
            return jsonify({"success": False, "error": "Missing scheduled_at"}), 400

        try:
            new_datetime = datetime.fromisoformat(scheduled_at_raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid datetime format"}), 400

        duration_minutes = data.get("duration_minutes")
        if duration_minutes is not None:
            try:
                duration_minutes = int(duration_minutes)
            except (TypeError, ValueError):
                duration_minutes = None

        result = interview_service.reschedule_interview(
            interview_id=interview_id,
            new_datetime=new_datetime,
            duration_minutes=duration_minutes,
        )
        return jsonify({"success": True, "data": result}), 200

    except InterviewServiceError as e:
        msg = str(e)
        if "not found" in msg.lower():
            return jsonify({"success": False, "error": msg}), 404
        return jsonify({"success": False, "error": msg}), 400
    except Exception as e:
        logger.exception("reschedule_interview failed")
        return jsonify({"success": False, "error": "An error occurred"}), 500


@bp.route("/<interview_id>/cancel", methods=["POST"])
@jwt_required()
@require_permission(Permissions.MANAGE_APPLICATIONS)
def cancel_interview(interview_id):
    """
    Cancel an interview.

    Request body (optional):
        reason: str

    Returns:
        200: { success: true, data: <interview> }
    """
    data = request.get_json() or {}
    reason = data.get("reason")

    try:
        result = interview_service.cancel_interview(interview_id=interview_id, reason=reason)
        return jsonify({"success": True, "data": result}), 200
    except InterviewServiceError as e:
        if "not found" in str(e).lower():
            return jsonify({"success": False, "error": str(e)}), 404
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("cancel_interview failed")
        return jsonify({"success": False, "error": "An error occurred"}), 500


@bp.route("/<interview_id>/complete", methods=["POST"])
@jwt_required()
@require_permission(Permissions.MANAGE_APPLICATIONS)
def complete_interview(interview_id):
    """
    Mark an interview as completed.

    Request body (optional):
        feedback: str (interviewer notes)

    Returns:
        200: { success: true, data: <interview> }
    """
    data = request.get_json() or {}
    feedback = data.get("feedback")

    try:
        result = interview_service.complete_interview(interview_id=interview_id, feedback=feedback)
        return jsonify({"success": True, "data": result}), 200
    except InterviewServiceError as e:
        if "not found" in str(e).lower():
            return jsonify({"success": False, "error": str(e)}), 404
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("complete_interview failed")
        return jsonify({"success": False, "error": "An error occurred"}), 500


@bp.route("/my-interviews", methods=["GET"])
@jwt_required()
def my_interviews():
    """
    Get interviews for the current user (candidate or recruiter).

    Bug #6 fix: auto-completes expired interviews via bulk update_many
    before fetching, so past-dated interviews no longer show as 'scheduled'.

    Returns:
        200: { success: true, data: [...], total: N }
    """
    user_id, role = _user_id_and_role()
    if not user_id:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        # Bug #6: bulk auto-complete expired interviews (30min grace period)
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=30)
        db = get_db()
        auto_result = db["interviews"].update_many(
            {
                "status": "scheduled",
                "scheduled_at": {"$lt": cutoff},
            },
            {
                "$set": {
                    "status": "completed",
                    "completed_at": now,
                    "auto_completed": True,
                    "auto_complete_reason": "Past scheduled time + grace period",
                }
            },
        )
        if auto_result.modified_count > 0:
            logger.info(
                f"Bug #6: Auto-completed {auto_result.modified_count} expired interview(s)"
            )

        if role in ("company", "recruiter", "admin"):
            interviews = interview_service.list_interviews_for_recruiter(user_id)
        else:
            interviews = interview_service.list_interviews_for_candidate(user_id)

        return jsonify({
            "success": True,
            "data": interviews,
            "total": len(interviews),
        }), 200
    except Exception as e:
        logger.exception("my_interviews failed")
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/job/<job_id>", methods=["GET"])
@jwt_required()
@require_permission(Permissions.VIEW_CANDIDATES)
def interviews_for_job(job_id):
    """
    Get all interviews for a specific job.

    Returns:
        200: { success: true, data: [...], total: N }
    """
    try:
        interviews = interview_service.list_interviews_for_job(job_id)
        return jsonify({
            "success": True,
            "data": interviews,
            "total": len(interviews),
        }), 200
    except Exception as e:
        logger.exception("interviews_for_job failed")
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/candidate/<candidate_id>", methods=["GET"])
@jwt_required()
def interviews_for_candidate(candidate_id):
    """
    Get all interviews for a specific candidate.

    Returns:
        200: { success: true, data: [...], total: N }
    """
    user_id, role = _user_id_and_role()

    # Candidates can only view their own interviews
    if role == "candidate" and user_id != candidate_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    try:
        interviews = interview_service.list_interviews_for_candidate(candidate_id)
        return jsonify({
            "success": True,
            "data": interviews,
            "total": len(interviews),
        }), 200
    except Exception as e:
        logger.exception("interviews_for_candidate failed")
        return jsonify({"success": False, "error": str(e)}), 500
