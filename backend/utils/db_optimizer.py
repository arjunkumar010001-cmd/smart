"""
Database optimization - Index creation and query optimization
"""

import logging
from backend.models.database import get_db

logger = logging.getLogger(__name__)


def create_indexes():
    """Create database indexes for optimal query performance"""
    
    db = get_db()
    
    try:
        # Users collection indexes
        users = db['users']
        users.create_index('email', unique=True)
        users.create_index('role')
        users.create_index([('email', 1), ('role', 1)])
        logger.info("✅ Users indexes created")
        
        # Jobs collection indexes
        jobs = db['jobs']
        jobs.create_index('recruiter_id')
        jobs.create_index('status')
        jobs.create_index('required_skills')
        jobs.create_index([('status', 1), ('created_at', -1)])
        jobs.create_index([('title', 'text'), ('description', 'text')])  # Text search
        logger.info("✅ Jobs indexes created")
        
        # Applications collection indexes
        applications = db['applications']
        applications.create_index('candidate_id')
        applications.create_index('job_id')
        applications.create_index('status')
        applications.create_index([('candidate_id', 1), ('job_id', 1)], unique=True)
        applications.create_index([('job_id', 1), ('status', 1)])
        applications.create_index([('job_id', 1), ('overall_score', -1)])
        logger.info("✅ Applications indexes created")
        
        # Questions collection indexes
        questions = db['questions']
        questions.create_index('created_by')
        questions.create_index('category')
        questions.create_index('difficulty')
        questions.create_index('is_active')
        questions.create_index([('is_active', 1), ('category', 1)])
        logger.info("✅ Questions indexes created")
        
        # Quizzes collection indexes
        quizzes = db['quizzes']
        quizzes.create_index('created_by')
        quizzes.create_index('job_id')
        quizzes.create_index('is_active')
        quizzes.create_index([('is_active', 1), ('created_by', 1)])
        logger.info("✅ Quizzes indexes created")
        
        # Quiz attempts collection indexes
        quiz_attempts = db['quiz_attempts']
        quiz_attempts.create_index('quiz_id')
        quiz_attempts.create_index('candidate_id')
        quiz_attempts.create_index('status')
        quiz_attempts.create_index([('quiz_id', 1), ('candidate_id', 1)])
        quiz_attempts.create_index([('quiz_id', 1), ('status', 1)])
        logger.info("✅ Quiz attempts indexes created")
        
        # Audit logs collection indexes
        audit_logs = db['audit_logs']
        audit_logs.create_index('user_id')
        audit_logs.create_index('action')
        audit_logs.create_index('timestamp')
        audit_logs.create_index([('user_id', 1), ('timestamp', -1)])
        logger.info("✅ Audit logs indexes created")
        
        # DSR logs collection indexes
        dsr_logs = db['dsr_logs']
        dsr_logs.create_index('user_id')
        dsr_logs.create_index('request_type')
        dsr_logs.create_index('status')
        dsr_logs.create_index('timestamp')
        logger.info("✅ DSR logs indexes created")

        # Smart assessment sessions indexes
        smart_sessions = db['smart_sessions']
        smart_sessions.create_index([('candidate_id', 1), ('status', 1)])
        smart_sessions.create_index('assessment_config_id')
        smart_sessions.create_index('job_application_id')
        logger.info("✅ Smart sessions indexes created")

        # Video interview sessions indexes  (critical for auto-complete query)
        vis = db['video_interview_sessions']
        vis.create_index([('status', 1), ('scheduled_at', 1)])
        vis.create_index('candidate_id')
        vis.create_index('job_id')
        logger.info("✅ Video interview sessions indexes created")

        # Blacklist collection indexes
        blacklist = db['blacklist']
        blacklist.create_index('candidate_id', unique=True)
        logger.info("✅ Blacklist indexes created")

        # Resume download audit logs
        dl_logs = db['resume_download_logs']
        dl_logs.create_index('timestamp')
        dl_logs.create_index('recruiter_id')
        logger.info("✅ Resume download logs indexes created")

        logger.info("🎉 All database indexes created successfully")
        
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        raise


def analyze_slow_queries():
    """Analyze and log slow queries (requires MongoDB profiling enabled)"""
    
    db = get_db()
    
    try:
        # Get slow queries from system.profile collection
        slow_queries = db['system.profile'].find({
            'millis': {'$gt': 100}  # Queries taking more than 100ms
        }).sort('millis', -1).limit(10)
        
        for query in slow_queries:
            logger.warning(
                f"Slow query detected: {query.get('command')} "
                f"took {query.get('millis')}ms"
            )
        
    except Exception as e:
        logger.info(f"Query profiling not enabled or error occurred: {e}")


def get_collection_stats():
    """Get statistics for all collections"""
    
    db = get_db()
    stats = {}
    
    collections = ['users', 'jobs', 'applications', 'questions', 'quizzes', 
                  'quiz_attempts', 'audit_logs', 'dsr_logs', 'smart_sessions',
                  'video_interview_sessions', 'blacklist', 'resume_download_logs']
    
    for collection_name in collections:
        try:
            collection = db[collection_name]
            count = collection.count_documents({})
            stats[collection_name] = {
                'count': count,
                'indexes': len(list(collection.list_indexes()))
            }
        except Exception as e:
            logger.error(f"Error getting stats for {collection_name}: {e}")
    
    return stats


if __name__ == '__main__':
    # Run index creation when script is executed directly
    logging.basicConfig(level=logging.INFO)
    print("Creating database indexes...")
    create_indexes()
    print("\nCollection statistics:")
    stats = get_collection_stats()
    for collection, data in stats.items():
        print(f"  {collection}: {data['count']} documents, {data['indexes']} indexes")
