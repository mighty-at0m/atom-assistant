import argparse
import os
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

RATE = 16000


def record_audio(seconds, label):
    print(f"\n{label}")
    input("Press Enter when ready, then speak or stay quiet for the recording.")
    audio = sd.rec(int(seconds * RATE), samplerate=RATE, channels=1, dtype="int16")
    sd.wait()
    return audio


def save_wav(path: Path, audio: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(RATE)
        wav_file.writeframes(audio.astype(np.int16).tobytes())


def collect_positive(root: Path, count: int, seconds: float):
    folder = root / "positive"
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(1, count + 1):
        print(f"\nPositive sample {index}/{count}")
        print("Say the exact phrase: 'hey atom'")
        audio = record_audio(seconds, "Recording...")
        save_wav(folder / f"sample_{index:02d}.wav", audio)
        print(f"Saved {folder / f'sample_{index:02d}.wav'}")


def collect_negative(root: Path, count: int, seconds: float):
    folder = root / "negative"
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(1, count + 1):
        print(f"\nNegative sample {index}/{count}")
        print("Stay silent for a moment or record room noise / random speech without saying the wake word.")
        audio = record_audio(seconds, "Recording ambient noise...")
        save_wav(folder / f"sample_{index:02d}.wav", audio)
        print(f"Saved {folder / f'sample_{index:02d}.wav'}")


def main():
    parser = argparse.ArgumentParser(description="Record and save positive and negative wake-word samples.")
    parser.add_argument("--root", default="wake_train", help="folder to store wake samples")
    parser.add_argument("--positive", type=int, default=30, help="number of positive samples to record")
    parser.add_argument("--negative", type=int, default=30, help="number of negative samples to record")
    parser.add_argument("--seconds", type=float, default=2.0, help="seconds to record per sample")
    args = parser.parse_args()

    root = Path(args.root)
    print(f"Collecting into {root.resolve()}")
    print("Use the exact phrase: 'hey atom'")
    print("For negative samples, record silence or unrelated speech, but do not say the phrase.")

    collect_positive(root, args.positive, args.seconds)
    collect_negative(root, args.negative, args.seconds)
    print("\nDone. Folder layout:")
    print(root / "positive")
    print(root / "negative")
    print("\nNext step: retrain the wake model with these files and replace hey_at_tom.onnx.")


if __name__ == "__main__":
    main()
