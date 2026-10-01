#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复/注入 fs/open.c 的 ksu_handle_faccessat hook（4.19- 内核写法）

背景: SUSFS 的 KSU 侧补丁会改写 fs/open.c，可能破坏原有 hook，导致:
  You lost ksu_handle_faccessat hook

按官方 manual-integrate 文档（4.19- 分支）:
  extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user,
                                  int *mode, int *flags);
  在 SYSCALL_DEFINE3(faccessat, ...) 体内插入:
    ksu_handle_faccessat(&dfd, &filename, &mode, NULL);

幂等: 已存在则跳过
"""
import os, sys, re

root = sys.argv[1] if len(sys.argv) > 1 else '.'
os.chdir(root)

DECL_PREFIX = ('int ', 'unsigned ', 'long ', 'char ', 'struct ', 'void ',
               'const ', 'bool ', 'size_t ', 'ssize_t ', 'loff_t ', 'u32 ')

DECL = """#ifdef CONFIG_KSU_MANUAL_HOOK
extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user,
\t\t\t\tint *mode, int *flags);
#endif
"""

CALL = """
#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_faccessat(&dfd, &filename, &mode, NULL);
#endif
"""

p = 'fs/open.c'
if not os.path.exists(p):
    print('未找到 fs/open.c')
    sys.exit(0)

with open(p, 'r', encoding='utf-8', errors='replace') as f:
    s = f.read()

if 'ksu_handle_faccessat(&dfd' in s:
    print('faccessat hook 已存在，跳过')
    sys.exit(0)


def find_body(src, sig):
    i = src.find(sig)
    if i < 0:
        return None
    j = src.find('{', i)
    if j < 0:
        return None
    depth, k = 0, j
    n = len(src)
    while k < n:
        c = src[k]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return (i, j, k)
        k += 1
    return None


def add_decl(src):
    if 'ksu_handle_faccessat' in src:
        return src
    lines = src.split('\n')
    last_inc = -1
    for i, ln in enumerate(lines):
        if ln.startswith('#include'):
            last_inc = i
    if last_inc >= 0:
        lines.insert(last_inc + 1, DECL)
        return '\n'.join(lines)
    return DECL + '\n' + src


s = add_decl(s)

# 4.19- 内核用 SYSCALL_DEFINE3(faccessat,...)
SIGS = ['SYSCALL_DEFINE3(faccessat,', 'SYSCALL_DEFINE3(faccessat ,']
sig = None
for c in SIGS:
    if c in s:
        sig = c
        break

if sig is None:
    # 退化尝试：do_faccessat
    sig = 'long do_faccessat('
    if sig not in s:
        print('!! fs/open.c 未找到 faccessat，跳过')
        sys.exit(0)

r = find_body(s, sig)
if not r:
    print('!! 未定位到函数体: %s' % sig)
    sys.exit(0)

i, j, k = r
body = s[j + 1:k]
lines = body.split('\n')
pos = len(lines)
for n, ln in enumerate(lines):
    t = ln.strip()
    if not t or t.startswith('/*') or t.startswith('*') or t.startswith('//'):
        continue
    if t.startswith(DECL_PREFIX) and t.endswith(';'):
        continue
    pos = n
    break

newbody = '\n'.join(lines[:pos]) + '\n' + CALL + '\n' + '\n'.join(lines[pos:])
s = s[:j + 1] + newbody + s[k:]

with open(p, 'w', encoding='utf-8') as f:
    f.write(s)

print('已注入 ksu_handle_faccessat -> %s' % p)
print('===== 结果预览 =====')
m = s.find(sig)
print(s[m:m + 700])
