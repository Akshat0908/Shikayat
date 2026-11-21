"""Run both dev servers, forwarding shutdown and stopping on either failure."""
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    processes: list[subprocess.Popen[bytes]] = []
    def stop(signum: int, frame: object) -> None:
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"], cwd=ROOT, start_new_session=True))
        processes.append(subprocess.Popen(["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"], cwd=ROOT / "frontend", start_new_session=True))
        while all(process.poll() is None for process in processes):
            time.sleep(0.25)
        return next((p.returncode for p in processes if p.returncode is not None), 1) or 1
    except KeyboardInterrupt:
        return 0
    finally:
        import os
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == "__main__":
    sys.exit(main())
