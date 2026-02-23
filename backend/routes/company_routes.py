from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from bson import ObjectId

from backend.models.database import get_db
from backend.utils.email_service import email_service
from backend.utils.matching import calculate_skill_match, compute_overall_score, extract_skills
from backend.routes.audit_routes import log_audit_event
from backend.security.rbac import require_permission, Permissions
from backend.services.video_interview_service import create_interview_session

bp = Blueprint('company', __name__)

@bp.route('/applications/<application_id>/status', methods=['PUT'])
@jwt_required()
@require_permission(Permissions.MANAGE_APPLICATIONS)
def update_application_status(application_id):
    """Update application status with history tracking"""
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
            recruiter_email = user.get('email')
        else:
            user_id = current_user.get('user_id')
            role = current_user.get('role')
            db = get_db()
            users_collection = db['users']
            user = users_collection.find_one({'_id': ObjectId(user_id)})
            recruiter_email = user.get('email') if user else 'Unknown'
        
        if (role or '').lower() not in ['company', 'recruiter', 'admin']:
            return jsonify({'error': 'Only recruiters can update application status'}), 403
        
        data = request.get_json()
        new_status = data.get('status')
        note = data.get('note', '')
        interview_date = data.get('interview_date')
        interview_type = data.get('interview_type', 'ai_automated')
        meeting_link = data.get('meeting_link')
        
        # Validate status
        valid_statuses = ['pending', 'shortlisted', 'interviewed', 'hired', 'rejected']
        if new_status not in valid_statuses:
            return jsonify({'error': 'Invalid status'}), 400
        
        db = get_db()
        applications_collection = db['applications']
        
        # Get application
        application = applications_collection.find_one({'_id': ObjectId(application_id)})
        if not application:
            return jsonify({'error': 'Application not found'}), 404
        
        # Auto-create internal interview session when status = interviewed
        if new_status == 'interviewed':
            try:
                base_url = request.host_url.rstrip('/')
                job_id = str(application.get('job_id', ''))
                candidate_id = str(application.get('candidate_id', ''))
                
                from datetime import timedelta
                scheduled_time = None
                if interview_date:
                    try:
                        scheduled_time = datetime.fromisoformat(interview_date)
                    except (ValueError, TypeError):
                        pass
                
                session_doc = create_interview_session(
                    job_id=job_id,
                    candidate_id=candidate_id,
                    scheduled_by=user_id,
                    interview_type=interview_type,
                    duration_minutes=90,
                    base_url=base_url,
                    scheduled_time_utc=scheduled_time,
                )
                meeting_link = session_doc.get('meeting_link', '')
            except Exception as interview_err:
                print(f"⚠️ Failed to create interview session: {interview_err}")
                # Fallback: generate a simple link
                import secrets
                token = secrets.token_urlsafe(32)
                base_url = request.host_url.rstrip('/')
                meeting_link = f"{base_url}/interview/room/{token}"
        
        old_status = application.get('status', 'pending')
        
        # Create status history entry
        status_history = application.get('status_history', [])
        status_history.append({
            'status': new_status,
            'changed_by': user_id,
            'changed_by_email': recruiter_email,
            'changed_at': datetime.utcnow(),
            'note': note,
            'previous_status': old_status
        })
        
        # Prepare update data
        update_data = {
            'status': new_status,
            'status_updated_at': datetime.utcnow(),
            'status_updated_by': user_id,
            'status_history': status_history
        }
        
        # Add interview details if status is interviewed
        if new_status == 'interviewed':
            if interview_date:
                update_data['interview_date'] = interview_date
            if meeting_link:
                update_data['meeting_link'] = meeting_link
            update_data['interview_scheduled'] = True
            update_data['interview_type'] = interview_type
        
        # Update application
        result = applications_collection.update_one(
            {'_id': ObjectId(application_id)},
            {'$set': update_data}
        )
        
        if result.modified_count == 0:
            return jsonify({'error': 'Failed to update status'}), 500
        
        # Log audit event for fairness tracking
        try:
            log_audit_event(
                event_type='status_changed',
                user_id=user_id,
                job_id=str(application.get('job_id', '')),
                candidate_id=str(application.get('candidate_id', '')),
                application_id=application_id,
                details={
                    'old_status': old_status,
                    'new_status': new_status,
                    'note': note,
                    'recruiter_email': recruiter_email,
                    'decision_type': new_status
                }
            )
        except Exception as audit_err:
            print(f"⚠️ Audit log failed (non-blocking): {audit_err}")
        
        # Send email notification to candidate
        try:
            candidates_collection = db['candidates']
            users_collection = db['users']
            jobs_collection = db['jobs']
            
            candidate_id = application.get('candidate_id')
            candidate_user = users_collection.find_one({'_id': ObjectId(candidate_id)})
            job = jobs_collection.find_one({'_id': ObjectId(application.get('job_id'))})
            
            if candidate_user and job:
                # If status is interviewed and we have interview details, send interview invitation
                if new_status == 'interviewed' and meeting_link:
                    # Import the interview invitation method if available
                    # For now, send enhanced status update with interview details
                    email_service.send_status_update_email(
                        to_email=candidate_user.get('email'),
                        candidate_name=candidate_user.get('full_name'),
                        job_title=job.get('title'),
                        new_status=new_status,
                        note=note if note else None,
                        interview_date=interview_date,
                        meeting_link=meeting_link
                    )
                else:
                    email_service.send_status_update_email(
                        to_email=candidate_user.get('email'),
                        candidate_name=candidate_user.get('full_name'),
                        job_title=job.get('title'),
                        new_status=new_status,
                        note=note if note else None
                    )
        except Exception as email_error:
            print(f"⚠️ Status update email failed: {email_error}")
        
        return jsonify({
            'message': 'Status updated successfully',
            'new_status': new_status,
            'application_id': application_id,
            'meeting_link': meeting_link if new_status == 'interviewed' else None
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/applications/<application_id>/history', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_APPLICATIONS)
def get_application_history(application_id):
    """Get status change history for an application"""
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
        
        if role not in ['company', 'recruiter', 'admin', 'candidate']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = get_db()
        applications_collection = db['applications']
        
        application = applications_collection.find_one({'_id': ObjectId(application_id)})
        if not application:
            return jsonify({'error': 'Application not found'}), 404
        
        # If candidate, verify they own this application
        if role == 'candidate' and application.get('candidate_id') != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        status_history = application.get('status_history', [])
        
        # Convert datetime objects to strings
        for entry in status_history:
            if 'changed_at' in entry:
                entry['changed_at'] = entry['changed_at'].isoformat()
        
        return jsonify({
            'application_id': application_id,
            'current_status': application.get('status', 'pending'),
            'history': status_history
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/applications/stats', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_APPLICATIONS)
def get_application_stats():
    """Get application statistics for recruiter"""
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
        
        if role not in ['company', 'recruiter', 'admin']:
            return jsonify({'error': 'Only recruiters can view stats'}), 403
        
        db = get_db()
        jobs_collection = db['jobs']
        applications_collection = db['applications']
        
        # Get all jobs for this recruiter
        recruiter_jobs = list(jobs_collection.find(
            {'recruiter_id': user_id}
        ))
        job_ids = [str(job['_id']) for job in recruiter_jobs]
        
        # Get all applications for these jobs
        applications = list(applications_collection.find(
            {'job_id': {'$in': job_ids}}
        ))
        
        # Calculate statistics
        stats = {
            'total': len(applications),
            'pending': len([a for a in applications if a.get('status') == 'pending']),
            'shortlisted': len([a for a in applications if a.get('status') == 'shortlisted']),
            'interviewed': len([a for a in applications if a.get('status') == 'interviewed']),
            'hired': len([a for a in applications if a.get('status') == 'hired']),
            'rejected': len([a for a in applications if a.get('status') == 'rejected']),
            'conversion_rate': 0
        }
        
        # Calculate conversion rate (hired / total)
        if stats['total'] > 0:
            stats['conversion_rate'] = round((stats['hired'] / stats['total']) * 100, 2)
        
        return jsonify(stats), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/jobs/<job_id>/ranked-candidates', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_CANDIDATES)
def get_ranked_candidates(job_id):
    """Get ranked list of candidates for a specific job"""
    try:
        current_user = get_jwt_identity()
        
        # Handle both string and dict JWT identity formats
        if isinstance(current_user, str):
            user_id = current_user
            db = get_db()
            user = db['users'].find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({'error': 'User not found'}), 404
            role = user.get('role')
        else:
            user_id = current_user.get('user_id')
            role = current_user.get('role')
        
        if role not in ['company', 'recruiter']:
            return jsonify({'error': 'Only recruiters can view ranked candidates'}), 403
        
        db = get_db()
        
        # Verify job belongs to this recruiter
        job = db['jobs'].find_one({'_id': ObjectId(job_id), 'recruiter_id': user_id})
        if not job:
            return jsonify({'error': 'Job not found or unauthorized'}), 404
        
        # Get job requirements
        job_skills = job.get('required_skills', [])
        job_description = job.get('description', '')
        job_requirements = job.get('requirements', [])
        job_text = f"{job_description} {' '.join(job_requirements) if isinstance(job_requirements, list) else job_requirements}"
        
        # Get all applications for this job
        applications = list(db['applications'].find({'job_id': job_id}))
        
        ranked_candidates = []
        
        for app in applications:
            candidate_id = app.get('candidate_id')
            
            # Get candidate profile (candidates collection keyed by user_id)
            candidate = db['candidates'].find_one({'user_id': candidate_id})
            if not candidate:
                # Fallback: try by _id
                try:
                    candidate = db['candidates'].find_one({'_id': ObjectId(candidate_id)})
                except Exception:
                    pass
            if not candidate:
                continue
            
            # Get user info for candidate
            user = db['users'].find_one({'_id': ObjectId(candidate_id)})
            if not user:
                continue
            
            # Extract candidate skills and resume text
            candidate_skills = candidate.get('skills', [])
            if not isinstance(candidate_skills, list):
                candidate_skills = []
            resume_text = candidate.get('resume_text', '')
            
            # Calculate skill match
            skill_match_score = calculate_skill_match(job_skills, candidate_skills)
            
            # For now, use simplified scoring (TF-IDF requires sklearn which may not be available)
            # Calculate based on skill match and experience
            # Robust extraction: experience_years may be missing, and
            # 'experience' may be a list of job-history dicts (not a number).
            experience_years = candidate.get('experience_years', None)
            if not isinstance(experience_years, (int, float)):
                exp_raw = candidate.get('experience', 0)
                if isinstance(exp_raw, (int, float)):
                    experience_years = exp_raw
                elif isinstance(exp_raw, list):
                    experience_years = len(exp_raw)  # approximate from entries
                else:
                    try:
                        experience_years = float(exp_raw)
                    except (TypeError, ValueError):
                        experience_years = 0
            
            # Experience score (normalize to 0-1, max at 10 years)
            experience_score = min(float(experience_years) / 10.0, 1.0)
            
            # Compute overall score (60% skills, 40% experience)
            overall_score = compute_overall_score(
                tfidf_score=experience_score,  # Using experience as proxy for TF-IDF
                skill_match=skill_match_score,
                cci_score=None
            )
            
            # Find matched and missing skills
            job_skills_set = set([s.lower() for s in job_skills])
            candidate_skills_set = set([s.lower() for s in candidate_skills])
            matched_skills = list(job_skills_set.intersection(candidate_skills_set))
            missing_skills = list(job_skills_set - candidate_skills_set)
            
            # Safely serialize applied_date (could be datetime, string, or None)
            raw_date = app.get('applied_date')
            if hasattr(raw_date, 'isoformat'):
                applied_date_str = raw_date.isoformat()
            elif isinstance(raw_date, str):
                applied_date_str = raw_date
            else:
                applied_date_str = datetime.utcnow().isoformat()
            
            # Add to ranked list
            ranked_candidates.append({
                'application_id': str(app['_id']),
                'candidate_id': candidate_id,
                'candidate_name': user.get('full_name', 'Unknown'),
                'candidate_email': user.get('email', ''),
                'applied_date': applied_date_str,
                'status': app.get('status', 'pending'),
                'scores': {
                    'overall_score': overall_score,
                    'skill_match': round(skill_match_score * 100, 1),
                    'experience_score': round(experience_score * 100, 1)
                },
                'skills': {
                    'matched': matched_skills,
                    'missing': missing_skills,
                    'candidate_skills': candidate_skills,
                    'match_count': len(matched_skills),
                    'total_required': len(job_skills)
                },
                'experience_years': experience_years,
                'education': candidate.get('education', 'Not specified') if isinstance(candidate.get('education'), str) else 'Not specified',
                'location': candidate.get('location', 'Not specified'),
                'resume_uploaded': candidate.get('resume_uploaded', False)
            })
        
        # Sort by overall score (highest first)
        ranked_candidates.sort(key=lambda x: x['scores']['overall_score'], reverse=True)
        
        # Add rank numbers and log audit events
        for i, candidate in enumerate(ranked_candidates, 1):
            candidate['rank'] = i
            
            # Log ranking event for audit trail
            log_audit_event(
                event_type='ranked',
                user_id=user_id,
                job_id=job_id,
                candidate_id=candidate['candidate_id'],
                application_id=candidate['application_id'],
                details={
                    'rank': i,
                    'total_applicants': len(ranked_candidates)
                },
                scores={
                    'overall_score': candidate['scores']['overall_score'],
                    'skill_match': candidate['scores']['skill_match'],
                    'experience_score': candidate['scores']['experience_score'],
                    'matched_skills_count': candidate['skills']['match_count'],
                    'total_required_skills': candidate['skills']['total_required']
                }
            )
        
        return jsonify({
            'job_id': job_id,
            'job_title': job.get('title', ''),
            'total_applicants': len(ranked_candidates),
            'ranked_candidates': ranked_candidates
        }), 200
        
    except Exception as e:
        print(f"Error in ranked candidates: {e}")
        return jsonify({'error': str(e)}), 500
