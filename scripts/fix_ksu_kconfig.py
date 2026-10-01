#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 SUSFS 补丁引入的 KSU Kconfig 循环依赖

症状:
  drivers/kernelsu/Kconfig:80:error: recursive dependency detected!
    choice contains KSU_SUSFS
    KSU_SUSFS depends on KSU_MANUAL_HOOK
    KSU_MANUAL_HOOK is part of choice

修法: 在 config KSU_SUSFS 块内删掉 depends on / default 行
      （这些是 SUSFS 补丁误插进 choice 组的，删掉即断开循环）
"""
import os, sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
os.chdir(root)

CANDS = [
    'drivers/kernelsu/Kconfig',
    'KernelSU/Kconfig',
    'drivers/kernelsu/Kconfig.new',
]

path = None
for c in CANDS:
    if os.path.exists(c):
        path = c
        break

if path is None:
    print('未找到 KSU Kconfig，跳过')
    sys.exit(0)

with open(path, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.read().split('\n')

# 定位 config KSU_SUSFS 块
start = -1
for i, ln in enumerate(lines):
    if ln.strip().startswith('config ') and ln.strip().split()[1] == 'KSU_SUSFS':
        start = i
        break

if start < 0:
    print('未找到 config KSU_SUSFS，无需修复')
    sys.exit(0)

# 找块结束：下一个顶层关键字
end = len(lines)
for j in range(start + 1, len(lines)):
    s = lines[j].strip()
    if s.startswith(('config ', 'menuconfig ', 'choice', 'endchoice',
                     'menu ', 'endmenu', 'if ', 'endif', 'source ')):
        end = j
        break

removed = []
kept = []
for idx in range(start, end):
    s = lines[idx].strip()
    if s.startswith('depends on') or s.startswith('default'):
        removed.append(lines[idx])
        continue
    kept.append(lines[idx])

if not removed:
    print('config KSU_SUSFS 块内无 depends/default，无需修复')
    sys.exit(0)

new = lines[:start] + kept + lines[end:]
with open(path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new))

print('已修复 %s' % path)
print('删除的行:')
for r in removed:
    print('   %s' % r.strip())
