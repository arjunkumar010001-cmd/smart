"""
Root-level app.py for deployment platforms that expect app.py in root
This simply imports and exposes the Flask app from backend
"""
from backend.app import app, application, create_app

if __name__ == '__main__':
    app.run(use_reloader=False)
