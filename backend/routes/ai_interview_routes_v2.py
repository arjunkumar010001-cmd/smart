"""
Enhanced AI Interview Routes with Dynamic Role-Specific Questions,
LinkedIn Integration, Fresher-Friendly Scoring, and Flan-T5 Interview Engine
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from bson import ObjectId
import logging

from backend.models.database import get_db
from backend.services.ai_interviewer_service_v2 import (
    generate_dynamic_interview_questions,
    evaluate_answer_advanced,
    create_interview_schedule_advanced
)
from backend.services.linkedin_career_service import (
    LinkedInService,
    calculate_career_consistency_index,
    calculate_fresher_potential_score,
    calculate_social_proof_score
)
from backend.services.ranking_service import rank_candidates_for_job, get_candidate_insights

# ── Flan-T5 imports (graceful) ────────────────────────────────────────────────
try:
    from backend.services.flan_t5_service import (
        FlanT5QuestionGenerator,
        run_gap_analysis,
        generate_gap_based_questions,
        get_generator,
    )
    FLAN_T5_ROUTES = True
except ImportError:
    FLAN_T5_ROUTES = False

logger = logging.getLogger(__name__)

bp = Blueprint('ai_interview_v2', __name__)
linkedin_service = LinkedInService()


def get_user_info(current_user):
    """Helper to extract user_id and role from JWT identity"""
    if isinstance(current_user, str):
        user_id = current_user
        db = get_db()
        user = db['users'].find_one({'_id': ObjectId(user_id)})
        return user_id, user.get('role') if user else None
    return current_user.get('user_id'), current_user.get('role')


# ============================================================================
# LINKEDIN INTEGRATION ENDPOINTS
# ============================================================================

@bp.route('/linkedin/authorize', methods=['GET'])
@jwt_required()
def linkedin_authorize():
    """
    Initiate LinkedIn OAuth flow
    GET /api/ai-interview-v2/linkedin/authorize
    """
    try:
        user_id, role = get_user_info(get_jwt_identity())
        
        if role != 'candidate':
            return jsonify({'error': 'Only candidates can connect LinkedIn'}), 403
        
        # Generate state for CSRF protection
        state = f"{user_id}_{datetime.utcnow().timestamp()}"
        
        # Save state to database
        db = get_db()
        db['linkedin_states'].insert_one({
            'state': state,
            'user_id': user_id,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow().timestamp() + 600  # 10 minutes
        })
        
        # Get authorization URL
        auth_url = linkedin_service.get_authorization_url(state)
        
        return jsonify({
            'authorization_url': auth_url,
            'message': 'Redirect user to this URL'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/linkedin/callback', methods=['GET'])
def linkedin_callback():
    """
    Handle LinkedIn OAuth callback
    GET /api/ai-interview-v2/linkedin/callback?code=xxx&state=xxx
    """
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        
        if not code or not state:
            return jsonify({'error': 'Missing code or state'}), 400
        
        # Verify state
        db = get_db()
        state_doc = db['linkedin_states'].find_one({'state': state})
        
        if not state_doc:
            return jsonify({'error': 'Invalid state'}), 400
        
        if datetime.utcnow().timestamp() > state_doc['expires_at']:
            return jsonify({'error': 'State expired'}), 400
        
        user_id = state_doc['user_id']
        
        # Exchange code for access token
        access_token = linkedin_service.get_access_token(code)
        if not access_token:
            return jsonify({'error': 'Failed to get access token'}), 500
        
        # Get LinkedIn profile
        linkedin_profile = linkedin_service.get_profile(access_token)
        if not linkedin_profile:
            return jsonify({'error': 'Failed to get profile'}), 500
        
        # Save LinkedIn data to candidate profile
        db['candidates'].update_one(
            {'user_id': user_id},
            {
                '$set': {
                    'linkedin_connected': True,
                    'linkedin_profile': linkedin_profile,
                    'linkedin_verified_at': datetime.utcnow()
                }
            }
        )
        
        # Clean up state
        db['linkedin_states'].delete_one({'state': state})
        
        return jsonify({
            'message': 'LinkedIn connected successfully!',
            'profile': linkedin_profile
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/career-consistency/<candidate_id>', methods=['GET'])
@jwt_required()
def get_career_consistency(candidate_id):
    """
    Calculate Career Consistency Index for a candidate
    GET /api/ai-interview-v2/career-consistency/{candidate_id}
    """
    try:
        user_id, role = get_user_info(get_jwt_identity())
        
        if role not in ['company', 'recruiter', 'admin']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = get_db()
        candidate = db['candidates'].find_one({'user_id': candidate_id})
        
        if not candidate:
            return jsonify({'error': 'Candidate not found'}), 404
        
        # Get LinkedIn data if available
        linkedin_data = candidate.get('linkedin_profile')
        
        # Calculate CCI
        cci_result = calculate_career_consistency_index(candidate, linkedin_data)
        
        # Save to candidate profile
        db['candidates'].update_one(
            {'user_id': candidate_id},
            {'$set': {'cci_data': cci_result, 'cci_calculated_at': datetime.utcnow()}}
        )
        
        return jsonify(cci_result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/fresher-potential/<candidate_id>', methods=['GET'])
@jwt_required()
def get_fresher_potential(candidate_id):
    """
    Calculate potential score for fresher/entry-level candidates
    GET /api/ai-interview-v2/fresher-potential/{candidate_id}
    """
    try:
        user_id, role = get_user_info(get_jwt_identity())
        
        if role not in ['company', 'recruiter', 'admin', 'candidate']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = get_db()
        candidate = db['candidates'].find_one({'user_id': candidate_id})
        
        if not candidate:
            return jsonify({'error': 'Candidate not found'}), 404
        
        # Calculate fresher potential
        potential_result = calculate_fresher_potential_score(candidate)
        
        # Save to profile
        db['candidates'].update_one(
            {'user_id': candidate_id},
            {'$set': {'fresher_potential': potential_result, 'potential_calculated_at': datetime.utcnow()}}
        )
        
        return jsonify(potential_result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# DYNAMIC INTERVIEW QUESTION GENERATION
# ============================================================================

@bp.route('/generate-questions-dynamic', methods=['POST'])
@jwt_required()
def generate_questions_dynamic():
    """
    Generate role-specific interview questions dynamically
    
    POST /api/ai-interview-v2/generate-questions-dynamic
    Body: {
        "job_id": "job123",
        "candidate_id": "candidate123",  // optional
        "num_questions": 10,
        "include_behavioral": true,
        "difficulty_distribution": {"easy": 0.2, "medium": 0.5, "hard": 0.3}  // optional
    }
    """
    try:
        user_id, role = get_user_info(get_jwt_identity())
        
        if role not in ['company', 'recruiter', 'admin']:
            return jsonify({'error': 'Only recruiters can generate interview questions'}), 403
        
        data = request.get_json()
        job_id = data.get('job_id')
        candidate_id = data.get('candidate_id')
        num_questions = data.get('num_questions', 10)
        include_behavioral = data.get('include_behavioral', True)
        difficulty_dist = data.get('difficulty_distribution')
        
        if not job_id:
            return jsonify({'error': 'job_id is required'}), 400
        
        # Get job details
        db = get_db()
        job = db['jobs'].find_one({'_id': ObjectId(job_id)})
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        # Verify ownership
        if str(job['recruiter_id']) != user_id and role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get candidate if specified
        candidate = None
        if candidate_id:
            candidate = db['candidates'].find_one({'user_id': candidate_id})
        
        # Generate dynamic questions
        print(f"🎯 Generating questions for job: {job.get('title')}")
        questions = generate_dynamic_interview_questions(
            job=job,
            candidate=candidate,
            num_questions=num_questions,
            include_behavioral=include_behavioral,
            difficulty_distribution=difficulty_dist
        )
        
        # Save to database
        interview_set = {
            'job_id': job_id,
            'job_title': job.get('title'),
            'recruiter_id': user_id,
            'candidate_id': candidate_id,
            'questions': questions,
            'created_at': datetime.utcnow(),
            'is_active': True,
            'version': 2,  # v2 indicates dynamic generation
            'role_detected': questions[0].get('category') if questions else None
        }
        
        result = db['interview_questions'].insert_one(interview_set)
        
        # Generate interview schedule
        schedule = create_interview_schedule_advanced(
            questions=questions,
            total_duration_minutes=data.get('duration_minutes', 60),
            include_breaks=True
        )
        
        return jsonify({
            'message': 'Dynamic interview questions generated successfully! 🎯',
            'interview_set_id': str(result.inserted_id),
            'questions': questions,
            'total_questions': len(questions),
            'schedule': schedule,
            'role_detected': interview_set.get('role_detected'),
            'difficulty_breakdown': schedule['summary']['difficulty_breakdown']
        }), 201
        
    except Exception as e:
        print(f"❌ Error generating dynamic questions: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/evaluate-answer-advanced', methods=['POST'])
@jwt_required()
def evaluate_answer_endpoint():
    """
    Evaluate candidate's answer with advanced analysis
    
    POST /api/ai-interview-v2/evaluate-answer-advanced
    Body: {
        "question": {...},
        "answer": "candidate's answer text"
    }
    """
    try:
        data = request.get_json()
        
        question = data.get('question')
        answer = data.get('answer', '')
        
        if not question or not answer:
            return jsonify({'error': 'question and answer are required'}), 400
        
        # Evaluate with advanced analysis
        evaluation = evaluate_answer_advanced(question, answer)
        
        return jsonify(evaluation), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# SMART CANDIDATE RANKING (with fresher support)
# ============================================================================

@bp.route('/rank-candidates-smart', methods=['POST'])
@jwt_required()
def rank_candidates_smart():
    """
    Intelligently rank candidates using ML, with special handling for freshers
    
    POST /api/ai-interview-v2/rank-candidates-smart
    Body: {
        "job_id": "job123",
        "include_freshers": true
    }
    """
    try:
        user_id, role = get_user_info(get_jwt_identity())
        
        if role not in ['company', 'recruiter', 'admin']:
            return jsonify({'error': 'Only recruiters can rank candidates'}), 403
        
        data = request.get_json()
        job_id = data.get('job_id')
        include_freshers = data.get('include_freshers', True)
        
        if not job_id:
            return jsonify({'error': 'job_id is required'}), 400
        
        db = get_db()
        
        # Get job
        job = db['jobs'].find_one({'_id': ObjectId(job_id)})
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        # Verify ownership
        if str(job['recruiter_id']) != user_id and role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get applications for this job
        applications = list(db['applications'].find({'job_id': job_id}))
        
        if not applications:
            return jsonify({'message': 'No applications found', 'ranked_candidates': []}), 200
        
        # Get candidate profiles
        experienced_candidates = []
        fresher_candidates = []
        
        for app in applications:
            candidate = db['candidates'].find_one({'user_id': app['candidate_id']})
            if candidate:
                candidate['application_id'] = str(app['_id'])
                candidate['application_status'] = app.get('status')
                
                # Calculate CCI if not already done
                if 'cci_data' not in candidate:
                    linkedin_data = candidate.get('linkedin_profile')
                    cci_result = calculate_career_consistency_index(candidate, linkedin_data)
                    candidate['cci_score'] = cci_result['cci_score']
                    candidate['cci_data'] = cci_result
                else:
                    candidate['cci_score'] = candidate['cci_data'].get('cci_score', 50)
                
                # Categorize as fresher or experienced
                experience_years = candidate.get('experience_years', 0)
                if experience_years <= 1:
                    # Calculate fresher potential
                    if 'fresher_potential' not in candidate:
                        potential_result = calculate_fresher_potential_score(candidate)
                        candidate['fresher_potential'] = potential_result
                    
                    fresher_candidates.append(candidate)
                else:
                    experienced_candidates.append(candidate)
        
        # Rank experienced candidates using ML
        ranked_experienced = []
        if experienced_candidates:
            ranked_experienced = rank_candidates_for_job(experienced_candidates, job)
        
        # Rank freshers using potential score
        ranked_freshers = []
        if include_freshers and fresher_candidates:
            for candidate in fresher_candidates:
                candidate['ml_score'] = candidate['fresher_potential']['potential_score']
                candidate['is_fresher'] = True
                candidate['score_type'] = 'potential'
            
            ranked_freshers = sorted(
                fresher_candidates,
                key=lambda x: x['ml_score'],
                reverse=True
            )
        
        # Combine rankings
        all_ranked = ranked_experienced + ranked_freshers
        
        # Recalculate percentiles
        for i, candidate in enumerate(all_ranked, 1):
            candidate['rank'] = i
            candidate['percentile'] = round((len(all_ranked) - i + 1) / len(all_ranked) * 100, 1)
        
        # Format response
        for candidate in all_ranked:
            candidate['_id'] = str(candidate.get('_id'))
            if 'user_id' in candidate:
                user = db['users'].find_one({'_id': ObjectId(candidate['user_id'])})
                if user:
                    candidate['name'] = user.get('full_name', 'Unknown')
                    candidate['email'] = user.get('email')
        
        return jsonify({
            'job_id': job_id,
            'job_title': job.get('title'),
            'total_candidates': len(all_ranked),
            'experienced_count': len(ranked_experienced),
            'fresher_count': len(ranked_freshers),
            'ranked_candidates': all_ranked,
            'ranking_method': 'smart_ml_with_fresher_support'
        }), 200
        
    except Exception as e:
        print(f"❌ Error ranking candidates: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/social-proof/<candidate_id>', methods=['GET'])
@jwt_required()
def get_social_proof(candidate_id):
    """
    Calculate social proof score for a candidate
    GET /api/ai-interview-v2/social-proof/{candidate_id}
    """
    try:
        user_id, role = get_user_info(get_jwt_identity())
        
        if role not in ['company', 'recruiter', 'admin']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = get_db()
        candidate = db['candidates'].find_one({'user_id': candidate_id})
        
        if not candidate:
            return jsonify({'error': 'Candidate not found'}), 404
        
        # Calculate social proof
        linkedin_profile = candidate.get('linkedin_profile')
        social_proof = calculate_social_proof_score(candidate, linkedin_profile)
        
        return jsonify(social_proof), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# FLAN-T5 DYNAMIC INTERVIEW ENGINE
# ============================================================================

@bp.route('/flan-t5/generate', methods=['POST'])
@jwt_required()
def flan_t5_generate_question():
    """
    Generate a single interview question using Flan-T5 for a specific skill gap.

    POST /api/ai-interview-v2/flan-t5/generate
    Body: {
        "skill_name": "Docker",
        "job_role": "DevOps Engineer",
        "difficulty_level": "medium"   // optional, defaults to "medium"
    }

    Returns: { generated_question, model_answer, skill, difficulty, source }
    """
    try:
        if not FLAN_T5_ROUTES:
            return jsonify({'error': 'Flan-T5 service not available'}), 503

        user_id, role = get_user_info(get_jwt_identity())

        data = request.get_json()
        skill_name = data.get('skill_name')
        job_role = data.get('job_role')
        difficulty_level = data.get('difficulty_level', 'medium')

        if not skill_name or not job_role:
            return jsonify({'error': 'skill_name and job_role are required'}), 400

        if difficulty_level not in ('easy', 'medium', 'hard'):
            return jsonify({'error': 'difficulty_level must be easy, medium, or hard'}), 400

        generator = get_generator()
        result = generator.generate(
            skill_name=skill_name,
            job_role=job_role,
            difficulty_level=difficulty_level,
        )

        return jsonify(result), 200

    except Exception as e:
        logger.exception(f"Flan-T5 generate failed: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/flan-t5/gap-interview', methods=['POST'])
@jwt_required()
def flan_t5_gap_interview():
    """
    Full Gap Analysis → Flan-T5 interview question generation pipeline.

    POST /api/ai-interview-v2/flan-t5/gap-interview
    Body: {
        "job_id": "job123",
        "candidate_id": "candidate456",
        "difficulty_level": "medium",   // optional
        "max_questions": 10             // optional
    }

    Flow:
      1. Fetch job required_skills + candidate skills from DB
      2. probe_zone = job_skills - candidate_skills  (Set Theory)
      3. For each missing skill → Flan-T5 generates question + model answer
      4. Returns gap analysis + generated questions
    """
    try:
        if not FLAN_T5_ROUTES:
            return jsonify({'error': 'Flan-T5 service not available'}), 503

        user_id, role = get_user_info(get_jwt_identity())

        if role not in ['company', 'recruiter', 'admin']:
            return jsonify({'error': 'Only recruiters can generate gap-based interviews'}), 403

        data = request.get_json()
        job_id = data.get('job_id')
        candidate_id = data.get('candidate_id')
        difficulty_level = data.get('difficulty_level', 'medium')
        max_questions = data.get('max_questions', 10)

        if not job_id or not candidate_id:
            return jsonify({'error': 'job_id and candidate_id are required'}), 400

        db = get_db()

        # Fetch job
        job = db['jobs'].find_one({'_id': ObjectId(job_id)})
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        # Verify ownership
        if str(job.get('recruiter_id')) != user_id and role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403

        # Fetch candidate
        candidate = db['candidates'].find_one({'user_id': candidate_id})
        if not candidate:
            return jsonify({'error': 'Candidate not found'}), 404

        job_skills = [s.strip() for s in job.get('required_skills', []) if s]
        candidate_skills = [s.strip() for s in candidate.get('skills', []) if s]

        if not job_skills:
            return jsonify({'error': 'Job has no required_skills defined'}), 400

        # Run full pipeline
        result = generate_gap_based_questions(
            job_required_skills=job_skills,
            candidate_skills=candidate_skills,
            job_role=job.get('title', 'Software Developer'),
            difficulty_level=difficulty_level,
            max_questions=max_questions,
        )

        # Persist to DB
        interview_doc = {
            'job_id': job_id,
            'candidate_id': candidate_id,
            'job_title': job.get('title'),
            'gap_analysis': result['gap_analysis'],
            'questions': result['generated_questions'],
            'summary': result['summary'],
            'created_at': datetime.utcnow(),
            'created_by': user_id,
            'version': 'flan-t5-gap',
            'is_active': True,
        }
        insert_result = db['interview_questions'].insert_one(interview_doc)

        return jsonify({
            'message': 'Gap-based interview questions generated successfully 🧠',
            'interview_set_id': str(insert_result.inserted_id),
            **result,
        }), 201

    except Exception as e:
        logger.exception(f"Flan-T5 gap interview failed: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/flan-t5/evaluate-answer', methods=['POST'])
@jwt_required()
def flan_t5_evaluate_answer():
    """
    Evaluate a candidate's answer using SBERT cosine similarity
    against the Flan-T5 generated model answer.

    POST /api/ai-interview-v2/flan-t5/evaluate-answer
    Body: {
        "candidate_answer": "My answer text...",
        "model_answer": "The reference answer from Flan-T5...",
        "threshold": 0.70   // optional, defaults to 0.70
    }

    Returns: {
        similarity_score, passed, threshold, evaluation_method, feedback
    }
    """
    try:
        if not FLAN_T5_ROUTES:
            return jsonify({'error': 'Flan-T5 service not available'}), 503

        data = request.get_json()
        candidate_answer = data.get('candidate_answer', '')
        model_answer = data.get('model_answer', '')
        threshold = data.get('threshold', 0.70)

        if not candidate_answer:
            return jsonify({'error': 'candidate_answer is required'}), 400
        if not model_answer:
            return jsonify({'error': 'model_answer is required'}), 400

        generator = get_generator()
        evaluation = generator.evaluate_answer(
            candidate_answer=candidate_answer,
            model_answer=model_answer,
            threshold=threshold,
        )

        return jsonify(evaluation), 200

    except Exception as e:
        logger.exception(f"Flan-T5 answer evaluation failed: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/flan-t5/full-interview', methods=['POST'])
@jwt_required()
def flan_t5_full_interview():
    """
    Submit a candidate answer for a Flan-T5 generated question and get
    full evaluation (SBERT cosine similarity + score).

    POST /api/ai-interview-v2/flan-t5/full-interview
    Body: {
        "interview_set_id": "...",
        "question_index": 0,
        "candidate_answer": "My answer..."
    }

    Flow:
      1. Fetch the interview set from DB
      2. Get the question + model_answer at question_index
      3. SBERT-embed candidate_answer and model_answer
      4. Cosine similarity → threshold 0.70
      5. Store result and return score
    """
    try:
        if not FLAN_T5_ROUTES:
            return jsonify({'error': 'Flan-T5 service not available'}), 503

        user_id, role = get_user_info(get_jwt_identity())

        data = request.get_json()
        interview_set_id = data.get('interview_set_id')
        question_index = data.get('question_index', 0)
        candidate_answer = data.get('candidate_answer', '')

        if not interview_set_id:
            return jsonify({'error': 'interview_set_id is required'}), 400
        if not candidate_answer:
            return jsonify({'error': 'candidate_answer is required'}), 400

        db = get_db()
        interview_set = db['interview_questions'].find_one({'_id': ObjectId(interview_set_id)})

        if not interview_set:
            return jsonify({'error': 'Interview set not found'}), 404

        questions = interview_set.get('questions', [])
        if question_index < 0 or question_index >= len(questions):
            return jsonify({'error': f'Invalid question_index. Must be 0-{len(questions) - 1}'}), 400

        question = questions[question_index]
        model_answer = question.get('model_answer', '')

        if not model_answer:
            return jsonify({'error': 'No model answer available for this question'}), 400

        # SBERT evaluation
        generator = get_generator()
        evaluation = generator.evaluate_answer(
            candidate_answer=candidate_answer,
            model_answer=model_answer,
            threshold=0.70,
        )

        # Store the answer + evaluation in DB
        answer_doc = {
            'interview_set_id': interview_set_id,
            'question_index': question_index,
            'question': question.get('question') or question.get('generated_question', ''),
            'skill': question.get('skill', ''),
            'candidate_answer': candidate_answer,
            'model_answer': model_answer,
            'evaluation': evaluation,
            'candidate_id': user_id,
            'answered_at': datetime.utcnow(),
        }
        db['interview_answers'].insert_one(answer_doc)

        # Update question status in interview set
        db['interview_questions'].update_one(
            {'_id': ObjectId(interview_set_id)},
            {'$set': {
                f'questions.{question_index}.candidate_answer': candidate_answer,
                f'questions.{question_index}.evaluation': evaluation,
                f'questions.{question_index}.answered_at': datetime.utcnow().isoformat(),
            }}
        )

        return jsonify({
            'question': question.get('question') or question.get('generated_question', ''),
            'skill': question.get('skill', ''),
            'candidate_answer': candidate_answer,
            'evaluation': evaluation,
        }), 200

    except Exception as e:
        logger.exception(f"Flan-T5 full interview evaluation failed: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/flan-t5/status', methods=['GET'])
@jwt_required()
def flan_t5_status():
    """
    Check Flan-T5 engine status — whether models are loaded and ready.

    GET /api/ai-interview-v2/flan-t5/status
    """
    try:
        if not FLAN_T5_ROUTES:
            return jsonify({
                'flan_t5_available': False,
                'sbert_available': False,
                'message': 'Flan-T5 service module not importable',
            }), 200

        from backend.services.flan_t5_service import FLAN_T5_AVAILABLE, SBERT_AVAILABLE

        generator = get_generator()

        return jsonify({
            'flan_t5_available': FLAN_T5_AVAILABLE,
            'flan_t5_model_loaded': generator.is_available,
            'sbert_available': SBERT_AVAILABLE,
            'sbert_model_loaded': generator.sbert is not None,
            'evaluation_threshold': 0.70,
            'message': 'Flan-T5 engine operational' if generator.is_available else 'Using fallback templates',
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
