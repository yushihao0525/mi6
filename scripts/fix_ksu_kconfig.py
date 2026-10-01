#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 SUSFS 补丁引入的 KSU Kconfig 循环依赖（加强版）

症状:
  choice <choice> contains symbol KSU_SUSFS
  symbol KSU_SUSFS depends on KSU_MANUAL_HOOK
  symbol KSU_MANUAL_HOOK is part of choice <choice>
  -> recursive dependency detected (error)

修法:
  1. 删除 KSU_SUSFS 块内 depends on KSU_MANUAL_HOOK 与 default 行
  2. 若 KSU_SUSFS 位于 choice...endchoice 之间，把整块移到 endchoice 之后
"""
import os, sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
os.chdir(root)

CANDS = ['drivers/kernelsu/Kconfig', 'KernelSU/Kconfig', 'drivers/kernelsu/Kconfig.new']

path = None
for c in CANDS:
    if os.path.exists(c):
        path = c
        break

if path is None:
    print('未找到 KSU Kconfig，跳过')
    sys.exit(0)


def read_lines(p):
    with open(p, 'r', encoding='utf-8', errors='replace') as f:
        return f.read().split('\n')


def write_lines(p, ls):
    with open(p, 'w', encoding='utf-8') as f:
        f.write('\n'.join(ls))


def find_block(lines, sym):
    start = -1
    for i, ln in enumerate(lines):
        parts = ln.strip().split()
        if len(parts) >= 2 and parts[0] == 'config' and parts[1] == sym:
            start = i
            break
    if start < 0:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        t = lines[j].strip()
        if t.startswith(('config ', 'menuconfig ', 'choice', 'endchoice',
                         'menu ', 'endmenu', 'if ', 'endif', 'source ', 'comment')):
            end = j
            break
    return (start, end)


def clean_block(block):
    out, removed = [], []
    for ln in block:
        t = ln.strip()
        if t.startswith('depends on') and 'KSU_MANUAL_HOOK' in t:
            removed.append(t)
            continue
        if t.startswith('default'):
            removed.append(t)
            continue
        out.append(ln)
    return out, removed


lines = read_lines(path)
b = find_block(lines, 'KSU_SUSFS')
if b is None:
    print('未找到 config KSU_SUSFS，无需修复')
    sys.exit(0)

start, end = b
cleaned, removed = clean_block(lines[start:end])

last_choice = -1
last_endchoice = -1
for i in range(start):
    t = lines[i].strip()
    if t.startswith('choice'):
        last_choice = i
    elif t.startswith('endchoice'):
        last_endchoice = i

in_choice = last_choice > last_endchoice
moved = False

if in_choice:
    print('检测到 KSU_SUSFS 位于 choice 组内，移出到 endchoice 之后')
    rest = lines[:start] + lines[end:]
    ec = -1
    for i, ln in enumerate(rest):
        if ln.strip().startswith('endchoice'):
            ec = i
    if ec >= 0:
        newlines = rest[:ec + 1] + [''] + cleaned + rest[ec + 1:]
        moved = True
    else:
        newlines = rest[:start] + cleaned + rest[start:]
        print('  警告: 未找到 endchoice，块放回原处')
else:
    newlines = lines[:start] + cleaned + lines[end:]

write_lines(path, newlines)

print('已处理 %s' % path)
if removed:
    print('删除的行:')
    for r in removed:
        print('   %s' % r)
else:
    print('   (块内无 depends on KSU_MANUAL_HOOK / default)')
print('KSU_SUSFS 移出 choice 组: %s' % ('是' if moved else '否(原本就在组外)'))

check = read_lines(path)
b2 = find_block(check, 'KSU_SUSFS')
print('===== 修复后 KSU_SUSFS 块 =====')
if b2:
    for ln in check[b2[0]:b2[1]]:
        print('  %s' % ln)
else:
    print('  (未找到)')

leftover = [ln.strip() for ln in check if 'depends on' in ln and 'KSU_MANUAL_HOOK' in ln]
if leftover:
    print('⚠ 仍残留 depends on KSU_MANUAL_HOOK:')
    for l in leftover:
        print('   %s' % l)
else:
    print('✅ 已无 depends on KSU_MANUAL_HOOK 残留')
