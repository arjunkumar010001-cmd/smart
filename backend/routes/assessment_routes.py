"""
Assessment and Quiz Management Routes  
Handles question bank, quiz creation, quiz taking, and results
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from bson import ObjectId
import random

from backend.models.database import get_db
from backend.models.assessment import Question, Quiz, QuizAttempt
from backend.security.rbac import require_permission, Permissions

bp = Blueprint('assessments', __name__)

def get_user_info(current_user):
    """Helper to extract user_id and role from JWT identity"""
    if isinstance(current_user, str):
        user_id = current_user
        db = get_db()
        user = db['users'].find_one({'_id': ObjectId(user_id)})
        return user_id, user.get('role') if user else None
    return current_user.get('user_id'), current_user.get('role')

# ==================== QUESTION BANK MANAGEMENT ====================

@bp.route('/questions', methods=['POST'])
@jwt_required()
@require_permission(Permissions.CREATE_ASSESSMENT)
def create_question():
    """Create a new question (recruiter/admin only)"""
    try:
        user_id, role = get_user_info(get_jwt_identity())
        if role not in ['company', 'admin', 'recruiter']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        required_fields = ['question_text', 'question_type']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing field: {field}'}), 400
        
        question = Question(
            question_text=data['question_text'],
            question_type=data.get('question_type', 'multiple_choice'),
            options=data.get('options', []),
            correct_answer=data.get('correct_answer', ''),
            points=data.get('points', 1),
            difficulty=data.get('difficulty', 'medium'),
            category=data.get('category', 'general'),
            tags=data.get('tags', []),
            explanation=data.get('explanation', ''),
            created_by=user_id
        )
        
        result = get_db()['questions'].insert_one(question.to_dict())
        return jsonify({'message': 'Question created', 'question_id': str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/questions', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def get_questions():
    """Get all questions with filtering"""
    try:
        user_id, role = get_user_info(get_jwt_identity())
        if role not in ['company', 'admin', 'recruiter']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        query = {'is_active': True}
        if role not in ('admin',):
            query['created_by'] = user_id
        
        # Apply filters
        for param in ['category', 'difficulty']:
            if request.args.get(param):
                query[param] = request.args.get(param)
        
        questions = list(get_db()['questions'].find(query))
        for q in questions:
            q['_id'] = str(q['_id'])
            q['created_at'] = q['created_at'].isoformat()
        
        return jsonify({'questions': questions, 'total': len(questions)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/questions/<question_id>', methods=['DELETE'])
@jwt_required()
@require_permission(Permissions.EDIT_ASSESSMENT)
def delete_question(question_id):
    """Soft delete a question"""
    try:
        user_id, role = get_user_info(get_jwt_identity())
        if role not in ['company', 'admin', 'recruiter']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = get_db()
        question = db['questions'].find_one({'_id': ObjectId(question_id)})
        if not question:
            return jsonify({'error': 'Question not found'}), 404
        
        if role != 'admin' and question['created_by'] != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db['questions'].update_one(
            {'_id': ObjectId(question_id)},
            {'$set': {'is_active': False}}
        )
        return jsonify({'message': 'Question deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== QUIZ MANAGEMENT ====================

@bp.route('/quizzes', methods=['POST'])
@jwt_required()
@require_permission(Permissions.CREATE_ASSESSMENT)
def create_quiz():
    """Create a new quiz"""
    try:
        user_id, role = get_user_info(get_jwt_identity())
        if role not in ['company', 'admin', 'recruiter']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        if 'title' not in data or 'questions' not in data:
            return jsonify({'error': 'Missing title or questions'}), 400
        
        # Calculate total points
        db = get_db()
        question_ids = [ObjectId(qid) for qid in data['questions']]
        questions = list(db['questions'].find({'_id': {'$in': question_ids}}))
        total_points = sum(q.get('points', 1) for q in questions)
        
        quiz = Quiz(
            title=data['title'],
            description=data.get('description', ''),
            created_by=user_id,
            questions=data['questions'],
            duration=data.get('duration', 3600),
            passing_score=data.get('passing_score', 70),
            total_points=total_points,
            job_id=data.get('job_id'),
            max_attempts=data.get('max_attempts', 1)
        )
        
        result = db['quizzes'].insert_one(quiz.to_dict())
        return jsonify({'message': 'Quiz created', 'quiz_id': str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/quizzes', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def get_quizzes():
    """Get quizzes"""
    try:
        user_id, role = get_user_info(get_jwt_identity())
        
        db = get_db()
        query = {'is_active': True}
        
        if role == 'company':
            query['created_by'] = user_id
        elif role == 'candidate':
            # Candidates see ALL active quizzes (general + job-specific)
            # This allows them to build their profile before applying
            # Job-specific quizzes will be marked if they applied to that job
            pass  # Show all active quizzes
        
        quizzes = list(db['quizzes'].find(query))
        
        # For candidates, add context about which quizzes are required for their applications
        if role == 'candidate':
            applications = list(db['applications'].find({'candidate_id': user_id}))
            applied_job_ids = [app['job_id'] for app in applications]
            
            for quiz in quizzes:
                quiz['_id'] = str(quiz['_id'])
                quiz['created_at'] = quiz['created_at'].isoformat()
                # Mark if this quiz is for a job they applied to
                quiz['is_required'] = quiz.get('job_id') in applied_job_ids if quiz.get('job_id') else False
        else:
            for quiz in quizzes:
                quiz['_id'] = str(quiz['_id'])
                quiz['created_at'] = quiz['created_at'].isoformat()
        
        return jsonify({'quizzes': quizzes, 'total': len(quizzes)}), 200
    except Exception as e:
        print(f"Error in get_quizzes: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ==================== CANDIDATE ATTEMPTS ====================

@bp.route('/my-attempts', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def get_my_attempts():
    """Get all quiz attempts for the current candidate"""
    try:
        user_id, role = get_user_info(get_jwt_identity())
        if role != 'candidate':
            return jsonify({'error': 'Only candidates can view their attempts'}), 403

        db = get_db()
        attempts = list(db['quiz_attempts'].find({'candidate_id': user_id}).sort('started_at', -1))

        for attempt in attempts:
            attempt['_id'] = str(attempt['_id'])
            if 'started_at' in attempt and hasattr(attempt['started_at'], 'isoformat'):
                attempt['started_at'] = attempt['started_at'].isoformat()
            if attempt.get('completed_at') and hasattr(attempt['completed_at'], 'isoformat'):
                attempt['completed_at'] = attempt['completed_at'].isoformat()

            # Enrich with quiz title
            quiz = db['quizzes'].find_one({'_id': ObjectId(attempt['quiz_id'])}) if attempt.get('quiz_id') else None
            if quiz:
                attempt['quiz_title'] = quiz.get('title', 'Unknown Quiz')

        return jsonify({'attempts': attempts, 'total': len(attempts)}), 200
    except Exception as e:
        print(f"Error in get_my_attempts: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ==================== QUIZ TAKING ====================

@bp.route('/quizzes/<quiz_id>/start', methods=['POST'])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def start_quiz(quiz_id):
    """Start a quiz attempt"""
    try:
        user_id, role = get_user_info(get_jwt_identity())
        if role != 'candidate':
            return jsonify({'error': 'Only candidates can take quizzes'}), 403
        
        db = get_db()
        quiz = db['quizzes'].find_one({'_id': ObjectId(quiz_id)})
        if not quiz:
            return jsonify({'error': 'Quiz not found'}), 404
        
        # Check max attempts
        attempts_count = db['quiz_attempts'].count_documents({
            'quiz_id': quiz_id,
            'candidate_id': user_id,
            'status': 'completed'
        })
        
        if attempts_count >= quiz.get('max_attempts', 1):
            return jsonify({'error': 'Maximum attempts reached'}), 400
        
        # Check for in-progress attempt
        existing = db['quiz_attempts'].find_one({
            'quiz_id': quiz_id,
            'candidate_id': user_id,
            'status': 'in_progress'
        })
        
        if existing:
            existing['_id'] = str(existing['_id'])
            return jsonify({'message': 'Existing attempt found', 'attempt': existing}), 200
        
        # Create new attempt
        attempt = QuizAttempt(quiz_id=quiz_id, candidate_id=user_id)
        result = db['quiz_attempts'].insert_one(attempt.to_dict())
        
        # Get questions (hide correct answers)
        question_ids = [ObjectId(qid) for qid in quiz['questions']]
        questions = list(db['questions'].find({'_id': {'$in': question_ids}}))
        
        if quiz.get('randomize_questions'):
            random.shuffle(questions)
        
        safe_questions = []
        for q in questions:
            safe_q = {
                '_id': str(q['_id']),
                'question_text': q['question_text'],
                'question_type': q['question_type'],
                'options': q['options'],
                'points': q['points']
            }
            if quiz.get('randomize_options') and q['question_type'] == 'multiple_choice':
                random.shuffle(safe_q['options'])
            safe_questions.append(safe_q)
        
        return jsonify({
            'message': 'Quiz started',
            'attempt_id': str(result.inserted_id),
            'quiz': {
                'title': quiz['title'],
                'duration': quiz['duration'],
                'total_points': quiz['total_points']
            },
            'questions': safe_questions
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/attempts/<attempt_id>/submit', methods=['POST'])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def submit_quiz(attempt_id):
    """Submit quiz answers"""
    try:
        user_id, role = get_user_info(get_jwt_identity())
        
        data = request.get_json()
        answers = data.get('answers', {})
        time_spent = data.get('time_spent', {})
        
        db = get_db()
        attempt = db['quiz_attempts'].find_one({'_id': ObjectId(attempt_id)})
        if not attempt or attempt['candidate_id'] != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        quiz = db['quizzes'].find_one({'_id': ObjectId(attempt['quiz_id'])})
        
        # Get questions and grade
        question_ids = [ObjectId(qid) for qid in quiz['questions']]
        questions = {str(q['_id']): q for q in db['questions'].find({'_id': {'$in': question_ids}})}
        
        score = 0
        correct_count = 0
        feedback = {}
        
        for q_id, answer in answers.items():
            question = questions.get(q_id)
            if not question:
                continue
            
            is_correct = False
            if question['question_type'] in ['multiple_choice', 'true_false']:
                is_correct = answer == question['correct_answer']
            elif question['question_type'] == 'short_answer':
                is_correct = answer.lower().strip() == question['correct_answer'].lower().strip()
            
            if is_correct:
                score += question.get('points', 1)
                correct_count += 1
            
            feedback[q_id] = is_correct
        
        total_points = quiz['total_points']
        percentage = (score / total_points * 100) if total_points > 0 else 0
        passed = percentage >= quiz['passing_score']
        
        # Update attempt
        db['quiz_attempts'].update_one(
            {'_id': ObjectId(attempt_id)},
            {'$set': {
                'answers': answers,
                'time_spent': time_spent,
                'score': score,
                'percentage': round(percentage, 2),
                'passed': passed,
                'status': 'completed',
                'completed_at': datetime.utcnow(),
                'correct_count': correct_count,
                'incorrect_count': len(answers) - correct_count,
                'unanswered_count': len(quiz['questions']) - len(answers),
                'feedback': feedback
            }}
        )
        
        return jsonify({
            'message': 'Quiz submitted',
            'score': score,
            'total_points': total_points,
            'percentage': round(percentage, 2),
            'passed': passed,
            'correct_count': correct_count
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/attempts/<attempt_id>', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_ASSESSMENT)
def get_attempt_results(attempt_id):
    """Get quiz attempt results"""
    try:
        user_id, role = get_user_info(get_jwt_identity())
        
        db = get_db()
        attempt = db['quiz_attempts'].find_one({'_id': ObjectId(attempt_id)})
        if not attempt or attempt['candidate_id'] != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        attempt['_id'] = str(attempt['_id'])
        attempt['started_at'] = attempt['started_at'].isoformat()
        if attempt.get('completed_at'):
            attempt['completed_at'] = attempt['completed_at'].isoformat()
        
        return jsonify({'attempt': attempt}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/quizzes/<quiz_id>/analytics', methods=['GET'])
@jwt_required()
@require_permission(Permissions.VIEW_COMPANY_ANALYTICS)
def get_quiz_analytics(quiz_id):
    """Get quiz analytics (recruiter/admin only)"""
    try:
        user_id, role = get_user_info(get_jwt_identity())
        if role not in ['company', 'admin', 'recruiter']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = get_db()
        attempts = list(db['quiz_attempts'].find({
            'quiz_id': quiz_id,
            'status': 'completed'
        }))
        
        if not attempts:
            return jsonify({'total_attempts': 0, 'average_score': 0, 'pass_rate': 0}), 200
        
        total = len(attempts)
        avg_score = sum(a['percentage'] for a in attempts) / total
        passed = sum(1 for a in attempts if a['passed'])
        
        return jsonify({
            'total_attempts': total,
            'average_score': round(avg_score, 2),
            'pass_rate': round((passed / total * 100), 2),
            'passed_count': passed,
            'failed_count': total - passed
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
