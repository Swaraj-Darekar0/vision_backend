import os
import logging
import librosa
import soundfile as sf
from pydub import AudioSegment
import imageio_ffmpeg

from config import AUDIO_SAMPLE_RATE

logger = logging.getLogger(__name__)

# Tell PyDub where ffmpeg is
AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

def preprocess_audio(input_path: str) -> str:
    """
    Standardizes audio: mono, 16kHz, amplitude normalization.
    Converts any input format to clean WAV.
    """

    session_id = os.path.splitext(os.path.basename(input_path))[0]

    os.makedirs("tmp", exist_ok=True)

    temp_wav = f"tmp/{session_id}_temp.wav"
    output_path = f"tmp/{session_id}_processed.wav"

    try:
        # 1️⃣ Extract audio and convert to mono WAV
        audio = AudioSegment.from_file(input_path)

        audio = audio.set_channels(1)

        audio.export(temp_wav, format="wav")

        # 2️⃣ Load audio with librosa and resample
        y, sr = librosa.load(temp_wav, sr=AUDIO_SAMPLE_RATE)

        # 3️⃣ Normalize amplitude
        y_norm = librosa.util.normalize(y)

        # 4️⃣ Save standardized WAV
        sf.write(output_path, y_norm, AUDIO_SAMPLE_RATE)

        # cleanup temp file
        if os.path.exists(temp_wav):
            os.remove(temp_wav)

        logger.info(f"Preprocessed audio saved to {output_path}")

        return output_path

    except Exception as e:
        logger.error(f"Audio preprocessing failed: {e}")
        raise ValueError(f"Failed to preprocess audio: {e}")