"""
MongoDB Index Setup Script
============================
Creates required indexes for the Smart Assessment collections.
Run once after initial deployment or when adding new collections.

Usage:
    python -m backend.scripts.setup_indexes
    # or from project root:
    python backend/scripts/setup_indexes.py
"""

import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pymongo import MongoClient, ASCENDING, DESCENDING
from config.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_indexes(db):
    """Create all required indexes for the Smart Assessment system."""

    logger.info("Creating indexes for Smart Assessment collections...")

    # ── assessment_configs ──────────────────────────────────────────────────
    db["assessment_configs"].create_index(
        [("created_by", ASCENDING), ("is_active", ASCENDING)],
        name="idx_configs_creator_active",
    )
    db["assessment_configs"].create_index(
        [("is_active", ASCENDING), ("created_at", DESCENDING)],
        name="idx_configs_active_date",
    )
    db["assessment_configs"].create_index(
        [("job_role", ASCENDING), ("is_active", ASCENDING)],
        name="idx_configs_role_active",
    )
    logger.info("  ✓ assessment_configs indexes created")

    # ── smart_sessions ──────────────────────────────────────────────────────
    db["smart_sessions"].create_index(
        [("candidate_id", ASCENDING), ("status", ASCENDING)],
        name="idx_sessions_candidate_status",
    )
    db["smart_sessions"].create_index(
        [("config_id", ASCENDING), ("status", ASCENDING)],
        name="idx_sessions_config_status",
    )
    db["smart_sessions"].create_index(
        [("candidate_id", ASCENDING), ("config_id", ASCENDING), ("status", ASCENDING)],
        name="idx_sessions_candidate_config_status",
    )
    db["smart_sessions"].create_index(
        [("status", ASCENDING), ("created_at", DESCENDING)],
        name="idx_sessions_status_date",
    )
    db["smart_sessions"].create_index(
        [("expires_at", ASCENDING)],
        name="idx_sessions_expiry",
        expireAfterSeconds=0,  # TTL — auto-delete expired sessions (optional)
        partialFilterExpression={"status": "expired"},
    )
    logger.info("  ✓ smart_sessions indexes created")

    # ── ai_questions (question bank / cache) ────────────────────────────────
    db["ai_questions"].create_index(
        [("job_role", ASCENDING), ("type", ASCENDING), ("topic", ASCENDING),
         ("difficulty", ASCENDING), ("is_active", ASCENDING)],
        name="idx_questions_generation_lookup",
    )
    db["ai_questions"].create_index(
        [("fingerprint", ASCENDING)],
        name="idx_questions_fingerprint",
        unique=True,
        sparse=True,
    )
    db["ai_questions"].create_index(
        [("id", ASCENDING)],
        name="idx_questions_id",
    )
    db["ai_questions"].create_index(
        [("usage_count", ASCENDING)],
        name="idx_questions_usage_count",
    )
    logger.info("  ✓ ai_questions indexes created")

    # ── code_submissions ────────────────────────────────────────────────────
    db["code_submissions"].create_index(
        [("session_id", ASCENDING), ("question_id", ASCENDING)],
        name="idx_submissions_session_question",
    )
    db["code_submissions"].create_index(
        [("candidate_id", ASCENDING), ("submitted_at", DESCENDING)],
        name="idx_submissions_candidate_date",
    )
    logger.info("  ✓ code_submissions indexes created")

    # ── api_usage (cost tracking — optional) ───────────────────────────────
    db["api_usage"].create_index(
        [("date", ASCENDING), ("provider", ASCENDING)],
        name="idx_api_usage_date_provider",
        unique=True,
    )
    logger.info("  ✓ api_usage indexes created")

    logger.info("All Smart Assessment indexes created successfully!")


def main():
    uri = Config.MONGODB_URI
    db_name = Config.DB_NAME

    logger.info("Connecting to MongoDB: %s / %s", uri, db_name)
    client = MongoClient(uri)
    db = client[db_name]

    create_indexes(db)

    # Print existing collections and index counts
    logger.info("\nCollection index summary:")
    for coll_name in ["assessment_configs", "smart_sessions", "ai_questions",
                       "code_submissions", "api_usage"]:
        indexes = list(db[coll_name].list_indexes())
        logger.info("  %s: %d indexes", coll_name, len(indexes))
        for idx in indexes:
            logger.info("    - %s", idx["name"])

    client.close()
    logger.info("\nDone.")


if __name__ == "__main__":
    main()
