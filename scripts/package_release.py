"""Build a clean release archive, excluding local runs and dependency directories."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    files=[]
    for name in ['README.md','requirements.txt','requirements.lock.txt','pytest.ini','Dockerfile','compose.yaml','.gitignore','.dockerignore']:
        files.append(ROOT/name)
    for name in ['backend','scripts','tests','frontend/src','frontend/dist','examples/synthetic','examples/networks','examples/case-study']:
        files.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and not any(x in p.parts for x in ['__pycache__','node_modules']) and p.suffix not in ['.pyc','.tmp','.log','.zip'] and p.name!='.DS_Store')
    files.extend(ROOT/'frontend'/n for n in ['package.json','pnpm-lock.yaml','tsconfig.json','vite.config.ts','index.html'])
    docnames=['clean-install-verification.json','ARCHITECTURE.md','METHODOLOGY.md','MIGRATIONS.md','VERIFICATION.md','CASE_STUDY.md','benchmark-v2.json','upgrade-before-1000.json','browser-benchmark.json','browser-v2-results.json','browser-state-results.json','paired-rerun-verification.json','hsr-topology.json','hsr-smoke.json','engine-profile.txt']
    files.extend(ROOT/'docs'/n for n in docnames)
    files.extend((ROOT/'docs').glob('v2-*.png'))
    files=sorted(set(files));manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    output=ROOT/'CityLab-2.0.0.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for p in files:archive.write(p,Path('CityLab-2.0.0')/p.relative_to(ROOT))
        archive.writestr('CityLab-2.0.0/RELEASE-MANIFEST.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert not any('/node_modules/' in n or '/.venv/' in n or '/data/jobs/' in n and '/examples/' not in n for n in archive.namelist())
    sha=hashlib.sha256(output.read_bytes()).hexdigest();output.with_suffix('.zip.sha256').write_text(sha+'  '+output.name+'\n')
    print(json.dumps({'archive':str(output),'files':len(files)+1,'bytes':output.stat().st_size,'sha256':sha},indent=2))
if __name__=='__main__':main()
