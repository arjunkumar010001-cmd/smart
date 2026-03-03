"""
Digital Onboarding Routes  —  Phase 6
=======================================
Complete onboarding workflow: offer letters, digital acceptance,
document uploads, NDA signing, IT provisioning, orientation.

Endpoints:
  POST   /api/onboarding/<app_id>/send-offer        — Send offer letter to candidate
  POST   /api/onboarding/<app_id>/accept-offer       — Candidate digitally accepts offer
  POST   /api/onboarding/<app_id>/reject-offer       — Candidate rejects offer
  POST   /api/onboarding/<app_id>/upload-documents    — Upload onboarding documents
  GET    /api/onboarding/<app_id>/documents           — List uploaded documents
  POST   /api/onboarding/<app_id>/sign-nda            — Digitally sign NDA
  POST   /api/onboarding/<app_id>/request-it-setup    — Request IT provisioning
  POST   /api/onboarding/<app_id>/schedule-orientation — Schedule orientation
  GET    /api/onboarding/<app_id>/status              — Full onboarding status
  GET    /api/onboarding/pending                      — All pending onboardings (HR)
  POST   /api/onboarding/<app_id>/complete            — Mark onboarding complete (HR)
  POST   /api/onboarding/<app_id>/verify-documents    — HR verifies uploaded documents

Blueprint prefix (registered in app.py): /api/onboarding
"""

import os
import hashlib
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId
from werkzeug.utils import secure_filename

from backend.models.database import get_db
from backend.security.rbac import require_role
from backend.routes.blacklist_routes import enforce_blacklist

logger = logging.getLogger(__name__)

bp = Blueprint("onboarding", __name__)

UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'uploads', 'onboarding'))
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _user_id_and_role():
    identity = get_jwt_identity()
    if identity is None:
        return None, None
    if isinstance(identity, dict):
        return str(identity.get("user_id", "")), identity.get("role")
    claims = get_jwt() or {}
    return str(identity), claims.get("role")


def _get_application(app_id, user_id=None, require_hired=True):
    """Helper: fetch application with optional ownership + status check."""
    db = get_db()
    query = {"_id": ObjectId(app_id)}
    if user_id:
        query["candidate_id"] = user_id
    if require_hired:
        query["status"] = {"$in": ["hired", "onboarding"]}
    app = db["applications"].find_one(query)
    return app


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ───────────────────────────── OFFER MANAGEMENT ──────────────────────────────

@bp.route("/<app_id>/send-offer", methods=["POST"])
@jwt_required()
@require_role(["admin", "company"])
def send_offer(app_id):
    """
    Send an offer letter to a hired candidate.

    Body:
        position: str, salary: str, start_date: str (ISO),
        response_deadline: str (ISO, optional — defaults to +7 days),
        benefits: str (optional), notes: str (optional)
    """
    user_id, role = _user_id_and_role()
    data = request.get_json() or {}

    db = get_db()
    application = db["applications"].find_one({"_id": ObjectId(app_id)})
    if not application:
        return jsonify({"error": "Application not found"}), 404

    # Update application status to 'hired' if not already
    if application.get("status") not in ("hired", "onboarding", "offered"):
        db["applications"].update_one({"_id": ObjectId(app_id)}, {"$set": {"status": "hired"}})

    position = data.get("position", application.get("job_title", "Position"))
    salary = data.get("salary", "As discussed")
    start_date = data.get("start_date", (datetime.utcnow() + timedelta(days=30)).isoformat())
    response_deadline = data.get("response_deadline",
                                  (datetime.utcnow() + timedelta(days=7)).isoformat())

    offer = {
        "position": position,
        "salary": salary,
        "start_date": start_date,
        "response_deadline": response_deadline,
        "benefits": data.get("benefits", ""),
        "notes": data.get("notes", ""),
        "sent_by": user_id,
        "sent_at": datetime.utcnow(),
        "status": "pending",  # pending | accepted | rejected | expired
    }

    db["applications"].update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {
            "offer": offer,
            "status": "offered",
            "onboarding.offer_sent": True,
            "onboarding.offer_sent_at": datetime.utcnow(),
        }}
    )

    # Send offer email
    try:
        candidate = db["users"].find_one({"_id": ObjectId(application["candidate_id"])}) or \
                    db["users"].find_one({"user_id": application["candidate_id"]})
        if candidate and candidate.get("email"):
            from backend.utils.email_service import email_service
            from backend.services.email_templates import render_offer_letter_email
            html = render_offer_letter_email(
                candidate_name=candidate.get("name", "Candidate"),
                position=position,
                company_name=application.get("company_name", "Company"),
                salary=salary,
                start_date=start_date,
                response_deadline=response_deadline,
            )
            email_service.send_email(
                to_email=candidate["email"],
                subject=f"Offer Letter — {position}",
                html_content=html,
            )
            logger.info("Offer letter emailed to %s", candidate["email"])
    except Exception as e:
        logger.warning("Offer email failed (non-blocking): %s", e)

    return jsonify({"success": True, "message": "Offer letter sent.", "offer": offer}), 200


@bp.route("/<app_id>/accept-offer", methods=["POST"])
@jwt_required()
@require_role(["candidate"])
def accept_offer(app_id):
    """Candidate digitally accepts the offer with e-signature."""
    user_id, _ = _user_id_and_role()
    data = request.get_json() or {}

    bl = enforce_blacklist(user_id)
    if bl:
        return bl

    application = _get_application(app_id, user_id=None, require_hired=False)
    if not application:
        return jsonify({"error": "Application not found"}), 404
    if application.get("candidate_id") != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    offer = application.get("offer", {})
    if offer.get("status") != "pending":
        return jsonify({"error": f"Offer is already {offer.get('status', 'unavailable')}"}), 400

    # Digital signature = full name + timestamp hash
    full_name = data.get("full_name", "")
    if not full_name:
        return jsonify({"error": "full_name is required for digital signature"}), 400

    signature_hash = hashlib.sha256(
        f"{user_id}:{full_name}:{datetime.utcnow().isoformat()}".encode()
    ).hexdigest()

    db = get_db()
    db["applications"].update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {
            "offer.status": "accepted",
            "offer.accepted_at": datetime.utcnow(),
            "offer.digital_signature": signature_hash,
            "offer.signee_name": full_name,
            "status": "onboarding",
            "onboarding.offer_accepted": True,
            "onboarding.offer_accepted_at": datetime.utcnow(),
        }}
    )

    logger.info("Offer accepted by %s for application %s", user_id, app_id)
    return jsonify({
        "success": True,
        "message": "Offer accepted. Welcome aboard!",
        "signature": signature_hash,
    }), 200


@bp.route("/<app_id>/reject-offer", methods=["POST"])
@jwt_required()
@require_role(["candidate"])
def reject_offer(app_id):
    """Candidate rejects the offer."""
    user_id, _ = _user_id_and_role()
    data = request.get_json() or {}

    application = _get_application(app_id, user_id=None, require_hired=False)
    if not application or application.get("candidate_id") != user_id:
        return jsonify({"error": "Application not found"}), 404

    db = get_db()
    db["applications"].update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {
            "offer.status": "rejected",
            "offer.rejected_at": datetime.utcnow(),
            "offer.rejection_reason": data.get("reason", ""),
            "status": "offer_rejected",
        }}
    )

    return jsonify({"success": True, "message": "Offer declined."}), 200


# ───────────────────────── DOCUMENT UPLOAD & VERIFY ──────────────────────────

@bp.route("/<app_id>/upload-documents", methods=["POST"])
@jwt_required()
@require_role(["candidate"])
def upload_documents(app_id):
    """
    Upload onboarding documents (ID proof, degree certificates, etc.).
    Accepts multipart/form-data with field 'files' (multiple).
    Optional form field 'doc_type' per file (id_proof, degree, experience_letter, other).
    """
    user_id, _ = _user_id_and_role()
    application = _get_application(app_id, user_id=user_id, require_hired=True)
    if not application:
        return jsonify({"error": "Application not found or not in hired/onboarding status"}), 404

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    uploaded = []

    doc_type = request.form.get("doc_type", "other")

    for f in files:
        if not _allowed_file(f.filename):
            continue
        filename = secure_filename(f"{user_id}_{app_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{f.filename}")
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        f.save(filepath)

        file_hash = hashlib.sha256(open(filepath, "rb").read()).hexdigest()

        doc_record = {
            "filename": filename,
            "original_name": f.filename,
            "doc_type": doc_type,
            "file_hash": file_hash,
            "uploaded_at": datetime.utcnow(),
            "verified": False,
            "verified_by": None,
            "verified_at": None,
        }
        uploaded.append(doc_record)

    if not uploaded:
        return jsonify({"error": "No valid files uploaded (allowed: pdf, png, jpg, doc, docx)"}), 400

    db = get_db()
    db["applications"].update_one(
        {"_id": ObjectId(app_id)},
        {
            "$push": {"onboarding.documents": {"$each": uploaded}},
            "$set": {
                "onboarding.documents_uploaded": True,
                "onboarding.documents_uploaded_at": datetime.utcnow(),
            }
        }
    )

    return jsonify({
        "success": True,
        "message": f"{len(uploaded)} document(s) uploaded.",
        "documents": [d["filename"] for d in uploaded],
    }), 200


@bp.route("/<app_id>/documents", methods=["GET"])
@jwt_required()
def list_documents(app_id):
    """List all uploaded onboarding documents for an application."""
    user_id, role = _user_id_and_role()
    application = _get_application(app_id, require_hired=False)
    if not application:
        return jsonify({"error": "Application not found"}), 404

    # Candidates can only see their own
    if role == "candidate" and application.get("candidate_id") != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    docs = application.get("onboarding", {}).get("documents", [])
    return jsonify({"success": True, "documents": docs}), 200


@bp.route("/<app_id>/verify-documents", methods=["POST"])
@jwt_required()
@require_role(["admin", "company"])
def verify_documents(app_id):
    """
    HR verifies uploaded documents.

    Body:
        document_index: int (index in the documents array)
        verified: bool
        notes: str (optional)
    """
    user_id, _ = _user_id_and_role()
    data = request.get_json() or {}
    doc_index = data.get("document_index")

    if doc_index is None:
        return jsonify({"error": "document_index is required"}), 400

    db = get_db()
    result = db["applications"].update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {
            f"onboarding.documents.{doc_index}.verified": data.get("verified", True),
            f"onboarding.documents.{doc_index}.verified_by": user_id,
            f"onboarding.documents.{doc_index}.verified_at": datetime.utcnow(),
            f"onboarding.documents.{doc_index}.verification_notes": data.get("notes", ""),
        }}
    )

    if result.modified_count == 0:
        return jsonify({"error": "Document not found or could not update"}), 404

    return jsonify({"success": True, "message": "Document verification updated."}), 200


# ─────────────────────────── NDA / AGREEMENT ─────────────────────────────────

@bp.route("/<app_id>/sign-nda", methods=["POST"])
@jwt_required()
@require_role(["candidate"])
def sign_nda(app_id):
    """
    Digitally sign the NDA/agreement.

    Body:
        full_name: str (required — acts as electronic signature)
        agreed_terms: bool (required — must be true)
    """
    user_id, _ = _user_id_and_role()
    data = request.get_json() or {}

    application = _get_application(app_id, user_id=user_id, require_hired=True)
    if not application:
        return jsonify({"error": "Application not found"}), 404

    full_name = data.get("full_name", "")
    agreed = data.get("agreed_terms", False)

    if not full_name or not agreed:
        return jsonify({"error": "full_name and agreed_terms=true are required"}), 400

    signature_hash = hashlib.sha256(
        f"NDA:{user_id}:{full_name}:{datetime.utcnow().isoformat()}".encode()
    ).hexdigest()

    db = get_db()
    db["applications"].update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {
            "onboarding.nda_signed": True,
            "onboarding.nda_signed_at": datetime.utcnow(),
            "onboarding.nda_signature": signature_hash,
            "onboarding.nda_signee_name": full_name,
        }}
    )

    return jsonify({
        "success": True,
        "message": "NDA signed successfully.",
        "signature": signature_hash,
    }), 200


# ──────────────────────── IT PROVISIONING ────────────────────────────────────

@bp.route("/<app_id>/request-it-setup", methods=["POST"])
@jwt_required()
@require_role(["candidate", "admin", "company"])
def request_it_setup(app_id):
    """
    Request IT provisioning (laptop, email, accounts).

    Body (optional):
        laptop_preference: str ('windows' | 'mac' | 'linux')
        special_software: list[str]
        notes: str
    """
    user_id, role = _user_id_and_role()
    data = request.get_json() or {}

    application = _get_application(app_id, require_hired=True)
    if not application:
        return jsonify({"error": "Application not found"}), 404

    if role == "candidate" and application.get("candidate_id") != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    it_request = {
        "requested_by": user_id,
        "requested_at": datetime.utcnow(),
        "laptop_preference": data.get("laptop_preference", "windows"),
        "special_software": data.get("special_software", []),
        "notes": data.get("notes", ""),
        "status": "pending",  # pending | in_progress | completed
    }

    db = get_db()
    db["applications"].update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {
            "onboarding.it_setup_requested": True,
            "onboarding.it_request": it_request,
        }}
    )

    return jsonify({"success": True, "message": "IT setup requested.", "it_request": it_request}), 200


# ──────────────────────── ORIENTATION ────────────────────────────────────────

@bp.route("/<app_id>/schedule-orientation", methods=["POST"])
@jwt_required()
@require_role(["admin", "company"])
def schedule_orientation(app_id):
    """
    Schedule orientation for a new hire.

    Body:
        date: str (ISO datetime)
        duration_minutes: int (default 120)
        location: str (e.g. 'Conference Room A' or 'Zoom link')
        agenda: str (optional)
    """
    user_id, _ = _user_id_and_role()
    data = request.get_json() or {}

    application = _get_application(app_id, require_hired=True)
    if not application:
        return jsonify({"error": "Application not found"}), 404

    orientation = {
        "scheduled_by": user_id,
        "scheduled_at": datetime.utcnow(),
        "date": data.get("date", (datetime.utcnow() + timedelta(days=7)).isoformat()),
        "duration_minutes": data.get("duration_minutes", 120),
        "location": data.get("location", "TBD"),
        "agenda": data.get("agenda", "Company overview, team introductions, policy walkthrough"),
        "status": "scheduled",  # scheduled | completed | cancelled
    }

    db = get_db()
    db["applications"].update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {
            "onboarding.orientation_scheduled": True,
            "onboarding.orientation": orientation,
        }}
    )

    # Notify candidate
    try:
        candidate = db["users"].find_one({"_id": ObjectId(application["candidate_id"])}) or \
                    db["users"].find_one({"user_id": application["candidate_id"]})
        if candidate and candidate.get("email"):
            from backend.utils.email_service import email_service
            email_service.send_email(
                to_email=candidate["email"],
                subject="Orientation Scheduled — Smart Hiring",
                html_content=f"""
                <h2>Your orientation has been scheduled!</h2>
                <p><strong>Date:</strong> {orientation['date']}</p>
                <p><strong>Duration:</strong> {orientation['duration_minutes']} minutes</p>
                <p><strong>Location:</strong> {orientation['location']}</p>
                <p><strong>Agenda:</strong> {orientation['agenda']}</p>
                """,
            )
    except Exception as e:
        logger.warning("Orientation email failed: %s", e)

    return jsonify({"success": True, "message": "Orientation scheduled.", "orientation": orientation}), 200


# ──────────────────────── STATUS & COMPLETION ────────────────────────────────

@bp.route("/<app_id>/status", methods=["GET"])
@jwt_required()
def onboarding_status(app_id):
    """Get full onboarding status for an application."""
    user_id, role = _user_id_and_role()

    application = _get_application(app_id, require_hired=False)
    if not application:
        return jsonify({"error": "Application not found"}), 404

    if role == "candidate" and application.get("candidate_id") != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    ob = application.get("onboarding", {})

    # Calculate completion percentage
    steps = ["offer_accepted", "documents_uploaded", "profile_completed",
             "nda_signed", "it_setup_requested", "orientation_scheduled"]
    completed_steps = sum(1 for s in steps if ob.get(s))
    completion_pct = round((completed_steps / len(steps)) * 100)

    # Document verification status
    docs = ob.get("documents", [])
    docs_verified = all(d.get("verified") for d in docs) if docs else False

    return jsonify({
        "success": True,
        "application_id": app_id,
        "status": application.get("status"),
        "onboarding": ob,
        "completion_percentage": completion_pct,
        "completed_steps": completed_steps,
        "total_steps": len(steps),
        "all_documents_verified": docs_verified,
        "steps_detail": {s: ob.get(s, False) for s in steps},
    }), 200


@bp.route("/pending", methods=["GET"])
@jwt_required()
@require_role(["admin", "company"])
def pending_onboardings():
    """List all applications currently in onboarding phase (HR dashboard view)."""
    user_id, role = _user_id_and_role()
    db = get_db()

    query = {"status": {"$in": ["hired", "onboarding", "offered"]}}

    # Company users only see their own jobs' applications
    if role == "company":
        job_ids = [str(j["_id"]) for j in db["jobs"].find({"recruiter_id": user_id}, {"_id": 1})]
        query["job_id"] = {"$in": job_ids}

    applications = list(db["applications"].find(query).sort("updated_at", -1).limit(100))

    results = []
    for app in applications:
        app["_id"] = str(app["_id"])
        ob = app.get("onboarding", {})
        steps = ["offer_accepted", "documents_uploaded", "profile_completed",
                 "nda_signed", "it_setup_requested", "orientation_scheduled"]
        completed = sum(1 for s in steps if ob.get(s))

        # Resolve candidate name
        c = db["users"].find_one({"_id": ObjectId(app["candidate_id"])}) if ObjectId.is_valid(app.get("candidate_id", "")) else None
        app["candidate_name"] = c.get("name", "Unknown") if c else "Unknown"
        app["candidate_email"] = c.get("email", "") if c else ""
        app["completion_percentage"] = round((completed / len(steps)) * 100)
        results.append(app)

    return jsonify({"success": True, "data": results, "total": len(results)}), 200


@bp.route("/<app_id>/complete", methods=["POST"])
@jwt_required()
@require_role(["admin", "company"])
def complete_onboarding(app_id):
    """Mark onboarding as fully complete — candidate becomes an active employee."""
    user_id, _ = _user_id_and_role()

    application = _get_application(app_id, require_hired=True)
    if not application:
        return jsonify({"error": "Application not found"}), 404

    db = get_db()
    db["applications"].update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {
            "status": "onboarded",
            "onboarding.completed": True,
            "onboarding.completed_at": datetime.utcnow(),
            "onboarding.completed_by": user_id,
        }}
    )

    return jsonify({"success": True, "message": "Onboarding complete. Candidate is now an active employee."}), 200
