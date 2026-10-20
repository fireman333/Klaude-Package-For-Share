#!/usr/bin/env python3
"""
Download OpenEvidence PublicationFigure images from artifact JSON(s).

Usage:
    # Single article.json
    python3 download_figures.py path/to/q1_article.json

    # Whole artifact dir (scans *_article.json)
    python3 download_figures.py path/to/oe_artifacts/

    # NCCN only (URL substring match — catches both host and path, e.g. /nccn_images/)
    python3 download_figures.py path/to/oe_artifacts/ --match nccn

Output:
    {artifact_dir}/figures/{qid}_{slug}.{ext}
    {artifact_dir}/figures/figures.json   # manifest: url, local path, caption, source host
"""

import sys
import os
import re
import json
import argparse
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

from parse_oe import extract_json_object


FIGURE_PATTERN = "REACTCOMPONENT!:!PublicationFigure!:!"
TIMEOUT_SEC = 20
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 OE-figure-downloader"


def iter_figures(article_json_path):
    """Yield {url, caption, name} dicts from one article JSON."""
    with open(article_json_path) as f:
        data = json.load(f)
    text = json.dumps(data)
    i = 0
    while i < len(text):
        idx = text.find(FIGURE_PATTERN, i)
        if idx == -1:
            break
        brace = text.find('{', idx)
        if brace == -1:
            break
        raw = extract_json_object(text, brace)
        if not raw:
            i = brace + 1
            continue
        try:
            unescaped = json.loads(f'"{raw}"') if raw.startswith('\\') else raw
        except json.JSONDecodeError:
            unescaped = raw
        payload = unescaped.replace('\\"', '"').replace('\\\\', '\\')
        try:
            fig = json.loads(payload)
        except json.JSONDecodeError:
            try:
                fig = json.loads(raw)
            except json.JSONDecodeError:
                i = brace + len(raw)
                continue
        url = fig.get('url')
        if url:
            yield {
                'url': url,
                'caption': fig.get('caption', ''),
                'name': fig.get('name', 'Figure'),
            }
        i = brace + len(raw)


def slugify(text, max_len=40):
    text = re.sub(r'[^A-Za-z0-9._-]+', '_', text).strip('_')
    return text[:max_len] or 'figure'


def ext_from_url(url):
    path = url.split('?', 1)[0]
    for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.pdf'):
        if path.lower().endswith(ext):
            return ext
    return '.bin'


def host_of(url):
    m = re.match(r'https?://([^/]+)/', url)
    return m.group(1).lower() if m else ''


def download(url, dest_path, timeout=TIMEOUT_SEC):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        with open(dest_path, 'wb') as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
    return os.path.getsize(dest_path)


def qid_from_filename(path):
    base = os.path.basename(path)
    m = re.match(r'(.+?)_article\.json$', base)
    return m.group(1) if m else os.path.splitext(base)[0]


def process_one(article_path, figures_dir, url_filter, seen_urls):
    qid = qid_from_filename(article_path)
    entries = []
    for fig in iter_figures(article_path):
        url = fig['url']
        host = host_of(url)
        if url_filter and url_filter.lower() not in url.lower():
            continue
        if url in seen_urls:
            entries.append({'qid': qid, 'url': url, 'status': 'dup',
                           'local_path': seen_urls[url], 'caption': fig['caption'],
                           'name': fig['name'], 'host': host})
            continue
        slug = slugify(fig.get('name', 'figure'))
        # short hash to avoid name collisions across same qid
        url_hash = hashlib.md5(url.encode()).hexdigest()[:6]
        filename = f"{qid}_{slug}_{url_hash}{ext_from_url(url)}"
        dest = figures_dir / filename
        entry = {'qid': qid, 'url': url, 'caption': fig['caption'],
                 'name': fig['name'], 'host': host, 'local_path': str(dest)}
        try:
            size = download(url, dest)
            entry['status'] = 'ok'
            entry['bytes'] = size
            seen_urls[url] = str(dest)
        except urllib.error.HTTPError as e:
            entry['status'] = f'http_{e.code}'
        except urllib.error.URLError as e:
            entry['status'] = f'url_err:{e.reason}'
        except Exception as e:  # noqa: BLE001
            entry['status'] = f'err:{type(e).__name__}:{e}'
        entries.append(entry)
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('target', help='article.json or artifact dir')
    parser.add_argument('--match', default='', help='Substring filter for URL (host or path; e.g., nccn, jama, pmc). Case-insensitive.')
    parser.add_argument('--dry-run', action='store_true', help='List figures but do not download')
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    if target.is_file():
        article_paths = [target]
        artifact_dir = target.parent
    elif target.is_dir():
        article_paths = sorted(target.glob('*_article.json')) + sorted(target.glob('article.json'))
        artifact_dir = target
        if not article_paths:
            print(f'No *_article.json found under {target}', file=sys.stderr)
            sys.exit(1)
    else:
        print(f'Not found: {target}', file=sys.stderr)
        sys.exit(1)

    figures_dir = artifact_dir / 'figures'
    figures_dir.mkdir(exist_ok=True)

    if args.dry_run:
        total = 0
        for p in article_paths:
            qid = qid_from_filename(p)
            for fig in iter_figures(p):
                if args.match and args.match.lower() not in fig['url'].lower():
                    continue
                host = host_of(fig['url'])
                print(f"{qid}\t{host}\t{fig['name']}\t{fig['url']}")
                total += 1
        print(f'\n[dry-run] {total} figure(s) matched filter={args.match!r}', file=sys.stderr)
        return

    manifest = []
    seen_urls = {}
    for p in article_paths:
        manifest.extend(process_one(str(p), figures_dir, args.match, seen_urls))

    manifest_path = figures_dir / 'figures.json'
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    ok = sum(1 for e in manifest if e.get('status') == 'ok')
    dup = sum(1 for e in manifest if e.get('status') == 'dup')
    fail = len(manifest) - ok - dup
    print(f'figures: {ok} ok, {dup} dup, {fail} fail → {manifest_path}')


if __name__ == '__main__':
    main()
