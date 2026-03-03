"""
Committee Override & Interview Rubrics Routes — Phase 4/5 completion
=====================================================================
Human-in-the-loop panel override of ML recommendations + configurable rubrics.

Endpoints:
  POST   /api/committee/override/<app_id>           — Override ML decision
  GET    /api/committee/overrides                    — List all overrides
  GET    /api/committee/overrides/<app_id>           — Get override for application

  POST   /api/committee/rubrics                     — Create interview rubric
  GET    /api/committee/rubrics                     — List rubrics
  GET    /api/committee/rubrics/<rubric_id>         — Get rubric detail
  PUT    /api/committee/rubrics/<rubric_id>         — Update rubric
  DELETE /api/committee/rubrics/<rubric_id>         — Delete rubric
  POST   /api/committee/rubrics/<rubric_id>/score   — Score a candidate using rubric

  POST   /api/committee/bias/analyze                — Analyze bias
  POST   /api/committee/bias/correct                — Apply bias corrections
  GET    /api/committee/bias/history                — Correction history

Blueprint prefix (registered in app.py): /api/committee
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId

from backend.models.database import get_db
from backend.security.rbac import require_role, require_permission, Permissions

logger = logging.getLogger(__name__)

bp = Blueprint("committee", __name__)


def _user_id_and_role():
    identity = get_jwt_identity()
    if identity is None:
        return None, None
    if isinstance(identity, dict):
        return str(identity.get("user_id", "")), identity.get("role")
    claims = get_jwt() or {}
    return str(identity), claims.get("role")


# ═══════════════════════════ COMMITTEE OVERRIDES ═════════════════════════════

@bp.route("/override/<app_id>", methods=["POST"])
@jwt_required()
@require_role(["admin", "company"])
def override_ml_decision(app_id):
    """
    Human override of ML recommendation.

    Body:
        new_status: str ('hire' | 'reject' | 'review' | 'shortlist')
        justification: str (required — free-text reason)
        committee_members: list[str] (optional — list of reviewer names/IDs)
        override_score: float (optional — manual score 0-100)
    """
    user_id, role = _user_id_and_role()
    data = request.get_json() or {}

    new_status = data.get("new_status")
    justification = data.get("justification")

    if not new_status or not justification:
        return jsonify({"error": "new_status and justification are required"}), 400

    valid_statuses = ["hire", "reject", "review", "shortlist"]
    if new_status not in valid_statuses:
        return jsonify({"error": f"new_status must be one of: {valid_statuses}"}), 400

    db = get_db()
    application = db["applications"].find_one({"_id": ObjectId(app_id)})
    if not application:
        return jsonify({"error": "Application not found"}), 404

    # Record the override
    override_record = {
        "application_id": app_id,
        "original_status": application.get("status"),
        "original_score": application.get("overall_score"),
        "new_status": new_status,
        "override_score": data.get("override_score"),
        "justification": justification,
        "committee_members": data.get("committee_members", [user_id]),
        "overridden_by": user_id,
        "overridden_by_role": role,
        "created_at": datetime.utcnow(),
    }

    # Save override log
    db["committee_overrides"].insert_one(override_record)

    # Update the application
    update_fields = {
        "status": new_status if new_status != "hire" else "hired",
        "committee_override": True,
        "committee_override_at": datetime.utcnow(),
        "committee_justification": justification,
    }
    if data.get("override_score") is not None:
        update_fields["overall_score"] = data["override_score"]

    db["applications"].update_one(
        {"_id": ObjectId(app_id)},
        {"$set": update_fields}
    )

    logger.info("Committee override: app=%s status=%s→%s by=%s",
                app_id, application.get("status"), new_status, user_id)

    override_record["_id"] = str(override_record.get("_id", ""))
    return jsonify({
        "success": True,
        "message": f"ML decision overridden to '{new_status}'.",
        "override": override_record,
    }), 200


@bp.route("/overrides", methods=["GET"])
@jwt_required()
@require_role(["admin", "company"])
def list_overrides():
    """List all committee overrides with pagination."""
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    skip = (page - 1) * per_page

    db = get_db()
    total = db["committee_overrides"].count_documents({})
    overrides = list(
        db["committee_overrides"]
        .find()
        .sort("created_at", -1)
        .skip(skip)
        .limit(per_page)
    )
    for o in overrides:
        o["_id"] = str(o["_id"])

    return jsonify({"success": True, "data": overrides, "total": total}), 200


@bp.route("/overrides/<app_id>", methods=["GET"])
@jwt_required()
@require_role(["admin", "company"])
def get_override(app_id):
    """Get override history for a specific application."""
    db = get_db()
    overrides = list(
        db["committee_overrides"]
        .find({"application_id": app_id})
        .sort("created_at", -1)
    )
    for o in overrides:
        o["_id"] = str(o["_id"])
    return jsonify({"success": True, "data": overrides}), 200


# ═══════════════════════ CONFIGURABLE INTERVIEW RUBRICS ══════════════════════

DEFAULT_RUBRIC_CRITERIA = [
    {"name": "Technical Knowledge", "weight": 30, "description": "Depth and accuracy of technical answers"},
    {"name": "Problem Solving", "weight": 25, "description": "Approach to solving coding/logic problems"},
    {"name": "Communication", "weight": 20, "description": "Clarity, structure, and articulation"},
    {"name": "Cultural Fit", "weight": 15, "description": "Alignment with company values and teamwork"},
    {"name": "Initiative & Learning", "weight": 10, "description": "Curiosity, self-improvement, adaptability"},
]


@bp.route("/rubrics", methods=["POST"])
@jwt_required()
@require_role(["admin", "company"])
def create_rubric():
    """
    Create a configurable interview rubric.

    Body:
        name: str (required)
        description: str (optional)
        job_level: str ('fresher' | 'entry' | 'mid' | 'senior')
        criteria: list of { name: str, weight: int (0-100), description: str }
            (weights must sum to 100)
    """
    user_id, _ = _user_id_and_role()
    data = request.get_json() or {}

    name = data.get("name")
    if not name:
        return jsonify({"error": "name is required"}), 400

    criteria = data.get("criteria", DEFAULT_RUBRIC_CRITERIA)

    # Validate weights sum to 100
    total_weight = sum(c.get("weight", 0) for c in criteria)
    if total_weight != 100:
        return jsonify({"error": f"Criteria weights must sum to 100 (got {total_weight})"}), 400

    db = get_db()
    rubric = {
        "name": name,
        "description": data.get("description", ""),
        "job_level": data.get("job_level", "entry"),
        "criteria": criteria,
        "created_by": user_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
    }

    result = db["interview_rubrics"].insert_one(rubric)
    rubric["_id"] = str(result.inserted_id)

    return jsonify({"success": True, "rubric": rubric}), 201


@bp.route("/rubrics", methods=["GET"])
@jwt_required()
@require_role(["admin", "company"])
def list_rubrics():
    """List all active rubrics."""
    db = get_db()
    rubrics = list(db["interview_rubrics"].find({"is_active": True}).sort("created_at", -1))
    for r in rubrics:
        r["_id"] = str(r["_id"])
    return jsonify({"success": True, "data": rubrics}), 200


@bp.route("/rubrics/<rubric_id>", methods=["GET"])
@jwt_required()
@require_role(["admin", "company"])
def get_rubric(rubric_id):
    """Get a specific rubric."""
    db = get_db()
    rubric = db["interview_rubrics"].find_one({"_id": ObjectId(rubric_id)})
    if not rubric:
        return jsonify({"error": "Rubric not found"}), 404
    rubric["_id"] = str(rubric["_id"])
    return jsonify({"success": True, "rubric": rubric}), 200


@bp.route("/rubrics/<rubric_id>", methods=["PUT"])
@jwt_required()
@require_role(["admin", "company"])
def update_rubric(rubric_id):
    """Update rubric criteria/weights."""
    data = request.get_json() or {}
    db = get_db()

    update = {"updated_at": datetime.utcnow()}
    if "name" in data:
        update["name"] = data["name"]
    if "description" in data:
        update["description"] = data["description"]
    if "job_level" in data:
        update["job_level"] = data["job_level"]
    if "criteria" in data:
        total_weight = sum(c.get("weight", 0) for c in data["criteria"])
        if total_weight != 100:
            return jsonify({"error": f"Criteria weights must sum to 100 (got {total_weight})"}), 400
        update["criteria"] = data["criteria"]

    result = db["interview_rubrics"].update_one(
        {"_id": ObjectId(rubric_id)},
        {"$set": update}
    )
    if result.matched_count == 0:
        return jsonify({"error": "Rubric not found"}), 404

    return jsonify({"success": True, "message": "Rubric updated."}), 200


@bp.route("/rubrics/<rubric_id>", methods=["DELETE"])
@jwt_required()
@require_role(["admin"])
def delete_rubric(rubric_id):
    """Soft-delete a rubric."""
    db = get_db()
    result = db["interview_rubrics"].update_one(
        {"_id": ObjectId(rubric_id)},
        {"$set": {"is_active": False, "deleted_at": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "Rubric not found"}), 404
    return jsonify({"success": True, "message": "Rubric deleted."}), 200


@bp.route("/rubrics/<rubric_id>/score", methods=["POST"])
@jwt_required()
@require_role(["admin", "company"])
def score_with_rubric(rubric_id):
    """
    Score a candidate's interview using a rubric.

    Body:
        application_id: str (required)
        scores: dict mapping criterion name → int score (1-10)
        notes: str (optional)
        interviewer_name: str (optional)
    """
    user_id, _ = _user_id_and_role()
    data = request.get_json() or {}

    application_id = data.get("application_id")
    scores = data.get("scores", {})

    if not application_id or not scores:
        return jsonify({"error": "application_id and scores are required"}), 400

    db = get_db()
    rubric = db["interview_rubrics"].find_one({"_id": ObjectId(rubric_id), "is_active": True})
    if not rubric:
        return jsonify({"error": "Rubric not found"}), 404

    # Calculate weighted score
    criteria_map = {c["name"]: c["weight"] for c in rubric["criteria"]}
    total_weighted = 0
    max_possible = 0
    score_breakdown = []

    for criterion_name, weight in criteria_map.items():
        raw_score = scores.get(criterion_name, 0)
        raw_score = max(0, min(10, raw_score))  # Clamp 0-10
        weighted = (raw_score / 10) * weight
        total_weighted += weighted
        max_possible += weight
        score_breakdown.append({
            "criterion": criterion_name,
            "raw_score": raw_score,
            "weight": weight,
            "weighted_score": round(weighted, 2),
        })

    final_score = round((total_weighted / max_possible) * 100, 2) if max_possible else 0

    # Save rubric score
    rubric_score_record = {
        "application_id": application_id,
        "rubric_id": rubric_id,
        "rubric_name": rubric["name"],
        "scores": scores,
        "score_breakdown": score_breakdown,
        "final_score": final_score,
        "notes": data.get("notes", ""),
        "interviewer_name": data.get("interviewer_name", ""),
        "scored_by": user_id,
        "scored_at": datetime.utcnow(),
    }

    db["rubric_scores"].insert_one(rubric_score_record)

    # Update application with rubric score
    db["applications"].update_one(
        {"_id": ObjectId(application_id)},
        {"$set": {
            "rubric_score": final_score,
            "rubric_breakdown": score_breakdown,
            "last_rubric_scored_at": datetime.utcnow(),
        }}
    )

    rubric_score_record["_id"] = str(rubric_score_record.get("_id", ""))
    return jsonify({
        "success": True,
        "final_score": final_score,
        "breakdown": score_breakdown,
        "record": rubric_score_record,
    }), 200


# ═══════════════════════ BIAS CORRECTION ENDPOINTS ═══════════════════════════

@bp.route("/bias/analyze", methods=["POST"])
@jwt_required()
@require_role(["admin", "company"])
def analyze_bias():
    """
    Analyze current hiring pipeline for bias.

    Body (optional):
        job_id: str — filter by specific job
    """
    data = request.get_json() or {}
    job_id = data.get("job_id")

    try:
        from backend.services.bias_correction_service import bias_correction_engine
        result = bias_correction_engine.analyze_bias(job_id=job_id)
        return jsonify({"success": True, **result}), 200
    except Exception as e:
        logger.exception("Bias analysis failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/bias/correct", methods=["POST"])
@jwt_required()
@require_role(["admin"])
def apply_bias_correction():
    """
    Apply bias corrections to scores.

    Body:
        job_id: str (optional)
        dry_run: bool (default true — preview only; set false to apply)
    """
    data = request.get_json() or {}
    job_id = data.get("job_id")
    dry_run = data.get("dry_run", True)

    try:
        from backend.services.bias_correction_service import bias_correction_engine
        result = bias_correction_engine.apply_corrections(job_id=job_id, dry_run=dry_run)
        return jsonify({"success": True, **result}), 200
    except Exception as e:
        logger.exception("Bias correction failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/bias/history", methods=["GET"])
@jwt_required()
@require_role(["admin", "company"])
def bias_correction_history():
    """Get bias correction history logs."""
    job_id = request.args.get("job_id")
    limit = int(request.args.get("limit", 20))

    try:
        from backend.services.bias_correction_service import bias_correction_engine
        logs = bias_correction_engine.get_correction_history(job_id=job_id, limit=limit)
        return jsonify({"success": True, "data": logs}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
