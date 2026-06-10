import argparse
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup


def safe_name(text):
    text = re.sub(r'[^a-zA-Z0-9_\-]+', '_', text.strip())
    return text[:80] or 'page'


def html_to_text(html):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else 'untitled'
    text = soup.get_text('\n')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return title, '\n'.join(lines), soup


def same_domain(url_a, url_b):
    return urlparse(url_a).netloc == urlparse(url_b).netloc


def discover_links(base_url, soup, max_links):
    links = []
    seen = set()
    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        if not href or href.startswith('#') or href.startswith('mailto:') or href.startswith('javascript:'):
            continue
        url = urljoin(base_url, href)
        if not same_domain(base_url, url):
            continue
        if any(url.lower().endswith(ext) for ext in ['.jpg', '.png', '.gif', '.zip', '.rar', '.mp4', '.mp3']):
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append(url)
        if len(links) >= max_links:
            break
    return links


def fetch_page(url, timeout):
    resp = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
    resp.raise_for_status()
    return resp.text


def save_page(out_dir, idx, source_name, url, category, html):
    title, text, soup = html_to_text(html)
    name = safe_name(source_name or title)
    path = out_dir / f'{idx:04d}_{name}.txt'
    body = f'Title: {title}\nSource: {url}\nCategory: {category}\n\n{text}'
    path.write_text(body, encoding='utf-8')
    print('saved', path)
    return soup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources_csv', default='data/data_sources.csv')
    parser.add_argument('--out_dir', default='data/raw')
    parser.add_argument('--timeout', type=int, default=20)
    parser.add_argument('--expand_links', action='store_true')
    parser.add_argument('--max_links_per_source', type=int, default=20)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.sources_csv)
    if 'url' not in df.columns:
        raise ValueError('sources_csv must contain url column')

    saved_idx = 0
    visited = set()
    for _, row in df.iterrows():
        url = str(row['url']).strip()
        if not url or url.lower() == 'nan' or url in visited:
            continue
        if url.lower().endswith('.pdf'):
            print('skip pdf; download manually:', url)
            continue
        source_name = str(row.get('source_name', 'page'))
        category = str(row.get('category', 'general'))
        try:
            html = fetch_page(url, args.timeout)
            visited.add(url)
            soup = save_page(out_dir, saved_idx, source_name, url, category, html)
            saved_idx += 1
            if args.expand_links:
                for link in discover_links(url, soup, args.max_links_per_source):
                    if link in visited:
                        continue
                    try:
                        sub_html = fetch_page(link, args.timeout)
                        visited.add(link)
                        save_page(out_dir, saved_idx, source_name + '_linked', link, category, sub_html)
                        saved_idx += 1
                    except Exception as exc:
                        print('failed linked page', link, exc)
        except Exception as exc:
            print('failed', url, exc)


if __name__ == '__main__':
    main()
