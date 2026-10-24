# 제3자 구성요소

| 구성요소 | 버전 | 라이선스 | 포함 방식 |
|---|---|---|---|
| Spotify Basic Pitch (모델 포함) | 0.4.0 | Apache-2.0, Copyright 2022 Spotify AB | pip 설치 (동봉하지 않음) |
| OpenSheetMusicDisplay | 2.2.1 | BSD-3-Clause, Copyright 2019 PhonicScore | `app/static/vendor/`에 동봉 (`OSMD-LICENSE.txt`) |
| └ VexFlow (OSMD 번들에 포함) | 1.2.93 | MIT, Copyright Mohit Muthanna Cheppudira | 위 파일에 포함 |
| └ JSZip (OSMD 번들에 포함) | 3.10.1 | MIT 또는 GPL-3.0-or-later 중 **MIT 선택**, Copyright Stuart Knightley 외 | 위 파일에 포함 |
| └ loglevel (OSMD 번들에 포함) | ^1.8.0 | MIT, Copyright Tim Perry | 위 파일에 포함 |
| └ typescript-collections (OSMD 번들에 포함) | ^1.3.3 | MIT, Copyright Basarat Ali Syed | 위 파일에 포함 |
| music21 | 10.5.1 | BSD-3-Clause | pip 설치 |
| librosa | 0.11.0 | ISC | pip 설치 |
| onnxruntime | 1.31.0 | MIT | pip 설치 |
| pretty-midi | 0.2.11.post0 | MIT | pip 설치 |
| FastAPI / uvicorn | 0.162.0 / 0.54.0 | MIT / BSD-3-Clause | pip 설치 |
| MuseScore (선택) | 4.x | GPL-3.0 | 사용자가 별도 설치, 외부 프로세스로만 호출 |

MuScriptor(코드 MIT, 가중치 CC BY-NC 4.0)는 포함하지 않았고 다운로드하지도 않았습니다. 선택 후보로만 문서화했습니다.
