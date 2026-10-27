"""개발용 실행 - hidoc 폴더의 .py 파일을 저장하면 입력창을 자동으로 껐다 다시 켬

python dev_run.py 로 실행하고, 끝낼 때는 이 창에서 Ctrl+C.
추가 설치 없이 0.5초마다 파일 수정 시각을 비교함.
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
WATCH_DIR = ROOT_DIR / "hidoc"
INTERVAL = 0.5


def snapshot() -> dict:
    return {p: p.stat().st_mtime for p in WATCH_DIR.glob("*.py")}


def start():
    print("[dev_run] python -m hidoc 실행")
    return subprocess.Popen([sys.executable, "-m", "hidoc"], cwd=ROOT_DIR)


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(3)
        except subprocess.TimeoutExpired:
            proc.kill()


def main():
    files = snapshot()
    proc = start()
    try:
        while True:
            time.sleep(INTERVAL)
            now = snapshot()
            if now == files:
                continue
            changed = [p.name for p in now if files.get(p) != now[p]] or ["(파일 삭제)"]
            files = now
            print(f"[dev_run] 바뀜: {', '.join(changed)} → 다시 실행")
            stop(proc)
            proc = start()
    except KeyboardInterrupt:
        stop(proc)
        print("[dev_run] 끝")


if __name__ == "__main__":
    main()
