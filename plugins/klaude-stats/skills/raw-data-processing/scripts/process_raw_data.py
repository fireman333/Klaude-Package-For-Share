#!/usr/bin/env python3
"""
Raw Data Processing Script

Two modes:
  --scan INPUT_FILE --scan-output SCAN_REPORT.json
      Scans the workbook, detects headers, analyzes columns, outputs JSON report.

  CONFIG.json
      Processes data according to the config, outputs cleansed data + data dictionary.
"""

import argparse
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime

import numpy as np
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
import pandas as pd


# ──────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────

SKIP_MARKERS = ["return to toc", "population:"]
DATE_PATTERNS = [
    re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$"),
    re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$"),
    re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$"),
    re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$"),
]

HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF", size=10)
DATA_FONT = Font(name="Arial", size=10)
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)


# ══════════════════════════════════════════════
#  SCAN MODE
# ══════════════════════════════════════════════


def scan_workbook(input_path):
    """Scan the workbook and return a JSON-serializable report."""
    wb = openpyxl.load_workbook(input_path, read_only=True, data_only=True)
    report = {
        "input_file": os.path.abspath(input_path),
        "total_sheets": len(wb.sheetnames),
        "sheet_names": wb.sheetnames,
        "sheets": {},
    }

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        sheet_report = _scan_sheet(ws, sheet_name)
        report["sheets"][sheet_name] = sheet_report

    wb.close()
    return report


def _scan_sheet(ws, sheet_name):
    """Scan a single sheet and return its report."""
    # Read first 15 rows to detect structure
    top_rows = []
    for i, row in enumerate(ws.iter_rows(max_row=15, values_only=True)):
        top_rows.append(list(row))
        if i >= 14:
            break

    if not top_rows:
        return {"is_data_sheet": False, "reason": "Empty sheet"}

    # Detect max columns (non-None in any row)
    max_cols = 0
    for row in top_rows:
        non_none = sum(1 for v in row if v is not None)
        max_cols = max(max_cols, non_none)

    if max_cols < 2:
        return {"is_data_sheet": False, "reason": "Fewer than 2 columns detected (likely cover/TOC)"}

    # Detect header row
    header_row, data_start_row = _detect_header_row(top_rows, max_cols)

    if header_row is None:
        return {"is_data_sheet": False, "reason": "Could not detect header row"}

    # Extract metadata
    metadata = _extract_metadata(top_rows, header_row)

    # Get headers
    headers_raw = top_rows[header_row - 1]  # Convert 1-indexed to 0-indexed
    total_cols = len(headers_raw)

    # Handle split headers: check if a row above has section labels
    section_labels = {}
    if header_row >= 2:
        prev_row = top_rows[header_row - 2]
        non_none_prev = [(i, v) for i, v in enumerate(prev_row) if v is not None]
        # If previous row has 1-3 values and they look like section labels (not data)
        if 1 <= len(non_none_prev) <= 3:
            for idx, val in non_none_prev:
                if isinstance(val, str) and len(val) > 3:
                    section_labels[str(idx)] = str(val)

    # Read data rows for column analysis (up to 500 rows)
    all_data_rows = []
    for i, row in enumerate(ws.iter_rows(min_row=data_start_row, max_row=data_start_row + 499, values_only=True)):
        all_data_rows.append(list(row))

    # Analyze each column
    columns = []
    duplicate_headers = []
    seen_names = {}

    for col_idx in range(total_cols):
        raw_name = headers_raw[col_idx]
        if raw_name is None:
            continue

        name = str(raw_name).strip().replace("\xa0", " ").strip()
        if not name:
            continue

        # Track duplicates
        if name in seen_names:
            duplicate_headers.append(name)
            seen_names[name] += 1
        else:
            seen_names[name] = 1

        # Collect values
        values = []
        for data_row in all_data_rows:
            if col_idx < len(data_row):
                v = data_row[col_idx]
                if v is not None and str(v).strip() != "":
                    values.append(v)

        unique_vals = list(OrderedDict.fromkeys(str(v) for v in values))[:20]
        suggested_type = _infer_variable_type(values, name)

        # Check for Chinese characters
        has_chinese = bool(re.search(r"[\u4e00-\u9fff]", name))

        columns.append({
            "index": col_idx,
            "original_name": name,
            "non_null_count": len(values),
            "total_rows": len(all_data_rows),
            "sample_values": unique_vals,
            "unique_count": len(set(str(v) for v in values)),
            "suggested_type": suggested_type,
            "has_chinese": has_chinese,
        })

    return {
        "is_data_sheet": True,
        "detected_header_row": header_row,
        "detected_data_start_row": data_start_row,
        "metadata": metadata,
        "section_labels": section_labels if section_labels else None,
        "row_count": len(all_data_rows),
        "column_count": len(columns),
        "columns": columns,
        "duplicate_headers": list(set(duplicate_headers)),
        "warnings": _generate_warnings(columns, duplicate_headers),
    }


def _detect_header_row(top_rows, max_cols):
    """
    Detect which row contains column headers.
    Returns (header_row, data_start_row) as 1-indexed values.
    """
    for row_idx, row in enumerate(top_rows):
        # Count non-empty cells
        non_empty = [(i, v) for i, v in enumerate(row) if v is not None]
        non_empty_count = len(non_empty)

        if non_empty_count == 0:
            continue

        # Skip single-cell metadata rows
        if non_empty_count == 1:
            val_str = str(non_empty[0][1]).strip().lower()
            if any(marker in val_str for marker in SKIP_MARKERS):
                continue
            # Single-cell rows with short text are likely titles
            if len(val_str) > 5:
                continue
            continue

        # Skip rows where first cell matches skip markers
        first_val = str(non_empty[0][1]).strip().lower() if non_empty else ""
        if any(marker in first_val for marker in SKIP_MARKERS):
            continue

        # Check fill ratio
        fill_ratio = non_empty_count / max(max_cols, 1)

        if fill_ratio >= 0.4:
            # Check if values look like headers (strings, not pure numbers)
            string_count = sum(1 for _, v in non_empty if isinstance(v, str))
            if string_count >= non_empty_count * 0.5:
                # Verify next row has data (not another header row)
                if row_idx + 1 < len(top_rows):
                    next_row = top_rows[row_idx + 1]
                    next_non_empty = sum(1 for v in next_row if v is not None)
                    if next_non_empty >= 2:
                        return (row_idx + 1, row_idx + 2)  # 1-indexed
                else:
                    return (row_idx + 1, row_idx + 2)

    return (None, None)


def _extract_metadata(top_rows, header_row):
    """Extract metadata text from rows above the header."""
    metadata = {"toc_marker": None, "title": None, "population": None}
    for row_idx in range(header_row - 1):  # 0-indexed iteration up to header
        row = top_rows[row_idx]
        non_empty = [v for v in row if v is not None]
        if not non_empty:
            continue
        text = str(non_empty[0]).strip()
        lower = text.lower()
        if "return to toc" in lower:
            metadata["toc_marker"] = text
        elif "population:" in lower:
            metadata["population"] = text
        elif metadata["title"] is None and len(text) > 3:
            metadata["title"] = text
    return metadata


def _infer_variable_type(values, col_name):
    """Infer the variable type from values and column name."""
    if not values:
        return "text"

    col_lower = col_name.lower()

    # Check for ID columns
    if any(kw in col_lower for kw in ["subject no", "center no", "subject_no", "center_no"]):
        return "id"

    # Separate strings and numbers
    str_values = []
    num_values = []
    date_values = []

    for v in values:
        if isinstance(v, datetime):
            date_values.append(v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            num_values.append(v)
        else:
            s = str(v).strip()
            if s == "":
                continue
            # Check if it's a date string
            if any(p.match(s) for p in DATE_PATTERNS):
                date_values.append(s)
            else:
                try:
                    num_values.append(float(s))
                except ValueError:
                    str_values.append(s)

    # Date detection
    if "date" in col_lower or "日期" in col_lower:
        return "date"
    if date_values and len(date_values) > len(str_values) and len(date_values) > len(num_values):
        return "date"

    # Pure string values
    if str_values and not num_values:
        unique_strs = set(s.strip() for s in str_values)
        if len(unique_strs) == 2:
            return "binary"
        elif len(unique_strs) <= 10:
            return "categorical"
        else:
            return "text"

    # Pure numeric values
    if num_values and not str_values:
        unique_nums = set(num_values)
        # Binary check
        if unique_nums <= {0, 1, 0.0, 1.0}:
            return "binary"
        # All integers with few unique values
        all_int = all(float(n).is_integer() for n in num_values if not np.isnan(n))
        if all_int and len(unique_nums) <= 5:
            return "categorical"
        return "continuous"

    # Mixed: if mostly strings with a few numbers, treat as categorical
    if str_values and num_values:
        all_unique = set(str(v).strip() for v in values if v is not None and str(v).strip())
        if len(all_unique) == 2:
            return "binary"
        elif len(all_unique) <= 10:
            return "categorical"
        return "text"

    return "text"


def _generate_warnings(columns, duplicate_headers):
    """Generate warning messages for the scan report."""
    warnings = []
    if duplicate_headers:
        warnings.append(f"Duplicate column names found: {duplicate_headers}")
    for col in columns:
        if col["non_null_count"] == 0:
            warnings.append(f"Column '{col['original_name']}' has no data")
        if col["has_chinese"]:
            warnings.append(f"Column '{col['original_name']}' contains Chinese characters")
    return warnings


# ══════════════════════════════════════════════
#  PROCESSING MODE
# ══════════════════════════════════════════════


def load_config(config_path):
    """Load and validate the JSON config."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    required = ["input_file", "output_data_file", "output_dict_file", "sheets"]
    for key in required:
        if key not in config:
            print(f"ERROR: Missing required config key: {key}", file=sys.stderr)
            sys.exit(1)

    return config


def process_workbook(config):
    """Main processing: read raw data, apply transformations, write outputs."""
    input_path = config["input_file"]
    skip_sheets = set(config.get("skip_sheets", []))

    wb = openpyxl.load_workbook(input_path, read_only=True, data_only=True)
    sheet_results = OrderedDict()  # sheet_name -> DataFrame
    sheet_stats = OrderedDict()    # sheet_name -> stats dict

    for sheet_name, sheet_config in config["sheets"].items():
        if sheet_name in skip_sheets:
            continue
        if sheet_name not in wb.sheetnames:
            print(f"WARNING: Sheet '{sheet_name}' not found in workbook, skipping.")
            continue

        ws = wb[sheet_name]
        df, stats = _process_sheet(ws, sheet_name, sheet_config)
        sheet_results[sheet_name] = df
        sheet_stats[sheet_name] = stats
        print(f"  Processed: {sheet_name} ({stats['rows']} rows, {stats['cols']} columns)")

    wb.close()

    # Write outputs
    _write_cleansed_excel(sheet_results, config["output_data_file"])
    _write_data_dictionary(config, sheet_stats, config["output_dict_file"])

    return sheet_stats


def _process_sheet(ws, sheet_name, sheet_config):
    """Process a single sheet according to its config."""
    header_row = sheet_config["header_row"]
    data_start_row = sheet_config["data_start_row"]
    col_configs = sheet_config["columns"]

    # Read all rows
    all_rows = []
    headers_raw = None
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if i == header_row:
            headers_raw = [_clean_header_name(v) for v in row]
        elif i >= data_start_row:
            all_rows.append(list(row))

    if headers_raw is None:
        return pd.DataFrame(), {"rows": 0, "cols": 0, "warnings": ["Header row not found"]}

    # Build DataFrame
    df = pd.DataFrame(all_rows, columns=headers_raw[:len(all_rows[0])] if all_rows else headers_raw)

    # Track stats
    renamed = 0
    encoded = 0
    warnings = []

    # Process columns according to config
    new_columns = OrderedDict()
    for orig_name, col_config in col_configs.items():
        # Find matching column (handle whitespace differences)
        matched_col = _find_column(df, orig_name)
        if matched_col is None:
            warnings.append(f"Column '{orig_name}' not found in sheet '{sheet_name}'")
            continue

        new_name = col_config["new_name"]
        col_type = col_config.get("type", "text")
        encoding = col_config.get("encoding")

        series = df[matched_col].copy()

        # Apply encoding
        if encoding and col_type in ("binary", "categorical"):
            series = _encode_column(series, encoding)
            encoded += 1

        # Standardize dates
        if col_type == "date":
            series = _standardize_dates(series)

        # Convert continuous to numeric
        if col_type == "continuous":
            series = pd.to_numeric(series, errors="coerce")

        new_columns[new_name] = series
        if new_name != orig_name:
            renamed += 1

    result_df = pd.DataFrame(new_columns)

    stats = {
        "rows": len(result_df),
        "cols": len(result_df.columns),
        "renamed": renamed,
        "encoded": encoded,
        "warnings": warnings,
        "description": sheet_config.get("description", ""),
        "metadata_text": sheet_config.get("metadata_text", ""),
    }

    return result_df, stats


def _clean_header_name(value):
    """Clean a raw header value for matching purposes."""
    if value is None:
        return None
    s = str(value).strip().replace("\xa0", " ").strip()
    return s if s else None


def _find_column(df, orig_name):
    """Find a column in the DataFrame, handling whitespace/encoding differences."""
    # Exact match
    if orig_name in df.columns:
        return orig_name

    # Normalized match
    norm_orig = orig_name.strip().replace("\xa0", " ").strip()
    for col in df.columns:
        if col is None:
            continue
        norm_col = str(col).strip().replace("\xa0", " ").strip()
        if norm_col == norm_orig:
            return col

    # Fuzzy match: ignore all whitespace differences
    norm_orig_nospace = re.sub(r"\s+", "", norm_orig)
    for col in df.columns:
        if col is None:
            continue
        norm_col_nospace = re.sub(r"\s+", "", str(col))
        if norm_col_nospace == norm_orig_nospace:
            return col

    return None


def _encode_column(series, encoding):
    """Apply encoding map to a series."""
    # Build normalized encoding map
    norm_map = {}
    for key, val in encoding.items():
        norm_map[str(key).strip().lower()] = val

    def encode_val(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return np.nan
        s = str(v).strip()
        if s == "" or s.upper() == "NOT DONE":
            return np.nan
        # Try exact match first
        if s in encoding:
            return encoding[s]
        # Try normalized match
        s_lower = s.lower()
        if s_lower in norm_map:
            return norm_map[s_lower]
        # If the value is already a number matching an encoded value, keep it
        try:
            num = float(s)
            if num in encoding.values():
                return num
            # If it's a number not in the encoding, return as-is
            return num
        except (ValueError, TypeError):
            pass
        return np.nan

    return series.apply(encode_val)


def _standardize_dates(series):
    """Standardize date values to YYYY-MM-DD string format."""
    def parse_date(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d")
        s = str(v).strip()
        if s == "" or s.upper() == "NOT DONE":
            return None
        # Try common formats
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"]:
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        # Try pandas
        try:
            return pd.to_datetime(s).strftime("%Y-%m-%d")
        except Exception:
            return s  # Return as-is if unparseable

    return series.apply(parse_date)


# ──────────────────────────────────────────────
#  OUTPUT: Cleansed Data Excel
# ──────────────────────────────────────────────


def _write_cleansed_excel(sheet_data, output_path):
    """Write cleansed data to Excel with formatting."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for sheet_name, df in sheet_data.items():
        ws = wb.create_sheet(title=sheet_name[:31])  # Excel 31-char limit

        # Write headers
        for col_idx, col_name in enumerate(df.columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Write data
        for row_idx, (_, row) in enumerate(df.iterrows(), start=2):
            for col_idx, val in enumerate(row, start=1):
                if isinstance(val, float) and np.isnan(val):
                    cell = ws.cell(row=row_idx, column=col_idx, value=None)
                else:
                    cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = DATA_FONT
                cell.border = THIN_BORDER

        # Auto-width columns
        for col_idx in range(1, len(df.columns) + 1):
            col_letter = get_column_letter(col_idx)
            max_len = len(str(df.columns[col_idx - 1]))
            for row_idx in range(2, min(52, len(df) + 2)):  # Sample first 50 rows
                cell_val = ws.cell(row=row_idx, column=col_idx).value
                if cell_val:
                    max_len = max(max_len, len(str(cell_val)))
            ws.column_dimensions[col_letter].width = min(max_len + 2, 40)

        # Freeze top row
        ws.freeze_panes = "A2"

    wb.save(output_path)
    print(f"Cleansed data saved to: {output_path}")


# ──────────────────────────────────────────────
#  OUTPUT: Data Dictionary Excel
# ──────────────────────────────────────────────


def _write_data_dictionary(config, sheet_stats, output_path):
    """Write data dictionary Excel with Summary, Column_Mapping, Codes, and Units sheets."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # ── Sheet 1: Summary ──
    ws_summary = wb.create_sheet(title="Summary")
    summary_headers = ["Sheet Name", "Description", "Population", "Row Count", "Column Count"]
    for col_idx, h in enumerate(summary_headers, start=1):
        cell = ws_summary.cell(row=1, column=col_idx, value=h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = THIN_BORDER

    row = 2
    for sheet_name, stats in sheet_stats.items():
        ws_summary.cell(row=row, column=1, value=sheet_name).border = THIN_BORDER
        ws_summary.cell(row=row, column=2, value=stats.get("description", "")).border = THIN_BORDER
        ws_summary.cell(row=row, column=3, value=stats.get("metadata_text", "")).border = THIN_BORDER
        ws_summary.cell(row=row, column=4, value=stats.get("rows", 0)).border = THIN_BORDER
        ws_summary.cell(row=row, column=5, value=stats.get("cols", 0)).border = THIN_BORDER
        row += 1

    _auto_width(ws_summary)

    # ── Sheet 2: Column_Mapping ──
    ws_mapping = wb.create_sheet(title="Column_Mapping")
    map_headers = ["Sheet", "Original_Name", "New_Name", "Type", "Encoding", "Description"]
    for col_idx, h in enumerate(map_headers, start=1):
        cell = ws_mapping.cell(row=1, column=col_idx, value=h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = THIN_BORDER

    row = 2
    for sheet_name, sheet_config in config["sheets"].items():
        if sheet_name in config.get("skip_sheets", []):
            continue
        for orig_name, col_config in sheet_config["columns"].items():
            ws_mapping.cell(row=row, column=1, value=sheet_name).border = THIN_BORDER
            ws_mapping.cell(row=row, column=2, value=orig_name).border = THIN_BORDER
            ws_mapping.cell(row=row, column=3, value=col_config["new_name"]).border = THIN_BORDER
            ws_mapping.cell(row=row, column=4, value=col_config.get("type", "")).border = THIN_BORDER

            # Format encoding
            enc = col_config.get("encoding")
            if enc:
                enc_str = ", ".join(f"{v}={k}" for k, v in enc.items())
            else:
                enc_str = ""
            ws_mapping.cell(row=row, column=5, value=enc_str).border = THIN_BORDER
            ws_mapping.cell(row=row, column=6, value=col_config.get("description", "")).border = THIN_BORDER
            row += 1

    _auto_width(ws_mapping)

    # ── Sheet 3: Codes (compact encoding reference) ──
    ws_codes = wb.create_sheet(title="Codes")
    _write_codes_sheet(ws_codes, config)

    # ── Sheet 4: Units (if any unit-related info) ──
    units_data = _extract_units(config)
    if units_data:
        ws_units = wb.create_sheet(title="Units")
        unit_headers = ["Variable", "Unit"]
        for col_idx, h in enumerate(unit_headers, start=1):
            cell = ws_units.cell(row=1, column=col_idx, value=h)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.border = THIN_BORDER
        for row_idx, (var_name, unit) in enumerate(units_data, start=2):
            ws_units.cell(row=row_idx, column=1, value=var_name).border = THIN_BORDER
            ws_units.cell(row=row_idx, column=2, value=unit).border = THIN_BORDER
        _auto_width(ws_units)

    wb.save(output_path)
    print(f"Data dictionary saved to: {output_path}")


def _write_codes_sheet(ws, config):
    """Write compact codes sheet grouped by variable."""
    # Collect all encoded variables
    encoded_vars = OrderedDict()
    for sheet_name, sheet_config in config["sheets"].items():
        if sheet_name in config.get("skip_sheets", []):
            continue
        for orig_name, col_config in sheet_config["columns"].items():
            enc = col_config.get("encoding")
            if enc:
                var_name = col_config["new_name"]
                if var_name not in encoded_vars:
                    encoded_vars[var_name] = {
                        "type": col_config.get("type", ""),
                        "description": col_config.get("description", ""),
                        "encoding": enc,
                    }

    if not encoded_vars:
        ws.cell(row=1, column=1, value="No encoded variables")
        return

    # Write in compact grouped format
    row = 1
    col_offset = 0
    items_in_column = 0
    max_items_per_column = 40  # Start a new column group after this many rows

    for var_name, info in encoded_vars.items():
        if items_in_column > max_items_per_column:
            col_offset += 3
            row = 1
            items_in_column = 0

        # Variable header
        cell = ws.cell(row=row, column=1 + col_offset, value=var_name)
        cell.font = Font(name="Arial", bold=True, size=10)
        row += 1
        items_in_column += 1

        # Encoding entries (sorted by value)
        sorted_enc = sorted(info["encoding"].items(), key=lambda x: x[1])
        for label, code in sorted_enc:
            ws.cell(row=row, column=1 + col_offset, value=label).font = DATA_FONT
            ws.cell(row=row, column=2 + col_offset, value=code).font = DATA_FONT
            row += 1
            items_in_column += 1

        # Blank row between variables
        row += 1
        items_in_column += 1

    _auto_width(ws)


def _extract_units(config):
    """Extract unit information from column descriptions or names."""
    units = []
    for sheet_name, sheet_config in config["sheets"].items():
        if sheet_name in config.get("skip_sheets", []):
            continue
        for orig_name, col_config in sheet_config["columns"].items():
            desc = col_config.get("description", "")
            # Check if description mentions units
            unit_match = re.search(r"\(([A-Z][A-Z/^0-9.\s]+)\)", desc)
            if unit_match:
                units.append((col_config["new_name"], unit_match.group(1)))
            # Check if the original name is a unit column
            if "unit" in orig_name.lower():
                units.append((orig_name, desc))
    return units


def _auto_width(ws):
    """Auto-adjust column widths."""
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_len + 2, 50)


# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="Raw Data Processing Tool")
    parser.add_argument("config", nargs="?", help="Path to JSON config file (processing mode)")
    parser.add_argument("--scan", metavar="INPUT_FILE", help="Input file to scan (scan mode)")
    parser.add_argument("--scan-output", metavar="OUTPUT_FILE", default="/tmp/raw_data_scan.json",
                        help="Output path for scan report JSON (default: /tmp/raw_data_scan.json)")

    args = parser.parse_args()

    if args.scan:
        # ── SCAN MODE ──
        print(f"Scanning: {args.scan}")
        if not os.path.exists(args.scan):
            print(f"ERROR: File not found: {args.scan}", file=sys.stderr)
            sys.exit(1)

        report = scan_workbook(args.scan)

        with open(args.scan_output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)

        print(f"Scan report saved to: {args.scan_output}")
        print(f"\nSummary:")
        print(f"  Total sheets: {report['total_sheets']}")
        data_sheets = [name for name, info in report['sheets'].items() if info.get('is_data_sheet')]
        skip_sheets = [name for name, info in report['sheets'].items() if not info.get('is_data_sheet')]
        print(f"  Data sheets ({len(data_sheets)}): {data_sheets}")
        print(f"  Non-data sheets ({len(skip_sheets)}): {skip_sheets}")

        for name in data_sheets:
            info = report['sheets'][name]
            print(f"\n  [{name}]")
            print(f"    Header row: {info['detected_header_row']}, Data starts: {info['detected_data_start_row']}")
            print(f"    Rows: {info['row_count']}, Columns: {info['column_count']}")
            if info.get("duplicate_headers"):
                print(f"    ⚠ Duplicate headers: {info['duplicate_headers']}")
            if info.get("warnings"):
                for w in info["warnings"]:
                    print(f"    ⚠ {w}")

    elif args.config:
        # ── PROCESSING MODE ──
        print(f"Loading config: {args.config}")
        config = load_config(args.config)

        print(f"Processing: {config['input_file']}")
        stats = process_workbook(config)

        print(f"\n{'='*50}")
        print(f"Processing complete!")
        print(f"  Cleansed data: {config['output_data_file']}")
        print(f"  Data dictionary: {config['output_dict_file']}")
        print(f"  Sheets processed: {len(stats)}")
        total_rows = sum(s['rows'] for s in stats.values())
        total_cols = sum(s['cols'] for s in stats.values())
        total_renamed = sum(s['renamed'] for s in stats.values())
        total_encoded = sum(s['encoded'] for s in stats.values())
        print(f"  Total rows: {total_rows}")
        print(f"  Total columns: {total_cols}")
        print(f"  Columns renamed: {total_renamed}")
        print(f"  Columns encoded: {total_encoded}")

        # Print warnings
        all_warnings = []
        for sn, s in stats.items():
            for w in s.get("warnings", []):
                all_warnings.append(f"  [{sn}] {w}")
        if all_warnings:
            print(f"\nWarnings:")
            for w in all_warnings:
                print(w)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
