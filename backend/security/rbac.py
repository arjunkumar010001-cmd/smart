"""
Role-Based Access Control (RBAC) System
Manages permissions and role-based authorization
"""

from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from typing import List, Set, Dict
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)


# Permission definitions
class Permissions:
    """Define all permissions in the system"""
    
    # User management
    MANAGE_USERS = 'manage_users'
    VIEW_USERS = 'view_users'
    
    # Job management
    CREATE_JOB = 'create_job'
    EDIT_JOB = 'edit_job'
    DELETE_JOB = 'delete_job'
    VIEW_JOB = 'view_job'
    PUBLISH_JOB = 'publish_job'
    
    # Application management
    VIEW_APPLICATIONS = 'view_applications'
    MANAGE_APPLICATIONS = 'manage_applications'
    REVIEW_APPLICATIONS = 'review_applications'
    
    # Candidate management
    VIEW_CANDIDATES = 'view_candidates'
    MANAGE_CANDIDATES = 'manage_candidates'
    VIEW_CANDIDATE_PII = 'view_candidate_pii'
    EXPORT_CANDIDATE_DATA = 'export_candidate_data'
    DELETE_CANDIDATE_DATA = 'delete_candidate_data'
    
    # Assessment management
    CREATE_ASSESSMENT = 'create_assessment'
    EDIT_ASSESSMENT = 'edit_assessment'
    VIEW_ASSESSMENT = 'view_assessment'
    GRADE_ASSESSMENT = 'grade_assessment'
    
    # Analytics & Reports
    VIEW_ANALYTICS = 'view_analytics'
    VIEW_COMPANY_ANALYTICS = 'view_company_analytics'
    EXPORT_REPORTS = 'export_reports'
    
    # Audit & Compliance
    VIEW_AUDIT_LOGS = 'view_audit_logs'
    EXPORT_AUDIT_LOGS = 'export_audit_logs'
    MANAGE_COMPLIANCE = 'manage_compliance'
    
    # System administration
    MANAGE_SETTINGS = 'manage_settings'
    VIEW_SYSTEM_HEALTH = 'view_system_health'


# Role-permission mappings
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    'admin': {
        # Admins have all permissions
        Permissions.MANAGE_USERS,
        Permissions.VIEW_USERS,
        Permissions.CREATE_JOB,
        Permissions.EDIT_JOB,
        Permissions.DELETE_JOB,
        Permissions.VIEW_JOB,
        Permissions.PUBLISH_JOB,
        Permissions.VIEW_APPLICATIONS,
        Permissions.MANAGE_APPLICATIONS,
        Permissions.REVIEW_APPLICATIONS,
        Permissions.VIEW_CANDIDATES,
        Permissions.MANAGE_CANDIDATES,
        Permissions.VIEW_CANDIDATE_PII,
        Permissions.EXPORT_CANDIDATE_DATA,
        Permissions.DELETE_CANDIDATE_DATA,
        Permissions.CREATE_ASSESSMENT,
        Permissions.EDIT_ASSESSMENT,
        Permissions.VIEW_ASSESSMENT,
        Permissions.GRADE_ASSESSMENT,
        Permissions.VIEW_ANALYTICS,
        Permissions.VIEW_COMPANY_ANALYTICS,
        Permissions.EXPORT_REPORTS,
        Permissions.VIEW_AUDIT_LOGS,
        Permissions.EXPORT_AUDIT_LOGS,
        Permissions.MANAGE_COMPLIANCE,
        Permissions.MANAGE_SETTINGS,
        Permissions.VIEW_SYSTEM_HEALTH,
    },
    
    'company': {
        # Company/recruiter permissions
        Permissions.CREATE_JOB,
        Permissions.EDIT_JOB,
        Permissions.DELETE_JOB,
        Permissions.VIEW_JOB,
        Permissions.PUBLISH_JOB,
        Permissions.VIEW_APPLICATIONS,
        Permissions.MANAGE_APPLICATIONS,
        Permissions.REVIEW_APPLICATIONS,
        Permissions.VIEW_CANDIDATES,
        Permissions.VIEW_CANDIDATE_PII,  # Can view PII of applicants
        Permissions.CREATE_ASSESSMENT,
        Permissions.EDIT_ASSESSMENT,
        Permissions.VIEW_ASSESSMENT,
        Permissions.GRADE_ASSESSMENT,
        Permissions.VIEW_ANALYTICS,
        Permissions.VIEW_COMPANY_ANALYTICS,
        Permissions.EXPORT_REPORTS,
        Permissions.VIEW_AUDIT_LOGS,      # Fairness audit access
        Permissions.MANAGE_COMPLIANCE,     # Run fairness audits
    },
    
    'hiring_manager': {
        # Hiring manager permissions (subset of company)
        Permissions.VIEW_JOB,
        Permissions.VIEW_APPLICATIONS,
        Permissions.REVIEW_APPLICATIONS,
        Permissions.VIEW_CANDIDATES,
        Permissions.VIEW_CANDIDATE_PII,
        Permissions.VIEW_ASSESSMENT,
        Permissions.GRADE_ASSESSMENT,
        Permissions.VIEW_COMPANY_ANALYTICS,
    },
    
    'recruiter': {
        # Recruiter permissions
        Permissions.CREATE_JOB,
        Permissions.EDIT_JOB,
        Permissions.VIEW_JOB,
        Permissions.PUBLISH_JOB,
        Permissions.VIEW_APPLICATIONS,
        Permissions.MANAGE_APPLICATIONS,
        Permissions.REVIEW_APPLICATIONS,
        Permissions.VIEW_CANDIDATES,
        Permissions.VIEW_CANDIDATE_PII,
        Permissions.CREATE_ASSESSMENT,
        Permissions.EDIT_ASSESSMENT,
        Permissions.VIEW_ASSESSMENT,
        Permissions.GRADE_ASSESSMENT,
        Permissions.VIEW_ANALYTICS,
        Permissions.VIEW_COMPANY_ANALYTICS,
        Permissions.EXPORT_REPORTS,
        Permissions.VIEW_AUDIT_LOGS,      # Fairness audit access
        Permissions.MANAGE_COMPLIANCE,     # Run fairness audits
    },
    
    'candidate': {
        # Candidate permissions
        Permissions.VIEW_JOB,
        Permissions.VIEW_ASSESSMENT,
        Permissions.VIEW_ANALYTICS,  # Own analytics only
    },
    
    'auditor': {
        # Auditor permissions (read-only compliance role)
        Permissions.VIEW_USERS,
        Permissions.VIEW_JOB,
        Permissions.VIEW_APPLICATIONS,
        Permissions.VIEW_CANDIDATES,
        Permissions.VIEW_ASSESSMENT,
        Permissions.VIEW_ANALYTICS,
        Permissions.VIEW_COMPANY_ANALYTICS,
        Permissions.VIEW_AUDIT_LOGS,
        Permissions.EXPORT_AUDIT_LOGS,
        Permissions.EXPORT_REPORTS,
    }
}


class RBACManager:
    """Manages role-based access control"""
    
    @staticmethod
    def get_role_permissions(role: str) -> Set[str]:
        """
        Get all permissions for a role
        
        Args:
            role: Role name
        
        Returns:
            Set of permission strings
        """
        return ROLE_PERMISSIONS.get(role, set())
    
    @staticmethod
    def has_permission(role: str, permission: str) -> bool:
        """
        Check if a role has a specific permission
        
        Args:
            role: Role name
            permission: Permission to check
        
        Returns:
            True if role has permission
        """
        permissions = RBACManager.get_role_permissions(role)
        return permission in permissions
    
    @staticmethod
    def has_any_permission(role: str, permissions: List[str]) -> bool:
        """
        Check if a role has any of the specified permissions
        
        Args:
            role: Role name
            permissions: List of permissions
        
        Returns:
            True if role has at least one permission
        """
        role_permissions = RBACManager.get_role_permissions(role)
        return any(perm in role_permissions for perm in permissions)
    
    @staticmethod
    def has_all_permissions(role: str, permissions: List[str]) -> bool:
        """
        Check if a role has all specified permissions
        
        Args:
            role: Role name
            permissions: List of permissions
        
        Returns:
            True if role has all permissions
        """
        role_permissions = RBACManager.get_role_permissions(role)
        return all(perm in role_permissions for perm in permissions)


def require_permission(permission: str, allow_self: bool = False):
    """
    Decorator to require a specific permission
    
    Args:
        permission: Required permission
        allow_self: Allow access if user is accessing their own resource
    
    Usage:
        @require_permission(Permissions.VIEW_CANDIDATES)
        def get_candidates():
            ...
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request()
                
                # Get user identity from JWT
                from backend.models.database import get_db
                db = get_db()
                
                current_user_id = get_jwt_identity()
                
                # Handle both string and dict JWT identity formats
                if isinstance(current_user_id, dict):
                    user_id_str = current_user_id.get('user_id', '')
                else:
                    user_id_str = str(current_user_id)
                
                users = db['users']
                # Try ObjectId lookup first, then string fallback
                user = None
                try:
                    user = users.find_one({'_id': ObjectId(user_id_str)})
                except Exception:
                    user = users.find_one({'_id': user_id_str})
                
                if not user:
                    return jsonify({'error': 'User not found'}), 404
                
                user_role = user.get('role', 'candidate')
                
                # Check if user has permission
                if RBACManager.has_permission(user_role, permission):
                    return fn(*args, **kwargs)
                
                # Check allow_self condition
                if allow_self:
                    # Extract resource_id from kwargs or args
                    resource_id = kwargs.get('user_id') or kwargs.get('candidate_id')
                    if resource_id and str(resource_id) == str(user_id_str):
                        return fn(*args, **kwargs)
                
                logger.warning(
                    f"Permission denied: User {user_id_str} (role: {user_role}) "
                    f"attempted to access {permission}"
                )
                
                return jsonify({
                    'error': 'Permission denied',
                    'message': f'You do not have the required permission: {permission}'
                }), 403
                
            except Exception as e:
                logger.error(f"RBAC error: {e}")
                return jsonify({'error': 'Authorization error'}), 500
        
        return wrapper
    return decorator


def require_any_permission(permissions: List[str]):
    """
    Decorator to require any of the specified permissions
    
    Args:
        permissions: List of permissions (user needs at least one)
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request()
                
                from backend.models.database import get_db
                db = get_db()
                
                current_user_id = get_jwt_identity()
                
                # Handle both string and dict JWT identity formats
                if isinstance(current_user_id, dict):
                    user_id_str = current_user_id.get('user_id', '')
                else:
                    user_id_str = str(current_user_id)
                
                users = db['users']
                user = None
                try:
                    user = users.find_one({'_id': ObjectId(user_id_str)})
                except Exception:
                    user = users.find_one({'_id': user_id_str})
                
                if not user:
                    return jsonify({'error': 'User not found'}), 404
                
                user_role = user.get('role', 'candidate')
                
                if RBACManager.has_any_permission(user_role, permissions):
                    return fn(*args, **kwargs)
                
                logger.warning(
                    f"Permission denied: User {user_id_str} (role: {user_role}) "
                    f"attempted to access resource requiring: {permissions}"
                )
                
                return jsonify({
                    'error': 'Permission denied',
                    'message': 'You do not have the required permissions'
                }), 403
                
            except Exception as e:
                logger.error(f"RBAC error: {e}")
                return jsonify({'error': 'Authorization error'}), 500
        
        return wrapper
    return decorator


def require_role(allowed_roles: List[str]):
    """
    Decorator to require specific roles
    
    Args:
        allowed_roles: List of allowed role names
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request()
                
                from backend.models.database import get_db
                db = get_db()
                
                current_user_id = get_jwt_identity()
                
                # Handle both string and dict JWT identity formats
                if isinstance(current_user_id, dict):
                    user_id_str = current_user_id.get('user_id', '')
                else:
                    user_id_str = str(current_user_id)
                
                users = db['users']
                user = None
                try:
                    user = users.find_one({'_id': ObjectId(user_id_str)})
                except Exception:
                    user = users.find_one({'_id': user_id_str})
                
                if not user:
                    return jsonify({'error': 'User not found'}), 404
                
                user_role = user.get('role', 'candidate')
                
                if user_role in allowed_roles:
                    return fn(*args, **kwargs)
                
                logger.warning(
                    f"Role check failed: User {user_id_str} (role: {user_role}) "
                    f"attempted to access resource requiring roles: {allowed_roles}"
                )
                
                return jsonify({
                    'error': 'Access denied',
                    'message': f'This resource requires one of: {", ".join(allowed_roles)}'
                }), 403
                
            except Exception as e:
                logger.error(f"Role check error: {e}")
                return jsonify({'error': 'Authorization error'}), 500
        
        return wrapper
    return decorator
