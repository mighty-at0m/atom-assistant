import io
import os
from pathlib import Path
import time
import wave

import numpy as np
import sounddevice as sd
from groq import Groq

RATE = 16000  # 16 kHz mono is what Whisper wants


def record(seconds=None):
    if seconds is None:
        return record_until_silence(max_seconds=None, on_status=lambda msg: print(msg))
    print(f"Recording {seconds}s... speak now")
    audio = sd.rec(int(seconds * RATE), samplerate=RATE, channels=1, dtype="int16")
    sd.wait()
    print("Done recording.")
    return audio


def record_until_silence(cancel_event=None, max_seconds=None, silence_seconds=1.0, on_status=None, on_partial=None):
    """Record until speech ends; return None if no speech is heard or cancelled."""
    block = 512
    frames = []
    heard_speech = False
    silent_blocks = 0
    max_blocks = None if max_seconds is None else int(max_seconds * RATE / block)
    required_silence = int(silence_seconds * RATE / block)
    last_partial_at = 0
    partial_every_blocks = max(1, int(2.0 * RATE / block))
    if on_status:
        on_status("Listening... speak naturally")

    try:
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=block) as stream:
            block_index = 0
            while max_blocks is None or block_index < max_blocks:
                if cancel_event and cancel_event.is_set():
                    return None
                frame, _ = stream.read(block)
                frames.append(frame.copy())
                block_index += 1
                rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
                if rms >= 450:
                    heard_speech = True
                    silent_blocks = 0
                elif heard_speech:
                    silent_blocks += 1
                    if silent_blocks >= required_silence:
                        break

                if heard_speech and on_partial and block_index - last_partial_at >= partial_every_blocks:
                    chunk = np.concatenate(frames[-partial_every_blocks:], axis=0)
                    if chunk.size > 0:
                        try:
                            text = transcribe(to_wav_bytes(chunk))
                            if text and text.strip():
                                on_partial(text.strip())
                                print("Partial:", text.strip())
                        except Exception:
                            pass
                    last_partial_at = block_index
    except sd.PortAudioError as error:
        print("Command microphone error:", error)
        return None

    return np.concatenate(frames, axis=0) if heard_speech else None


def to_wav_bytes(audio):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.tobytes())
    return buf.getvalue()


def transcribe(wav_bytes):
    key_file = Path(__file__).with_name("groq_key.txt")
    key = os.environ.get("GROQ_API_KEY") or (key_file.read_text().strip() if key_file.exists() else None)
    if not key:
        raise RuntimeError("Set GROQ_API_KEY or add the key file beside stt.py.")
    client = Groq(api_key=key)
    result = client.audio.transcriptions.create(
        file=("speech.wav", wav_bytes),
        model="whisper-large-v3-turbo",
        language="en",
    )
    return result.text.strip()


if __name__ == "__main__":
    text = transcribe(to_wav_bytes(record(5)))
    print("You said:", text)
