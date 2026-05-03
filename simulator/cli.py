import argparse
import requests
import time
import random
import uuid

class AgentSimulator:
    def __init__(self, target_url):
        self.target_url = target_url

    def send_event(self, session_id, step, action, input_str, output_str, status="success", file=None, delay=0.35):
        payload = {
            "session_id": session_id,
            "timestamp": time.time(),
            "step": step,
            "action": action,
            "input": input_str,
            "output": output_str,
            "metadata": {
                "file": file,
                "status": status
            }
        }
        
        # Random Chaos: Duplicates (5% chance)
        num_sends = 2 if random.random() < 0.05 else 1
        
        # Random Chaos: Lag (5% chance)
        if random.random() < 0.05:
            payload["timestamp"] -= 10 # Send with old timestamp
            
        for _ in range(num_sends):
            try:
                resp = requests.post(self.target_url, json=payload)
                file_hint = f" file={file}" if file else ""
                print(f"[{session_id}] step {step:02d} {action} {status}{file_hint} -> {resp.status_code}")
            except Exception as e:
                print(f"[{session_id}] error sending event: {e}")
        
        time.sleep(delay)

    def scenario_normal(self, session_id):
        print(f"--- Starting Normal Scenario: {session_id} ---")
        print("A straight-through edit cycle: inspect, reason, write, verify, finish.")
        self.send_event(session_id, 1, "read_file", "src/main.py", "Opening the entrypoint to understand the flow.", file="src/main.py")
        self.send_event(session_id, 2, "llm_call", "Summarize the request and propose a small test", "Add a focused regression test around the main branch.")
        self.send_event(session_id, 3, "write_file", "tests/test_main.py", "Writing the smallest useful test fixture.", file="tests/test_main.py")
        self.send_event(session_id, 4, "run_command", "pytest -q", "1 test passed, 0 skipped", status="success")
        self.send_event(session_id, 5, "llm_call", "Capture the result and mark the task done", "The change is verified and ready to ship.")

    def scenario_loop(self, session_id):
        print(f"--- Starting Loop Scenario: {session_id} ---")
        print("The agent keeps trying adjacent fixes while the command keeps failing.")
        self.send_event(session_id, 1, "read_file", "package.json", "Looking for the right script name.", file="package.json")
        self.send_event(session_id, 2, "llm_call", "Ask which test command is correct", "Try the test script directly; maybe the wrapper is wrong.")
        commands = [
            "npm test",
            "npm run test",
            "npm run test:unit",
            "npm t",
            "npm run test -- --runInBand",
            "npm test -- --watch=false",
        ]
        outputs = [
            "Missing script: test",
            "Missing script: test",
            "No matching script",
            "npm ERR! command not found",
            "Still no target script",
            "Retry exhausted",
        ]
        for i, (cmd, output) in enumerate(zip(commands, outputs), start=3):
            self.send_event(session_id, i, "run_command", cmd, output, status="failure")
        self.send_event(session_id, 9, "llm_call", "Rephrase the request and try again", "The agent is circling the same failure mode.", status="failure")

    def scenario_drift(self, session_id):
        print(f"--- Starting Drift Scenario: {session_id} ---")
        print("Two streams interleave: the main session drifts from auth work into styling docs.")
        shadow_session = f"{session_id}_shadow"

        primary_events = [
            (1, "read_file", "src/auth/login.py", "Inspect auth flow before changing it.", "login.py loaded", "src/auth/login.py"),
            (3, "llm_call", "Summarize auth constraints", "Keep the auth flow intact and small.", None, None),
            (5, "read_file", "src/auth/tokens.py", "Check token handling for the session.", "tokens.py loaded", "src/auth/tokens.py"),
            (7, "write_file", "src/auth/login.py", "Patch auth state handling.", "Updated auth state guard.", "src/auth/login.py"),
            (9, "llm_call", "Validate the auth approach", "Looks good; one more pass on the auth files.", None, None),
            (11, "read_file", "docs/styles/theme.css", "Why is styling becoming relevant?", "Swapped context into CSS work.", "docs/styles/theme.css"),
            (13, "write_file", "docs/styles/theme.css", "Adjust the palette and spacing.", "Tuned the theme tokens.", "docs/styles/theme.css"),
            (15, "run_command", "npm run lint", "Lint passes after the CSS edit.", "src/auth tests untouched", None),
        ]

        shadow_events = [
            (2, "read_file", "src/components/Nav.tsx", "Check the shared navigation component.", "Nav loaded", "src/components/Nav.tsx"),
            (4, "llm_call", "Suggest a small UI polish", "Use softer spacing and clearer labels.", None, None),
            (6, "write_file", "src/components/Nav.tsx", "Add a tiny UI polish.", "Navigation copy updated.", "src/components/Nav.tsx"),
            (8, "run_command", "npm run build", "Build still passes.", "Build green", None),
            (10, "llm_call", "Summarize the UI tweak", "The shadow session is stable.", None, None),
        ]

        for event in sorted(primary_events + shadow_events, key=lambda item: item[0]):
            step, action, input_str, output_str, status, file = event
            if step in {2, 4, 6, 8, 10}:
                session = shadow_session
                event_status = "success"
            else:
                session = session_id
                event_status = "success"
            self.send_event(session, step, action, input_str, output_str, status=event_status, file=file)

    def scenario_failure(self, session_id):
        print(f"--- Starting Failure Scenario: {session_id} ---")
        print("The agent retries the same dead path and never recovers.")
        attempts = [
            (1, "llm_call", "Generate code for the new endpoint", "Connection timeout", "failure"),
            (2, "run_command", "pytest -q", "pytest timed out", "failure"),
            (3, "llm_call", "Retry with a shorter prompt", "Connection timeout", "failure"),
            (4, "run_command", "pytest -q", "pytest timed out", "failure"),
            (5, "llm_call", "Ask for a safer fallback", "Connection timeout", "failure"),
            (6, "run_command", "pytest -q", "pytest timed out", "failure"),
        ]
        for step, action, input_str, output_str, status in attempts:
            self.send_event(session_id, step, action, input_str, output_str, status=status)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent Simulator CLI")
    parser.add_argument("--target", default="http://localhost:8000/events", help="Target API URL")
    parser.add_argument("--scenario", choices=["normal", "loop", "drift", "failure"], required=True, help="Scenario to run")
    args = parser.parse_args()

    sim = AgentSimulator(args.target)
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    
    if args.scenario == "normal":
        sim.scenario_normal(session_id)
    elif args.scenario == "loop":
        sim.scenario_loop(session_id)
    elif args.scenario == "drift":
        sim.scenario_drift(session_id)
    elif args.scenario == "failure":
        sim.scenario_failure(session_id)
