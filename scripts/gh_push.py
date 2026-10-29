"""用 GitHub REST API 推送代码（本机直连 github.com 会被 TLS 重置）。

背景：这台机器上 ``git push`` 会报 ``unexpected eof while reading``，
但 ``api.github.com`` 可用。所以走 Git Data API 手动造一次提交：

    blob（逐文件） → tree → commit → 移动 ref

代价：远端只有一个快照提交，不保留本地历史。对「开源首发」够用；
等网络恢复或换台机器，用 ``git push --force`` 一次性把历史接管回去即可。

用法：
    py scripts/gh_push.py --repo ASH-C776/ImageAngle --token <PAT> \
        --branch main --message "初始发布"

    # 只更新（追加一个提交，保留远端已有文件）
    py scripts/gh_push.py ... --keep-tree
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = 'https://api.github.com'


def _req(method: str, url: str, token: str, payload=None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'ImageAngle-release')
    if data:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode('utf-8')
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        raise SystemExit(f'{method} {url} → {e.code}\n{body[:600]}') from None


def tracked_files() -> list[str]:
    """要上传的文件：git 已跟踪的 + 未忽略的新文件。.gitignore 说的不传就不传。"""
    out = subprocess.run(['git', 'ls-files', '--cached', '--others',
                          '--exclude-standard', '-z'],
                         cwd=ROOT, capture_output=True, check=True).stdout
    names = [n for n in out.decode('utf-8').split('\0') if n]
    # 去重并只留真实存在的文件（删除过的旧路径不该出现在 tree 里）
    seen, files = set(), []
    for n in names:
        if n not in seen and os.path.isfile(os.path.join(ROOT, n)):
            seen.add(n)
            files.append(n)
    return sorted(files)


def make_blob(token: str, repo: str, path: str) -> dict:
    with open(os.path.join(ROOT, path), 'rb') as f:
        content = base64.b64encode(f.read()).decode()
    r = _req('POST', f'{API}/repos/{repo}/git/blobs', token,
             {'content': content, 'encoding': 'base64'})
    return {'path': path, 'mode': '100644', 'type': 'blob', 'sha': r['sha']}


def head_commit(token: str, repo: str, branch: str) -> str | None:
    try:
        r = _req('GET', f'{API}/repos/{repo}/git/ref/heads/{branch}', token)
        return r['object']['sha']
    except SystemExit:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', required=True, help='owner/name')
    ap.add_argument('--token', default=os.environ.get('GITHUB_TOKEN', ''))
    ap.add_argument('--branch', default='main')
    ap.add_argument('--message', required=True)
    ap.add_argument('--keep-tree', action='store_true',
                    help='在远端已有 tree 基础上追加（默认从头重建）')
    args = ap.parse_args()
    if not args.token:
        raise SystemExit('缺 token（--token 或环境变量 GITHUB_TOKEN）')

    files = tracked_files()
    print(f'待上传 {len(files)} 个文件')

    parent = head_commit(args.token, args.repo, args.branch)
    base_tree = None
    if parent and args.keep_tree:
        base_tree = _req('GET', f'{API}/repos/{args.repo}/git/commits/{parent}',
                         args.token)['tree']['sha']
    print('远端父提交:', parent or '（空仓库，首次推送）')

    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(pool.map(lambda p: make_blob(args.token, args.repo, p), files))
    print(f'上传 blob 完成：{len(entries)} 个')

    tree_payload = {'tree': entries}
    if base_tree:
        tree_payload['base_tree'] = base_tree
    tree = _req('POST', f'{API}/repos/{args.repo}/git/trees', args.token, tree_payload)

    commit_payload = {'message': args.message, 'tree': tree['sha']}
    if parent:
        commit_payload['parents'] = [parent]
    commit = _req('POST', f'{API}/repos/{args.repo}/git/commits', args.token, commit_payload)
    print('新提交:', commit['sha'][:12])

    if parent:
        _req('PATCH', f'{API}/repos/{args.repo}/git/refs/heads/{args.branch}', args.token,
             {'sha': commit['sha'], 'force': True})
    else:
        _req('POST', f'{API}/repos/{args.repo}/git/refs', args.token,
             {'ref': f'refs/heads/{args.branch}', 'sha': commit['sha']})
    print(f'已更新 {args.branch} → {commit["sha"][:12]}')
    print('BRANCH_HEAD=' + commit['sha'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
