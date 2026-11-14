from wake import load_model, wait_for_wake

model = load_model()
print("Say 'Hey Jarvis'... (Ctrl+C to stop)")
while True:
    score = wait_for_wake(model)
    print(f"Wake word heard! score {score:.2f}")