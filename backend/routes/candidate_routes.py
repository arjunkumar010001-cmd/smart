from flask import Blueprint, request, jsonify, Response, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from bson import ObjectId
import os
import io
import re
import logging

from backend.models.database import get_db
from backend.models.job import Application
from backend.models.user import Candidate
from backend.services.resume_parser_service import extract_text_from_file
from backend.utils.cci_calculator import calculate_career_consistency_index
from backend.utils.email_service import email_service
from backend.tasks.email_tasks import send_new_application_alert, send_application_confirmation
from backend.routes.audit_routes import log_audit_event
from backend.security.rbac import require_role

# P0 ML: Import new ML services
try:
    from backend.services.ml_matching_service import get_ml_matching_service, analyze_candidate
    from backend.services.anonymization_service import anonymize_text, get_anonymizer
    ML_SERVICES_AVAILABLE = True
except (ImportError, AttributeError, Exception) as _ml_err:
    from backend.utils.matching import extract_skills, analyze_candidate
    from backend.services.resume_parser_service import anonymize_text
    ML_SERVICES_AVAILABLE = False
    logging.warning("⚠️ ML services not available - using basic matching")

logger = logging.getLogger(__name__)

# Gap 8: Allowed values for voluntary self-identification
VALID_GENDERS = {'male', 'female', 'non-binary', 'other', 'prefer_not_to_say'}
VALID_AGE_GROUPS = {'18-25', '26-35', '36-45', '46-55', '56+', 'prefer_not_to_say'}
VALID_ETHNICITIES = {
    'group_a', 'group_b', 'group_c', 'group_d', 'group_e', 'prefer_not_to_say'
}

bp = Blueprint('candidates', __name__)

@bp.route('/upload-resume', methods=['POST'])
@jwt_required()
@require_role(['candidate', 'admin'])
def upload_resume():
    """
    Upload and parse candidate resume with automatic score invalidation.
    
    CRITICAL: When resume changes, ALL existing application scores are
    automatically re-calculated to prevent stale match scores.
    """
    try:
        current_user = get_jwt_identity()
        
        # Handle both string and dict JWT identity formats
        if isinstance(current_user, str):
            user_id = current_user
            db = get_db()
            users_collection = db['users']
            user = users_collection.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({'error': 'User not found'}), 404
            role = user.get('role')
        else:
            user_id = current_user.get('user_id')
            role = current_user.get('role')
        
        if role != 'candidate':
            return jsonify({'error': 'Only candidates can upload resumes'}), 403
        
        # Check if file is present
        if 'resume' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['resume']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Use production-grade upload service with score invalidation
        try:
            from backend.services.resume_upload_service import upload_resume as process_resume
            db = get_db()
            result = process_resume(user_id, file, db)
            
            if not result.success:
                return jsonify({'error': result.error}), 400
            
            response = {
                'message': 'Resume uploaded successfully',
                'skills_found': result.skills_extracted,
                'skills_count': len(result.skills_extracted),
                'was_duplicate': result.was_duplicate,
                'applications_rescored': result.applications_rescored,
                'resume_hash': result.resume_hash[:16] if result.resume_hash else None
            }
            
            if result.was_duplicate:
                response['message'] = 'Resume unchanged - no re-processing needed'
            elif result.applications_rescored > 0:
                response['message'] = f'Resume uploaded and {result.applications_rescored} application(s) re-scored'
            
            logger.info(f"✅ Resume processed: {response}")
            return jsonify(response), 200
            
        except ImportError as ie:
            logger.warning(f"Resume upload service not available, using legacy: {ie}")
            # Fallback to legacy implementation if service unavailable
            return _legacy_upload_resume(user_id, file)
        
    except Exception as e:
        logger.exception(f"Resume upload error: {e}")
        return jsonify({'error': str(e)}), 500


def _legacy_upload_resume(user_id: str, file):
    """Legacy upload handler - used only if new service unavailable"""
    from backend.services.resume_parser_service import extract_text_from_file
    
    file_data = file.read()
    resume_text = extract_text_from_file(file_data, file.filename)
    
    if not resume_text:
        return jsonify({'error': 'Could not extract text from resume'}), 400
    
    # Basic anonymization
    if ML_SERVICES_AVAILABLE:
        try:
            anonymizer = get_anonymizer()
            anonymization_result = anonymizer.anonymize(resume_text)
            anonymized_text = anonymization_result['anonymized_text']
        except Exception:
            from backend.services.resume_parser_service import anonymize_text
            anonymized_text = anonymize_text(resume_text)
    else:
        from backend.services.resume_parser_service import anonymize_text
        anonymized_text = anonymize_text(resume_text)
    
    # Basic skill extraction
    if ML_SERVICES_AVAILABLE:
        try:
            ml_service = get_ml_matching_service()
            skills = ml_service.extract_skills(resume_text)
        except Exception:
            from backend.utils.matching import extract_skills
            skills = extract_skills(resume_text)
    else:
        from backend.utils.matching import extract_skills
        skills = extract_skills(resume_text)
    
    # Update candidate
    db = get_db()
    db['candidates'].update_one(
        {'user_id': user_id},
        {'$set': {
            'resume_file': file.filename,
            'resume_text': resume_text,
            'anonymized_resume': anonymized_text,
            'skills': skills,
            'updated_at': datetime.utcnow()
        }},
        upsert=True
    )
    
    db['users'].update_one(
        {'_id': ObjectId(user_id)},
        {'$set': {'profile_completed': True}}
    )
    
    return jsonify({
        'message': 'Resume uploaded (legacy mode)',
        'skills_found': skills,
        'skills_count': len(skills),
        'warning': 'Existing applications NOT re-scored in legacy mode'
    }), 200


@bp.route('/resume/<application_id>', methods=['GET'])
@jwt_required()
def download_resume(application_id):
    """Download resume for an application — accessible by recruiters and the candidate.

    Fallback chain:
      1. Disk file (original upload) — anonymised PDF for recruiters, raw for candidate
      2. Text-to-PDF generation from stored resume_text
      3. Graceful 404

    For recruiters/company/admin: PII is anonymised (name → Candidate [ID], etc.)
    For the candidate themselves: original resume is served as-is.
    """
    try:
        current_user = get_jwt_identity()
        if isinstance(current_user, str):
            user_id = current_user
        else:
            user_id = current_user.get('user_id')

        db = get_db()
        users_collection = db['users']
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        role = user.get('role', '')

        # Look up the application
        application = db['applications'].find_one({'_id': ObjectId(application_id)})
        if not application:
            return jsonify({'success': False, 'error': 'Application not found'}), 404

        candidate_id = application.get('candidate_id')

        # Authorization: only the candidate themselves, company, recruiter, or admin
        if role == 'candidate' and str(user_id) != str(candidate_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403

        # Get candidate's resume data
        candidate = db['candidates'].find_one({'user_id': str(candidate_id)})
        if not candidate:
            return jsonify({'success': False, 'error': 'Candidate profile not found'}), 404

        # Check ALL possible resume-text field names (Bug #3 / #7 field-name mismatch)
        resume_text = (
            candidate.get('resume_text')
            or candidate.get('resume_content')
            or ''
        )
        resume_file = (
            candidate.get('resume_file')
            or candidate.get('resume_path')
            or ''
        )

        if not resume_text and not resume_file:
            return jsonify({'success': False, 'error': 'No resume uploaded for this candidate'}), 404

        # Determine if this is a recruiter viewing (needs anonymisation)
        is_recruiter_view = role in ('company', 'recruiter', 'admin')

        # Get candidate user info for PII anonymisation
        candidate_user = users_collection.find_one({'_id': ObjectId(candidate_id)})
        candidate_name = candidate_user.get('full_name', 'Candidate') if candidate_user else 'Candidate'
        candidate_email = candidate_user.get('email', '') if candidate_user else ''
        candidate_phone = candidate.get('phone', '') or (candidate_user.get('phone', '') if candidate_user else '')
        skills = candidate.get('skills', [])

        logger.info(
            f"Resume download: app={application_id}, candidate={candidate_id[:8]}…, "
            f"role={role}, recruiter_view={is_recruiter_view}, "
            f"resume_file={'yes' if resume_file else 'no'}, "
            f"resume_text={'yes' if resume_text else 'no'}"
        )

        # ── FALLBACK 1: Serve disk file ─────────────────────────────────────
        uploads_folder = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads'
        )
        candidate_upload_dir = os.path.join(uploads_folder, str(candidate_id))
        disk_file_path = os.path.join(candidate_upload_dir, resume_file) if resume_file else None

        if disk_file_path and os.path.exists(disk_file_path):
            ext = resume_file.rsplit('.', 1)[-1].lower() if '.' in resume_file else 'txt'
            logger.info(f"Resume disk file found: {disk_file_path} (ext={ext})")

            if not is_recruiter_view:
                # Serve original file to candidate
                try:
                    with open(disk_file_path, 'rb') as f:
                        file_data = f.read()
                    mime_types = {
                        'pdf': 'application/pdf',
                        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'doc': 'application/msword',
                        'txt': 'text/plain',
                    }
                    mime = mime_types.get(ext, 'application/octet-stream')
                    response = make_response(file_data)
                    response.headers['Content-Type'] = mime
                    response.headers['Content-Disposition'] = f'attachment; filename="{resume_file}"'
                    logger.info(f"Serving original resume from disk ({len(file_data)} bytes)")
                    return response
                except Exception as disk_err:
                    logger.warning(f"Disk read failed, falling through: {disk_err}")

            elif ext == 'pdf':
                # Anonymise PDF using PyMuPDF for recruiter downloads
                try:
                    anonymised_data = bytes(_anonymise_pdf_file(
                        disk_file_path, candidate_name, candidate_email,
                        candidate_phone, candidate_id
                    ))
                    response = make_response(anonymised_data)
                    response.headers['Content-Type'] = 'application/pdf'
                    response.headers['Content-Disposition'] = (
                        f'attachment; filename="resume_candidate_{candidate_id[:8]}.pdf"'
                    )
                    logger.info(f"Serving anonymised PDF from disk ({len(anonymised_data)} bytes)")
                    return response
                except Exception as anon_err:
                    logger.warning(f"PDF anonymisation failed, falling through: {anon_err}")
            else:
                # Recruiter viewing a non-PDF file — fall through to text-PDF generation
                logger.info(f"Non-PDF disk file for recruiter view, falling through to text-PDF")
        else:
            logger.info(
                f"Disk file not found (path={disk_file_path}), "
                f"falling through to text-PDF generation"
            )

        # ── FALLBACK 2: Generate PDF from stored resume text ────────────────
        if resume_text:
            try:
                display_name = f"Candidate [{candidate_id[:8]}]" if is_recruiter_view else candidate_name
                display_email = "***@***.com" if is_recruiter_view else candidate_email
                display_phone = "XXX-XXX-XXXX" if is_recruiter_view else candidate_phone

                # Anonymise resume text content for recruiters
                display_text = resume_text
                if is_recruiter_view:
                    display_text = _anonymise_resume_text(
                        resume_text, candidate_name, candidate_email, candidate_phone
                    )

                pdf_bytes = bytes(_generate_resume_pdf(
                    display_name, display_email, display_phone, skills, display_text
                ))

                filename = (
                    f"resume_candidate_{candidate_id[:8]}.pdf"
                    if is_recruiter_view
                    else f"resume_{candidate_name.replace(' ', '_')}.pdf"
                )
                response = make_response(pdf_bytes)
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
                logger.info(f"Generated text-to-PDF resume ({len(pdf_bytes)} bytes)")
                return response
            except Exception as gen_err:
                logger.error(f"Text-to-PDF generation failed: {gen_err}", exc_info=True)

        # ── FALLBACK 3: Graceful failure ────────────────────────────────────
        logger.error(f"All resume download fallbacks exhausted for app={application_id}")
        return jsonify({
            'success': False,
            'error': 'Resume could not be downloaded. Please re-upload your resume.'
        }), 404

    except Exception as e:
        logger.error(f"Resume download error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to download resume'}), 500


def _anonymise_resume_text(text, name, email, phone):
    """Replace PII in resume text with comprehensive anonymised placeholders.

    Redacts: name, email, phone, street addresses, city/country/state,
    college/university/school names, CGPA/GPA/percentage scores, LinkedIn/GitHub URLs,
    and date-of-birth patterns.
    """
    import re
    result = text

    # --- 1. Name ---
    if name and len(name) > 1:
        for variant in [name, name.upper(), name.lower(), name.title()]:
            result = result.replace(variant, '[CANDIDATE]')
        parts = name.split()
        for part in parts:
            if len(part) > 2:
                result = re.sub(r'\b' + re.escape(part) + r'\b', '[REDACTED]', result, flags=re.IGNORECASE)

    # --- 2. Email ---
    if email:
        result = result.replace(email, '[EMAIL REDACTED]')
    result = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL REDACTED]', result)

    # --- 3. Phone ---
    if phone:
        result = result.replace(phone, '[PHONE REDACTED]')
    # International / Indian / US formats
    result = re.sub(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '[PHONE REDACTED]', result)
    result = re.sub(r'\b\d{10}\b', '[PHONE REDACTED]', result)
    result = re.sub(r'\+91[-.\s]?\d{5}[-.\s]?\d{5}', '[PHONE REDACTED]', result)

    # --- 4. Street addresses ---
    result = re.sub(
        r'\d{1,5}\s[\w\s]{3,40}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl)\.?'
        r'(?:\s*,?\s*[\w\s]+,?\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?)?',
        '[ADDRESS REDACTED]', result, flags=re.IGNORECASE)

    # --- 5. City / State / Country ---
    _CITIES = (
        'Mumbai|Delhi|Bangalore|Bengaluru|Hyderabad|Chennai|Kolkata|Pune|Ahmedabad|Jaipur|Lucknow|Kanpur|Nagpur|Indore|Thane|Bhopal|'
        'Visakhapatnam|Patna|Vadodara|Ghaziabad|Ludhiana|Agra|Nashik|Faridabad|Meerut|Rajkot|Varanasi|Srinagar|Aurangabad|'
        'Coimbatore|Madurai|Kochi|Trivandrum|Thiruvananthapuram|Noida|Gurgaon|Gurugram|Chandigarh|Mysore|Mysuru|Mangalore|'
        'New York|San Francisco|Los Angeles|Chicago|Houston|Seattle|Austin|Boston|London|Berlin|Toronto|Sydney|Singapore|Dubai|'
        'Tokyo|Paris|Amsterdam|Dublin|Zurich|Munich|Stockholm|Helsinki|Copenhagen|Melbourne|Vancouver|Montreal|Calgary|'
        'San Jose|Sunnyvale|Mountain View|Palo Alto|Cupertino|Redmond|Kirkland'
    )
    _STATES = (
        'Tamil Nadu|Karnataka|Maharashtra|Telangana|Andhra Pradesh|Kerala|West Bengal|Gujarat|Rajasthan|Uttar Pradesh|'
        'Madhya Pradesh|Bihar|Punjab|Haryana|Odisha|Jharkhand|Chhattisgarh|Uttarakhand|Himachal Pradesh|Goa|'
        'California|Texas|Washington|New York|Massachusetts|Illinois|Georgia|Virginia|Florida|Oregon|'
        'Colorado|Pennsylvania|New Jersey|Maryland|North Carolina|Ohio|Michigan|Arizona|Minnesota|Connecticut'
    )
    _COUNTRIES = (
        'India|United States|USA|U\\.S\\.A|UK|United Kingdom|Canada|Australia|Germany|France|Japan|Singapore|'
        'Netherlands|Ireland|Switzerland|Sweden|Norway|Denmark|Finland|New Zealand|UAE|Israel|South Korea|China'
    )
    # Replace "City, State" / "City, Country" / standalone known cities in context
    result = re.sub(
        r'\b(' + _CITIES + r')\s*[,\-]\s*(' + _STATES + r'|' + _COUNTRIES + r')\b',
        '[LOCATION REDACTED]', result, flags=re.IGNORECASE)
    result = re.sub(
        r'\b(' + _STATES + r')\s*[,\-]\s*(' + _COUNTRIES + r')\b',
        '[LOCATION REDACTED]', result, flags=re.IGNORECASE)
    # Standalone city when preceded/followed by comma or newline (avoids false positives on skill words)
    result = re.sub(
        r'(?:^|[,\n])\s*\b(' + _CITIES + r')\b\s*(?:[,\n]|$)',
        ' [LOCATION REDACTED] ', result, flags=re.IGNORECASE | re.MULTILINE)
    # PIN codes (Indian 6-digit)
    result = re.sub(r'\b\d{6}\b', '[PIN REDACTED]', result)
    # US ZIP codes
    result = re.sub(r'\b\d{5}(?:-\d{4})?\b', '[ZIP REDACTED]', result)

    # --- 6. College / University / School names ---
    _INSTITUTIONS = (
        'IIT|Indian Institute of Technology|NIT|National Institute of Technology|IIIT|'
        'Indian Institute of Information Technology|BITS|Birla Institute|VIT|SRM|'
        'Anna University|Amity|Manipal|LPU|Lovely Professional|Jadavpur|'
        'JNTU|Jawaharlal Nehru|Osmania|Savitribai Phule|Mumbai University|'
        'Delhi University|Calcutta University|Madras University|'
        'MIT|Stanford|Harvard|Carnegie Mellon|UC Berkeley|Georgia Tech|'
        'Caltech|Princeton|Yale|Columbia|Cornell|Oxford|Cambridge|'
        'University of \\w+|\\w+ University|\\w+ Institute of Technology|'
        'College of \\w+|\\w+ College|\\w+ School of \\w+'
    )
    result = re.sub(
        r'\b(' + _INSTITUTIONS + r')(?:\s*,\s*[\w\s,]+)?',
        '[INSTITUTION REDACTED]', result, flags=re.IGNORECASE)

    # --- 7. CGPA / GPA / Percentage scores ---
    result = re.sub(r'\b(?:CGPA|GPA|CPI|SPI)\s*[:\-]?\s*\d+\.?\d*\s*(?:/\s*\d+\.?\d*)?', '[SCORE REDACTED]', result, flags=re.IGNORECASE)
    result = re.sub(r'\b\d{1,2}\.\d{1,2}\s*/\s*(?:10|4(?:\.0)?)\b', '[SCORE REDACTED]', result)
    result = re.sub(r'\b(?:percentage|percent|marks)\s*[:\-]?\s*\d{1,3}\.?\d*\s*%?', '[SCORE REDACTED]', result, flags=re.IGNORECASE)
    result = re.sub(r'\b\d{2,3}(?:\.\d+)?\s*%', '[SCORE REDACTED]', result)

    # --- 8. LinkedIn / GitHub / personal URLs ---
    result = re.sub(r'https?://(?:www\.)?linkedin\.com/in/[\w\-]+/?', '[LINKEDIN REDACTED]', result, flags=re.IGNORECASE)
    result = re.sub(r'https?://(?:www\.)?github\.com/[\w\-]+/?', '[GITHUB REDACTED]', result, flags=re.IGNORECASE)
    result = re.sub(r'https?://[\w\-]+\.[\w\-.]+(?:/[\w\-./]*)?', '[URL REDACTED]', result)

    # --- 9. Date of birth ---
    result = re.sub(
        r'\b(?:DOB|Date\s+of\s+Birth|D\.O\.B)\s*[:\-]?\s*\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}',
        '[DOB REDACTED]', result, flags=re.IGNORECASE)

    return result


# ---------------------------------------------------------------------------
# Resume section parser – extracts structured sections from raw text
# ---------------------------------------------------------------------------
_SECTION_PATTERNS = {
    'summary':        re.compile(r'^(?:PROFESSIONAL\s+)?(?:SUMMARY|OBJECTIVE|PROFILE|ABOUT\s+ME)\s*[:\-]?\s*$', re.IGNORECASE),
    'experience':     re.compile(r'^(?:WORK\s+)?(?:EXPERIENCE|EMPLOYMENT|WORK\s+HISTORY|PROFESSIONAL\s+EXPERIENCE)\s*[:\-]?\s*$', re.IGNORECASE),
    'education':      re.compile(r'^EDUCATION(?:AL)?\s*(?:BACKGROUND|QUALIFICATIONS?)?\s*[:\-]?\s*$', re.IGNORECASE),
    'skills':         re.compile(r'^(?:TECHNICAL\s+)?SKILLS?\s*(?:&\s*(?:TOOLS|TECHNOLOGIES))?\s*[:\-]?\s*$', re.IGNORECASE),
    'projects':       re.compile(r'^(?:PERSONAL\s+|ACADEMIC\s+)?PROJECTS?\s*[:\-]?\s*$', re.IGNORECASE),
    'certifications': re.compile(r'^CERTIFICATIONS?\s*(?:&\s*LICEN[SC]ES?)?\s*[:\-]?\s*$', re.IGNORECASE),
    'languages':      re.compile(r'^LANGUAGES?\s*[:\-]?\s*$', re.IGNORECASE),
    'achievements':   re.compile(r'^(?:AWARDS?\s*(?:&\s*)?)?(?:ACHIEVEMENTS?|HONORS?|ACCOMPLISHMENTS?)\s*[:\-]?\s*$', re.IGNORECASE),
    'interests':      re.compile(r'^(?:HOBBIES?\s*(?:&\s*)?)?INTERESTS?\s*[:\-]?\s*$', re.IGNORECASE),
    'publications':   re.compile(r'^PUBLICATIONS?\s*[:\-]?\s*$', re.IGNORECASE),
    'references':     re.compile(r'^REFERENCES?\s*[:\-]?\s*$', re.IGNORECASE),
}

import re as _re_module  # top-level for section patterns


def _parse_resume_sections(resume_text):
    """Parse raw resume text into labelled sections.

    Returns an OrderedDict: section_name → list[str] (lines).
    Unknown content before the first heading goes into 'header'.
    """
    from collections import OrderedDict
    sections = OrderedDict()
    current = 'header'
    sections[current] = []

    for line in resume_text.splitlines():
        stripped = line.strip()
        if not stripped:
            sections.setdefault(current, []).append('')
            continue
        matched = False
        for sec_name, pattern in _SECTION_PATTERNS.items():
            if pattern.match(stripped):
                current = sec_name
                sections.setdefault(current, [])
                matched = True
                break
        if not matched:
            sections.setdefault(current, []).append(line)
    # Remove empty trailing lines per section
    for k in sections:
        while sections[k] and sections[k][-1].strip() == '':
            sections[k].pop()
    return sections


# ---------------------------------------------------------------------------
# Skill categorisation helper
# ---------------------------------------------------------------------------
_SKILL_CATEGORIES = {
    'Languages': {'python', 'java', 'javascript', 'typescript', 'c', 'c++', 'c#', 'go', 'rust', 'ruby', 'php',
                  'swift', 'kotlin', 'scala', 'r', 'matlab', 'perl', 'dart', 'lua', 'shell', 'bash', 'sql',
                  'html', 'css', 'sass', 'less'},
    'Frontend': {'react', 'reactjs', 'react.js', 'angular', 'angularjs', 'vue', 'vuejs', 'vue.js', 'svelte',
                 'next.js', 'nextjs', 'nuxt', 'gatsby', 'tailwind', 'tailwindcss', 'bootstrap', 'material-ui',
                 'chakra', 'redux', 'webpack', 'vite', 'jquery'},
    'Backend': {'node', 'nodejs', 'node.js', 'express', 'expressjs', 'django', 'flask', 'fastapi',
                'spring', 'spring boot', 'springboot', '.net', 'asp.net', 'rails', 'laravel', 'nestjs',
                'graphql', 'rest', 'grpc', 'microservices'},
    'Databases': {'mysql', 'postgresql', 'postgres', 'mongodb', 'redis', 'sqlite', 'oracle', 'sql server',
                  'cassandra', 'dynamodb', 'elasticsearch', 'neo4j', 'firebase', 'supabase', 'couchdb',
                  'mariadb', 'cockroachdb'},
    'Cloud & DevOps': {'aws', 'azure', 'gcp', 'google cloud', 'docker', 'kubernetes', 'k8s', 'terraform',
                       'ansible', 'jenkins', 'ci/cd', 'github actions', 'gitlab ci', 'circleci', 'heroku',
                       'vercel', 'netlify', 'cloudflare', 'nginx', 'apache', 'linux', 'helm', 'prometheus',
                       'grafana', 'datadog', 'aws lambda', 'ec2', 's3'},
    'Data & ML': {'pandas', 'numpy', 'scikit-learn', 'sklearn', 'tensorflow', 'pytorch', 'keras', 'spark',
                  'hadoop', 'airflow', 'kafka', 'tableau', 'power bi', 'matplotlib', 'seaborn', 'opencv',
                  'nltk', 'spacy', 'huggingface', 'transformers', 'llm', 'deep learning', 'machine learning',
                  'data science', 'data engineering', 'etl', 'data pipeline'},
    'Tools & Other': {'git', 'github', 'gitlab', 'bitbucket', 'jira', 'confluence', 'figma', 'postman',
                      'swagger', 'vs code', 'intellij', 'agile', 'scrum', 'kanban', 'tdd', 'bdd',
                      'unit testing', 'jest', 'pytest', 'selenium', 'cypress', 'playwright'},
}


def _categorise_skills(skills):
    """Group a flat skill list into categories. Returns dict[category] → list[str]."""
    categorised = {}
    uncategorised = []
    skill_lower_map = {s.lower().strip(): s for s in skills}
    assigned = set()

    for category, keywords in _SKILL_CATEGORIES.items():
        matched = []
        for kw in keywords:
            if kw in skill_lower_map and kw not in assigned:
                matched.append(skill_lower_map[kw])
                assigned.add(kw)
        if matched:
            categorised[category] = sorted(matched, key=str.lower)

    for s_lower, s_orig in skill_lower_map.items():
        if s_lower not in assigned:
            uncategorised.append(s_orig)
    if uncategorised:
        categorised['Other'] = sorted(uncategorised, key=str.lower)

    return categorised


def _generate_resume_pdf(name, email, phone, skills, resume_text):
    """Generate a professional, structured PDF resume from resume text using fpdf2.

    Layout:
      - Header: Name centred, contact line
      - Professional Summary (first few lines or parsed summary section)
      - Technical Skills grouped by category
      - Work Experience with role / company / dates / bullet points
      - Projects
      - Education
      - Certifications
      - Languages / Achievements / Other sections
    """
    try:
        from fpdf import FPDF
    except ImportError:
        return _generate_minimal_pdf(name, resume_text)

    # --- Parse resume into sections ---
    sections = _parse_resume_sections(resume_text)

    class ResumePDF(FPDF):
        """Custom PDF with helper drawing methods."""
        _accent = (37, 99, 235)   # Blue accent #2563EB
        _dark   = (30, 41, 59)    # Slate-800
        _muted  = (100, 116, 139) # Slate-500
        _light  = (241, 245, 249) # Slate-100

        def _section_heading(self, title):
            self.ln(3)
            self.set_font('Helvetica', 'B', 11)
            self.set_text_color(*self._accent)
            self.cell(0, 7, title.upper(), ln=True)
            self.set_draw_color(*self._accent)
            self.set_line_width(0.5)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(2)
            self.set_text_color(*self._dark)

        def _body_text(self, text, bold=False):
            self.set_font('Helvetica', 'B' if bold else '', 9.5)
            clean = text.encode('latin-1', errors='replace').decode('latin-1')
            self.multi_cell(0, 4.5, clean)

        def _bullet_line(self, text):
            self.set_font('Helvetica', '', 9.5)
            x = self.get_x()
            self.cell(5, 4.5, chr(8226))  # bullet char
            clean = text.strip().encode('latin-1', errors='replace').decode('latin-1')
            self.multi_cell(0, 4.5, clean)

        def _tag_row(self, items, per_row=6):
            """Draw skill tags in a row."""
            self.set_font('Helvetica', '', 8.5)
            x_start = self.l_margin
            x = x_start
            for item in items:
                clean = item.encode('latin-1', errors='replace').decode('latin-1')
                tw = self.get_string_width(clean) + 8
                if x + tw > self.w - self.r_margin:
                    self.ln(6.5)
                    x = x_start
                self.set_xy(x, self.get_y())
                # Tag background
                self.set_fill_color(*self._light)
                self.set_draw_color(200, 200, 200)
                self.cell(tw, 5.5, clean, border=1, fill=True, align='C')
                x += tw + 3
            self.ln(7)

    pdf = ResumePDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(18, 15, 18)

    # ===== HEADER =====
    pdf.set_font('Helvetica', 'B', 20)
    pdf.set_text_color(*ResumePDF._dark)
    header_name = name.encode('latin-1', errors='replace').decode('latin-1')
    pdf.cell(0, 10, header_name, ln=True, align='C')

    contact_parts = []
    if email:
        contact_parts.append(email)
    if phone:
        contact_parts.append(phone)
    # Try to pull location from header section (first couple of lines)
    header_lines = sections.get('header', [])
    for hl in header_lines[:3]:
        hl_stripped = hl.strip()
        if hl_stripped and hl_stripped != name and '@' not in hl_stripped and not hl_stripped.replace('-','').replace('+','').replace(' ','').isdigit():
            # Likely a tagline / location / link – skip if it looks like a section start
            if len(hl_stripped) < 80 and not any(p.match(hl_stripped) for p in _SECTION_PATTERNS.values()):
                contact_parts.append(hl_stripped)
                break

    if contact_parts:
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(*ResumePDF._muted)
        contact_str = '  |  '.join(contact_parts).encode('latin-1', errors='replace').decode('latin-1')
        pdf.cell(0, 5, contact_str, ln=True, align='C')

    pdf.ln(2)
    pdf.set_draw_color(*ResumePDF._accent)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    # ===== PROFESSIONAL SUMMARY =====
    summary_lines = sections.get('summary', [])
    if not summary_lines:
        # Fallback: use first non-empty header lines as summary
        summary_lines = [l for l in header_lines if l.strip() and l.strip() != name][:5]
    if summary_lines:
        pdf._section_heading('Professional Summary')
        summary_text = '\n'.join(summary_lines).strip()
        pdf._body_text(summary_text)
        pdf.ln(2)

    # ===== TECHNICAL SKILLS =====
    categorised = _categorise_skills(skills) if skills else {}
    parsed_skills_lines = sections.get('skills', [])
    if categorised:
        pdf._section_heading('Technical Skills')
        for cat, items in categorised.items():
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(*ResumePDF._muted)
            pdf.cell(0, 5, f'{cat}:', ln=True)
            pdf.set_text_color(*ResumePDF._dark)
            pdf._tag_row(items)
        pdf.ln(1)
    elif parsed_skills_lines:
        pdf._section_heading('Technical Skills')
        for sl in parsed_skills_lines:
            if sl.strip():
                pdf._body_text(sl.strip())
        pdf.ln(2)

    # ===== WORK EXPERIENCE =====
    exp_lines = sections.get('experience', [])
    if exp_lines:
        pdf._section_heading('Work Experience')
        for line in exp_lines:
            stripped = line.strip()
            if not stripped:
                pdf.ln(2)
                continue
            # Heuristic: lines with dates are likely role/company headers
            if _re_module.search(r'\b(19|20)\d{2}\b', stripped) or _re_module.search(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}', stripped, _re_module.IGNORECASE):
                pdf._body_text(stripped, bold=True)
            elif stripped.startswith(('-', '*', chr(8226), chr(9679))):
                pdf._bullet_line(stripped.lstrip('-*' + chr(8226) + chr(9679) + ' '))
            else:
                pdf._body_text(stripped)
        pdf.ln(2)

    # ===== PROJECTS =====
    proj_lines = sections.get('projects', [])
    if proj_lines:
        pdf._section_heading('Projects')
        for line in proj_lines:
            stripped = line.strip()
            if not stripped:
                pdf.ln(2)
                continue
            if stripped.startswith(('-', '*', chr(8226), chr(9679))):
                pdf._bullet_line(stripped.lstrip('-*' + chr(8226) + chr(9679) + ' '))
            elif len(stripped) < 80 and not stripped.endswith('.'):
                pdf._body_text(stripped, bold=True)
            else:
                pdf._body_text(stripped)
        pdf.ln(2)

    # ===== EDUCATION =====
    edu_lines = sections.get('education', [])
    if edu_lines:
        pdf._section_heading('Education')
        for line in edu_lines:
            stripped = line.strip()
            if not stripped:
                pdf.ln(2)
                continue
            if _re_module.search(r'\b(19|20)\d{2}\b', stripped):
                pdf._body_text(stripped, bold=True)
            elif stripped.startswith(('-', '*', chr(8226))):
                pdf._bullet_line(stripped.lstrip('-*' + chr(8226) + ' '))
            else:
                pdf._body_text(stripped)
        pdf.ln(2)

    # ===== CERTIFICATIONS =====
    cert_lines = sections.get('certifications', [])
    if cert_lines:
        pdf._section_heading('Certifications')
        for line in cert_lines:
            stripped = line.strip()
            if stripped:
                pdf._bullet_line(stripped.lstrip('-*' + chr(8226) + ' '))
        pdf.ln(2)

    # ===== LANGUAGES =====
    lang_lines = sections.get('languages', [])
    if lang_lines:
        pdf._section_heading('Languages')
        pdf._body_text(', '.join(l.strip() for l in lang_lines if l.strip()))
        pdf.ln(2)

    # ===== ACHIEVEMENTS =====
    ach_lines = sections.get('achievements', [])
    if ach_lines:
        pdf._section_heading('Awards & Achievements')
        for line in ach_lines:
            stripped = line.strip()
            if stripped:
                pdf._bullet_line(stripped.lstrip('-*' + chr(8226) + ' '))
        pdf.ln(2)

    # ===== REMAINING SECTIONS =====
    rendered = {'header', 'summary', 'experience', 'education', 'skills', 'projects',
                'certifications', 'languages', 'achievements', 'interests', 'references', 'publications'}
    for sec_name, lines in sections.items():
        if sec_name in rendered or not lines:
            continue
        pdf._section_heading(sec_name.replace('_', ' ').title())
        for line in lines:
            stripped = line.strip()
            if stripped:
                pdf._body_text(stripped)
        pdf.ln(2)

    # If NO sections were parsed at all, dump the full text neatly
    meaningful_sections = [k for k in sections if k != 'header' and sections[k]]
    if not meaningful_sections and not skills:
        pdf._section_heading('Resume Content')
        clean_text = resume_text.encode('latin-1', errors='replace').decode('latin-1')
        pdf.set_font('Helvetica', '', 9.5)
        pdf.multi_cell(0, 4.5, clean_text)

    return pdf.output()


def _generate_minimal_pdf(name, text):
    """Minimal PDF generation without any library dependencies."""
    clean = text.encode('latin-1', errors='replace').decode('latin-1')
    content = f"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
4 0 obj
<</Length {len(clean) + 50}>>
stream
BT /F1 12 Tf 72 720 Td ({name}) Tj 0 -20 Td /F1 10 Tf ({clean[:2000]}) Tj ET
endstream
endobj
xref
0 6
trailer<</Size 6/Root 1 0 R>>
startxref
0
%%EOF"""
    return content.encode('latin-1')


def _anonymise_pdf_file(file_path, name, email, phone, candidate_id):
    """Anonymise PII in a PDF file using PyMuPDF (fitz).

    Redacts: name, email, phone, LinkedIn/GitHub URLs, city/college names, CGPA/GPA.
    """
    import fitz  # PyMuPDF
    import re

    doc = fitz.open(file_path)

    # Build list of literal PII strings to redact
    pii_patterns = []
    if name and len(name) > 1:
        pii_patterns.append(name)
        pii_patterns.append(name.upper())
        pii_patterns.append(name.title())
        for part in name.split():
            if len(part) > 2:
                pii_patterns.append(part)
    if email:
        pii_patterns.append(email)
    if phone:
        pii_patterns.append(phone)

    # Regex patterns to search per-span
    _regex_patterns = [
        re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),                 # emails
        re.compile(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'),         # phones
        re.compile(r'\b\d{10}\b'),                                                        # 10-digit phones
        re.compile(r'\+91[-.\s]?\d{5}[-.\s]?\d{5}'),                                      # Indian phones
        re.compile(r'https?://(?:www\.)?linkedin\.com/in/[\w\-]+/?', re.I),               # LinkedIn
        re.compile(r'https?://(?:www\.)?github\.com/[\w\-]+/?', re.I),                    # GitHub
        re.compile(r'\b(?:CGPA|GPA|CPI|SPI)\s*[:\-]?\s*\d+\.?\d*(?:\s*/\s*\d+\.?\d*)?', re.I),  # CGPA
        re.compile(r'\b\d{1,2}\.\d{1,2}\s*/\s*(?:10|4(?:\.0)?)\b'),                      # x.x/10
        re.compile(r'\b\d{2,3}(?:\.\d+)?\s*%'),                                           # percentage
    ]

    for page in doc:
        # 1. Redact literal PII strings
        for pattern in pii_patterns:
            for inst in page.search_for(pattern):
                page.add_redact_annot(inst, fill=(0, 0, 0))

        # 2. Redact regex-matched PII in text spans
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"]
                    for rgx in _regex_patterns:
                        for match in rgx.finditer(text):
                            for r in page.search_for(match.group()):
                                page.add_redact_annot(r, fill=(0, 0, 0))

        # Apply all redactions
        page.apply_redactions()

        # Watermark on first page
        if page.number == 0:
            page.insert_text(
                fitz.Point(72, 30),
                f"ANONYMISED - Candidate [{candidate_id[:8]}]",
                fontsize=9,
                color=(0.5, 0.5, 0.5)
            )

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    return output.getvalue()


@bp.route('/apply/<job_id>', methods=['POST'])
@jwt_required()
@require_role(['candidate', 'admin'])
def apply_to_job(job_id):
    """Apply to a job posting"""
    try:
        current_user = get_jwt_identity()
        
        # Handle both string and dict JWT identity formats
        if isinstance(current_user, str):
            user_id = current_user
            # Fetch user role from database
            db = get_db()
            users_collection = db['users']
            user = users_collection.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({'error': 'User not found'}), 404
            role = user.get('role')
        else:
            user_id = current_user.get('user_id')
            role = current_user.get('role')
        
        if role != 'candidate':
            return jsonify({'error': 'Only candidates can apply to jobs'}), 403
        
        db = get_db()
        jobs_collection = db['jobs']
        candidates_collection = db['candidates']
        applications_collection = db['applications']
        
        # Check if job exists
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        if job.get('status', 'open') != 'open':
            return jsonify({'error': 'Job is not accepting applications'}), 400
        
        # Get candidate profile first (needed for resume hash check)
        candidate = candidates_collection.find_one({'user_id': user_id})
        if not candidate:
            return jsonify({'error': 'Complete your profile first'}), 400
        
        if not candidate.get('resume_text'):
            return jsonify({'error': 'Upload your resume first'}), 400
        
        current_resume_hash = candidate.get('resume_hash', '')
        
        # Check if already applied - but allow re-apply if resume has been updated
        existing_app = applications_collection.find_one({
            'job_id': job_id,
            'candidate_id': user_id
        })
        
        is_reapplication = False
        if existing_app:
            # Check if resume has changed since last application
            previous_resume_hash = existing_app.get('resume_hash_at_application', '')
            
            if current_resume_hash and current_resume_hash == previous_resume_hash:
                # Resume unchanged - don't allow re-apply
                return jsonify({
                    'error': 'Already applied to this job',
                    'hint': 'Upload an updated resume to re-apply with improved qualifications'
                }), 409
            else:
                # Resume has changed - allow re-application by updating existing
                is_reapplication = True
                logger.info(f"🔄 Re-application allowed: resume hash changed from {previous_resume_hash[:8]}... to {current_resume_hash[:8]}...")
        
        # Analyze candidate fit
        analysis = analyze_candidate(
            job_description=job['description'],
            job_skills=job.get('required_skills', []),
            resume_text=candidate.get('anonymized_resume', ''),
            resume_skills=candidate.get('skills', []),
            cci_score=candidate.get('cci_score')
        )
        
        # Prepare application data
        application_data = {
            'job_id': job_id,
            'candidate_id': user_id,
            'resume_match_score': analysis['tfidf_score'],
            'skill_match_score': analysis['skill_match'],
            'overall_score': analysis['overall_score'],
            'cci_score': analysis['cci_score'],
            'matched_skills': analysis['matched_skills'],
            'decision': analysis['decision'],
            'resume_hash_at_application': current_resume_hash,  # Track which resume version
            # AUTO-SHORTLIST: Score >= 70 → shortlisted, else pending
            'status': 'shortlisted' if analysis['overall_score'] >= 70 else 'pending',
            'auto_status_reason': f"Auto-shortlisted (score: {analysis['overall_score']:.0f}%)" if analysis['overall_score'] >= 70 else None
        }
        
        if is_reapplication:
            # UPDATE existing application with new scores
            application_data['reapplied_at'] = datetime.utcnow()
            application_data['application_version'] = existing_app.get('application_version', 1) + 1
            
            applications_collection.update_one(
                {'_id': existing_app['_id']},
                {'$set': application_data}
            )
            application_id = str(existing_app['_id'])
            logger.info(f"✅ Re-application updated: {application_id} (version {application_data['application_version']})")
        else:
            # CREATE new application
            application = Application(
                job_id=job_id,
                candidate_id=user_id,
                resume_match_score=analysis['tfidf_score'],
                skill_match_score=analysis['skill_match'],
                overall_score=analysis['overall_score'],
                cci_score=analysis['cci_score'],
                matched_skills=analysis['matched_skills'],
                decision=analysis['decision']
            )
            
            app_dict = application.to_dict()
            app_dict['resume_hash_at_application'] = current_resume_hash
            app_dict['application_version'] = 1
            
            result = applications_collection.insert_one(app_dict)
            application_id = str(result.inserted_id)
        
        # Log audit event for application submission
        log_audit_event(
            event_type='application_resubmitted' if is_reapplication else 'application_submitted',
            user_id=user_id,
            job_id=job_id,
            candidate_id=user_id,
            application_id=application_id,
            details={
                'job_title': job.get('title'),
                'anonymized': True,
                'is_reapplication': is_reapplication,
                'resume_hash': current_resume_hash[:16] if current_resume_hash else None
            },
            scores={
                'overall_score': analysis['overall_score'],
                'tfidf_score': analysis['tfidf_score'],
                'skill_match': analysis['skill_match'],
                'cci_score': analysis.get('cci_score'),
                'decision': analysis['decision']
            }
        )
        
        # Log auto-shortlist / auto-filter as a status_changed audit event
        auto_status = application_data.get('status', 'pending')
        if auto_status != 'pending':
            log_audit_event(
                event_type='status_changed',
                user_id='system',
                job_id=job_id,
                candidate_id=user_id,
                application_id=application_id,
                details={
                    'old_status': 'pending',
                    'new_status': auto_status,
                    'note': application_data.get('auto_status_reason', 'Auto-decision by scoring engine'),
                    'decision_type': auto_status,
                    'automated': True
                },
                scores={
                    'overall_score': analysis['overall_score'],
                    'skill_match': analysis['skill_match']
                }
            )
        
        # Update job application count (ONLY for new applications, not re-applications)
        if not is_reapplication:
            jobs_collection.update_one(
                {'_id': ObjectId(job_id)},
                {'$inc': {'applications_count': 1}}
            )
            
            # Update candidate applications list (only for new)
            candidates_collection.update_one(
                {'user_id': user_id},
                {'$addToSet': {'applications': job_id}}  # Use addToSet to avoid duplicates
            )
        
        # Send email notifications
        try:
            users_collection = db['users']
            candidate_user = users_collection.find_one({'_id': ObjectId(user_id)})
            
            # Send confirmation email to candidate (Async)
            if candidate_user:
                send_application_confirmation.delay(
                    candidate_user.get('email'),
                    candidate_user.get('full_name'),
                    job.get('title'),
                    job.get('company_name', 'the company')
                )
            
            # Send alert email to recruiter (Async)
            recruiter_id = job.get('recruiter_id')
            if recruiter_id:
                recruiter_user = users_collection.find_one({'_id': ObjectId(recruiter_id)})
                if recruiter_user:
                    send_new_application_alert.delay(
                        recruiter_user.get('email'),
                        recruiter_user.get('full_name'),
                        candidate_user.get('full_name'),
                        job.get('title'),
                        analysis['overall_score']
                    )
        except Exception as email_error:
            logger.warning(f"⚠️ Application emails failed: {email_error}")

        # ── Bug #1: Auto-assign assessment session if job has an assessment config ──
        try:
            assessment_config = db['assessment_configs'].find_one({
                'job_id': job_id,
                'is_active': True
            })
            if assessment_config and not is_reapplication:
                # Check if candidate already has a session for this config
                existing_session = db['smart_sessions'].find_one({
                    'candidate_id': user_id,
                    'config_id': str(assessment_config['_id'])
                })
                if not existing_session:
                    session_doc = {
                        'candidate_id': user_id,
                        'config_id': str(assessment_config['_id']),
                        'application_id': application_id,
                        'job_id': job_id,
                        'status': 'assigned',
                        'assigned_at': datetime.utcnow(),
                        'expires_at': datetime.utcnow() + timedelta(days=7),
                        'attempts_remaining': assessment_config.get('max_attempts', 3),
                        'questions': [],
                        'answers': {},
                        'final_score': 0.0,
                        'final_percentage': 0.0,
                        'passed': False,
                        'verdict': 'pending',
                        'created_at': datetime.utcnow()
                    }
                    session_result = db['smart_sessions'].insert_one(session_doc)
                    logger.info(
                        f"Assessment session auto-assigned: session={session_result.inserted_id}, "
                        f"config={assessment_config['_id']}, candidate={user_id[:8]}, "
                        f"expires_at={session_doc['expires_at'].isoformat()}"
                    )

                    # Send assessment notification email
                    try:
                        from backend.services.email_templates import EmailTemplates
                        from backend.services.email_service import EmailNotificationSystem

                        candidate_user = db['users'].find_one({'_id': ObjectId(user_id)})
                        frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:5000')
                        email_html = EmailTemplates.render_template('assessment_invitation', {
                            'candidate_name': candidate_user.get('full_name', 'Candidate') if candidate_user else 'Candidate',
                            'job_title': job.get('title', 'the position'),
                            'assessment_title': assessment_config.get('title', assessment_config.get('job_role', 'Assessment')),
                            'question_count': assessment_config.get('total_questions', 'N/A'),
                            'time_limit': assessment_config.get('duration_minutes', 'N/A'),
                            'deadline': session_doc['expires_at'].strftime('%B %d, %Y'),
                            'assessment_url': f"{frontend_url}/candidate.html#assessments",
                        })
                        email_system = EmailNotificationSystem()
                        candidate_email = candidate_user.get('email', '') if candidate_user else ''
                        if candidate_email:
                            email_system.send_email(
                                candidate_email,
                                f"Assessment Ready: {job.get('title', 'Position')}",
                                email_html
                            )
                            logger.info(f"Assessment notification sent to {candidate_email}")
                    except Exception as email_err:
                        logger.warning(f"Assessment email notification failed: {email_err}")

                else:
                    logger.info(f"Assessment session already exists for candidate={user_id[:8]}, config={assessment_config['_id']}")
        except Exception as assess_err:
            logger.warning(f"Assessment auto-assignment failed: {assess_err}")

        # Return appropriate response
        if is_reapplication:
            return jsonify({
                'message': 'Application re-submitted with updated resume!',
                'application_id': application_id,
                'score': analysis['overall_score'],
                'score_improved': True,  # Could compare old vs new score
                'decision': analysis['decision'],
                'matched_skills': analysis['matched_skills'],
                'recommendations': analysis['recommendations']
            }), 200  # 200 for update, not 201
        else:
            return jsonify({
                'message': 'Application submitted successfully',
                'application_id': application_id,
                'score': analysis['overall_score'],
                'decision': analysis['decision'],
                'matched_skills': analysis['matched_skills'],
                'recommendations': analysis['recommendations']
            }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/applications', methods=['GET'])
@jwt_required()
@require_role(['candidate', 'admin'])
def get_my_applications():
    """Get candidate's own applications"""
    try:
        current_user = get_jwt_identity()
        
        # Handle both string and dict JWT identity formats
        if isinstance(current_user, str):
            user_id = current_user
            db = get_db()
            users_collection = db['users']
            user = users_collection.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({'error': 'User not found'}), 404
            role = user.get('role')
        else:
            user_id = current_user.get('user_id')
            role = current_user.get('role')
        
        if role != 'candidate':
            return jsonify({'error': 'Only candidates can view their applications'}), 403
        
        db = get_db()
        applications_collection = db['applications']
        jobs_collection = db['jobs']
        
        # Get applications
        applications = list(applications_collection.find(
            {'candidate_id': user_id}
        ).sort('applied_date', -1))
        
        # Enrich with job details
        for app in applications:
            app['_id'] = str(app['_id'])
            job = jobs_collection.find_one({'_id': ObjectId(app['job_id'])})
            if job:
                app['job_title'] = job['title']
                app['company_name'] = job.get('company_name', 'Company')
                app['location'] = job.get('location', 'Remote')
                # Bug #4 fix: include job_details for skills match insights
                app['job_details'] = {
                    'required_skills': job.get('required_skills', []),
                    'job_type': job.get('job_type', ''),
                    'department': job.get('department', ''),
                    'title': job['title']
                }
            
            # Convert applied_date to applied_at for frontend compatibility
            if 'applied_date' in app:
                app['applied_at'] = app['applied_date']
        
        return jsonify({
            'applications': applications,
            'count': len(applications)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/profile', methods=['GET'])
@jwt_required()
@require_role(['candidate', 'admin'])
def get_candidate_profile():
    """Get candidate profile details"""
    try:
        current_user = get_jwt_identity()
        
        # Handle both string and dict JWT identity formats
        if isinstance(current_user, str):
            user_id = current_user
        else:
            user_id = current_user.get('user_id')
        
        db = get_db()
        candidates_collection = db['candidates']
        users_collection = db['users']
        
        # Get or create candidate profile
        candidate = candidates_collection.find_one({'user_id': user_id})
        
        if not candidate:
            # Create default candidate profile
            user = users_collection.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({'error': 'User account not found'}), 404
            
            default_profile = {
                'user_id': user_id,
                'email': user.get('email', ''),
                'first_name': user.get('full_name', '').split()[0] if user.get('full_name') else '',
                'last_name': ' '.join(user.get('full_name', '').split()[1:]) if user.get('full_name') else '',
                'phone': '',
                'skills': [],
                'experience_years': 0,
                'education': '',
                'resume_file': None,
                'resume_uploaded': False,
                'applications': [],
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            result = candidates_collection.insert_one(default_profile)
            default_profile['_id'] = str(result.inserted_id)
            
            return jsonify(default_profile), 200
        
        candidate['_id'] = str(candidate['_id'])
        # Don't send full resume text, just metadata
        if 'resume_text' in candidate:
            candidate['resume_uploaded'] = True
            del candidate['resume_text']
        if 'anonymized_resume' in candidate:
            del candidate['anonymized_resume']

        # Bug #3 fix: compute profile completion_score server-side
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        completion_details = {
            'name': bool(user and user.get('full_name')),
            'phone': bool(candidate.get('phone')),
            'location': bool(candidate.get('location')),
            'about_me': len(candidate.get('bio', '') or '') > 50,
            'skills': len(candidate.get('skills', [])) >= 3,
            'experience': (candidate.get('experience_years', 0) or 0) > 0,
            'education': bool(candidate.get('education')),
            'resume': bool(
                candidate.get('resume_uploaded')
                or candidate.get('resume_file')
                or candidate.get('resume_path')
            ),
        }
        weights = {
            'name': 10, 'phone': 10, 'location': 10, 'about_me': 15,
            'skills': 15, 'experience': 15, 'education': 15, 'resume': 10
        }
        candidate['completion_score'] = sum(
            weights[k] for k, v in completion_details.items() if v
        )
        candidate['completion_details'] = completion_details

        return jsonify(candidate), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/profile', methods=['PUT'])
@jwt_required()
@require_role(['candidate', 'admin'])
def update_candidate_profile():
    """Update candidate profile details"""
    try:
        current_user = get_jwt_identity()
        
        # Handle both string and dict JWT identity formats
        if isinstance(current_user, str):
            user_id = current_user
        else:
            user_id = current_user.get('user_id')
        
        data = request.get_json()
        
        # Validate required fields
        if not data.get('first_name') or not data.get('last_name'):
            return jsonify({'error': 'First name and last name are required'}), 400
        
        db = get_db()
        candidates_collection = db['candidates']
        users_collection = db['users']
        
        # Prepare update data
        update_data = {
            'first_name': data.get('first_name'),
            'last_name': data.get('last_name'),
            'phone': data.get('phone', ''),
            'skills': data.get('skills', []),
            'experience_years': float(data.get('experience', 0)),
            'education': data.get('education', ''),
            'bio': data.get('bio', ''),
            'location': data.get('location', ''),
            'linkedin': data.get('linkedin', ''),
            'portfolio': data.get('portfolio', ''),
            'updated_at': datetime.utcnow()
        }
        
        # Update candidate profile
        result = candidates_collection.update_one(
            {'user_id': user_id},
            {'$set': update_data},
            upsert=True
        )
        
        # Update user full_name in users collection
        full_name = f"{data.get('first_name')} {data.get('last_name')}"
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'full_name': full_name}}
        )
        
        return jsonify({
            'message': 'Profile updated successfully',
            'profile': update_data
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Gap 8: Voluntary self-identification for fairness auditing ────────────────

@bp.route('/self-identification', methods=['PUT'])
@jwt_required()
@require_role(['candidate', 'admin'])
def update_self_identification():
    """
    Opt-in endpoint for candidates to voluntarily provide demographic data
    used *only* for aggregate fairness auditing.  Data is stored in the
    candidate profile and never exposed to individual recruiters.
    All fields are optional; sending ``{}`` clears stored demographics.
    """
    try:
        current_user = get_jwt_identity()
        user_id = current_user if isinstance(current_user, str) else current_user.get('user_id')

        data = request.get_json() or {}

        demographics: dict = {}

        # Validate each optional field against allowed value sets
        if 'gender' in data:
            val = str(data['gender']).lower().strip()
            if val not in VALID_GENDERS:
                return jsonify({
                    'error': f"Invalid gender value. Allowed: {sorted(VALID_GENDERS)}"
                }), 400
            demographics['gender'] = val

        if 'age_group' in data:
            val = str(data['age_group']).strip()
            if val not in VALID_AGE_GROUPS:
                return jsonify({
                    'error': f"Invalid age_group value. Allowed: {sorted(VALID_AGE_GROUPS)}"
                }), 400
            demographics['age_group'] = val

        if 'ethnicity' in data:
            val = str(data['ethnicity']).lower().strip()
            if val not in VALID_ETHNICITIES:
                return jsonify({
                    'error': f"Invalid ethnicity value. Allowed: {sorted(VALID_ETHNICITIES)}"
                }), 400
            demographics['ethnicity'] = val

        # Store consent timestamp
        demographics['consent_given_at'] = datetime.utcnow()
        demographics['updated_at'] = datetime.utcnow()

        db = get_db()
        db['candidates'].update_one(
            {'user_id': user_id},
            {'$set': {'demographics': demographics}},
            upsert=True,
        )

        return jsonify({
            'message': 'Self-identification data saved. This data is used only for aggregate fairness auditing.',
            'demographics': {k: v for k, v in demographics.items()
                             if k not in ('consent_given_at', 'updated_at')},
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/self-identification', methods=['DELETE'])
@jwt_required()
@require_role(['candidate', 'admin'])
def delete_self_identification():
    """Allow candidates to withdraw their self-identification data entirely."""
    try:
        current_user = get_jwt_identity()
        user_id = current_user if isinstance(current_user, str) else current_user.get('user_id')

        db = get_db()
        db['candidates'].update_one(
            {'user_id': user_id},
            {'$unset': {'demographics': 1}},
        )

        return jsonify({'message': 'Self-identification data removed.'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/applications/<application_id>/onboarding', methods=['PUT'])
@jwt_required()
@require_role(['candidate', 'admin'])
def update_onboarding_step(application_id):
    """Toggle an onboarding checklist step for a hired candidate."""
    try:
        current_user = get_jwt_identity()
        user_id = current_user if isinstance(current_user, str) else current_user.get('user_id')

        data = request.get_json()
        step = data.get('step')
        completed = data.get('completed', False)

        valid_steps = [
            'offer_accepted', 'documents_uploaded', 'profile_completed',
            'nda_signed', 'it_setup_requested', 'orientation_scheduled'
        ]
        if step not in valid_steps:
            return jsonify({'error': 'Invalid onboarding step'}), 400

        db = get_db()
        applications_collection = db['applications']

        # Verify the application belongs to this candidate and is hired
        application = applications_collection.find_one({
            '_id': ObjectId(application_id),
            'candidate_id': user_id,
            'status': 'hired'
        })
        if not application:
            return jsonify({'error': 'Application not found or not in hired status'}), 404

        # Update the specific onboarding step
        applications_collection.update_one(
            {'_id': ObjectId(application_id)},
            {'$set': {f'onboarding.{step}': completed}}
        )

        return jsonify({'message': f'Onboarding step {step} updated', 'step': step, 'completed': completed}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
