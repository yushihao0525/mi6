#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 fs/exec.c 的 ksu_handle_execveat / ksu_handle_post_execveat hook

背景:
  SUSFS 的 KSU 侧补丁(如 10_enable_susfs_for_ksu.patch)会改写 fs/exec.c，
  可能破坏原有的 execveat hook，导致 ReSukiSU 报:
    You lost ksu_handle_execveat hook

修法(按官方 manual-integrate 文档 3.14+ 写法):
  在 do_execveat_common 中重建:
    int retval;
    ksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);
    retval = __do_execve_file(fd, filename, argv, envp, flags, NULL);
    ksu_handle_post_execveat(&fd, &filename, &argv, &envp, &flags, &retval);
    return retval;

幂等: 已含 ksu_handle_execveat 调用则跳过
"""
import os, sys, re

root = sys.argv[1] if len(sys.argv) > 1 else '.'
os.chdir(root)

p = 'fs/exec.c'
if not os.path.exists(p):
    print('未找到 fs/exec.c')
    sys.exit(0)

with open(p, 'r', encoding='utf-8', errors='replace') as f:
    s = f.read()

if 'ksu_handle_execveat(&fd' in s and 'ksu_handle_post_execveat' in s:
    print('execveat hook 已存在，跳过')
    sys.exit(0)

DECL = """#ifdef CONFIG_KSU_MANUAL_HOOK
__attribute__((hot))
extern int ksu_handle_execveat(int *fd, struct filename **filename_ptr,
\t\tvoid *argv, void *envp, int *flags);
__attribute__((hot))
extern int ksu_handle_post_execveat(int *fd, struct filename **filename_ptr,
\t\tvoid *argv, void *envp, int *flags, int *retval);
#endif
"""

# 定位 do_execveat_common
sig = 'do_execveat_common'
i = s.find(sig)
if i < 0:
    print('未找到 do_execveat_common，尝试 do_execve / compat_do_execve')
    for alt in ('do_execve_common', 'do_execve'):
        i = s.find(alt)
        if i >= 0:
            sig = alt
            break

if i < 0:
    print('!! fs/exec.c 中未找到任何 execve 函数，跳过')
    sys.exit(0)

# 找函数体
j = s.find('{', i)
if j < 0:
    print('!! 未找到函数体')
    sys.exit(0)

depth, k = 0, j
n = len(s)
while k < n:
    c = s[k]
    if c == '{':
        depth += 1
    elif c == '}':
        depth -= 1
        if depth == 0:
            break
    k += 1

body = s[j + 1:k]

# 已有 ksu 相关代码则整体替换掉旧的 ksu 块
body = re.sub(
    r'#ifdef CONFIG_KSU_MANUAL_HOOK.*?#endif\s*',
    '', body, flags=re.S)

NEW_BODY = """
#ifdef CONFIG_KSU_MANUAL_HOOK
\tint retval;
\tksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);

\tretval = __do_execve_file(fd, filename, argv, envp, flags, NULL);

\tksu_handle_post_execveat(&fd, &filename, &argv, &envp, &flags, &retval);

\treturn retval;
#else
%s
#endif
""" % body.strip('\n')

# 声明插到 do_execveat_common 之前
if 'ksu_handle_execveat' not in s:
    s = s[:i] + DECL + '\n' + s[i:]
    # 重新定位（插入后偏移）
    i = s.find(sig)
    j = s.find('{', i)
    depth, k = 0, j
    while k < len(s):
        c = s[k]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                break
        k += 1
    body = s[j + 1:k]
    NEW_BODY = """
#ifdef CONFIG_KSU_MANUAL_HOOK
\tint retval;
\tksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);

\tretval = __do_execve_file(fd, filename, argv, envp, flags, NULL);

\tksu_handle_post_execveat(&fd, &filename, &argv, &envp, &flags, &retval);

\treturn retval;
#else
%s
#endif
""" % body.strip('\n')

s = s[:j + 1] + NEW_BODY + s[k:]

with open(p, 'w', encoding='utf-8') as f:
    f.write(s)

print('已重建 execveat hook (%s): %s' % (sig, p))
print('===== 结果预览 =====')
m = s.find(sig)
print(s[m:m + 900])
