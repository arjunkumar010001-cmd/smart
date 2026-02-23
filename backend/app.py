
"""
Smart Hiring System - Main Application Entry Point
Version: 2.0.0 - Enterprise Edition with Security, Workers, GDPR Compliance
Initializes Flask app with all routes and configurations
© 2025 Smart Hiring System - Proprietary Software - All Rights Reserved
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config.config import config
from backend.models.database import Database
from backend.routes import auth_routes, job_routes, candidate_routes, company_routes, email_preferences_routes, assessment_routes, audit_routes, dsr_routes, dashboard_routes, ai_interview_routes, admin_routes, google_oauth_routes, interview_routes, analytics_routes, llm_routes
from backend.routes import smart_assessment_routes
# Import enhanced v2 routes
try:
    from backend.routes import ai_interview_routes_v2
    V2_ROUTES_AVAILABLE = True
except ImportError:
    V2_ROUTES_AVAILABLE = False
    print("⚠️ V2 routes not available (requires requests-oauthlib). Install with: pip install requests-oauthlib")
    
from backend.utils.license_validator import check_deployment_authorization, require_valid_license
from backend.utils.env_config import env_config, print_startup_banner
from backend.utils.monitoring import initialize_monitoring
from backend.workers.job_processor import start_workers, stop_workers
import atexit
import logging

# Configure logging
logging.basicConfig(
    level=getattr(logging, env_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app(config_name=None):
    """
    Application factory — creates and configures the Flask application.

    Args:
        config_name: One of 'development', 'production', 'testing', or None
                     (defaults to FLASK_ENV env-var, then 'development').

    Returns:
        Configured Flask application instance.
    """
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    # Initialize Flask app with frontend folder
    frontend_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
    flask_app = Flask(__name__, static_folder=frontend_folder, static_url_path='')

    # Load configuration
    flask_app.config.from_object(config[config_name])

    # Initialize extensions
    # SECURITY: Configure CORS properly for production
    allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:5000').split(',')
    CORS(flask_app, 
         resources={r"/api/*": {
             "origins": allowed_origins,
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization"],
             "expose_headers": ["Content-Type", "Authorization"],
             "supports_credentials": True,
             "max_age": 3600
         }})

    # Initialize JWT Manager  
    jwt = JWTManager(flask_app)

    # Security headers
    @flask_app.after_request
    def set_security_headers(response):
        """Add security headers to all responses"""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: https: blob:; "
            "font-src 'self' data: https://fonts.gstatic.com https://fonts.googleapis.com; "
            "connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com https://*.googleapis.com blob:; "
            "media-src 'self' blob:; "
            "frame-src 'self' https://accounts.google.com"
        )
        return response

    # Initialize database connection
    db = Database()
    db.connect(config_name)

    # Auto-create test accounts on startup (skip in testing mode)
    if config_name != 'testing':
        _create_default_accounts(db)

    # Register blueprints (API routes)
    flask_app.register_blueprint(auth_routes.bp, url_prefix='/api/auth')
    flask_app.register_blueprint(google_oauth_routes.bp, url_prefix='/api/auth')
    flask_app.register_blueprint(job_routes.bp, url_prefix='/api/jobs')
    flask_app.register_blueprint(candidate_routes.bp, url_prefix='/api/candidates')
    flask_app.register_blueprint(company_routes.bp, url_prefix='/api/company')
    flask_app.register_blueprint(email_preferences_routes.bp, url_prefix='/api/email')
    flask_app.register_blueprint(assessment_routes.bp, url_prefix='/api/assessments')
    flask_app.register_blueprint(smart_assessment_routes.bp, url_prefix='/api/smart-assessments')
    flask_app.register_blueprint(audit_routes.bp, url_prefix='/api/audit')
    flask_app.register_blueprint(dsr_routes.bp, url_prefix='/api/dsr')
    flask_app.register_blueprint(dashboard_routes.bp, url_prefix='/api/dashboard')
    flask_app.register_blueprint(ai_interview_routes.bp, url_prefix='/api/ai-interview')
    flask_app.register_blueprint(interview_routes.bp, url_prefix='/api/interviews')
    flask_app.register_blueprint(admin_routes.bp, url_prefix='/api/admin')

    # v1 feature routes (analytics & LLM) — url_prefix defined inside the Blueprint
    flask_app.register_blueprint(analytics_routes.bp)   # /api/analytics
    flask_app.register_blueprint(llm_routes.bp)          # /api/llm

    # Register V2 routes if available
    if V2_ROUTES_AVAILABLE:
        flask_app.register_blueprint(ai_interview_routes_v2.bp, url_prefix='/api/ai-interview-v2')
        logger.info("✅ Enhanced V2 routes registered: LinkedIn integration, dynamic questions, fresher scoring")

    # Try to register video interview routes
    try:
        from backend.routes import video_interview_routes
        flask_app.register_blueprint(video_interview_routes.bp, url_prefix='/api/video-interview')
        logger.info("✅ Video interview routes registered")
    except ImportError:
        logger.info("ℹ️ Video interview routes not available yet")

    # ── Initialize Flan-T5 Question Generator (load model once at startup) ────
    if config_name != 'testing':
        try:
            from backend.services.flan_t5_service import initialize_flan_t5
            flan_status = initialize_flan_t5(
                flan_model=os.getenv('FLAN_T5_MODEL', 'google/flan-t5-base'),
                sbert_model=os.getenv('SBERT_MODEL', 'all-MiniLM-L6-v2'),
            )
            if flan_status.get('flan_t5_loaded'):
                logger.info("🧠 Flan-T5 interview engine loaded — dynamic question generation enabled")
            else:
                logger.warning("⚠️ Flan-T5 not loaded — falling back to static question bank")
            if flan_status.get('sbert_loaded'):
                logger.info("🔗 SBERT loaded for Flan-T5 answer evaluation (threshold=0.70)")
        except Exception as e:
            logger.warning(f"⚠️ Flan-T5 initialization skipped: {e}")

    # Initialize monitoring & observability
    initialize_monitoring(flask_app)

    # Bug #6 fix: Auto-complete stale interviews on startup (fallback for Celery Beat)
    if config_name != 'testing':
        try:
            from backend.utils.interview_cleanup import auto_complete_stale_interviews
            completed = auto_complete_stale_interviews(stale_hours=24)
            if completed:
                logger.info(f"⏰ Startup: auto-completed {completed} stale interview(s)")
        except Exception as e:
            logger.warning(f"⚠️ Interview auto-complete skipped: {e}")

    # Start background workers if enabled (skip in testing mode)
    if config_name != 'testing' and env_config.enable_background_workers and env_config.enable_redis:
        try:
            logger.info("🚀 Starting background workers...")
            start_workers(num_workers=env_config.num_workers)

            def cleanup_workers():
                logger.info("🛑 Stopping background workers...")
                stop_workers()

            atexit.register(cleanup_workers)
            logger.info(f"✅ {env_config.num_workers} background workers started")
        except Exception as e:
            logger.warning(f"⚠️ Failed to start workers: {e}. Continuing without workers...")
    elif config_name == 'testing':
        logger.info("ℹ️ Background workers skipped in testing mode")
    else:
        logger.info("ℹ️ Background workers disabled (enable with ENABLE_BACKGROUND_WORKERS=true and Redis)")

    # ── Routes defined on the app (not blueprints) ────────────────────────────

    @flask_app.route('/')
    def home():
        """Serve the frontend application"""
        try:
            return send_from_directory(flask_app.static_folder, 'index.html')
        except Exception as e:
            logger.error(f"❌ Error serving index.html: {e}")
            return jsonify({'error': 'Failed to serve frontend', 'details': str(e)}), 500

    @flask_app.route('/interview/room/<token>')
    def interview_room(token):
        """Serve the video interview room page"""
        try:
            return send_from_directory(flask_app.static_folder, 'interview_room.html')
        except Exception as e:
            logger.error(f"❌ Error serving interview_room.html: {e}")
            return jsonify({'error': 'Interview room unavailable'}), 500

    @flask_app.route('/oauth/callback')
    def oauth_callback():
        """Handle Google OAuth callback - serve frontend SPA"""
        return send_from_directory(flask_app.static_folder, 'index.html')

    @flask_app.route('/<path:path>')
    def catch_all(path):
        """Serve frontend for all non-API routes"""
        try:
            if path.startswith('api/'):
                return jsonify({'error': 'API endpoint not found'}), 404
            file_path = os.path.join(flask_app.static_folder, path)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return send_from_directory(flask_app.static_folder, path)
            else:
                return send_from_directory(flask_app.static_folder, 'index.html')
        except Exception as e:
            logger.error(f"❌ Error in catch_all for path '{path}': {e}")
            return jsonify({'error': 'Failed to serve resource', 'path': path}), 500

    @flask_app.route('/api')
    def api_info():
        """API information"""
        return jsonify({
            'message': 'Smart Hiring System API',
            'version': '2.0.0',
            'endpoints': {
                'auth': '/api/auth',
                'jobs': '/api/jobs',
                'candidates': '/api/candidates',
                'assessments': '/api/assessments',
                'dashboard': '/api/dashboard',
                'video_interview': '/api/video-interview',
                'analytics': '/api/analytics',
                'llm': '/api/llm',
                'ai_interview_v2': '/api/ai-interview-v2',
                'flan_t5_engine': '/api/ai-interview-v2/flan-t5',
            },
            'documentation': 'See API_DOCUMENTATION.md for details'
        })

    @flask_app.route('/api/health')
    def health():
        """Health check endpoint"""
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'environment': config_name
        })

    @flask_app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Endpoint not found'}), 404

    @flask_app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500

    return flask_app


# ── Helper: default accounts ─────────────────────────────────────────────────

def _create_default_accounts(db):
    """Create default test accounts if they don't exist"""
    try:
        from werkzeug.security import generate_password_hash
        from datetime import datetime

        users_collection = db.get_collection('users')
        if users_collection is None:
            print("⚠️ Could not get users collection")
            return

        admin_pwd = os.getenv('DEFAULT_ADMIN_PASSWORD', 'Admin@123')
        test_pwd = os.getenv('DEFAULT_TEST_PASSWORD', 'password123')

        default_accounts = [
            {
                'email': os.getenv('DEFAULT_ADMIN_EMAIL', 'admin@smarthiring.com'),
                'password': generate_password_hash(admin_pwd),
                'name': 'System Admin',
                'role': 'admin',
                'is_active': True,
                'created_at': datetime.utcnow(),
                'email_verified': True
            },
            {
                'email': os.getenv('DEFAULT_RECRUITER_EMAIL', 'recruiter@test.com'),
                'password': generate_password_hash(test_pwd),
                'name': 'Test Recruiter',
                'role': 'company',
                'company_name': 'Test Company Inc.',
                'is_active': True,
                'created_at': datetime.utcnow(),
                'email_verified': True
            },
            {
                'email': os.getenv('DEFAULT_CANDIDATE_EMAIL', 'candidate@test.com'),
                'password': generate_password_hash(test_pwd),
                'name': 'Test Candidate',
                'role': 'candidate',
                'is_active': True,
                'created_at': datetime.utcnow(),
                'email_verified': True
            }
        ]

        created_count = 0
        for account in default_accounts:
            existing = users_collection.find_one({'email': account['email']})
            if not existing:
                users_collection.insert_one(account)
                print(f"✅ Created default account: {account['email']}")
                created_count += 1
            else:
                print(f"ℹ️ Account already exists: {account['email']}")

        if created_count > 0:
            print(f"🎉 Created {created_count} default account(s)")
        else:
            print("ℹ️ All default accounts already exist")

    except Exception as e:
        print(f"⚠️ Could not create default accounts: {e}")


# ── Module-level app (backward compatibility) ────────────────────────────────
# Deployment platforms, root app.py, and wsgi.py all import `app` directly.
app = create_app()
application = app  # WSGI / Vercel compatibility

if __name__ == '__main__':
    # Print startup banner
    print_startup_banner()
    
    # Start Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=env_config.debug,
        use_reloader=False,
        threaded=True
    )

# Export app for Vercel
application = app
