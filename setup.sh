#!/usr/bin/env bash
# Linux/macOS 설치: Python 3.11 가상환경(.venv)을 만들고 의존성을 설치한다. 전역 설정은 바꾸지 않는다.
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3.11}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python 3.11이 필요합니다. (예: sudo apt install python3.11 python3.11-venv / brew install python@3.11)" >&2
  exit 1
fi
"$PY" -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --no-deps basic-pitch==0.4.0
command -v ffmpeg >/dev/null 2>&1 || echo "참고: ffmpeg가 없으면 일부 MP3/M4A 디코딩이 실패할 수 있습니다. (sudo apt install ffmpeg / brew install ffmpeg)"
echo "설치 완료. 실행: ./run.sh"
