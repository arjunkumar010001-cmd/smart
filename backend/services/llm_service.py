"""
OpenAI GPT-4o-mini integration for Smart Hiring.
Job description generation, resume summarization, interview questions, rejection emails.
Uses in-memory cache and rate limiting; fallback templates when API unavailable.
Migrated from v1 (smart-hiring-system) into v2 enterprise codebase.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    OPENAI_AVAILABLE = False


class LLMService:
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if (OPENAI_AVAILABLE and api_key) else None
        self.model = "gpt-4o-mini"
        self._cache: Dict[str, tuple] = {}
        self._rate_limit: Dict[str, List[float]] = {}

    def _check_rate_limit(self, key: str, max_per_minute: int = 10) -> bool:
        now = time.time()
        cutoff = now - 60
        if key not in self._rate_limit:
            self._rate_limit[key] = []
        self._rate_limit[key] = [t for t in self._rate_limit[key] if t > cutoff]
        if len(self._rate_limit[key]) >= max_per_minute:
            logger.warning("Rate limit exceeded for %s", key)
            return False
        self._rate_limit[key].append(now)
        return True

    def _get_cached(self, cache_key: str) -> Optional[Any]:
        if cache_key in self._cache:
            data, expiry = self._cache[cache_key]
            if datetime.utcnow() < expiry:
                return data
        return None

    def _set_cache(self, cache_key: str, data: Any, ttl_days: int = 7) -> None:
        self._cache[cache_key] = (data, datetime.utcnow() + timedelta(days=ttl_days))

    # ── Job description generation ────────────────────────────────────────────

    def generate_job_description(
        self,
        job_title: str,
        skills: List[str],
        experience_level: str,
        company_culture: Optional[str] = None,
        benefits: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        cache_key = f"job_desc_{job_title}_{'-'.join(sorted(skills))}_{experience_level}"
        cached = self._get_cached(cache_key)
        if cached:
            return {**cached, "from_cache": True}
        if not self._check_rate_limit("generate_job_description"):
            return {**self._fallback_job_description(job_title, skills, experience_level), "from_cache": False}
        if not self.client:
            return {**self._fallback_job_description(job_title, skills, experience_level), "from_cache": False}
        try:
            prompt = f"""Create a professional, engaging job description for a {job_title} position.
Required skills: {', '.join(skills)}
Experience level: {experience_level}
"""
            if company_culture:
                prompt += f"\nCompany culture: {company_culture}"
            if benefits:
                prompt += f"\nBenefits: {', '.join(benefits)}"
            prompt += """
Structure: 1) Overview (2-3 sentences), 2) Key Responsibilities (4-6 bullets), 3) Required Qualifications, 4) Nice-to-Have, 5) What Makes This Role Great.
Use inclusive language. Be specific. Under 500 words. Clean HTML with headings and bullets."""

            t0 = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert recruiter writing job descriptions that attract top talent."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=1000,
            )
            description = response.choices[0].message.content
            metadata = {
                "model": self.model,
                "tokens_used": getattr(response.usage, "total_tokens", 0),
                "generation_time": time.time() - t0,
            }
            self._set_cache(cache_key, {"description": description, "metadata": metadata}, 7)
            return {"description": description, "metadata": metadata, "from_cache": False}
        except Exception as e:
            logger.exception("Job description generation failed: %s", e)
            return {**self._fallback_job_description(job_title, skills, experience_level), "from_cache": False}

    def _fallback_job_description(self, job_title: str, skills: List[str], experience_level: str) -> Dict[str, Any]:
        exp_map = {"entry": "Entry-level", "mid": "Mid-level (2-4 years)", "senior": "Senior (5+ years)", "lead": "Lead (7+ years)"}
        skills_ul = "".join([f"<li>Strong proficiency in {s}</li>" for s in skills[:10]])
        return {
            "description": f"""<h2>About the Role</h2>
<p>We're looking for a {job_title}. {exp_map.get(experience_level, '')}.</p>
<h3>Key Responsibilities</h3>
<ul><li>Design, develop, and maintain high-quality solutions</li><li>Collaborate with cross-functional teams</li><li>Write clean, maintainable code</li><li>Participate in code reviews</li></ul>
<h3>Required Qualifications</h3>
<ul>{skills_ul}<li>Excellent communication skills</li></ul>
<h3>Nice to Have</h3>
<ul><li>Open-source contributions</li><li>Mentoring experience</li></ul>
<h3>Why Join Us</h3>
<ul><li>Impactful projects</li><li>Growth opportunities</li></ul>""",
            "metadata": {"source": "fallback_template"},
        }

    # ── Resume summarization ──────────────────────────────────────────────────

    def summarize_resume(self, resume_text: str, max_words: int = 150) -> Dict[str, Any]:
        cache_key = f"resume_summary_{hash(resume_text[:500]) % (10**8)}"
        cached = self._get_cached(cache_key)
        if cached:
            return {**cached, "from_cache": True}
        if not self._check_rate_limit("summarize_resume") or not self.client:
            return {**self._fallback_resume_summary(resume_text), "from_cache": False}
        try:
            truncated = (resume_text or "")[:4000]
            prompt = f"""Analyze this resume and provide a concise summary in {max_words} words or less.
Resume:\n{truncated}
Provide as JSON: {{ "summary": "...", "key_skills": ["s1","s2"], "experience_level": "entry|mid|senior|lead", "years_experience": 0 }}"""
            t0 = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a recruitment analyst. Be factual and concise."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            out = {
                **result,
                "metadata": {"model": self.model, "tokens_used": getattr(response.usage, "total_tokens", 0), "generation_time": time.time() - t0},
            }
            self._set_cache(cache_key, out, 30)
            return {**out, "from_cache": False}
        except Exception as e:
            logger.exception("Resume summary failed: %s", e)
            return {**self._fallback_resume_summary(resume_text), "from_cache": False}

    def _fallback_resume_summary(self, resume_text: str) -> Dict[str, Any]:
        words = (resume_text or "").split()
        summary = " ".join(words[:100]) + ("..." if len(words) > 100 else "")
        return {"summary": summary, "key_skills": [], "experience_level": "unknown", "metadata": {"source": "fallback"}}

    # ── Interview questions ───────────────────────────────────────────────────

    def generate_interview_questions(
        self,
        job_skills: List[str],
        candidate_skills: List[str],
        role_level: str,
        num_questions: int = 8,
    ) -> Dict[str, Any]:
        matched = list(set(job_skills) & set(candidate_skills))[:10]
        gap = list(set(job_skills) - set(candidate_skills))[:10]
        cache_key = f"questions_{'-'.join(sorted(matched))}_{'-'.join(sorted(gap))}_{role_level}"
        cached = self._get_cached(cache_key)
        if cached:
            return {**cached, "from_cache": True}
        if not self._check_rate_limit("generate_interview_questions") or not self.client:
            return {**self._fallback_interview_questions(matched, gap, role_level), "from_cache": False}
        try:
            prompt = f"""Generate {num_questions} interview questions for a {role_level} role.
Candidate has: {', '.join(matched) or 'none'}. Job also requires: {', '.join(gap) or 'none'}.
Mix: technical depth, gap assessment, behavioral. For each give: question, category, skill, difficulty.
Format as JSON: {{ "questions": [ {{ "question": "...", "category": "...", "skill": "...", "difficulty": "easy|medium|hard" }} ] }}"""
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert technical interviewer."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(response.choices[0].message.content)
            questions = parsed.get("questions", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
            result = {"questions": questions[:num_questions], "metadata": {"model": self.model}}
            self._set_cache(cache_key, result, 7)
            return {**result, "from_cache": False}
        except Exception as e:
            logger.exception("Interview questions failed: %s", e)
            return {**self._fallback_interview_questions(matched, gap, role_level), "from_cache": False}

    def _fallback_interview_questions(
        self, matched: List[str], gap: List[str], role_level: str
    ) -> Dict[str, Any]:
        qs = [
            {"question": "Tell me about a challenging project you worked on.", "category": "behavioral", "skill": "general", "difficulty": "medium"},
            {"question": "How do you approach learning new technologies?", "category": "behavioral", "skill": "general", "difficulty": "easy"},
        ]
        for s in matched[:3]:
            qs.append({"question": f"Describe your experience with {s}.", "category": "depth_check", "skill": s, "difficulty": "medium"})
        for s in gap[:2]:
            qs.append({"question": f"The role requires {s}. What exposure do you have?", "category": "gap_assessment", "skill": s, "difficulty": "medium"})
        return {"questions": qs[:8], "metadata": {"source": "fallback"}}

    # ── Rejection email ───────────────────────────────────────────────────────

    def draft_rejection_email(self, candidate_name: str, job_title: str, reason: str = "other_candidates") -> Dict[str, Any]:
        cache_key = f"rejection_{reason}_{job_title}"
        cached = self._get_cached(cache_key)
        if cached:
            body = (cached.get("email_body") or "").replace("[CANDIDATE_NAME]", candidate_name)
            subj = (cached.get("subject") or "").replace("[JOB_TITLE]", job_title)
            return {"email_body": body, "subject": subj, "metadata": cached.get("metadata", {}), "from_cache": True}
        if not self._check_rate_limit("draft_rejection_email") or not self.client:
            return {**self._fallback_rejection_email(candidate_name, job_title, reason), "from_cache": False}
        reasons = {
            "other_candidates": "we moved forward with candidates whose experience aligned more closely",
            "skills_gap": "we were looking for more direct experience in specific areas",
            "experience_level": "we decided to pursue candidates with different experience levels",
        }
        try:
            prompt = f"""Write a kind, professional rejection email. Candidate: [CANDIDATE_NAME]. Position: {job_title}. Reason: {reasons.get(reason, reasons['other_candidates'])}. Warm tone, thank them, encourage future applications. Under 150 words. Format as JSON: {{ "subject": "...", "email_body": "HTML content" }}"""
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a compassionate HR professional."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            self._set_cache(cache_key, result, 30)
            body = (result.get("email_body") or "").replace("[CANDIDATE_NAME]", candidate_name)
            subj = (result.get("subject") or "").replace("[JOB_TITLE]", job_title)
            return {"email_body": body, "subject": subj, "metadata": {"model": self.model}, "from_cache": False}
        except Exception as e:
            logger.exception("Rejection email failed: %s", e)
            return {**self._fallback_rejection_email(candidate_name, job_title, reason), "from_cache": False}

    def _fallback_rejection_email(self, candidate_name: str, job_title: str, reason: str) -> Dict[str, Any]:
        return {
            "email_body": f"<p>Dear {candidate_name},</p><p>Thank you for your interest in the {job_title} position. After careful consideration, we have decided to move forward with other candidates. We encourage you to apply for future openings.</p><p>Best regards,<br>The Hiring Team</p>",
            "subject": f"Update on Your Application for {job_title}",
            "metadata": {"source": "fallback"},
        }
