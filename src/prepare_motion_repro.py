"""Bind the portable public native proof to a new local motion manifest.

Only exact source/prediction PNG identities from the recorded test are accepted.
This does not relax hashes, manufacture decode proof, or imply a fresh GPU run
will be byte-identical. Different predictions require a new reviewed run.
"""
import argparse,hashlib,json
from pathlib import Path

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--manifest',default='reel_final_manifest.json')
    parser.add_argument('--output-manifest',default='reel_final_local_manifest.json')
    args=parser.parse_args();root=args.root.resolve()
    assert Path(args.manifest).name==args.manifest and Path(args.output_manifest).name==args.output_manifest
    published=root/'docs/reel_render_receipt.json'
    prior=json.loads(published.read_text(encoding='utf-8'))
    manifest=json.loads((root/args.manifest).read_text(encoding='utf-8'))
    proof={'kind':'PORTABLE_COPY_OF_RECORDED_NATIVE_INPUT_IDENTITIES','public_receipt_sha256':sha(published),'cases':[]}
    ids={c['id'] for c in manifest['cases']};assert len(ids)==8 and '02_dance' not in ids
    for case in prior['cases']:
        if case['id'] not in ids:continue
        item={k:case[k] for k in ('id','roi','native_size','credit','ground_truth_available','input_files')}
        assert item['ground_truth_available'] is False and len(item['input_files'])==96
        for row in item['input_files']:
            for name in ('source','prediction'):
                path=(root/row[name].replace('\\','/')).resolve()
                assert path.is_relative_to(root) and path.is_file(),('Prepare the original inputs/model output first',path)
                assert sha(path)==row[name+'_sha256'],('PNG differs from recorded proof; new output needs a new reviewed run',path)
                row[name]=path.relative_to(root).as_posix()
        proof['cases'].append(item)
    assert {c['id'] for c in proof['cases']}==ids
    folder=root/'.repro';folder.mkdir(exist_ok=True)
    reference=folder/'native_reference.json';target=root/args.output_manifest
    proof_bytes=(json.dumps(proof,indent=2)+'\n').encode('utf-8')
    if reference.exists():assert reference.read_bytes()==proof_bytes,'Preserve differing existing proof; use a fresh checkout'
    else:reference.write_bytes(proof_bytes)
    manifest['reference_render_receipt']=reference.relative_to(root).as_posix()
    manifest['reference_render_receipt_sha256']=sha(reference)
    manifest['local_reference_note']='Portable public receipt, all96 source/pred PNG identities per case rechecked. Original recorded manifests remain unchanged.'
    manifest_bytes=(json.dumps(manifest,indent=2)+'\n').encode('utf-8')
    if target.exists():assert target.read_bytes()==manifest_bytes,'Preserve differing existing manifest; use a fresh checkout'
    else:target.write_bytes(manifest_bytes)
    print(json.dumps({'cases':len(proof['cases']),'matched_pngs':1536,'manifest':target.name}))
if __name__=='__main__':main()
