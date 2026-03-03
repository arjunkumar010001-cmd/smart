"""
Analytics API - interview metrics and reporting.
Filter by recruiter (user_id) since jobs use recruiter_id.
Migrated from v1 (smart-hiring-system) into v2 enterprise codebase.
"""

import logging
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId

from backend.models.database import get_db
from backend.utils.rbac_decorator import require_permission

logger = logging.getLogger(__name__)

bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


def _current_user_id():
    identity = get_jwt_identity()
    if identity is None:
        return None
    if isinstance(identity, dict):
        return identity.get("user_id")
    return identity


@bp.route("/interview-metrics", methods=["GET"])
@jwt_required()
@require_permission("ANALYTICS_VIEW")
def get_interview_metrics():
    """
    Interview analytics for the current recruiter's jobs.
    Query params: days (default 30), job_id (optional).
    Returns: total_scheduled, completion_rate, no_show_rate, time_series, top_interviewers.
    """
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    days = request.args.get("days", 30, type=int)
    job_id = request.args.get("job_id")
    start_date = datetime.utcnow() - timedelta(days=days)
    db = get_db()

    match_criteria = {"scheduled_at": {"$gte": start_date}}
    if job_id:
        match_criteria["job_id"] = job_id
    pipeline = [
        {"$match": match_criteria},
        {
            "$lookup": {
                "from": "jobs",
                "let": {"jid": "$job_id"},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$_id", {"$toObjectId": {"$ifNull": ["$$jid", ""]}}]}}}
                ],
                "as": "job",
            }
        },
        {"$unwind": {"path": "$job", "preserveNullAndEmptyArrays": True}},
        {"$match": {"job.recruiter_id": str(user_id)}},
    ]

    stats_pipeline = pipeline + [
        {
            "$group": {
                "_id": None,
                "total_scheduled": {"$sum": 1},
                "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
                "no_shows": {"$sum": {"$cond": [{"$eq": ["$status", "no_show"]}, 1, 0]}},
                "cancelled": {"$sum": {"$cond": [{"$eq": ["$status", "cancelled"]}, 1, 0]}},
                "scheduled": {"$sum": {"$cond": [{"$eq": ["$status", "scheduled"]}, 1, 0]}},
                "avg_duration": {"$avg": "$duration_minutes"},
                "avg_panel_size": {"$avg": {"$size": {"$ifNull": ["$panel", []]}}},
            }
        }
    ]

    stats_result = list(db["interviews"].aggregate(stats_pipeline))
    if not stats_result:
        return jsonify({
            "success": True,
            "data": {
                "total_scheduled": 0,
                "completed": 0,
                "no_shows": 0,
                "cancelled": 0,
                "scheduled": 0,
                "completion_rate": 0,
                "no_show_rate": 0,
                "cancellation_rate": 0,
                "avg_duration": 0,
                "avg_panel_size": 0,
                "time_series": [],
                "top_interviewers": [],
            }
        }), 200

    stats = stats_result[0]
    total = stats["total_scheduled"]
    completion_rate = (stats["completed"] / total * 100) if total > 0 else 0
    no_show_rate = (stats["no_shows"] / total * 100) if total > 0 else 0
    cancellation_rate = (stats["cancelled"] / total * 100) if total > 0 else 0

    timeseries_pipeline = pipeline + [
        {
            "$group": {
                "_id": {
                    "year": {"$year": "$scheduled_at"},
                    "week": {"$week": "$scheduled_at"},
                },
                "count": {"$sum": 1},
                "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
                "no_shows": {"$sum": {"$cond": [{"$eq": ["$status", "no_show"]}, 1, 0]}},
            }
        },
        {"$sort": {"_id.year": 1, "_id.week": 1}},
    ]
    time_series = list(db["interviews"].aggregate(timeseries_pipeline))
    time_series_data = [
        {
            "week": f"{item['_id']['year']}-W{item['_id']['week']}",
            "total": item["count"],
            "completed": item["completed"],
            "no_shows": item["no_shows"],
        }
        for item in time_series
    ]

    top_pipeline = pipeline + [
        {"$unwind": {"path": "$panel", "preserveNullAndEmptyArrays": False}},
        {
            "$group": {
                "_id": "$panel.user_id",
                "name": {"$first": "$panel.name"},
                "count": {"$sum": 1},
                "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_interviewers = list(db["interviews"].aggregate(top_pipeline))
    top_data = [
        {
            "user_id": str(item["_id"]),
            "name": item.get("name", ""),
            "total_interviews": item["count"],
            "completed": item["completed"],
            "completion_rate": round(item["completed"] / item["count"] * 100, 1) if item["count"] > 0 else 0,
        }
        for item in top_interviewers
    ]

    return jsonify({
        "success": True,
        "data": {
            "total_scheduled": total,
            "completed": stats["completed"],
            "no_shows": stats["no_shows"],
            "cancelled": stats["cancelled"],
            "scheduled": stats["scheduled"],
            "completion_rate": round(completion_rate, 2),
            "no_show_rate": round(no_show_rate, 2),
            "cancellation_rate": round(cancellation_rate, 2),
            "avg_duration": round(stats["avg_duration"] or 0, 1),
            "avg_panel_size": round(stats["avg_panel_size"] or 0, 1),
            "time_series": time_series_data,
            "top_interviewers": top_data,
        }
    }), 200
