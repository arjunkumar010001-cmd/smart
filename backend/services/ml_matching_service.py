"""
P0 ML: Job-Candidate Matching Service with Sentence-BERT
=========================================================
Production-ready semantic matching using sentence embeddings

Features:
- Sentence-BERT embeddings for semantic similarity
- TF-IDF fallback when sentence-transformers unavailable
- Cosine similarity scoring
- Skill extraction and matching
- Metrics logging for all ML operations

Author: Smart Hiring System Team
Date: January 2026
"""

import os
import re
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from config.scoring_config import ScoringConfig
from config.skill_ontology import SKILL_DATABASE, SKILL_ALIASES

# P0 FIX: Make numpy optional for Lite environments
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

# Configure logging
logger = logging.getLogger(__name__)

# Check if ML models should be disabled (for memory-constrained environments like Render free tier)
DISABLE_ML_MODELS = os.getenv('DISABLE_ML_MODELS', 'false').lower() == 'true' or not NUMPY_AVAILABLE

# Check if sentence-transformers is explicitly disabled
USE_SENTENCE_TRANSFORMERS = os.getenv('USE_SENTENCE_TRANSFORMERS', 'true').lower() == 'true'

# Try to import sentence-transformers (P0 ML requirement)
SBERT_AVAILABLE = False
sbert_model = None
if DISABLE_ML_MODELS:
    if not NUMPY_AVAILABLE:
        logger.warning("⚠️ Numpy missing - ML models disabled")
    else:
        logger.info("ℹ️ ML models disabled via DISABLE_ML_MODELS env var - using TF-IDF only")
elif not USE_SENTENCE_TRANSFORMERS:
    # Explicitly disabled via env var - this is intentional, not a warning
    logger.info("ℹ️ Sentence-transformers disabled via USE_SENTENCE_TRANSFORMERS=false - using TF-IDF")
else:
    try:
        from sentence_transformers import SentenceTransformer
        SBERT_AVAILABLE = True
        logger.info("✅ Sentence-BERT available for semantic matching")
    except (ImportError, AttributeError, Exception) as _sbert_err:
        logger.warning(f"⚠️ sentence-transformers not available ({_sbert_err}) - using TF-IDF fallback")

# Try to import scikit-learn for TF-IDF
SKLEARN_AVAILABLE = False
try:
    if NUMPY_AVAILABLE:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine
        SKLEARN_AVAILABLE = True
        logger.info("✅ scikit-learn available for TF-IDF matching")
    else:
        raise ImportError("Numpy missing")
except ImportError:
    logger.warning("⚠️ scikit-learn not installed - limited matching capability")


class MLMatchingMetrics:
    """Track ML matching metrics for monitoring"""
    def __init__(self):
        self.total_matches = 0
        self.sbert_matches = 0
        self.tfidf_matches = 0
        self.total_latency_ms = 0
        self.avg_score = 0
        self.scores_sum = 0
        
    def record_match(self, method: str, latency_ms: float, score: float):
        self.total_matches += 1
        if method == 'sbert':
            self.sbert_matches += 1
        else:
            self.tfidf_matches += 1
        self.total_latency_ms += latency_ms
        self.scores_sum += score
        self.avg_score = self.scores_sum / self.total_matches
        
    def get_stats(self) -> Dict:
        return {
            'total_matches': self.total_matches,
            'sbert_matches': self.sbert_matches,
            'tfidf_matches': self.tfidf_matches,
            'avg_latency_ms': round(self.total_latency_ms / self.total_matches, 2) if self.total_matches > 0 else 0,
            'avg_match_score': round(self.avg_score, 4),
            'sbert_available': SBERT_AVAILABLE,
            'sklearn_available': SKLEARN_AVAILABLE
        }


# Global metrics
ml_metrics = MLMatchingMetrics()


class MLMatchingService:
    """
    P0 ML: Production-ready job-candidate matching service
    
    Uses Sentence-BERT for semantic matching with TF-IDF fallback
    """
    
    # Gap 10: Skills loaded from unified skill_ontology.json
    SKILLS_MASTER = sorted(SKILL_DATABASE)
    
    # Gap 10: Aliases loaded from unified skill_ontology.json
    SKILL_ALIASES = SKILL_ALIASES
    
    def __init__(self):
        """Initialize ML matching service"""
        self.sbert_model = None
        self.tfidf_vectorizer = None
        self.metrics = ml_metrics
        self._initialize_models()
        
    def _initialize_models(self):
        """Initialize ML models (lazy loading for performance)"""
        global sbert_model
        
        if SBERT_AVAILABLE and sbert_model is None:
            try:
                logger.info("🔄 Loading Sentence-BERT model (all-MiniLM-L6-v2)...")
                start_time = time.time()
                sbert_model = SentenceTransformer('all-MiniLM-L6-v2')
                load_time = (time.time() - start_time) * 1000
                logger.info(f"✅ Sentence-BERT loaded in {load_time:.0f}ms")
            except Exception as e:
                logger.error(f"❌ Failed to load Sentence-BERT: {e}")
                
        self.sbert_model = sbert_model
        
        if SKLEARN_AVAILABLE:
            self.tfidf_vectorizer = TfidfVectorizer(
                stop_words='english',
                max_features=5000,
                ngram_range=(1, 2)
            )
            
    def compute_semantic_similarity(self, text1: str, text2: str) -> Tuple[float, str]:
        """
        Compute semantic similarity between two texts
        
        Returns:
            Tuple of (similarity_score, method_used)
        """
        start_time = time.time()
        
        # Try Sentence-BERT first (preferred)
        if self.sbert_model is not None:
            try:
                embeddings = self.sbert_model.encode([text1, text2])
                similarity = float(np.dot(embeddings[0], embeddings[1]) / 
                                  (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])))
                latency_ms = (time.time() - start_time) * 1000
                self.metrics.record_match('sbert', latency_ms, similarity)
                return similarity, 'sbert'
            except Exception as e:
                logger.warning(f"SBERT matching failed, falling back to TF-IDF: {e}")
        
        # Fall back to TF-IDF
        if SKLEARN_AVAILABLE and self.tfidf_vectorizer is not None:
            try:
                tfidf_matrix = self.tfidf_vectorizer.fit_transform([text1, text2])
                raw_similarity = float(sklearn_cosine(tfidf_matrix[0], tfidf_matrix[1])[0][0])
                # TF-IDF calibration: raw cosine between short job desc and long resume
                # is typically 0.05-0.25. Apply a ×1.4 boost (capped at 1.0) to bring
                # scores into a realistic 0.10-0.45 range before weighting.
                similarity = min(raw_similarity * 1.4, 1.0)
                latency_ms = (time.time() - start_time) * 1000
                self.metrics.record_match('tfidf', latency_ms, similarity)
                return similarity, 'tfidf'
            except Exception as e:
                logger.warning(f"TF-IDF matching failed: {e}")
        
        # Final fallback: keyword overlap
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        overlap = len(words1 & words2) / max(len(words1 | words2), 1)
        # Same calibration for keyword fallback
        overlap = min(overlap * 1.4, 1.0)
        latency_ms = (time.time() - start_time) * 1000
        self.metrics.record_match('keyword', latency_ms, overlap)
        return overlap, 'keyword'
    
    def extract_skills(self, text: str) -> List[str]:
        """Extract skills from text using pattern matching"""
        if not text:
            return []
        
        text_lower = text.lower()
        found_skills = []
        
        for skill in self.SKILLS_MASTER:
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, text_lower):
                found_skills.append(skill)
        
        return list(set(found_skills))
    
    def _normalize_skill(self, skill: str) -> str:
        """Normalize a skill name using the alias map."""
        s = skill.strip().lower()
        return self.SKILL_ALIASES.get(s, s)
    
    def _normalize_skill_set(self, skills: List[str]) -> set:
        """Normalize a list of skills, returning canonical names."""
        return set(self._normalize_skill(s) for s in skills if s.strip())
    
    def compute_skill_match(self, job_skills: List[str], candidate_skills: List[str]) -> Dict[str, Any]:
        """
        Compute skill match between job requirements and candidate skills.
        
        Uses alias-aware normalization so "ML" matches "machine learning",
        "react.js" matches "react", etc.
        
        Returns:
            Dict with match score, matched skills, and missing skills
        """
        if not job_skills:
            return {
                'score': 0.0,
                'matched_skills': [],
                'missing_skills': [],
                'extra_skills': candidate_skills
            }
        
        # Normalize through alias map
        job_set = self._normalize_skill_set(job_skills)
        candidate_set = self._normalize_skill_set(candidate_skills)
        
        matched = job_set & candidate_set
        missing = job_set - candidate_set
        extra = candidate_set - job_set
        
        score = len(matched) / len(job_set) if job_set else 0.0
        
        return {
            'score': score,
            'matched_skills': sorted(matched),
            'missing_skills': sorted(missing),
            'extra_skills': sorted(extra)
        }
    
    def compute_match_score(
        self, 
        job_description: str, 
        job_skills: List[str],
        resume_text: str, 
        candidate_skills: List[str],
        cci_score: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Compute comprehensive match score between job and candidate
        
        Args:
            job_description: Full job description text
            job_skills: Required skills for the job
            resume_text: Candidate's resume text
            candidate_skills: Candidate's extracted skills
            cci_score: Career Consistency Index (0-100), optional
            
        Returns:
            Dict with all scores, decision, and recommendations
        """
        start_time = time.time()
        
        # Semantic similarity (SBERT or TF-IDF)
        semantic_score, method = self.compute_semantic_similarity(job_description, resume_text)
        
        # Skill matching
        skill_result = self.compute_skill_match(job_skills, candidate_skills)
        skill_score = skill_result['score']
        
        # Calculate weighted overall score — canonical weights from ScoringConfig (Gap 6)
        if cci_score is not None:
            w = ScoringConfig.weights_for('similarity', 'skills', 'cci')
            cci_normalized = cci_score / 100.0
            overall_score = (
                w['similarity'] * semantic_score +
                w['skills'] * skill_score +
                w['cci'] * cci_normalized
            ) * 100
        else:
            w = ScoringConfig.weights_for_without_cci('similarity', 'skills')
            overall_score = (
                w['similarity'] * semantic_score +
                w['skills'] * skill_score
            ) * 100
        
        overall_score = round(overall_score, 2)
        
        # Decision based on score
        if overall_score >= 75:
            decision = "STRONG_MATCH"
            recommendation = "Highly recommended for interview"
        elif overall_score >= 60:
            decision = "GOOD_MATCH"
            recommendation = "Recommended for further review"
        elif overall_score >= 45:
            decision = "POTENTIAL_MATCH"
            recommendation = "Consider if other candidates are scarce"
        else:
            decision = "WEAK_MATCH"
            recommendation = "Skills gap may require training"
        
        # Generate improvement suggestions
        suggestions = []
        if skill_result['missing_skills']:
            suggestions.append(f"Missing key skills: {', '.join(skill_result['missing_skills'][:5])}")
        if semantic_score < 0.5:
            suggestions.append("Resume could better highlight relevant experience")
        
        latency_ms = (time.time() - start_time) * 1000
        
        return {
            'overall_score': overall_score,
            'semantic_score': round(semantic_score * 100, 2),
            'skill_score': round(skill_score * 100, 2),
            'cci_score': cci_score,
            'decision': decision,
            'recommendation': recommendation,
            'matched_skills': skill_result['matched_skills'],
            'missing_skills': skill_result['missing_skills'],
            'extra_skills': skill_result['extra_skills'][:10],  # Top 10 extra skills
            'suggestions': suggestions,
            'matching_method': method,
            'latency_ms': round(latency_ms, 2),
            'computed_at': datetime.utcnow().isoformat()
        }
    
    def get_metrics(self) -> Dict:
        """Get ML matching metrics"""
        return self.metrics.get_stats()


# Singleton instance
_ml_service = None

def get_ml_matching_service() -> MLMatchingService:
    """Get or create ML matching service singleton"""
    global _ml_service
    if _ml_service is None:
        _ml_service = MLMatchingService()
    return _ml_service


# Convenience function for backward compatibility
def analyze_candidate(
    job_description: str,
    job_skills: List[str],
    resume_text: str,
    resume_skills: List[str],
    cci_score: Optional[float] = None
) -> Dict[str, Any]:
    """
    Analyze candidate fit for a job (backward compatible function)
    
    Returns dict compatible with existing code:
        - overall_score
        - tfidf_score (now semantic_score)
        - skill_match
        - decision (now maps to 'Hire', 'Review', 'Reject')
        - matched_skills
        - recommendations
    """
    service = get_ml_matching_service()
    result = service.compute_match_score(
        job_description, job_skills, resume_text, resume_skills, cci_score
    )
    
    # Map to legacy format
    decision_map = {
        'STRONG_MATCH': 'Hire',
        'GOOD_MATCH': 'Review',
        'POTENTIAL_MATCH': 'Review',
        'WEAK_MATCH': 'Reject'
    }
    
    return {
        'overall_score': result['overall_score'],
        'tfidf_score': result['semantic_score'] / 100,  # Normalize to 0-1
        'skill_match': result['skill_score'] / 100,  # Normalize to 0-1
        'cci_score': result.get('cci_score'),
        'decision': decision_map.get(result['decision'], 'Review'),
        'matched_skills': result['matched_skills'],
        'missing_skills': result['missing_skills'],
        'recommendations': result['suggestions'],
        'matching_method': result['matching_method']
    }


if __name__ == '__main__':
    # Test the ML service
    print("\n" + "="*60)
    print("🧪 ML MATCHING SERVICE TEST")
    print("="*60 + "\n")
    
    service = get_ml_matching_service()
    
    job_desc = """
    We are looking for a Senior Python Developer with experience in Django and Flask.
    The ideal candidate should have strong skills in REST API development, PostgreSQL,
    and cloud deployment using AWS or Azure. Experience with machine learning is a plus.
    """
    
    resume = """
    Experienced software developer with 5 years in Python development.
    Proficient in Django, Flask, and FastAPI for web development.
    Strong database skills with PostgreSQL and MongoDB.
    Deployed multiple applications on AWS using Docker and Kubernetes.
    """
    
    job_skills = ['python', 'django', 'flask', 'rest api', 'postgresql', 'aws']
    resume_skills = ['python', 'django', 'flask', 'fastapi', 'postgresql', 'mongodb', 'aws', 'docker', 'kubernetes']
    
    result = service.compute_match_score(job_desc, job_skills, resume, resume_skills)
    
    print(f"Overall Score: {result['overall_score']}%")
    print(f"Semantic Score: {result['semantic_score']}%")
    print(f"Skill Score: {result['skill_score']}%")
    print(f"Decision: {result['decision']}")
    print(f"Recommendation: {result['recommendation']}")
    print(f"Matched Skills: {result['matched_skills']}")
    print(f"Missing Skills: {result['missing_skills']}")
    print(f"Method Used: {result['matching_method']}")
    print(f"Latency: {result['latency_ms']}ms")
    
    print("\n📊 Metrics:")
    print(service.get_metrics())
    print("\n" + "="*60)
