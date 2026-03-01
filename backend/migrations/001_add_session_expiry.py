"""
Migration 001: Add expires_at and attempts_remaining to existing assessment sessions.

Run:     python backend/migrations/001_add_session_expiry.py
Rollback: python backend/migrations/001_add_session_expiry.py --rollback

This migration updates all SmartSession documents that are missing
the `expires_at` field (created before the Bug #1 fix) by giving
them a 7-day window from now and 3 default attempts.
"""

import os
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _get_db():
    """Connect to database using app config or fallback to direct pymongo."""
    try:
        from backend.models.database import get_db
        return get_db()
    except Exception:
        from pymongo import MongoClient
        try:
            import dotenv
            dotenv.load_dotenv()
        except ImportError:
            pass
        mongo_uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/smart_hiring')
        client = MongoClient(mongo_uri)
        return client.get_default_database()


def migrate():
    """Add expires_at and attempts_remaining to existing assessment sessions."""
    db = _get_db()
    now = datetime.utcnow()

    # Update sessions missing expires_at
    result = db['smart_sessions'].update_many(
        {'expires_at': {'$exists': False}},
        {'$set': {
            'expires_at': now + timedelta(days=7),
            'attempts_remaining': 3,
            'migrated_at': now,
            'migration': '001_add_session_expiry'
        }}
    )
    print(f"[OK] Updated {result.modified_count} sessions with expires_at")

    # Update sessions missing attempts_remaining
    result2 = db['smart_sessions'].update_many(
        {'attempts_remaining': {'$exists': False}},
        {'$set': {
            'attempts_remaining': 3,
            'migrated_at': now,
            'migration': '001_add_session_expiry'
        }}
    )
    print(f"[OK] Updated {result2.modified_count} sessions with attempts_remaining")

    # Add indexes for performance
    db['smart_sessions'].create_index([('candidate_id', 1), ('config_id', 1)])
    db['smart_sessions'].create_index([('expires_at', 1)])
    db['smart_sessions'].create_index([('status', 1)])
    print("[OK] Indexes created on smart_sessions")

    # Also add index for interview auto-complete (Bug #6)
    db['interviews'].create_index([('status', 1), ('scheduled_at', 1)])
    print("[OK] Index created on interviews (status + scheduled_at)")

    print("\n[DONE] Migration 001 complete!")


def rollback():
    """Remove fields added by this migration if deployment fails."""
    db = _get_db()

    # Remove migration-added fields
    result = db['smart_sessions'].update_many(
        {'migration': '001_add_session_expiry'},
        {'$unset': {
            'expires_at': '',
            'attempts_remaining': '',
            'migrated_at': '',
            'migration': ''
        }}
    )
    print(f"[OK] Rolled back {result.modified_count} sessions (removed expires_at, attempts)")

    # Drop indexes (safe — won't error if they don't exist)
    try:
        db['smart_sessions'].drop_index([('candidate_id', 1), ('config_id', 1)])
    except Exception:
        pass
    try:
        db['smart_sessions'].drop_index([('expires_at', 1)])
    except Exception:
        pass
    try:
        db['interviews'].drop_index([('status', 1), ('scheduled_at', 1)])
    except Exception:
        pass

    print("[OK] Indexes dropped")
    print("\n[DONE] Rollback 001 complete!")


if __name__ == '__main__':
    print("\n" + "=" * 50)
    if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
        print("  Migration 001: ROLLBACK")
        print("=" * 50 + "\n")
        rollback()
    else:
        print("  Migration 001: Add Session Expiry")
        print("=" * 50 + "\n")
        migrate()
