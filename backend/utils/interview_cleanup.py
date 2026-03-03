"""
Bug #6 Fix:  Auto-complete past interviews that are still marked as active.

Usage:
  • Called once on app startup (see app.py) for immediate cleanup.
  • Optionally invoked periodically via Celery Beat or cron.

Logic:
  1. Find `video_interview_sessions` with status IN (scheduled, in_progress)
     AND `scheduled_at` older than a configurable threshold (default 24 h).
  2. Mark each as `completed` with an `auto_completed` flag.
  3. Update the matching `application` status to `interview_completed`.
"""

import logging
from datetime import datetime, timedelta
from backend.models.database import get_db

logger = logging.getLogger(__name__)

DEFAULT_STALE_HOURS = 24  # interviews older than this are considered stale


def auto_complete_stale_interviews(stale_hours: int = DEFAULT_STALE_HOURS) -> int:
    """
    Mark all stale interview sessions as completed.

    Returns:
        Number of interviews auto-completed.
    """
    try:
        db = get_db()
        sessions_col = db['video_interview_sessions']
        apps_col = db['applications']

        cutoff = datetime.utcnow() - timedelta(hours=stale_hours)

        stale_sessions = list(sessions_col.find({
            'status': {'$in': ['scheduled', 'in_progress']},
            'scheduled_at': {'$lt': cutoff}
        }))

        count = 0
        for session in stale_sessions:
            sessions_col.update_one(
                {'_id': session['_id']},
                {'$set': {
                    'status': 'completed',
                    'completed_at': datetime.utcnow(),
                    'auto_completed': True,
                    'auto_complete_reason': f'Stale after {stale_hours}h'
                }}
            )

            # Also update the application status if linked
            app_id = session.get('application_id')
            if app_id:
                apps_col.update_one(
                    {'_id': app_id},
                    {'$set': {'interview_status': 'completed'}}
                )

            count += 1

        if count:
            logger.info(f"⏰ Auto-completed {count} stale interview(s)")
        else:
            logger.debug("No stale interviews to auto-complete")

        return count

    except Exception as e:
        logger.error(f"Interview auto-complete failed: {e}")
        return 0
