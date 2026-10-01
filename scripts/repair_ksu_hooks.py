#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保守修复 fs/exec.c 与 fs/open.c 的 KSU hook

原则:
  ★ 文件中只要出现 hook 函数名（哪怕只是 extern 声明）就一律跳过
  ★ 只有完全找不到函数名时才注入，且用行级精确定位

覆盖:
  fs/exec.c : ksu_handle_execveat  (do_execveat_common)
  fs/open.c : ksu_handle_faccessat (SYSCALL_DEFINE3(faccessat,...))
"""
import os, sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
os.chdir(root)

DECL_PREFIX = ('int ', 'unsigned ', 'long ', 'char ', 'struct ', 'void ',
               'const ', 'bool ', 'size_t ', 'ssize_t ', 'loff_t ', 'u32 ')


def rd(p):
    with open(p, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def wr(p, s):
    with open(p, 'w', encoding='utf-8') as f:
        f.write(s)


def find_def_line(lines, needle):
    for i, ln in enumerate(lines):
        if needle in ln:
            return i
    return -1


def find_body_brace(lines, start):
    for i in range(start, len(lines)):
        if '{' in lines[i]:
            return i
    return -1


def find_body_end(lines, brace_line):
    depth = 0
    for i in range(brace_line, len(lines)):
        for ch in lines[i]:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return i
    return len(lines) - 1


def insert_call(lines, brace_line, end_line, call):
    pos = None
    for i in range(brace_line + 1, end_line):
        t = lines[i].strip()
        if not t or t.startswith('/*') or t.startswith('*') or t.startswith('//'):
            continue
        if t.startswith(DECL_PREFIX) and t.endswith(';'):
            continue
        pos = i
        break
    if pos is None:
        pos = brace_line + 1
    lines.insert(pos, call)
    return lines


TASKS = [
    {
        'file': 'fs/exec.c',
        'symbol': 'ksu_handle_execveat',
        'needle': 'do_execveat_common',
        'decl': """#ifdef CONFIG_KSU_MANUAL_HOOK
extern int ksu_handle_execveat(int *fd, struct filename **filename_ptr,
\t\tvoid *argv, void *envp, int *flags);
#endif
""",
        'call': """#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);
#endif
""",
    },
    {
        'file': 'fs/open.c',
        'symbol': 'ksu_handle_faccessat',
        'needle': 'SYSCALL_DEFINE3(faccessat',
        'decl': """#ifdef CONFIG_KSU_MANUAL_HOOK
extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user,
\t\t\t\tint *mode, int *flags);
#endif
""",
        'call': """#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_faccessat(&dfd, &filename, &mode, NULL);
#endif
""",
    },
]

for t in TASKS:
    p = t['file']
    print('===== %s : %s =====' % (p, t['symbol']))
    if not os.path.exists(p):
        print('  未找到文件，跳过')
        continue

    s = rd(p)
    if t['symbol'] in s:
        print('  已存在 %s，不改动' % t['symbol'])
        continue

    lines = s.split('\n')
    idx = find_def_line(lines, t['needle'])
    if idx < 0:
        print('  未找到 %s，跳过' % t['needle'])
        continue

    lines.insert(idx, t['decl'])
    idx2 = find_def_line(lines, t['needle'])
    bl = find_body_brace(lines, idx2)
    if bl < 0:
        print('  未找到函数体，跳过')
        continue
    el = find_body_end(lines, bl)
    lines = insert_call(lines, bl, el, t['call'])
    wr(p, '\n'.join(lines))
    print('  已注入 %s -> %s' % (t['symbol'], p))

print('===== 修复结束 =====')
