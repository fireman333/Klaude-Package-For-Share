"""
Data Dictionary Generator
Generates a codebook-style CSV matching TTM Dictionary.csv format (4 columns):
  類別, name, label, values

Handles two input structures:
  - Single-row header: row 1 = column names, row 2+ = data
  - Two-row header:    row 1 = sparse category labels, row 2 = column names, row 3+ = data
    (auto-detected; category labels are forward-filled to populate 類別 column)
"""

import argparse
import sys
import os
import warnings
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)


# ── Header Structure Detection ─────────────────────────────────────────────────

def detect_header_rows(raw_df: pd.DataFrame):
    """
    Detect whether the file has a two-row header (sparse category + variable names).

    Returns:
        (header_row_index, category_series_or_None)
        header_row_index: 0-based index of the row containing column names
        category_series:  pd.Series mapping column positions to category labels,
                          or None if single-row header
    """
    if len(raw_df) < 2:
        return 0, None

    row0 = raw_df.iloc[0]
    row1 = raw_df.iloc[1]

    n_cols = len(raw_df.columns)
    row0_filled = row0.notna().sum() / n_cols
    row1_filled = row1.notna().sum() / n_cols

    # Two-row header: row 0 is sparse (< 35%) and row 1 is dense (> 65%)
    if row0_filled < 0.35 and row1_filled > 0.65:
        # Forward-fill row 0 to get category per column
        category_series = row0.copy()
        category_series = category_series.where(category_series.notna()).ffill()
        return 1, category_series

    return 0, None


def read_csv_with_structure(input_file: str):
    """Read a CSV, auto-detecting single vs two-row headers."""
    # Read raw (no header interpretation) to inspect structure
    raw = pd.read_csv(input_file, header=None, encoding='utf-8-sig',
                      low_memory=False, dtype=str)

    header_row_idx, category_series = detect_header_rows(raw)

    # Re-read with the correct header row
    df = pd.read_csv(input_file, header=header_row_idx, encoding='utf-8-sig',
                     low_memory=False)

    # Build column → category mapping
    col_to_category = {}
    if category_series is not None:
        for col_idx, col_name in enumerate(df.columns):
            cat = category_series.iloc[col_idx] if col_idx < len(category_series) else ""
            col_to_category[col_name] = str(cat) if pd.notna(cat) else ""
    else:
        for col_name in df.columns:
            col_to_category[col_name] = ""

    return df, col_to_category


def read_excel_with_structure(input_file: str, sheet_name=None):
    """Read an Excel file, detecting structure and available sheets."""
    xl = pd.ExcelFile(input_file)
    all_sheets = xl.sheet_names

    # Filter valid sheets
    valid_sheets = []
    for name in all_sheets:
        try:
            tmp = xl.parse(name, nrows=5, header=None)
            if tmp.shape[1] >= 2 and tmp.shape[0] >= 1:
                valid_sheets.append(name)
        except Exception:
            pass

    if not valid_sheets:
        print(f"ERROR: No valid sheets found in {input_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Available sheets: {valid_sheets}")

    if sheet_name is not None:
        if sheet_name not in all_sheets:
            print(f"ERROR: Sheet '{sheet_name}' not found. Available: {all_sheets}",
                  file=sys.stderr)
            sys.exit(1)
        chosen = sheet_name
    else:
        chosen = valid_sheets[0]
        print(f"Using sheet: '{chosen}' (first valid sheet)")

    # Read raw to detect structure
    raw = xl.parse(chosen, header=None, dtype=str)
    header_row_idx, category_series = detect_header_rows(raw)

    df = xl.parse(chosen, header=header_row_idx)

    col_to_category = {}
    if category_series is not None:
        for col_idx, col_name in enumerate(df.columns):
            cat = category_series.iloc[col_idx] if col_idx < len(category_series) else ""
            col_to_category[col_name] = str(cat) if pd.notna(cat) else ""
    else:
        for col_name in df.columns:
            col_to_category[col_name] = ""

    return df, col_to_category, valid_sheets


# ── Type Detection ─────────────────────────────────────────────────────────────

def is_date_column(series: pd.Series) -> bool:
    """Return True if ≥80% of non-null values parse as dates."""
    s = series.dropna()
    if len(s) == 0:
        return False
    if pd.api.types.is_numeric_dtype(series):
        return False
    try:
        parsed = pd.to_datetime(s, errors='coerce', format='mixed')
        return parsed.notna().sum() / len(s) >= 0.80
    except Exception:
        return False


def detect_type(series: pd.Series) -> str:
    """Return 'date', 'categorical', or 'continuous'."""
    if is_date_column(series):
        return 'date'

    s = series.dropna()
    n_total = len(s)
    if n_total == 0:
        return 'continuous'

    n_unique = s.nunique()

    if pd.api.types.is_numeric_dtype(series):
        if n_unique <= 20 and (n_unique / n_total) <= 0.10:
            return 'categorical'
        return 'continuous'
    else:
        if n_unique <= 20:
            return 'categorical'
        return 'continuous'


# ── Values Field Formatter ──────────────────────────────────────────────────────

def format_values(series: pd.Series) -> str:
    """Format unique values as {v1}{v2}... for categorical columns."""
    s = series.dropna()

    try:
        unique_vals = sorted(s.unique())
    except TypeError:
        unique_vals = sorted(s.unique(), key=str)

    parts = []
    for v in unique_vals:
        if pd.api.types.is_numeric_dtype(series):
            if isinstance(v, float) and v == int(v):
                parts.append(f"{{{int(v)}}}")
            else:
                parts.append(f"{{{v}}}")
        else:
            parts.append(f"{{{v}}}")

    return "".join(parts)


# ── Label Derivation ───────────────────────────────────────────────────────────

def derive_label(col_name: str) -> str:
    """Replace underscores with spaces to create a human-readable label."""
    return str(col_name).replace("_", " ")


# ── 類別 Sparse Formatter ──────────────────────────────────────────────────────

def build_category_column(col_names, col_to_category: dict) -> list:
    """
    Return sparse category values: only fill in the first column of each group,
    leave the rest blank (matching TTM Dictionary.csv style).
    """
    result = []
    last_cat = None
    for col in col_names:
        cat = col_to_category.get(str(col), "")
        if cat and cat != last_cat:
            result.append(cat)
            last_cat = cat
        else:
            result.append("")
    return result


# ── Core Processing ────────────────────────────────────────────────────────────

def process_dataframe(df: pd.DataFrame, col_to_category: dict) -> pd.DataFrame:
    """Build the data dictionary rows from a dataframe."""
    category_col = build_category_column(df.columns, col_to_category)

    rows = []
    for i, col in enumerate(df.columns):
        series = df[col]
        col_type = detect_type(series)

        values_str = "None" if col_type in ('date', 'continuous') else format_values(series)

        rows.append({
            "類別": category_col[i],
            "name": col,
            "label": derive_label(col),
            "values": values_str,
        })

    return pd.DataFrame(rows, columns=["類別", "name", "label", "values"])


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate a codebook-style Data Dictionary CSV."
    )
    parser.add_argument("input_file", help="Path to input .xlsx, .xls, or .csv file")
    parser.add_argument("output_csv", help="Path for the output Data Dictionary CSV")
    parser.add_argument("--sheet", default=None,
                        help="Sheet name to process (Excel only; default: first sheet)")
    args = parser.parse_args()

    print(f"Reading: {args.input_file}")
    ext = os.path.splitext(args.input_file)[1].lower()

    if ext == '.csv':
        df, col_to_category = read_csv_with_structure(args.input_file)
        sheet_list = None
    elif ext in ('.xlsx', '.xls'):
        df, col_to_category, sheet_list = read_excel_with_structure(
            args.input_file, sheet_name=args.sheet
        )
    else:
        print(f"ERROR: Unsupported file type '{ext}'. Use .csv, .xlsx, or .xls",
              file=sys.stderr)
        sys.exit(1)

    if df.empty:
        print("ERROR: Input data is empty.", file=sys.stderr)
        sys.exit(1)

    print(f"Columns found: {len(df.columns)}, Rows: {len(df)}")

    has_categories = any(v for v in col_to_category.values())
    if has_categories:
        print("Two-row header detected: category labels auto-populated in 類別 column.")

    dict_df = process_dataframe(df, col_to_category)

    n_with_values = (dict_df["values"] != "None").sum()
    n_none = (dict_df["values"] == "None").sum()

    os.makedirs(os.path.dirname(os.path.abspath(args.output_csv)), exist_ok=True)
    dict_df.to_csv(args.output_csv, index=False, encoding='utf-8-sig')

    print(f"\n✓ Data Dictionary saved to: {args.output_csv}")
    print(f"  Total variables  : {len(dict_df)}")
    print(f"  With values      : {n_with_values}")
    print(f"  Continuous/Date  : {n_none}")
    if sheet_list:
        print(f"\n  Other sheets available: {sheet_list}")
        print("  Re-run with --sheet 'SheetName' to process a different sheet.")
    print("\n  Next steps:")
    if not has_categories:
        print("  1. Fill in the '類別' column with category/section groupings")
    print("  2. Edit 'label' column for Chinese labels or corrections")
    print("  3. For numeric codes in 'values', add labels: {0}{1} → {0, No}{1, Yes}")


if __name__ == "__main__":
    main()
