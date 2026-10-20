#!/usr/bin/env python3
"""
extract_metadata.py — PDF 文獻 metadata 萃取工具
用法: python3 extract_metadata.py <目錄路徑> [--no-recurse]

輸出每個 PDF 的建議 year_author_title 新檔名。
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path
from urllib.parse import unquote

# ── 設定 ──────────────────────────────────────────────────────────────

# 這些關鍵字出現在檔名中，視為使用者筆記，略過
SKIP_KEYWORDS = ["整理", "筆記", "研究", "想法", "總結", "回顧", "OpenEvidence"]

# mdls title 若等於這些值，視為無效（是 PDF 生成軟體名稱）
INVALID_TITLE_PATTERNS = [
    r"^Adobe", r"^Thomson$", r"^Elsevier$", r"^LaTeX",
    r"^Arbortext", r"^Microsoft", r"^Word", r"^InDesign",
]

# ── Helper functions ───────────────────────────────────────────────────

def parse_mdls(path: str) -> dict:
    """用 mdls 取得 macOS Spotlight metadata。"""
    result = {"title": None, "year": None, "description": None}
    try:
        out = subprocess.check_output(
            ["mdls", "-name", "kMDItemTitle", "-name", "kMDItemDescription", str(path)],
            text=True, stderr=subprocess.DEVNULL
        )
    except Exception:
        return result

    for line in out.splitlines():
        if "kMDItemTitle" in line and "(null)" not in line:
            m = re.search(r'"(.+)"', line)
            if m:
                title = m.group(1).strip()
                if not any(re.search(p, title) for p in INVALID_TITLE_PATTERNS):
                    result["title"] = title
        if "kMDItemDescription" in line and "(null)" not in line:
            m = re.search(r'"(.+)"', line)
            if m:
                result["description"] = m.group(1)
                # 從 description 解出年份
                ym = re.search(r'\b(20\d{2}|19\d{2})\b', m.group(1))
                if ym:
                    result["year"] = ym.group(1)
    return result


def parse_pypdf_page0(path: str) -> dict:
    """用 pypdf 讀取 page 0 文字，嘗試萃取 title / first_author / year。"""
    result = {"title": None, "author": None, "year": None, "raw_text": ""}
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        text = reader.pages[0].extract_text() or ""
        result["raw_text"] = text[:1000]
    except Exception:
        return result

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 年份：找第一個合理年份
    for line in lines[:30]:
        ym = re.search(r'\b(20\d{2}|19\d{2})\b', line)
        if ym:
            result["year"] = ym.group(1)
            break

    # 標題：找最長的純文字行（通常是大字體標題），排除短行和全大寫行
    candidates = [l for l in lines[:20] if 20 < len(l) < 200 and not l.isupper()]
    if candidates:
        result["title"] = max(candidates, key=len)

    # 第一作者：找 "Firstname Lastname, MD" 或 "Lastname F," 或 "Lastname et al."
    author_patterns = [
        r'^([A-Z][a-z]+(?:-[A-Z][a-z]+)?),?\s+[A-Z]{1,3}\b',  # Lastname F,
        r'^([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+[A-Z][a-z]+,?\s+MD',  # Firstname Lastname, MD
        r'([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+et al\.',  # Lastname et al.
    ]
    for line in lines[:25]:
        for pat in author_patterns:
            m = re.search(pat, line)
            if m:
                result["author"] = m.group(1)
                break
        if result["author"]:
            break

    return result


def parse_filename(filename: str) -> dict:
    """從檔名推斷 year / author / title。"""
    result = {"year": None, "author": None, "title_hint": None}
    name = unquote(filename)  # URL decode
    name = re.sub(r'\.pdf$', '', name, flags=re.IGNORECASE)

    # 模式 1: "YEAR FirstLast, et al" 或 "YEAR FL Author"
    m = re.match(r'^(\d{4})\s+([A-Z]{1,2}[a-zA-Z]+(?:\s+[A-Z]{1,2}[a-zA-Z]*)?)', name)
    if m:
        result["year"] = m.group(1)
        parts = m.group(2).strip().split()
        result["author"] = parts[-1]  # last word as lastname
        return result

    # 模式 2: "lastname-et-al-YEAR-title-words"
    m = re.match(r'^([a-zA-Z\-]+?)-et-al-(\d{4})-(.+)', name)
    if m:
        result["author"] = m.group(1).split("-")[0].capitalize()
        result["year"] = m.group(2)
        result["title_hint"] = m.group(3).replace("-", " ").replace("%20", " ")
        return result

    # 模式 3: "lastname-year" 或純 DOI
    ym = re.search(r'\b(20\d{2}|19\d{2})\b', name)
    if ym:
        result["year"] = ym.group(1)

    return result


def slugify_title(title: str, max_len: int = 50) -> str:
    """標題轉 slug：去除冠詞、特殊字元，底線連接，截斷。"""
    # 保留常用縮寫
    keep = title

    # 去掉標點（保留連字號和字母數字）
    keep = re.sub(r'[^\w\s\-\u00C0-\u024F]', '', keep)
    # 刪除冠詞
    keep = re.sub(r'\b(a|an|the|of|in|and|for|with|after|during|versus|vs|at)\b', '',
                  keep, flags=re.IGNORECASE)
    # 空白 → 底線
    keep = re.sub(r'\s+', '_', keep.strip())
    # 截斷
    if len(keep) > max_len:
        keep = keep[:max_len].rstrip('_')
    return keep


def propose_name(pdf_path: Path) -> dict:
    """
    綜合所有來源，提議新檔名。
    回傳: {"original": ..., "proposed": ..., "year": ..., "author": ..., "title": ..., "method": ..., "skip": bool}
    """
    fname = pdf_path.name

    # 判斷是否略過
    if any(kw in fname for kw in SKIP_KEYWORDS):
        return {"original": fname, "proposed": fname, "skip": True, "reason": "使用者筆記/整理文件"}

    # Step 1: mdls
    md = parse_mdls(str(pdf_path))
    title = md.get("title")
    year = md.get("year")
    author = None
    method = "mdls"

    # Step 2: pypdf fallback
    if not title:
        pp = parse_pypdf_page0(str(pdf_path))
        title = pp.get("title")
        year = year or pp.get("year")
        author = pp.get("author")
        method = "pypdf"

    # Step 3: 從檔名推斷
    fn = parse_filename(fname)
    year = year or fn.get("year")
    if not author:
        author = fn.get("author")
    if not title and fn.get("title_hint"):
        title = fn.get("title_hint")
        method = "filename"

    if not year or not title:
        return {"original": fname, "proposed": fname, "skip": True,
                "reason": f"無法取得 {'year' if not year else 'title'}"}

    # 組合新檔名
    author_part = author or "Unknown"
    title_slug = slugify_title(title)
    new_name = f"{year}_{author_part}_{title_slug}.pdf"

    return {
        "original": fname,
        "proposed": new_name,
        "year": year,
        "author": author_part,
        "title": title[:80],
        "method": method,
        "skip": False,
    }


# ── Main ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("用法: python3 extract_metadata.py <目錄路徑> [--no-recurse]")
        sys.exit(1)

    base_dir = Path(sys.argv[1]).expanduser().resolve()
    recurse = "--no-recurse" not in sys.argv

    if recurse:
        pdf_files = sorted(base_dir.rglob("*.pdf"))
    else:
        pdf_files = sorted(base_dir.glob("*.pdf"))

    results = []
    skipped = []

    for pdf in pdf_files:
        info = propose_name(pdf)
        rel = pdf.relative_to(base_dir)
        info["relative_path"] = str(rel)
        if info["skip"]:
            skipped.append(info)
        else:
            results.append(info)

    # 偵測重複建議（相同 proposed name → 不同原始檔）
    seen = {}
    for r in results:
        key = r["proposed"].lower()
        if key in seen:
            r["duplicate_of"] = seen[key]["original"]
            seen[key]["has_duplicate"] = True
        else:
            seen[key] = r

    # 輸出
    print("\n" + "=" * 70)
    print("📄 建議重命名清單")
    print("=" * 70)
    for r in results:
        dup_note = " ⚠ DUPLICATE" if r.get("duplicate_of") or r.get("has_duplicate") else ""
        print(f"\n{'[' + r['relative_path'] + ']':}")
        print(f"  舊: {r['original']}")
        print(f"  新: {r['proposed']}{dup_note}")
        print(f"  來源: {r.get('method', '?')} | {r.get('year', '?')} | {r.get('author', '?')}")

    print("\n" + "=" * 70)
    print(f"⚠ 略過 ({len(skipped)} 個)")
    print("=" * 70)
    for s in skipped:
        print(f"  {s['relative_path']}: {s.get('reason', '未知原因')}")

    # 輸出 JSON 供 rename 腳本使用
    output = {"renames": results, "skipped": skipped}
    out_path = base_dir / "_lit_rename_proposal.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 對照表已儲存至: {out_path}")
    print("確認後執行: python3 rename_pdfs.py <目錄> _lit_rename_proposal.json")


if __name__ == "__main__":
    main()
