# Reading the evidence

Current delivery: collection_v7,13 existing real-footage tests at1080×1350/30fps.
Each case is17seconds; combined221seconds. White outer margins are56px each,
the gutter is22px, and the two-line creator credit is inside the lower picture.

| Evidence | Scope |
| --- | --- |
| `qa/collection_review.json` and `qa/collection_encoded/` | Current actual encoded117sample visual review and selected full1080 views. |
| `docs/collection_render_audit.json` and `docs/collection_render_receipt.json` | All14 full decodes/color/clock/metadata; all6630 unique authored timeline events, credit/white-margin checks; old8 source/viewport/wipe clocks preserved. |
| `docs/legacy_reuse_audit.json`, `docs/legacy_display_streamcopy_audit.json`, `qa/legacy_native/` | Five earlier results:520ProRes frames fully decoded,344prepared24fps samples,688newPNG caches, original540files unchanged. Existing display interpretation is preserved, not newly measured camera colorimetry. |
| `docs/collection_layout_review.json` | Native13preview approval, v5 panel comparisons outside the new caption, and legacy detail ROI selection. |
| `qa/manual_review.json`, `docs/hold_render_audit.json`, `qa/hold_encoded/` | Prior8-case v1.1.0 native/final presentation history. |
| `docs/motion_render_audit.json`, `qa/motion_encoded/` | Earlier v1.0.0 motion presentation. |
| `docs/obs_recording_audit.json`, `docs/obs_motion_audit.json`, `docs/obs_hold_audit.json` | Earlier recordings. OBS stayed stopped for this latest edit; no new capture of this batch is claimed. |

Technical integrity is separate from sampled visual review. No source provides
ground-truth alpha. Cropping enlarges existing pixels. Legacy missing color
tags, smoke gamma-interpretation conflict, spill, matte softness and retained
studio equipment are documented. Original plates, isolated alpha/cutouts,
font and model remain local. See [rights and credits](RIGHTS.md).

See `docs/collection_job_provenance.json` for the preserved failed consumer guards and the successful audit-only successor. Lossy8px boundary bands are descriptive; the authored white geometry stays exact.
