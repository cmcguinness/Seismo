#!/usr/bin/env python3
"""watch.py <part.py> — live-render a build123d part.

Runs the given part file once with the project venv, then re-runs it whenever
that file or dimensions.py changes (300 ms debounce). Never dies on a model
error: prints the traceback and keeps watching. The ocp_vscode viewer must be
running first (see setup) — show() pushes to it.

    .venv/bin/python watch.py parts/geophone_base.py
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
PY = str(ROOT / ".venv" / "bin" / "python")
DIMENSIONS = ROOT / "dimensions.py"

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


def run(part_file: str) -> None:
    print(f"\n=== running {part_file} ===", flush=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT)}  # so `import dimensions` resolves
    proc = subprocess.run([PY, part_file], env=env)
    if proc.returncode != 0:
        print(f"=== {part_file} exited {proc.returncode} — still watching ===",
              flush=True)


class Rerun(FileSystemEventHandler):
    def __init__(self, part_file: str) -> None:
        self.part_file = part_file
        self.watched = {
            str(Path(part_file).resolve()),
            str(DIMENSIONS),
        }
        self._timer: threading.Timer | None = None

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        if str(Path(event.src_path).resolve()) in self.watched:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(0.3, run, args=(self.part_file,))
            self._timer.start()


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: .venv/bin/python watch.py parts/<name>.py")
        sys.exit(1)
    part_file = sys.argv[1]
    run(part_file)

    handler = Rerun(part_file)
    obs = Observer()
    obs.schedule(handler, str(Path(part_file).resolve().parent), recursive=False)
    obs.schedule(handler, str(ROOT), recursive=False)  # for dimensions.py
    obs.start()
    print(f"watching {part_file} + dimensions.py  (Ctrl+C to stop)", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()


if __name__ == "__main__":
    main()
