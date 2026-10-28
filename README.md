# CorridorKey2.0 ·13 existing real-footage tests

[221초1080×1350 합본](https://github.com/hyun2xyz/keying-lab/releases/download/v1.2.0/keying_breakdown_real13_1080x1350.mp4) · [전체 다운로드](https://github.com/hyun2xyz/keying-lab/releases/tag/v1.2.0)

현재8개와 이전 머리카락·모션블러·금속 안경·연기·전신5개를 같은 형식으로 모았습니다. 실제 촬영본과 기존 실제 모델 결과를 재사용했으며 이번 수정에서 새 추론은 하지 않았습니다. 기존v1.0.0/v1.1.0 릴리스는 보존했습니다.

- 1080×1350/30fps, H264 High/yuv420p,CRF10/preset slow. 각17초×13개, 합본221초.
- 위 원본·아래 결과. 위/아래 흰 여백56px씩, 가운데22px, 상단 개별 제목·ROI 박스·하단 바깥 자막 없음.
- 아래 영상 우측 하단 두 줄: `Only an LLM + CorridorKey2.0` / `See Caption for Details!`. 이전 브레이크다운과 같은 Jibaek120 글꼴, 20px, 우측 정렬27px, 줄 간격3px, 흰 박스·검정 글씨. 글꼴 파일은 배포하지 않습니다.
- 와이프0.5초와 비교 화면1초, 체커 결과3초와 더 깊은 비교 뒤4초. 카메라/와이프가 머무르는 동안 실제 영상의 동작은 계속됩니다.
- 추가5개는30/60fps 원본 길이를 유지하며24fps로 프레임 선택했습니다. 소스 구간 길이가 달라 반복수는 사례별로 다릅니다. `reel_collection_manifest.json`의 frame mapping을 참조하세요.

ZIP을 모두 풀고 `review.html`을 여세요. 새 ZIP은14개 편집 영상·검수·코드를 포함하며, 촬영 원본·독립cutout/alpha·모델·글꼴은 포함하지 않습니다.

| ID | Test | Prepared frames | Creator / source |
| --- | --- | --- | --- |
| 01_hair_glasses | Curly hair and glasses | 96@24 | [(CC) Blender Foundation \| mango.blender.org \| CC BY 3.0](https://mango.blender.org/production/4-tb-original-4k-footage-available-as-cc-by/) |
| 02_male_presenter | Male presenter / hair, beard and gestures | 96@24 | [Mixkit / video28287 / Stock Video Free License](https://mixkit.co/free-stock-video/man-talking-head-on-on-a-chroma-background-28287/) |
| 03_dog | Dog / fine fur and shadow | 96@24 | [GreenCardShow / Pixabay / Pixabay Content License](https://pixabay.com/videos/chromakey-dog-sitting-puppy-11342/) |
| 04_sheer_shawl | Sheer shawl / real transmission | 96@24 | [Hollywood Camera Work / practice footage / results permitted](https://www.hollywoodcamerawork.com/green-screen-plates.html) |
| 05_furniture | Furniture / fabric texture and hard edges | 96@24 | [GreenCardShow / Pixabay / Pixabay Content License](https://pixabay.com/videos/chromakey-sofa-old-ruined-used-11292/) |
| 06_office_pair | Two coworkers / hair and overlapping subjects | 96@24 | [Mixkit / video42638 / Stock Video Free License](https://mixkit.co/free-stock-video/entrepreneurs-working-in-the-office-chroma-background-42638/) |
| 07_mature_pair | Mature pair / two silhouettes | 96@24 | [Mixkit / video100760 / Stock Video Free License](https://mixkit.co/free-stock-video/mature-couple-sharing-a-warm-moment-100760/) |
| 08_male_prop | Clothed man / hands and recycling bin | 96@24 | [Lara Jameson / Pexels / Pexels License](https://www.pexels.com/video/a-man-holding-a-recycling-bin-in-front-of-a-green-screen-9323252/) |
| 09_legacy_hair | Hair detail | 64@24 | [Hollywood Camera Work / practice footage / results permitted](https://www.hollywoodcamerawork.com/green-screen-plates.html) |
| 10_legacy_motion_blur | Motion blur | 40@24 | [Hollywood Camera Work / practice footage / results permitted](https://www.hollywoodcamerawork.com/green-screen-plates.html) |
| 11_legacy_metal_glasses | Metal glasses | 72@24 | [Hollywood Camera Work / practice footage / results permitted](https://www.hollywoodcamerawork.com/green-screen-plates.html) |
| 12_legacy_smoke | Smoke | 96@24 | [Hollywood Camera Work / practice footage / results permitted](https://www.hollywoodcamerawork.com/green-screen-plates.html) |
| 13_legacy_fullbody | Uneven screen / full body | 72@24 | [Hollywood Camera Work / practice footage / results permitted](https://www.hollywoodcamerawork.com/green-screen-plates.html) |

## Evidence and limits

[직접 검수](qa/collection_review.json) · [실제 인코딩 검사](docs/collection_render_audit.json) · [렌더 receipt](docs/collection_render_receipt.json) · [이전5개 재사용](docs/legacy_reuse_audit.json) · [레이아웃 검토](docs/collection_layout_review.json)

모든14개 영상의 전체 디코딩, 프레임 수/정확한 시간, 색 정보와 메타데이터를 검사했습니다. 직접 시각검수는117선택 프레임과 별도1080상세 프레임 범위입니다. GT 알파가 없어 정확도/MAE/완벽한 복원 점수는 없습니다. 디지털 확대이며 새 해상도 복원을 뜻하지 않습니다. 추가5개의 기존 색 해석과 누락 정보, smoke gAMA1.0/이전 sRGB관습 처리 충돌, 스필·장비·거친 경계 잔류도 기록했습니다.

H264의 흰 여백 경계 잔차는 안쪽 흰 영역과 나누어 측정했습니다. 원래 실패한 검사 상태와 영상은 보존하고, 완성 영상에 대한 별도 검사를 실행했습니다. [검사 수정과 작업 증거](docs/collection_job_provenance.json)에 그 범위를 기록했습니다.

이 작업에서는 이전 중단 요청에 따라 OBS 녹화를 재개하지 않았으며 이번 편집의 새 녹화는 없습니다. 이전 녹화는 [v1.0.0](https://github.com/hyun2xyz/keying-lab/releases/tag/v1.0.0)과 [v1.1.0](https://github.com/hyun2xyz/keying-lab/releases/tag/v1.1.0)에 있습니다. 재생된 결과를 새 추론으로 표시하지 않습니다.

## Reproduction

Python3.12와 `requirements-review.txt`, FFmpeg/ffprobe7.1.1을 사용했습니다. `src`의 독립 유틸리티는 [MIT](LICENSE-CODE.txt)이며 CorridorKey 코드·모델과 촬영본·폰트의 조건은 별도입니다. [권리와 크레딧](docs/RIGHTS.md)을 먼저 확인하세요. 무료 사용 조건이 있는 촬영본이며 CC0 자료가 아닙니다.

원본8개의 입력/모델 준비는 `src/prepare_inputs.py`, `src/run_real_case.py`, 기존 `dataset_manifest.json`과 `docs/runtime.json`을 참조하세요. 추가5개 준비 도구 `src/prepare_legacy_reuse.py`는 이 기록의 `<workspace>/outputs/keying-real5` 저장소 배치와 `<workspace>/work`·과거 모델MOV 경로를 사용합니다. 먼저 공식 촬영본과 본인 환경의 실제 모델 결과를 준비해야 하며, 원본은 여기서 재배포하지 않습니다.

모든 로컬 source/prediction PNG가 `collection_reference.json`의 기록된 SHA와 일치하면 다음 명령으로 새 폴더에 렌더합니다. 다른 GPU/런타임의 새 모델 결과는 바이트가 다를 수 있어 원래 검수 승인을 재사용할 수 없습니다. SHA 불일치를 완화하지 말고 새 검수를 기록하세요. 라이선스가 있는 로컬 Jibaek120 파일은 공개된 SHA와 일치해야 합니다.

```text
python src/render_collection_hidden.py --manifest reel_collection_manifest.json --output-dir <new-folder> --credit-font <licensed-local-Jibaek-120g-beta.otf>
python src/audit_collection_boundaries.py --root . --manifest reel_collection_manifest.json --output-dir <new-folder> --audit-output <new-audit-folder>
```

`--check-history`는 기존 모든 버전의 로컬 영상·receipt와 preserved baseline이 있는 제작 환경에서만 사용합니다. 기술 성공은 직접 시각 승인과 별개입니다. 모델·원본·이전 결과를 보존하며 새 출력 폴더만 사용하세요.
