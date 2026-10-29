"""一条命令出两个包：便携包（单文件 exe）+ 安装包（Inno Setup 安装程序）。

    py scripts/build.py            # 两个都打
    py scripts/build.py --portable # 只打便携包（快，约 1 分钟）
    py scripts/build.py --setup    # 只打安装包（需要先有便携包？不必，目录版独立构建）

为什么要脚本而不让人手敲两条命令：
    1. 两个包必须来自**同一份** Analysis 配置，否则哪天有人只改了 ImageAngle.spec，
       安装包体积就悄悄回到 100 MB；
    2. 产物名要带版本号（ImageAngle-1.0.4-便携包.exe / -安装包.exe），版本号只从
       app/__init__.py 取，避免手抄错；
    3. 打完自动报体积并与上次对比，涨了会醒目提示 —— 这是"加功能会不会把包撑大"
       唯一可靠的回答方式。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, 'dist')
BUILD = os.path.join(ROOT, 'build')
SIZE_CACHE = os.path.join(BUILD, 'last_sizes.json')

#: 体积警戒线（MB）。便携包超过它，说明有东西被重新打进来了
WARN_MB = 45.0


def version() -> str:
    """从 app/__init__.py 读版本，不执行包导入（避免拉起 Qt）。"""
    src = open(os.path.join(ROOT, 'app', '__init__.py'), encoding='utf-8').read()
    m = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", src, re.M)
    if not m:
        raise SystemExit('读不到 app/__init__.py 里的 __version__')
    return m.group(1)


def kb(path: str) -> float:
    return os.path.getsize(path) / 1048576


def tree_mb(path: str) -> float:
    total = 0
    for base, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    return total / 1048576


def run(cmd: list[str], *, quiet_tail: int = 6) -> None:
    print('  $ ' + ' '.join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    out = (proc.stdout or '') + (proc.stderr or '')
    if proc.returncode != 0:
        print(out[-4000:])
        raise SystemExit(f'命令失败（exit {proc.returncode}）')
    tail = [ln for ln in out.splitlines() if ln.strip()][-quiet_tail:]
    for ln in tail:
        print('    ' + ln)


def kill_running() -> None:
    """dist 里的 exe 被占用时 PyInstaller 清不掉，提前结束掉。"""
    names = {'ImageAngle.exe'}
    names.update(os.path.basename(p) for p in glob.glob(os.path.join(DIST, '*.exe')))
    for name in names:
        subprocess.run(['taskkill', '/F', '/IM', name], capture_output=True)


def build_portable(ver: str) -> tuple[str, float]:
    print('\n[1/3] 便携包（单文件 exe）')
    run([sys.executable, '-m', 'PyInstaller', 'ImageAngle.spec', '--noconfirm',
         '--distpath', DIST, '--workpath', BUILD])
    path = os.path.join(DIST, f'ImageAngle-{ver}-便携包.exe')
    if not os.path.exists(path):
        raise SystemExit(f'没找到产物：{path}')
    return path, kb(path)


def build_onedir(ver: str) -> tuple[str, float]:
    """目录版只是安装包的原料，放进 build/stage —— dist 里只留两个交付文件。"""
    print('\n[2/3] 目录版（安装包的原料）')
    stage_root = os.path.join(BUILD, 'stage')
    run([sys.executable, '-m', 'PyInstaller', os.path.join('packaging', 'onedir.spec'),
         '--noconfirm', '--distpath', stage_root, '--workpath', BUILD])
    path = os.path.join(stage_root, f'ImageAngle-{ver}')
    if not os.path.isdir(path):
        raise SystemExit(f'没找到产物目录：{path}')
    return path, tree_mb(path)


def find_iscc() -> str:
    """找 Inno Setup 编译器：环境变量 → 默认安装位置 → PATH。"""
    env = os.environ.get('INNO_SETUP_ISCC')
    if env and os.path.exists(env):
        return env
    local = os.environ.get('LOCALAPPDATA', '')
    cands = [
        os.path.join(local, 'Programs', 'Inno Setup 6', 'ISCC.exe'),
        r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        r'C:\Program Files\Inno Setup 6\ISCC.exe',
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    found = shutil.which('ISCC')
    if found:
        return found
    raise SystemExit(
        '找不到 ISCC.exe（Inno Setup 6 编译器）。\n'
        '装法（免管理员）：下载 innosetup-6.x.x.exe 后运行\n'
        '  innosetup.exe /VERYSILENT /CURRENTUSER /SUPPRESSMSGBOXES /NORESTART /SP-\n'
        '或用环境变量 INNO_SETUP_ISCC 指定路径。')


def build_setup(ver: str, stage: str) -> tuple[str, float]:
    print('\n[3/3] 安装包（Inno Setup）')
    iscc = find_iscc()
    run([iscc,
         f'/DAppVer={ver}',
         f'/DStageDir={stage}',
         f'/O{DIST}',
         os.path.join('installer', 'ImageAngle.iss')])
    path = os.path.join(DIST, f'ImageAngle-{ver}-安装包.exe')
    if not os.path.exists(path):
        raise SystemExit(f'没找到产物：{path}')
    return path, kb(path)


def report(rows: list[tuple[str, float]]) -> None:
    prev = {}
    if os.path.exists(SIZE_CACHE):
        try:
            prev = json.load(open(SIZE_CACHE, encoding='utf-8'))
        except (OSError, ValueError):
            prev = {}

    print('\n' + '=' * 62)
    print(f'{"产物":<34}{"体积":>10}{"对比上次":>14}')
    print('-' * 62)
    warn = False
    for name, size in rows:
        key = os.path.basename(name)
        delta = ''
        if key in prev:
            d = size - float(prev[key])
            if abs(d) >= 0.05:
                delta = f'{d:+.2f} MB'
        line = f'{key:<34}{size:>8.2f} MB{delta:>14}'
        if size > WARN_MB and name.endswith('.exe') and '便携包' in name:
            line += '   ← 偏大'
            warn = True
        print(line)
    print('=' * 62)

    json.dump({os.path.basename(n): round(s, 3) for n, s in rows},
              open(SIZE_CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    if warn:
        print(f'⚠ 便携包超过 {WARN_MB:.0f} MB。常见原因：新增第三方库、'
              f'用到了被 packaging/qt_prune.py 裁掉的 Qt 模块、或打包时没走 spec。')


def main() -> int:
    ap = argparse.ArgumentParser(description='打包 ImageAngle（便携包 + 安装包）')
    ap.add_argument('--portable', action='store_true', help='只打便携包')
    ap.add_argument('--setup', action='store_true', help='只打安装包')
    args = ap.parse_args()
    if args.portable and args.setup:
        args.portable = args.setup = False        # 两个都指定 = 两个都打

    ver = version()
    print(f'ImageAngle {ver}  →  {DIST}')
    os.makedirs(DIST, exist_ok=True)
    os.makedirs(BUILD, exist_ok=True)
    kill_running()

    t0 = time.time()
    rows: list[tuple[str, float]] = []
    stage = ''
    if not args.setup:
        p, s = build_portable(ver)
        rows.append((p, s))
    if not args.portable:
        stage, s = build_onedir(ver)
        p2, s2 = build_setup(ver, stage)
        rows.append((p2, s2))

    report(rows)
    print(f'完成，用时 {time.time() - t0:.0f} 秒。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
