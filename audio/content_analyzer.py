import json
import logging
from typing import Dict, Optional
from groq import Groq
import config

logger = logging.getLogger(__name__)

# Initialize Groq client
_client: Optional[Groq] = None
if config.GROQ_API_KEY:
    try:
        _client = Groq(api_key=config.GROQ_API_KEY)
        logger.info("Groq client initialized for content analysis.")
    except Exception as e:
        logger.error(f"Failed to initialize Groq client in content_analyzer: {e}")
else:
    logger.warning("GROQ_API_KEY missing in config for content analysis.")

def analyze_content(transcript_data: Dict, topic_title: str) -> float:
    """
    Evaluates transcript relevance and reasoning against the topic title using Groq.
    
    Args:
        transcript_data: Dict from transcriber { "full_text": str }
        topic_title: The title of the presentation/topic.
        
    Returns:
        float: reasoning_clarity_score [0, 1]
    """
    full_text = transcript_data.get("full_text", "").strip()
    
    if not full_text:
        logger.warning("Empty transcript provided for content analysis. Returning 0.0")
        return 0.0
    
    if _client is None:
        logger.error("Groq client not available for content analysis. Falling back to 1.0 (neutral).")
        return 1.0

    try:
        user_content = f"Topic: {topic_title}\nTranscript: {full_text}"
        
        response = _client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": config.REASONING_CLARITY_PROMPT},
                {"role": "user",   "content": user_content}
            ],
            response_format={"type": "json_object"}
        )
        
        raw_content = response.choices[0].message.content
        data = json.loads(raw_content)
        
        score = data.get("reasoning_clarity_score", 1.0)
        
        # Ensure clamping [0, 1]
        import numpy as np
        final_score = float(np.clip(score, 0.0, 1.0))
        
        logger.info(f"Content analysis complete. Reasoning Clarity Score: {final_score}")
        return final_score

    except Exception as e:
        logger.error(f"Groq API call failed during content analysis: {e}")
        return 1.0 # Fallback to neutral/good to avoid penalizing user for API failures
