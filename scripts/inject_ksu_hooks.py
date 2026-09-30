#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ReSukiSU manual hook 自动注入（小米6 / 4.4 内核）
往 fs/stat.c 的 SYSCALL_DEFINE2(newfstat,...) 注入 ksu_handle_newfstat_ret
幂等：已存在则跳过
"""
import os, sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
os.chdir(root)

MARK = 'ksu_handle_newfstat_ret'
SIG  = 'SYSCALL_DEFINE2(newfstat,'

DECL = """#ifdef CONFIG_KSU_MANUAL_HOOK
extern void ksu_handle_newfstat_ret(unsigned int *fd, struct stat __user **statbuf_ptr);
#endif
"""

CALL = """
#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_newfstat_ret(&fd, &statbuf);
#endif
"""

p = 'fs/stat.c'
if not os.path.exists(p):
    print('!! 未找到 fs/stat.c')
    sys.exit(0)

with open(p, 'r', encoding='utf-8', errors='replace') as f:
    s = f.read()

if MARK in s:
    print('fs/stat.c 已含 %s，跳过' % MARK)
    sys.exit(0)

# ① extern 声明：插在最后一个 #include 之后
lines = s.split('\n')
last_inc = -1
for i, ln in enumerate(lines):
    if ln.startswith('#include'):
        last_inc = i
if last_inc >= 0:
    lines.insert(last_inc + 1, DECL)
    s = '\n'.join(lines)
    print('  已插入 extern 声明')
else:
    s = DECL + s
    print('  未找到 #include，声明置于文件头')

# ② 在 newfstat 函数体开头注入调用
i = s.find(SIG)
if i < 0:
    print('  !! 未找到 %s' % SIG)
else:
    j = s.find('{', i)
    if j < 0:
        print('  !! 未找到函数体起始括号')
    else:
        s = s[:j + 1] + '\n' + CALL + s[j + 1:]
        print('  已注入 ksu_handle_newfstat_ret 到 newfstat')

with open(p, 'w', encoding='utf-8') as f:
    f.write(s)

print('完成: fs/stat.c')
