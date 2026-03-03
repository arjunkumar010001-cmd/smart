"""
PDF Audit Report Generator — WeasyPrint + Jinja2.

Generates a comprehensive PDF audit report for a smart assessment session,
including scoring, proctoring events, evidence snapshots (thumbnailed), and
assessment configuration.

If WeasyPrint is unavailable, falls back to a minimal plain-text error.
"""

import os
import io
import base64
import hashlib
import logging
from datetime import datetime

from bson import ObjectId
from jinja2 import Environment, FileSystemLoader

from backend.models.database import get_db

logger = logging.getLogger(__name__)

# Template directory
_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
_UPLOADS_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads')
)
SNAPSHOTS_DIR = os.path.join(_UPLOADS_ROOT, 'snapshots')


def generate_audit_report(session_id: str, include_pii: bool = False) -> bytes:
    """
    Generate a PDF audit report for the given session.

    Args:
        session_id: The smart_sessions document ID.
        include_pii: If True, include candidate name/email.
                     If False, anonymize with SHA-256 hash.

    Returns:
        PDF file as bytes.

    Raises:
        ValueError: If session not found.
        ImportError: If WeasyPrint is not available.
    """
    db = get_db()

    # ── Fetch session ─────────────────────────────────────────────
    session_doc = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
    if not session_doc:
        raise ValueError(f"Session {session_id} not found")

    # ── Fetch candidate ───────────────────────────────────────────
    candidate_id = session_doc.get("candidate_id", "")
    candidate = db["users"].find_one({"_id": ObjectId(candidate_id)}) if candidate_id else None

    if include_pii and candidate:
        candidate_display = f"{candidate.get('full_name', candidate.get('name', 'Unknown'))} ({candidate.get('email', '')})"
    else:
        # Anonymize: SHA-256 of candidate ID, first 12 chars
        anon_hash = hashlib.sha256(str(candidate_id).encode()).hexdigest()[:12]
        candidate_display = f"Candidate #{anon_hash}"

    # ── Fetch assessment config ───────────────────────────────────
    config_id = session_doc.get("config_id") or session_doc.get("assessment_id")
    config_doc = db["assessment_configs"].find_one({"_id": ObjectId(config_id)}) if config_id else None

    # ── Fetch recording availability ──────────────────────────────
    rec_count = db["recording_chunks"].count_documents({"session_id": session_id})

    # ── Build template context ────────────────────────────────────
    started = session_doc.get("started_at", "")
    completed = session_doc.get("completed_at", session_doc.get("terminated_at", ""))

    session_ctx = {
        "session_id": session_id,
        "status": session_doc.get("status", "unknown"),
        "started_at_fmt": _fmt_dt(started),
        "ended_at_fmt": _fmt_dt(completed),
        "termination_reason": session_doc.get("termination_reason", ""),
    }

    # Scoring
    score_ctx = {
        "percentage": session_doc.get("percentage", session_doc.get("final_percentage", 0)),
        "total": session_doc.get("total_score", 0),
        "max": session_doc.get("max_score", 0),
        "verdict": session_doc.get("verdict", ""),
        "penalty_applied": session_doc.get("penalty_applied", 0),
        "type_breakdown": _build_type_breakdown(session_doc.get("type_breakdown")),
    }

    # Proctoring
    events_raw = session_doc.get("proctoring_events", [])
    events_ctx = []
    for evt in events_raw:
        events_ctx.append({
            "timestamp": _fmt_dt(evt.get("timestamp", "")),
            "event_type": evt.get("event_type", ""),
            "consequence": evt.get("consequence", ""),
            "score_delta": evt.get("score_delta", 0),
            "metadata_summary": _summarize_metadata(evt.get("metadata", {})),
        })

    proctoring_ctx = {
        "score": session_doc.get("proctoring_score", 100),
        "blacklist_score": session_doc.get("blacklist_score", 0),
        "event_count": len(events_raw),
        "events": events_ctx,
    }

    # Config
    config_ctx = {
        "title": "",
        "duration_minutes": 0,
        "question_count": 0,
        "passing_score": 70,
        "neg_marking": False,
        "neg_penalty": 0,
        "question_types": "",
    }
    if config_doc:
        config_ctx.update({
            "title": config_doc.get("title", "Smart Assessment"),
            "duration_minutes": config_doc.get("duration_minutes", 0),
            "question_count": config_doc.get("total_questions", 0),
            "passing_score": config_doc.get("passing_score", 70),
            "neg_marking": config_doc.get("negative_marking", False),
            "neg_penalty": config_doc.get("negative_marking_penalty", 0.5),
            "question_types": ", ".join(config_doc.get("question_types", [])),
        })

    # Snapshots — thumbnail to 200×150, base64 encode in memory
    snapshots_ctx = _build_snapshot_thumbnails(session_id, session_doc)

    # ── Render HTML ───────────────────────────────────────────────
    env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)
    template = env.get_template("audit_report.html")

    html_content = template.render(
        session=session_ctx,
        score=score_ctx,
        proctoring=proctoring_ctx,
        config=config_ctx,
        candidate_display=candidate_display,
        snapshots=snapshots_ctx,
        has_recording=rec_count > 0,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )

    # ── Convert to PDF via WeasyPrint ─────────────────────────────
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content).write_pdf()
        logger.info("Audit report PDF generated for session %s (%d bytes)", session_id, len(pdf_bytes))
        return pdf_bytes
    except ImportError:
        logger.error("WeasyPrint not installed — cannot generate PDF")
        raise ImportError(
            "WeasyPrint is not installed. Install with: pip install weasyprint. "
            "System deps required: libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0"
        )


def _fmt_dt(val) -> str:
    """Format a datetime value for display."""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M:%S UTC")
    if isinstance(val, str) and val:
        return val[:19]
    return "—"


def _build_type_breakdown(breakdown):
    """Normalize type_breakdown into a list of dicts."""
    if not breakdown:
        return []
    if isinstance(breakdown, dict):
        result = []
        for qtype, data in breakdown.items():
            if isinstance(data, dict):
                result.append({
                    "type": qtype,
                    "correct": data.get("correct", 0),
                    "total": data.get("total", 0),
                    "score": round(data.get("correct", 0) / max(data.get("total", 1), 1) * 100),
                })
        return result
    return breakdown


def _summarize_metadata(meta: dict) -> str:
    """Create a short text summary of event metadata."""
    if not meta:
        return ""
    parts = []
    if "faceCount" in meta:
        parts.append(f"Faces: {meta['faceCount']}")
    if "action" in meta:
        parts.append(meta["action"])
    if "duration" in meta:
        parts.append(f"{meta['duration']}s")
    return ", ".join(parts) if parts else str(meta)[:60]


def _build_snapshot_thumbnails(session_id: str, session_doc: dict) -> list:
    """
    Build base64-encoded thumbnail images for the report.

    Uses Pillow to resize to max 200×150px IN MEMORY — never saves to disk.
    """
    thumbnails = []

    # Method 1: Use snapshots[] array from session doc (Step 1 fix)
    snapshots_list = session_doc.get("snapshots", [])
    session_dir = os.path.join(SNAPSHOTS_DIR, session_id)

    if snapshots_list:
        for snap in snapshots_list[:20]:  # Cap at 20 thumbnails
            filepath = os.path.join(session_dir, snap.get("filename", ""))
            thumb = _make_thumbnail(filepath)
            if thumb:
                thumbnails.append({
                    "b64": thumb,
                    "reason": snap.get("reason", ""),
                    "timestamp": snap.get("timestamp", "")[:19],
                })
    elif os.path.isdir(session_dir):
        # Fallback: list files on disk for old sessions without snapshots[]
        files = sorted(f for f in os.listdir(session_dir) if f.endswith('.jpg'))
        for fname in files[:20]:
            filepath = os.path.join(session_dir, fname)
            thumb = _make_thumbnail(filepath)
            if thumb:
                # Parse reason from filename: reason_timestamp.jpg
                reason = fname.split("_")[0] if "_" in fname else "snapshot"
                thumbnails.append({
                    "b64": thumb,
                    "reason": reason,
                    "timestamp": "",
                })

    return thumbnails


def _make_thumbnail(filepath: str) -> str | None:
    """
    Create a base64-encoded JPEG thumbnail (max 200×150px) in memory.
    Returns None if file doesn't exist or Pillow fails.
    """
    if not os.path.isfile(filepath):
        return None

    try:
        from PIL import Image

        img = Image.open(filepath)
        img.verify()  # Check for corrupt file before processing
        img = Image.open(filepath)  # Re-open after verify
        img.thumbnail((200, 150))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("ascii")

    except Exception as e:
        logger.warning("Thumbnail generation failed for %s: %s", filepath, e)
        return None
