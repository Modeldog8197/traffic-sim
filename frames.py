"""Atomic, indexed 32-frame gzip chunks. Reads touch at most the requested chunks."""
import threading
import gzip
import json
from pathlib import Path
CHUNK = 32

def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, separators=(',', ':')))
    tmp.replace(path)

class FrameWriter:
    def __init__(self, folder):
        self.folder = Path(folder) / 'frames'
        self.folder.mkdir(exist_ok=True, parents=True)
        self.count, self.buffer = 0, []
    def append(self, frame):
        chunk = self.count // CHUNK
        if self.count % CHUNK == 0:
            self.buffer = []
        self.buffer.append(frame)
        path = self.folder / f'{chunk:06d}.json.gz'
        tmp = path.with_suffix('.tmp')
        tmp.write_bytes(gzip.compress(json.dumps(self.buffer, separators=(',', ':')).encode(), compresslevel=1, mtime=0))
        tmp.replace(path)
        self.count += 1
        atomic_json(self.folder / 'index.json', {'count': self.count, 'chunk_size': CHUNK, 'last_time': frame['time'], 'interval': 2, 'version': 2})

def _page(folder, offset=0, limit=64):
    folder = Path(folder)
    index = folder / 'frames/index.json'
    if not index.exists():
        # One-time migration: retain original recordings unchanged.
        legacy = folder / 'frames.ndjson'
        if legacy.exists():
            writer = FrameWriter(folder)
            with legacy.open() as stream:
                for line in stream:
                    try: writer.append(json.loads(line))
                    except json.JSONDecodeError: break
        else:
            return {'frames': [], 'next': offset, 'total': 0}
    meta = json.loads(index.read_text())
    offset = max(0, offset)
    end = min(meta['count'], offset + min(max(limit, 1), 128))
    frames = []
    for chunk in range(offset // CHUNK, (end - 1) // CHUNK + 1) if end > offset else []:
        rows = json.loads(gzip.decompress((folder / 'frames' / f'{chunk:06d}.json.gz').read_bytes()))
        first = max(offset, chunk * CHUNK) - chunk * CHUNK
        last = min(end, (chunk + 1) * CHUNK) - chunk * CHUNK
        frames.extend(rows[first:last])
    return {'frames': frames, 'next': offset + len(frames), 'total': meta['count'], 'last_time': meta['last_time']}


_legacy_migration_lock = threading.Lock()
def page(folder, offset=0, limit=64):
    # A second request must not observe a partially migrated legacy index.
    if (Path(folder)/'frames.ndjson').exists():
        with _legacy_migration_lock:return _page(folder,offset,limit)
    return _page(folder,offset,limit)
