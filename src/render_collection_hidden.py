"""Use the unchanged collection renderer with hidden, resource-bounded encoders."""
import hashlib,json,sys
from pathlib import Path
import render_collection_reels as renderer
from collection_encoder_runtime import install

if __name__=='__main__':
    if '--output-dir' in sys.argv:
        out=Path(sys.argv[sys.argv.index('--output-dir')+1]).resolve();out.mkdir(parents=True,exist_ok=True)
        runtime=Path(__file__).with_name('collection_encoder_runtime.py')
        with runtime.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        with (out/'encoder_runtime_identity.json').open('x',encoding='utf-8') as f:
            json.dump({'runtime_sha256':digest,'encoder_threads':8,'filter_threads':2,'hidden_windows_process_group':True,
                       'authored_pixel_renderer':'render_collection_reels.py','authored_pixel_code_modified':False},f,indent=2)
        install(out/'process_events.jsonl',8)
    raise SystemExit(renderer.main())
