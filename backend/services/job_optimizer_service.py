"""
AI Job Description Optimizer — Phase 1 completion
====================================================
Uses the existing LLM waterfall (Groq → Claude → OpenAI → static fallback)
to enhance job descriptions, suggest missing skills, optimize for inclusivity,
and generate SEO-friendly versions.

Author: Smart Hiring System
"""

import os
import json
import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _call_groq(prompt: str) -> Optional[str]:
    """Call Groq API."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.6,
                "max_tokens": 2000,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("Groq optimizer call failed: %s", e)
    return None


def _call_openai(prompt: str) -> Optional[str]:
    """Fallback to OpenAI."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        import requests
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.6,
                "max_tokens": 2000,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("OpenAI optimizer call failed: %s", e)
    return None


def optimize_job_description(
    title: str,
    description: str,
    required_skills: list = None,
    job_type: str = "Full-time",
    experience_required: int = 0,
) -> Dict:
    """
    Optimize a job description using AI.

    Returns:
        {
            "optimized_description": str,
            "suggested_skills": list,
            "inclusivity_score": int (0-100),
            "inclusivity_suggestions": list,
            "seo_keywords": list,
            "readability_notes": str,
        }
    """
    skills_str = ", ".join(required_skills) if required_skills else "Not specified"

    prompt = f"""You are an expert HR consultant and job posting optimizer. Analyze and improve the following job posting.

JOB TITLE: {title}
JOB TYPE: {job_type}
EXPERIENCE: {experience_required}+ years
LISTED SKILLS: {skills_str}
DESCRIPTION:
{description}

Return a JSON object with EXACTLY these keys:
1. "optimized_description" — A rewritten, improved job description that is clear, engaging, and professional. Keep it concise.
2. "suggested_skills" — An array of 3-5 additional skills that should be required or preferred but are missing.
3. "inclusivity_score" — An integer 0-100 rating how inclusive/bias-free the language is.
4. "inclusivity_suggestions" — An array of specific suggestions to make the posting more inclusive (e.g., removing gendered language, age bias).
5. "seo_keywords" — An array of 5-8 SEO keywords candidates would search for.
6. "readability_notes" — A single string with brief readability feedback.

Return ONLY valid JSON, no markdown or explanation."""

    # Waterfall: Groq → OpenAI → static fallback
    raw = _call_groq(prompt) or _call_openai(prompt)

    if raw:
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                result = json.loads(json_match.group())
                # Validate required keys
                for key in ["optimized_description", "suggested_skills", "inclusivity_score"]:
                    if key not in result:
                        raise ValueError(f"Missing key: {key}")
                return result
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse AI optimizer response: %s", e)

    # Static fallback
    return {
        "optimized_description": description,
        "suggested_skills": ["Communication", "Problem-solving", "Team collaboration"],
        "inclusivity_score": 70,
        "inclusivity_suggestions": [
            "Consider using gender-neutral language",
            "Avoid specifying exact years of experience — use ranges",
            "Replace 'must have' with 'ideally has' for non-critical skills",
        ],
        "seo_keywords": [title.lower(), job_type.lower(), "hiring", "career", "opportunity"],
        "readability_notes": "Consider breaking long paragraphs into bullet points for better readability.",
    }
