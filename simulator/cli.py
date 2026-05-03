import argparse
import requests
import time
import random
import uuid
from datetime import datetime

class AgentSimulator:
    def __init__(self, target_url):
        self.target_url = target_url

    def send_event(self, session_id, step, action, input_str, output_str, status="success", file=None, delay=0.5):
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
                print(f"Step {step}: {action} -> {status} ({resp.status_code})")
            except Exception as e:
                print(f"Error sending event: {e}")
        
        time.sleep(delay)

    def scenario_normal(self, session_id):
        print(f"--- Starting Normal Scenario: {session_id} ---")
        self.send_event(session_id, 1, "read_file", "src/main.py", "file content...", file="src/main.py")
        self.send_event(session_id, 2, "llm_call", "Analyze code", "Code looks good, add a test.")
        self.send_event(session_id, 3, "write_file", "tests/test_main.py", "test code...", file="tests/test_main.py")
        self.send_event(session_id, 4, "run_command", "pytest", "4 passed", status="success")

    def scenario_loop(self, session_id):
        print(f"--- Starting Loop Scenario: {session_id} ---")
        # Initial steps
        self.send_event(session_id, 1, "read_file", "package.json", "{}")
        
        # The loop: Trying to run a command that fails, with variations
        commands = ["npm test", "npm run test", "npm run test:unit", "npm t"]
        for i in range(2, 10):
            cmd = commands[i % len(commands)]
            self.send_event(session_id, i, "run_command", cmd, "Command not found", status="failure")

    def scenario_drift(self, session_id):
        print(f"--- Starting Drift Scenario: {session_id} ---")
        # Baseline: Auth work
        for i in range(1, 11):
            self.send_event(session_id, i, "read_file", f"src/auth/module_{i}.py", "...", file=f"src/auth/module_{i}.py")
        
        # The Drift: Suddenly styling docs
        for i in range(11, 20):
            self.send_event(session_id, i, "write_file", f"docs/styles/theme_{i}.css", "...", file=f"docs/styles/theme_{i}.css")

    def scenario_failure(self, session_id):
        print(f"--- Starting Failure Scenario: {session_id} ---")
        for i in range(1, 6):
            self.send_event(session_id, i, "llm_call", "Generate code", "Connection timeout", status="failure")

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