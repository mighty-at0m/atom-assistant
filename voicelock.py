import os
from pathlib import Path

import numpy as np
import torch
from speechbrain.inference.speaker import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy

HERE = Path(__file__).resolve().parent
MODEL_DIR = str(HERE / "models" / "ecapa")
VOICE_FILE = str(HERE / "my_voice.npy")
THRESHOLD = float(os.getenv("ATOM_VOICE_THRESHOLD", "0.20"))
# Real voice matches were scoring around 0.20 to 0.35, so the older 0.40 cutoff
# was too strict and rejected valid usage. Keep the default low and let the env
# override tune it without a code change.


def load_encoder():
    return EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=MODEL_DIR,
        run_opts={"device": "cpu"},
        local_strategy=LocalStrategy.COPY,
    )


def embed(enc, audio):
    wav = torch.from_numpy(audio.flatten().astype(np.float32) / 32768.0).unsqueeze(0)
    with torch.no_grad():
        e = enc.encode_batch(wav).squeeze().numpy()
    return e / np.linalg.norm(e)


_MINE = None


def voice_score(enc, audio):
    global _MINE
    if _MINE is None:
        if not Path(VOICE_FILE).exists():
            raise RuntimeError("No voice profile yet. Run: python enroll.py")
        _MINE = np.load(VOICE_FILE)
    mine = _MINE
    return float(np.dot(embed(enc, audio), mine))


def is_me(enc, audio):
    s = voice_score(enc, audio)
    return s >= THRESHOLD, s


ENC = None


def check(audio):
    global ENC
    if os.getenv("ATOM_DISABLE_VOICELOCK", "").lower() in {"1", "true", "yes", "on"}:
        return True, 1.0
    if ENC is None:
        ENC = load_encoder()
    return is_me(ENC, audio)


def disabled():
    return os.getenv("ATOM_DISABLE_VOICELOCK", "").lower() in {"1", "true", "yes", "on"}
