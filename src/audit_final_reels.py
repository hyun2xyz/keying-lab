#!/usr/bin/env python3
"""Audit completed local final reels; optional production history check requires local legacy outputs."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from PIL import Image

SELECTED = [0, 67, 90, 112, 135, 180, 315, 360, 509]


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--ffmpeg",default="ffmpeg")
    parser.add_argument("--manifest",type=Path,help="Manifest used for the completed local render")
    parser.add_argument("--output-dir",type=Path,help="Completed render folder containing final_receipt.json")
    parser.add_argument("--audit-output",type=Path,help="New audit folder; existing evidence is never overwritten")
    parser.add_argument("--check-history",action="store_true",help="Also require private production legacy receipts/videos and preserved baseline")
    args=parser.parse_args()
    root=args.root.resolve(); out=args.output_dir.resolve() if args.output_dir else root/"reels/final_v5"
    manifest_path=args.manifest.resolve() if args.manifest else root/"reel_final_manifest.json"
    script=root/"src/render_final_reels.py"
    receipt=json.loads((out/"final_receipt.json").read_text(encoding="utf-8"))
    preview_path=out/"previews/final_receipt.json"
    preview=json.loads(preview_path.read_text(encoding="utf-8")) if preview_path.exists() else receipt
    assert receipt["status"]=="ENCODED_TECHNICALLY_VERIFIED_REQUIRES_VISUAL_QA"
    assert receipt["output_size"]==[1080,1350] and len(receipt["videos"])==9
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location("final_encoded_audit_renderer",script)
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    m.cv2.setNumThreads(2)
    assert m.sha(script)==receipt["renderer_sha256"]==preview["renderer_sha256"]
    assert m.sha(manifest_path)==receipt["manifest_sha256"]==preview["manifest_sha256"]
    history_videos_checked=0
    if args.check_history:
        baseline=json.loads((out/"preserved_baseline.json").read_text(encoding="utf-8"))
        assert all(m.sha(root/path)==digest for path,digest in baseline.items())
        for old in ("reels/final_v1/render_receipt.json","reels/motion_v2/motion_receipt.json","reels/hold_v3/pilots/hold_receipt.json","reels/pause_v4/pilots/pause_receipt.json"):
            legacy=json.loads((root/old).read_text(encoding="utf-8"))
            assert all(m.sha(Path(v["path"]))==v["sha256"] for v in legacy["videos"])
            history_videos_checked+=len(legacy["videos"])
    cases,identity=m.load_cases(manifest_path,None)
    assert len(cases)==8
    for a,b in zip(receipt["cases"],preview["cases"]):
        assert a["id"]==b["id"] and a["input_files"]==b["input_files"] and a["roi"]==b["roi"]
    for video in receipt["videos"]:
        assert m.sha(Path(video["path"]))==video["sha256"]
        count=4080 if Path(video["path"]).name.startswith("keying_breakdown") else 510
        assert video["frames"]==video["full_decode_frames"]==count
        assert video["seconds"]==count/30 and video["all_packet_pts_dts_durations_checked"]
        assert video['actual_crf_confirmed']==10 and video['preset_from_encoding_invocation']=='slow'
        assert 'crf=10.0' in video['actual_x264_sei']
        assert video['published_color']['codec_name']=='h264' and video['published_color']['profile']=='High'
        assert video['published_color']['pix_fmt']=='yuv420p'
        if not Path(video['path']).name.startswith('keying_breakdown'):
            invocation=video['encoder_command']
            assert invocation[invocation.index('-crf')+1]=='10' and invocation[invocation.index('-preset')+1]=='slow'
    fonts=m.Fonts(Path(receipt["font"]["path"]))
    assert m.sha(fonts.path)==receipt["font"]["sha256"]
    destination=args.audit_output.resolve() if args.audit_output else out/"encoded_review";destination.mkdir(exist_ok=True,parents=True)
    if (destination/"final_encoded_audit.json").exists(): raise RuntimeError("Existing audit; do not overwrite")
    result={"status":"TECHNICAL_FINAL_HQ_AUDIT_PASSED_CONTACTS_REQUIRE_DIRECT_REVIEW",
            "renderer_sha256":receipt["renderer_sha256"],"manifest_sha256":receipt["manifest_sha256"],
            "source_and_prediction_png_sha_all_match_v1":True,"production_history_checked":args.check_history,"legacy_videos_checked":history_videos_checked,
            "all9_final_videos_full_decode_color_clock_metadata_proofs_bound":True,
            "all4080_runtime_source_viewport_wipe_and_footer_events_checked":True,
            "all4080_authored_header70_and_footer_blank":True,"all4080_only2_panel_text_tags":True,
            "encoding_quality":{"crf":10,"preset":"slow","actual_codec":"h264","actual_profile":"High","actual_pixel_format":"yuv420p","all9_crf_confirmed_in_x264_sei":True,"direct_native_png":True},
            "case_frames":510,"case_seconds":17,"combined_frames":4080,"combined_seconds":136,
            "wipe_frames":15,"comparison_dwell_frames":30,
            "ground_truth_available":False,"accuracy_metrics_computed":False,
            "selected_output_indices":SELECTED,"preview_receipt_compared":preview_path.exists(),"cases":[],
            "rgb_residual_note":"Descriptive lossy H264/YUV420p display-code differences; not matte/GT error."}
    for case,proof in zip(cases,receipt["videos"][:8]):
        assert case.inputs==next(x for x in receipt["cases"] if x["id"]==case.id)["input_files"]
        ledger_path=Path(proof["runtime_frame_ledger"])
        assert m.sha(ledger_path)==proof["ledger_sha256"]
        ledger=[json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
        assert len(ledger)==510
        for n,event in enumerate(ledger):
            rect,matrix=m.viewport(case,n,(1080,608))
            assert event["output_index"]==n and event["source_index"]==m.source_index(n)
            assert event["viewport_native_xywh"]==rect and event["shared_viewport_matrix"]==matrix.tolist()
            assert event["upper_lower_viewport_identical"] and event["wipe"]==m.wipe_state(n,1080)
            assert event['authored_header_blank'] and event["authored_footer_blank"] and not event["roi_guide_drawn"]
            assert len(event["authored_text_boxes"])==2
            assert event["authored_text_boxes"][0][1]>=70 and event["authored_text_boxes"][0][3]<=140
            assert event["authored_text_boxes"][1][1]>=698 and event["authored_text_boxes"][1][3]<=768
        assert sum(e["wipe"]["line_visible"] for e in ledger)==84
        holds={}
        for name,start,end,expected_sources in (("first_checker",165,255,72),("detail_checker",390,510,96)):
            captured=ledger[start:end]
            assert len(captured)==end-start
            assert len({tuple(v for row in e['shared_viewport_matrix'] for v in row) for e in captured})==1
            assert len({tuple(e['viewport_native_xywh']) for e in captured})==1
            assert all(e['wipe']['before']==e['wipe']['after']=='checker' and not e['wipe']['line_visible'] for e in captured)
            assert len({e['source_index'] for e in captured})==expected_sources
            holds[name]={'indices':[start,end-1],'frames':end-start,'seconds':(end-start)/30,
                         'viewport_matrix_unique':1,'wipe_active_frames':0,'source_indices_unique':expected_sources,
                         'raw_rgb_unique':len({e['raw_rgb_sha256'] for e in captured})}
        dwells={}
        for material,start,end in (("source",75,105),("alpha",120,150),("black",300,330),("white",345,375)):
            captured=ledger[start:end]
            assert len(captured)==30
            assert len({tuple(v for row in e['shared_viewport_matrix'] for v in row) for e in captured})==1
            assert all(e['wipe']['before']==e['wipe']['after']==material and not e['wipe']['line_visible'] for e in captured)
            assert len({e['source_index'] for e in captured})==24
            dwells[material]={'indices':[start,end-1],'frames':30,'seconds':1,'viewport_matrix_unique':1,
                              'wipe_active_frames':0,'source_indices_unique':24,
                              'raw_rgb_unique':len({e['raw_rgb_sha256'] for e in captured})}
        ratio=1080/608
        detail_width=max(case.detail_roi[2],case.detail_roi[3]*ratio)
        first_width=max(case.roi[2],case.roi[3]*ratio)
        expected_zoom=1080/detail_width
        maximum_zoom=max(1080/e['viewport_native_xywh'][2] for e in ledger)
        assert abs(maximum_zoom-expected_zoom)<1e-12
        assert maximum_zoom<=expected_zoom+1e-12
        assert proof['hold_validation']==m.validate_hold_ledger(case,ledger,(1080,1350))
        expr="+".join(f"eq(n\\,{n})" for n in SELECTED)
        command=[args.ffmpeg,"-nostdin","-hide_banner","-v","error","-i",str(out/(case.id+"_reel.mp4")),
                 "-vf",f"select={expr},scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgb24",
                 "-fps_mode","passthrough","-f","rawvideo","pipe:1"]
        decoded=subprocess.run(command,capture_output=True)
        if decoded.returncode: raise RuntimeError(decoded.stderr.decode("utf-8",errors="replace"))
        frames=np.frombuffer(decoded.stdout,np.uint8).reshape((9,1350,1080,3))
        contact=Image.new("RGB",(1080,1350),"white");stats=[]
        for cell,(n,actual) in enumerate(zip(SELECTED,frames)):
            expected,_=m.frame(case,n,fonts,(1080,1350))
            assert hashlib.sha256(expected.tobytes()).hexdigest()==ledger[n]["raw_rgb_sha256"]
            assert np.all(np.asarray(expected)[:70]==255) and np.all(np.asarray(expected)[1306:]==255)
            header_delta=255-actual[:70].astype(np.int16)
            footer_delta=255-actual[1306:].astype(np.int16)
            assert float(header_delta.mean())<=1.0 and float(footer_delta.mean())<=1.0
            assert int((255-actual[:60].astype(np.int16)).max())<=3
            assert int((255-actual[1320:].astype(np.int16)).max())<=3
            delta=np.abs(actual.astype(np.int16)-np.asarray(expected).astype(np.int16))
            stats.append({"output_index":n,"source_index":m.source_index(n),"raw_rgb_sha_matches_runtime":True,
                          "authored_header70_blank":True,"authored_footer_blank":True,
                          "coded_header70_white_mean_error":float(header_delta.mean()),
                          "coded_footer44_white_mean_error":float(footer_delta.mean()),
                          "coded_inner_header_footer_white_within3_codes":True,
                          "mean_absolute_rgb_codes":float(delta.mean()),"p99":float(np.percentile(delta,99)),"max":int(delta.max())})
            contact.paste(Image.fromarray(actual).resize((360,450),Image.Resampling.LANCZOS),((cell%3)*360,(cell//3)*450))
        contact_path=destination/(case.id+"_final_encoded.jpg")
        contact.save(contact_path,quality=95,subsampling=0)
        result["cases"].append({"id":case.id,"decoded_contact":str(contact_path),"sha256":m.sha(contact_path),
                                "ledger_events":510,"wipe_line_visible_frames":84,"checker_holds":holds,"comparison_dwells":dwells,
                                "maximum_native_zoom_measured":maximum_zoom,"maximum_native_zoom_target":expected_zoom,
                                "detail_relative_to_first":first_width/detail_width,"zoom_overshoot":False,
                                "selected_frame_comparisons":stats,"decode_command":command})
        m.load_native.cache_clear()
        print(f"Final HQ encoded audit/contact ready: {case.id}",flush=True)
    with (destination/"final_encoded_audit.json").open("x",encoding="utf-8",newline="\n") as h:
        json.dump(result,h,ensure_ascii=False,indent=2,allow_nan=False);h.write("\n")
    print(json.dumps({"status":result["status"],"audit":str(destination/"final_encoded_audit.json")}),flush=True)
    return 0


if __name__=="__main__": raise SystemExit(main())
