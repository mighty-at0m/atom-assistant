import io
import os
import wave

import numpy as np
import sounddevice as sd

from groqclient import get_client

RATE = 16000  # 16 kHz mono is what Whisper wants
MAX_SECONDS = float(os.getenv("ATOM_MAX_SECONDS", "25"))
# How long a pause ends your request. 1.8 s lets you stop to think mid-sentence.
SILENCE_SECONDS = float(os.getenv("ATOM_SILENCE_SECONDS", "1.8"))
MIN_SPEECH_RMS = 450
MAX_SPEECH_RMS = 1500  # never demand louder than this, even if calibration caught your voice
# Live preview sends extra Whisper requests while you talk and uses up Groq's
# free per-minute limit, so it is off unless ATOM_LIVE_PREVIEW=1.
LIVE_PREVIEW = os.getenv("ATOM_LIVE_PREVIEW", "").lower() in {"1", "true", "yes", "on"}


def record(seconds=None):
    if seconds is None:
        return record_until_silence(on_status=print)
    print(f"Recording {seconds}s... speak now")
    audio = sd.rec(int(seconds * RATE), samplerate=RATE, channels=1, dtype="int16")
    sd.wait()
    print("Done recording.")
    return audio


def record_until_silence(cancel_event=None, max_seconds=MAX_SECONDS, silence_seconds=SILENCE_SECONDS,
                         on_status=None, on_partial=None, wait_for_speech_seconds=6, on_level=None,
                         noise_rms=None, already_speaking=False):
    """Record until speech ends. Return None if nothing is said, it is cancelled, or the mic fails.

    Always stops after max_seconds, so a noisy room can never keep ATOM listening forever.
    noise_rms: room noise measured earlier (skips calibration, so talking straight away is fine).
    already_speaking: the user is mid-sentence (barge-in), so count it as speech from the start.
    """
    block = 512
    frames = []
    heard_speech = False
    silent_blocks = 0
    max_blocks = int(max_seconds * RATE / block)
    wait_blocks = int(wait_for_speech_seconds * RATE / block)
    required_silence = int(silence_seconds * RATE / block)
    calibration_blocks = 0 if noise_rms is not None else int(0.3 * RATE / block)
    floor = noise_rms if noise_rms is not None else 150.0
    speech_rms = min(MAX_SPEECH_RMS, max(MIN_SPEECH_RMS, floor * 3))
    heard_speech = bool(already_speaking)
    noise = []
    recent = []
    last_partial_at = 0
    partial_every_blocks = max(1, int(2.0 * RATE / block))
    if on_status:
        on_status("Listening... speak naturally")

    try:
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=block) as stream:
            for block_index in range(1, max_blocks + 1):
                if cancel_event and cancel_event.is_set():
                    return None
                frame, _ = stream.read(block)
                frames.append(frame.copy())
                rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
                if on_level:
                    on_level(min(1.0, rms / 3000))

                # Learn the room's noise level for the first third of a second. The quietest
                # part is used, so talking right after the wake word doesn't fool it.
                if block_index <= calibration_blocks:
                    noise.append(rms)
                    if block_index == calibration_blocks:
                        floor = float(np.percentile(noise, 20))
                        speech_rms = min(MAX_SPEECH_RMS, max(MIN_SPEECH_RMS, floor * 3))
                    if rms >= speech_rms * 1.5:
                        heard_speech = True
                    continue

                # Only real quiet counts as a pause; soft words and trailing syllables keep it open.
                # The quiet level follows the last 3 seconds, so a steady fan or hum still ends it.
                recent = (recent + [rms])[-int(3 * RATE / block):]
                quiet_rms = max(250.0, min(speech_rms * 0.8, min(floor, float(np.percentile(recent, 10))) * 1.8 + 60))
                if rms >= speech_rms:
                    heard_speech = True
                    silent_blocks = 0
                elif rms > quiet_rms:
                    silent_blocks = 0 if heard_speech else silent_blocks
                elif heard_speech:
                    silent_blocks += 1
                    if silent_blocks >= required_silence:
                        break
                elif block_index >= wait_blocks:
                    return None  # nobody spoke

                if (LIVE_PREVIEW and heard_speech and on_partial
                        and block_index - last_partial_at >= partial_every_blocks):
                    try:
                        text = transcribe(to_wav_bytes(np.concatenate(frames, axis=0)))
                        if text:
                            on_partial(text)
                    except Exception:
                        pass
                    last_partial_at = block_index
    except sd.PortAudioError as error:
        print("Command microphone error:", error)
        return None

    return np.concatenate(frames, axis=0) if heard_speech else None


def listen_for_barge_in(stop_event, on_level=None, speech_seconds=0.35):
    """While ATOM is thinking, wait for the user to start talking again.

    Returns the new speech (with the half second before it) once they finish, or None if
    stop_event is set first. Used to add extra words to a command that is already running.
    """
    block = 512
    needed = int(speech_seconds * RATE / block)
    history = []
    loud = 0
    try:
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=block) as stream:
            calibration = []
            while not stop_event.is_set():
                frame, _ = stream.read(block)
                rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
                history = (history + [frame.copy()])[-16:]
                if len(calibration) < 8:
                    calibration.append(rms)
                    continue
                threshold = max(MIN_SPEECH_RMS * 1.5, float(np.median(calibration)) * 4)
                loud = loud + 1 if rms >= threshold else 0
                if loud >= needed:
                    break
            else:
                return None
    except sd.PortAudioError:
        return None
    room = float(np.percentile(calibration, 20)) if calibration else None
    rest = record_until_silence(wait_for_speech_seconds=3, on_level=on_level, noise_rms=room,
                                already_speaking=True)
    head = np.concatenate(history, axis=0)
    return head if rest is None else np.concatenate([head, rest], axis=0)


def to_wav_bytes(audio):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.tobytes())
    return buf.getvalue()


def transcribe(wav_bytes):
    result = get_client().audio.transcriptions.create(
        file=("speech.wav", wav_bytes),
        model="whisper-large-v3-turbo",
        language="en",
    )
    return result.text.strip()


if __name__ == "__main__":
    print("You said:", transcribe(to_wav_bytes(record(5))))
