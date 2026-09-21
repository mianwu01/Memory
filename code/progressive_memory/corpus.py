"""Full-corpus CPU BM25 adapter with deterministic tool provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import tiktoken

STOP = set("a an the is are was were be been being in on at of to for from by with and or that this which who what when where as it its they their he she his her did do does had has have individual stated certain according article interview country city between".split())


def build(source, target):
    import pyarrow.parquet as pq
    source, target = Path(source), Path(target)
    if target.exists():
        raise RuntimeError("Index exists; inspect metadata instead of overwriting")
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE docs(docid TEXT PRIMARY KEY, text TEXT, url TEXT, sha256 TEXT)")
    db.execute("CREATE VIRTUAL TABLE search USING fts5(text, content='docs', content_rowid='rowid', tokenize='porter unicode61')")
    count = 0
    for path in sorted(source.glob('*.parquet')):
        pf = pq.ParquetFile(path)
        print('schema', path.name, pf.schema_arrow.names, flush=True)
        for batch in pf.iter_batches(batch_size=256):
            values = []
            for row in batch.to_pylist():
                docid = str(row.get('docid', row.get('id')))
                text = row.get('text') or row.get('contents') or row.get('content')
                if not isinstance(text, str) or docid == 'None':
                    raise ValueError('Unknown corpus schema')
                title = row.get('title') or ''
                text = (title+'\n'+text).strip() if title else text
                values.append((docid, text, str(row.get('url') or ''), hashlib.sha256(text.encode()).hexdigest()))
            db.executemany('INSERT INTO docs VALUES (?,?,?,?)', values)
            count += len(values)
        db.commit()
        print('indexed_docs', count, flush=True)
    db.execute("INSERT INTO search(search) VALUES ('rebuild')")
    db.commit()
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.close()
    target.with_suffix('.metadata.json').write_text(json.dumps(dict(documents=count, source=json.loads((source/'source.json').read_text()), backend='SQLite FTS5 BM25, porter unicode61'),indent=2))
    print('complete',count,flush=True)


class Corpus:
    def __init__(self, path, log=None, blocked=()):
        self.db = sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro', uri=True)
        self.db.row_factory = sqlite3.Row
        self.encoder = tiktoken.get_encoding('cl100k_base')
        self.log = log if log is not None else []
        self.blocked = set(blocked)

    def _document(self, row, limit):
        tokens = self.encoder.encode(row['text'], disallowed_special=())
        return dict(docid=row['docid'], text=self.encoder.decode(tokens[:limit]), url=row['url'],
                    original_sha256=row['sha256'], original_tokens=len(tokens), truncated=len(tokens)>limit)

    def search(self, query, k=5, allowed_docids=None):
        words = list(dict.fromkeys(w.lower() for w in re.findall(r'\w+', query) if w.lower() not in STOP and len(w)>1))[:48]
        if not words:
            return []
        match = ' OR '.join('"'+w.replace('"','')+'"' for w in words)
        rows = self.db.execute('SELECT docs.*, bm25(search) AS rank FROM search JOIN docs ON docs.rowid=search.rowid WHERE search MATCH ? ORDER BY rank LIMIT 200',(match,)).fetchall()
        selected = [r for r in rows if r['docid'] not in self.blocked and (allowed_docids is None or r['docid'] in allowed_docids)][:k]
        result = [{**self._document(r,512),'score':-r['rank']} for r in selected]
        self.log.append(dict(tool='search',query=query,results=result))
        return result

    def get_document(self, docid):
        if str(docid) in self.blocked:
            self.log.append(dict(tool='get_document',docid=str(docid),blocked=True))
            return None
        row = self.db.execute('SELECT * FROM docs WHERE docid=?',(str(docid),)).fetchone()
        result = self._document(row,6000) if row else None
        self.log.append(dict(tool='get_document',docid=str(docid),result=result))
        return result

    def search_description(self,k=5):
        return f'Search the full authorized BrowseComp-Plus corpus. Returns top-{k} document snippets. Use discriminative terms, names and quoted concepts; refine searches as needed.'

    def get_document_description(self):
        return 'Read the document for a docid returned by search (up to 6000 tokens).'


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',default='.tmp/progressive_search')
    p.add_argument('--target',default='.tmp/progressive_search/corpus.sqlite')
    args=p.parse_args();build(args.source,args.target)
