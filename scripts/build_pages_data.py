"""Bundle only the reviewed release examples. Never read the user's local database.

No simulations are executed. The source recordings remain unmodified. Large shared
network descriptions are de-duplicated; the browser restores them before inspection.
"""
import csv
import gzip
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'examples/case-study'
OUT = ROOT / 'frontend/public/demo'

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(',', ':'), allow_nan=False))

def main():
    from backend.models import Scenario
    from backend import network
    from backend.exports import report_html, report_pdf
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    catalog = json.loads((SOURCE/'catalog.json').read_text())
    index = json.loads((SOURCE/'index.json').read_text())
    result = {'defaults': Scenario().model_dump(), 'demo': index, 'jobs': [], 'tasks': [], 'observations': [], 'networks': []}
    for table, description in catalog.items():
        for values in description['rows']:
            row = dict(zip(description['columns'], values))
            payload = json.loads(row.pop('payload'))
            if table == 'jobs': row['scenario'] = payload
            elif table == 'tasks':
                row['spec'] = payload; row['detail'] = json.loads(row['detail'])
            else: row.update(payload)
            result[table].append(row)
    # Network conversion is read-only and uses an isolated copy of the reviewed inputs.
    with tempfile.TemporaryDirectory(prefix='citylab-pages-') as tmp:
        network.DATA = Path(tmp)
        shutil.copytree(ROOT/'examples/networks', network.DATA/'networks')
        network.ensure_synthetic()
        for directory in sorted((network.DATA/'networks').iterdir()):
            n = network.describe(directory.name)
            result['networks'].append({'id': n['id'], 'label': n['label']})
            write(OUT/'networks'/f"{n['id']}.json", n)
    for job in result['jobs']:
        source = SOURCE/'data/jobs'/job['id']; target = OUT/'jobs'/job['id']
        run = json.loads((source/'result.json').read_text())
        write(OUT/'networks'/f"{run['network']['version']}.json", run['network'])
        packed = {**run, 'network_ref': run['network']['version']}; del packed['network']
        write(target/'result.json', packed)
        frames = source/'frames'
        if (frames/'index.json').exists():
            shutil.copyfile(frames/'index.json', target/'frames-index.json')
            for chunk in frames.glob('*.json.gz'):
                write(target/'frames'/chunk.name.removesuffix('.gz'), json.loads(gzip.decompress(chunk.read_bytes())))
        else: write(target/'frames-index.json', {'count':0,'chunk_size':32,'last_time':0})
        buffer=io.StringIO(); writer=csv.writer(buffer); writer.writerow(['metric','value'])
        for key, value in run['metrics'].items():
            if key!='warnings': writer.writerow([key,'' if value is None else value])
        (target/'export.csv').write_text(buffer.getvalue())
        with zipfile.ZipFile(target/'bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
            for name in ['result.json','manifest.json','network.json','network.net.xml','routes.xml']:
                if (source/name).exists(): z.write(source/name,name)
            z.writestr('README.txt','Authentic recorded synthetic example. Generated demand; no Bangalore field observations. Frame playback is bundled separately on Pages. Install the full application to reproduce simulations.')
    for task in result['tasks']:
        source=SOURCE/'data/tasks'/task['id']; target=OUT/'tasks'/task['id']
        report=json.loads((source/'result.json').read_text())
        write(target/'result.json',report)
        (target/'report.html').write_text(report_html(report))
        report_pdf(report,target/'report.pdf')
        with zipfile.ZipFile(target/'evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
            for name in ['result.json','report.html','report.pdf']: z.write(target/name,name)
            for rid in sorted({r['run_id'] for r in report.get('records',[])}):
                folder=SOURCE/'data/jobs'/rid
                for name in ['result.json','manifest.json','network.net.xml','routes.xml']:
                    if (folder/name).exists(): z.write(folder/name,f'runs/{rid}/{name}')
            if task['kind']=='calibration':
                # Calibration's source observations and exact replicate records are evidence too.
                for p in source.rglob('*'):
                    if p.is_file(): z.write(p,'calibration/'+str(p.relative_to(source)))
                z.write(SOURCE/'synthetic-observations.csv','SYNTHETIC-observations.csv')
    for observation in result['observations']:
        target=OUT/'observations'/observation['id']; target.mkdir(parents=True)
        shutil.copyfile(SOURCE/'data/observations'/observation['id']/'original.csv',target/'original.csv')
    write(OUT/'catalog.json',result)
    print(f"Bundled {len(result['jobs'])} authentic runs, {len(result['tasks'])} completed studies; no simulations executed.")

if __name__=='__main__':main()
