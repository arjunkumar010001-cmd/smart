"""
Fairness Audit Logging Routes
Track all hiring decisions for compliance and bias detection
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from bson import ObjectId

from backend.models.database import get_db
from backend.security.rbac import require_permission, Permissions

bp = Blueprint('audit', __name__)


def log_audit_event(event_type, user_id, job_id=None, candidate_id=None, 
                   application_id=None, details=None, scores=None):
    """
    Log an audit event for fairness tracking
    
    Args:
        event_type: Type of event (application_submitted, status_changed, ranked, etc.)
        user_id: ID of user performing the action
        job_id: ID of job (optional)
        candidate_id: ID of candidate (optional)
        application_id: ID of application (optional)
        details: Additional details about the event
        scores: Scoring information if applicable
    """
    try:
        db = get_db()
        audit_log = {
            'event_type': event_type,
            'user_id': user_id,
            'job_id': job_id,
            'candidate_id': candidate_id,
            'application_id': application_id,
            'details': details or {},
            'scores': scores or {},
            'timestamp': datetime.utcnow(),
            'ip_address': request.remote_addr if request else None,
            'user_agent': request.headers.get('User-Agent') if request else None
        }
        
        db['audit_logs'].insert_one(audit_log)
        print(f"✅ Audit log created: {event_type}")
        return True
    except Exception as e:
        print(f"❌ Audit log error: {e}")
        return False


@bp.route('/logs', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_AUDIT_LOGS)
def get_audit_logs():
    """Get audit logs (admin only)"""
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
        
        if role not in ('admin', 'company', 'recruiter'):
            return jsonify({'error': 'Admin or company access required'}), 403
        
        db = get_db()
        
        # Get filters from query params
        event_type = request.args.get('event_type')
        job_id = request.args.get('job_id')
        candidate_id = request.args.get('candidate_id')
        limit = int(request.args.get('limit', 100))
        
        # Build query
        query = {}
        if event_type:
            query['event_type'] = event_type
        if job_id:
            query['job_id'] = job_id
        if candidate_id:
            query['candidate_id'] = candidate_id
        
        # Get logs
        logs = list(db['audit_logs'].find(query).sort('timestamp', -1).limit(limit))
        
        # Convert ObjectId to string and format dates
        for log in logs:
            log['_id'] = str(log['_id'])
            if 'timestamp' in log:
                log['timestamp'] = log['timestamp'].isoformat()
        
        return jsonify({
            'total': len(logs),
            'logs': logs
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/report', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_AUDIT_LOGS)
def generate_audit_report():
    """Generate comprehensive fairness audit report"""
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
        
        if role not in ['admin', 'company', 'recruiter']:
            return jsonify({'error': 'Admin or company access required'}), 403
        
        db = get_db()
        
        # Get date range
        days = int(request.args.get('days', 30))
        from_date = datetime.utcnow() - timedelta(days=days)
        
        # Filter by company for recruiters/company users
        query = {'timestamp': {'$gte': from_date}}
        if role in ('company', 'recruiter'):
            # Only show logs for this company's jobs
            jobs = list(db['jobs'].find({'recruiter_id': user_id}))
            job_ids = [str(job['_id']) for job in jobs]
            query['job_id'] = {'$in': job_ids}
        
        # Get all relevant logs
        logs = list(db['audit_logs'].find(query))
        
        # Generate statistics
        report = {
            'period': f'Last {days} days',
            'generated_at': datetime.utcnow().isoformat(),
            'total_events': len(logs),
            'events_by_type': {},
            'applications_processed': 0,
            'status_changes': 0,
            'rankings_performed': 0,
            'average_score': 0,
            'score_distribution': {
                'excellent': 0,  # 75%+
                'good': 0,       # 50-74%
                'fair': 0,       # 25-49%
                'poor': 0        # <25%
            },
            'decisions': {
                'hired': 0,
                'rejected': 0,
                'pending': 0,
                'shortlisted': 0,
                'interviewed': 0
            },
            # Frontend-compatible keys
            'decisions_breakdown': {
                'hired': 0,
                'rejected': 0,
                'pending': 0,
                'shortlisted': 0,
                'interviewed': 0
            },
            'average_scores': {
                'overall': 0,
                'skills_match': 0,
                'experience': 0
            }
        }
        
        total_scores = []
        skills_scores = []
        experience_scores = []
        
        for log in logs:
            event_type = log.get('event_type', 'unknown')
            report['events_by_type'][event_type] = report['events_by_type'].get(event_type, 0) + 1
            
            if event_type == 'application_submitted':
                report['applications_processed'] += 1
            elif event_type == 'status_changed':
                report['status_changes'] += 1
                status = log.get('details', {}).get('new_status')
                if status in report['decisions']:
                    report['decisions'][status] += 1
                if status in report['decisions_breakdown']:
                    report['decisions_breakdown'][status] += 1
            elif event_type == 'ranked':
                report['rankings_performed'] += 1
                scores = log.get('scores', {})
                score = scores.get('overall_score')
                if score:
                    total_scores.append(score)
                    if score >= 75:
                        report['score_distribution']['excellent'] += 1
                    elif score >= 50:
                        report['score_distribution']['good'] += 1
                    elif score >= 25:
                        report['score_distribution']['fair'] += 1
                    else:
                        report['score_distribution']['poor'] += 1
                skill_score = scores.get('skill_match')
                if skill_score is not None:
                    skills_scores.append(skill_score)
                exp_score = scores.get('experience_score')
                if exp_score is not None:
                    experience_scores.append(exp_score)
        
        # Calculate average scores
        if total_scores:
            avg_overall = round(sum(total_scores) / len(total_scores), 2)
            report['average_score'] = avg_overall
            report['average_scores']['overall'] = avg_overall
        if skills_scores:
            report['average_scores']['skills_match'] = round(sum(skills_scores) / len(skills_scores), 2)
        if experience_scores:
            report['average_scores']['experience'] = round(sum(experience_scores) / len(experience_scores), 2)
        
        return jsonify(report), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/job/<job_id>/report', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_AUDIT_LOGS)
def get_job_audit_report(job_id):
    """Get audit report for a specific job"""
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
        
        if role not in ['admin', 'company', 'recruiter']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = get_db()
        
        # Verify job access for companies/recruiters
        if role in ('company', 'recruiter'):
            job = db['jobs'].find_one({'_id': ObjectId(job_id), 'recruiter_id': user_id})
            if not job:
                return jsonify({'error': 'Job not found or unauthorized'}), 404
        
        # Get all logs for this job
        logs = list(db['audit_logs'].find({'job_id': job_id}))
        
        report = {
            'job_id': job_id,
            'total_logs': len(logs),
            'applications': 0,
            'rankings': 0,
            'status_changes': 0,
            'timeline': []
        }
        
        for log in logs:
            event = {
                'type': log.get('event_type'),
                'timestamp': log.get('timestamp').isoformat() if log.get('timestamp') else None,
                'details': log.get('details', {})
            }
            report['timeline'].append(event)
            
            event_type = log.get('event_type')
            if event_type == 'application_submitted':
                report['applications'] += 1
            elif event_type == 'ranked':
                report['rankings'] += 1
            elif event_type == 'status_changed':
                report['status_changes'] += 1
        
        # Sort timeline by date (newest first)
        report['timeline'].sort(key=lambda x: x['timestamp'] if x['timestamp'] else '', reverse=True)
        
        return jsonify(report), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# P0 ML: ML METRICS AND FAIRNESS AUDIT ENDPOINTS
# =============================================================================

@bp.route('/ml-metrics', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_ANALYTICS)
def get_ml_metrics():
    """
    P0 ML: Get ML system metrics (admin only)
    
    Returns metrics from:
    - ML matching service (SBERT/TF-IDF)
    - Anonymization service
    - Email service
    """
    try:
        current_user = get_jwt_identity()
        
        # Check admin access
        if isinstance(current_user, dict):
            role = current_user.get('role')
        else:
            db = get_db()
            user = db['users'].find_one({'_id': ObjectId(current_user)})
            role = user.get('role') if user else None
        
        if role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        metrics = {
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Get ML matching metrics
        try:
            from backend.services.ml_matching_service import get_ml_matching_service
            ml_service = get_ml_matching_service()
            metrics['ml_matching'] = ml_service.get_metrics()
        except Exception as e:
            metrics['ml_matching'] = {'error': str(e)}
        
        # Get anonymization metrics
        try:
            from backend.services.anonymization_service import get_anonymizer
            anonymizer = get_anonymizer()
            metrics['anonymization'] = anonymizer.get_metrics()
        except Exception as e:
            metrics['anonymization'] = {'error': str(e)}
        
        # Get email metrics
        try:
            from backend.utils.email_service import email_service
            metrics['email'] = email_service.get_metrics()
        except Exception as e:
            metrics['email'] = {'error': str(e)}
        
        return jsonify(metrics), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/fairness-audit', methods=['POST'])
@jwt_required()
@require_permission(Permissions.MANAGE_COMPLIANCE)
def run_fairness_audit():
    """
    P0 ML: Run fairness audit on hiring decisions
    
    Request body:
        job_id: Optional - audit decisions for specific job
        time_range_days: Optional - audit decisions in last N days
        attribute: Optional - specific attribute to audit (gender, etc.)
    """
    try:
        current_user = get_jwt_identity()
        
        # Check admin/recruiter access
        if isinstance(current_user, dict):
            role = current_user.get('role')
            user_id = current_user.get('user_id')
        else:
            user_id = current_user
            db = get_db()
            user = db['users'].find_one({'_id': ObjectId(user_id)})
            role = user.get('role') if user else None
        
        if role not in ['admin', 'recruiter', 'company']:
            return jsonify({'error': 'Admin or recruiter access required'}), 403
        
        data = request.get_json() or {}
        job_id = data.get('job_id')
        time_range_days = data.get('time_range_days', 30)
        
        db = get_db()
        
        # Build query
        query = {}
        if job_id:
            query['job_id'] = job_id
        if role in ['recruiter', 'company']:
            # Recruiters can only audit their own jobs
            recruiter_jobs = list(db['jobs'].find({'recruiter_id': user_id}, {'_id': 1}))
            job_ids = [str(j['_id']) for j in recruiter_jobs]
            query['job_id'] = {'$in': job_ids}
        
        # Add time filter
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=time_range_days)
        query['applied_date'] = {'$gte': cutoff_date}
        
        # Get applications
        applications = list(db['applications'].find(query))
        
        if len(applications) < 10:
            return jsonify({
                'warning': 'Insufficient data for meaningful fairness analysis',
                'applications_found': len(applications),
                'minimum_required': 10
            }), 200
        
        # Run fairness audit
        try:
            from backend.services.fairness_audit_service import get_fairness_service
            fairness_service = get_fairness_service()
            
            # Gap 8: Use real opt-in demographic data instead of score_group proxy
            audit_data = []
            attribute_fields_found = set()
            for app in applications:
                entry = {
                    'decision': app.get('status', 'pending'),
                    'overall_score': app.get('overall_score', 0),
                }
                # Look up candidate demographics from opt-in self-identification
                candidate_id = app.get('candidate_id') or app.get('user_id')
                if candidate_id:
                    candidate = db['candidates'].find_one({'user_id': str(candidate_id)})
                    demographics = (candidate or {}).get('demographics', {})
                    for attr in ('gender', 'age_group', 'ethnicity'):
                        if attr in demographics and demographics[attr] != 'prefer_not_to_say':
                            entry[attr] = demographics[attr]
                            attribute_fields_found.add(attr)

                # Fallback: keep score_group for candidates without opt-in data
                if not any(a in entry for a in ('gender', 'age_group', 'ethnicity')):
                    entry['score_group'] = 'high' if app.get('overall_score', 0) >= 70 else 'low'
                    attribute_fields_found.add('score_group')

                audit_data.append(entry)

            # Use real demographic fields when available, otherwise fall back to score_group
            attribute_fields = sorted(attribute_fields_found)
            
            # Run audit
            audit_result = fairness_service.audit_application_batch(
                audit_data,
                decision_field='decision',
                attribute_fields=attribute_fields
            )
            
            return jsonify({
                'audit_result': audit_result,
                'applications_analyzed': len(applications),
                'time_range_days': time_range_days,
                'job_id': job_id
            }), 200
            
        except Exception as e:
            return jsonify({'error': f'Fairness audit failed: {str(e)}'}), 500
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
