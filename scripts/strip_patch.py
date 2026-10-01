#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 unified diff 补丁中剔除指定文件的段落（替代 GNU patch 不支持的 --exclude）

用法: strip_patch.py <输入补丁> <输出补丁> [要排除的文件...]
例:   strip_patch.py in.patch out.patch kernel/sys.c
"""
import sys, os, re

if len(sys.argv) < 3:
    print('用法: strip_patch.py <in> <out> [exclude...]')
    sys.exit(1)

inp, outp = sys.argv[1], sys.argv[2]
excludes = sys.argv[3:]

with open(inp, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.read().split('\n')

blocks = []      # [(filekey, [lines])]
cur = None       # {'key':..., 'buf':[...]}
preamble = []

def path_of(txt):
    m = re.match(r'^diff --git a/(.*?) b/(.*?)$', txt.strip())
    if m:
        return m.group(2)
    m = re.match(r'^--- a/(.*?)(\t|$)', txt)
    if m:
        return m.group(1)
    m = re.match(r'^\+\+\+ b/(.*?)(\t|$)', txt)
    if m:
        return m.group(1)
    return None

for ln in lines:
    t = ln.strip()
    if t.startswith('diff --git') or (t.startswith('--- ') and cur is None):
        p = path_of(t)
        if p:
            if cur:
                blocks.append(cur)
            cur = {'key': p, 'buf': [ln]}
            continue
    if cur is None:
        preamble.append(ln)
    else:
        cur['buf'].append(ln)

if cur:
    blocks.append(cur)

kept, dropped = [], []
for b in blocks:
    hit = any(ex in b['key'] for ex in excludes)
    if hit:
        dropped.append(b['key'])
    else:
        kept.append(b)

out = list(preamble)
for b in kept:
    out.extend(b['buf'])

with open(outp, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))

print('剔除的文件段: %s' % (dropped if dropped else '(无)'))
print('保留文件数: %d' % len(kept))
for b in kept:
    print('   %s' % b['key'])
