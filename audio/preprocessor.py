import os
import logging
import librosa
import soundfile as sf
from pydub import AudioSegment
import imageio_ffmpeg

from config import AUDIO_SAMPLE_RATE
from config import AUDIO_TRANSCRIPTION_BITRATE
from config import AUDIO_TRANSCRIPTION_FORMAT

logger = logging.getLogger(__name__)

# Tell PyDub where ffmpeg is
AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

def preprocess_audio(input_path: str) -> dict:
    """
    Standardizes audio for two downstream uses:
    - resampled WAV for local librosa analysis (normalized in acoustic_extractor)
    - compressed mono upload for remote transcription
    
    For .m4a files, uses the original file directly without transformation.
    """

    # Check if input is already .m4a - use directly without conversion
    if input_path.lower().endswith('.m4a'):
        logger.info("Input is .m4a format - using original file without transformation")
        return {
            "analysis_path": input_path,
            "transcription_path": input_path,
        }

    session_id = os.path.splitext(os.path.basename(input_path))[0]

    os.makedirs("tmp", exist_ok=True)

    temp_wav = f"tmp/{session_id}_temp.wav"
    analysis_path = f"tmp/{session_id}_processed.wav"
    transcription_path = f"tmp/{session_id}_transcription.{AUDIO_TRANSCRIPTION_FORMAT}"

    try:
        # 1️⃣ Extract audio and convert to mono WAV
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_channels(1).set_frame_rate(AUDIO_SAMPLE_RATE)

        audio.export(temp_wav, format="wav")

        # 2️⃣ Load audio with librosa and resample
        y, sr = librosa.load(temp_wav, sr=AUDIO_SAMPLE_RATE)

        # 3️⃣ Save standardized WAV for local DSP
        sf.write(analysis_path, y, AUDIO_SAMPLE_RATE)

        # 5️⃣ Export compressed speech file for remote transcription upload
        normalized_audio = AudioSegment.from_file(analysis_path)
        normalized_audio.export(
            transcription_path,
            format=AUDIO_TRANSCRIPTION_FORMAT,
            bitrate=AUDIO_TRANSCRIPTION_BITRATE,
        )

        # cleanup temp file
        if os.path.exists(temp_wav):
            os.remove(temp_wav)

        logger.info(
            "Preprocessed audio saved to analysis=%s transcription=%s",
            analysis_path,
            transcription_path,
        )

        return {
            "analysis_path": analysis_path,
            "transcription_path": transcription_path,
        }

    except Exception as e:
        logger.error(f"Audio preprocessing failed: {e}")
        raise ValueError(f"Failed to preprocess audio: {e}")
