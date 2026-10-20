#!/usr/bin/env python3
"""
CONSORT-Style Patient Selection Flowchart Generator
Generates a publication-ready flowchart showing sequential exclusion steps
with automatic calculation of excluded and remaining patient counts.

Outputs: Flowchart image (.png) and Excel summary (.xlsx).

Usage:
    python flowchart.py config.json              # Full generation
    python flowchart.py config.json --preview     # Preview counts only
"""

import sys
import json
import os
import operator
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    config.setdefault('filters', [])
    config.setdefault('derived_variables', [])
    config.setdefault('group_split', None)

    # Plot settings defaults
    ps = config.setdefault('plot_settings', {})
    ps.setdefault('figsize', [10, 14])
    ps.setdefault('dpi', 300)
    ps.setdefault('main_box_width', 0.50)
    ps.setdefault('main_box_color', '#D6E4F0')
    ps.setdefault('exclude_box_color', '#FADBD8')
    ps.setdefault('final_box_color', '#D5F5E3')
    ps.setdefault('group_box_color', '#D6E4F0')
    ps.setdefault('font_size', 10)
    ps.setdefault('title_font_size', 11)
    ps.setdefault('arrow_color', '#333333')
    ps.setdefault('border_color', '#2C3E50')

    return config


# ═══════════════════════════════════════════════════════════════════════════════
# Data Loading & Preprocessing
# ═══════════════════════════════════════════════════════════════════════════════

OPS = {
    '==': operator.eq, '!=': operator.ne,
    '>': operator.gt, '>=': operator.ge,
    '<': operator.lt, '<=': operator.le,
}


def load_data(config):
    path = config['data_file']
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.xlsx', '.xls'):
        df = pd.read_excel(path)
    elif ext == '.csv':
        df = pd.read_csv(path)
    elif ext == '.tsv':
        df = pd.read_csv(path, sep='\t')
    elif ext == '.sas7bdat':
        df = pd.read_sas(path)
    elif ext == '.dta':
        df = pd.read_stata(path)
    else:
        df = pd.read_csv(path)

    # Apply filters
    for f in config['filters']:
        col, op, val = f['column'], f['operator'], f['value']
        if op in OPS:
            df = df[OPS[op](pd.to_numeric(df[col], errors='coerce'), val)]
        elif op == 'in':
            df = df[df[col].isin(val)]
        elif op == 'not_in':
            df = df[~df[col].isin(val)]

    # Compute derived variables
    for dv in config['derived_variables']:
        if dv['type'] == 'coalesce':
            result = pd.to_numeric(df[dv['columns'][0]], errors='coerce')
            for c in dv['columns'][1:]:
                result = result.combine_first(pd.to_numeric(df[c], errors='coerce'))
            df[dv['name']] = result
        elif dv['type'] == 'expression':
            local_ns = {}
            for dep in dv.get('dependencies', []):
                local_ns[dep] = pd.to_numeric(df[dep], errors='coerce')
            local_ns['np'] = np
            df[dv['name']] = eval(dv['expression'], {"__builtins__": {}}, local_ns)

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# Exclusion Step Processing
# ═══════════════════════════════════════════════════════════════════════════════

def apply_exclusion(df, step):
    """Apply one exclusion step and return (remaining_df, n_excluded)."""
    n_before = len(df)

    if 'condition' in step:
        cond = step['condition']
        try:
            # Try .isna() / .notna() patterns
            if '.isna()' in cond or '.notna()' in cond:
                mask = df.eval(cond)
                df_remaining = df[~mask]
            else:
                mask = df.eval(cond)
                df_remaining = df[~mask]
        except Exception:
            try:
                df_remaining = df.query(f"not ({cond})")
            except Exception as e:
                # TP-2 audit fix (2026-05-08, fc-A-1 + fc-D-1): invalid
                # exclusion expression previously printed warning to stdout
                # and returned unchanged df → n_excluded=0 silently. Now:
                # raise so caller sees blocking error instead of false 0.
                raise RuntimeError(
                    f"[QC_BLOCKING] Could not evaluate condition '{cond}': {e}"
                )
    elif 'keep_condition' in step:
        cond = step['keep_condition']
        try:
            if '.isna()' in cond or '.notna()' in cond:
                mask = df.eval(cond)
                df_remaining = df[mask]
            else:
                df_remaining = df.query(cond)
        except Exception as e:
            # TP-2 audit fix: same as above for keep_condition path
            raise RuntimeError(
                f"[QC_BLOCKING] Could not evaluate keep_condition '{cond}': {e}"
            )
    else:
        df_remaining = df

    n_excluded = n_before - len(df_remaining)
    return df_remaining, n_excluded


def process_exclusions(df, config):
    """Process all exclusion steps and return step-by-step results."""
    steps_result = []
    current_df = df.copy()
    initial_n = len(current_df)

    steps_result.append({
        'description': config['initial_label'].replace('\n', ' '),
        'n_remaining': initial_n,
        'n_excluded': 0,
        'step_type': 'initial'
    })

    for step in config['exclusion_steps']:
        current_df, n_excluded = apply_exclusion(current_df, step)
        steps_result.append({
            # `label` was the original key, but research-plan's plan_template.md
            # documents exclusion_steps as {description, condition} and
            # generate_configs passes them through verbatim — so every plan
            # written to that schema raised KeyError here, in the check phase,
            # which has no retry. Accept either, prefer the documented one.
            'description': step.get('label') or step.get('description', ''),
            'n_remaining': len(current_df),
            'n_excluded': n_excluded,
            'step_type': 'exclusion'
        })

    steps_result.append({
        'description': config['final_label'],
        'n_remaining': len(current_df),
        'n_excluded': 0,
        'step_type': 'final'
    })

    # Group split
    group_counts = []
    if config['group_split']:
        gs = config['group_split']
        col = gs['column']
        col_numeric = pd.to_numeric(current_df[col], errors='coerce')
        for g in gs['groups']:
            n = len(current_df[col_numeric == g['value']])
            group_counts.append({'label': g['label'], 'n': n})

    return steps_result, current_df, group_counts


def preview_counts(steps_result, group_counts):
    """Print step-by-step counts for preview."""
    lines = []
    lines.append("=" * 70)
    lines.append("FLOWCHART PREVIEW — Patient Selection Counts")
    lines.append("=" * 70)
    lines.append(f"{'Step':<5} {'Description':<40} {'Excluded':>10} {'Remaining':>10}")
    lines.append("-" * 70)

    for i, step in enumerate(steps_result):
        if step['step_type'] == 'initial':
            lines.append(f"{'':5} {step['description']:<40} {'':>10} {step['n_remaining']:>10,}")
        elif step['step_type'] == 'exclusion':
            lines.append(f"{i:<5} {step['description']:<40} {step['n_excluded']:>10,} {step['n_remaining']:>10,}")
        elif step['step_type'] == 'final':
            lines.append("-" * 70)
            lines.append(f"{'':5} {step['description']:<40} {'':>10} {step['n_remaining']:>10,}")

    if group_counts:
        lines.append("")
        lines.append("  Group Split:")
        for gc in group_counts:
            lines.append(f"    {gc['label']}: n = {gc['n']:,}")

    total_excluded = steps_result[0]['n_remaining'] - steps_result[-1]['n_remaining']
    lines.append("")
    lines.append(f"  Total excluded: {total_excluded:,} "
                 f"({total_excluded / steps_result[0]['n_remaining'] * 100:.1f}%)"
                 if steps_result[0]['n_remaining'] > 0 else "  Total excluded: 0")
    lines.append("=" * 70)

    print("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════════
# Flowchart Drawing
# ═══════════════════════════════════════════════════════════════════════════════

def draw_box(ax, x, y, width, height, text, color, border_color, font_size,
             bold=False, text_color='black'):
    """Draw a rounded rectangle box with text."""
    box = mpatches.FancyBboxPatch(
        (x - width / 2, y - height / 2), width, height,
        boxstyle=mpatches.BoxStyle("Round", pad=0.02),
        facecolor=color, edgecolor=border_color, linewidth=1.5
    )
    ax.add_patch(box)
    fontweight = 'bold' if bold else 'normal'
    ax.text(x, y, text, ha='center', va='center', fontsize=font_size,
            fontweight=fontweight, color=text_color, wrap=True,
            multialignment='center')
    return box


def draw_arrow(ax, x1, y1, x2, y2, color='#333333'):
    """Draw an arrow from (x1,y1) to (x2,y2)."""
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.5))


def generate_flowchart(steps_result, group_counts, config):
    """Generate the CONSORT-style flowchart."""
    ps = config['plot_settings']
    figsize = ps['figsize']
    dpi = ps['dpi']
    font_size = ps['font_size']
    title_font_size = ps['title_font_size']
    main_box_color = ps['main_box_color']
    exclude_box_color = ps['exclude_box_color']
    final_box_color = ps['final_box_color']
    group_box_color = ps['group_box_color']
    arrow_color = ps['arrow_color']
    border_color = ps['border_color']
    main_box_width_frac = ps['main_box_width']

    # Count elements to determine spacing
    n_exclusions = sum(1 for s in steps_result if s['step_type'] == 'exclusion')
    has_groups = len(group_counts) > 0
    n_rows = 1 + n_exclusions + 1 + (1 if has_groups else 0)  # initial + exclusions + final + groups

    # Layout in normalized coordinates
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    # Spacing
    top_margin = 0.95
    bottom_margin = 0.05
    usable_height = top_margin - bottom_margin
    row_height = usable_height / max(n_rows, 1)
    box_height = min(row_height * 0.55, 0.08)

    # Main flow center x
    main_x = 0.42
    main_box_w = main_box_width_frac
    exclude_box_w = 0.32
    exclude_x = main_x + main_box_w / 2 + 0.02 + exclude_box_w / 2

    current_row = 0

    # Initial box
    initial_step = steps_result[0]
    initial_y = top_margin - current_row * row_height
    initial_text = f"{config['initial_label']}\n(N = {initial_step['n_remaining']:,})"
    draw_box(ax, main_x, initial_y, main_box_w, box_height,
             initial_text, main_box_color, border_color, title_font_size, bold=True)

    prev_y = initial_y

    # Exclusion steps
    for step in steps_result:
        if step['step_type'] != 'exclusion':
            continue
        current_row += 1
        step_y = top_margin - current_row * row_height

        # Arrow from previous box
        draw_arrow(ax, main_x, prev_y - box_height / 2,
                   main_x, step_y + box_height / 2, arrow_color)

        # Remaining box (main flow)
        remaining_text = f"Remaining\n(N = {step['n_remaining']:,})"
        draw_box(ax, main_x, step_y, main_box_w, box_height,
                 remaining_text, main_box_color, border_color, font_size)

        # Exclusion box (side)
        exclude_y = (prev_y + step_y) / 2  # midpoint between previous and current
        exclude_text = f"{step['description']}\n(n = {step['n_excluded']:,})"
        draw_box(ax, exclude_x, exclude_y, exclude_box_w, box_height,
                 exclude_text, exclude_box_color, border_color, font_size)

        # Horizontal arrow from main flow to exclusion box
        arrow_start_y = (prev_y - box_height / 2 + step_y + box_height / 2) / 2
        draw_arrow(ax, main_x + main_box_w / 2, arrow_start_y,
                   exclude_x - exclude_box_w / 2, exclude_y, arrow_color)

        prev_y = step_y

    # Final box
    current_row += 1
    final_y = top_margin - current_row * row_height
    final_step = steps_result[-1]
    final_text = f"{config['final_label']}\n(N = {final_step['n_remaining']:,})"

    draw_arrow(ax, main_x, prev_y - box_height / 2,
               main_x, final_y + box_height / 2, arrow_color)
    draw_box(ax, main_x, final_y, main_box_w, box_height,
             final_text, final_box_color, border_color, title_font_size, bold=True)

    # Group split
    if has_groups:
        n_groups = len(group_counts)
        group_y = final_y - row_height
        total_width = 0.85
        group_spacing = total_width / n_groups
        group_box_w = min(group_spacing * 0.85, 0.30)

        for i, gc in enumerate(group_counts):
            gx = (total_width / n_groups) * (i + 0.5) + (1 - total_width) / 2
            group_text = f"{gc['label']}\n(n = {gc['n']:,})"

            draw_arrow(ax, main_x, final_y - box_height / 2,
                       gx, group_y + box_height / 2, arrow_color)
            draw_box(ax, gx, group_y, group_box_w, box_height,
                     group_text, group_box_color, border_color, font_size, bold=True)

    plt.tight_layout(pad=0.5)

    # Save
    output_base = os.path.splitext(config['output_file'])[0]
    png_path = output_base + '.png'
    fig.savefig(png_path, dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"  Flowchart saved: {png_path}")
    return png_path


# ═══════════════════════════════════════════════════════════════════════════════
# Excel Output
# ═══════════════════════════════════════════════════════════════════════════════

DARK_BLUE = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
MEDIUM_BLUE = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
LIGHT_BLUE = PatternFill(start_color='D6E4F0', end_color='D6E4F0', fill_type='solid')
LIGHT_GRAY = PatternFill(start_color='F2F2F2', end_color='F2F2F2', fill_type='solid')
WHITE_FILL = PatternFill(start_color='FFFFFF', end_color='FFFFFF', fill_type='solid')
LIGHT_GREEN = PatternFill(start_color='D5F5E3', end_color='D5F5E3', fill_type='solid')
WHITE_FONT = Font(color='FFFFFF', bold=True, size=12)
HEADER_FONT = Font(color='FFFFFF', bold=True, size=10)
DATA_FONT = Font(size=10)
BOLD_FONT = Font(size=10, bold=True)
THIN_BORDER = Border(
    left=Side(style='thin', color='D9D9D9'),
    right=Side(style='thin', color='D9D9D9'),
    top=Side(style='thin', color='D9D9D9'),
    bottom=Side(style='thin', color='D9D9D9')
)
CENTER_ALIGN = Alignment(horizontal='center', vertical='center', wrap_text=True)
LEFT_ALIGN = Alignment(horizontal='left', vertical='center', wrap_text=True)


def write_excel(steps_result, group_counts, config):
    """Write formatted Excel output with step-by-step counts."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Patient Selection"

    n_cols = 4  # Step, Description, N Excluded, N Remaining

    # Row 1: Title
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    cell = ws.cell(row=1, column=1, value='Patient Selection Flowchart Summary')
    cell.font = WHITE_FONT
    cell.fill = DARK_BLUE
    cell.alignment = CENTER_ALIGN
    ws.row_dimensions[1].height = 30

    # Row 2: Subtitle
    initial_n = steps_result[0]['n_remaining']
    final_n = steps_result[-1]['n_remaining']
    subtitle = f"Initial N = {initial_n:,} → Final N = {final_n:,}"
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    cell = ws.cell(row=2, column=1, value=subtitle)
    cell.font = Font(size=10, italic=True)
    cell.fill = LIGHT_BLUE
    cell.alignment = CENTER_ALIGN
    ws.row_dimensions[2].height = 22

    # Row 3: Headers
    headers = ['Step', 'Description', 'N Excluded', 'N Remaining']
    for j, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=j, value=header)
        cell.font = HEADER_FONT
        cell.fill = MEDIUM_BLUE
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    # Data rows
    row_idx = 4
    step_num = 0
    for step in steps_result:
        fill = LIGHT_GRAY if (row_idx - 4) % 2 == 0 else WHITE_FILL

        if step['step_type'] == 'initial':
            step_label = 'Initial'
            fill = LIGHT_BLUE
        elif step['step_type'] == 'final':
            step_label = 'Final'
            fill = LIGHT_GREEN
        else:
            step_num += 1
            step_label = f'Exclusion {step_num}'

        cell = ws.cell(row=row_idx, column=1, value=step_label)
        cell.font = BOLD_FONT if step['step_type'] in ('initial', 'final') else DATA_FONT
        cell.fill = fill
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

        cell = ws.cell(row=row_idx, column=2, value=step['description'])
        cell.font = DATA_FONT
        cell.fill = fill
        cell.alignment = LEFT_ALIGN
        cell.border = THIN_BORDER

        excl_text = f"{step['n_excluded']:,}" if step['n_excluded'] > 0 else '—'
        cell = ws.cell(row=row_idx, column=3, value=excl_text)
        cell.font = DATA_FONT
        cell.fill = fill
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

        cell = ws.cell(row=row_idx, column=4, value=f"{step['n_remaining']:,}")
        cell.font = BOLD_FONT if step['step_type'] in ('initial', 'final') else DATA_FONT
        cell.fill = fill
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

        row_idx += 1

    # Group split rows
    if group_counts:
        row_idx += 1
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=n_cols)
        cell = ws.cell(row=row_idx, column=1, value='Group Split')
        cell.font = Font(size=10, bold=True, italic=True)
        cell.fill = LIGHT_BLUE
        cell.alignment = CENTER_ALIGN
        row_idx += 1

        for gc in group_counts:
            cell = ws.cell(row=row_idx, column=1, value='Group')
            cell.font = DATA_FONT
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER

            cell = ws.cell(row=row_idx, column=2, value=gc['label'])
            cell.font = BOLD_FONT
            cell.alignment = LEFT_ALIGN
            cell.border = THIN_BORDER

            cell = ws.cell(row=row_idx, column=3, value='—')
            cell.font = DATA_FONT
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER

            cell = ws.cell(row=row_idx, column=4, value=f"{gc['n']:,}")
            cell.font = BOLD_FONT
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER

            row_idx += 1

    # Column widths
    ws.column_dimensions['A'].width = 15
    ws.column_dimensions['B'].width = 45
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 15

    # Save
    output_path = config['output_file']
    wb.save(output_path)
    print(f"  Excel saved: {output_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_academic_style():
    """academic-style integration (Wave 2). Consumes --style=<journal> from
    sys.argv. No-op when skill not installed or flag absent."""
    from pathlib import Path as _P
    _as = _P.home() / ".claude" / "skills" / "academic-style"
    if not _as.exists():
        return None
    if str(_as) not in sys.path:
        sys.path.insert(0, str(_as))
    try:
        from core.biostats_integration import apply_style_from_argv
    except ImportError:
        return None
    return apply_style_from_argv(sys.argv)


def main():
    _AS_STYLE = _apply_academic_style()
    if _AS_STYLE:
        print(f"  Applied {_AS_STYLE} journal style")

    if len(sys.argv) < 2:
        print("Usage: python flowchart.py config.json [--preview] [--style=<journal>]")
        sys.exit(1)

    config_path = sys.argv[1]
    preview_mode = '--preview' in sys.argv

    config = load_config(config_path)

    print("Loading data...")
    df = load_data(config)
    print(f"  Data loaded: {len(df)} rows")

    # Process exclusions
    print("\nProcessing exclusion steps...")
    steps_result, final_df, group_counts = process_exclusions(df, config)

    if preview_mode:
        preview_counts(steps_result, group_counts)
        sys.exit(0)

    # Generate flowchart
    print("\nGenerating flowchart...")
    generate_flowchart(steps_result, group_counts, config)

    # Write Excel
    print("Writing Excel output...")
    write_excel(steps_result, group_counts, config)

    # Print summary
    print("\n" + "=" * 60)
    print("FLOWCHART GENERATION COMPLETE")
    print("=" * 60)
    print(f"  Initial: N = {steps_result[0]['n_remaining']:,}")
    total_excluded = steps_result[0]['n_remaining'] - steps_result[-1]['n_remaining']
    print(f"  Total excluded: {total_excluded:,} "
          f"({total_excluded / steps_result[0]['n_remaining'] * 100:.1f}%)"
          if steps_result[0]['n_remaining'] > 0 else "  Total excluded: 0")
    print(f"  Final: N = {steps_result[-1]['n_remaining']:,}")
    if group_counts:
        print("  Groups:")
        for gc in group_counts:
            print(f"    {gc['label']}: n = {gc['n']:,}")
    print("=" * 60)

    # ── QC Warnings ──────────────────────────────────────────────────────────
    # TP-2 audit fix (2026-05-08, fc-D-1 + fc-B-3): track [QC_BLOCKING]
    # emissions and sys.exit(2) so pipeline detects failure; surface QC
    # block exception instead of silent pass.
    qc_blocking_count = 0
    try:
        final_n = steps_result[-1]['n_remaining']
        if final_n == 0:
            print("[QC_BLOCKING] Final cohort has 0 patients remaining after all exclusions", file=sys.stderr)
            qc_blocking_count += 1
        if group_counts:
            for gc in group_counts:
                if gc['n'] < 30:
                    print(f"[QC_WARNING] Group '{gc['label']}' has n={gc['n']} (< 30)", file=sys.stderr)
            # TP-2 audit fix (fc-A-2): subgroup totals must reconcile vs final N
            sum_groups = sum(gc['n'] for gc in group_counts)
            if sum_groups != final_n:
                print(f"[QC_BLOCKING] Subgroup total sum ({sum_groups}) != final cohort N ({final_n}) — "
                      f"check grouping variable for missing/unlisted categories",
                      file=sys.stderr)
                qc_blocking_count += 1
    except Exception as e:
        print(f"[QC_WARNING] QC block raised: {type(e).__name__}: {e}", file=sys.stderr)

    if qc_blocking_count > 0:
        sys.exit(2)


if __name__ == '__main__':
    main()
