"""
Bias Auto-Correction Service — Phase 5 completion
====================================================
Implements an automated feedback loop that:
1. Reads fairness audit results
2. Detects which demographic groups are disadvantaged
3. Computes correction weights to re-balance scoring
4. Applies corrections and logs the adjustment

This closes the gap between "computing fairness metrics" and
"actually doing something about bias."

Author: Smart Hiring System
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.models.database import get_db

logger = logging.getLogger(__name__)

# Fairness thresholds
DEMOGRAPHIC_PARITY_THRESHOLD = 0.10   # max acceptable difference
DISPARATE_IMPACT_THRESHOLD = 0.80     # 80% rule
EQUAL_OPPORTUNITY_THRESHOLD = 0.10


class BiasCorrectionEngine:
    """
    Automated bias correction engine.

    Reads fairness metrics, identifies disadvantaged groups,
    and computes score adjustments to bring the hiring pipeline
    within fairness thresholds.
    """

    def __init__(self):
        self.db = None

    def _get_db(self):
        if self.db is None:
            self.db = get_db()
        return self.db

    # ── 1. Analyse current fairness state ──────────────────────────────────

    def analyze_bias(self, job_id: str = None) -> Dict:
        """
        Analyze current hiring data for bias.

        Returns:
            {
                "has_bias": bool,
                "demographic_parity": {...},
                "disparate_impact": {...},
                "disadvantaged_groups": [...],
                "recommended_corrections": {...},
            }
        """
        db = self._get_db()

        # Get all scored applications, optionally filtered by job
        query = {"overall_score": {"$exists": True}}
        if job_id:
            query["job_id"] = job_id

        applications = list(db["applications"].find(query))
        if len(applications) < 10:
            return {
                "has_bias": False,
                "message": "Insufficient data (need at least 10 scored applications).",
                "sample_size": len(applications),
            }

        # Get demographic data for candidates
        candidate_ids = list(set(a.get("candidate_id") for a in applications if a.get("candidate_id")))
        candidates = {
            str(c.get("user_id", c.get("_id"))): c
            for c in db["candidates"].find({"user_id": {"$in": candidate_ids}})
        }

        # Group scores by demographic attributes
        group_scores = {}  # {attribute: {group_value: [scores]}}
        group_selected = {}  # {attribute: {group_value: count_selected}}
        group_total = {}  # {attribute: {group_value: count_total}}

        threshold_score = 70  # Score above which a candidate is "selected"

        for app in applications:
            cid = app.get("candidate_id")
            candidate = candidates.get(cid, {})
            demographics = candidate.get("demographics", {})
            score = app.get("overall_score", 0)

            for attr in ["gender", "age_group", "ethnicity"]:
                group = demographics.get(attr, "unknown")
                if group == "prefer_not_to_say" or group == "unknown":
                    continue

                group_scores.setdefault(attr, {}).setdefault(group, []).append(score)
                group_total.setdefault(attr, {}).setdefault(group, 0)
                group_total[attr][group] += 1
                if score >= threshold_score:
                    group_selected.setdefault(attr, {}).setdefault(group, 0)
                    group_selected[attr][group] += 1

        # Calculate fairness metrics
        bias_report = {
            "has_bias": False,
            "sample_size": len(applications),
            "metrics": {},
            "disadvantaged_groups": [],
            "recommended_corrections": {},
        }

        for attr in group_scores:
            groups = group_scores[attr]
            if len(groups) < 2:
                continue

            # Selection rates
            selection_rates = {}
            for g in groups:
                total = group_total.get(attr, {}).get(g, 1)
                selected = group_selected.get(attr, {}).get(g, 0)
                selection_rates[g] = selected / total if total > 0 else 0

            # Demographic parity
            rates = list(selection_rates.values())
            dp_diff = max(rates) - min(rates) if rates else 0

            # Disparate impact
            max_rate = max(rates) if rates else 1
            min_rate = min(rates) if rates else 0
            di_ratio = min_rate / max_rate if max_rate > 0 else 1.0

            bias_report["metrics"][attr] = {
                "selection_rates": selection_rates,
                "demographic_parity_diff": round(dp_diff, 4),
                "disparate_impact_ratio": round(di_ratio, 4),
                "avg_scores": {g: round(sum(s) / len(s), 2) for g, s in groups.items()},
            }

            # Check thresholds
            if dp_diff > DEMOGRAPHIC_PARITY_THRESHOLD or di_ratio < DISPARATE_IMPACT_THRESHOLD:
                bias_report["has_bias"] = True

                # Identify disadvantaged group
                disadvantaged = min(selection_rates, key=selection_rates.get)
                advantaged = max(selection_rates, key=selection_rates.get)

                bias_report["disadvantaged_groups"].append({
                    "attribute": attr,
                    "disadvantaged_group": disadvantaged,
                    "advantaged_group": advantaged,
                    "gap": round(selection_rates[advantaged] - selection_rates[disadvantaged], 4),
                })

                # Compute correction weight
                if selection_rates[advantaged] > 0:
                    correction_factor = selection_rates[advantaged] / max(selection_rates[disadvantaged], 0.01)
                    correction_factor = min(correction_factor, 1.15)  # Cap at 15% boost
                    bias_report["recommended_corrections"][f"{attr}:{disadvantaged}"] = {
                        "group": disadvantaged,
                        "attribute": attr,
                        "correction_factor": round(correction_factor, 4),
                        "description": f"Boost scores for {attr}={disadvantaged} by {round((correction_factor - 1) * 100, 1)}%",
                    }

        return bias_report

    # ── 2. Apply corrections ────────────────────────────────────────────────

    def apply_corrections(self, job_id: str = None, dry_run: bool = True) -> Dict:
        """
        Apply bias corrections to scores.

        Args:
            job_id: optional job filter
            dry_run: if True, only preview changes without writing to DB

        Returns:
            { "corrections_applied": int, "adjustments": [...], "dry_run": bool }
        """
        analysis = self.analyze_bias(job_id)

        if not analysis.get("has_bias"):
            return {
                "corrections_applied": 0,
                "message": "No bias detected — no corrections needed.",
                "dry_run": dry_run,
            }

        corrections = analysis.get("recommended_corrections", {})
        if not corrections:
            return {
                "corrections_applied": 0,
                "message": "Bias detected but no corrections could be computed.",
                "dry_run": dry_run,
            }

        db = self._get_db()
        adjustments = []

        # Get candidate demographics mapping
        candidates_cursor = db["candidates"].find(
            {"demographics": {"$exists": True}},
            {"user_id": 1, "demographics": 1}
        )
        candidate_demographics = {
            str(c.get("user_id")): c.get("demographics", {})
            for c in candidates_cursor
        }

        # Get applications to correct
        query = {"overall_score": {"$exists": True}}
        if job_id:
            query["job_id"] = job_id

        applications = list(db["applications"].find(query))

        for app in applications:
            cid = app.get("candidate_id")
            demographics = candidate_demographics.get(cid, {})
            original_score = app.get("overall_score", 0)
            adjusted_score = original_score

            applied_factors = []
            for key, correction in corrections.items():
                attr = correction["attribute"]
                group = correction["group"]
                factor = correction["correction_factor"]

                if demographics.get(attr) == group:
                    adjusted_score = min(100, round(adjusted_score * factor, 2))
                    applied_factors.append({
                        "attribute": attr,
                        "group": group,
                        "factor": factor,
                    })

            if applied_factors and adjusted_score != original_score:
                adj = {
                    "application_id": str(app["_id"]),
                    "candidate_id": cid,
                    "original_score": original_score,
                    "adjusted_score": adjusted_score,
                    "factors_applied": applied_factors,
                }
                adjustments.append(adj)

                if not dry_run:
                    db["applications"].update_one(
                        {"_id": app["_id"]},
                        {"$set": {
                            "overall_score": adjusted_score,
                            "bias_correction_applied": True,
                            "bias_correction_log": {
                                "original_score": original_score,
                                "adjusted_score": adjusted_score,
                                "factors": applied_factors,
                                "applied_at": datetime.utcnow(),
                            }
                        }}
                    )

        # Log the correction run
        correction_log = {
            "job_id": job_id,
            "dry_run": dry_run,
            "analysis": analysis,
            "corrections_applied": len(adjustments),
            "adjustments_preview": adjustments[:20],  # Keep log manageable
            "created_at": datetime.utcnow(),
        }
        db["bias_correction_logs"].insert_one(correction_log)

        return {
            "corrections_applied": len(adjustments),
            "adjustments": adjustments,
            "dry_run": dry_run,
            "analysis_summary": {
                "has_bias": analysis["has_bias"],
                "disadvantaged_groups": analysis["disadvantaged_groups"],
            },
        }

    # ── 3. History ──────────────────────────────────────────────────────────

    def get_correction_history(self, job_id: str = None, limit: int = 20) -> List[Dict]:
        """Get recent bias correction log entries."""
        db = self._get_db()
        query = {}
        if job_id:
            query["job_id"] = job_id

        logs = list(
            db["bias_correction_logs"]
            .find(query)
            .sort("created_at", -1)
            .limit(limit)
        )
        for log in logs:
            log["_id"] = str(log["_id"])
        return logs


# Module-level singleton
bias_correction_engine = BiasCorrectionEngine()
