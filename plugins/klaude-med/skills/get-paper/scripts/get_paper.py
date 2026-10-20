#!/usr/bin/env python3
"""get_paper — fetch full-text PDF via Unpaywall (OA) or your own institution.

Legal access only: open-access copies, or your institution's licensed access.

Modes (institutional step; configure in config.json, see config.example.json):
  direct   — your institution's VPN / proxy gives you an institutional IP.
    - Realistic Chrome UA + Sec-Ch-Ua headers (passes Cloudflare bot check)
    - Warm-up GET to full-text URL → collect session cookies
    - Fetch PDF with Referer header
    - Route: env ALL_PROXY/HTTPS_PROXY, else config "socks_proxy"/"http_proxy"
      (only the institutional step uses it), else a system-wide VPN tunnel.

  prefix   — library login-URL prefix (EZproxy "login?url=" style)
    - config "proxy_prefix", e.g. https://<your-library-proxy>/login?url=
    - Needs Netscape cookies.txt exported from your logged-in browser

  ezproxy  — host-rewriting EZproxy: foo.bar.com → foo-bar-com.<proxy_host_suffix>
    - Needs Netscape cookies.txt exported from your logged-in browser

Mode chosen by config "mode" field; override with --direct or --proxy.
Unpaywall (OA) is tried first regardless of mode (unless --proxy-only).
Email for Unpaywall: env UNPAYWALL_EMAIL, else config "unpaywall_email".
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from urllib.parse import urlparse, urlunparse, urljoin, quote

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"Missing dependency: {e}. Install with: pip3 install requests beautifulsoup4",
          file=sys.stderr)
    sys.exit(1)


SKILL_DIR = Path(__file__).resolve().parent.parent
# Config lookup: $GET_PAPER_CONFIG, else <skill dir>/config.json (copy config.example.json).
CONFIG_PATH = Path(os.environ.get("GET_PAPER_CONFIG") or (SKILL_DIR / "config.json"))
CONFIG_EXAMPLE = SKILL_DIR / "config.example.json"

# Institutional (campus-IP) traffic only; OA and doi.org stay on the normal link.
# Set "socks_proxy" (e.g. socks5h://127.0.0.1:1080) or "http_proxy" in config.json.
CURL_PROXY = None  # set by ensure_campus_route() before the direct-mode fetch

CHROME_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Google Chrome";v="130", "Chromium";v="130", "Not?A_Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
}


def _curl_header_args(extra=None):
    """Build -H args from CHROME_HEADERS + optional overrides."""
    merged = dict(CHROME_HEADERS)
    if extra:
        merged.update(extra)
    args = []
    for k, v in merged.items():
        args.extend(["-H", f"{k}: {v}"])
    return args


def curl_fetch(url, *, cookie_jar, output_path, referer=None, sec_fetch_site="none",
               timeout=60):
    """Run curl with Chrome headers + cookie jar. Returns (status_code, effective_url)
    or (None, None) on subprocess error."""
    extra = {"Sec-Fetch-Site": sec_fetch_site}
    if referer:
        extra["Referer"] = referer
    cmd = [
        "curl", "-sS", "-L",
        "-w", "%{http_code}\n%{url_effective}",
        "-c", str(cookie_jar), "-b", str(cookie_jar),
        "-o", str(output_path),
        *_curl_header_args(extra),
        "--max-time", str(timeout),
        *(["--proxy", CURL_PROXY] if CURL_PROXY else []),
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None, None
    out = proc.stdout.strip().split("\n", 1)
    status = int(out[0]) if out and out[0].isdigit() else None
    eff = out[1] if len(out) > 1 else url
    return status, eff


# ---------- config + helpers ----------

def load_config():
    if not CONFIG_PATH.exists():
        # OA-only usage works without any config (just set UNPAYWALL_EMAIL).
        print(f"[config] {CONFIG_PATH} not found — OA-only defaults. For institutional "
              f"access: cp {CONFIG_EXAMPLE} {CONFIG_PATH} and edit it.", file=sys.stderr)
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def expand(p):
    return Path(os.path.expanduser(p))


def normalize_doi(s):
    s = s.strip()
    if s.startswith("10.") and "/" in s:
        return s.rstrip(".,;)")
    m = re.search(r"10\.\d{4,9}/[^\s?#]+", s)
    if m:
        return m.group(0).rstrip(".,;)")
    return None


def safe_filename(doi):
    return doi.replace("/", "_").replace(":", "_") + ".pdf"


def looks_like_pdf(response):
    ct = response.headers.get("content-type", "").lower()
    if ct.startswith("application/pdf"):
        return True
    return response.content[:5] == b"%PDF-"


# ---------- Unpaywall (OA) ----------

def try_unpaywall(doi, email):
    """Return an ordered list of candidate PDF URLs (best first); [] if none."""
    if not email:
        return []
    try:
        r = requests.get(
            f"https://api.unpaywall.org/v2/{quote(doi, safe='/')}",
            params={"email": email}, timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception as e:
        print(f"[unpaywall] skipped: {e}", file=sys.stderr)
        return []

    # best_oa_location often has url_for_pdf=None even when is_oa is true
    # (PLOS is a frequent offender: its publisher location links to the landing
    # page only). Collect every location instead of giving up on the best one,
    # and let the caller try them in turn — institutional repositories are the
    # most likely to 403 or serve an HTML splash page.
    best = (data.get("best_oa_location") or {}).get("url_for_pdf")
    others = [loc.get("url_for_pdf") for loc in (data.get("oa_locations") or [])]
    others = [u for u in others if u and u != best]

    # Europe PMC's render endpoint is the single most reliable OA source: it
    # answers application/pdf to a plain curl, while pmc.ncbi.nlm.nih.gov,
    # BioMed Central and most institutional repositories serve a bot-check page
    # (HTTP 200 + HTML, or a Cloudflare 403). Slot it in right after the
    # publisher's own link, which is usually direct when it works at all.
    pmcid = (_find_pmcid([best] + others if best else others)
             or _doi_to_pmcid(doi, email) or _epmc_pmcid(doi))
    europe_pmc = [f"https://europepmc.org/articles/{pmcid}?pdf=render"] if pmcid else []

    return dedupe(([best] if best else []) + europe_pmc + others)


PMCID_RE = re.compile(r"(PMC\d+)", re.I)


def _find_pmcid(urls):
    for u in urls:
        m = PMCID_RE.search(u or "")
        if m:
            return m.group(1).upper()
    return None


def _doi_to_pmcid(doi, email):
    """Ask the PMC ID Converter whether this DOI has a PMC copy."""
    try:
        r = requests.get(
            "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/",
            params={"ids": doi, "format": "json", "tool": "get-paper",
                    "email": email},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        records = r.json().get("records") or []
        return (records[0].get("pmcid") if records else None) or None
    except Exception as e:
        print(f"[idconv] skipped: {e}", file=sys.stderr)
        return None


def _epmc_pmcid(doi):
    """Fallback when the NCBI ID Converter is down or rate-limited (HTTP 429)."""
    try:
        r = requests.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": f'DOI:"{doi}"', "format": "json", "resultType": "lite"},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        for hit in r.json().get("resultList", {}).get("result", []):
            if hit.get("pmcid"):
                return hit["pmcid"]
    except Exception as e:
        print(f"[epmc] skipped: {e}", file=sys.stderr)
    return None


def dedupe(urls):
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ---------- shared HTML parser ----------

def find_pdf_url(html, base_url, doi=None):
    """Look for citation_pdf_url meta; fallback prefers anchors that match the current DOI
    (long review papers have unrelated PDF links in references — must be DOI-aware)."""
    soup = BeautifulSoup(html, "html.parser")

    meta = soup.find("meta", attrs={"name": "citation_pdf_url"})
    if meta and meta.get("content"):
        return urljoin(base_url, meta["content"])

    link = soup.find("link", attrs={"rel": "alternate", "type": "application/pdf"})
    if link and link.get("href"):
        return urljoin(base_url, link["href"])

    # Anchor fallback: prefer URLs containing current DOI (handles long review papers
    # with unrelated PDF links in their references list)
    doi_lower = (doi or "").lower()
    doi_tail = doi_lower.split("/", 1)[-1] if doi_lower else ""
    matching = []
    fallback = []
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if "/doi/pdf" in href or "/doi/epdf" in href or href.endswith(".pdf"):
            (matching if (doi_tail and doi_tail in href) else fallback).append(a["href"])
    if matching:
        return urljoin(base_url, matching[0])
    if fallback:
        return urljoin(base_url, fallback[0])

    return None


def resolve_doi(doi, session=None):
    """DOI → publisher URL via doi.org redirect. Tolerates non-2xx landing pages
    (some publishers 403 the short `/doi/<DOI>` form but accept `/doi/full/<DOI>`)."""
    s = session or requests.Session()
    s.headers.update(CHROME_HEADERS)
    r = s.get(
        f"https://doi.org/{quote(doi, safe='/')}",
        allow_redirects=True, timeout=30,
    )
    # Return final URL even on 403/5xx — caller will try variants
    return r.url


def url_candidates(publisher_url):
    """Return ordered list of URLs to try as warm-up landing pages."""
    cands = [publisher_url]
    if "/doi/" in publisher_url and not any(
        seg in publisher_url for seg in ("/doi/full/", "/doi/pdf/", "/doi/abs/", "/doi/epdf/")
    ):
        cands.append(publisher_url.replace("/doi/", "/doi/full/", 1))
    return cands


# ---------- direct mode (institutional VPN / proxy) ----------

def _port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _default_route_is_tunnel():
    try:
        out = subprocess.run(["route", "-n", "get", "default"],
                             capture_output=True, text=True).stdout
    except OSError:
        return False
    m = re.search(r"interface:\s*(\S+)", out)
    return bool(m and m.group(1).startswith("utun"))


def ensure_campus_route(cfg, verbose=False):
    """Pick how institutional requests reach an institutional IP; exit 7 early if none."""
    global CURL_PROXY
    if os.environ.get("ALL_PROXY") or os.environ.get("HTTPS_PROXY"):
        if verbose:
            print("[route]    env proxy", file=sys.stderr)
        return
    http_proxy = cfg.get("http_proxy")
    if http_proxy:
        CURL_PROXY = http_proxy
        if verbose:
            print(f"[route]    HTTP proxy {http_proxy} (institutional step only)",
                  file=sys.stderr)
        return
    socks_url = cfg.get("socks_proxy")
    if socks_url:
        u = urlparse(socks_url)
        if u.hostname and u.port and _port_open(u.hostname, u.port):
            CURL_PROXY = socks_url
            if verbose:
                print(f"[route]    SOCKS {socks_url} (institutional step only)",
                      file=sys.stderr)
            return
    if _default_route_is_tunnel():
        print("[route]    system-wide VPN (utun default route) — all traffic "
              "is going through it", file=sys.stderr)
        return
    print("No institutional route: no 'socks_proxy' listening / 'http_proxy' set "
          "in config.json, and no system-wide VPN detected.", file=sys.stderr)
    print("Connect your institution's VPN (or start your SOCKS tunnel), set "
          "socks_proxy/http_proxy in config.json, then retry. "
          "Or use mode 'prefix' (proxy_prefix) instead.", file=sys.stderr)
    sys.exit(7)


def _discard(path):
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass

def fetch_direct(doi, out_path, cfg, verbose=False):
    """Institutional VPN/proxy flow via curl subprocess (requests is blocked by Cloudflare TLS fingerprinting).

    Warm-up at full-text URL → curl persists session cookies → fetch PDF with Referer.
    """
    if not shutil.which("curl"):
        print("curl not found in PATH; direct mode requires system curl.", file=sys.stderr)
        sys.exit(1)
    ensure_campus_route(cfg, verbose=verbose)

    publisher_url = resolve_doi(doi)  # doi.org is not behind Cloudflare; requests works
    if verbose:
        print(f"[publisher] {publisher_url}", file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="get_paper_") as tmpd:
        cookie_jar = Path(tmpd) / "cookies.txt"
        landing_path = Path(tmpd) / "landing.html"

        # Warm-up: try original URL + /doi/full/ variant
        landing_url = None
        status = None
        for cand in url_candidates(publisher_url):
            if verbose:
                print(f"[warm-up]  try → {cand}", file=sys.stderr)
            status, eff = curl_fetch(
                cand, cookie_jar=cookie_jar, output_path=landing_path,
                sec_fetch_site="none", timeout=60,
            )
            if status == 200:
                landing_url = eff
                break

        if status != 200 or landing_url is None:
            print(f"Publisher warm-up failed (HTTP {status}).", file=sys.stderr)
            print("Likely causes: VPN/proxy not connected (institutional IP needed), "
                  "Cloudflare bot challenge, or your institution has no subscription.",
                  file=sys.stderr)
            print("Check your IP with: curl -s https://ipinfo.io/org "
                  "(should show your institution's network)", file=sys.stderr)
            sys.exit(7)

        # Did the warm-up itself return a PDF? (some publishers redirect /doi/full → /doi/pdf)
        with open(landing_path, "rb") as f:
            head = f.read(5)
        if head == b"%PDF-":
            shutil.copy(landing_path, out_path)
            print(f"OK (direct, warm-up returned PDF): {out_path}")
            return

        # Parse landing HTML for PDF URL (DOI-aware to avoid grabbing unrelated
        # PDF links from references list)
        html = landing_path.read_text(encoding="utf-8", errors="replace")
        pdf_url = find_pdf_url(html, landing_url, doi=doi)
        if not pdf_url:
            print("Could not locate PDF URL on landing page.", file=sys.stderr)
            print(f"Landing: {landing_url}  (saved to {landing_path})", file=sys.stderr)
            sys.exit(5)
        if verbose:
            print(f"[pdf]      {pdf_url}", file=sys.stderr)

        status2, _ = curl_fetch(
            pdf_url, cookie_jar=cookie_jar, output_path=out_path,
            referer=landing_url, sec_fetch_site="same-origin", timeout=120,
        )
        if status2 != 200:
            _discard(out_path)
            print(f"PDF fetch returned HTTP {status2}.", file=sys.stderr)
            sys.exit(5)

        with open(out_path, "rb") as f:
            magic = f.read(5)
        if magic != b"%PDF-":
            _discard(out_path)
            print(f"Downloaded file is not a PDF (magic bytes: {magic!r}).", file=sys.stderr)
            print("Could be VPN dropped, paywall layer, or anti-bot challenge.",
                  file=sys.stderr)
            sys.exit(6)

        print(f"OK (direct): {out_path}")


# ---------- ezproxy mode (URL rewriting + Netscape cookies) ----------

def to_proxy_url(url, proxy_suffix, port=None):
    """https://www.nejm.org/path  →  https://www-nejm-org.<suffix>[:port]/path"""
    p = urlparse(url)
    if not p.hostname:
        raise ValueError(f"Cannot parse hostname from {url}")
    new_host = p.hostname.replace(".", "-") + "." + proxy_suffix
    if port:
        new_host = f"{new_host}:{port}"
    return urlunparse(("https", new_host, p.path, p.params, p.query, p.fragment))


def is_proxied(url, proxy_suffix):
    p = urlparse(url)
    return bool(p.hostname and proxy_suffix in p.hostname)


def fetch_ezproxy(doi, out_path, cfg, verbose=False):
    proxy_suffix = cfg["proxy_host_suffix"].lstrip(".")
    proxy_port = cfg.get("proxy_port")
    cookies_path = expand(cfg.get("cookies_path", str(SKILL_DIR / "cookies.txt")))

    if not cookies_path.exists():
        print(f"Cookies file missing: {cookies_path}", file=sys.stderr)
        print("Export logged-in library cookies (Netscape format) to that path.",
              file=sys.stderr)
        sys.exit(4)

    jar = MozillaCookieJar(str(cookies_path))
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        print(f"Failed to load cookies ({e}). Re-export as Netscape format.",
              file=sys.stderr)
        sys.exit(4)

    session = requests.Session()
    session.cookies = jar
    session.headers.update(CHROME_HEADERS)

    publisher_url = resolve_doi(doi)
    if verbose:
        print(f"[publisher] {publisher_url}", file=sys.stderr)

    proxy_url = to_proxy_url(publisher_url, proxy_suffix, proxy_port)
    if verbose:
        print(f"[proxy]    {proxy_url}", file=sys.stderr)

    try:
        r = session.get(proxy_url, timeout=60, allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"Proxy fetch failed: {e}", file=sys.stderr)
        sys.exit(5)

    if looks_like_pdf(r):
        out_path.write_bytes(r.content)
        print(f"OK (ezproxy direct): {out_path}")
        return

    pdf_url = find_pdf_url(r.text, r.url, doi=doi)
    if not pdf_url:
        print("Could not locate PDF URL in page.", file=sys.stderr)
        sys.exit(5)
    if verbose:
        print(f"[pdf]      {pdf_url}", file=sys.stderr)

    if not is_proxied(pdf_url, proxy_suffix):
        pdf_url = to_proxy_url(pdf_url, proxy_suffix, proxy_port)
        if verbose:
            print(f"[pdf']     re-proxied → {pdf_url}", file=sys.stderr)

    try:
        r2 = session.get(pdf_url, timeout=120, allow_redirects=True,
                         headers={"Referer": r.url})
        r2.raise_for_status()
    except requests.RequestException as e:
        print(f"PDF download failed: {e}", file=sys.stderr)
        sys.exit(5)

    if not looks_like_pdf(r2):
        print("Downloaded content is not a valid PDF. Cookies may be expired.",
              file=sys.stderr)
        sys.exit(6)

    out_path.write_bytes(r2.content)
    print(f"OK (ezproxy): {out_path}")


# ---------- prefix mode (library login-URL prefix) ----------

def fetch_prefix(doi, out_path, cfg, verbose=False):
    """Open <proxy_prefix><publisher_url> with logged-in library cookies."""
    prefix = cfg["proxy_prefix"]
    cookies_path = expand(cfg.get("cookies_path", str(SKILL_DIR / "cookies.txt")))
    session = requests.Session()
    session.headers.update(CHROME_HEADERS)
    if cookies_path.exists():
        jar = MozillaCookieJar(str(cookies_path))
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
            session.cookies = jar
        except Exception as e:
            print(f"Failed to load cookies ({e}). Re-export as Netscape format.",
                  file=sys.stderr)
            sys.exit(4)
    else:
        print(f"[prefix] no cookies file at {cookies_path}; trying without "
              "(will likely hit the library login page)", file=sys.stderr)

    publisher_url = resolve_doi(doi)
    target = prefix + publisher_url
    if verbose:
        print(f"[publisher] {publisher_url}\n[prefix]    {target}", file=sys.stderr)
    try:
        r = session.get(target, timeout=60, allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"Prefix fetch failed: {e}", file=sys.stderr)
        sys.exit(5)
    if looks_like_pdf(r):
        out_path.write_bytes(r.content)
        print(f"OK (prefix): {out_path}")
        return
    pdf_url = find_pdf_url(r.text, r.url, doi=doi)
    if not pdf_url:
        print("Could not locate PDF URL (not logged in / no subscription?). "
              "Re-export cookies after logging in to your library proxy.", file=sys.stderr)
        sys.exit(5)
    # Already on the proxied host after redirects? otherwise wrap with the prefix.
    if urlparse(pdf_url).hostname != urlparse(r.url).hostname:
        pdf_url = prefix + pdf_url
    if verbose:
        print(f"[pdf]      {pdf_url}", file=sys.stderr)
    try:
        r2 = session.get(pdf_url, timeout=120, allow_redirects=True,
                         headers={"Referer": r.url})
        r2.raise_for_status()
    except requests.RequestException as e:
        print(f"PDF download failed: {e}", file=sys.stderr)
        sys.exit(5)
    if not looks_like_pdf(r2):
        print("Downloaded content is not a valid PDF. Cookies may be expired.",
              file=sys.stderr)
        sys.exit(6)
    out_path.write_bytes(r2.content)
    print(f"OK (prefix): {out_path}")


# ---------- main ----------

def determine_mode(cfg, args):
    if args.direct:
        return "direct"
    if args.proxy:
        return "prefix" if cfg.get("proxy_prefix") else "ezproxy"
    cfg_mode = (cfg.get("mode") or "").lower()
    if cfg_mode in ("direct", "ezproxy", "prefix"):
        return cfg_mode
    # auto-detect from which fields are filled in
    if cfg.get("proxy_prefix"):
        return "prefix"
    return "ezproxy" if cfg.get("proxy_host_suffix") else "direct"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="DOI (10.xxxx/yyyy) or publisher URL containing one")
    ap.add_argument("-o", "--output", help="Output PDF path (default: <download_dir>/<doi>.pdf)")
    ap.add_argument("--proxy-only", action="store_true",
                    help="Skip Unpaywall; go straight to institutional path")
    ap.add_argument("--oa-only", action="store_true",
                    help="Only try Unpaywall; never touch institutional path")
    ap.add_argument("--direct", action="store_true",
                    help="Force direct mode (institutional VPN/proxy). Overrides config.")
    ap.add_argument("--proxy", action="store_true",
                    help="Force library-proxy mode (prefix if proxy_prefix set, else ezproxy host rewriting).")
    ap.add_argument("-f", "--force", action="store_true",
                    help="Re-download even if the output PDF already exists")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.direct and args.proxy:
        print("--direct and --proxy are mutually exclusive.", file=sys.stderr)
        sys.exit(2)

    cfg = load_config()
    download_dir = expand(cfg.get("download_dir", "~/Downloads/papers"))
    email = os.environ.get("UNPAYWALL_EMAIL") or cfg.get("unpaywall_email", "")
    if email in ("", "your-email@example.com"):
        email = ""
        print("[unpaywall] no email: set env UNPAYWALL_EMAIL (any real address) to enable "
              "the open-access lookup.", file=sys.stderr)
    download_dir.mkdir(parents=True, exist_ok=True)

    doi = normalize_doi(args.input)
    if not doi:
        print(f"Could not extract DOI from: {args.input}", file=sys.stderr)
        sys.exit(2)
    if args.verbose:
        print(f"[doi]      {doi}", file=sys.stderr)

    out_path = Path(args.output) if args.output else download_dir / safe_filename(doi)
    # Re-fetching the same paper only adds load that publisher abuse detection counts.
    if not args.force and out_path.exists() and out_path.read_bytes()[:5] == b"%PDF-":
        print(f"OK (already exists): {out_path}")
        return

    # Step 1: Unpaywall (OA)
    if not args.proxy_only:
        for oa_url in try_unpaywall(doi, email):
            if args.verbose:
                print(f"[unpaywall] OA → {oa_url}", file=sys.stderr)
            # Use curl, not requests: PMC and several publishers reject the
            # requests TLS fingerprint and answer with HTML instead of a PDF.
            with tempfile.TemporaryDirectory() as td:
                tmp_pdf = Path(td) / "oa.pdf"
                status, _ = curl_fetch(oa_url, cookie_jar=Path(td) / "cookies.txt",
                                       output_path=tmp_pdf)
                if status == 200 and tmp_pdf.exists() and \
                        tmp_pdf.read_bytes()[:5] == b"%PDF-":
                    out_path.write_bytes(tmp_pdf.read_bytes())
                    print(f"OK (OA): {out_path}")
                    return
            if args.verbose:
                print(f"[unpaywall] not a PDF (HTTP {status}); next candidate",
                      file=sys.stderr)

    if args.oa_only:
        print("No OA copy found and --oa-only set.", file=sys.stderr)
        sys.exit(3)

    # Step 2: institutional path (mode dispatch)
    mode = determine_mode(cfg, args)
    if args.verbose:
        print(f"[mode]     {mode}", file=sys.stderr)

    if mode == "direct":
        fetch_direct(doi, out_path, cfg, verbose=args.verbose)
    elif mode == "prefix":
        if not cfg.get("proxy_prefix"):
            print("prefix mode but proxy_prefix not set in config.", file=sys.stderr)
            sys.exit(1)
        fetch_prefix(doi, out_path, cfg, verbose=args.verbose)
    elif mode == "ezproxy":
        if not cfg.get("proxy_host_suffix"):
            print("ezproxy mode but proxy_host_suffix not set in config.", file=sys.stderr)
            sys.exit(1)
        fetch_ezproxy(doi, out_path, cfg, verbose=args.verbose)
    else:
        print(f"Unknown mode: {mode}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
