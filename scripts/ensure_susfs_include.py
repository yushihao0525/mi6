#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确保使用 susfs 符号的 .c 文件都 #include <linux/susfs.h>

SUSFS 补丁的 include hunk 常因上下文变化而匹配失败，导致:
  implicit declaration of function 'susfs_xxx'
  use of undeclared identifier 'INODE_STATE_SUS_KSTAT'
本脚本扫描所有用到 susfs 的 .c 文件并补齐 include（幂等）。
"""
import os, sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
os.chdir(root)

INC = '#include <linux/susfs.h>'

if not os.path.exists('include/linux/susfs.h'):
    print('⚠ 未找到 include/linux/susfs.h，跳过')
    sys.exit(0)

targets = []
for dirpath, dirnames, filenames in os.walk('.'):
    dirnames[:] = [d for d in dirnames if d not in ('.git', 'out', '.cache')]
    for fn in filenames:
        if not fn.endswith('.c'):
            continue
        p = os.path.join(dirpath, fn)
        if os.path.basename(p) == 'susfs.c':
            continue
        try:
            with open(p, 'r', encoding='utf-8', errors='replace') as f:
                s = f.read()
        except Exception:
            continue
        if 'susfs' not in s:
            continue
        if INC in s:
            continue
        targets.append(p)

for p in targets:
    with open(p, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().split('\n')
    last = -1
    for i, ln in enumerate(lines):
        if ln.startswith('#include'):
            last = i
    if last >= 0:
        lines.insert(last + 1, INC)
    else:
        lines.insert(0, INC)
    with open(p, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('  已补充 include: %s' % p)

print('补充 include 文件数: %d' % len(targets))
