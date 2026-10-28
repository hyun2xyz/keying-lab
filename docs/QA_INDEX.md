# Reading the evidence

The final delivery uses **motion_v2**: continuous matched zoom, vertical
before/after wipes, white tags with black text, no ROI outlines or footer text.
The eight real camera inputs and computed mattes are shared with the first pass.

| Evidence | Purpose |
| --- | --- |
| `qa/manual_review.json` | Main native-matte findings and final presentation review. |
| `qa/*_roi_review*.jpg` | Selected native source/alpha/checker/black/white samples, including adjacent frames46–50. |
| `docs/motion_render_audit.json` and `qa/motion_encoded/` | Final motion encode and directly reviewed samples. |
| `docs/obs_motion_audit.json` and `qa/motion_process/` | Actual zoom/wipe revision capture and decoded evidence. |
| `docs/obs_recording_audit.json` and `qa/process/` | Initial inference and first-edit work history. The rejected former second example is cut out of the public recording. |
| `docs/reel_render_receipt.json`, `docs/reel_render_audit.json`, `qa/encoded_stages/` | First presentation pass, kept as history; its ROI boxes/footer are superseded. These are not the final released reels. |

Technical full decodes, color/clock checks and file identities are separate from
sampled visual review. No source has ground-truth alpha. The fixed screen probe
and inter-frame alpha change are diagnostics, not accuracy or flicker scores.
The furniture's physical tracking-marker residue remains visible in some views.

Original stock/HCW camera plates, isolated foreground/alpha sequences and
unredacted OBS capture remain local. See [rights and credits](RIGHTS.md).
