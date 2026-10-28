"""Build review documents from actual completed real-footage tests."""
import argparse
import csv
import html
import json
from pathlib import Path
import shutil


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args();root=args.root.resolve()
    data=json.loads((root/'dataset_manifest.json').read_text(encoding='utf-8'))
    metrics=[]
    for c in data['cases']:
        current=root/'results'/c['id']/'metrics.json'
        metrics.append(json.loads((current if current.exists() else root/'qa/native_metrics'/f'{c["id"]}.json').read_text(encoding='utf-8')))
    assert len(metrics)==8 and all(m['id']!='02_dance' for m in metrics) and all(m['frames']==96 and m['ground_truth_available'] is False for m in metrics)
    fields=['id','title','width','height','frames','fps','engine_seconds','processing_fps','screen_probe_mean_alpha','peak_torch_allocated_GiB']
    with (root/'qa/metrics.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fields);writer.writeheader();writer.writerows({k:m[k] for k in fields} for m in metrics)
    summary={'cases':[{k:m[k] for k in fields} for m in metrics],'source_frames':768,'source_duration_seconds':32,
        'total_engine_seconds':round(sum(m['engine_seconds'] for m in metrics),3),'ground_truth_available':False,
        'accuracy_score':None,'source_categories':[c['title'] for c in data['cases']],
        'quality_evidence':'Native ROI, black/white/checker, first/middle/end and adjacent46..50 frames; see manual_review.json. Full technical video decode is separate from sampled visual review.'}
    (root/'qa/summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    sections=[];table=[]
    for c,m in zip(data['cases'],metrics):
        ident=c['id'];title=html.escape(c['title']);credit=html.escape(c['credit'])
        roi_name='05_furniture_roi_review_v2.jpg' if ident=='05_furniture' else f'{ident}_roi_review.jpg'
        sections.append(f'''<article><h2>{title}</h2><p>{credit}. <a href="{html.escape(c['source_page'])}">공식 원본 다운로드</a></p>
<p>{c['width']}×{c['height']},96프레임@24fps / 모델 처리 {m['engine_seconds']:.1f}초. GT 없음.</p>
<video controls muted loop preload="none" src="reels/final_v5/{ident}_reel.mp4"></video>
<details><summary>원본 ROI·알파·체커·검정·흰색과 연속 프레임 검수</summary><a href="qa/{roi_name}"><img loading="lazy" src="qa/{roi_name}" alt="Real source alpha and three composite backgrounds"></a></details></article>''')
        table_credit=c['credit'].replace('|',chr(92)+'|')
        table.append(f'| {ident} | {c["title"]} | [{table_credit}]({c["source_page"]}) | {c["width"]}×{c["height"]} | {m["engine_seconds"]:.1f}s |')
    page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Keying Lab · 실사8종 검수</title>
<style>body{background:#14191e;color:#edf1f4;font:16px/1.65 system-ui;max-width:1120px;margin:40px auto;padding:0 20px}a{color:#91dfc3}article{margin-top:48px;border-top:1px solid #48515a;padding-top:16px}img{width:100%;height:auto}video{width:min(100%,540px);display:block;margin:18px 0}summary{cursor:pointer}</style>
<h1>CorridorKey 2.0 · 실제 촬영 소스 8종</h1>
<p>곱슬머리·안경, 남성 발표자, 강아지 털, 반투명 숄, 가구 표면, 사무실2인, 중년2인, 소품을 든 남성. 서로 다른 소재의 실제 촬영본을 공식 무료 이용 조건에 따라 다운로드해 처리했습니다. 원본·결과 모두 출처 조건을 따르며 CC0로 재허가하지 않습니다.</p>
<p>완성 릴스는1080×1350/30fps, 위 원본·아래 실제 결과입니다. 와이프는0.5초이며 바뀐 비교 화면마다1초씩 머뭅니다. 첫 확대·비교 뒤 체커 결과3초, 머리카락·반투명 경계를 더 확대·비교한 뒤 체커 결과4초를 유지합니다. 카메라와 와이프만 멈추며 원본 영상은 계속 움직입니다. 상단 컷 제목과 하단 자막을 없애고 패널 안의 흰 박스·검정 글씨 구분만 남겼습니다. 정식1080×1350에서직접렌더한H264 high/CRF10/slow MP4입니다. 사례당4초 촬영 구간을4.25회 반복해17초로 구성했고 합본136초입니다. 음악·내레이션 없음.</p>
<video controls preload="metadata" src="reels/final_v5/keying_breakdown_real8_1080x1350.mp4"></video>
<p><a href="https://github.com/hyun2xyz/keying-lab">공개 GitHub</a> · <a href="https://github.com/hyun2xyz/keying-lab/releases/tag/v1.1.0">완성 릴스·OBS 편집본·검수 패키지</a> · <a href="qa/manual_review.json">직접 검수 기록</a> · <a href="qa/metrics.csv">처리 기록 CSV</a></p>
<p>실사 정답 알파는 제공되지 않아 정확도 점수를 만들지 않았습니다. 작은 배경 영역의 알파와 처리시간은 진단값입니다. 원본960×720의 비정방 픽셀 숄은1280×720 정방 픽셀로 바로잡았고, 영상25/30/60fps는 실제 속도를 유지해24fps로 프레임 선택했습니다.</p>
<p>OBS는 실제 로컬 작업 모니터를 녹화했습니다. 최신 <a href="recordings/process_hold_revision.mp4">체커 유지·세부 확대 수정 과정</a>은 편집 준비와 중간 파일럿, 기존 결과 재생을 담았습니다. 사용자 요청으로 녹화를 중단했으므로 이후 최종1080 HQ 렌더·검수는 포함하지 않습니다. <a href="docs/obs_hold_audit.json">녹화 검증</a>에 범위를 기록했습니다. 이전 <a href="https://github.com/hyun2xyz/keying-lab/releases/download/v1.0.0/process_recording.mp4">추론·초기 편집 과정</a> 및 <a href="https://github.com/hyun2xyz/keying-lab/releases/download/v1.0.0/process_motion_revision.mp4">줌·와이프 수정 과정</a>은v1.0.0 릴리스의 작업 이력입니다.</p>'''
    (root/'review.html').write_text(page+'\n'.join(sections)+'</html>',encoding='utf-8')
    readme='''# Keying Lab — CorridorKey 2.0 real footage

여덟 종류의 **실제 촬영된 그린스크린 자료**를 다운로드해 테스트한 기록입니다.
곱슬머리·안경, 남성 발표자, 강아지 털, 반투명 숄, 가구 표면, 사무실2인, 중년2인, 소품을 든 남성을 살펴봅니다.

[136초 1080×1350 릴스](https://github.com/hyun2xyz/keying-lab/releases/download/v1.1.0/keying_breakdown_real8_1080x1350.mp4) ·
[개별 릴스·OBS 편집본·검수 패키지](https://github.com/hyun2xyz/keying-lab/releases/tag/v1.1.0)

![실제 촬영 소스 8종](qa/source_contact.jpg)

위에 원본, 아래에 실제 키잉 결과를 놓았습니다. 회색 체커보드, 같은 위치의 확대,
모델 알파 화면이 포함됩니다. 네모 표시 없이 부드럽게 같은 영역으로 확대하고 세로 와이프로
원본·체커·알파·검정/흰 배경을 비교합니다. 와이프를0.5초로 늦추고 각 비교 화면에서1초씩 머뭅니다. 첫 체커 결과3초, 머리카락·반투명 경계의 추가 확대·비교 뒤 체커 결과4초를 유지합니다. 카메라와 와이프만 멈추며 영상은 계속 움직입니다. 상단 컷 제목과 하단 자막을 모두 없애고 BEFORE/AFTER/ALPHA만 흰 박스·검정 글씨로 표시합니다. 정식1080×1350에서 H264 high/CRF10/slow로 직접 렌더했습니다.
각4초 입력을4.25회 반복해17초씩 구성했으며 합본은136초입니다.
오디오·음원은 없습니다. 모델 추론 결과에 수동 마스크·알파 크런치·경계 복구를 추가하지 않았습니다.

| ID | 검사 소재 | 출처·크레딧 | 처리 입력 크기 | 실제 모델 시간 |
| --- | --- | --- | --- | --- |
'''+ '\n'.join(table)+'''

출처별 라이선스가 다릅니다. 모두 무료 이용 가능한 자료이나 저작권이 없는 자료는 아닙니다.
[RIGHTS.md](docs/RIGHTS.md)를 확인하세요. 원본 및 원본을 추출한PNG는 로컬에 보관하고,
공개 저장소에는 공식 다운로드 페이지·프레임 범위·SHA256 및 편집된 비교·검수 자료를 제공합니다.
독립된 전경/알파 시퀀스와 전체 처리 원본은 로컬에 보관합니다. 공개 영상 안에서 알파와 확대 결과를 확인할 수 있습니다.
같은 영화의 다섯 컷으로 구성한 테스트가 아닙니다.

## 검수와 해석

- 8종×96프레임@24fps, 총768프레임/32초의 실제 입력.
- 원본 크기에서 알파를 디코드하고, 체커·검정·흰색 합성에서 시작/중간/끝과 연속46–50프레임을 직접 검사했습니다.
- [직접 검수](qa/manual_review.json), [ROI 이미지](qa), [실행 수치](qa/metrics.csv), [모델/런타임 버전](docs/runtime.json).
- 실사 정답 알파가 없으므로 MAE/정확도/GT점수를 제시하지 않습니다. `screen_probe_mean_alpha`는 사전에 지정한 작은 배경 사각형의 진단값이며 전 화면 배경 정확도가 아닙니다.
- 알파 변화량에는 실제 피사체·카메라 움직임이 포함되므로 깜빡임 점수로 해석할 수 없습니다.
- 모델ProRes의10-bit 입력 변환 오차를 보존했습니다. 디코드PNG의16-bit 저장 공간은16-bit 유효 알파 정밀도를 뜻하지 않습니다. [같은 장비의 코덱 제어 측정](docs/alpha_codec_control.json).
- 기술 검증은 전체 디코드·해상도·프레임 수·시간·색상 태그 확인이며, 직접 눈으로 한 검수는 표본 및 연속 프레임 검사입니다.
- 샷 밖 장비/실물 추적 마커 제거는 별도 합성 작업입니다. 실제 결과의 잔류물과 한계를 그대로 남겼습니다.
- 최신 OBS 녹화는 편집 준비와 중간 파일럿, 기존 결과 재생을 기록했습니다. 사용자 요청으로 녹화를 중단해 이후 최종1080 HQ 렌더·검수는 포함하지 않습니다. [최신 녹화 확인](docs/obs_hold_audit.json). 이전 추론/줌·와이프 과정2편은v1.0.0 릴리스에 보존했습니다. 재생된 리뷰를 새 모델 추론으로 표시하지 않습니다.
- [최신 편집 검수](docs/hold_render_audit.json): 첫 체커3초, 세부 체커4초의뷰포트와와이프고정을검사합니다. 확대는기존픽셀의디지털크롭이며새해상도복원이나새모델출력을뜻하지않습니다.

## 다시 실행하기

Python3.12, FFmpeg/ffprobe7.1.1, `requirements-review.txt`의NumPy/Pillow/OpenCV로 리뷰 도구를 실행했습니다.
외부 CorridorKey2.0은 별도 설치된 환경이 필요합니다. 코드/가중치는 이 저장소에 포함되지 않습니다.
`docs/runtime.json`의 커밋과 모델 리비전을 확인하고 외부 도구의 라이선스를 따르세요.

1. 표의 공식 페이지에서 각 원본을 무료 다운로드합니다. Mixkit는 해당 소스 페이지에 명시된 Stock Video Free License 버전을 사용합니다. `dataset_manifest.json`의원본SHA와 파일명을 대조합니다.
2. `python src/fetch_tos_hair.py --root .`로 CC BY 원본의 선택된96EXR과 리뷰용PNG를 준비합니다. 파일 목록과 원본 해시를 모두 기록합니다.
3. `python src/prepare_inputs.py --root . --downloads <download-folder> --shawl-zip <GodivaClose.zip>`으로96@24fps 입력PNG를 만듭니다. 원본 속도를 유지하며 프레임만 선택합니다. TOS는linear→sRGB, 동영상은limitedBT709→fullsRGB를 명시합니다. HCW는 원래RGB코드값의sRGB표시 해석입니다.
4. 외부 엔진의Python으로 `python src/run_real_case.py --root . --engine <CorridorKey2.0> --cache <SSD-cache> --case <id>`를 각사례에 실행합니다. 새 결과 디렉토리만 생성합니다.
5. `reel_final_manifest.json`은 소스/실제prediction·크레딧·첫ROI와더깊은detail_roi를묶습니다. 공개 체크아웃에서는 `python src/prepare_motion_repro.py --root .`로 공개 검증 기록에 모든 입력/예측PNG의SHA가 일치하는지 확인하고 로컬참조를 만든 뒤, `python src/render_final_reels.py --manifest reel_final_local_manifest.json --output-dir reels/final_v5`로 최종 릴스를 렌더합니다. PNG가 달라지면 원래 검수 결과를 재사용하지 않고 중단합니다. 다른GPU/런타임의 새 모델 출력은 바이트가 다를 수 있어 새 검수가 필요합니다. 기존renderer/매니페스트와v1.0.0 릴리스는 보존했습니다.
6. `python src/audit_final_reels.py --root . --manifest reel_final_local_manifest.json --output-dir reels/final_v5 --audit-output <new-audit-folder>`로 완료된 로컬 렌더의 프레임 기록·파일 정보와 실제 디코드 비교 이미지를 검사합니다. `--check-history`는 이전 버전의 로컬 영상·영수증까지 보존한 제작 환경에서만 사용합니다.
7. `python src/build_report.py --root .`로 로컬리뷰와CSV를 생성합니다. 실제시각검수 없이 이를 품질승인으로 간주하지 마세요.

하드웨어는RTX4070TiSUPER16GB, 작업 저장소는C:NVMeSSD입니다. 모든 사례에 `low_vram`, Hann24/stride12, despill0.5, 입력알파힌트없음을 사용했습니다. 다른GPU앱도실행중이었으므로 시간은 통제된성능벤치마크가 아닙니다.

`src`의 독립적인 유틸리티는[MIT](LICENSE-CODE.txt)입니다. CorridorKey/Corridor Digital 및 모델 의존성은 별도 라이선스이며 재배포하지 않습니다. 영상/소스는[원저작자별 조건](docs/RIGHTS.md)이 적용됩니다.
'''
    (root/'README.md').write_text(readme,encoding='utf-8')
    print(json.dumps({'cases':8,'frames':768,'engine_seconds':summary['total_engine_seconds'],'report':'review.html'}))


if __name__=='__main__':main()
