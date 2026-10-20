"""Idempotent installation of the release's authentic recorded examples."""
import json,shutil
from .network import ROOT,DATA
from .store import connect

def install_examples():
    source=ROOT/'examples/case-study'
    catalog=source/'catalog.json'
    if catalog.exists():
        for table,description in json.loads(catalog.read_text()).items():
            if table not in ('jobs','tasks','observations'):continue
            for row in description['rows']:
                with connect() as c:
                    if c.execute('SELECT 1 FROM '+table+' WHERE id=?',(row[0],)).fetchone():continue
                origin=source/'data'/table/row[0];target=DATA/table/row[0]
                if origin.exists():shutil.copytree(origin,target,dirs_exist_ok=True)
                with connect() as c:c.execute('INSERT OR IGNORE INTO '+table+' VALUES ('+','.join('?' for _ in row)+')',row)
    for folder in (ROOT/'examples/networks').glob('*'):
        if folder.is_dir() and not (DATA/'networks'/folder.name).exists():
            shutil.copytree(folder,DATA/'networks'/folder.name)
