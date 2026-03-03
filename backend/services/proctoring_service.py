"""
Proctoring Service
==================
Server-side violation engine for Smart Assessment proctoring.

Handles a SINGLE SocketIO event ('proctoring_event') and routes it through
a dual-threshold consequence engine:

  session_score  — cumulative per-session; terminates session at >= 15
  blacklist_score — cumulative per-session; permanently blacklists at >= 30

Immediate-blacklist events (multiple_faces, secondary_voice, copy_paste 2nd)
bypass the score engine entirely.

Upload directories (snapshots / recordings) are created per-session so that
the Phase 4 audit report generator knows exactly where to look.

Author: Smart Hiring System
"""

import os
import logging
from datetime import datetime
from typing import Dict, Optional, Any

from flask import current_app
from flask_socketio import emit
from bson import ObjectId

from backend.models.database import get_db

logger = logging.getLogger(__name__)

# ─── Upload path roots ──────────────────────────────────────────────────────
_UPLOADS_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                 'uploads')
)
SNAPSHOTS_DIR = os.path.join(_UPLOADS_ROOT, 'snapshots')
RECORDINGS_DIR = os.path.join(_UPLOADS_ROOT, 'recordings')

# ─── Thresholds (configurable via env) ──────────────────────────────────────
SESSION_TERMINATE_THRESHOLD = int(os.getenv('PROCTOR_SESSION_THRESHOLD', '15'))
BLACKLIST_THRESHOLD = int(os.getenv('PROCTOR_BLACKLIST_THRESHOLD', '30'))

# ─── Event severity & routing table ────────────────────────────────────────
# Each event maps to (session_score_delta, blacklist_score_delta).
# Events with blacklist_delta=0 NEVER contribute to the blacklist score.
EVENT_SEVERITY: Dict[str, tuple] = {
    'right_click':        (1, 0),
    'devtools_open':      (2, 0),
    'audio_anomaly':      (2, 0),
    'tab_switch':         (3, 3),
    'fullscreen_exit':    (3, 3),
    'copy_paste':         (4, 4),
    'face_not_detected':  (2, 2),
}

# Events that immediately terminate + blacklist on FIRST detection.
# They bypass the score engine entirely.
IMMEDIATE_BLACKLIST_EVENTS = frozenset({'multiple_faces', 'secondary_voice'})

# Tab switch thresholds
TAB_SWITCH_WARN_COUNT = 3
TAB_SWITCH_TERMINATE_COUNT = 5

# ─── Helpers ────────────────────────────────────────────────────────────────

def ensure_session_directories(session_id: str) -> None:
    """Create upload directories for a session (idempotent)."""
    for base in (SNAPSHOTS_DIR, RECORDINGS_DIR):
        path = os.path.join(base, session_id)
        os.makedirs(path, exist_ok=True)


def check_blacklist(user_id: str) -> bool:
    """
    Return True if the candidate is blacklisted.
    Call this at the top of candidate-facing assessment routes.
    """
    db = get_db()
    return db['blacklist'].find_one({'candidate_id': user_id}) is not None


def _blacklist_candidate(user_id: str, session_id: str, reason: str) -> None:
    """Insert or update the blacklist record for a candidate."""
    db = get_db()
    db['blacklist'].update_one(
        {'candidate_id': user_id},
        {'$set': {
            'candidate_id': user_id,
            'blacklisted_at': datetime.utcnow(),
            'reason': reason,
            'triggering_session_id': session_id,
        }},
        upsert=True,
    )
    logger.warning(
        "🚫 Candidate %s BLACKLISTED — reason: %s (session %s)",
        user_id, reason, session_id,
    )


def _terminate_session(session_id: str, reason: str) -> None:
    """Force-complete a session and record the termination reason."""
    db = get_db()
    db['smart_sessions'].update_one(
        {'_id': ObjectId(session_id)},
        {'$set': {
            'status': 'terminated',
            'terminated_at': datetime.utcnow(),
            'termination_reason': reason,
        }},
    )
    logger.warning("⛔ Session %s TERMINATED — reason: %s", session_id, reason)

    # Send completion emails (candidate + recruiter)
    try:
        from backend.services.session_emails import send_session_completion_emails
        updated = db['smart_sessions'].find_one({'_id': ObjectId(session_id)})
        send_session_completion_emails(session_id, updated)
    except Exception as e:
        logger.warning("termination email failed: %s", e)


def _pause_session(session_id: str) -> None:
    """Pause the session timer (server-side)."""
    db = get_db()
    db['smart_sessions'].update_one(
        {'_id': ObjectId(session_id), 'status': 'in_progress'},
        {'$set': {
            'status': 'paused',
            'paused_at': datetime.utcnow(),
        }},
    )
    logger.info("⏸️ Session %s PAUSED for warning acknowledgement", session_id)


def _resume_session(session_id: str) -> None:
    """Resume the session timer after warning acknowledgement."""
    db = get_db()
    session = db['smart_sessions'].find_one({'_id': ObjectId(session_id)})
    if not session or session.get('status') != 'paused':
        return

    paused_at = session.get('paused_at')
    if paused_at:
        # Calculate elapsed pause duration and preserve remaining time
        elapsed_pause = (datetime.utcnow() - paused_at).total_seconds()
        logger.info(
            "▶️ Session %s RESUMED after %.1fs pause", session_id, elapsed_pause
        )

    db['smart_sessions'].update_one(
        {'_id': ObjectId(session_id)},
        {
            '$set': {'status': 'in_progress'},
            '$unset': {'paused_at': ''},
        },
    )


def _count_event_type(session_id: str, event_type: str) -> int:
    """Count how many times a specific event type has occurred in a session."""
    db = get_db()
    session = db['smart_sessions'].find_one(
        {'_id': ObjectId(session_id)},
        {'proctoring_events': 1},
    )
    if not session:
        return 0
    return sum(
        1 for e in session.get('proctoring_events', [])
        if e.get('event_type') == event_type
    )


# ─── ProctoringService ─────────────────────────────────────────────────────

class ProctoringService:
    """
    Server-side proctoring engine. Registers a single SocketIO event handler
    ('proctoring_event') and routes violations through the dual-threshold
    consequence engine.
    """

    def __init__(self, app=None):
        self.socketio = None
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Wire SocketIO event handlers. Must be called after SocketIO init."""
        assert hasattr(app, 'socketio') and app.socketio is not None, (
            'SocketIO must be initialized on app before '
            'ProctoringService.init_app() is called'
        )
        self.socketio = app.socketio
        self._register_handlers()
        logger.info("✅ Proctoring service initialized")

    def _register_handlers(self):
        """Register the single unified proctoring event handler."""

        @self.socketio.on('proctoring_event')
        def handle_proctoring_event(data):
            """
            Unified handler for all proctoring events.

            Expected payload:
                {
                    event_type: str,
                    session_id: str,
                    timestamp: str (ISO),
                    metadata: dict
                }
            """
            event_type = data.get('event_type')
            session_id = data.get('session_id')
            timestamp = data.get('timestamp', datetime.utcnow().isoformat())
            metadata = data.get('metadata', {})

            if not event_type or not session_id:
                emit('proctoring_error', {
                    'error': 'Missing event_type or session_id'
                })
                return

            try:
                result = self._process_event(
                    event_type, session_id, timestamp, metadata
                )
                # Always ack the event back to client with consequence info
                emit('proctoring_ack', result)
            except Exception as e:
                logger.error(
                    "Proctoring event error: %s (session=%s, event=%s)",
                    e, session_id, event_type, exc_info=True,
                )
                emit('proctoring_error', {'error': str(e)})

        @self.socketio.on('resume_session')
        def handle_resume_session(data):
            """Client acknowledged warning modal — resume timer."""
            session_id = data.get('session_id')
            if not session_id:
                emit('proctoring_error', {'error': 'Missing session_id'})
                return
            _resume_session(session_id)
            emit('session_resumed', {'session_id': session_id})

    def _process_event(
        self,
        event_type: str,
        session_id: str,
        timestamp: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Core consequence engine.

        Returns a dict describing the action taken, which is emitted back
        to the client as 'proctoring_ack'.
        """
        db = get_db()
        session = db['smart_sessions'].find_one({'_id': ObjectId(session_id)})

        if not session:
            return {'error': 'Session not found', 'action': 'none'}

        if session.get('status') in ('completed', 'terminated'):
            return {'action': 'none', 'reason': 'session_already_ended'}

        candidate_id = session.get('candidate_id', '')

        # ── Log the event to the session ────────────────────────────────
        event_doc = {
            'event_type': event_type,
            'timestamp': timestamp,
            'metadata': metadata,
            'processed_at': datetime.utcnow(),
        }

        # ── IMMEDIATE BLACKLIST EVENTS ──────────────────────────────────
        if event_type in IMMEDIATE_BLACKLIST_EVENTS:
            event_doc['consequence'] = 'immediate_blacklist'
            db['smart_sessions'].update_one(
                {'_id': ObjectId(session_id)},
                {'$push': {'proctoring_events': event_doc}},
            )
            _terminate_session(session_id, f'immediate_{event_type}')
            _blacklist_candidate(candidate_id, session_id, event_type)
            self.socketio.emit('session_terminated', {
                'session_id': session_id,
                'reason': event_type,
                'blacklisted': True,
            }, room=f'user_{candidate_id}')
            return {
                'action': 'terminated_and_blacklisted',
                'event_type': event_type,
            }

        # ── COPY-PASTE: 2nd occurrence = immediate blacklist ────────────
        if event_type == 'copy_paste':
            prior_count = _count_event_type(session_id, 'copy_paste')
            if prior_count >= 1:
                # This is the 2nd (or later) occurrence — immediate blacklist
                event_doc['consequence'] = 'copy_paste_second_strike'
                db['smart_sessions'].update_one(
                    {'_id': ObjectId(session_id)},
                    {'$push': {'proctoring_events': event_doc}},
                )
                _terminate_session(session_id, 'copy_paste_second_strike')
                _blacklist_candidate(
                    candidate_id, session_id, 'copy_paste_second_strike'
                )
                self.socketio.emit('session_terminated', {
                    'session_id': session_id,
                    'reason': 'copy_paste_second_strike',
                    'blacklisted': True,
                }, room=f'user_{candidate_id}')
                return {
                    'action': 'terminated_and_blacklisted',
                    'event_type': 'copy_paste_second_strike',
                }

        # ── SCORE-BASED EVENTS ──────────────────────────────────────────
        severity = EVENT_SEVERITY.get(event_type, (1, 0))
        session_delta, blacklist_delta = severity

        new_session_score = session.get('proctoring_score', 0) + session_delta
        new_blacklist_score = session.get('blacklist_score', 0) + blacklist_delta

        event_doc['session_score_delta'] = session_delta
        event_doc['blacklist_score_delta'] = blacklist_delta

        # Determine consequence
        action = 'logged'
        consequence = 'none'
        should_pause = False
        should_terminate = False
        should_blacklist = False

        # ── Event-specific logic ────────────────────────────────────────

        if event_type == 'tab_switch':
            tab_count = _count_event_type(session_id, 'tab_switch') + 1
            if tab_count >= TAB_SWITCH_TERMINATE_COUNT:
                should_terminate = True
                consequence = 'tab_switch_limit_exceeded'
            elif tab_count >= TAB_SWITCH_WARN_COUNT:
                consequence = 'tab_switch_warning'
                action = 'warning'

        elif event_type == 'fullscreen_exit':
            should_pause = True
            consequence = 'fullscreen_grace_period'
            action = 'warning'
            # Client has 10s to restore; if not, client sends another
            # fullscreen_exit which will accumulate score toward termination

        elif event_type == 'copy_paste':
            # First occurrence (2nd handled above)
            should_pause = True
            consequence = 'copy_paste_first_warning'
            action = 'warning'

        elif event_type == 'face_not_detected':
            face_count = _count_event_type(session_id, 'face_not_detected') + 1
            if face_count >= 3:  # ~30s at 2s detection interval
                consequence = 'face_snapshot_required'
                action = 'snapshot'
            else:
                consequence = 'face_detection_warning'
                action = 'warning'

        elif event_type == 'devtools_open':
            consequence = 'devtools_logged'
            action = 'logged'  # severity 2, log only, no termination

        elif event_type == 'right_click':
            consequence = 'right_click_suppressed'
            action = 'logged'

        elif event_type == 'audio_anomaly':
            consequence = 'audio_anomaly_warning'
            action = 'warning'

        # ── Threshold checks ────────────────────────────────────────────

        if new_session_score >= SESSION_TERMINATE_THRESHOLD:
            should_terminate = True
            consequence = 'session_score_threshold_exceeded'

        if new_blacklist_score >= BLACKLIST_THRESHOLD:
            should_blacklist = True
            consequence = 'blacklist_score_threshold_exceeded'

        # ── Apply consequences ──────────────────────────────────────────
        event_doc['consequence'] = consequence

        update_ops: Dict[str, Any] = {
            '$push': {'proctoring_events': event_doc},
            '$set': {
                'proctoring_score': new_session_score,
                'blacklist_score': new_blacklist_score,
            },
        }
        db['smart_sessions'].update_one(
            {'_id': ObjectId(session_id)},
            update_ops,
        )

        if should_pause and not should_terminate:
            _pause_session(session_id)
            self.socketio.emit('warning_issued', {
                'session_id': session_id,
                'event_type': event_type,
                'consequence': consequence,
                'session_score': new_session_score,
                'message': _warning_message(event_type),
            }, room=f'user_{candidate_id}')
            action = 'warning_with_pause'

        if should_terminate:
            _terminate_session(session_id, consequence)
            if should_blacklist:
                _blacklist_candidate(candidate_id, session_id, consequence)
            self.socketio.emit('session_terminated', {
                'session_id': session_id,
                'reason': consequence,
                'blacklisted': should_blacklist,
            }, room=f'user_{candidate_id}')
            action = 'terminated' + ('_and_blacklisted' if should_blacklist else '')

        return {
            'action': action,
            'event_type': event_type,
            'consequence': consequence,
            'session_score': new_session_score,
            'blacklist_score': new_blacklist_score,
        }


def _warning_message(event_type: str) -> str:
    """Human-readable warning message for the blocking modal."""
    messages = {
        'copy_paste': (
            'Copy-paste activity has been detected during your assessment. '
            'This is your first and only warning. A second occurrence will '
            'result in immediate termination and a permanent ban from future '
            'assessments. Click "I Understand" to continue.'
        ),
        'fullscreen_exit': (
            'You have exited full-screen mode. You have 10 seconds to return '
            'to full-screen. If you do not, your assessment will be '
            'automatically terminated. Click "I Understand" to continue.'
        ),
        'tab_switch': (
            'Multiple tab switches have been detected. Further tab switches '
            'will result in automatic termination of your assessment. '
            'Click "I Understand" to continue.'
        ),
        'face_not_detected': (
            'Your face could not be detected by the camera. Please ensure '
            'you are visible and centered in the camera view. '
            'Click "I Understand" to continue.'
        ),
        'audio_anomaly': (
            'Unusual audio activity has been detected in your environment. '
            'Please ensure you are in a quiet, private space. '
            'Click "I Understand" to continue.'
        ),
    }
    return messages.get(event_type, 'A proctoring violation has been detected.')


# ─── Module-level singleton ─────────────────────────────────────────────────

_proctoring_service: Optional[ProctoringService] = None


def get_proctoring_service() -> Optional[ProctoringService]:
    """Get the global ProctoringService instance."""
    global _proctoring_service
    return _proctoring_service


def init_proctoring_service(app) -> ProctoringService:
    """Initialize and return the global ProctoringService."""
    global _proctoring_service
    _proctoring_service = ProctoringService(app)
    return _proctoring_service

