"""
Flan-T5 Dynamic Interview Question Generator
=============================================
Uses google/flan-t5-base from HuggingFace to dynamically generate
interview questions based on Gap Analysis (probe_zone = job_skills - candidate_skills).

Flow:
  1. Gap Analysis identifies missing skills (Set Theory — already built)
  2. Missing skill passed to Flan-T5 as instruction prompt
  3. Flan-T5 generates question + model answer
  4. Candidate answer evaluated via SBERT cosine similarity (threshold 0.70)
  5. If Flan-T5 fails, falls back to static question bank

Model is loaded ONCE at startup — not per request.

© 2025 Smart Hiring System — All Rights Reserved
"""

import logging
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Lazy imports — graceful degradation if libraries are absent ────────────────
FLAN_T5_AVAILABLE = False
_flan_t5_model = None
_flan_t5_tokenizer = None

SBERT_AVAILABLE = False
_sbert_model = None

try:
    from transformers import T5ForConditionalGeneration, T5Tokenizer
    FLAN_T5_AVAILABLE = True
    logger.info("✅ HuggingFace transformers available for Flan-T5")
except ImportError:
    logger.warning("⚠️ transformers not installed — Flan-T5 generation disabled")

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine
    import numpy as np
    SBERT_AVAILABLE = True
    logger.info("✅ sentence-transformers available for SBERT answer evaluation")
except ImportError:
    logger.warning("⚠️ sentence-transformers not installed — SBERT evaluation disabled")


# =============================================================================
# MODEL LOADING — called once at app startup
# =============================================================================

def load_flan_t5_model(model_name: str = "google/flan-t5-base") -> bool:
    """
    Load the Flan-T5 model and tokenizer into memory.
    Called once at Flask app startup via create_app().

    Returns True if successfully loaded, False otherwise.
    """
    global _flan_t5_model, _flan_t5_tokenizer, FLAN_T5_AVAILABLE

    if not FLAN_T5_AVAILABLE:
        logger.error("❌ Cannot load Flan-T5 — transformers library not installed")
        return False

    try:
        logger.info(f"🔄 Loading Flan-T5 model: {model_name} ...")
        t0 = time.time()

        _flan_t5_tokenizer = T5Tokenizer.from_pretrained(model_name)
        _flan_t5_model = T5ForConditionalGeneration.from_pretrained(model_name)
        _flan_t5_model.eval()  # Set to evaluation mode — no gradient computation

        elapsed = round(time.time() - t0, 2)
        logger.info(f"✅ Flan-T5 model loaded in {elapsed}s (params: {_flan_t5_model.num_parameters():,})")
        return True

    except Exception as e:
        logger.exception(f"❌ Failed to load Flan-T5 model: {e}")
        FLAN_T5_AVAILABLE = False
        return False


def load_sbert_model(model_name: str = "all-MiniLM-L6-v2") -> bool:
    """
    Load SBERT model for answer evaluation.
    Reuses existing model if already loaded elsewhere; otherwise loads fresh.
    """
    global _sbert_model, SBERT_AVAILABLE

    if not SBERT_AVAILABLE:
        logger.error("❌ Cannot load SBERT — sentence-transformers not installed")
        return False

    try:
        logger.info(f"🔄 Loading SBERT model: {model_name} ...")
        t0 = time.time()

        _sbert_model = SentenceTransformer(model_name)

        elapsed = round(time.time() - t0, 2)
        logger.info(f"✅ SBERT model loaded in {elapsed}s")
        return True

    except Exception as e:
        logger.exception(f"❌ Failed to load SBERT model: {e}")
        SBERT_AVAILABLE = False
        return False


# =============================================================================
# FLAN-T5 QUESTION GENERATOR CLASS
# =============================================================================

class FlanT5QuestionGenerator:
    """
    Generates dynamic interview questions using google/flan-t5-base.

    Usage:
        generator = FlanT5QuestionGenerator()
        result = generator.generate(
            skill_name="Docker",
            job_role="DevOps Engineer",
            difficulty_level="medium"
        )
        # result = {
        #     "generated_question": "...",
        #     "model_answer": "...",
        #     "skill": "Docker",
        #     "difficulty": "medium",
        #     "source": "flan-t5"
        # }
    """

    # Difficulty-aware prompt modifiers
    DIFFICULTY_PROMPTS = {
        "easy": "a beginner-level",
        "medium": "an intermediate-level",
        "hard": "an advanced expert-level",
    }

    # Maximum token lengths for generation
    QUESTION_MAX_TOKENS = 128
    ANSWER_MAX_TOKENS = 256

    def __init__(self):
        """Initialize with module-level models (loaded once at startup)."""
        self.model = _flan_t5_model
        self.tokenizer = _flan_t5_tokenizer
        self.sbert = _sbert_model

    @property
    def is_available(self) -> bool:
        """Check if Flan-T5 model is loaded and ready."""
        return self.model is not None and self.tokenizer is not None

    # ── Core generation ───────────────────────────────────────────────────────

    def generate(
        self,
        skill_name: str,
        job_role: str,
        difficulty_level: str = "medium",
    ) -> Dict:
        """
        Generate a single interview question + model answer for a missing skill.

        Args:
            skill_name:       The skill from probe_zone (gap analysis)
            job_role:         Target job role (e.g., "Backend Developer")
            difficulty_level: One of 'easy', 'medium', 'hard'

        Returns:
            Dict with keys: generated_question, model_answer, skill,
                            difficulty, source, generation_time_ms
        """
        if not self.is_available:
            logger.warning("Flan-T5 not loaded — returning fallback")
            return self._fallback(skill_name, job_role, difficulty_level)

        difficulty_label = self.DIFFICULTY_PROMPTS.get(
            difficulty_level, self.DIFFICULTY_PROMPTS["medium"]
        )

        # ── Build instruction prompts ─────────────────────────────────────────
        question_prompt = (
            f"Generate {difficulty_label} technical interview question "
            f"for a candidate missing the skill: {skill_name} "
            f"applying for {job_role}."
        )

        t0 = time.time()
        try:
            generated_question = self._run_inference(
                question_prompt, max_length=self.QUESTION_MAX_TOKENS
            )

            # Now generate a model answer for evaluation
            answer_prompt = (
                f"Provide a detailed correct answer to this interview question: "
                f"{generated_question}"
            )
            model_answer = self._run_inference(
                answer_prompt, max_length=self.ANSWER_MAX_TOKENS
            )

            elapsed_ms = round((time.time() - t0) * 1000, 1)

            return {
                "generated_question": generated_question,
                "model_answer": model_answer,
                "skill": skill_name,
                "job_role": job_role,
                "difficulty": difficulty_level,
                "source": "flan-t5",
                "generation_time_ms": elapsed_ms,
            }

        except Exception as e:
            logger.exception(f"Flan-T5 generation failed for skill={skill_name}: {e}")
            return self._fallback(skill_name, job_role, difficulty_level)

    def generate_batch(
        self,
        skills: List[str],
        job_role: str,
        difficulty_level: str = "medium",
    ) -> List[Dict]:
        """
        Generate questions for multiple missing skills (batch convenience).

        Args:
            skills:           List of skills from probe_zone
            job_role:         Target job role
            difficulty_level: Difficulty for all generated questions

        Returns:
            List of question dicts (one per skill)
        """
        results = []
        for skill in skills:
            result = self.generate(skill, job_role, difficulty_level)
            results.append(result)
        return results

    # ── SBERT answer evaluation ───────────────────────────────────────────────

    def evaluate_answer(
        self,
        candidate_answer: str,
        model_answer: str,
        threshold: float = 0.70,
    ) -> Dict:
        """
        Evaluate a candidate's answer against the Flan-T5 model answer
        using SBERT (all-MiniLM-L6-v2) cosine similarity.

        Args:
            candidate_answer: The candidate's textual response
            model_answer:     The Flan-T5 generated reference answer
            threshold:        Cosine similarity threshold (default 0.70)

        Returns:
            Dict with: similarity_score, passed, threshold, evaluation_method
        """
        if not candidate_answer or not candidate_answer.strip():
            return {
                "similarity_score": 0.0,
                "passed": False,
                "threshold": threshold,
                "evaluation_method": "empty_answer",
                "feedback": "No answer provided.",
            }

        if self.sbert is None or not SBERT_AVAILABLE:
            logger.warning("SBERT not available — falling back to keyword evaluation")
            return self._keyword_fallback_evaluation(candidate_answer, model_answer, threshold)

        try:
            # Encode both texts
            embeddings = self.sbert.encode(
                [candidate_answer, model_answer],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            # Cosine similarity between the two embeddings
            similarity = float(
                sklearn_cosine(
                    embeddings[0].reshape(1, -1),
                    embeddings[1].reshape(1, -1),
                )[0][0]
            )

            passed = similarity >= threshold

            # Generate feedback tier
            if similarity >= 0.85:
                feedback = "🌟 Excellent — comprehensive and accurate answer."
            elif similarity >= 0.70:
                feedback = "👍 Good — answer demonstrates solid understanding."
            elif similarity >= 0.50:
                feedback = "⚠️ Partial — answer covers some aspects but lacks depth."
            else:
                feedback = "❌ Insufficient — answer does not adequately address the question."

            return {
                "similarity_score": round(similarity, 4),
                "passed": passed,
                "threshold": threshold,
                "evaluation_method": "sbert_cosine_similarity",
                "feedback": feedback,
            }

        except Exception as e:
            logger.exception(f"SBERT evaluation failed: {e}")
            return self._keyword_fallback_evaluation(candidate_answer, model_answer, threshold)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _run_inference(self, prompt: str, max_length: int = 128) -> str:
        """Run a single Flan-T5 inference pass."""
        import torch

        input_ids = self.tokenizer(
            prompt, return_tensors="pt", max_length=512, truncation=True
        ).input_ids

        with torch.no_grad():
            outputs = self.model.generate(
                input_ids,
                max_length=max_length,
                num_beams=4,
                early_stopping=True,
                no_repeat_ngram_size=3,
                temperature=0.7,
                do_sample=False,  # beam search, deterministic
            )

        decoded = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        return decoded.strip()

    def _fallback(self, skill_name: str, job_role: str, difficulty_level: str) -> Dict:
        """
        Fallback when Flan-T5 is unavailable — return a template-based question
        that the static question bank can supplement.
        """
        templates = {
            "easy": (
                f"Can you explain what {skill_name} is and why it is important for a {job_role}?",
                f"{skill_name} is a key technology/skill used by {job_role} professionals. "
                f"It involves understanding the core concepts, basic usage patterns, "
                f"and how it fits into the broader technology stack.",
            ),
            "medium": (
                f"Describe how you would use {skill_name} in a real-world {job_role} project. "
                f"What are the key considerations?",
                f"In a {job_role} context, {skill_name} is applied by understanding its "
                f"architecture and integration patterns, handling common pitfalls, and "
                f"following best practices for production-grade implementations.",
            ),
            "hard": (
                f"Design a scalable solution using {skill_name} for a complex {job_role} "
                f"scenario. Discuss trade-offs, failure modes, and optimization strategies.",
                f"A scalable {skill_name} solution requires understanding distributed "
                f"systems principles, performance trade-offs, failure handling, "
                f"monitoring strategies, and optimization at both the code and "
                f"infrastructure levels.",
            ),
        }

        question, answer = templates.get(difficulty_level, templates["medium"])

        return {
            "generated_question": question,
            "model_answer": answer,
            "skill": skill_name,
            "job_role": job_role,
            "difficulty": difficulty_level,
            "source": "fallback_template",
            "generation_time_ms": 0,
        }

    def _keyword_fallback_evaluation(
        self, candidate_answer: str, model_answer: str, threshold: float
    ) -> Dict:
        """
        Simple keyword overlap evaluation when SBERT is unavailable.
        Uses Jaccard similarity on word tokens.
        """
        candidate_words = set(candidate_answer.lower().split())
        model_words = set(model_answer.lower().split())

        if not model_words:
            return {
                "similarity_score": 0.0,
                "passed": False,
                "threshold": threshold,
                "evaluation_method": "keyword_fallback",
                "feedback": "Could not evaluate — empty model answer.",
            }

        intersection = candidate_words & model_words
        union = candidate_words | model_words
        jaccard = len(intersection) / len(union) if union else 0.0

        # Scale Jaccard to approximate cosine range (Jaccard is typically lower)
        scaled_score = min(jaccard * 1.5, 1.0)
        passed = scaled_score >= threshold

        if scaled_score >= 0.70:
            feedback = "👍 Good keyword overlap with expected answer."
        elif scaled_score >= 0.40:
            feedback = "⚠️ Partial match — some relevant terms present."
        else:
            feedback = "❌ Low overlap — answer may not address the question."

        return {
            "similarity_score": round(scaled_score, 4),
            "passed": passed,
            "threshold": threshold,
            "evaluation_method": "keyword_fallback",
            "feedback": feedback,
        }


# =============================================================================
# GAP ANALYSIS INTEGRATION
# =============================================================================

def run_gap_analysis(job_required_skills: List[str], candidate_skills: List[str]) -> Dict:
    """
    Set Theory gap analysis: probe_zone = job_required_skills - candidate_skills

    Args:
        job_required_skills: Skills required by the job posting
        candidate_skills:    Skills the candidate possesses

    Returns:
        Dict with matched_skills, missing_skills (probe_zone), coverage_pct
    """
    job_set = set(s.lower().strip() for s in job_required_skills if s)
    candidate_set = set(s.lower().strip() for s in candidate_skills if s)

    matched = job_set & candidate_set
    probe_zone = job_set - candidate_set  # Missing skills

    coverage = (len(matched) / len(job_set) * 100) if job_set else 100.0

    return {
        "job_required_skills": sorted(job_set),
        "candidate_skills": sorted(candidate_set),
        "matched_skills": sorted(matched),
        "missing_skills": sorted(probe_zone),  # probe_zone
        "extra_skills": sorted(candidate_set - job_set),
        "coverage_percentage": round(coverage, 1),
        "total_required": len(job_set),
        "total_matched": len(matched),
        "total_missing": len(probe_zone),
    }


def generate_gap_based_questions(
    job_required_skills: List[str],
    candidate_skills: List[str],
    job_role: str,
    difficulty_level: str = "medium",
    max_questions: int = 10,
) -> Dict:
    """
    Full pipeline: Gap Analysis → Flan-T5 question generation.

    1. Run Set Theory gap analysis
    2. For each missing skill → generate Flan-T5 question
    3. Return questions + gap analysis metadata

    Args:
        job_required_skills: Skills required by the job
        candidate_skills:    Skills the candidate has
        job_role:            Target job title/role
        difficulty_level:    'easy' | 'medium' | 'hard'
        max_questions:       Max number of gap questions to generate

    Returns:
        Dict with gap_analysis, generated_questions, summary
    """
    # Step 1 — Gap Analysis
    gap = run_gap_analysis(job_required_skills, candidate_skills)

    # Step 2 — Generate questions for missing skills
    generator = FlanT5QuestionGenerator()
    missing = gap["missing_skills"][:max_questions]

    questions = generator.generate_batch(
        skills=missing,
        job_role=job_role,
        difficulty_level=difficulty_level,
    )

    # Add question metadata
    for i, q in enumerate(questions, 1):
        q["question_number"] = i
        q["points"] = {"easy": 5, "medium": 10, "hard": 15}.get(
            q.get("difficulty", "medium"), 10
        )
        q["time_limit_minutes"] = {"easy": 5, "medium": 8, "hard": 12}.get(
            q.get("difficulty", "medium"), 8
        )

    # Summary
    flan_count = sum(1 for q in questions if q.get("source") == "flan-t5")
    fallback_count = sum(1 for q in questions if q.get("source") == "fallback_template")

    return {
        "gap_analysis": gap,
        "generated_questions": questions,
        "summary": {
            "total_missing_skills": gap["total_missing"],
            "questions_generated": len(questions),
            "flan_t5_generated": flan_count,
            "fallback_generated": fallback_count,
            "job_role": job_role,
            "difficulty_level": difficulty_level,
            "coverage_percentage": gap["coverage_percentage"],
        },
    }


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

# Instantiated after models are loaded at startup
flan_t5_generator: Optional[FlanT5QuestionGenerator] = None


def get_generator() -> FlanT5QuestionGenerator:
    """Get the module-level FlanT5QuestionGenerator singleton."""
    global flan_t5_generator
    if flan_t5_generator is None:
        flan_t5_generator = FlanT5QuestionGenerator()
    return flan_t5_generator


def initialize_flan_t5(
    flan_model: str = "google/flan-t5-base",
    sbert_model: str = "all-MiniLM-L6-v2",
) -> Dict:
    """
    Initialize both models at app startup. Call this from create_app().

    Returns status dict with load results.
    """
    results = {}

    # Load Flan-T5
    results["flan_t5_loaded"] = load_flan_t5_model(flan_model)
    results["flan_t5_model"] = flan_model

    # Load SBERT for answer evaluation
    results["sbert_loaded"] = load_sbert_model(sbert_model)
    results["sbert_model"] = sbert_model

    # Create singleton generator
    global flan_t5_generator
    flan_t5_generator = FlanT5QuestionGenerator()

    results["generator_ready"] = flan_t5_generator.is_available

    if results["flan_t5_loaded"]:
        logger.info("🚀 Flan-T5 Question Generator fully initialized")
    else:
        logger.warning("⚠️ Flan-T5 unavailable — will use fallback templates")

    return results
