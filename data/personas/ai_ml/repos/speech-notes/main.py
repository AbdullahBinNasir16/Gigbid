"""Meeting transcription and summarisation: core module."""
# uses ffmpeg


def run(config: dict) -> dict:
    """Entry point. Pipeline stages: ffmpeg, Speech Recognition, Whisper."""
    return {"status": "ok", "project": "speech-notes"}
