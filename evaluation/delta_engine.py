import numpy as np
import logging
from typing import Dict, Optional
import config

logger = logging.getLogger(__name__)

def classify_delta(delta: float) -> str:
    """Classifies a numeric change based on config thresholds."""
    if delta > config.SIGNIFICANT_IMPROVEMENT_THRESHOLD:
        return "Significant Improvement"
    if delta > config.MODERATE_IMPROVEMENT_THRESHOLD:
        return "Moderate Improvement"
    if delta < config.NOTICEABLE_DECLINE_THRESHOLD:
        return "Noticeable Decline"
    return "Stable"

def compute_deltas(current_scores: Dict, baseline: Optional[Dict]) -> Dict:
    """
    Delta computation + threshold-based classification.
    Source: backend_SKILL.md Section 6 (evaluation/delta_engine.py).
    
    Args:
        current_scores: Dict of current session fused scores.
        baseline: Dict of baseline scores or None.
        
    Returns:
        Dict: Progress comparison data.
    """
    if baseline is None:
        return {
            "headline": "Baseline Session",
            "is_first_session": True,
            "deltas": {}
        }

    deltas = {}
    
    # 1. Psychological & Skill Deltas (current - baseline)
    # Higher is better for all of these
    for field in ["confidence", "clarity", "engagement", "overall"]:
        curr = current_scores.get(field, 0.0)
        base = baseline.get(field, 0.0)
        diff = curr - base
        deltas[field] = {
            "change": float(diff),
            "label": classify_delta(diff)
        }
        
    # 2. Nervousness Delta (baseline - current)
    # Lower nervousness is better, so base - curr = improvement
    curr_n = current_scores.get("nervousness", 0.0)
    base_n = baseline.get("nervousness", 0.0)
    diff_n = base_n - curr_n
    deltas["nervousness"] = {
        "change": float(diff_n),
        "label": classify_delta(diff_n)
    }
    
    # 3. Behavioral Deltas (improvement-oriented directions)
    # Lower filler is better
    filler_change = baseline.get("filler_ratio", 0.0) - current_scores.get("filler_ratio", 0.0)
    # Lower pause is better
    pause_change = baseline.get("pause_ratio", 0.0) - current_scores.get("pause_ratio", 0.0)
    # Higher posture stability is better
    posture_change = current_scores.get("posture_stability_index", 0.0) - baseline.get("posture_stability_index", 0.0)
    
    deltas["behavioral"] = {
        "filler_reduction": {"change": float(filler_change), "label": classify_delta(filler_change)},
        "pause_optimization": {"change": float(pause_change), "label": classify_delta(pause_change)},
        "posture_stability": {"change": float(posture_change), "label": classify_delta(posture_change)}
    }

    # 4. Overall Headline
    headline = f"Overall performance is {deltas['overall']['label'].lower()}"
    
    output = {
        "headline": headline,
        "is_first_session": False,
        "deltas": deltas
    }
    
    logger.info("Deltas computed successfully.")
    return output
