#!/usr/bin/env python3
"""
PubMed Literature Search — 文獻整理小幫手

Searches PubMed via NCBI E-utilities API and generates formatted Excel + CSV output
with article metadata (PMID, title, authors, year, journal, abstract, link).

Usage:
    python pubmed_search.py config.json                              # Full search
    python pubmed_search.py config.json --update                     # Incremental update
    python pubmed_search.py config.json --fill-summaries sums.json   # Inject AI summaries
"""

import sys
import json
import os
import time
import ssl
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime

# Create SSL context — handles macOS Python missing root certificates
# PubMed is a public read-only API, so unverified context is acceptable
_ssl_context = ssl._create_unverified_context()

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

def load_config(path):
    """Load JSON config and set defaults."""
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Validate required fields
    required = ['search_terms', 'email', 'output_file']
    for field in required:
        if field not in config or not config[field]:
            print(f"Error: Required field '{field}' is missing in config.", file=sys.stderr)
            sys.exit(1)

    # Set defaults
    config.setdefault('date_range', None)
    config.setdefault('max_results', 100)
    config.setdefault('sort_by', 'pub_date')
    # Optional NCBI API key: read from the NCBI_API_KEY environment variable only
    # (works without a key at a lower rate limit: 3 req/s instead of 10).
    config['api_key'] = os.environ.get('NCBI_API_KEY', '')
    config.setdefault('generate_summary', True)
    config.setdefault('author_truncate', 6)
    config.setdefault('tool_name', 'pubmed-search-skill')

    return config


# ═══════════════════════════════════════════════════════════════════════════════
# PubMed API
# ═══════════════════════════════════════════════════════════════════════════════

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _api_request(url, params, config, max_retries=3):
    """Make an API request with retry logic and rate limiting."""
    # Add required NCBI parameters
    params['tool'] = config['tool_name']
    params['email'] = config['email']
    if config.get('api_key'):
        params['api_key'] = config['api_key']

    query_string = urllib.parse.urlencode(params)
    full_url = f"{url}?{query_string}"

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(full_url)
            req.add_header('User-Agent', f"{config['tool_name']}/1.0 ({config['email']})")
            with urllib.request.urlopen(req, timeout=30, context=_ssl_context) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            if e.code == 429:  # Rate limited
                wait_time = (2 ** attempt) * 1
                print(f"  Rate limited (429). Waiting {wait_time}s before retry...", file=sys.stderr)
                time.sleep(wait_time)
                continue
            elif e.code >= 500:  # Server error
                wait_time = (2 ** attempt) * 1
                print(f"  Server error ({e.code}). Waiting {wait_time}s before retry...", file=sys.stderr)
                time.sleep(wait_time)
                continue
            else:
                print(f"  HTTP Error {e.code}: {e.reason}", file=sys.stderr)
                raise
        except urllib.error.URLError as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 1
                print(f"  Network error. Waiting {wait_time}s before retry...", file=sys.stderr)
                time.sleep(wait_time)
                continue
            else:
                raise

    print("Error: Max retries exceeded.", file=sys.stderr)
    sys.exit(1)


def build_search_query(config, last_date=None):
    """Build PubMed search query string with optional date filtering."""
    query = config['search_terms']

    if last_date:
        # For update mode: search from last_date to present
        query = f"({query}) AND (\"{last_date}/01/01\"[PDAT] : \"3000\"[PDAT])"
    elif config.get('date_range'):
        dr = config['date_range']
        min_d = dr.get('min_date', '1900/01/01')
        max_d = dr.get('max_date', '3000/12/31')
        query = f"({query}) AND (\"{min_d}\"[PDAT] : \"{max_d}\"[PDAT])"

    return query


def esearch(query, config):
    """Search PubMed and return (web_env, query_key, total_count)."""
    params = {
        'db': 'pubmed',
        'term': query,
        'usehistory': 'y',
        'retmax': 0,
        'sort': config.get('sort_by', 'pub_date'),
    }

    xml_text = _api_request(f"{BASE_URL}/esearch.fcgi", params, config)
    root = ET.fromstring(xml_text)

    # Check for errors
    error_list = root.find('.//ErrorList')
    if error_list is not None:
        errors = [e.text for e in error_list]
        print(f"PubMed search errors: {errors}", file=sys.stderr)

    count = int(root.findtext('Count', '0'))
    web_env = root.findtext('WebEnv', '')
    query_key = root.findtext('QueryKey', '')

    if not web_env or not query_key:
        print("Error: Failed to get WebEnv/QueryKey from ESearch.", file=sys.stderr)
        sys.exit(1)

    return web_env, query_key, count


def efetch_batch(web_env, query_key, total, config):
    """Fetch article details in batches, respecting rate limits."""
    batch_size = 200
    max_results = min(total, config['max_results'])
    all_articles = []
    sleep_time = 0.1 if config.get('api_key') else 0.35

    print(f"Fetching {max_results} articles from PubMed (total found: {total})...")

    for start in range(0, max_results, batch_size):
        retmax = min(batch_size, max_results - start)
        print(f"  Fetching articles {start + 1} - {start + retmax}...")

        params = {
            'db': 'pubmed',
            'WebEnv': web_env,
            'query_key': query_key,
            'retstart': start,
            'retmax': retmax,
            'rettype': 'xml',
            'retmode': 'xml',
        }

        xml_text = _api_request(f"{BASE_URL}/efetch.fcgi", params, config)
        articles = parse_articles(xml_text)
        all_articles.extend(articles)

        # Rate limiting between batches
        if start + batch_size < max_results:
            time.sleep(sleep_time)

    return all_articles


# ═══════════════════════════════════════════════════════════════════════════════
# XML Parsing
# ═══════════════════════════════════════════════════════════════════════════════

def _get_text(element, path, default=''):
    """Safely get text from an XML element."""
    if element is None:
        return default
    el = element.find(path)
    if el is None:
        return default
    # Handle mixed content (e.g., <ArticleTitle> with inline tags)
    text = ''.join(el.itertext())
    return text.strip() if text else default


def _get_authors(article_el, truncate=6):
    """Extract author list from an Article element."""
    author_list = article_el.find('.//AuthorList')
    if author_list is None:
        return ''

    authors = []
    for author in author_list.findall('Author'):
        last = author.findtext('LastName', '')
        initials = author.findtext('Initials', '')
        if last:
            authors.append(f"{last} {initials}".strip())
        else:
            # Collective/group author
            collective = author.findtext('CollectiveName', '')
            if collective:
                authors.append(collective)

    if not authors:
        return ''

    if len(authors) > truncate:
        return ', '.join(authors[:truncate]) + ', et al.'
    return ', '.join(authors)


def _get_year(article_el):
    """Extract publication year from an Article element."""
    # Try Journal > JournalIssue > PubDate > Year
    year = article_el.findtext('.//Journal/JournalIssue/PubDate/Year')
    if year:
        return year

    # Try MedlineDate (format: "2024 Jan-Feb" or "2024")
    medline_date = article_el.findtext('.//Journal/JournalIssue/PubDate/MedlineDate', '')
    if medline_date and len(medline_date) >= 4:
        return medline_date[:4]

    # Try ArticleDate
    year = article_el.findtext('.//ArticleDate/Year')
    if year:
        return year

    return ''


def _get_abstract(article_el):
    """Extract abstract text, handling structured abstracts."""
    abstract_el = article_el.find('.//Abstract')
    if abstract_el is None:
        return ''

    parts = []
    for text_el in abstract_el.findall('AbstractText'):
        label = text_el.get('Label', '')
        text = ''.join(text_el.itertext()).strip()
        if label and text:
            parts.append(f"{label}: {text}")
        elif text:
            parts.append(text)

    return '\n'.join(parts)


def parse_articles(xml_string):
    """Parse EFetch XML response into a list of article dicts."""
    articles = []

    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as e:
        print(f"  Warning: XML parse error: {e}", file=sys.stderr)
        return articles

    for pubmed_article in root.findall('.//PubmedArticle'):
        try:
            article = pubmed_article.find('.//Article')
            if article is None:
                continue

            pmid = _get_text(pubmed_article, './/PMID')
            title = _get_text(article, 'ArticleTitle')
            year = _get_year(article)
            journal = _get_text(article, './/Journal/ISOAbbreviation')
            if not journal:
                journal = _get_text(article, './/Journal/Title')
            abstract = _get_abstract(article)

            # Author truncation uses config default; will be applied later if needed
            authors = _get_authors(article)

            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ''

            articles.append({
                'PMID': pmid,
                '標題(Title)': title,
                '作者(Authors)': authors,
                '年份(Year)': year,
                '期刊(Journal)': journal,
                'Abstract': abstract,
                '內容摘要(Summary)': '',
                '文章連結(Link)': link,
            })
        except Exception as e:
            print(f"  Warning: Failed to parse article: {e}", file=sys.stderr)
            continue

    return articles


# ═══════════════════════════════════════════════════════════════════════════════
# Data Management
# ═══════════════════════════════════════════════════════════════════════════════

COLUMNS = ['PMID', '標題(Title)', '作者(Authors)', '年份(Year)', '期刊(Journal)',
           'Abstract', '內容摘要(Summary)', '文章連結(Link)']


def load_existing(output_path):
    """Load existing Excel file for update mode. Returns (DataFrame, max_year)."""
    if not os.path.exists(output_path):
        return pd.DataFrame(columns=COLUMNS), None

    try:
        df = pd.read_excel(output_path, dtype={'PMID': str, '年份(Year)': str})
        # Ensure all expected columns exist
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ''
        df = df[COLUMNS]

        # Get the most recent year
        years = df['年份(Year)'].dropna().astype(str)
        years = years[years.str.match(r'^\d{4}$')]
        max_year = years.max() if len(years) > 0 else None

        print(f"Loaded {len(df)} existing articles (most recent year: {max_year})")
        return df, max_year
    except Exception as e:
        print(f"Warning: Could not read existing file: {e}", file=sys.stderr)
        return pd.DataFrame(columns=COLUMNS), None


def merge_articles(existing_df, new_articles):
    """Merge new articles with existing, deduplicate by PMID, sort by year desc."""
    if not new_articles:
        return existing_df

    new_df = pd.DataFrame(new_articles, columns=COLUMNS)

    if existing_df.empty:
        combined = new_df
    else:
        # Concatenate, keeping new articles' data for duplicates
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        # For duplicates, keep the LAST occurrence (new data takes precedence)
        # But preserve existing summaries if new ones are empty
        if not existing_df.empty:
            existing_summaries = existing_df.set_index('PMID')['內容摘要(Summary)'].to_dict()
            mask = combined.duplicated(subset='PMID', keep='last')
            combined = combined[~mask].copy()
            # Restore summaries for articles that already had them
            for idx, row in combined.iterrows():
                pmid = row['PMID']
                if (not row['內容摘要(Summary)'] or pd.isna(row['內容摘要(Summary)'])) and pmid in existing_summaries:
                    summary = existing_summaries[pmid]
                    if summary and not pd.isna(summary):
                        combined.at[idx, '內容摘要(Summary)'] = summary
        else:
            combined = combined.drop_duplicates(subset='PMID', keep='last')

    # Sort by year descending, then by PMID descending
    combined['_year_sort'] = pd.to_numeric(combined['年份(Year)'], errors='coerce')
    combined = combined.sort_values(['_year_sort', 'PMID'], ascending=[False, False])
    combined = combined.drop(columns=['_year_sort']).reset_index(drop=True)

    return combined


# ═══════════════════════════════════════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════════════════════════════════════

def write_excel(df, config):
    """Write formatted Excel output with hyperlinks."""
    output_path = config['output_file']
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    # Write base data
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='PubMed Results')

    # Format with openpyxl
    wb = load_workbook(output_path)
    ws = wb.active

    # Header styling
    header_font = Font(name='Arial', bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='2E5090', end_color='2E5090', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin', color='D0D0D0'),
        right=Side(style='thin', color='D0D0D0'),
        top=Side(style='thin', color='D0D0D0'),
        bottom=Side(style='thin', color='D0D0D0'),
    )

    for col_idx in range(1, len(COLUMNS) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    # Column widths
    col_widths = {
        'PMID': 14,
        '標題(Title)': 55,
        '作者(Authors)': 35,
        '年份(Year)': 10,
        '期刊(Journal)': 22,
        'Abstract': 65,
        '內容摘要(Summary)': 45,
        '文章連結(Link)': 40,
    }
    for col_idx, col_name in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = col_widths.get(col_name, 15)

    # Data cell styling
    data_font = Font(name='Arial', size=10)
    wrap_alignment = Alignment(vertical='top', wrap_text=True)
    no_wrap_alignment = Alignment(vertical='top', wrap_text=False)
    link_font = Font(name='Arial', size=10, color='0563C1', underline='single')

    wrap_columns = {'Abstract', '內容摘要(Summary)', '標題(Title)', '作者(Authors)'}
    link_col_idx = COLUMNS.index('文章連結(Link)') + 1

    for row_idx in range(2, ws.max_row + 1):
        for col_idx in range(1, len(COLUMNS) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = thin_border

            if col_idx == link_col_idx and cell.value:
                # Make clickable hyperlink
                url = str(cell.value)
                cell.hyperlink = url
                cell.font = link_font
                cell.alignment = no_wrap_alignment
            else:
                cell.font = data_font
                col_name = COLUMNS[col_idx - 1]
                cell.alignment = wrap_alignment if col_name in wrap_columns else no_wrap_alignment

    # Freeze top row
    ws.freeze_panes = 'A2'

    # Auto-filter
    ws.auto_filter.ref = ws.dimensions

    # Truncate abstracts exceeding Excel cell limit (32767 chars)
    abstract_col_idx = COLUMNS.index('Abstract') + 1
    for row_idx in range(2, ws.max_row + 1):
        cell = ws.cell(row=row_idx, column=abstract_col_idx)
        if cell.value and len(str(cell.value)) > 32000:
            cell.value = str(cell.value)[:32000] + '\n... [truncated]'

    wb.save(output_path)
    print(f"Excel output saved: {output_path}")
    return output_path


def write_csv(df, config):
    """Write CSV companion file."""
    output_path = config['output_file']
    csv_path = os.path.splitext(output_path)[0] + '.csv'
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"CSV output saved: {csv_path}")
    return csv_path


def _bibtex_escape(text):
    """Minimal BibTeX field escape: braces around special chars, strip newlines."""
    if text is None:
        return ''
    s = str(text).replace('\r', ' ').replace('\n', ' ').strip()
    # Escape backslash, then % and & which are LaTeX-special
    s = s.replace('\\', '\\textbackslash{}')
    s = s.replace('%', '\\%').replace('&', '\\&').replace('#', '\\#').replace('$', '\\$').replace('_', '\\_')
    return s


def _authors_to_bibtex(authors_str):
    """Convert 'Smith J, Doe K, Lee M' → 'Smith J and Doe K and Lee M' for BibTeX."""
    if not authors_str:
        return ''
    parts = [p.strip() for p in str(authors_str).split(',') if p.strip() and p.strip() != 'et al.']
    return ' and '.join(parts)


def write_bib(df, config):
    """Write a BibTeX companion file for downstream import (e.g. /endnote-import)."""
    output_path = config['output_file']
    bib_path = os.path.splitext(output_path)[0] + '.bib'
    lines = []
    seen_keys = set()
    for _, row in df.iterrows():
        pmid = str(row.get('PMID') or '').strip()
        if not pmid:
            continue
        key = f'pmid{pmid}'
        if key in seen_keys:
            continue
        seen_keys.add(key)

        title = _bibtex_escape(row.get('標題(Title)'))
        authors = _bibtex_escape(_authors_to_bibtex(row.get('作者(Authors)')))
        year = _bibtex_escape(row.get('年份(Year)'))
        journal = _bibtex_escape(row.get('期刊(Journal)'))
        abstract = _bibtex_escape(row.get('Abstract'))
        url = str(row.get('文章連結(Link)') or '').strip()

        entry = [f'@article{{{key},']
        if authors:
            entry.append(f'  author = {{{authors}}},')
        if title:
            entry.append(f'  title = {{{title}}},')
        if journal:
            entry.append(f'  journal = {{{journal}}},')
        if year:
            entry.append(f'  year = {{{year}}},')
        if abstract:
            entry.append(f'  abstract = {{{abstract}}},')
        if url:
            entry.append(f'  url = {{{url}}},')
        entry.append(f'  pmid = {{{pmid}}}')
        entry.append('}')
        lines.append('\n'.join(entry))

    with open(bib_path, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(lines) + '\n')
    print(f"BibTeX output saved: {bib_path}  ({len(seen_keys)} entries)")
    return bib_path


# ═══════════════════════════════════════════════════════════════════════════════
# Fill Summaries
# ═══════════════════════════════════════════════════════════════════════════════

def fill_summaries(config, summaries_path):
    """Read summaries JSON and inject into existing Excel output."""
    output_path = config['output_file']

    with open(summaries_path, 'r', encoding='utf-8') as f:
        summaries = json.load(f)

    if not os.path.exists(output_path):
        print(f"Error: Output file not found: {output_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_excel(output_path, dtype={'PMID': str, '年份(Year)': str})
    df['內容摘要(Summary)'] = df['內容摘要(Summary)'].astype(str).replace('nan', '')

    filled_count = 0
    for idx, row in df.iterrows():
        pmid = str(row['PMID'])
        if pmid in summaries and summaries[pmid]:
            df.at[idx, '內容摘要(Summary)'] = summaries[pmid]
            filled_count += 1

    # Re-write the formatted Excel
    write_excel(df, config)
    write_csv(df, config)

    print(f"Filled summaries for {filled_count} articles.")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    config_path = sys.argv[1]
    config = load_config(config_path)

    # Parse flags
    update_mode = '--update' in sys.argv
    fill_mode = '--fill-summaries' in sys.argv

    if fill_mode:
        # Find summaries path
        idx = sys.argv.index('--fill-summaries')
        if idx + 1 >= len(sys.argv):
            print("Error: --fill-summaries requires a JSON file path.", file=sys.stderr)
            sys.exit(1)
        summaries_path = sys.argv[idx + 1]
        fill_summaries(config, summaries_path)
        return

    # --- Search mode (full or update) ---
    existing_df = pd.DataFrame(columns=COLUMNS)
    last_date = None

    if update_mode:
        existing_df, last_date = load_existing(config['output_file'])
        if last_date:
            print(f"Update mode: searching for articles from {last_date} onwards...")

    # Build query and search
    query = build_search_query(config, last_date)
    print(f"Search query: {query}")

    web_env, query_key, total_count = esearch(query, config)
    print(f"PubMed returned {total_count} results.")

    if total_count == 0:
        if update_mode:
            print("No new articles found.")
        else:
            print("No articles found matching the search criteria.")
            # Create empty output with headers
            empty_df = pd.DataFrame(columns=COLUMNS)
            write_excel(empty_df, config)
            write_csv(empty_df, config)
        return

    if total_count > config['max_results']:
        print(f"Note: Limiting to {config['max_results']} articles (out of {total_count} found).")

    # Fetch articles
    new_articles = efetch_batch(web_env, query_key, total_count, config)
    print(f"Successfully parsed {len(new_articles)} articles.")

    # Merge and write
    final_df = merge_articles(existing_df, new_articles)

    new_count = len(final_df) - len(existing_df) if update_mode else len(final_df)
    write_excel(final_df, config)
    write_csv(final_df, config)
    write_bib(final_df, config)

    # Summary
    years = final_df['年份(Year)'].dropna().astype(str)
    years = years[years.str.match(r'^\d{4}$')]
    min_year = years.min() if len(years) > 0 else 'N/A'
    max_year = years.max() if len(years) > 0 else 'N/A'

    print(f"\n{'='*60}")
    print(f"Search complete!")
    print(f"  Total articles: {len(final_df)}")
    if update_mode:
        print(f"  New articles added: {new_count}")
    print(f"  Year range: {min_year} - {max_year}")
    print(f"  Output: {config['output_file']}")
    print(f"  CSV:    {os.path.splitext(config['output_file'])[0]}.csv")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
