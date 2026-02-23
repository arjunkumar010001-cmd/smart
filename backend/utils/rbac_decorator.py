"""
Role-based access control decorator for API routes.
Lightweight RBAC used by analytics_routes and llm_routes (migrated from v1).

For the full enterprise RBAC system, see backend.security.rbac.

Usage:
    @bp.route('/schedule', methods=['POST'])
    @jwt_required()
    @require_permission('SCHEDULE_INTERVIEW')
    def schedule_interview():
        ...
"""

import logging
from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt

logger = logging.getLogger(__name__)

# Permissions mapped to allowed roles
PERMISSION_ROLES = {
    "SCHEDULE_INTERVIEW": ("recruiter", "company", "admin"),
    "CONDUCT_INTERVIEW": ("recruiter", "company", "admin", "interviewer"),
    "SUBMIT_EVALUATION": ("recruiter", "company", "admin", "interviewer"),
    "JOB_CREATE": ("recruiter", "company", "admin"),
    "JOB_EDIT": ("recruiter", "company", "admin"),
    "JOB_DELETE": ("recruiter", "company", "admin"),
    "CANDIDATE_VIEW": ("recruiter", "company", "admin"),
    "CANDIDATE_EDIT": ("recruiter", "company", "admin"),
    "USER_MANAGEMENT": ("admin",),
    "ANALYTICS_VIEW": ("recruiter", "company", "admin"),
}


def _current_user_identity():
    """Return (user_id, role). get_jwt_identity() may be dict or string."""
    identity = get_jwt_identity()
    if identity is None:
        return None, None
    if isinstance(identity, dict):
        return identity.get("user_id"), identity.get("role")
    # identity is string (user_id); role from additional_claims
    claims = get_jwt() or {}
    return identity, claims.get("role")


def require_permission(permission: str):
    """Decorator that requires the current user to have the given permission (role check)."""

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user_id, role = _current_user_identity()
            if user_id is None:
                return jsonify({"error": "Authentication required"}), 401
            allowed = PERMISSION_ROLES.get(permission, ())
            if role not in allowed:
                logger.warning("Permission denied: user=%s role=%s permission=%s", user_id, role, permission)
                return jsonify({"error": "You do not have permission to perform this action"}), 403
            return f(*args, **kwargs)

        return wrapped

    return decorator
