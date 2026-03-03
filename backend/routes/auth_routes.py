from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
from bson import ObjectId
import re
import secrets
import hashlib
import os
import logging

from backend.models.database import get_db
from backend.models.user import User, Candidate
from backend.utils.sanitizer import sanitizer
from backend.utils.rate_limiter import rate_limit
from backend.utils.email_service import email_service
from backend.tasks.email_tasks import send_verification_email
from backend.security.encryption import decrypt_pii_fields

logger = logging.getLogger(__name__)
bp = Blueprint('auth', __name__)
bcrypt = Bcrypt()


def find_user_by_email(users_collection, email):
    """Find user by email, supporting both encrypted (email_hash) and plaintext storage."""
    email_lower = email.lower().strip()
    # Try encrypted lookup via email_hash first
    email_hash = hashlib.sha256(email_lower.encode()).hexdigest()
    user = users_collection.find_one({'email_hash': email_hash})
    if user:
        return decrypt_pii_fields(user)
    # Fallback: plaintext email (legacy / seed accounts)
    user = users_collection.find_one({'email': email_lower})
    return user

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@bp.route('/register', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=3600)  # 10 registrations per hour
def register():
    """Register a new user (candidate or recruiter)"""
    try:
        print("📝 Registration attempt started")
        data = request.get_json()
        print(f"📥 Received registration data: {data}")
        
        # Validate required fields
        required_fields = ['email', 'password', 'full_name', 'role']
        for field in required_fields:
            if field not in data:
                print(f"❌ Missing field: {field}")
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Validate and sanitize email
        email = sanitizer.sanitize_email(data.get('email', ''))
        if not email:
            print("❌ Invalid email format after sanitization")
            return jsonify({'error': 'Invalid email format'}), 400
        
        password = data['password']
        full_name = data['full_name'].strip()
        role = data['role'].lower()
        
        # Map 'company' to 'recruiter' if sent
        if role == 'company':
            role = 'recruiter'
        
        print(f"📧 Email: {email}, Role: {role}")
        
        # Validate email
        if not validate_email(email):
            print("❌ Email validation failed")
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Validate role - Only candidate and recruiter allowed via registration
        # Admin accounts must be created by existing admins or via CLI
        if role not in ['candidate', 'recruiter']:
            print(f"❌ Invalid role: {role}")
            return jsonify({'error': 'Invalid role. Must be candidate or recruiter'}), 400
        
        # Validate password strength (minimum 8 chars, complexity requirements)
        if len(password) < 8:
            print("❌ Password too short")
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        
        # Check password complexity
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        
        if not (has_upper and has_lower and has_digit):
            print("❌ Password complexity failed")
            return jsonify({'error': 'Password must contain uppercase, lowercase, and numbers'}), 400
        
        print("✅ Validation passed, connecting to database...")
        db = get_db()
        users_collection = db['users']
        
        # Check if user already exists
        print(f"🔍 Checking if email exists: {email}")
        existing_user = find_user_by_email(users_collection, email)
        if existing_user:
            print(f"❌ Email already registered: {email}")
            return jsonify({'error': 'Email already registered'}), 409
        
        print("🔒 Hashing password...")
        # Hash password
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # P0 FIX: Generate email verification token
        verification_token = secrets.token_urlsafe(32)
        verification_token_hash = hashlib.sha256(verification_token.encode()).hexdigest()
        verification_expires = datetime.utcnow() + timedelta(hours=24)
        
        print("👤 Creating user object...")
        
        # P0 FIX: Check environment for dev mode auto-activation
        flask_env = os.getenv('FLASK_ENV', 'production')
        is_dev_mode = flask_env == 'development'
        
        # Create user - auto-activate in dev mode, otherwise require email verification
        user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            full_name=full_name,
            phone=data.get('phone', ''),
            linkedin_url=data.get('linkedin_url', ''),
            github_url=data.get('github_url', ''),
            is_active=is_dev_mode  # DEV MODE: auto-activate, PROD: require email verification
        )
        
        # P0 FIX: Add verification fields to user document
        user_dict = user.to_dict()
        user_dict['email_verified'] = is_dev_mode  # Auto-verify in dev mode
        user_dict['verification_token'] = verification_token_hash
        user_dict['verification_expires'] = verification_expires
        
        # ALWAYS print verification URL to console for testing
        base_url = os.getenv('FRONTEND_URL', 'http://localhost:5000')
        verification_url = f"{base_url}/api/auth/verify-email?token={verification_token}&email={email}"
        print(f"\n{'='*60}")
        print(f"🔗 VERIFICATION URL (for testing):")
        print(f"   {verification_url}")
        if is_dev_mode:
            print(f"   ✅ DEV MODE: User auto-activated, no verification needed")
        print(f"{'='*60}\n")
        
        print("💾 Inserting user into database...")
        result = users_collection.insert_one(user_dict)
        user_id = str(result.inserted_id)
        print(f"✅ User created with ID: {user_id}")
        
        # If candidate, create candidate profile
        if role == 'candidate':
            print("📄 Creating candidate profile...")
            candidates_collection = db['candidates']
            candidate = Candidate(user_id=user_id)
            candidates_collection.insert_one(candidate.to_dict())
            print("✅ Candidate profile created")
        
        print("🎫 Generating access token...")
        # Generate JWT token - identity is always a string (user_id), role in additional_claims
        access_token = create_access_token(
            identity=user_id,
            additional_claims={'role': role}
        )
        
        # P0 FIX: Send verification email AND welcome email
        verification_email_sent = False
        welcome_email_sent = False
        try:
            # Priority 1: Try Async Verification Email via Celery
            task = send_verification_email.delay(email, full_name, verification_token)
            verification_email_sent = True
            logger.info(f"✅ Verification email task dispatched for {email} (Task ID: {task.id})")
        except Exception as celery_error:
            logger.warning(f"⚠️ Celery not available, sending verification email synchronously: {celery_error}")
            try:
                verification_email_sent = email_service.send_email_verification(email, full_name, verification_token)
            except Exception as sync_error:
                logger.error(f"❌ Sync verification email also failed: {sync_error}")
        
        # Send welcome email (synchronous)
        try:
            welcome_email_sent = email_service.send_welcome_email(email, full_name, role)
            if welcome_email_sent:
                logger.info(f"✅ Welcome email sent to {email}")
        except Exception as welcome_error:
            logger.error(f"❌ Welcome email exception for {email}: {welcome_error}")
        
        print(f"🎉 Registration successful for {email}")
        return jsonify({
            'message': 'User registered successfully. Please check your email to verify your account.',
            'user_id': user_id,
            'access_token': access_token,
            'email_sent': verification_email_sent or welcome_email_sent,
            'verification_email_sent': verification_email_sent,  # P0 FIX: Report verification status
            'email_verified': False,  # P0 FIX: Explicit verification status
            'user': {
                'email': email,
                'full_name': full_name,
                'role': role,
                'email_verified': False
            }
        }), 201
        
    except Exception as e:
        print(f"❌ Registration error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@bp.route('/login', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=300)  # 5 attempts per 5 minutes
def login():
    """Login user"""
    try:
        print("🔐 Login attempt started")
        data = request.get_json()
        print(f"📥 Received data: {data.get('email', 'no email')} (password hidden)")
        
        if 'email' not in data or 'password' not in data:
            print("❌ Missing email or password")
            return jsonify({'error': 'Email and password required'}), 400
        
        # Sanitize inputs
        print("🧹 Sanitizing email...")
        email = sanitizer.sanitize_email(data['email'])
        if not email:
            print("❌ Email validation failed")
            return jsonify({'error': 'Invalid email format'}), 400
        
        print(f"✅ Email sanitized: {email}")
        password = data['password']
        
        print("🔌 Connecting to database...")
        db = get_db()
        users_collection = db['users']
        
        # Find user
        print(f"🔍 Looking up user: {email}")
        user = find_user_by_email(users_collection, email)
        if not user:
            print("❌ User not found")
            return jsonify({'error': 'Invalid credentials'}), 401
        
        print(f"✅ User found: {user.get('email')} (role: {user.get('role')})")
        
        # Check if password_hash exists
        if 'password_hash' not in user:
            print("❌ No password_hash in user document")
            return jsonify({'error': 'Account configuration error. Please contact administrator.'}), 500
        
        print("🔒 Checking password...")
        # Check password
        if not bcrypt.check_password_hash(user['password_hash'], password):
            print("❌ Password check failed")
            return jsonify({'error': 'Invalid credentials'}), 401
        
        print("✅ Password correct")
        
        # Role mismatch detection (for debugging)
        requested_role = data.get('role')
        actual_role = user.get('role')
        if requested_role and actual_role:
            # Normalize roles for comparison
            normalized_requested = 'recruiter' if requested_role in ['company', 'recruiter'] else requested_role
            normalized_actual = 'recruiter' if actual_role in ['company', 'recruiter'] else actual_role
            
            if normalized_requested != normalized_actual and normalized_requested != 'admin':
                print(f"⚠️ ROLE MISMATCH WARNING: User '{email}' has role '{actual_role}' but tried to login via '{requested_role}' portal")
                print(f"   💡 To fix: Update user's role in database or use the correct portal")
                # Note: We allow login but log the mismatch. The frontend handles portal redirection.
        
        # Check if user is active (email verified)
        if not user.get('is_active', True):
            print("❌ User account is not activated")
            # UX FIX: Provide specific, actionable error message
            return jsonify({
                'error': 'Account not activated. Please check your email to verify your account.',
                'email_verified': user.get('email_verified', False),
                'requires_verification': True
            }), 403
        
        print("🎫 Generating JWT token...")
        # Generate JWT token with user_id as identity and role as additional claim
        access_token = create_access_token(
            identity=str(user['_id']),
            additional_claims={'role': user['role']}
        )
        
        # Send login confirmation email (security alert)
        login_email_sent = False
        try:
            from datetime import datetime
            login_time = datetime.now().strftime('%B %d, %Y at %I:%M %p UTC')
            ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
            device_info = request.headers.get('User-Agent', 'Unknown device')[:100]
            
            login_email_sent = email_service.send_login_confirmation(
                to_email=user['email'],
                user_name=user['full_name'],
                login_time=login_time,
                ip_address=ip_address,
                device_info=device_info
            )
            if login_email_sent:
                logger.info(f"✅ Login confirmation email sent to {user['email']}")
            else:
                logger.warning(f"⚠️ Login confirmation email NOT sent to {user['email']}")
        except Exception as email_error:
            logger.error(f"❌ Login email exception: {email_error}")
        
        print("✅ Login successful!")
        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'login_email_sent': login_email_sent,
            'user': {
                'user_id': str(user['_id']),
                'email': user['email'],
                'full_name': user['full_name'],
                'role': user['role'],
                'profile_completed': user.get('profile_completed', False)
            }
        }), 200
        
    except KeyError as e:
        # Specific handling for missing keys
        print(f"KeyError in login: {str(e)}")
        return jsonify({'error': f'Account data error: missing {str(e)}'}), 500
    except Exception as e:
        # General exception handling
        print(f"Login error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Login failed. Please try again.'}), 500

@bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get current user profile"""
    try:
        current_user = get_jwt_identity()
        # Handle both string and dict identity formats
        user_id = current_user if isinstance(current_user, str) else current_user.get('user_id', current_user)
        
        db = get_db()
        users_collection = db['users']
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # P0 FIX: Remove ALL sensitive data before returning
        user['_id'] = str(user['_id'])
        
        # List of sensitive fields that should NEVER be returned
        sensitive_fields = [
            'password_hash',
            'reset_token',
            'reset_token_expires',
            'verification_token',
            'verification_expires',
            'otp_secret',
            'two_factor_secret'
        ]
        for field in sensitive_fields:
            if field in user:
                del user[field]
        
        return jsonify(user), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/forgot-password', methods=['POST'])
@rate_limit(max_requests=3, window_seconds=3600)  # 3 requests per hour
def forgot_password():
    """Request password reset - generates reset token"""
    try:
        data = request.get_json()
        
        if 'email' not in data:
            return jsonify({'error': 'Email is required'}), 400
        
        email = data['email'].lower().strip()
        
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        db = get_db()
        users_collection = db['users']
        
        # Check if user exists
        user = find_user_by_email(users_collection, email)
        
        if not user:
            # Return success even if user doesn't exist (security best practice)
            return jsonify({
                'message': 'If an account exists with this email, a password reset link has been sent',
                'note': 'Email functionality not configured - use reset token below for testing'
            }), 200
        
        # Generate reset token (valid for 1 hour)
        reset_token = secrets.token_urlsafe(32)
        reset_token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
        reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        
        # Store reset token in database
        users_collection.update_one(
            {'_id': user['_id']},
            {
                '$set': {
                    'reset_token': reset_token_hash,
                    'reset_token_expires': reset_token_expires,
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        # Send password reset email
        base_url = os.getenv('FRONTEND_URL', 'http://localhost:5000')
        reset_link = f"{base_url}/reset-password.html?token={reset_token}&email={email}"
        
        # Send email with reset link
        from backend.utils.email_service import email_service
        email_sent = False
        try:
            email_sent = email_service.send_password_reset_email(
                to_email=email,
                reset_link=reset_link,
                user_name=user.get('full_name', user.get('name', email))
            )
        except Exception as email_error:
            logger.warning(f"Failed to send password reset email: {email_error}")
        
        # Build response with development info if emails are disabled
        response_data = {
            'message': 'If an account exists with this email, password reset instructions have been sent',
            'email_sent': email_sent  # FIX: Always report email status honestly
        }
        
        # FIX: Only expose tokens in DEVELOPMENT environment, NEVER based on DEBUG flag alone
        flask_env = os.getenv('FLASK_ENV', 'production')
        if flask_env == 'development' and not email_sent:
            # Only expose if in dev mode AND email failed
            logger.warning(f"[DEV MODE] Password reset token exposed for {email}")
            response_data['dev_mode'] = True
            response_data['reset_token'] = reset_token
            response_data['reset_link'] = reset_link
            response_data['note'] = 'DEV MODE: Token exposed because email failed. NEVER enable in production.'
        elif not email_sent:
            # Production mode - just warn that email failed
            response_data['warning'] = 'Email delivery may have failed. Contact support if you do not receive the email.'
        
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Reset password using reset token"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['email', 'reset_token', 'new_password']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        email = data['email'].lower().strip()
        reset_token = data['reset_token']
        new_password = data['new_password']
        
        # Validate email
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Validate new password strength (minimum 8 chars, complexity requirements)
        if len(new_password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        
        # Check password complexity
        has_upper = any(c.isupper() for c in new_password)
        has_lower = any(c.islower() for c in new_password)
        has_digit = any(c.isdigit() for c in new_password)
        
        if not (has_upper and has_lower and has_digit):
            return jsonify({'error': 'Password must contain uppercase, lowercase, and numbers'}), 400
        
        db = get_db()
        users_collection = db['users']
        
        # Hash the provided token
        reset_token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
        
        # Find user with matching email and valid reset token
        user = users_collection.find_one({
            'email': email,
            'reset_token': reset_token_hash,
            'reset_token_expires': {'$gt': datetime.utcnow()}
        })
        
        if not user:
            return jsonify({'error': 'Invalid or expired reset token'}), 400
        
        # Hash new password
        new_password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        
        # Update password and clear reset token
        users_collection.update_one(
            {'_id': user['_id']},
            {
                '$set': {
                    'password_hash': new_password_hash,
                    'updated_at': datetime.utcnow()
                },
                '$unset': {
                    'reset_token': '',
                    'reset_token_expires': ''
                }
            }
        )
        
        return jsonify({
            'message': 'Password reset successfully',
            'success': True
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """Change password for logged-in user"""
    try:
        current_user = get_jwt_identity()
        # Handle both string and dict identity formats
        user_id = current_user if isinstance(current_user, str) else current_user.get('user_id', current_user)
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['current_password', 'new_password']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        current_password = data['current_password']
        new_password = data['new_password']
        
        # Validate new password strength (minimum 8 chars, complexity requirements)
        if len(new_password) < 8:
            return jsonify({'error': 'New password must be at least 8 characters'}), 400
        
        # Check password complexity
        has_upper = any(c.isupper() for c in new_password)
        has_lower = any(c.islower() for c in new_password)
        has_digit = any(c.isdigit() for c in new_password)
        
        if not (has_upper and has_lower and has_digit):
            return jsonify({'error': 'Password must contain uppercase, lowercase, and numbers'}), 400
        
        if current_password == new_password:
            return jsonify({'error': 'New password must be different from current password'}), 400
        
        db = get_db()
        users_collection = db['users']
        
        # Get user
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Verify current password
        if not bcrypt.check_password_hash(user['password_hash'], current_password):
            return jsonify({'error': 'Current password is incorrect'}), 401
        
        # Hash new password
        new_password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        
        # Update password
        users_collection.update_one(
            {'_id': user['_id']},
            {
                '$set': {
                    'password_hash': new_password_hash,
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        return jsonify({
            'message': 'Password changed successfully',
            'success': True
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """Update user profile"""
    try:
        current_user = get_jwt_identity()
        # Handle both string and dict identity formats
        user_id = current_user if isinstance(current_user, str) else current_user.get('user_id', current_user)
        data = request.get_json()
        
        db = get_db()
        users_collection = db['users']
        
        # Fields that can be updated
        allowed_fields = ['full_name', 'phone', 'linkedin_url', 'github_url']
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        update_data['updated_at'] = datetime.utcnow()
        
        result = users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': update_data}
        )
        
        if result.modified_count > 0:
            return jsonify({'message': 'Profile updated successfully'}), 200
        else:
            return jsonify({'message': 'No changes made'}), 200
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# P0 FIX: EMAIL VERIFICATION ENDPOINTS
# =============================================================================

@bp.route('/verify-email', methods=['GET'])
def verify_email():
    """
    P0 FIX: Verify user's email address using token
    
    Query params:
        token: Verification token from email
        email: User's email address
    """
    try:
        token = request.args.get('token')
        email = request.args.get('email', '').lower().strip()
        
        if not token or not email:
            return jsonify({'error': 'Token and email are required'}), 400
        
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        db = get_db()
        users_collection = db['users']
        
        # Hash the provided token
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        # Find user with matching email and valid verification token
        email_hash_val = hashlib.sha256(email.encode()).hexdigest()
        user = users_collection.find_one({
            'email_hash': email_hash_val,
            'verification_token': token_hash,
            'verification_expires': {'$gt': datetime.utcnow()}
        })
        if not user:
            # Fallback: try plaintext email (legacy records)
            user = users_collection.find_one({
                'email': email,
                'verification_token': token_hash,
                'verification_expires': {'$gt': datetime.utcnow()}
            })
        if user:
            user = decrypt_pii_fields(user)
        
        if not user:
            # Check if email is already verified
            existing_user = find_user_by_email(users_collection, email)
            if existing_user and existing_user.get('email_verified'):
                return jsonify({
                    'message': 'Email already verified',
                    'email_verified': True
                }), 200
            return jsonify({'error': 'Invalid or expired verification token'}), 400
        
        # Mark email as verified and remove verification token
        users_collection.update_one(
            {'_id': user['_id']},
            {
                '$set': {
                    'email_verified': True,
                    'is_active': True,  # Priority 1: Activate user
                    'email_verified_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                },
                '$unset': {
                    'verification_token': '',
                    'verification_expires': ''
                }
            }
        )
        
        logger.info(f"✅ Email verified for user: {email}")
        
        return jsonify({
            'message': 'Email verified successfully! You can now access all features.',
            'email_verified': True,
            'success': True
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Email verification error: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/resend-verification', methods=['POST'])
@rate_limit(max_requests=3, window_seconds=3600)  # 3 requests per hour
def resend_verification():
    """
    P0 FIX: Resend email verification link
    """
    try:
        data = request.get_json()
        
        if 'email' not in data:
            return jsonify({'error': 'Email is required'}), 400
        
        email = data['email'].lower().strip()
        
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        db = get_db()
        users_collection = db['users']
        
        # Find user
        user = find_user_by_email(users_collection, email)
        
        if not user:
            # Security: Don't reveal if email exists
            return jsonify({
                'message': 'If an account exists with this email, a verification link has been sent'
            }), 200
        
        # Check if already verified
        if user.get('email_verified'):
            return jsonify({
                'message': 'Email is already verified',
                'email_verified': True
            }), 200
        
        # Generate new verification token
        verification_token = secrets.token_urlsafe(32)
        verification_token_hash = hashlib.sha256(verification_token.encode()).hexdigest()
        verification_expires = datetime.utcnow() + timedelta(hours=24)
        
        # Update user with new token
        users_collection.update_one(
            {'_id': user['_id']},
            {
                '$set': {
                    'verification_token': verification_token_hash,
                    'verification_expires': verification_expires,
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        # Send verification email
        email_sent = email_service.send_email_verification(
            email, 
            user.get('full_name', 'User'), 
            verification_token
        )
        
        return jsonify({
            'message': 'If an account exists with this email, a verification link has been sent',
            'email_sent': email_sent
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Resend verification error: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/email-metrics', methods=['GET'])
@jwt_required()
def get_email_metrics():
    """
    P0 FIX: Get email sending metrics (admin only)
    """
    try:
        current_user = get_jwt_identity()
        
        # Check if admin
        if isinstance(current_user, dict):
            role = current_user.get('role')
        else:
            db = get_db()
            user = db['users'].find_one({'_id': ObjectId(current_user)})
            role = user.get('role') if user else None
        
        if role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        metrics = email_service.get_metrics()
        
        return jsonify({
            'email_metrics': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# FRAUD REPORT & ACCOUNT SECURITY ENDPOINTS
# =============================================================================

@bp.route('/report-fraud', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=3600)
def report_fraud():
    """
    Report suspicious/unauthorized activity on account.
    
    This endpoint:
    1. Accepts fraud reports from users (authenticated or via email)
    2. Temporarily locks the account for security
    3. Sends a confirmation email to the account holder
    4. Logs the incident for admin review
    
    Body:
        email: User's email address
        report_type: 'unauthorized_login' | 'unauthorized_application' | 'account_compromise' | 'other'
        details: Optional description of the suspicious activity
    """
    try:
        data = request.get_json()
        
        if not data or 'email' not in data:
            return jsonify({'error': 'Email is required'}), 400
        
        email = data['email'].lower().strip()
        report_type = data.get('report_type', 'suspicious_activity')
        details = data.get('details', '')
        
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        db = get_db()
        users_collection = db['users']
        
        # Find user
        user = find_user_by_email(users_collection, email)
        
        if not user:
            # Security: Don't reveal if email exists
            return jsonify({
                'message': 'If an account exists with this email, the report has been filed and the account has been secured.'
            }), 200
        
        # Temporarily lock the account
        users_collection.update_one(
            {'_id': user['_id']},
            {
                '$set': {
                    'is_active': False,
                    'account_locked': True,
                    'account_locked_reason': f'Fraud report: {report_type}',
                    'account_locked_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        # Log the fraud report
        fraud_reports_collection = db['fraud_reports']
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        fraud_reports_collection.insert_one({
            'user_id': str(user['_id']),
            'email': email,
            'report_type': report_type,
            'details': details,
            'reporter_ip': ip_address,
            'reporter_user_agent': request.headers.get('User-Agent', 'Unknown')[:200],
            'status': 'pending_review',
            'created_at': datetime.utcnow()
        })
        
        logger.warning(f"🚨 FRAUD REPORT filed for {email} - Type: {report_type} - Account LOCKED")
        
        # Send confirmation email
        try:
            email_service.send_fraud_report_confirmation(
                to_email=email,
                user_name=user.get('full_name', 'User'),
                report_type=report_type,
                report_details=details
            )
        except Exception as email_error:
            logger.error(f"Failed to send fraud report confirmation: {email_error}")
        
        return jsonify({
            'message': 'Fraud report filed successfully. Your account has been temporarily locked for security. Our security team will investigate within 24 hours.',
            'account_locked': True,
            'next_steps': [
                'Your account has been temporarily secured',
                'Reset your password before logging in again',
                'Our security team will review within 24 hours',
                'You will receive an email confirmation'
            ]
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Fraud report error: {e}")
        return jsonify({'error': 'Failed to process fraud report'}), 500


@bp.route('/report-fraud', methods=['GET'])
def report_fraud_page():
    """
    Serve a simple fraud report form (for links in emails).
    Returns JSON with form info - frontend handles the actual form.
    """
    return jsonify({
        'message': 'Report suspicious activity on your Smart Hiring account',
        'required_fields': {
            'email': 'Your registered email address',
            'report_type': 'unauthorized_login | unauthorized_application | account_compromise | other',
            'details': '(Optional) Describe the suspicious activity'
        },
        'endpoint': '/api/auth/report-fraud',
        'method': 'POST'
    }), 200


@bp.route('/unlock-account', methods=['POST'])
@rate_limit(max_requests=3, window_seconds=3600)
def unlock_account():
    """
    Unlock a fraud-locked account after password reset.
    Requires the user to reset their password first, then provide the reset token.
    """
    try:
        data = request.get_json()
        
        required_fields = ['email', 'reset_token', 'new_password']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        email = data['email'].lower().strip()
        reset_token = data['reset_token']
        new_password = data['new_password']
        
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Validate password strength
        if len(new_password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        
        has_upper = any(c.isupper() for c in new_password)
        has_lower = any(c.islower() for c in new_password)
        has_digit = any(c.isdigit() for c in new_password)
        
        if not (has_upper and has_lower and has_digit):
            return jsonify({'error': 'Password must contain uppercase, lowercase, and numbers'}), 400
        
        db = get_db()
        users_collection = db['users']
        
        # Hash the provided token
        reset_token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
        
        # Find locked user with valid reset token
        user = users_collection.find_one({
            'email': email,
            'reset_token': reset_token_hash,
            'reset_token_expires': {'$gt': datetime.utcnow()},
            'account_locked': True
        })
        
        if not user:
            return jsonify({'error': 'Invalid token, email, or account is not locked'}), 400
        
        # Hash new password and unlock
        new_password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        
        users_collection.update_one(
            {'_id': user['_id']},
            {
                '$set': {
                    'password_hash': new_password_hash,
                    'is_active': True,
                    'account_locked': False,
                    'account_unlocked_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                },
                '$unset': {
                    'reset_token': '',
                    'reset_token_expires': '',
                    'account_locked_reason': ''
                }
            }
        )
        
        # Update fraud report status
        db['fraud_reports'].update_many(
            {'email': email, 'status': 'pending_review'},
            {'$set': {'status': 'resolved_by_user', 'resolved_at': datetime.utcnow()}}
        )
        
        logger.info(f"✅ Account unlocked for {email} after password reset")
        
        return jsonify({
            'message': 'Account unlocked and password reset successfully. You can now log in.',
            'success': True
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Unlock account error: {e}")
        return jsonify({'error': str(e)}), 500
