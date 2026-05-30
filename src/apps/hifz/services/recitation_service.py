from pathlib import Path
import os
import tempfile

import whisper
from django.utils.translation import gettext as _


model = whisper.load_model("base")


def transcribe_uploaded_audio(uploaded_file) -> str:
    suffix = Path(uploaded_file.name).suffix or ".webm"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        temp_path = temp_file.name

    try:
        result = model.transcribe(
            temp_path,
            language="ar",
            fp16=False,
            task="transcribe",
            temperature=0,
            initial_prompt=_("quran_recitation_prompt"),
        )
        return (result.get("text") or "").strip()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)