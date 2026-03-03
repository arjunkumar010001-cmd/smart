"""
Data Subject Request (DSR) Routes
Handles GDPR compliance: data export, data deletion, consent management
"""

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.models.database import get_db
from backend.security.rbac import require_permission, Permissions
from backend.security.rate_limiter import rate_limit
from backend.security.encryption import decrypt_pii_fields
from bson import ObjectId
from datetime import datetime
import json
import os
import io
import zipfile
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('dsr', __name__)


def _get_identity():
    """Extract user_id from JWT identity (handles both string and dict formats)."""
    identity = get_jwt_identity()
    if isinstance(identity, dict):
        return identity.get('user_id')
    return identity


@bp.route('/export', methods=['POST'])
@jwt_required()
@rate_limit(max_requests=5, window_seconds=3600)  # 5 exports per hour
def export_user_data():
    """
    Export all user data (GDPR Article 15 - Right to Access)
    
    Returns JSON file with all user data including:
    - Profile information
    - Applications
    - Assessment results
    - Audit logs
    """
    try:
        current_user_id = _get_identity()
        data = request.get_json()
        target_user_id = data.get('user_id', current_user_id)
        
        # Authorization check
        database = get_db()
        users = database['users']
        current_user = users.find_one({'_id': ObjectId(current_user_id)})
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Only admins can export other users' data
        if target_user_id != current_user_id and current_user.get('role') != 'admin':
            return jsonify({'error': 'Permission denied'}), 403
        
        # Log DSR request
        _log_dsr_activity('data_export', current_user_id, target_user_id)
        
        # Collect all user data
        export_data = _collect_user_data(target_user_id)
        
        # Create export package
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        
        # Convert to JSON with formatting
        json_data = json.dumps(export_data, indent=2, default=str)
        
        # Create in-memory file
        memory_file = io.BytesIO()
        memory_file.write(json_data.encode('utf-8'))
        memory_file.seek(0)
        
        logger.info(f"✅ Data export completed for user: {target_user_id}")
        
        return send_file(
            memory_file,
            mimetype='application/json',
            as_attachment=True,
            download_name=f'user_data_export_{target_user_id}_{timestamp}.json'
        )
        
    except Exception as e:
        logger.error(f"❌ Data export failed: {e}")
        return jsonify({'error': 'Export failed', 'details': str(e)}), 500


@bp.route('/delete', methods=['POST'])
@jwt_required()
@rate_limit(max_requests=3, window_seconds=3600)  # 3 deletions per hour
def delete_user_data():
    """
    Delete all user data (GDPR Article 17 - Right to Erasure)
    
    Deletes or anonymizes:
    - User profile
    - Applications
    - Uploaded files
    - Personal data in audit logs (anonymized)
    """
    try:
        current_user_id = _get_identity()
        data = request.get_json()
        target_user_id = data.get('user_id', current_user_id)
        confirmation = data.get('confirmation', '')
        
        # Require confirmation
        if confirmation != 'DELETE':
            return jsonify({
                'error': 'Confirmation required',
                'message': 'Please send {"confirmation": "DELETE"} to confirm deletion'
            }), 400
        
        # Authorization check
        users = get_db()['users']
        current_user = users.find_one({'_id': ObjectId(current_user_id)})
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Only admins can delete other users' data
        if target_user_id != current_user_id and current_user.get('role') != 'admin':
            return jsonify({'error': 'Permission denied'}), 403
        
        # Log DSR request BEFORE deletion
        _log_dsr_activity('data_deletion', current_user_id, target_user_id)
        
        # Perform deletion
        deletion_summary = _delete_user_data(target_user_id)
        
        logger.info(f"✅ Data deletion completed for user: {target_user_id}")
        
        return jsonify({
            'success': True,
            'message': 'All user data has been deleted',
            'summary': deletion_summary
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Data deletion failed: {e}")
        return jsonify({'error': 'Deletion failed', 'details': str(e)}), 500


@bp.route('/anonymize', methods=['POST'])
@jwt_required()
@require_permission(Permissions.MANAGE_COMPLIANCE)
def anonymize_user_data():
    """
    Anonymize user data while preserving analytics
    
    Replaces PII with anonymized values but keeps statistical data
    """
    try:
        data = request.get_json()
        target_user_id = data.get('user_id')
        
        if not target_user_id:
            return jsonify({'error': 'user_id required'}), 400
        
        # Log DSR request
        current_user_id = _get_identity()
        _log_dsr_activity('data_anonymization', current_user_id, target_user_id)
        
        # Perform anonymization
        anonymization_summary = _anonymize_user_data(target_user_id)
        
        logger.info(f"✅ Data anonymization completed for user: {target_user_id}")
        
        return jsonify({
            'success': True,
            'message': 'User data has been anonymized',
            'summary': anonymization_summary
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Data anonymization failed: {e}")
        return jsonify({'error': 'Anonymization failed', 'details': str(e)}), 500


@bp.route('/consent', methods=['GET'])
@jwt_required()
def get_consent_status():
    """Get user's consent status"""
    try:
        current_user_id = _get_identity()
        
        users = get_db()['users']
        user = users.find_one({'_id': ObjectId(current_user_id)})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        consent = user.get('consent', {})
        
        return jsonify({
            'consent': {
                'data_processing': consent.get('data_processing', False),
                'data_storage': consent.get('data_storage', False),
                'marketing_emails': consent.get('marketing_emails', False),
                'analytics': consent.get('analytics', False),
                'third_party_sharing': consent.get('third_party_sharing', False),
                'consented_at': consent.get('consented_at'),
                'updated_at': consent.get('updated_at')
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Get consent failed: {e}")
        return jsonify({'error': 'Failed to get consent'}), 500


@bp.route('/consent', methods=['POST'])
@jwt_required()
def update_consent():
    """Update user's consent preferences"""
    try:
        current_user_id = _get_identity()
        data = request.get_json()
        
        # Validate consent data
        consent_fields = [
            'data_processing',
            'data_storage',
            'marketing_emails',
            'analytics',
            'third_party_sharing'
        ]
        
        consent_update = {}
        for field in consent_fields:
            if field in data:
                consent_update[field] = bool(data[field])
        
        if not consent_update:
            return jsonify({'error': 'No consent preferences provided'}), 400
        
        # Add timestamps
        consent_update['updated_at'] = datetime.utcnow().isoformat()
        
        if 'consented_at' not in data:
            consent_update['consented_at'] = datetime.utcnow().isoformat()
        
        # Update user's consent
        users = get_db()['users']
        result = users.update_one(
            {'_id': ObjectId(current_user_id)},
            {'$set': {f'consent.{key}': value for key, value in consent_update.items()}}
        )
        
        if result.modified_count == 0:
            return jsonify({'error': 'Failed to update consent'}), 500
        
        # Log consent change
        _log_dsr_activity('consent_update', current_user_id, current_user_id, consent_update)
        
        logger.info(f"✅ Consent updated for user: {current_user_id}")
        
        return jsonify({
            'success': True,
            'message': 'Consent preferences updated',
            'consent': consent_update
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Update consent failed: {e}")
        return jsonify({'error': 'Failed to update consent'}), 500


@bp.route('/logs', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_AUDIT_LOGS)
def get_dsr_logs():
    """Get DSR activity logs (admin only)"""
    try:
        # Get query parameters
        user_id = request.args.get('user_id')
        activity_type = request.args.get('type')
        limit = min(int(request.args.get('limit', 100)), 500)
        
        # Build query
        query = {'activity_type': {'$in': ['data_export', 'data_deletion', 'data_anonymization', 'consent_update']}}
        
        if user_id:
            query['target_user_id'] = user_id
        
        if activity_type:
            query['activity_type'] = activity_type
        
        # Get logs
        dsr_logs = get_db()['dsr_logs']
        logs = list(dsr_logs.find(query).sort('timestamp', -1).limit(limit))
        
        # Format response
        for log in logs:
            log['_id'] = str(log['_id'])
        
        return jsonify({
            'logs': logs,
            'count': len(logs)
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Get DSR logs failed: {e}")
        return jsonify({'error': 'Failed to get logs'}), 500


# Helper functions

def _collect_user_data(user_id: str) -> dict:
    """Collect all data for a user"""
    database = get_db()
    
    # Get user profile
    user = database['users'].find_one({'_id': user_id})
    if user:
        user.pop('password', None)  # Never export password hashes
        user.pop('password_hash', None)  # Also handle password_hash key
        user = decrypt_pii_fields(user)  # Decrypt PII for export
    
    # Get candidate profile
    candidate = database['candidates'].find_one({'user_id': user_id})
    if candidate:
        candidate = decrypt_pii_fields(candidate)
    
    # Get applications
    applications = list(database['applications'].find({'user_id': user_id}))
    
    # Get quiz attempts
    quiz_attempts = list(database['quiz_attempts'].find({'candidate_id': user_id}))
    
    # Get audit logs (relevant to this user)
    audit_logs = list(database['audit_logs'].find({
        '$or': [
            {'user_id': user_id},
            {'candidate_id': user_id}
        ]
    }).limit(1000))
    
    return {
        'export_date': datetime.utcnow().isoformat(),
        'user_id': user_id,
        'user': user,
        'candidate_profile': candidate,
        'applications': applications,
        'quiz_attempts': quiz_attempts,
        'audit_logs': audit_logs,
        'gdpr_notice': 'This export contains all personal data stored about you in the Smart Hiring System.'
    }


def _delete_user_data(user_id: str) -> dict:
    """Delete all data for a user"""
    database = get_db()
    summary = {}
    
    # Delete uploaded files
    import os
    from backend.security.file_security import file_security_manager
    
    try:
        # Get candidate profile to find resume files
        candidate = database['candidates'].find_one({'user_id': user_id})
        if candidate and candidate.get('resume_file'):
            # Delete physical resume file
            resume_path = os.path.join(
                os.getenv('UPLOAD_FOLDER', 'uploads'),
                candidate['resume_file']
            )
            if os.path.exists(resume_path):
                file_security_manager.delete_file_securely(resume_path)
                summary['files_deleted'] = 1
        
        # Delete any other files associated with applications
        applications = database['applications'].find({'candidate_id': user_id})
        files_deleted = 0
        for app in applications:
            if app.get('resume_file'):
                file_path = os.path.join(
                    os.getenv('UPLOAD_FOLDER', 'uploads'),
                    app['resume_file']
                )
                if os.path.exists(file_path):
                    file_security_manager.delete_file_securely(file_path)
                    files_deleted += 1
        
        if files_deleted > 0:
            summary['application_files_deleted'] = files_deleted
            
    except Exception as e:
        logger.warning(f"Error deleting files for user {user_id}: {e}")
        summary['file_deletion_errors'] = str(e)
    
    # Delete user record
    result = database['users'].delete_one({'_id': user_id})
    summary['user_deleted'] = result.deleted_count
    
    # Delete candidate profile
    result = database['candidates'].delete_one({'user_id': user_id})
    summary['candidate_profile_deleted'] = result.deleted_count
    
    # Delete applications
    result = database['applications'].delete_many({'user_id': user_id})
    summary['applications_deleted'] = result.deleted_count
    
    # Delete quiz attempts
    result = database['quiz_attempts'].delete_many({'candidate_id': user_id})
    summary['quiz_attempts_deleted'] = result.deleted_count
    
    # Anonymize audit logs (keep for compliance, but remove PII)
    result = database['audit_logs'].update_many(
        {'$or': [{'user_id': user_id}, {'candidate_id': user_id}]},
        {'$set': {
            'user_id': f'DELETED_{user_id[:8]}',
            'candidate_id': f'DELETED_{user_id[:8]}',
            'details.email': '[REDACTED]',
            'details.name': '[REDACTED]',
            'anonymized': True,
            'anonymized_at': datetime.utcnow().isoformat()
        }}
    )
    summary['audit_logs_anonymized'] = result.modified_count
    
    return summary


def _anonymize_user_data(user_id: str) -> dict:
    """Anonymize user data while preserving analytics"""
    database = get_db()
    summary = {}
    
    anonymous_id = f"ANON_{user_id[:8]}"
    anonymous_email = f"anonymized_{user_id[:8]}@deleted.local"
    
    # Anonymize user record
    result = database['users'].update_one(
        {'_id': user_id},
        {'$set': {
            'email': anonymous_email,
            'first_name': '[Anonymized]',
            'last_name': '[User]',
            'phone': None,
            'anonymized': True,
            'anonymized_at': datetime.utcnow().isoformat()
        }}
    )
    summary['user_anonymized'] = result.modified_count
    
    # Anonymize candidate profile
    result = database['candidates'].update_one(
        {'user_id': user_id},
        {'$set': {
            'name': '[Anonymized User]',
            'email': anonymous_email,
            'phone': None,
            'address': None,
            'anonymized': True,
            'anonymized_at': datetime.utcnow().isoformat()
        }}
    )
    summary['candidate_profile_anonymized'] = result.modified_count
    
    # Keep applications but anonymize
    result = database['applications'].update_many(
        {'user_id': user_id},
        {'$set': {
            'anonymized': True,
            'anonymized_at': datetime.utcnow().isoformat()
        }}
    )
    summary['applications_anonymized'] = result.modified_count
    
    return summary


def _log_dsr_activity(activity_type: str, requester_id: str, target_user_id: str, details: dict = None):
    """Log DSR activity for compliance"""
    try:
        database = get_db()
        dsr_logs = database['dsr_logs']
        
        log_entry = {
            'activity_type': activity_type,
            'requester_id': requester_id,
            'target_user_id': target_user_id,
            'timestamp': datetime.utcnow().isoformat(),
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'details': details or {}
        }
        
        dsr_logs.insert_one(log_entry)
        logger.info(f"📝 DSR activity logged: {activity_type} for {target_user_id}")
        
    except Exception as e:
        logger.error(f"❌ Failed to log DSR activity: {e}")
