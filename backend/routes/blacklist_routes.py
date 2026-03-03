"""
Blacklist Routes
=================
CRUD + enforcement for candidate blacklisting.

Endpoints:
  POST   /api/blacklist/add                — Blacklist a candidate
  DELETE /api/blacklist/<candidate_id>     — Remove from blacklist
  GET    /api/blacklist                    — List all blacklisted candidates
  GET    /api/blacklist/check/<candidate_id> — Check if candidate is blacklisted

Blueprint prefix (registered in app.py): /api/blacklist
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId

from backend.models.database import get_db
from backend.security.rbac import require_permission, require_role, Permissions

logger = logging.getLogger(__name__)

bp = Blueprint("blacklist", __name__)


def _user_id_and_role():
    identity = get_jwt_identity()
    if identity is None:
        return None, None
    if isinstance(identity, dict):
        return str(identity.get("user_id", "")), identity.get("role")
    claims = get_jwt() or {}
    return str(identity), claims.get("role")


# ── Enforcement helper — import this in other routes ──────────────────────────

def is_blacklisted(candidate_id: str) -> bool:
    """Check whether a candidate_id is on the blacklist. O(1) indexed lookup."""
    try:
        db = get_db()
        entry = db["blacklist"].find_one({"candidate_id": str(candidate_id)})
        return entry is not None
    except Exception:
        return False


def enforce_blacklist(candidate_id: str):
    """Return a (response, status) tuple if blacklisted, else None."""
    if is_blacklisted(candidate_id):
        return jsonify({
            "error": "Your account has been restricted. Contact support for details.",
            "code": "BLACKLISTED"
        }), 403
    return None


# ── Routes ────────────────────────────────────────────────────────────────────

@bp.route("/add", methods=["POST"])
@jwt_required()
@require_role(["admin", "company"])
def add_to_blacklist():
    """
    Blacklist a candidate.

    Body:
        candidate_id: str (required)
        reason: str (required)
        severity: str ('warning' | 'temporary' | 'permanent', default 'permanent')
        notes: str (optional)
    """
    user_id, role = _user_id_and_role()
    data = request.get_json() or {}

    candidate_id = data.get("candidate_id")
    reason = data.get("reason")

    if not candidate_id or not reason:
        return jsonify({"error": "candidate_id and reason are required"}), 400

    severity = data.get("severity", "permanent")
    if severity not in ("warning", "temporary", "permanent"):
        severity = "permanent"

    db = get_db()

    # Check candidate exists
    candidate = db["users"].find_one({"_id": ObjectId(candidate_id)}) or \
                db["users"].find_one({"user_id": candidate_id})
    # Allow blacklisting even if user record missing (e.g. deleted account)

    # Upsert — update reason if already blacklisted
    db["blacklist"].update_one(
        {"candidate_id": str(candidate_id)},
        {"$set": {
            "candidate_id": str(candidate_id),
            "reason": reason,
            "severity": severity,
            "notes": data.get("notes", ""),
            "blacklisted_by": user_id,
            "blacklisted_by_role": role,
            "blacklisted_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True
        }},
        upsert=True,
    )

    logger.info("Candidate %s blacklisted by %s: %s", candidate_id, user_id, reason)

    return jsonify({
        "success": True,
        "message": f"Candidate {candidate_id} has been blacklisted.",
        "severity": severity,
    }), 201


@bp.route("/<candidate_id>", methods=["DELETE"])
@jwt_required()
@require_role(["admin"])
def remove_from_blacklist(candidate_id):
    """Remove a candidate from the blacklist (admin only)."""
    user_id, _ = _user_id_and_role()
    db = get_db()

    result = db["blacklist"].delete_one({"candidate_id": str(candidate_id)})
    if result.deleted_count == 0:
        return jsonify({"error": "Candidate not found in blacklist"}), 404

    logger.info("Candidate %s removed from blacklist by %s", candidate_id, user_id)
    return jsonify({"success": True, "message": "Candidate removed from blacklist."}), 200


@bp.route("", methods=["GET"])
@jwt_required()
@require_role(["admin", "company"])
def list_blacklisted():
    """List all blacklisted candidates with pagination."""
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    skip = (page - 1) * per_page

    db = get_db()
    total = db["blacklist"].count_documents({"is_active": True})
    entries = list(
        db["blacklist"]
        .find({"is_active": True})
        .sort("blacklisted_at", -1)
        .skip(skip)
        .limit(per_page)
    )

    for e in entries:
        e["_id"] = str(e["_id"])
        # Resolve candidate name
        c = db["users"].find_one({"_id": ObjectId(e["candidate_id"])}) if ObjectId.is_valid(e["candidate_id"]) else None
        e["candidate_name"] = c.get("name", "Unknown") if c else "Unknown"
        e["candidate_email"] = c.get("email", "") if c else ""

    return jsonify({
        "success": True,
        "data": entries,
        "total": total,
        "page": page,
        "per_page": per_page,
    }), 200


@bp.route("/check/<candidate_id>", methods=["GET"])
@jwt_required()
def check_blacklist(candidate_id):
    """Check whether a specific candidate is blacklisted."""
    db = get_db()
    entry = db["blacklist"].find_one({"candidate_id": str(candidate_id), "is_active": True})

    if entry:
        entry["_id"] = str(entry["_id"])
        return jsonify({"blacklisted": True, "entry": entry}), 200

    return jsonify({"blacklisted": False}), 200
