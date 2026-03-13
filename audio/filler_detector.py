import logging
from typing import Dict, List
import config
import numpy as np

logger = logging.getLogger(__name__)

def detect_fillers(transcript_data: Dict) -> Dict:
    """
    Filler word identification with contextual validation.
    Source: backend_SKILL.md Section 6 (audio/filler_detector.py).
    
    Args:
        transcript_data: Dict from transcriber { "words": List[Dict] }
        
    Returns:
        Dict: { "filler_count":              int,
                "filler_ratio":              float,
                "filler_ratio_normalized":   float,
                "filler_words_used":         Dict[str, int] }
    """
    words = transcript_data.get("words", [])
    total_words = len(words)
    
    if total_words == 0:
        return {
            "filler_count": 0,
            "filler_ratio": 0.0,
            "filler_ratio_normalized": 0.0,
            "filler_words_used": {}
        }

    filler_count = 0
    filler_words_used = {}
    
    # 1. Identify fillers with contextual rules
    for i, word_item in enumerate(words):
        word = word_item["word"].lower().strip(",.?!")
        start = word_item["start"]
        end = word_item["end"]
        
        # Check if word is in filler dictionary
        if word in config.FILLER_WORDS:
            is_filler = False
            
            # Rule: pause_before > 0.3s OR pause_after > 0.3s
            # Compute pauses
            pause_before = 0.0
            if i > 0:
                pause_before = start - words[i-1]["end"]
                
            pause_after = 0.0
            if i < total_words - 1:
                pause_after = words[i+1]["start"] - end
            
            if pause_before > config.FILLER_PAUSE_CONTEXT or pause_after > config.FILLER_PAUSE_CONTEXT:
                is_filler = True
                
            # Special case for "like": check for simple context if spacy not available
            # Rule: if followed by a noun (simplified: if not followed by a pause), 
            # might be valid. But the pause rule is usually a good proxy.
            
            if is_filler:
                filler_count += 1
                filler_words_used[word] = filler_words_used.get(word, 0) + 1
                
    # 2. Compute ratios
    filler_ratio = filler_count / total_words
    # Normalize: FillerRatioNormalized = min(FillerRatio / 0.20, 1)
    filler_ratio_normalized = float(np.clip(filler_ratio / config.FILLER_RATIO_CEILING, 0.0, 1.0))
    
    output = {
        "filler_count": filler_count,
        "filler_ratio": float(filler_ratio),
        "filler_ratio_normalized": filler_ratio_normalized,
        "filler_words_used": filler_words_used
    }
    
    logger.info(f"Filler detection complete: {filler_count} fillers found.")
    return output
