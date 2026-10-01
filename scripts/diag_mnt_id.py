#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断 mnt_id 重复定义的来源（只打印，不修改任何文件）"""
import os, sys, re
from collections import Counter

root = sys.argv[1] if len(sys.argv) > 1 else '.'
os.chdir(root)

print("===== 在源码中查找 mnt_id 定义 =====")
hits = []
for dirpath, dirnames, filenames in os.walk('.'):
    dirnames[:] = [d for d in dirnames if d not in ('.git', 'out', '.cache')]
    for fn in filenames:
        if not (fn.endswith('.h') or fn.endswith('.c')):
            continue
        p = os.path.join(dirpath, fn)
        try:
            with open(p, 'r', encoding='utf-8', errors='replace') as f:
                for i, line in enumerate(f, 1):
                    if 'mnt_id' not in line:
                        continue
                    s = line.strip()
                    if s.startswith('//') or s.startswith('/*') or s.startswith('*'):
                        continue
                    if 'extern' in s or 'static' in s:
                        continue
                    if re.search(r'\b(int|unsigned\s+int|u32|bool|long)\s+mnt_id\b', s):
                        hits.append((p, i, s))
        except Exception:
            pass

if not hits:
    print("未找到无 extern 的 mnt_id 定义")
else:
    print("找到 %d 处:" % len(hits))
    c = Counter(p for p, _, _ in hits)
    for p, n in c.most_common(20):
        print("   %-50s %d 处" % (p, n))
    print("\n前 10 处详情:")
    for p, i, s in hits[:10]:
        print("   %s:%d  %s" % (p, i, s))

print("\n===== 汇总 =====")
