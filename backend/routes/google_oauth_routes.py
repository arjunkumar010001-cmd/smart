"""
Google OAuth 2.0 Authentication Routes for Job Seekers
Allows candidates to sign in/sign up using their Google account
"""

from flask import Blueprint, request, jsonify, redirect, session, current_app
from flask_jwt_extended import create_access_token
from datetime import datetime, timedelta
from bson import ObjectId
import os
import requests
import secrets
import logging
import hashlib

from backend.models.database import get_db
from backend.models.user import User, Candidate
from backend.utils.email_service import email_service
from backend.security.encryption import decrypt_pii_fields

logger = logging.getLogger(__name__)
bp = Blueprint('google_oauth', __name__)

# Google OAuth endpoints (these are constant)
GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'


def get_google_client_id():
    """Get Google Client ID at runtime"""
    return os.getenv('GOOGLE_CLIENT_ID', '')


def get_google_client_secret():
    """Get Google Client Secret at runtime"""
    return os.getenv('GOOGLE_CLIENT_SECRET', '')


def get_google_redirect_uri():
    """Get Google Redirect URI at runtime"""
    return os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/api/auth/google/callback')


def get_frontend_url():
    """Get Frontend URL at runtime"""
    return os.getenv('FRONTEND_URL', 'http://localhost:5000')


def is_google_oauth_configured():
    """Check if Google OAuth is properly configured"""
    client_id = get_google_client_id()
    client_secret = get_google_client_secret()
    return bool(client_id and client_secret and 
                'your-' not in client_id and 
                'your-' not in client_secret)


@bp.route('/google/status', methods=['GET'])
def google_oauth_status():
    """Check if Google OAuth is available"""
    configured = is_google_oauth_configured()
    return jsonify({
        'google_oauth_available': configured,
        'message': 'Google OAuth is configured and ready' if configured else 'Google OAuth not configured - set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env'
    }), 200


@bp.route('/google/login', methods=['GET'])
def google_login():
    """
    Initiate Google OAuth flow for job seekers
    Returns the Google authorization URL for the frontend to redirect to
    """
    if not is_google_oauth_configured():
        return jsonify({
            'error': 'Google OAuth not configured',
            'message': 'Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env file'
        }), 503
    
    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store state in session (or you can use Redis/database for distributed systems)
    # For stateless API, we'll encode it in the response
    
    # Build authorization URL
    params = {
        'client_id': get_google_client_id(),
        'redirect_uri': get_google_redirect_uri(),
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'offline',
        'state': state,
        'prompt': 'select_account'  # Always show account selector
    }
    
    auth_url = f"{GOOGLE_AUTH_URL}?" + "&".join(f"{k}={v}" for k, v in params.items())
    
    logger.info(f"🔐 Google OAuth initiated, redirecting to Google")
    
    return jsonify({
        'auth_url': auth_url,
        'state': state,
        'message': 'Redirect user to auth_url for Google sign-in'
    }), 200


@bp.route('/google/callback', methods=['GET', 'POST'])
def google_callback():
    """
    Handle Google OAuth callback
    Exchange authorization code for tokens and create/login user
    """
    if not is_google_oauth_configured():
        return jsonify({'error': 'Google OAuth not configured'}), 503
    
    # Get authorization code from query params (GET) or body (POST)
    if request.method == 'GET':
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
    else:
        data = request.get_json() or {}
        code = data.get('code')
        state = data.get('state')
        error = data.get('error')
    
    if error:
        logger.error(f"❌ Google OAuth error: {error}")
        # Redirect to frontend with error
        return redirect(f"{get_frontend_url()}/login?error=google_auth_failed&message={error}")
    
    if not code:
        return jsonify({'error': 'Authorization code not provided'}), 400
    
    try:
        # Exchange code for tokens
        token_data = {
            'client_id': get_google_client_id(),
            'client_secret': get_google_client_secret(),
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': get_google_redirect_uri()
        }
        
        logger.info("🔄 Exchanging authorization code for tokens...")
        token_response = requests.post(GOOGLE_TOKEN_URL, data=token_data, timeout=10)
        
        if token_response.status_code != 200:
            logger.error(f"❌ Token exchange failed: {token_response.text}")
            return redirect(f"{get_frontend_url()}/login?error=token_exchange_failed")
        
        tokens = token_response.json()
        access_token = tokens.get('access_token')
        
        if not access_token:
            return redirect(f"{get_frontend_url()}/login?error=no_access_token")
        
        # Get user info from Google
        logger.info("👤 Fetching user info from Google...")
        headers = {'Authorization': f'Bearer {access_token}'}
        userinfo_response = requests.get(GOOGLE_USERINFO_URL, headers=headers, timeout=10)
        
        if userinfo_response.status_code != 200:
            logger.error(f"❌ Failed to get user info: {userinfo_response.text}")
            return redirect(f"{get_frontend_url()}/login?error=userinfo_failed")
        
        google_user = userinfo_response.json()
        
        email = google_user.get('email')
        full_name = google_user.get('name', '')
        google_id = google_user.get('sub')  # Google's unique user ID
        picture = google_user.get('picture', '')
        email_verified = google_user.get('email_verified', False)
        
        if not email:
            return redirect(f"{get_frontend_url()}/login?error=no_email")
        
        logger.info(f"✅ Google user info: {email}, verified: {email_verified}")
        
        # Check if user exists in database
        db = get_db()
        users_collection = db['users']
        
        # Try encrypted lookup first, then plaintext fallback
        email_hash = hashlib.sha256(email.lower().strip().encode()).hexdigest()
        existing_user = users_collection.find_one({'email_hash': email_hash})
        if existing_user:
            existing_user = decrypt_pii_fields(existing_user)
        else:
            existing_user = users_collection.find_one({'email': email})
        
        if existing_user:
            # User exists - log them in
            user_id = str(existing_user['_id'])
            role = existing_user.get('role', 'candidate')
            
            # Update Google ID if not set
            if not existing_user.get('google_id'):
                users_collection.update_one(
                    {'_id': existing_user['_id']},
                    {'$set': {
                        'google_id': google_id,
                        'profile_picture': picture or existing_user.get('profile_picture', ''),
                        'last_login': datetime.utcnow(),
                        'email_verified': True  # Google verified the email
                    }}
                )
            
            logger.info(f"✅ Existing user logged in via Google: {email}")
            is_new_user = False
            
        else:
            # New user - create account as candidate (job seeker)
            role = 'candidate'
            
            new_user = {
                'email': email,
                'password_hash': None,  # No password for Google OAuth users
                'role': role,
                'full_name': full_name,
                'google_id': google_id,
                'profile_picture': picture,
                'phone': '',
                'linkedin_url': '',
                'github_url': '',
                'is_active': True,
                'email_verified': True,  # Google verified
                'auth_provider': 'google',
                'created_at': datetime.utcnow(),
                'last_login': datetime.utcnow()
            }
            
            result = users_collection.insert_one(new_user)
            user_id = str(result.inserted_id)
            
            # Create candidate profile
            candidates_collection = db['candidates']
            candidate_profile = {
                'user_id': user_id,
                'skills': [],
                'experience': [],
                'education': [],
                'resume_url': '',
                'applications': [],
                'created_at': datetime.utcnow()
            }
            candidates_collection.insert_one(candidate_profile)
            
            logger.info(f"✅ New user created via Google OAuth: {email}")
            is_new_user = True
            
            # Send welcome email
            try:
                email_service.send_welcome_email(email, full_name, role)
            except Exception as e:
                logger.warning(f"⚠️ Welcome email failed: {e}")
        
        # Generate JWT token
        jwt_token = create_access_token(
            identity=user_id,
            additional_claims={'role': role, 'auth_provider': 'google'}
        )
        
        # SECURITY FIX: Use a short-lived auth code instead of sending JWT in URL
        # Store jwt_token in a temporary auth code in the database (30 second TTL)
        auth_code = secrets.token_urlsafe(48)
        db['oauth_auth_codes'].insert_one({
            'code': auth_code,
            'jwt_token': jwt_token,
            'user_id': user_id,
            'role': role,
            'is_new': is_new_user,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(seconds=60),
            'used': False
        })
        # Create TTL index on first run (MongoDB will auto-expire documents)
        try:
            db['oauth_auth_codes'].create_index('expires_at', expireAfterSeconds=0)
        except Exception:
            pass  # Index already exists
        
        # Redirect to frontend with only the short-lived auth code (not the JWT)
        redirect_url = f"{get_frontend_url()}/oauth/callback?code={auth_code}&is_new={is_new_user}"
        
        logger.info(f"🎉 Google OAuth successful for {email}, redirecting to frontend")
        return redirect(redirect_url)
        
    except requests.RequestException as e:
        logger.error(f"❌ Network error during Google OAuth: {e}")
        return redirect(f"{get_frontend_url()}/login?error=network_error")
    except Exception as e:
        logger.error(f"❌ Google OAuth error: {e}")
        import traceback
        traceback.print_exc()
        return redirect(f"{get_frontend_url()}/login?error=server_error")


@bp.route('/google/exchange', methods=['POST'])
def exchange_auth_code():
    """
    Exchange a short-lived auth code for a JWT token.
    This is the secure second step of the OAuth flow.
    The frontend sends the auth code received from the redirect,
    and receives the JWT token in the response body (not in URL).
    """
    data = request.get_json()
    code = data.get('code')
    
    if not code:
        return jsonify({'error': 'Auth code not provided'}), 400
    
    try:
        db = get_db()
        # Find and consume the auth code (one-time use)
        auth_record = db['oauth_auth_codes'].find_one_and_update(
            {
                'code': code,
                'used': False,
                'expires_at': {'$gt': datetime.utcnow()}
            },
            {'$set': {'used': True, 'used_at': datetime.utcnow()}}
        )
        
        if not auth_record:
            return jsonify({'error': 'Invalid or expired auth code'}), 401
        
        # Fetch the full user object so the frontend has displayable data
        from bson import ObjectId
        user_doc = db['users'].find_one({'_id': ObjectId(auth_record['user_id'])})
        user_info = {
            'id': auth_record['user_id'],
            'email': user_doc.get('email', '') if user_doc else '',
            'full_name': user_doc.get('full_name', '') if user_doc else '',
            'role': auth_record['role'],
            'profile_picture': user_doc.get('profile_picture', '') if user_doc else '',
            'auth_provider': 'google'
        }
        
        return jsonify({
            'message': 'Authentication successful',
            'access_token': auth_record['jwt_token'],
            'user': user_info,
            'user_id': auth_record['user_id'],
            'role': auth_record['role'],
            'is_new_user': auth_record.get('is_new', False)
        }), 200
        
    except Exception as e:
        logger.error(f"Auth code exchange error: {e}")
        return jsonify({'error': 'Authentication failed'}), 500


@bp.route('/google/token', methods=['POST'])
def google_token_auth():
    """
    Alternative: Authenticate with Google ID token directly from frontend
    This is useful when frontend handles the OAuth flow
    """
    if not is_google_oauth_configured():
        return jsonify({'error': 'Google OAuth not configured'}), 503
    
    data = request.get_json()
    id_token = data.get('id_token') or data.get('credential')
    
    if not id_token:
        return jsonify({'error': 'ID token not provided'}), 400
    
    try:
        # Verify the ID token with Google
        verify_url = f'https://oauth2.googleapis.com/tokeninfo?id_token={id_token}'
        response = requests.get(verify_url, timeout=10)
        
        if response.status_code != 200:
            return jsonify({'error': 'Invalid ID token'}), 401
        
        token_info = response.json()
        
        # Verify the token is for our app
        if token_info.get('aud') != get_google_client_id():
            return jsonify({'error': 'Token not intended for this application'}), 401
        
        email = token_info.get('email')
        full_name = token_info.get('name', '')
        google_id = token_info.get('sub')
        picture = token_info.get('picture', '')
        
        if not email:
            return jsonify({'error': 'Email not provided by Google'}), 400
        
        # Find or create user (same logic as callback)
        db = get_db()
        users_collection = db['users']
        
        # Try encrypted lookup first, then plaintext fallback
        email_hash = hashlib.sha256(email.lower().strip().encode()).hexdigest()
        existing_user = users_collection.find_one({'email_hash': email_hash})
        if existing_user:
            existing_user = decrypt_pii_fields(existing_user)
        else:
            existing_user = users_collection.find_one({'email': email})
        
        if existing_user:
            user_id = str(existing_user['_id'])
            role = existing_user.get('role', 'candidate')
            is_new_user = False
            
            # Update last login
            users_collection.update_one(
                {'_id': existing_user['_id']},
                {'$set': {'last_login': datetime.utcnow()}}
            )
        else:
            # Create new candidate user
            role = 'candidate'
            new_user = {
                'email': email,
                'password_hash': None,
                'role': role,
                'full_name': full_name,
                'google_id': google_id,
                'profile_picture': picture,
                'phone': '',
                'is_active': True,
                'email_verified': True,
                'auth_provider': 'google',
                'created_at': datetime.utcnow(),
                'last_login': datetime.utcnow()
            }
            
            result = users_collection.insert_one(new_user)
            user_id = str(result.inserted_id)
            
            # Create candidate profile
            candidates_collection = db['candidates']
            candidates_collection.insert_one({
                'user_id': user_id,
                'skills': [],
                'experience': [],
                'education': [],
                'applications': [],
                'created_at': datetime.utcnow()
            })
            
            is_new_user = True
            
            # Send welcome email
            try:
                email_service.send_welcome_email(email, full_name, role)
            except Exception as e:
                logger.warning(f"Welcome email failed: {e}")
        
        # Generate JWT
        jwt_token = create_access_token(
            identity=user_id,
            additional_claims={'role': role, 'auth_provider': 'google'}
        )
        
        return jsonify({
            'message': 'Google authentication successful',
            'access_token': jwt_token,
            'user_id': user_id,
            'is_new_user': is_new_user,
            'user': {
                'email': email,
                'full_name': full_name,
                'role': role,
                'profile_picture': picture
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Google token auth error: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/google/disconnect', methods=['POST'])
def google_disconnect():
    """
    Disconnect Google account - allows user to set a password
    Only works if user was created via Google OAuth
    """
    from flask_jwt_extended import jwt_required, get_jwt_identity
    from flask_bcrypt import Bcrypt
    
    bcrypt = Bcrypt()
    
    @jwt_required()
    def disconnect():
        user_id = get_jwt_identity()
        data = request.get_json()
        new_password = data.get('password')
        
        if not new_password or len(new_password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        
        db = get_db()
        users_collection = db['users']
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.get('auth_provider') != 'google':
            return jsonify({'error': 'Account not linked with Google'}), 400
        
        # Set password and update auth provider
        password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {
                'password_hash': password_hash,
                'auth_provider': 'local',
                'google_id': user.get('google_id')  # Keep Google ID for potential re-linking
            }}
        )
        
        return jsonify({
            'message': 'Google account disconnected. You can now login with email and password.'
        }), 200
    
    return disconnect()
