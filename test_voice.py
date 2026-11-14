from stt import record
from voicelock import load_encoder, is_me, THRESHOLD

enc = load_encoder()
print("Threshold:", THRESHOLD)
while True:
    input("Press Enter and speak for 5 seconds (Ctrl+C to quit)")
    ok, s = is_me(enc, record(5))
    print("Score:", round(s, 2), "-> ATOM" if ok else "-> NOT YOU")