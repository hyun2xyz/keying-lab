"""Build the13-case local review and repository README from approved evidence."""
import argparse,html,json
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
    root=args.root.resolve();manifest=json.loads((root/'reel_collection_manifest.json').read_text(encoding='utf-8'))
    review=json.loads((root/'qa/collection_review.json').read_text(encoding='utf-8'))
    assert len(manifest['cases'])==review['accepted_cases']==13
    assert review['final_reel_visual_review']['status']=='VISUALLY_REVIEWED_ENCODED_SAMPLES'
    base='https://github.com/hyun2xyz/keying-lab';release=base+'/releases/tag/v1.2.0'
    movie='reels/collection_v7_recovery/keying_breakdown_real13_1080x1350.mp4'
    cards=[];rows=[]
    for c in manifest['cases']:
        ident=c['id'];title=html.escape(c['title']);page=c['source_page'];credit=c['credit']
        cards.append(f'<section><h2>{title}</h2><p>{c["width"]}×{c["height"]}, {c["frames"]} prepared samples @24fps. Existing model result.</p><video controls muted loop playsinline preload="none" poster="qa/collection_encoded/{ident}_poster.jpg" src="reels/collection_v7_recovery/{ident}_reel.mp4"></video><p>Source: <a href="{html.escape(page,quote=True)}">{html.escape(credit)}</a></p></section>')
        rows.append(f'| {ident} | {c["title"]} | {c["frames"]}@24 | [{credit.replace("|", chr(92)+"|")}]({page}) |')
    page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CorridorKey2.0 ·13 existing real-footage tests</title>
<style>*{box-sizing:border-box}body{margin:0;background:#fff;color:#111;font:16px/1.65 system-ui,"Malgun Gothic",sans-serif}main{max-width:1000px;margin:auto;padding:32px 22px}h1{line-height:1.2;font-size:clamp(26px,4vw,42px)}section{padding:24px 0;border-top:1px solid #ddd}video{display:block;width:100%;max-height:82vh;object-fit:contain;background:#fff}a{color:#154b8a}p{max-width:80ch}</style><main><h1>13개 실사 키잉 테스트</h1>
<p>1080×1350/30fps. 위 원본·아래 결과, 위아래 흰 여백56px씩과 가운데22px. 아래 영상 우측 하단의 두 줄은 <b>Only an LLM + CorridorKey2.0</b> / <b>See Caption for Details!</b>입니다.</p>
<p>와이프0.5초, 비교 화면1초씩, 체커3초와 추가 세부 비교 뒤4초 유지. 원본 동작은 계속되며 각 짧은 구간을 반복해17초씩 구성했습니다. 기존8개와 이전5개를 합친221초 영상입니다.</p>'''
    page+=f'<video controls playsinline preload="metadata" src="{movie}"></video><p><a href="{release}">GitHub release / all downloads</a> · <a href="docs/RIGHTS.md">권리와 출처</a> · <a href="qa/collection_review.json">직접 검수</a></p>'
    page+='<p>새 모델 추론 없이 기존 결과를 재사용했습니다. 추가5개는 기존 ProRes의 전체 디코드와 원본 속도를 유지하는24fps 표시 캐시를 검증했습니다. 이전 영상의 감마 해석 충돌, 누락 색 정보, 잔류 스필·장비·거친 경계는 <a href="docs/legacy_reuse_audit.json">재사용 검증</a>에 남겼습니다. 실제 정답 알파가 없으므로 정확도 점수를 계산하지 않았습니다.</p><p>전체 디코딩과 프레임/색/시간 검증을 통과했고, 직접 눈으로 한 검수는 선택 프레임 범위입니다. 디지털 확대이며 새 세부 복원이나 무손실 센서 원본을 뜻하지 않습니다. 이번 편집에서 OBS를 재시작하지 않았습니다. 과거 작업 녹화는 이전 릴리스에 있습니다.</p>'
    page+=''.join(cards)+'</main></html>'
    (root/'review.html').write_text(page,encoding='utf-8')
    readme=f'''# CorridorKey2.0 ·13 existing real-footage tests

[221초1080×1350 합본]({base}/releases/download/v1.2.0/keying_breakdown_real13_1080x1350.mp4) · [전체 다운로드]({release})

현재8개와 이전 머리카락·모션블러·금속 안경·연기·전신5개를 같은 형식으로 모았습니다. 실제 촬영본과 기존 실제 모델 결과를 재사용했으며 이번 수정에서 새 추론은 하지 않았습니다. 기존v1.0.0/v1.1.0 릴리스는 보존했습니다.

- 1080×1350/30fps, H264 High/yuv420p,CRF10/preset slow. 각17초×13개, 합본221초.
- 위 원본·아래 결과. 위/아래 흰 여백56px씩, 가운데22px, 상단 개별 제목·ROI 박스·하단 바깥 자막 없음.
- 아래 영상 우측 하단 두 줄: `Only an LLM + CorridorKey2.0` / `See Caption for Details!`. 이전 브레이크다운과 같은 Jibaek120 글꼴, 20px, 우측 정렬27px, 줄 간격3px, 흰 박스·검정 글씨. 글꼴 파일은 배포하지 않습니다.
- 와이프0.5초와 비교 화면1초, 체커 결과3초와 더 깊은 비교 뒤4초. 카메라/와이프가 머무르는 동안 실제 영상의 동작은 계속됩니다.
- 추가5개는30/60fps 원본 길이를 유지하며24fps로 프레임 선택했습니다. 소스 구간 길이가 달라 반복수는 사례별로 다릅니다. `reel_collection_manifest.json`의 frame mapping을 참조하세요.

ZIP을 모두 풀고 `review.html`을 여세요. 새 ZIP은14개 편집 영상·검수·코드를 포함하며, 촬영 원본·독립cutout/alpha·모델·글꼴은 포함하지 않습니다.

| ID | Test | Prepared frames | Creator / source |
| --- | --- | --- | --- |
'''+ '\n'.join(rows)+f'''

## Evidence and limits

[직접 검수](qa/collection_review.json) · [실제 인코딩 검사](docs/collection_render_audit.json) · [렌더 receipt](docs/collection_render_receipt.json) · [이전5개 재사용](docs/legacy_reuse_audit.json) · [레이아웃 검토](docs/collection_layout_review.json)

모든14개 영상의 전체 디코딩, 프레임 수/정확한 시간, 색 정보와 메타데이터를 검사했습니다. 직접 시각검수는117선택 프레임과 별도1080상세 프레임 범위입니다. GT 알파가 없어 정확도/MAE/완벽한 복원 점수는 없습니다. 디지털 확대이며 새 해상도 복원을 뜻하지 않습니다. 추가5개의 기존 색 해석과 누락 정보, smoke gAMA1.0/이전 sRGB관습 처리 충돌, 스필·장비·거친 경계 잔류도 기록했습니다.

H264의 흰 여백 경계 잔차는 안쪽 흰 영역과 나누어 측정했습니다. 원래 실패한 검사 상태와 영상은 보존하고, 완성 영상에 대한 별도 검사를 실행했습니다. [검사 수정과 작업 증거](docs/collection_job_provenance.json)에 그 범위를 기록했습니다.

이 작업에서는 이전 중단 요청에 따라 OBS 녹화를 재개하지 않았으며 이번 편집의 새 녹화는 없습니다. 이전 녹화는 [v1.0.0]({base}/releases/tag/v1.0.0)과 [v1.1.0]({base}/releases/tag/v1.1.0)에 있습니다. 재생된 결과를 새 추론으로 표시하지 않습니다.

## Reproduction

Python3.12와 `requirements-review.txt`, FFmpeg/ffprobe7.1.1을 사용했습니다. `src`의 독립 유틸리티는 [MIT](LICENSE-CODE.txt)이며 CorridorKey 코드·모델과 촬영본·폰트의 조건은 별도입니다. [권리와 크레딧](docs/RIGHTS.md)을 먼저 확인하세요. 무료 사용 조건이 있는 촬영본이며 CC0 자료가 아닙니다.

원본8개의 입력/모델 준비는 `src/prepare_inputs.py`, `src/run_real_case.py`, 기존 `dataset_manifest.json`과 `docs/runtime.json`을 참조하세요. 추가5개 준비 도구 `src/prepare_legacy_reuse.py`는 이 기록의 `<workspace>/outputs/keying-real5` 저장소 배치와 `<workspace>/work`·과거 모델MOV 경로를 사용합니다. 먼저 공식 촬영본과 본인 환경의 실제 모델 결과를 준비해야 하며, 원본은 여기서 재배포하지 않습니다.

모든 로컬 source/prediction PNG가 `collection_reference.json`의 기록된 SHA와 일치하면 다음 명령으로 새 폴더에 렌더합니다. 다른 GPU/런타임의 새 모델 결과는 바이트가 다를 수 있어 원래 검수 승인을 재사용할 수 없습니다. SHA 불일치를 완화하지 말고 새 검수를 기록하세요. 라이선스가 있는 로컬 Jibaek120 파일은 공개된 SHA와 일치해야 합니다.

```text
python src/render_collection_hidden.py --manifest reel_collection_manifest.json --output-dir <new-folder> --credit-font <licensed-local-Jibaek-120g-beta.otf>
python src/audit_collection_boundaries.py --root . --manifest reel_collection_manifest.json --output-dir <new-folder> --audit-output <new-audit-folder>
```

`--check-history`는 기존 모든 버전의 로컬 영상·receipt와 preserved baseline이 있는 제작 환경에서만 사용합니다. 기술 성공은 직접 시각 승인과 별개입니다. 모델·원본·이전 결과를 보존하며 새 출력 폴더만 사용하세요.
'''
    (root/'README.md').write_text(readme,encoding='utf-8')
    print(json.dumps({'cases':13,'combined_seconds':221,'report':'review.html'}))

if __name__=='__main__':main()
