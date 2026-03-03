"""
Phase 2 - Proctoring Consequence Engine: Behavioral Verification Tests
======================================================================
Tests the actual consequence engine logic directly (no SocketIO transport).
Uses a real MongoDB connection via the project's Database singleton.

Tests:
  1. Dual-score DB writes (score accumulation)
  2. Immediate blacklist on multiple_faces (no score accumulation)
  3. Copy-paste 2nd strike = immediate blacklist
  4. Session termination at score >= 15
  5. check_blacklist() returns True after blacklisting
  6. Timer pause on fullscreen_exit warning
"""

import os
import sys

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from datetime import datetime
from bson import ObjectId

# Bootstrap Flask + SocketIO (required by ProctoringService)
from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-verification-key'
app.config['TESTING'] = True

socketio = SocketIO(app, async_mode='eventlet', logger=False, engineio_logger=False)
app.socketio = socketio

# Import get_db from the project's database module (auto-connects via config)
from backend.models.database import get_db

# Import proctoring service
from backend.services.proctoring_service import (
    ProctoringService, check_blacklist,
    EVENT_SEVERITY, IMMEDIATE_BLACKLIST_EVENTS,
    SESSION_TERMINATE_THRESHOLD,
)

svc = ProctoringService()
svc.init_app(app)

# --- Helpers ---
passed = 0
failed = 0
total = 0

TEST_DB_COLLECTION_PREFIX = 'proctoring_test_'


def test(name, condition, detail=""):
    global passed, failed, total
    total += 1
    if condition:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name} -- {detail}")


def create_test_session(candidate_id="test_candidate_123"):
    """Create a fresh in-progress session for testing."""
    db = get_db()
    session_doc = {
        'config_id': 'test_proctoring_config',
        'candidate_id': candidate_id,
        'status': 'in_progress',
        'created_at': datetime.utcnow(),
        'proctoring_events': [],
        'proctoring_score': 0,
        'blacklist_score': 0,
        'questions': [],
        'answers': {},
        'title': 'Test Assessment - Proctoring Verification',
    }
    result = db['smart_sessions'].insert_one(session_doc)
    return str(result.inserted_id)


def cleanup():
    """Remove all test data."""
    db = get_db()
    db['smart_sessions'].delete_many({'config_id': 'test_proctoring_config'})
    db['blacklist'].delete_many({'candidate_id': {'$regex': '^test_candidate_proct'}})


# === Run tests ===

with app.app_context():
    cleanup()
    db = get_db()

    # ===========================================================
    print("\n=== TEST 1: Dual-Score DB Writes ===")

    sid1 = create_test_session("test_candidate_proct_score")

    # tab_switch: session_delta=3, blacklist_delta=3
    result1 = svc._process_event('tab_switch', sid1, datetime.utcnow().isoformat(), {})
    session = db['smart_sessions'].find_one({'_id': ObjectId(sid1)})

    test("tab_switch returns action",
         result1.get('action') is not None,
         f"got: {result1}")
    test("session_score = 3 after tab_switch",
         session['proctoring_score'] == 3,
         f"got: {session['proctoring_score']}")
    test("blacklist_score = 3 after tab_switch",
         session['blacklist_score'] == 3,
         f"got: {session['blacklist_score']}")
    test("proctoring_events has 1 entry",
         len(session.get('proctoring_events', [])) == 1,
         f"got: {len(session.get('proctoring_events', []))}")

    # right_click: session_delta=1, blacklist_delta=0
    result2 = svc._process_event('right_click', sid1, datetime.utcnow().isoformat(), {})
    session = db['smart_sessions'].find_one({'_id': ObjectId(sid1)})

    test("session_score = 4 after right_click",
         session['proctoring_score'] == 4,
         f"got: {session['proctoring_score']}")
    test("blacklist_score stays 3 (right_click has 0 blacklist delta)",
         session['blacklist_score'] == 3,
         f"got: {session['blacklist_score']}")

    # ===========================================================
    print("\n=== TEST 2: Immediate Blacklist on multiple_faces ===")

    sid2 = create_test_session("test_candidate_proct_multiface")

    result3 = svc._process_event('multiple_faces', sid2, datetime.utcnow().isoformat(), {
        'faceCount': 2
    })
    session2 = db['smart_sessions'].find_one({'_id': ObjectId(sid2)})

    test("action = terminated_and_blacklisted",
         result3.get('action') == 'terminated_and_blacklisted',
         f"got: {result3.get('action')}")
    test("session status = terminated",
         session2.get('status') == 'terminated',
         f"got: {session2.get('status')}")
    test("proctoring_score unchanged (0) - bypass scoring",
         session2.get('proctoring_score', 0) == 0,
         f"got: {session2.get('proctoring_score')}")

    blacklist_rec = db['blacklist'].find_one({'candidate_id': 'test_candidate_proct_multiface'})
    test("blacklist record created",
         blacklist_rec is not None,
         "no blacklist record found")
    test("blacklist reason = multiple_faces",
         blacklist_rec and blacklist_rec.get('reason') == 'multiple_faces',
         f"got: {blacklist_rec.get('reason') if blacklist_rec else 'N/A'}")

    # ===========================================================
    print("\n=== TEST 3: Copy-Paste 2nd Strike = Immediate Blacklist ===")

    sid3 = create_test_session("test_candidate_proct_copypaste")

    # 1st copy_paste - should warn, not blacklist
    r_cp1 = svc._process_event('copy_paste', sid3, datetime.utcnow().isoformat(), {'action': 'paste'})
    test("1st copy_paste: action = warning_with_pause",
         r_cp1.get('action') == 'warning_with_pause',
         f"got: {r_cp1.get('action')}")

    s3 = db['smart_sessions'].find_one({'_id': ObjectId(sid3)})
    test("1st copy_paste: session still active (paused)",
         s3.get('status') in ('paused', 'in_progress'),
         f"got: {s3.get('status')}")

    # Resume session to allow 2nd event
    db['smart_sessions'].update_one(
        {'_id': ObjectId(sid3)}, {'$set': {'status': 'in_progress'}}
    )

    # 2nd copy_paste - should immediately blacklist
    r_cp2 = svc._process_event('copy_paste', sid3, datetime.utcnow().isoformat(), {'action': 'copy'})
    test("2nd copy_paste: action = terminated_and_blacklisted",
         r_cp2.get('action') == 'terminated_and_blacklisted',
         f"got: {r_cp2.get('action')}")

    bl_cp = db['blacklist'].find_one({'candidate_id': 'test_candidate_proct_copypaste'})
    test("2nd copy_paste: blacklist record created",
         bl_cp is not None,
         "no blacklist record found")

    # ===========================================================
    print("\n=== TEST 4: Session Termination at Score >= 15 ===")

    sid4 = create_test_session("test_candidate_proct_threshold")

    # Accumulate score: right_click (+1) x 5 = 5, devtools (+2) x 5 = 10, total = 15
    for i in range(5):
        svc._process_event('right_click', sid4, datetime.utcnow().isoformat(), {})

    for i in range(5):
        svc._process_event('devtools_open', sid4, datetime.utcnow().isoformat(), {})

    s4 = db['smart_sessions'].find_one({'_id': ObjectId(sid4)})
    test(f"session_score = {s4.get('proctoring_score')} (>= 15)",
         s4.get('proctoring_score', 0) >= SESSION_TERMINATE_THRESHOLD,
         f"got: {s4.get('proctoring_score')}")
    test("session status = terminated",
         s4.get('status') == 'terminated',
         f"got: {s4.get('status')}")
    test("termination_reason = session_score_threshold_exceeded",
         s4.get('termination_reason') == 'session_score_threshold_exceeded',
         f"got: {s4.get('termination_reason')}")

    # ===========================================================
    print("\n=== TEST 5: check_blacklist() Returns True After Blacklist ===")

    test("check_blacklist test_candidate_proct_multiface = True",
         check_blacklist('test_candidate_proct_multiface') is True,
         f"got: {check_blacklist('test_candidate_proct_multiface')}")
    test("check_blacklist test_candidate_proct_copypaste = True",
         check_blacklist('test_candidate_proct_copypaste') is True,
         f"got: {check_blacklist('test_candidate_proct_copypaste')}")
    test("check_blacklist nonexistent_user = False",
         check_blacklist('nonexistent_user_xyz') is False,
         f"got: {check_blacklist('nonexistent_user_xyz')}")

    # ===========================================================
    print("\n=== TEST 6: Timer Pause on fullscreen_exit Warning ===")

    sid6 = create_test_session("test_candidate_proct_pause")

    r_fs = svc._process_event('fullscreen_exit', sid6, datetime.utcnow().isoformat(), {})
    test("fullscreen_exit action = warning_with_pause",
         r_fs.get('action') == 'warning_with_pause',
         f"got: {r_fs.get('action')}")

    s6 = db['smart_sessions'].find_one({'_id': ObjectId(sid6)})
    test("session status = paused",
         s6.get('status') == 'paused',
         f"got: {s6.get('status')}")
    test("paused_at timestamp exists",
         s6.get('paused_at') is not None,
         "paused_at not set")

    # ===========================================================
    # Cleanup
    cleanup()

    # Summary
    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    else:
        print("  ALL BEHAVIORAL TESTS PASSED")
        sys.exit(0)
