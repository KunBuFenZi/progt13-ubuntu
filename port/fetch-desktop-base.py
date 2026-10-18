#!/usr/bin/env python3
"""Fetch the reference port's pinned official Ubuntu ARM64 desktop ISO."""
import hashlib
import argparse
import json
from pathlib import Path
import re
import subprocess
import concurrent.futures
import time
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
spec = json.loads((ROOT / 'inputs/desktop-source.json').read_text())['iso']
assert urlsplit(spec['url']).netloc == 'cdimage.ubuntu.com'
assert urlsplit(spec['url']).scheme == 'https'
assert re.fullmatch('[0-9a-f]{64}', spec['sha256'])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mirror',choices=['canonical','tuna','ustc'],default='canonical')
parser.add_argument('--range-chunks',action='store_true',help='Use bounded HTTP ranges for mirrors that reject open-ended resumes')
args = parser.parse_args()
url = spec['url']
if args.mirror != 'canonical':
    host = {'tuna':'mirrors.tuna.tsinghua.edu.cn','ustc':'mirrors.ustc.edu.cn'}[args.mirror]
    url = 'https://' + host + '/ubuntu-cdimage' + urlsplit(url).path
target = ROOT / 'inputs/ubuntu-26.04-desktop-arm64.iso'
partial = target.with_suffix('.iso.part')
def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8*1024*1024), b''): h.update(chunk)
    return h.hexdigest()
if not target.exists():
    if args.range_chunks:
        def get_range(start,end,total=None):
            request=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}'})
            with urllib.request.urlopen(request,timeout=30) as response:
                assert response.status==206
                header=response.headers['Content-Range']
                assert header.startswith(f'bytes {start}-{end}/'),header
                if total is not None:assert header.endswith('/'+str(total))
                data=response.read(end-start+2)
                assert len(data)==end-start+1
                return data,int(header.split('/')[1])
        _,total=get_range(0,0)
        chunk=8*1024*1024
        position=partial.stat().st_size if partial.exists() else 0
        assert position<=total
        with partial.open('ab') as output, concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            while position<total:
                spans=[(start,min(start+chunk,total)-1) for start in range(position,min(position+4*chunk,total),chunk)]
                futures=[pool.submit(get_range,start,end,total) for start,end in spans]
                for future in futures:
                    data,_=future.result();output.write(data);position+=len(data)
                output.flush()
                print(json.dumps({'downloaded':position,'total':total,'mirror':args.mirror}),flush=True)
    else:
        subprocess.run(['curl','--fail','--location','--retry','3','--continue-at','-',
                        '--connect-timeout','20','--output',str(partial),url],check=True)
    assert digest(partial) == spec['sha256'], 'Official ISO digest does not match reference pin'
    partial.rename(target)
assert digest(target) == spec['sha256']
print(json.dumps({'status':'ISO_HASH_VERIFIED','path':str(target),
                  'size':target.stat().st_size,'sha256':spec['sha256']}),flush=True)
