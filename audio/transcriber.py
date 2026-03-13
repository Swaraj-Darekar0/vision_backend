import assemblyai as aai
import logging
from typing import Dict, List
import config

logger = logging.getLogger(__name__)

# Initialize AssemblyAI client
if config.ASSEMBLYAI_KEY:
    aai.settings.api_key = config.ASSEMBLYAI_KEY
else:
    logger.warning("ASSEMBLYAI_API_KEY not found in config. Transcription will fail.")

def transcribe(audio_path: str) -> Dict:
    """
    AssemblyAI: audio file → transcript + word timestamps.
    Source: backend_SKILL.md Section 3 & 6.
    
    Args:
        audio_path: Path to standardized WAV file.
        
    Returns:
        Dict: { "full_text":    str,
                "segments":     List[Dict],  # {start: float, end: float, text: str}
                "words":        List[Dict],  # {word: str, start: float, end: float}
                "total_words":  int }
    """
    if not config.ASSEMBLYAI_KEY:
        raise RuntimeError("AssemblyAI API key is missing.")

    logger.info(f"Transcribing {audio_path} using AssemblyAI (disfluencies enabled)")
    
    try:
        # 1. Configure transcription options
        # Universal-3 Pro supports prompting for raw disfluency preservation

        transcription_config = aai.TranscriptionConfig(
            speech_models=["universal-3-pro"],
            prompt=config.ASSEMBLYAI_TRANSCRIPTION_PROMPT ,
            temperature=0.1
        )

        # 2. Perform transcription
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(audio_path, config=transcription_config)

        if transcript.status == aai.TranscriptStatus.error:
            raise ValueError(f"AssemblyAI Error: {transcript.error}")

        # 3. Process words with timestamps
        words_data = []
        for word in transcript.words:
            words_data.append({
                "word": word.text.lower(), # Store as lowercase for easier matching
                "start": float(word.start) / 1000.0, # Convert ms to seconds
                "end": float(word.end) / 1000.0
            })

        # 4. Extract segments (using utterance detection if possible, or mapping words)
        # For simplicity, we can use transcript.utterances if enabled, 
        # but basic segments are words grouped by pauses or sentences.
        # AssemblyAI provides 'utterances' if configured.
        
        segments = []
        # If utterances are not explicitly enabled, we treat the whole transcript as one segment
        # or we could implement basic chunking logic.
        # Let's assume one main segment for now if utterances aren't used.
        segments.append({
            "start": words_data[0]["start"] if words_data else 0.0,
            "end": words_data[-1]["end"] if words_data else 0.0,
            "text": transcript.text
        })

        output = {
            "full_text": transcript.text,
            "segments": segments,
            "words": words_data,
            "total_words": len(words_data)
        }

        logger.info(f"Transcription complete: {len(words_data)} words detected")
        return output

    except Exception as e:
        logger.error(f"AssemblyAI transcription failed: {e}")
        raise ValueError(f"Transcription failed: {e}")
