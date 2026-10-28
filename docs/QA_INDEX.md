# Reading the evidence

The final delivery uses **final_v5**: two-stage matched zoom,0.5-second vertical
before/after wipes with1-second comparison dwells, then3/4-second checker holds.
White tags use black text; there are no main case headings, ROI outlines or footer text.
Each real-footage case is17seconds at1080×1350/30fps, encoded directly from native
PNGs with H264 High/CRF10/preset slow. The combined reel is136seconds.
The eight real camera inputs and computed mattes are shared with the first pass.

| Evidence | Purpose |
| --- | --- |
| `qa/manual_review.json` | Main native-matte findings and final presentation review. |
| `qa/*_roi_review*.jpg` | Selected native source/alpha/checker/black/white samples, including adjacent frames46–50. |
| `docs/hold_render_audit.json`, `docs/hold_render_receipt.json` and `qa/hold_encoded/` | Final1080 HQ encode: all4080 timeline events checked,72 decoded samples directly reviewed, plus three full1080 detail views. |
| `docs/hold_control.json` | Authored wipe/dwell/zoom/header controls, separate from actual encoded-output proofs. |
| `docs/hold_background_completion.json` | Independent completion/hash validation after the original supervisor exited. Original job state was preserved; no rerender was performed. |
| `docs/obs_hold_audit.json` and `qa/hold_process/` | Actual editing preparation and intermediate pilots. Recording was stopped at user request before final1080 HQ render/review; those stages are outside its coverage. |
| `docs/motion_render_audit.json` and `qa/motion_encoded/` | Earlier12-second motion presentation, preserved as v1.0.0 history. |
| `docs/obs_motion_audit.json` and `qa/motion_process/` | Earlier zoom/wipe revision capture and decoded evidence. |
| `docs/obs_recording_audit.json` and `qa/process/` | Initial inference and first-edit work history. The rejected former second example is cut out of the public recording. |
| `docs/reel_render_receipt.json`, `docs/reel_render_audit.json`, `qa/encoded_stages/` | First presentation pass, kept as history; its ROI boxes/footer are superseded. These are not the final released reels. |

Technical full decodes, color/clock checks and file identities are separate from
sampled visual review. No source has ground-truth alpha. The fixed screen probe
and inter-frame alpha change are diagnostics, not accuracy or flicker scores.
The furniture's physical tracking-marker residue remains visible in some views.

Original stock/HCW camera plates, isolated foreground/alpha sequences and
unredacted OBS capture remain local. See [rights and credits](RIGHTS.md).
