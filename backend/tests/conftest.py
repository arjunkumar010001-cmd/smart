"""
PyTest configuration and fixtures for Smart Hiring System tests.
Provides: app, client, mock_db, mock_candidate_user, mock_recruiter_user,
          sample data, and auth_headers helpers.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime
from bson import ObjectId

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app import app as flask_app
from backend.models.database import Database
from backend.backend_config import config


# ---------------------------------------------------------------------------
# App & Client Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create application fixture."""
    flask_app.config['TESTING'] = True
    flask_app.config['DEBUG'] = False
    flask_app.config['WTF_CSRF_ENABLED'] = False
    return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create CLI runner."""
    return app.test_cli_runner()


# ---------------------------------------------------------------------------
# Database Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def db():
    """Create database fixture (real MongoDB connection for integration tests)."""
    db = Database()
    db.connect('testing')
    yield db
    # Cleanup after tests


@pytest.fixture
def mock_db(mocker):
    """
    Provide a mongomock-based in-memory MongoDB fixture.
    Patches backend.models.database.get_db to return a mongomock database.
    """
    import mongomock
    mock_client = mongomock.MongoClient()
    mock_database = mock_client['smart_hiring_test']
    mocker.patch('backend.models.database.get_db', return_value=mock_database)
    return mock_database


# ---------------------------------------------------------------------------
# User Fixtures
# ---------------------------------------------------------------------------

_CANDIDATE_ID = str(ObjectId())
_RECRUITER_ID = str(ObjectId())


@pytest.fixture
def mock_candidate_user():
    """
    Return a test candidate user dict with a pre-built JWT identity payload.
    Use with mocker.patch('flask_jwt_extended.get_jwt_identity', return_value=...).
    """
    return {
        "user_id": _CANDIDATE_ID,
        "email": "test.candidate@example.com",
        "role": "candidate",
        "full_name": "Test Candidate",
        "phone": "+1234567890",
        "skills": ["python", "flask", "mongodb", "docker"],
        "experience": 4,
        "education": "BS Computer Science",
        "bio": "Experienced software engineer with passion for building scalable systems.",
        "location": "Remote",
        "resume_file": "test_resume.pdf",
        "linkedin": "https://linkedin.com/in/testcandidate",
        # JWT identity payload (what get_jwt_identity() returns)
        "jwt_identity": {"user_id": _CANDIDATE_ID, "role": "candidate"},
    }


@pytest.fixture
def mock_recruiter_user():
    """
    Return a test recruiter user dict with a pre-built JWT identity payload.
    Use with mocker.patch('flask_jwt_extended.get_jwt_identity', return_value=...).
    """
    return {
        "user_id": _RECRUITER_ID,
        "email": "recruiter@company.com",
        "role": "recruiter",
        "full_name": "Test Recruiter",
        "company_name": "TechCorp",
        # JWT identity payload
        "jwt_identity": {"user_id": _RECRUITER_ID, "role": "recruiter"},
    }


# ---------------------------------------------------------------------------
# Sample Data Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_resume_text():
    """Sample resume text for testing."""
    return """
    John Doe
    john.doe@email.com
    (555) 123-4567
    123 Main St, City, State 12345
    
    PROFESSIONAL SUMMARY
    Experienced software engineer with 5 years of experience in Python and web development.
    
    SKILLS
    - Python, JavaScript, React
    - Flask, Django, FastAPI
    - MongoDB, PostgreSQL
    - Docker, Kubernetes
    
    EXPERIENCE
    Senior Software Engineer - Tech Company (2020-Present)
    - Developed RESTful APIs using Flask
    - Implemented ML models for recommendation system
    - Led team of 5 developers
    
    EDUCATION
    BS in Computer Science - University Name (2018)
    """


@pytest.fixture
def sample_job_data():
    """Sample job data for testing."""
    return {
        "title": "Senior Python Developer",
        "description": "Looking for experienced Python developer",
        "requirements": "5+ years Python, Flask, MongoDB, Docker",
        "skills": ["python", "flask", "mongodb", "docker", "api development"],
        "required_skills": ["python", "flask", "mongodb", "docker"],
        "location": "Remote",
        "salary_range": "$100k-$150k",
        "job_type": "Full-time",
    }


@pytest.fixture
def sample_candidate_data():
    """Sample candidate data for testing."""
    return {
        "name": "Jane Smith",
        "email": "jane.smith@example.com",
        "phone": "+1234567890",
        "skills": ["python", "django", "postgresql", "react"],
        "experience_years": 4,
        "education": "BS Computer Science",
    }


@pytest.fixture
def sample_assessment_config():
    """Sample assessment config document for testing."""
    return {
        "_id": ObjectId(),
        "job_id": str(ObjectId()),
        "title": "Python Coding Assessment",
        "question_types": ["mcq", "coding"],
        "difficulty": "hard",
        "num_questions": 10,
        "time_limit_minutes": 60,
        "negative_marking": False,
        "created_by": _RECRUITER_ID,
        "created_at": datetime.utcnow(),
    }


@pytest.fixture
def auth_headers(client):
    """Get authentication headers for testing (uses admin login)."""
    response = client.post('/api/auth/login', json={
        'email': 'admin@smarthiring.com',
        'password': config.ADMIN_PASSWORD
    })

    if response.status_code == 200:
        data = response.get_json()
        token = data.get('access_token')
        return {'Authorization': f'Bearer {token}'}

    return {}
