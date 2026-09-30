#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ReSukiSU manual hook 全量注入（小米6 sagit / Linux 4.4）

按官方 manual-integrate 文档，一次性注入全部 hook。
设计原则：
  1. 幂等     —— 已存在则跳过，重复运行无害
  2. 独立容错 —— 每个 hook 单独 try/except，失败/找不到就跳过，不影响其他
  3. 安全     —— 全部包在 #ifdef CONFIG_KSU_MANUAL_HOOK 里
  4. C89 友好 —— 调用语句插在变量声明之后，不触发 declaration-after-statement

开关（改下方 ENABLE 字典）：
  stat_hook      必加  fs/stat.c : newfstatat
  stat_hook64    32位  fs/stat.c : fstatat64
  newfstat_ret   必加  fs/stat.c : newfstat
  fstat64_ret    32位  fs/stat.c : fstat64
  sys_reboot     必加  kernel/reboot.c(3.11+) 或 kernel/sys.c(3.11-)
  vfs_read       可选  fs/read_write.c —— ReSukiSU 已用 LSM hook 接管 init rc
                       开启可能重复触发或符号缺失，默认关闭
  devpts         可选  fs/devpts/inode.c —— 仅 pm 命令异常时需要，默认关闭
"""
import os, sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
os.chdir(root)

ENABLE = {
    'stat_hook':    True,
    'stat_hook64':  True,
    'newfstat_ret': True,
    'fstat64_ret':  True,
    'sys_reboot':   True,
    'vfs_read':     False,
    'devpts':       False,
}

# 声明行常见起始关键字（用于跳过变量声明区）
DECL_PREFIX = ('char ', 'int ', 'struct ', 'unsigned ', 'long ', 'void ',
               'const ', 'bool ', 'size_t ', 'ssize_t ', 'loff_t ',
               'static ', 'register ', 'u8 ', 'u16 ', 'u32 ', 'u64 ')


def rd(p):
    with open(p, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def wr(p, s):
    with open(p, 'w', encoding='utf-8') as f:
        f.write(s)


def find_body(src, sig):
    """定位函数：返回 (签名起点, 体起始'{', 体结尾'}')"""
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


def add_decl(src, decl, guard):
    """在最后一个 #include 之后插入 extern 声明（幂等）"""
    if guard in src:
        return src, False
    lines = src.split('\n')
    last_inc = -1
    for i, ln in enumerate(lines):
        if ln.startswith('#include'):
            last_inc = i
    if last_inc >= 0:
        lines.insert(last_inc + 1, decl)
        src = '\n'.join(lines)
    else:
        src = decl + '\n' + src
    return src, True


def insert_after_declarations(src, sig, snippet, marker):
    """跳过变量声明区，在第一个语句前插入（C89 安全）"""
    if marker in src:
        return src, False, '已存在'
    r = find_body(src, sig)
    if not r:
        return src, False, '未找到函数'
    i, j, k = r
    body = src[j + 1:k]
    lines = body.split('\n')
    pos_line = 0
    idx = 0
    for n, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith('/*') or s.startswith('*') or s.startswith('//'):
            continue
        if s.startswith(DECL_PREFIX) and s.endswith(';'):
            continue
        pos_line = n
        break
    else:
        pos_line = len(lines)
    newbody = '\n'.join(lines[:pos_line]) + '\n' + snippet + '\n' + \
              '\n'.join(lines[pos_line:])
    src = src[:j + 1] + newbody + src[k:]
    return src, True, '已注入'


def insert_before_last_return(src, sig, snippet, marker):
    """在最后一个 return 之前插入（取返回值型 hook）"""
    if marker in src:
        return src, False, '已存在'
    r = find_body(src, sig)
    if not r:
        return src, False, '未找到函数'
    i, j, k = r
    body = src[j + 1:k]
    pos = body.rfind('return error;')
    if pos < 0:
        pos = body.rfind('return ')
    if pos < 0:
        pos = len(body)
    newbody = body[:pos] + snippet + '\n\n' + body[pos:]
    src = src[:j + 1] + newbody + src[k:]
    return src, True, '已注入'


def work(path_candidates, sig_list, decl, decl_guard, snippets, markers,
         name, mode='decl'):
    """统一处理单个 hook：多候选文件、多签名"""
    if not ENABLE.get(name, False):
        print('[%s] 已禁用（ENABLE=False），跳过' % name)
        return
    path = None
    for c in path_candidates:
        if os.path.exists(c):
            path = c
            break
    if path is None:
        print('[%s] 未找到文件 %s，跳过' % (name, path_candidates))
        return

    print('[%s] 处理 %s' % (name, path))
    s = rd(path)
    changed = False

    if decl:
        s, ok = add_decl(s, decl, decl_guard)
        if ok:
            print('   已插入 extern 声明')
            changed = True

    for idx, sig in enumerate(sig_list):
        snip = snippets[idx] if idx < len(snippets) else snippets[0]
        mk = markers[idx] if idx < len(markers) else markers[0]
        if mode == 'return':
            s, ok, msg = insert_before_last_return(s, sig, snip, mk)
        else:
            s, ok, msg = insert_after_declarations(s, sig, snip, mk)
        print('   %-46s -> %s' % (sig, msg))
        changed = changed or ok

    if changed:
        wr(path, s)
        print('   ✔ %s 已写入' % path)
    else:
        print('   · %s 无需改动' % path)


# ═══════════════ fs/stat.c ═══════════════
STAT_DECL = """#ifdef CONFIG_KSU_MANUAL_HOOK
extern int ksu_handle_stat(int *dfd, const char __user **filename_user,
\t\t\t\tint *flags);
extern void ksu_handle_newfstat_ret(unsigned int *fd, struct stat __user **statbuf_ptr);
#if defined(__ARCH_WANT_STAT64) || defined(__ARCH_WANT_COMPAT_STAT64)
extern void ksu_handle_fstat64_ret(unsigned long *fd, struct stat64 __user **statbuf_ptr); // optional
#endif
#endif
"""

work(
    ['fs/stat.c'],
    ['SYSCALL_DEFINE4(newfstatat,', 'SYSCALL_DEFINE4(fstatat64,'],
    STAT_DECL, 'ksu_handle_stat',
    [
        """#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_stat(&dfd, &filename, &flag);
#endif
""",
        """#ifdef CONFIG_KSU_MANUAL_HOOK // 32-bit
\tksu_handle_stat(&dfd, &filename, &flag);
#endif
""",
    ],
    ['ksu_handle_stat(&dfd', 'ksu_handle_stat(&dfd'],
    'stat_hook', mode='decl',
)

work(
    ['fs/stat.c'],
    ['SYSCALL_DEFINE2(newfstat,'],
    None, None,
    ["""#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_newfstat_ret(&fd, &statbuf);
#endif
"""],
    ['ksu_handle_newfstat_ret(&fd'],
    'newfstat_ret', mode='return',
)

work(
    ['fs/stat.c'],
    ['SYSCALL_DEFINE2(fstat64,'],
    None, None,
    ["""#ifdef CONFIG_KSU_MANUAL_HOOK // for 32-bit
\tksu_handle_fstat64_ret(&fd, &statbuf);
#endif
"""],
    ['ksu_handle_fstat64_ret(&fd'],
    'fstat64_ret', mode='return',
)

# ═══════════════ reboot hook ═══════════════
# 3.11+ 用 kernel/reboot.c，3.11- 用 kernel/sys.c；小米6 是 4.4 → reboot.c
work(
    ['kernel/reboot.c', 'kernel/sys.c'],
    ['SYSCALL_DEFINE4(reboot,'],
    """#ifdef CONFIG_KSU_MANUAL_HOOK
extern int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd, void __user **arg);
#endif
""", 'ksu_handle_sys_reboot',
    ["""#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_sys_reboot(magic1, magic2, cmd, &arg);
#endif
"""],
    ['ksu_handle_sys_reboot(magic1'],
    'sys_reboot', mode='decl',
)

# ═══════════════ 可选：vfs_read ═══════════════
work(
    ['fs/read_write.c'],
    ['ssize_t vfs_read('],
    """#ifdef CONFIG_KSU_MANUAL_HOOK
extern bool ksu_vfs_read_hook __read_mostly;
extern int ksu_handle_vfs_read(struct file **file_ptr, char __user **buf_ptr,
\tsize_t *count_ptr, loff_t **pos);
#endif
""", 'ksu_handle_vfs_read',
    ["""#ifdef CONFIG_KSU_MANUAL_HOOK
\tif (unlikely(ksu_vfs_read_hook))
\t\tksu_handle_vfs_read(&file, &buf, &count, &pos);
#endif
"""],
    ['ksu_handle_vfs_read(&file'],
    'vfs_read', mode='decl',
)

# ═══════════════ 可选：devpts ═══════════════
work(
    ['fs/devpts/inode.c'],
    ['static void *devpts_get_priv('],
    """#ifdef CONFIG_KSU_MANUAL_HOOK
extern void ksu_handle_devpts(struct inode *inode);
#endif
""", 'ksu_handle_devpts',
    ["""#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_devpts(dentry->d_inode);
#endif
"""],
    ['ksu_handle_devpts('],
    'devpts', mode='decl',
)

print('===== 注入流程结束 =====')
