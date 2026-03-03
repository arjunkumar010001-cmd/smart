"""
Enhanced AI Interviewer Service - Dynamic Role-Specific Questioning
Generates personalized interview questions based on job roles, skills, and experience levels.

v2.1 — Expanded question banks (35+ per role) to support 25-30 questions per interview.
v2.2 — Flan-T5 integration for dynamic gap-based question generation.
       probe_zone = job_required_skills - candidate_skills → Flan-T5 prompt → question + answer.
       Falls back to static question bank if Flan-T5 unavailable.
"""

import random
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import re
import logging

from backend.services.question_banks import (
    ROLE_QUESTION_BANKS,
    UNIVERSAL_BEHAVIORAL_QUESTIONS,
)

# ── Flan-T5 integration (graceful — does not break if unavailable) ────────────
try:
    from backend.services.flan_t5_service import (
        FlanT5QuestionGenerator,
        run_gap_analysis,
        get_generator,
    )
    FLAN_T5_INTEGRATION = True
except ImportError:
    FLAN_T5_INTEGRATION = False

logger = logging.getLogger(__name__)


# ============================================================================
# COMPREHENSIVE ROLE-SPECIFIC QUESTION BANKS
# ============================================================================
# NOTE: Questions are imported from backend/services/question_banks.py
# ROLE_QUESTION_BANKS  — 35+ technical per role across 7-8 categories
# UNIVERSAL_BEHAVIORAL_QUESTIONS — 15 total

# ---------- backward-compat guard (if anyone references the old constant) ----
# The imported ROLE_QUESTION_BANKS is canonical.  No duplicate definition here.
# Legacy references:  ROLE_QUESTION_BANKS  and  UNIVERSAL_BEHAVIORAL_QUESTIONS
# are now re-exported from question_banks.py — see import above.
# =============================================================================
_LEGACY_PLACEHOLDER = True  # noqa: keep old line count stable for minimal diff


# ============================================================================
# ROLE DETECTION AND MAPPING
# ============================================================================

ROLE_KEYWORDS = {
    'software_developer': ['software', 'developer', 'programmer', 'backend', 'frontend', 'fullstack', 'full stack', 'engineer', 'sde', 'coding'],
    'data_analyst': ['data analyst', 'business analyst', 'analytics', 'bi developer', 'data visualization'],
    'data_scientist': ['data scientist', 'machine learning', 'ml engineer', 'ai engineer', 'deep learning', 'nlp'],
    'devops_engineer': ['devops', 'sre', 'site reliability', 'infrastructure', 'cloud engineer', 'platform engineer'],
    'product_manager': ['product manager', 'product owner', 'pm', 'product lead'],
    'ui_ux_designer': ['ui designer', 'ux designer', 'ui/ux', 'product designer', 'interaction designer']
}


def detect_role_from_job(job: Dict) -> str:
    """
    Intelligently detect the role category from job title and description
    """
    job_title = job.get('title', '').lower()
    job_desc = job.get('description', '').lower()
    combined_text = f"{job_title} {job_desc}"
    
    # Score each role category
    role_scores = {}
    for role, keywords in ROLE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in combined_text)
        if score > 0:
            role_scores[role] = score
    
    # Return role with highest score, default to software_developer
    if role_scores:
        return max(role_scores.items(), key=lambda x: x[1])[0]
    return 'software_developer'


# ============================================================================
# ENHANCED QUESTION GENERATION
# ============================================================================

def generate_dynamic_interview_questions(
    job: Dict,
    candidate: Optional[Dict] = None,
    num_questions: int = 25,
    include_behavioral: bool = True,
    difficulty_distribution: Optional[Dict] = None
) -> List[Dict]:
    """
    Generate highly personalized interview questions based on:
    - Job role and requirements
    - Candidate experience level
    - Required skills
    - Difficulty distribution
    
    Args:
        job: Job dictionary with title, description, required_skills, experience_level
        candidate: Optional candidate dictionary with skills, experience_years
        num_questions: Total number of questions to generate
        include_behavioral: Whether to include behavioral questions
        difficulty_distribution: {'easy': 0.2, 'medium': 0.5, 'hard': 0.3}
    
    Returns:
        List of personalized interview questions
    """
    
    # Detect role
    role = detect_role_from_job(job)
    print(f"🎯 Detected role: {role}")
    
    # Get role-specific question bank
    role_questions = ROLE_QUESTION_BANKS.get(role, ROLE_QUESTION_BANKS['software_developer'])
    
    # Determine candidate experience level
    experience_level = _determine_experience_level(job, candidate)
    print(f"📊 Experience level: {experience_level}")
    
    # Set difficulty distribution based on experience
    if not difficulty_distribution:
        if experience_level == 'entry':
            difficulty_distribution = {'easy': 0.5, 'medium': 0.4, 'hard': 0.1}
        elif experience_level == 'mid':
            difficulty_distribution = {'easy': 0.2, 'medium': 0.5, 'hard': 0.3}
        else:  # senior
            difficulty_distribution = {'easy': 0.1, 'medium': 0.4, 'hard': 0.5}
    
    # Calculate question counts
    behavioral_count = min(3, num_questions // 3) if include_behavioral else 0
    technical_count = num_questions - behavioral_count

    # ── Flan-T5 Gap-Based Question Generation ─────────────────────────────────
    # If Flan-T5 is available AND candidate skills info exists, run gap analysis
    # and generate dynamic questions for missing skills.  Static bank fills the rest.
    flan_t5_questions: List[Dict] = []
    flan_t5_count = 0

    if FLAN_T5_INTEGRATION and candidate:
        try:
            job_skills = [s.strip() for s in job.get('required_skills', []) if s]
            candidate_skills_list = [s.strip() for s in candidate.get('skills', []) if s]

            if job_skills and candidate_skills_list:
                gap = run_gap_analysis(job_skills, candidate_skills_list)
                missing_skills = gap.get('missing_skills', [])

                if missing_skills:
                    # Allocate up to 40% of technical slots to Flan-T5 gap questions
                    max_flan = max(1, int(technical_count * 0.4))
                    skills_to_probe = missing_skills[:max_flan]

                    # Map experience level to difficulty
                    difficulty_map = {
                        'entry': 'easy',
                        'mid': 'medium',
                        'senior': 'hard',
                    }
                    diff = difficulty_map.get(experience_level, 'medium')

                    generator = get_generator()
                    for skill in skills_to_probe:
                        result = generator.generate(
                            skill_name=skill,
                            job_role=job.get('title', 'Software Developer'),
                            difficulty_level=diff,
                        )
                        # Convert Flan-T5 output to question bank format
                        flan_q = {
                            'id': f'FLAN_{skill.upper().replace(" ", "_")}',
                            'question': result['generated_question'],
                            'difficulty': result.get('difficulty', diff),
                            'expected_keywords': [skill],
                            'time_limit_minutes': {'easy': 5, 'medium': 8, 'hard': 12}.get(diff, 8),
                            'points': {'easy': 5, 'medium': 10, 'hard': 15}.get(diff, 10),
                            'follow_up': f'Can you go deeper on your experience with {skill}?',
                            'category': 'gap_analysis',
                            'type': 'flan_t5_generated',
                            'source': result.get('source', 'flan-t5'),
                            'model_answer': result.get('model_answer', ''),
                            'skill': skill,
                        }
                        flan_t5_questions.append(flan_q)

                    flan_t5_count = len(flan_t5_questions)
                    logger.info(
                        f"🧠 Flan-T5 generated {flan_t5_count} gap-based questions "
                        f"for missing skills: {skills_to_probe}"
                    )
        except Exception as e:
            logger.warning(f"⚠️ Flan-T5 gap generation failed (using bank only): {e}")
            flan_t5_questions = []
            flan_t5_count = 0

    # Remaining technical slots filled from static question bank
    bank_count = technical_count - flan_t5_count

    # Generate technical questions from bank
    technical_questions = _generate_technical_questions(
        role_questions,
        bank_count,
        difficulty_distribution,
        job,
        candidate
    )

    # Merge: Flan-T5 gap questions first, then bank questions
    technical_questions = flan_t5_questions + technical_questions
    
    # Generate behavioral questions
    behavioral_questions = []
    if include_behavioral:
        behavioral_questions = _generate_behavioral_questions(
            behavioral_count,
            experience_level
        )
    
    # Combine and add metadata
    all_questions = technical_questions + behavioral_questions
    
    # Add job-specific context
    for q in all_questions:
        q['job_title'] = job.get('title')
        q['job_id'] = str(job.get('_id', ''))
        q['generated_at'] = datetime.utcnow().isoformat()
        q['candidate_level'] = experience_level
    
    print(f"✅ Generated {len(all_questions)} questions "
          f"({len(technical_questions)} technical [{flan_t5_count} Flan-T5 + {len(technical_questions) - flan_t5_count} bank], "
          f"{len(behavioral_questions)} behavioral)")
    
    return all_questions


def _determine_experience_level(job: Dict, candidate: Optional[Dict]) -> str:
    """
    Determine appropriate experience level for question difficulty
    """
    # Check job requirements first
    job_min_exp = job.get('min_experience_years', 0)
    job_title = job.get('title', '').lower()
    
    # Determine from job posting
    if 'senior' in job_title or 'lead' in job_title or 'principal' in job_title or job_min_exp >= 5:
        job_level = 'senior'
    elif 'junior' in job_title or 'entry' in job_title or 'associate' in job_title or job_min_exp <= 1:
        job_level = 'entry'
    else:
        job_level = 'mid'
    
    # If candidate info available, consider it
    if candidate:
        candidate_exp = candidate.get('experience_years', 0)
        if candidate_exp >= 5:
            candidate_level = 'senior'
        elif candidate_exp <= 1:
            candidate_level = 'entry'
        else:
            candidate_level = 'mid'
        
        # Use the higher of job or candidate level (challenge them appropriately)
        levels = {'entry': 1, 'mid': 2, 'senior': 3}
        return 'entry' if levels.get(job_level, 2) > levels.get(candidate_level, 2) else candidate_level
    
    return job_level


def _generate_technical_questions(
    role_questions: Dict,
    count: int,
    difficulty_dist: Dict,
    job: Dict,
    candidate: Optional[Dict]
) -> List[Dict]:
    """
    Generate technical questions based on role and difficulty distribution
    """
    questions = []
    
    # Flatten all role questions
    all_role_questions = []
    for category, category_questions in role_questions.items():
        for q in category_questions:
            q['category'] = category
            all_role_questions.append(q)
    
    # Calculate how many of each difficulty
    easy_count = int(count * difficulty_dist.get('easy', 0.2))
    hard_count = int(count * difficulty_dist.get('hard', 0.3))
    medium_count = count - easy_count - hard_count
    
    # Select questions by difficulty
    easy_questions = [q for q in all_role_questions if q['difficulty'] == 'easy']
    medium_questions = [q for q in all_role_questions if q['difficulty'] == 'medium']
    hard_questions = [q for q in all_role_questions if q['difficulty'] == 'hard']
    
    # Randomly sample from each difficulty
    if easy_questions:
        questions.extend(random.sample(easy_questions, min(easy_count, len(easy_questions))))
    if medium_questions:
        questions.extend(random.sample(medium_questions, min(medium_count, len(medium_questions))))
    if hard_questions:
        questions.extend(random.sample(hard_questions, min(hard_count, len(hard_questions))))
    
    # If we don't have enough, fill with any available
    if len(questions) < count:
        remaining = [q for q in all_role_questions if q not in questions]
        questions.extend(random.sample(remaining, min(count - len(questions), len(remaining))))
    
    # Add points based on difficulty
    for q in questions:
        if q['difficulty'] == 'easy':
            q['points'] = 5
        elif q['difficulty'] == 'medium':
            q['points'] = 10
        else:
            q['points'] = 15
    
    return questions


def _generate_behavioral_questions(count: int, experience_level: str) -> List[Dict]:
    """
    Generate behavioral questions appropriate for experience level
    """
    # Filter questions by experience level
    if experience_level == 'entry':
        # For entry level, avoid questions requiring extensive experience
        suitable = [q for q in UNIVERSAL_BEHAVIORAL_QUESTIONS 
                   if q['category'] in ['learning_agility', 'achievement', 'problem_solving']]
    else:
        suitable = UNIVERSAL_BEHAVIORAL_QUESTIONS
    
    # Randomly select
    selected = random.sample(suitable, min(count, len(suitable)))
    
    # Add metadata
    for q in selected:
        q['type'] = 'behavioral'
        q['time_limit_minutes'] = 8 if q['difficulty'] == 'easy' else 12
        q['points'] = 10
    
    return selected


# ============================================================================
# ADVANCED ANSWER EVALUATION
# ============================================================================

def evaluate_answer_advanced(question: Dict, answer: str) -> Dict:
    """
    Enhanced answer evaluation with deeper analysis
    """
    if not answer or len(answer.strip()) < 10:
        return {
            'score': 0,
            'max_score': question.get('points', 10),
            'percentage': 0,
            'feedback': '❌ Answer too short or empty',
            'keyword_match_count': 0,
            'total_keywords': len(question.get('expected_keywords', [])),
            'strengths': [],
            'areas_for_improvement': ['Provide more detail', 'Address the question directly'],
            'follow_up_questions': [question.get('follow_up', '')]
        }
    
    answer_lower = answer.lower()
    expected_keywords = question.get('expected_keywords', [])
    
    # Keyword matching
    matched_keywords = [kw for kw in expected_keywords if kw.lower() in answer_lower]
    keyword_score = (len(matched_keywords) / len(expected_keywords)) * 100 if expected_keywords else 50
    
    # Length analysis (should be substantial but not rambling)
    word_count = len(answer.split())
    if word_count < 30:
        length_score = word_count / 30 * 100
        length_feedback = "Too brief - provide more detail"
    elif word_count > 500:
        length_score = 85  # Penalize excessive length slightly
        length_feedback = "Very detailed - ensure you're staying on topic"
    else:
        length_score = 100
        length_feedback = "Good length"
    
    # STAR method check for behavioral questions
    star_score = 0
    star_feedback = ""
    if question.get('star_required', False):
        star_components = {
            'situation': any(word in answer_lower for word in ['when', 'situation', 'context', 'background']),
            'task': any(word in answer_lower for word in ['needed', 'had to', 'responsible', 'goal', 'objective']),
            'action': any(word in answer_lower for word in ['i did', 'i implemented', 'i created', 'i developed', 'my approach']),
            'result': any(word in answer_lower for word in ['result', 'outcome', 'achieved', 'impact', 'improved', 'increased'])
        }
        star_score = (sum(star_components.values()) / 4) * 100
        missing_components = [k.upper() for k, v in star_components.items() if not v]
        if missing_components:
            star_feedback = f"Consider adding: {', '.join(missing_components)}"
    
    # Technical depth indicators
    technical_depth = any(word in answer_lower for word in 
                         ['because', 'therefore', 'however', 'specifically', 'for example', 'such as'])
    depth_score = 100 if technical_depth else 70
    
    # Calculate final score
    max_score = question.get('points', 10)
    if question.get('star_required'):
        final_percentage = (keyword_score * 0.4 + length_score * 0.2 + star_score * 0.3 + depth_score * 0.1)
    else:
        final_percentage = (keyword_score * 0.6 + length_score * 0.2 + depth_score * 0.2)
    
    final_score = (final_percentage / 100) * max_score
    
    # Generate feedback
    strengths = []
    improvements = []
    
    if len(matched_keywords) >= len(expected_keywords) * 0.7:
        strengths.append(f"✅ Covered key concepts: {', '.join(matched_keywords[:3])}")
    else:
        improvements.append(f"Missing key concepts: {', '.join([kw for kw in expected_keywords if kw not in matched_keywords][:3])}")
    
    if word_count >= 50:
        strengths.append("✅ Provided detailed explanation")
    else:
        improvements.append("Provide more detail and examples")
    
    if technical_depth:
        strengths.append("✅ Demonstrated reasoning and examples")
    else:
        improvements.append("Add more reasoning and concrete examples")
    
    if question.get('star_required'):
        if star_score >= 75:
            strengths.append("✅ Clear STAR structure")
        else:
            improvements.append(star_feedback)
    
    # Generate feedback summary
    if final_percentage >= 80:
        feedback = "🌟 Excellent answer! Strong understanding demonstrated."
    elif final_percentage >= 60:
        feedback = "👍 Good answer with room for improvement."
    elif final_percentage >= 40:
        feedback = "⚠️ Acceptable but needs more depth and detail."
    else:
        feedback = "❌ Insufficient answer. Please elaborate more."
    
    return {
        'score': round(final_score, 1),
        'max_score': max_score,
        'percentage': round(final_percentage, 1),
        'feedback': feedback,
        'detailed_scores': {
            'keyword_coverage': round(keyword_score, 1),
            'length_appropriateness': round(length_score, 1),
            'star_structure': round(star_score, 1) if question.get('star_required') else None,
            'technical_depth': round(depth_score, 1)
        },
        'keyword_match_count': len(matched_keywords),
        'total_keywords': len(expected_keywords),
        'matched_keywords': matched_keywords,
        'word_count': word_count,
        'strengths': strengths,
        'areas_for_improvement': improvements,
        'follow_up_questions': [question.get('follow_up', '')],
        'length_feedback': length_feedback
    }


# ============================================================================
# INTERVIEW SCHEDULE GENERATION
# ============================================================================

def create_interview_schedule_advanced(
    questions: List[Dict],
    total_duration_minutes: int = 60,
    include_breaks: bool = True
) -> Dict:
    """
    Create a detailed interview schedule with time allocation
    """
    # Calculate total question time
    total_question_time = sum(q.get('time_limit_minutes', 10) for q in questions)
    
    # Add intro (5 min) and outro (5 min)
    intro_time = 5
    outro_time = 5
    break_time = 5 if include_breaks and total_duration_minutes >= 45 else 0
    
    available_time = total_duration_minutes - intro_time - outro_time - break_time
    
    # Scale question times if needed
    scale_factor = available_time / total_question_time if total_question_time > available_time else 1
    
    # Build schedule
    schedule = {
        'total_duration_minutes': total_duration_minutes,
        'sections': [
            {
                'section': 'Introduction',
                'duration_minutes': intro_time,
                'description': 'Welcome, role overview, interview structure explanation'
            }
        ],
        'questions': [],
        'break_included': include_breaks
    }
    
    current_time = intro_time
    for i, q in enumerate(questions, 1):
        allocated_time = int(q.get('time_limit_minutes', 10) * scale_factor)
        schedule['questions'].append({
            'question_number': i,
            'question_id': q.get('id'),
            'question': q.get('question'),
            'start_time_minutes': current_time,
            'allocated_minutes': allocated_time,
            'difficulty': q.get('difficulty'),
            'points': q.get('points'),
            'category': q.get('category', q.get('type', 'technical'))
        })
        current_time += allocated_time
        
        # Add break after halfway point
        if include_breaks and i == len(questions) // 2:
            schedule['sections'].append({
                'section': 'Break',
                'duration_minutes': break_time,
                'start_time_minutes': current_time,
                'description': 'Short break'
            })
            current_time += break_time
    
    schedule['sections'].append({
        'section': 'Closing',
        'duration_minutes': outro_time,
        'start_time_minutes': current_time,
        'description': 'Q&A, next steps, thank you'
    })
    
    # Summary
    schedule['summary'] = {
        'total_questions': len(questions),
        'technical_questions': len([q for q in questions if q.get('type') != 'behavioral']),
        'behavioral_questions': len([q for q in questions if q.get('type') == 'behavioral']),
        'total_points': sum(q.get('points', 0) for q in questions),
        'difficulty_breakdown': {
            'easy': len([q for q in questions if q.get('difficulty') == 'easy']),
            'medium': len([q for q in questions if q.get('difficulty') == 'medium']),
            'hard': len([q for q in questions if q.get('difficulty') == 'hard'])
        }
    }
    
    return schedule


# ============================================================================
# PUBLIC API
# ============================================================================

# Keep backward compatibility
generate_interview_questions = generate_dynamic_interview_questions
evaluate_answer = evaluate_answer_advanced
create_interview_schedule = create_interview_schedule_advanced
