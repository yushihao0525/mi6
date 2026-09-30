#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ReSukiSU manual hook 自动注入（小米6 / 4.4 内核）
注入 fs/stat.c 的：
  - ksu_handle_newfstat_ret   (必加)
  - ksu_handle_fstat64_ret    (32-bit su 支持，ReSukiSU 会检查)
幂等：已存在则跳过
"""
import os, sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
os.chdir(root)

DECL = """#ifdef CONFIG_KSU_MANUAL_HOOK
extern void ksu_handle_newfstat_ret(unsigned int *fd, struct stat __user **statbuf_ptr);
#if defined(__ARCH_WANT_STAT64) || defined(__ARCH_WANT_COMPAT_STAT64)
extern void ksu_handle_fstat64_ret(unsigned long *fd, struct stat64 __user **statbuf_ptr);
#endif
#endif
"""

CALL_NEWFSTAT = """
#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_newfstat_ret(&fd, &statbuf);
#endif
"""

CALL_FSTAT64 = """
#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_fstat64_ret(&fd, &statbuf);
#endif
"""

def rd(p):
    with open(p, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()

def wr(p, s):
    with open(p, 'w', encoding='utf-8') as f:
        f.write(s)

def find_body(src, sig):
    """返回 (签名起点, 体起始{, 体结束}) """
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

def inject_before_return(src, sig, snippet, marker):
    """在函数体最后一个 return 之前插入 snippet"""
    if marker in src:
        print('  跳过(已存在): %s' % marker)
        return src, False
    r = find_body(src, sig)
    if not r:
        print('  !! 未找到函数: %s' % sig)
        return src, False
    i, j, k = r
    body = src[j + 1:k]
    pos = body.rfind('return error;')
    if pos < 0:
        pos = body.rfind('return ')
    if pos < 0:
        print('  !! 未找到 return: %s' % sig)
        return src, False
    newbody = body[:pos] + snippet + '\n\n' + body[pos:]
    src = src[:j + 1] + newbody + src[k:]
    print('  已注入: %s' % sig)
    return src, True

p = 'fs/stat.c'
if not os.path.exists(p):
    print('!! 未找到 fs/stat.c')
    sys.exit(0)

s = rd(p)
changed = False

# ① extern 声明（幂等）
if 'ksu_handle_newfstat_ret' not in s or 'ksu_handle_fstat64_ret' not in s:
    if 'ksu_handle_newfstat_ret' not in s:
        lines = s.split('\n')
        last_inc = -1
        for i, ln in enumerate(lines):
            if ln.startswith('#include'):
                last_inc = i
        if last_inc >= 0:
            lines.insert(last_inc + 1, DECL)
            s = '\n'.join(lines)
        else:
            s = DECL + '\n' + s
        print('  已插入 extern 声明')
        changed = True
    else:
        # newfstat 声明已有，只补 fstat64 声明
        print('  newfstat 声明已存在')

s, ok = inject_before_return(s, 'SYSCALL_DEFINE2(newfstat,',
                            CALL_NEWFSTAT, 'ksu_handle_newfstat_ret(&fd')
changed = changed or ok

s, ok = inject_before_return(s, 'SYSCALL_DEFINE2(fstat64,',
                            CALL_FSTAT64, 'ksu_handle_fstat64_ret(&fd')
changed = changed or ok

if changed:
    wr(p, s)
    print('完成: fs/stat.c 已写入')
else:
    print('完成: fs/stat.c 无需改动')
