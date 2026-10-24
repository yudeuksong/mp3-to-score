# 조사 문서: MP3 → 피아노 악보 공개 도구와 서비스

조사일: 2026-10-24 · 조사 환경: Claude Code 클라우드 컨테이너(네트워크 정책 제한 있음)

각 항목은 **관찰(직접 확인)**, **2차 출처(검색 결과·제3자 글)**, **미확인**으로 구분한다.
서버 내부 모델이나 비공개 API는 관찰하지 않았고 추측하지 않는다.

---

## 1. REA 도구 가용성 (실제 호출로 확인)

| 항목 | 결과 |
|---|---|
| REA MCP 서버 | 연결됨. `rea-agents` 6.4.0, MCP 도구 170개, 스킬 `reverse-engineer-anything` (`binary_session` 호출로 확인) |
| 웹 분석 도구 15종(`analyze_web_bundle`, `inspect_web_page`, `capture_browser_scenario` 등) | `available`로 보고됨 |
| `capture_browser_scenario` (launch 모드) | **실패**. Chromium 실행 파일 경로를 바르게 줘도 `cleanup_incomplete / unreadable_output`. 원인 미확인(REA 제공자 쪽 문제로 보임) |
| `inspect_web_page` (CDP 연결) | **성공**. 직접 띄운 headless Chromium(루프백 9222)에 연결해 로컬 UI 관찰. Evidence `ev_3afbf99e5581cf0b5359a834a50effbe629562b920defb2a598b328d06720d23` |
| `analyze_javascript_application` | **성공**. 공개 npm 패키지 `@spotify/basic-pitch@1.0.1` 정적 분석. Evidence `ev_238999f82e9c2e448231a37966a81f4a91777e86e100c35f9a75be577988d832` |
| Ghidra 등 네이티브 분석 | 분석할 바이너리가 없어 사용하지 않음 |

### 차단된 도메인 (네트워크/보안 설정은 변경하지 않음)

| 도메인 | 결과 |
|---|---|
| `klang.io` (transcription-studio, help 페이지) | 차단. 프록시 `CONNECT 403` (curl), DNS 실패 (WebFetch) |
| `lunaverus.com` | 차단. DNS 실패 / 연결 거부 |
| `github.com` 웹 페이지 | curl은 403. WebFetch로는 열람 가능. `raw.githubusercontent.com`은 허용 |
| `cdn.jsdelivr.net` | 차단. 그래서 OSMD는 npm 레지스트리에서 받아 동봉 |
| `pypi.org`, `registry.npmjs.org` | 허용 |

→ Klang·Lunaverus 사이트는 **REA로 관찰하지 못했다**. 아래 내용은 검색 결과(2차 출처)뿐이다.
허용하려면 환경 설정 → Network access → Allowed domains에 추가해야 한다
(https://code.claude.com/docs/en/cloud-environments#network-access).

---

## 2. 공개 엔진·라이브러리

### 2.1 Spotify Basic Pitch (Python) — **채택한 기본 엔진**
- 출처: https://github.com/spotify/basic-pitch · PyPI `basic-pitch` 0.4.0
- 라이선스: **Apache-2.0** (관찰: 레포 LICENSE와 설치된 wheel의 LICENSE/NOTICE 모두 "Copyright 2022 Spotify AB, Apache License")
- 관찰된 사실 (README, 설치된 소스):
  - 악기 종류를 가리지 않는 다성음 모델이며, "works best on one instrument at a time"
  - 입력은 모노로 다운믹스한 뒤 22050 Hz로 리샘플링
  - Python 3.7~3.11 지원 (Mac M1은 3.10만)
  - 모델 백엔드: TF / CoreML / TFLite / ONNX. 패키지 안에 `nmp.onnx`, `nmp.tflite`, `nmp.mlpackage`, `nmp`(SavedModel)가 모두 들어 있음
  - `predict()` 시그니처(설치본 inspect로 확인): `onset_threshold=0.5, frame_threshold=0.3, minimum_note_length=127.7(ms), minimum_frequency, maximum_frequency, multiple_pitch_bends=False, melodia_trick=True, midi_tempo=120`
  - PyPI 메타데이터상 **Python ≥3.11 + Linux/Windows에서는 tensorflow<2.15.1을 강제 설치**한다. 이 프로젝트는 `--no-deps`로 설치하고 `onnxruntime`으로 ONNX 모델을 쓴다. Windows/Linux/macOS가 같은 백엔드를 쓰게 되고, 설치 용량도 크게 줄어든다.
- 이 환경에서 확인: Python 3.11.x + onnxruntime 1.31.0에서 실제 추론 성공. Python 3.13에서는 시험하지 않았다(이전 기록상 설치 실패, 공식 지원 범위 밖).

### 2.2 Spotify Basic Pitch TS (브라우저 구현 후보)
- 출처: https://github.com/spotify/basic-pitch-ts · npm `@spotify/basic-pitch` 1.0.1 (latest)
- 라이선스: **Apache-2.0** (npm 메타데이터, 패키지 LICENSE)
- 의존성: `@tensorflow/tfjs ^3.2.0`, `@tonejs/midi ^2.0.28`. 모델은 `model/model.json` + `group1-shard1of1.bin`으로 동봉(패키지 전체 1.9MB)
- REA 정적 분석 결과(Evidence `ev_2389…d832`, authority = shipped-artifact):
  - JS 파일 40개 파싱, 파싱 실패 0건
  - `request` 관계(fetch/WebSocket/http) **0건**. grep으로도 `fetch(`·`XMLHttpRequest`·`WebSocket` 없음 → 라이브러리가 오디오를 외부로 보내지 않음. 모델은 호출하는 쪽이 로드해 생성자에 넘김(정적 관찰이며 실행 관찰은 아님)
  - 상수: `AUDIO_SAMPLE_RATE = 22050`, `FFT_HOP = 256`(약 86 프레임/초). 입력이 22050Hz가 아니면 오류
  - `outputToNotesPoly(frames, onsets, onsetThresh=0.5, frameThresh=0.3, minNoteLen=5 프레임, …, melodiaTrick=true, energyTolerance=11)`. Python 기본값과 같음
- 판단: 완전 브라우저 방식(서버 없음) 2차 버전의 후보. 이번 1차 구현은 테스트·디버깅이 쉬운 Python 로컬 서버로 만들었다.

### 2.3 MuScriptor (Kyutai × Mirelo) — **선택 후보로만 문서화, 채택·다운로드하지 않음**
- 출처: https://github.com/muscriptor/muscriptor (README·LICENSE를 raw.githubusercontent로 직접 확인)
- 라이선스: 코드 **MIT** ("Copyright (c) 2026 Kyutai x Mirelo"), 모델 가중치 **CC BY-NC 4.0**(비상업)
- 제한: HuggingFace 로그인 후 모델 페이지에서 **라이선스 동의가 필요**하며, `HF_TOKEN`이나 `hf auth login`으로 인증해야 한다. 악보 PDF를 만들려면 MuseScore 4 이상이 필요하다
- 모델: small 103M / medium 307M(기본) / large 1.4B. CPU라면 small이 현실적
- 이번 작업에서는 사용자 지시에 따라 약관 동의·토큰 요청·모델 다운로드를 **하지 않았다**. 비상업 용도로 정확도를 더 높이고 싶을 때 쓸 수 있는 선택 엔진 후보다.

### 2.4 그 밖에 사용한 라이브러리
| 라이브러리 | 버전 | 라이선스 | 용도 |
|---|---|---|---|
| music21 | 10.5.1 | BSD-3-Clause | 대보표 구성, 조성 추정, MusicXML/MIDI 출력 |
| OpenSheetMusicDisplay | 2.2.1 (npm, 동봉) | BSD-3-Clause | 브라우저 악보 미리보기 |
| librosa / soundfile / audioread | 0.11.0 / 0.14.0 / 3.1.0 | ISC / BSD-3 / MIT | 디코딩, BPM 추정, YIN |
| pretty-midi | 0.2.11.post0 | MIT | 원래 타이밍 MIDI |
| onnxruntime | 1.31.0 | MIT | Basic Pitch ONNX 실행 |
| FastAPI / uvicorn | 0.162.0 / 0.54.0 | MIT / BSD-3 | 로컬 웹 서버 |
| MuseScore (선택, 외부 설치) | 4.x | GPL-3.0 | 서버 측 PDF 생성(설치된 경우에만) |

---

## 3. 상용 서비스 (참고용, 2차 출처)

### 3.1 Klangio Transcription Studio — https://klang.io/transcription-studio/
- **직접 관찰 불가**(도메인 차단). 아래는 검색 결과 요약이며 대부분 경쟁사(Songscription) 블로그와 도구 목록 사이트에서 나온 것이다.
- 무료: 곡의 처음 **20초** 미리 채보, 전체 내보내기 없음 (2차 출처)
- 내보내기 형식: PDF, MIDI, MusicXML, GuitarPro (2차 출처)
- 사용자가 준 정보(직접 확인 못 함): 무료는 최대 20초·PDF, MIDI/MusicXML/브라우저 편집은 유료
- 구조: 악기별 앱(Piano2Notes, Guitar2Tabs 등) + 여러 악기를 다루는 Transcription Studio
- 가격(2차 출처): Studio 연간 결제 시 월 $8.49 상당, 월 결제 $19.99
- **미확인**: 처리가 서버에서 이루어지는지 브라우저에서 이루어지는지, 어떤 모델을 쓰는지, API 형태. 사이트를 관찰하지 못했으므로 추측하지 않는다.
- 출처: https://www.songscription.ai/blog/klangio-alternatives , https://www.songscription.ai/blog/songscription-vs-klangio , https://dataconomy.com/tools/klangio/

### 3.2 Lunaverus (AnthemScore) — https://lunaverus.com/transcribe
- **직접 관찰 불가**(도메인 차단). 검색 결과 요약:
  - 오디오나 MIDI를 PDF·MusicXML·MIDI 악보로 변환. 타브 악보와 여러 악기 옵션 포함
  - 웹판은 브라우저에서 쓰는 구독 서비스, 데스크톱판은 1회 구매 로컬 소프트웨어
  - 체험판: 곡마다 처음 30초, 총 100회 (공식 페이지 인용으로 보고됨)
  - 등급(edition)별 내보내기 형식 차이는 출처마다 다름 → 미확인
- 출처: https://lunaverus.com/ , https://www.lunaverus.com/compareEditions , https://dataconomy.com/tools/anthemscore-by-lunaverus/

### 3.3 이 프로젝트에 반영한 공통 기능 (공개 정보 기준)
상용 서비스들이 공개적으로 내세우는 기능 묶음을 오픈소스로 구현했다. 상용 코드나 모델을 복제하지 않았다.
- 오디오 업로드 → 자동 채보 → 악보 미리보기 → PDF/MusicXML/MIDI 내보내기
- 음원 종류 구분, 템포/박자/양자화 조절, 원음 재생
- 브라우저 악보 편집(Klang 유료 기능)은 이번 범위 밖이다. MusicXML을 MuseScore에서 편집하도록 안내한다.

---

## 4. 설계 결정 요약
1. **엔진**: Basic Pitch ONNX(Apache-2.0)를 기본으로 쓴다. 상업적 이용에도 라이선스 문제가 없다. YIN은 Basic Pitch를 쓸 수 없을 때만 쓰는 단선율 실험용 대체 엔진이다.
2. **후처리**:
   - 음역·최소 길이 필터
   - 배음 유령음 제거: 합성음 측정에서 원본 정밀도가 0.64~0.70으로 낮게 나온 원인
   - 박자 격자 양자화와 레가토 보정
   - 분할음 기준 왼손/오른손 분리(휴리스틱)
3. **악보**: music21로 피아노 대보표(PartStaff 2개 + 중괄호)를 만들고, 조표에 맞춰 음이름을 정한다.
4. **PDF**: MuseScore가 있으면 서버에서 만들고, 없으면 브라우저 인쇄(인쇄 CSS로 악보만 출력)로 안내한다.
5. **개인정보**: 서버는 127.0.0.1에만 바인딩한다. 업로드 원본은 처리 후 즉시 삭제하고, 결과는 1시간 뒤 삭제하며, 종료 시 임시 폴더도 지운다. 원음 재생은 브라우저의 로컬 blob URL로 한다.
