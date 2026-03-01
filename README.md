# Smart Hiring System

[![CI - Build and Test](https://github.com/arjunkumar010001-cmd/smart/actions/workflows/ci.yml/badge.svg)](https://github.com/arjunkumar010001-cmd/smart/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Flask 3.0](https://img.shields.io/badge/flask-3.0-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-see%20LICENSE-lightgrey.svg)](LICENSE)

An AI-powered, bias-aware recruitment platform that automates resume screening, candidate matching, AI-driven interviews, and fairness auditing — built with Flask, MongoDB, and modern ML/NLP libraries.

---

## Key Features

- **AI Resume Parsing** — Automated extraction of skills, experience, and qualifications from PDF/DOCX resumes using NLP (spaCy, PyPDF2, pdfplumber)
- **ML Candidate Matching** — Semantic job-candidate matching with Sentence-BERT and scikit-learn, with separate scoring models for freshers and experienced candidates
- **AI Interviews** — Dynamic AI-generated interview questions with real-time evaluation (v1 & v2 engines)
- **Fairness & Bias Prevention** — Multi-layered fairness engine using Fairlearn, with AIF360 microservice integration, demographic parity monitoring, and explainability reporting
- **GDPR Compliance** — Data Subject Request (DSR) handling, PII anonymization, and comprehensive audit logging
- **Role-Based Access Control** — Candidate, Company, and Admin portals with RBAC, rate limiting, and encryption
- **Real-Time Communication** — WebSocket support for live video interviews and notifications
- **Email Workflow** — Transactional emails via Brevo SMTP with customizable templates and opt-in/out preferences
- **Analytics Dashboard** — Hiring analytics, scoring audit trails, and compliance dashboards
- **Multi-Platform Deployment** — Docker Compose, Railway, Render, Fly.io, Vercel, Netlify, and Electron desktop app

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | Python 3.10, Flask 3.0, Gunicorn, Eventlet |
| Database | MongoDB 7.0 (PyMongo) |
| Cache / Queue | Redis 7, Celery 5.3, Flower |
| Frontend | Vanilla HTML/CSS/JS (served by Flask) |
| Desktop App | Electron (Node.js) |
| ML/NLP | scikit-learn, Sentence-Transformers, PyTorch, spaCy, Fairlearn |
| Fairness Service | Standalone Flask microservice (AIF360) |
| ML Service | Standalone Flask microservice |
| Auth | Flask-JWT-Extended, Flask-Bcrypt, Google OAuth, LinkedIn OAuth |
| Email | Brevo SMTP |
| Monitoring | Sentry SDK, Flower |
| CI/CD | GitHub Actions |

---

## Project Structure

```
smart_hiring/
├── app.py                    # Root entry point (imports from backend)
├── backend/                  # Core Flask application
│   ├── app.py                # App factory (create_app)
│   ├── routes/               # 14+ API blueprint modules
│   ├── services/             # 24 service modules (AI, ML, email, fairness...)
│   ├── models/               # MongoDB data models
│   ├── security/             # Encryption, RBAC, rate limiting, file security
│   ├── middleware/            # Rate limiter middleware
│   ├── matching/             # Decision engine, scoring, eligibility
│   ├── utils/                # Caching, monitoring, sanitization, Swagger
│   ├── workers/              # Background job processors
│   ├── tasks/                # Celery async tasks
│   ├── scripts/              # DB init & seed scripts
│   └── tests/                # Backend unit tests
├── frontend/                 # Static HTML/CSS/JS frontend
│   ├── index.html            # Main entry page
│   ├── app.js                # Core SPA routing
│   ├── api.js                # API client
│   └── ...                   # Admin, candidate, company portals
├── aif360-service/           # Standalone fairness analysis microservice
├── ml-service/               # Standalone ML microservice
├── config/                   # App & scoring configuration
├── deploy/                   # Docker deployment configs
├── desktop/                  # Electron desktop app
├── scripts/                  # Utility & build scripts
├── tests/                    # Integration & system tests
├── build_scripts/            # PowerShell build automation
├── doc_generator/            # Documentation generation tools
├── ppt_generator/            # Presentation generation tools
├── netlify/functions/        # Netlify serverless functions
├── docs/                     # Essential project documentation
│   ├── SECURITY.md
│   └── API_DOCUMENTATION.md
├── .github/workflows/        # CI/CD pipelines
├── docker-compose.yml        # Full-stack Docker orchestration
├── Dockerfile                # Main Docker image
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variable template
└── .gitignore                # Git exclusion rules
```

---

## Getting Started

### Prerequisites

- **Python 3.10+**
- **MongoDB 7.0+** (local or [MongoDB Atlas](https://www.mongodb.com/atlas))
- **Redis 7+** (for Celery task queue)
- **Node.js 18+** (only if building the Electron desktop app)

### 1. Clone the Repository

```bash
git clone https://github.com/arjunkumar010001-cmd/smart.git
cd smart
```

### 2. Set Up Environment

```bash
# Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
# Copy the template and fill in your values
cp .env.example .env
```

At minimum, set these in `.env`:
- `SECRET_KEY` — Flask secret key (32+ characters)
- `JWT_SECRET_KEY` — JWT signing key (32+ characters)
- `MONGODB_URI` — MongoDB connection string
- `SMTP_*` — Email configuration (Brevo recommended)

See [.env.example](.env.example) for all available options.

### 4. Initialize the Database

```bash
python -m backend.scripts.init_db
```

### 5. Run the Application

```bash
# Development
flask run --debug

# Production (via Gunicorn)
gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:5000 app:app
```

The app will be available at `http://localhost:5000`.

### 6. Run with Docker (Full Stack)

```bash
docker-compose up --build
```

This starts the backend, MongoDB, Redis, and Celery worker.

---

## Running Tests

```bash
# Run all tests
pytest

# Run specific test suite
pytest tests/test_api.py
pytest backend/tests/
```

---

## API Documentation

See [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) for the full API reference.

Key API prefixes:
- `/api/auth` — Authentication & OAuth
- `/api/jobs` — Job management
- `/api/candidates` — Candidate operations
- `/api/ai-interview` — AI interview engine
- `/api/assessments` — Skills assessments
- `/api/dashboard` — Analytics
- `/api/admin` — Administration
- `/api/audit` — Fairness audits
- `/api/dsr` — GDPR data requests

---

## Deployment

The project supports multiple deployment targets:

| Platform | Config File |
|----------|-------------|
| Docker Compose | `docker-compose.yml` |
| Railway | `railway.json`, `Procfile` |
| Render | `render.yaml` |
| Fly.io | `fly.toml` |
| Vercel | `vercel.json` |
| Netlify | `netlify.toml` |
| Google Cloud Build | `cloudbuild.yaml` |

---

## Security

See [docs/SECURITY.md](docs/SECURITY.md) for security policies and vulnerability reporting.

Key security features:
- JWT-based authentication with token refresh
- Role-Based Access Control (RBAC)
- Data encryption at rest
- Input sanitization and XSS prevention
- Rate limiting per endpoint
- Secure file upload validation
- CORS policy enforcement
- Security headers (HSTS, CSP, X-Frame-Options)

---

## License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.
