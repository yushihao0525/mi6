#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ReSukiSU manual hook 全量注入（小米6 sagit / Linux 4.4）

按官方 manual-integrate 文档一次性注入全部 hook：
  fs/stat.c        -> ksu_handle_stat        (newfstatat / fstatat64)
  fs/stat.c        -> ksu_handle_newfstat_ret
  fs/stat.c        -> ksu_handle_fstat64_ret
  kernel/reboot.c  -> ksu_handle_sys_reboot
  fs/read_write.c  -> ksu_handle_vfs_read    (默认关闭)
  fs/devpts/inode.c-> ksu_handle_devpts      (默认关闭)

原则：幂等 / 每个 hook 独立容错 / 全包 #ifdef CONFIG_KSU_MANUAL_HOOK / C89 安全
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


def ensure_decl(src, decl, guards):
    """guards 全部命中才跳过；任一缺失就插入整块声明"""
    if all(g in src for g in guards):
        return src, False, '声明已存在'
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
    return src, True, '已插入声明'


def insert_after_declarations(src, sig, snippet, marker):
    if marker in src:
        return src, False, '已存在'
    r = find_body(src, sig)
    if not r:
        return src, False, '未找到函数'
    i, j, k = r
    body = src[j + 1:k]
    lines = body.split('\n')
    pos = len(lines)
    for n, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith('/*') or s.startswith('*') or s.startswith('//'):
            continue
        if s.startswith(DECL_PREFIX) and s.endswith(';'):
            continue
        pos = n
        break
    newbody = '\n'.join(lines[:pos]) + '\n' + snippet + '\n' + '\n'.join(lines[pos:])
    src = src[:j + 1] + newbody + src[k:]
    return src, True, '已注入'


def insert_before_last_return(src, sig, snippet, marker):
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


def work(name, candidates, sig_list, decl, decl_guards,
         snippets, markers, mode='decl'):
    if not ENABLE.get(name, False):
        print('[%s] 已禁用，跳过' % name)
        return
    path = None
    for c in candidates:
        if os.path.exists(c):
            path = c
            break
    if path is None:
        print('[%s] 未找到文件 %s，跳过' % (name, candidates))
        return

    print('[%s] 处理 %s' % (name, path))
    s = rd(path)
    changed = False

    if decl:
        s, ok, msg = ensure_decl(s, decl, decl_guards)
        print('   %-46s -> %s' % ('extern 声明', msg))
        changed = changed or ok

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


# ══════════ fs/stat.c : newfstatat / fstatat64 ══════════
work('stat_hook', ['fs/stat.c'],
     ['SYSCALL_DEFINE4(newfstatat,', 'SYSCALL_DEFINE4(fstatat64,'],
     """#ifdef CONFIG_KSU_MANUAL_HOOK
extern int ksu_handle_stat(int *dfd, const char __user **filename_user,
\t\t\t\tint *flags);
#endif
""",
     ['extern int ksu_handle_stat'],
     ["""#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_stat(&dfd, &filename, &flag);
#endif
""",
      """#ifdef CONFIG_KSU_MANUAL_HOOK // 32-bit
\tksu_handle_stat(&dfd, &filename, &flag);
#endif
"""],
     ['ksu_handle_stat(&dfd', 'ksu_handle_stat(&dfd'],
     mode='decl')

# ══════════ fs/stat.c : newfstat / fstat64 ══════════
work('newfstat_ret', ['fs/stat.c'],
     ['SYSCALL_DEFINE2(newfstat,'],
     """#ifdef CONFIG_KSU_MANUAL_HOOK
extern void ksu_handle_newfstat_ret(unsigned int *fd, struct stat __user **statbuf_ptr);
#if defined(__ARCH_WANT_STAT64) || defined(__ARCH_WANT_COMPAT_STAT64)
extern void ksu_handle_fstat64_ret(unsigned long *fd, struct stat64 __user **statbuf_ptr);
#endif
#endif
""",
     ['extern void ksu_handle_newfstat_ret', 'extern void ksu_handle_fstat64_ret'],
     ["""#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_newfstat_ret(&fd, &statbuf);
#endif
"""],
     ['ksu_handle_newfstat_ret(&fd'],
     mode='return')

work('fstat64_ret', ['fs/stat.c'],
     ['SYSCALL_DEFINE2(fstat64,'],
     None, ['extern void ksu_handle_fstat64_ret'],
     ["""#ifdef CONFIG_KSU_MANUAL_HOOK // for 32-bit
\tksu_handle_fstat64_ret(&fd, &statbuf);
#endif
"""],
     ['ksu_handle_fstat64_ret(&fd'],
     mode='return')

# ══════════ reboot hook ══════════
work('sys_reboot', ['kernel/reboot.c', 'kernel/sys.c'],
     ['SYSCALL_DEFINE4(reboot,'],
     """#ifdef CONFIG_KSU_MANUAL_HOOK
extern int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd, void __user **arg);
#endif
""",
     ['extern int ksu_handle_sys_reboot'],
     ["""#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_sys_reboot(magic1, magic2, cmd, &arg);
#endif
"""],
     ['ksu_handle_sys_reboot(magic1'],
     mode='decl')

# ══════════ 可选 ══════════
work('vfs_read', ['fs/read_write.c'], ['ssize_t vfs_read('],
     """#ifdef CONFIG_KSU_MANUAL_HOOK
extern bool ksu_vfs_read_hook __read_mostly;
extern int ksu_handle_vfs_read(struct file **file_ptr, char __user **buf_ptr,
\tsize_t *count_ptr, loff_t **pos);
#endif
""",
     ['extern int ksu_handle_vfs_read'],
     ["""#ifdef CONFIG_KSU_MANUAL_HOOK
\tif (unlikely(ksu_vfs_read_hook))
\t\tksu_handle_vfs_read(&file, &buf, &count, &pos);
#endif
"""],
     ['ksu_handle_vfs_read(&file'],
     mode='decl')

work('devpts', ['fs/devpts/inode.c'], ['static void *devpts_get_priv('],
     """#ifdef CONFIG_KSU_MANUAL_HOOK
extern void ksu_handle_devpts(struct inode *inode);
#endif
""",
     ['extern void ksu_handle_devpts'],
     ["""#ifdef CONFIG_KSU_MANUAL_HOOK
\tksu_handle_devpts(dentry->d_inode);
#endif
"""],
     ['ksu_handle_devpts('],
     mode='decl')

print('===== 注入结束 =====')
