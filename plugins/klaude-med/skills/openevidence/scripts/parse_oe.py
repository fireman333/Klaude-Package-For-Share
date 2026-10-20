#!/usr/bin/env python3
"""
Parse OpenEvidence JSON response → clean text with AMA-numbered citations.

Usage:
    python3 parse_oe.py <json_file_path>

Output (stdout):
    Line 1:  ARTICLE_ID: <uuid>
    Line 2:  blank
    Line 3+: Cleaned article text (HTML preserved, citations replaced with [N])
    ...
    Last section: numbered AMA reference list
"""

import sys
import json
import os
import re


def extract_json_object(text, start):
    """Extract a JSON object from text starting at position `start` using brace-depth counting."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def format_ref_ama(ref_text):
    """Clean a reference string for AMA display: extract URL, strip HTML tags."""
    url_match = re.search(r'href="([^"]+)"', ref_text)
    url = url_match.group(1) if url_match else None
    clean = re.sub(r'<[^>]+>', '', ref_text).strip()
    clean = re.sub(r'\.\.+$', '.', clean)
    if not clean.endswith('.'):
        clean += '.'
    if url:
        clean += f' URL: {url}'
    return clean


def normalize_ref(ref_text):
    """Normalize reference text for deduplication."""
    clean = re.sub(r'<[^>]+>', '', ref_text).strip()
    return re.sub(r'\s+', ' ', clean).lower()


def process_citations(text):
    """Parse [[[$$$...$$$]]] citation markers → deduplicated numbered refs."""
    citation_map = {}   # normalized_ref -> number
    citation_list = []  # (number, ama_formatted_text)
    counter = 0

    def replace_block(match):
        nonlocal counter
        block = match.group(1)
        parts = block.split('$$$]!!![$$$')
        seen_in_block = set()
        numbers = []
        for ref in parts:
            ref = ref.strip()
            if not ref:
                continue
            norm = normalize_ref(ref)
            if norm not in citation_map:
                counter += 1
                citation_map[norm] = counter
                citation_list.append((counter, format_ref_ama(ref)))
            num = citation_map[norm]
            if num not in seen_in_block:
                seen_in_block.add(num)
                numbers.append(str(num))
        if numbers:
            return '[' + ','.join(numbers) + ']'
        return ''

    text = re.sub(r'\[\[\[\$\$\$(.*?)\$\$\$\]\]\]', replace_block, text, flags=re.DOTALL)
    return text, citation_list


def remove_thinking_blocks(text):
    """Remove REACTCOMPONENT Thinking blocks (processing status, no clinical content)."""
    pattern = r'REACTCOMPONENT!:!Thinking!:!'
    result = []
    i = 0
    while i < len(text):
        idx = text.find(pattern, i)
        if idx == -1:
            result.append(text[i:])
            break
        result.append(text[i:idx])
        json_start = text.find('{', idx)
        if json_start == -1:
            break
        json_str = extract_json_object(text, json_start)
        if json_str:
            i = json_start + len(json_str)
        else:
            i = json_start + 1
    return ''.join(result)


def convert_publication_figures(text):
    """Convert REACTCOMPONENT PublicationFigure → clean markdown figure line."""
    pattern = r'REACTCOMPONENT!:!PublicationFigure!:!'
    result = []
    i = 0
    while i < len(text):
        idx = text.find(pattern, i)
        if idx == -1:
            result.append(text[i:])
            break
        result.append(text[i:idx])
        json_start = text.find('{', idx)
        if json_start == -1:
            result.append(text[idx:])
            break
        json_str = extract_json_object(text, json_start)
        if json_str:
            try:
                fig = json.loads(json_str)
                caption = fig.get('caption', 'Figure')
                url = fig.get('url', '')
                if url:
                    result.append(f'\n[Figure: {caption}]({url})\n')
                else:
                    result.append(f'\n[Figure: {caption}]\n')
            except json.JSONDecodeError:
                pass
            i = json_start + len(json_str)
        else:
            i = json_start + 1
    return ''.join(result)


def clean_whitespace(text):
    """Collapse excessive blank lines, strip trailing whitespace per line."""
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text.strip()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parse_oe.py <json_file_path>", file=sys.stderr)
        sys.exit(1)

    filepath = sys.argv[1]

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error loading JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # v0.2.0+ exposes article_id at top level; legacy MCPs nested it under article.id
    article_id = data.get('article_id') or data.get('article', {}).get('id') or 'UNKNOWN'
    # v0.2.0+ resolves <visual> tags into extracted_answer_raw; legacy used article.output.text
    text = data.get('extracted_answer_raw', '') or data.get('article', {}).get('output', {}).get('text', '')

    if not text.strip():
        print(f"ARTICLE_ID: {article_id}")
        print()
        print("Error: No content found in 'extracted_answer_raw' or 'article.output.text'")
        sys.exit(1)

    # Resolve sibling citations.bib next to the saved article.json (v0.2.0+ Crossref-augmented)
    bibtex_path = None
    article_path = (data.get('artifacts') or {}).get('articlePath')
    if article_path:
        candidate = os.path.join(os.path.dirname(article_path), 'citations.bib')
        if os.path.exists(candidate):
            bibtex_path = candidate

    # Step 1: Remove REACTCOMPONENT Thinking blocks
    text = remove_thinking_blocks(text)

    # Step 2: Convert REACTCOMPONENT PublicationFigure → figure lines
    text = convert_publication_figures(text)

    # Step 3: Parse citations → numbered AMA refs
    text, citation_list = process_citations(text)

    # Step 4: Clean whitespace
    text = clean_whitespace(text)

    # Output
    print(f'ARTICLE_ID: {article_id}')
    if bibtex_path:
        print(f'BIBTEX: {bibtex_path}')
    print()
    print(text)

    if citation_list:
        print()
        print('---')
        print('References')
        print()
        for num, ref in citation_list:
            print(f'{num}. {ref}')


if __name__ == '__main__':
    main()
