"""
Session Completion Emails — Unified email handler for assessment sessions.

Called from all three termination paths:
  1. finish_session() — normal completion
  2. _terminate_session() — proctoring termination
  3. auto_complete_stale_interviews() — stale session cleanup

Never duplicate email logic — this is the SINGLE source of truth.
"""

import logging
from datetime import datetime
from bson import ObjectId
from backend.models.database import get_db

logger = logging.getLogger(__name__)


def send_session_completion_emails(session_id: str, session_doc: dict = None) -> None:
    """
    Send completion emails to candidate + recruiter for a finished session.

    Args:
        session_id: The smart_sessions document ID.
        session_doc: Optional pre-fetched session document.
                     If None, fetched from DB.
    """
    try:
        db = get_db()

        # Fetch session if not provided
        if session_doc is None:
            session_doc = db["smart_sessions"].find_one({"_id": ObjectId(session_id)})
        if not session_doc:
            logger.warning("send_session_completion_emails: session %s not found", session_id)
            return

        # Dedup guard: skip if emails already sent for this session
        if session_doc.get("emails_sent"):
            logger.info("send_session_completion_emails: emails already sent for %s", session_id)
            return

        # Get candidate info
        candidate_id = session_doc.get("candidate_id")
        candidate = db["users"].find_one({"_id": ObjectId(candidate_id)}) if candidate_id else None
        if not candidate:
            logger.warning("send_session_completion_emails: candidate %s not found", candidate_id)
            return

        candidate_email = candidate.get("email", "")
        candidate_name = candidate.get("full_name") or candidate.get("name", "Candidate")

        # Get assessment config → job → recruiter
        config_id = session_doc.get("assessment_id")
        config = db["assessment_configs"].find_one({"_id": config_id}) if config_id else None
        job_title = "Assessment"
        recruiter_email = None
        recruiter_name = None

        if config:
            job_title = config.get("title", job_title)
            job_id = config.get("job_id")
            if job_id:
                job = db["jobs"].find_one({"_id": ObjectId(job_id)})
                if job:
                    job_title = job.get("title", job_title)
                    recruiter_id = job.get("recruiter_id")
                    if recruiter_id:
                        recruiter = db["users"].find_one({"_id": ObjectId(recruiter_id)})
                        if recruiter:
                            recruiter_email = recruiter.get("email")
                            recruiter_name = recruiter.get("full_name") or recruiter.get("name", "Recruiter")

        # Extract results
        results = session_doc.get("results", {})
        overall_score = results.get("overall_score", 0)
        status = session_doc.get("status", "completed")
        is_terminated = status == "terminated"
        termination_reason = session_doc.get("termination_reason", "")

        # Proctoring summary
        proctoring_events = session_doc.get("proctoring_events", [])
        proctoring_score = session_doc.get("proctoring_score", 100)
        event_count = len(proctoring_events)
        proctoring_status = "Clean" if event_count == 0 else f"{event_count} event(s) flagged"

        # ── Send candidate email ──────────────────────────────────────
        _send_candidate_email(
            candidate_email, candidate_name, job_title,
            overall_score, is_terminated, termination_reason,
        )

        # ── Send recruiter email ──────────────────────────────────────
        if recruiter_email:
            _send_recruiter_email(
                recruiter_email, recruiter_name, candidate_name,
                job_title, overall_score, is_terminated,
                proctoring_status, proctoring_score, session_id,
            )

        # Mark emails as sent (atomic, prevents double-send on race)
        db["smart_sessions"].update_one(
            {"_id": ObjectId(session_id), "emails_sent": {"$ne": True}},
            {"$set": {"emails_sent": True, "emails_sent_at": datetime.utcnow()}},
        )

    except Exception as e:
        # Email failures must NEVER break the caller
        logger.error("send_session_completion_emails failed: %s", e, exc_info=True)


def _send_candidate_email(to_email, name, job_title, score, is_terminated, reason):
    """Send assessment completion email to candidate."""
    try:
        from backend.services.email_service import EmailNotificationSystem
        email_svc = EmailNotificationSystem()

        if is_terminated:
            subject = f"Assessment Session Ended — {job_title}"
            status_badge = '<span style="background:#fee2e2;color:#991b1b;padding:4px 12px;border-radius:8px;font-weight:600;">Session Terminated</span>'
            message = f"Your assessment session was terminated. Reason: {reason or 'Policy violation detected'}"
        else:
            subject = f"Assessment Completed — {job_title}"
            status_badge = '<span style="background:#dcfce7;color:#166534;padding:4px 12px;border-radius:8px;font-weight:600;">Completed</span>'
            message = "Your assessment has been submitted successfully. Your results have been shared with the recruiter."

        html = f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f8fafc;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 32px; text-align: center; border-radius: 12px 12px 0 0;">
                <h1 style="margin: 0; font-size: 22px;">📋 Assessment Update</h1>
            </div>
            <div style="padding: 32px; background: white; border-radius: 0 0 12px 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                <p>Hi {name},</p>
                <p>{message}</p>

                <div style="background: #f1f5f9; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: center;">
                    <div style="font-size: 14px; color: #64748b; margin-bottom: 8px;">Assessment</div>
                    <div style="font-size: 18px; font-weight: 600; color: #1e293b; margin-bottom: 12px;">{job_title}</div>
                    <div style="font-size: 36px; font-weight: 700; color: {'#10b981' if score >= 70 else '#f59e0b' if score >= 40 else '#ef4444'};">{score}%</div>
                    <div style="margin-top: 8px;">{status_badge}</div>
                </div>

                <p style="color: #64748b; font-size: 13px;">If you have any questions about your results, please contact the recruiter directly.</p>
                <p>Best regards,<br>Smart Hiring Team</p>
            </div>
        </body>
        </html>
        """

        email_svc.send_email(to_email, subject, html)
        logger.info("Candidate completion email sent to %s", to_email)

    except Exception as e:
        logger.error("Candidate email failed: %s", e)


def _send_recruiter_email(to_email, recruiter_name, candidate_name, job_title,
                          score, is_terminated, proctoring_status, proctoring_score,
                          session_id):
    """Send assessment results email to recruiter."""
    try:
        from backend.services.email_service import EmailNotificationSystem
        email_svc = EmailNotificationSystem()

        subject = f"Assessment Results — {candidate_name} for {job_title}"

        proctoring_color = "#10b981" if proctoring_score >= 80 else "#f59e0b" if proctoring_score >= 50 else "#ef4444"
        status_text = "🚫 Terminated" if is_terminated else "✅ Completed"

        html = f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f8fafc;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 32px; text-align: center; border-radius: 12px 12px 0 0;">
                <h1 style="margin: 0; font-size: 22px;">📊 Assessment Results</h1>
            </div>
            <div style="padding: 32px; background: white; border-radius: 0 0 12px 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                <p>Hi {recruiter_name},</p>
                <p>An assessment has been completed for the <strong>{job_title}</strong> position.</p>

                <div style="display: flex; gap: 12px; margin: 20px 0;">
                    <div style="flex: 1; background: #f0f9ff; padding: 16px; border-radius: 10px; text-align: center; border-left: 3px solid #3b82f6;">
                        <div style="font-size: 12px; color: #64748b;">Candidate</div>
                        <div style="font-size: 16px; font-weight: 600; color: #1e293b;">{candidate_name}</div>
                    </div>
                    <div style="flex: 1; background: #f0fdf4; padding: 16px; border-radius: 10px; text-align: center; border-left: 3px solid #10b981;">
                        <div style="font-size: 12px; color: #64748b;">Score</div>
                        <div style="font-size: 24px; font-weight: 700; color: {'#10b981' if score >= 70 else '#f59e0b' if score >= 40 else '#ef4444'};">{score}%</div>
                    </div>
                </div>

                <div style="background: #f8fafc; padding: 16px; border-radius: 10px; margin: 16px 0; border: 1px solid #e2e8f0;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <span style="color: #64748b;">Status</span>
                        <span style="font-weight: 600;">{status_text}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <span style="color: #64748b;">Proctoring</span>
                        <span style="color: {proctoring_color}; font-weight: 600;">{proctoring_status} (Score: {proctoring_score})</span>
                    </div>
                </div>

                <div style="text-align: center; margin: 24px 0;">
                    <a href="/company-portal.html" style="
                        display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white; padding: 12px 32px; border-radius: 8px; text-decoration: none;
                        font-weight: 600; font-size: 14px;">
                        📄 View Full Audit Report
                    </a>
                </div>

                <p style="color: #64748b; font-size: 13px;">You can download the full PDF audit report from your company portal.</p>
                <p>Best regards,<br>Smart Hiring Team</p>
            </div>
        </body>
        </html>
        """

        email_svc.send_email(to_email, subject, html)
        logger.info("Recruiter completion email sent to %s", to_email)

    except Exception as e:
        logger.error("Recruiter email failed: %s", e)
