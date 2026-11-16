"""Cross-platform dev tasks (Windows has no make). Usage: python scripts/dev.py <setup|test|lint|up|down>"""

import subprocess
import sys

TASKS = {
    "setup": [[sys.executable, "-m", "pip", "install", "-e", ".[dev,ui]"]],
    "test": [[sys.executable, "-m", "pytest", "-q"]],
    "lint": [[sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"]],
    "up": [["docker", "compose", "up", "-d"]],
    "down": [["docker", "compose", "down"]],
}

if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "test"
    if task not in TASKS:
        sys.exit(f"unknown task {task!r}; choose from {', '.join(TASKS)}")
    for cmd in TASKS[task]:
        subprocess.run(cmd, check=True)
