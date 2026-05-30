import io
import librosa
import numpy as np
import soundfile as sf


def _load_audio_from_uploaded_file(audio_file):
    audio_file.seek(0)
    raw_bytes = audio_file.read()
    audio_file.seek(0)

    if not raw_bytes:
        return None, None

    data, sr = sf.read(io.BytesIO(raw_bytes), dtype="float32", always_2d=False)

    if data is None:
        return None, None

    if len(np.shape(data)) > 1:
        data = np.mean(data, axis=1)

    if sr != 16000:
        data = librosa.resample(data, orig_sr=sr, target_sr=16000)
        sr = 16000

    return data, sr


def detect_speech_presence(
    audio_file,
    min_rms: float = 0.0035,
    min_non_silent_ratio: float = 0.03,
    min_non_silent_duration: float = 0.18,
):
    try:
        y, sr = _load_audio_from_uploaded_file(audio_file)
    except Exception:
        return {
            "has_speech": True,
            "reason": "audio_guard_failed_open",
            "duration": 0.0,
            "rms": 0.0,
            "non_silent_ratio": 0.0,
            "non_silent_duration": 0.0,
        }

    if y is None or sr is None or len(y) == 0:
        return {
            "has_speech": False,
            "reason": "empty_audio",
            "duration": 0.0,
            "rms": 0.0,
            "non_silent_ratio": 0.0,
            "non_silent_duration": 0.0,
        }

    duration = len(y) / sr if sr else 0.0
    rms = float(np.sqrt(np.mean(np.square(y)))) if len(y) else 0.0

    if duration <= 0:
        return {
            "has_speech": False,
            "reason": "invalid_duration",
            "duration": 0.0,
            "rms": round(rms, 6),
            "non_silent_ratio": 0.0,
            "non_silent_duration": 0.0,
        }

    intervals = librosa.effects.split(
        y,
        top_db=38,
        frame_length=2048,
        hop_length=512,
    )

    non_silent_samples = 0
    for start, end in intervals:
        non_silent_samples += max(0, end - start)

    non_silent_duration = non_silent_samples / sr
    non_silent_ratio = non_silent_duration / duration if duration > 0 else 0.0

    has_speech = (
        rms >= min_rms
        and non_silent_ratio >= min_non_silent_ratio
        and non_silent_duration >= min_non_silent_duration
    )

    return {
        "has_speech": has_speech,
        "reason": "speech_detected" if has_speech else "mostly_silence",
        "duration": round(duration, 3),
        "rms": round(rms, 6),
        "non_silent_ratio": round(non_silent_ratio, 4),
        "non_silent_duration": round(non_silent_duration, 3),
    }