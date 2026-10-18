#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check published text sources and local Markdown links; no device access."""
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
errors = []
count = 0
for p in ROOT.rglob('*'):
    rel = p.relative_to(ROOT)
    if not p.is_file() or any(x in rel.parts for x in ['.git', 'out', '__pycache__', 'inputs', 'private', 'cache']):
        continue
    count += 1
    raw = p.read_bytes()
    if b'\0' in raw:
        errors.append(f'{rel}: binary file in source tree')
        continue
    try:
        text = raw.decode('utf-8')
        if p.suffix == '.py':
            ast.parse(text, filename=str(rel))
        if p.suffix == '.json':
            json.loads(text)
    except (SyntaxError, UnicodeError, ValueError) as e:
        errors.append(f'{rel}: {e}')
        continue
    if b'\r\n' in raw:
        errors.append(f'{rel}: use LF line endings')
    if re.search(r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----', text):
        errors.append(f'{rel}: private key content')
    if p.suffix == '.md':
        for target in re.findall(r'\]\(([^)]+)\)', text):
            if re.match(r'[a-z]+:|#', target):
                continue
            path = target.split('#', 1)[0]
            if not (p.parent / path).exists():
                errors.append(f'{rel}: missing Markdown target {target}')
    if sys.platform != 'win32' and (text.startswith('#!/bin/sh') or text.startswith('#!/system/bin/sh')):
        r = subprocess.run(['sh', '-n', str(p)], capture_output=True, text=True)
        if r.returncode:
            errors.append(f'{rel}: {r.stderr}')
    elif sys.platform != 'win32' and text.startswith('#!/bin/bash'):
        r = subprocess.run(['bash', '-n', str(p)], capture_output=True, text=True)
        if r.returncode:
            errors.append(f'{rel}: {r.stderr}')
if errors:
    print('\n'.join(errors))
    raise SystemExit(1)
print(f'Source syntax, JSON, shell syntax and document links passed: {count} files')
