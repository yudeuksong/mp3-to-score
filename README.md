# MP3 → 피아노 악보 (로컬 변환기) v0.1.0

MP3/WAV 음원을 **내 컴퓨터 안에서** 피아노 악보(MusicXML·MIDI·PDF)로 바꾸는 프로그램입니다.
음표 추론에는 Spotify의 오픈소스 모델 **Basic Pitch**(Apache-2.0)를 사용합니다.
파일은 외부 서비스로 전송하지 않습니다.

> 자동 채보 결과는 **초안**입니다. MusicXML을 MuseScore 같은 악보 프로그램에서 열어 꼭 검토·수정하세요.

## 지원 범위

| 음원 종류 | 지원 수준 | 설명 |
|---|---|---|
| 단선율 (피아노 한 손, 플루트, 허밍 등) | 좋음 | 음높이는 대체로 정확. 박자는 BPM 입력과 양자화 설정에 크게 좌우됨 |
| 피아노 다성음 (화음, 양손) | 보통 | 화음 음 일부가 빠지거나 더해질 수 있음. 페달·잔향이 많으면 정확도 저하 |
| 보컬+반주 혼합곡 (찬양, 가요 등) | **실험적** | 음원 분리를 하지 않음. 보컬 선율을 정확히 뽑아낸다고 약속하지 않음 |

- **왼손/오른손 분리는 음역 기반 휴리스틱입니다.** 분할음(기본 C4) 이상은 오른손, 미만은 왼손으로 나눕니다. 실제 운지와 다를 수 있습니다.
- **YIN 대체 엔진은 단선율 실험용입니다.** Basic Pitch를 설치할 수 없을 때만 자동으로 쓰이며, 화음은 검출하지 못합니다.
- 템포 자동 추정은 절반/두 배로 틀릴 수 있습니다. 곡의 BPM을 알면 직접 입력하세요.

## 설치

공통 요구사항: **Python 3.11** (Basic Pitch 0.4.0은 Python 3.7~3.11만 지원하며, 3.12/3.13은 지원 범위 밖입니다).
설치 스크립트는 프로젝트 폴더 안에 `.venv` 가상환경을 만들 뿐, 전역 설정은 바꾸지 않습니다.

### Windows
1. https://www.python.org/downloads/ 에서 **Python 3.11.x**를 설치합니다("py launcher" 옵션 포함).
2. (권장) ffmpeg 설치: `winget install Gyan.FFmpeg`. 없어도 WAV는 동작하며, MP3도 대부분 동작합니다.
3. 압축을 푼 폴더에서 `setup_windows.bat`을 더블클릭합니다.
4. `run_windows.bat`을 더블클릭하면 브라우저에 http://127.0.0.1:8765/ 가 열립니다.

### Linux / macOS
```bash
./setup.sh          # python3.11 이 PATH에 있어야 함 (PYTHON=경로 로 지정 가능)
./run.sh            # http://127.0.0.1:8765/
```

### 수동 설치
```bash
python3.11 -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install --no-deps basic-pitch==0.4.0             # TensorFlow 강제 설치를 피함 (ONNX 사용)
python -m app.server
```
`requirements-lock.txt`에는 검증에 사용한 전체 의존성 고정본이 있습니다.

## 사용법 (웹 UI)
1. MP3/WAV 파일을 끌어 놓습니다. 브라우저 안에서 원음을 바로 재생할 수 있습니다.
2. 음원 종류(피아노/단선율/혼합곡)를 고릅니다.
3. 필요하면 BPM·박자표·양자화 단위·최소 음 길이·음역·분할음·감도·분석 구간을 조절합니다.
4. **악보로 변환**을 누르면 진행률이 표시되고, 완료되면 악보 미리보기와 다운로드 버튼이 나타납니다.
   - `MusicXML`: MuseScore, Finale, Sibelius, Dorico 등에서 편집할 수 있음
   - `MIDI (악보)`: 양자화된 악보 그대로의 MIDI
   - `MIDI (원래 타이밍)`: 양자화하지 않은, 연주 그대로의 MIDI
   - `PDF`: MuseScore가 설치되어 있을 때만 서버에서 생성
   - **브라우저로 인쇄 (PDF 저장)**: MuseScore가 없을 때의 대안. 인쇄 창에서 대상을 "PDF로 저장"으로 고르면 악보만 PDF로 저장됨

### PDF와 MuseScore
- MuseScore 4가 설치되어 있으면 자동으로 찾아 `score.pdf`를 만듭니다(Windows: `C:\Program Files\MuseScore 4\bin\MuseScore4.exe`, macOS: `/Applications/MuseScore 4.app`, Linux: PATH의 `mscore`/`musescore`).
- 다른 위치에 있으면 환경변수 `MUSESCORE_PATH`로 지정하세요.
- 설치: https://musescore.org/ko/download (GPL-3.0, 무료)

## 명령줄 사용
```bash
python -m app.cli song.mp3 -o out --bpm 96 --mode piano --grid 4 --split 60
python -m app.cli song.mp3 -o out --mode melody --start 30 --length 60   # 30초부터 60초 구간만
```
`python -m app.cli -h`로 모든 옵션을 볼 수 있습니다.

## 제한과 안전장치
- 최대 50MB, 분석 구간 최대 10분. 더 긴 곡은 시작 위치/분석 길이로 구간을 나누세요. 환경변수로 바꿀 수 있습니다: `MP3SCORE_MAX_MB`, `MP3SCORE_MAX_SECONDS`.
- 빈 파일, 손상 파일, 무음 파일, 지원하지 않는 형식은 한국어 오류 메시지를 표시합니다.
- 작업은 한 번에 하나씩 처리해 메모리를 보호합니다.
- 서버는 `127.0.0.1`에만 열리며 외부에서 접속할 수 없습니다.
- 업로드 원본은 변환이 끝나면 바로 삭제하고, 결과 파일은 1시간 뒤(또는 다음 변환 시작 시, 서버 종료 시) 삭제합니다. 보관 시간은 `MP3SCORE_JOB_TTL`(초)로 바꿀 수 있습니다.

## 테스트
```bash
. .venv/bin/activate
python -m pytest -q          # 단위 + 실제 Basic Pitch 추론 통합 + 웹 API 테스트
python tools/evaluate.py     # 합성 음원 정확도 측정 → docs/results/
```
측정 결과와 검증 범위는 [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md), 조사 내용과 라이선스는 [docs/RESEARCH.md](docs/RESEARCH.md)를 보세요.

## 구조
```
app/
  audio.py        입력 검증, 22050Hz 모노 디코딩
  transcribe.py   Basic Pitch(ONNX) / YIN(단선율 실험용) 엔진
  postprocess.py  필터, 배음 유령음 제거, 양자화, 왼손/오른손 분리
  score.py        music21 대보표, MusicXML/MIDI, MuseScore PDF
  pipeline.py     전체 흐름
  server.py       로컬 웹 서버(FastAPI)
  cli.py          명령줄
  static/         한국어 UI (+ OpenSheetMusicDisplay 동봉)
tests/            합성 음원 생성기와 테스트
tools/evaluate.py 정확도 측정
```

## 음악 저작권 안내
이 프로그램이 만든 악보는 **원곡의 저작권 영향을 받습니다.** 저작권이 있는 곡을 채보한 악보는 개인 연습(사적 이용) 범위를 넘어 복사·배포·공유·판매하거나 예배·공연에서 쓰려면, 저작권자의 허락이나 해당 사용 허가(예: 교회용 라이선스, 음악저작권협회)가 필요할 수 있습니다. 직접 만든 곡이나 저작권 보호기간이 끝난 곡은 자유롭게 쓸 수 있습니다. 사용자는 자신이 넣는 음원에 대한 권리를 확인할 책임이 있습니다.

## 라이선스
이 프로젝트 코드는 [MIT 라이선스](LICENSE)입니다. 사용한 구성요소의 라이선스는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 있습니다.
Basic Pitch 모델(Apache-2.0)은 이 저장소에 포함하지 않으며, 설치할 때 PyPI에서 받습니다.
