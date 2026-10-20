#!/usr/bin/env python3
"""
Multi-sheet Excel to single CSV merger for clinical research data.

Usage:
    python merge_excel_to_csv.py <input_excel> <output_csv> [--subject-col Subject_num]

This script handles:
1. Reading all sheets from a multi-sheet Excel workbook
2. Identifying baseline vs longitudinal sheets
3. Extracting baseline data from longitudinal sheets (Visit == 1 or earliest)
4. Extracting outcome data from Follow Up sheets (death, midpoint events)
5. Merging paired columns (admission/outpatient)
6. Computing derived clinical variables
7. Outputting a single CSV with one row per subject
"""

import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path


def simplify_col(s):
    """Normalize column names: strip whitespace, non-breaking spaces, newlines."""
    return str(s).strip().replace('\xa0', ' ').replace('\n', '')


def read_sheet(xl, sheet_name, subject_col='Subject_num'):
    """Read a sheet, normalize column names, return DataFrame."""
    df = pd.read_excel(xl, sheet_name=sheet_name)
    # Normalize column names
    df.columns = [simplify_col(c) for c in df.columns]
    return df


def deduplicate(df, subject_col='Subject_num'):
    """Drop duplicate subject rows, keeping first occurrence."""
    if subject_col in df.columns:
        before = len(df)
        df = df.drop_duplicates(subset=[subject_col], keep='first')
        after = len(df)
        if before != after:
            print(f"  Removed {before - after} duplicate rows")
    return df


def drop_helper_cols(df, cols_to_drop=None):
    """Drop common helper columns that shouldn't be merged."""
    if cols_to_drop is None:
        cols_to_drop = ['Center_num', 'Subject_Is', 'Subject_Is_cm_part_1',
                        'Subject_Is_cm_part_2', 'B_day']
    existing = [c for c in cols_to_drop if c in df.columns]
    return df.drop(columns=existing)


def extract_baseline_from_longitudinal(df, visit_col, subject_col='Subject_num'):
    """From a longitudinal sheet, extract baseline (Visit == 1 or earliest visit)."""
    if visit_col not in df.columns:
        print(f"  Warning: Visit column '{visit_col}' not found, treating as baseline")
        return deduplicate(df, subject_col)

    min_visit = df[visit_col].dropna().min()
    # Prefer Visit == 1 if it exists, otherwise use the minimum visit number
    if 1.0 in df[visit_col].values:
        baseline = df[df[visit_col] == 1].copy()
    else:
        baseline = df[df[visit_col] == min_visit].copy()

    baseline = baseline.drop(columns=[visit_col], errors='ignore')
    return deduplicate(baseline, subject_col)


def process_follow_up(df_fu, df_visit, subject_col='Subject_num'):
    """
    Process Follow Up sheet to extract:
    1. Death outcome (Death_fu, Cause_of_death_fu, Date_of_death_fu, Death_Day)
    2. Unplanned HF hospitalization (midpoint method)

    Returns a DataFrame with one row per subject containing outcome columns.
    """
    # --- Death processing ---
    # For each subject, find if Death_fu == 1 anywhere
    death_rows = df_fu[df_fu.get('Death_fu', pd.Series(dtype=float)) == 1].copy()
    if len(death_rows) > 0:
        death_data = death_rows.drop_duplicates(subset=[subject_col], keep='first')
        death_cols = [subject_col]
        for c in ['Death_fu', 'Cause_of_death_fu', 'Date_of_death_fu']:
            if c in death_data.columns:
                death_cols.append(c)
        death_data = death_data[death_cols]
    else:
        death_data = pd.DataFrame(columns=[subject_col, 'Death_fu'])

    # For subjects without death, set Death_fu = 0
    all_subjects = df_fu[[subject_col]].drop_duplicates()
    death_data = all_subjects.merge(death_data, on=subject_col, how='left')
    death_data['Death_fu'] = death_data['Death_fu'].fillna(0).astype(int)

    # --- Compute Death_Day ---
    if 'Enrollment_Date' in df_visit.columns and 'Date_of_death_fu' in death_data.columns:
        visit_enroll = df_visit[[subject_col, 'Enrollment_Date']].drop_duplicates(subset=[subject_col])
        death_data = death_data.merge(visit_enroll, on=subject_col, how='left')
        # NaT audit (silent corruption guard): count rows where to_datetime
        # turned a non-null string into NaT (parse failure). Pre-NaN excluded
        # so we only count actual coerce-induced losses.
        enroll_pre_nan = death_data['Enrollment_Date'].isna().sum()
        death_data['Enrollment_Date'] = pd.to_datetime(death_data['Enrollment_Date'], errors='coerce')
        enroll_nat_added = death_data['Enrollment_Date'].isna().sum() - enroll_pre_nan
        if enroll_nat_added > 0:
            print(f"  [WARN] {enroll_nat_added} Enrollment_Date values failed to parse → NaT",
                  file=sys.stderr)

        death_pre_nan = death_data['Date_of_death_fu'].isna().sum()
        death_data['Date_of_death_fu'] = pd.to_datetime(death_data['Date_of_death_fu'], errors='coerce')
        death_nat_added = death_data['Date_of_death_fu'].isna().sum() - death_pre_nan
        if death_nat_added > 0:
            print(f"  [WARN] {death_nat_added} Date_of_death_fu values failed to parse → NaT",
                  file=sys.stderr)

        death_data['Death_Day'] = (death_data['Date_of_death_fu'] - death_data['Enrollment_Date']).dt.days
        death_data = death_data.drop(columns=['Enrollment_Date'])

    # --- Unplanned HF hospitalization (midpoint method) ---
    hf_col = None
    for candidate in ['Un-planned_HF_hos_fu', 'Unplanned_HF_hos_fu', 'Un-planned HF hos fu']:
        if candidate in df_fu.columns:
            hf_col = candidate
            break

    visit_fu_col = None
    for candidate in ['Visit_fu', 'Visit fu']:
        if candidate in df_fu.columns:
            visit_fu_col = candidate
            break

    death_data['Unplanned_HF_hos_fu'] = 0
    death_data['Unplanned_HF_hos_fu_Day'] = np.nan

    if hf_col and visit_fu_col:
        # Find first occurrence of HF event for each subject
        hf_events = df_fu[df_fu[hf_col] == 1].copy()
        hf_events = hf_events.sort_values(by=[subject_col, visit_fu_col])
        hf_first = hf_events.drop_duplicates(subset=[subject_col], keep='first')
        hf_map = hf_first.set_index(subject_col)[visit_fu_col].to_dict()

        # Prepare visit date lookup
        visit_date_cols = [subject_col, 'Enrollment_Date']
        for i in range(1, 9):
            col = f'Follow_up_{i}_Date'
            if col in df_visit.columns:
                visit_date_cols.append(col)

        df_visit_dates = df_visit[[c for c in visit_date_cols if c in df_visit.columns]].copy()
        df_visit_dates = df_visit_dates.drop_duplicates(subset=[subject_col])
        # NaT audit per date column (silent corruption guard).
        nat_per_col = {}
        for col in df_visit_dates.columns:
            if col != subject_col:
                pre_nan = df_visit_dates[col].isna().sum()
                df_visit_dates[col] = pd.to_datetime(df_visit_dates[col], errors='coerce')
                added = df_visit_dates[col].isna().sum() - pre_nan
                if added > 0:
                    nat_per_col[col] = added
        if nat_per_col:
            print(f"  [WARN] visit-date columns with parse failures → NaT: {nat_per_col}",
                  file=sys.stderr)
        df_visit_dates = df_visit_dates.set_index(subject_col)

        def get_day_count(subject_dates, idx):
            """Get days from enrollment for follow-up index. idx=0 means enrollment (day 0)."""
            if idx <= 0:
                return 0
            col_name = f'Follow_up_{idx}_Date'
            if col_name in subject_dates.index and pd.notna(subject_dates[col_name]):
                delta = subject_dates[col_name] - subject_dates['Enrollment_Date']
                return delta.days
            return None

        # Drug-Helper-pattern skip counter: every `continue` increments a
        # named bucket so silent cohort loss is visible in stderr summary.
        skip_reasons = {
            "no_hf_event": 0,           # subject not in hf_map (expected: no event)
            "missing_visit_dates": 0,   # subject in hf_map but no visit-dates row
            "missing_followup_date": 0, # follow-up date NaT → can't compute day
        }
        imported_with_day = 0
        total_subjects = len(death_data)

        for idx, row in death_data.iterrows():
            subj = row[subject_col]
            if subj not in hf_map:
                skip_reasons["no_hf_event"] += 1
                continue

            death_data.at[idx, 'Unplanned_HF_hos_fu'] = 1

            x = int(hf_map[subj])
            if subj not in df_visit_dates.index:
                skip_reasons["missing_visit_dates"] += 1
                continue

            subject_dates = df_visit_dates.loc[subj]
            d1 = get_day_count(subject_dates, x - 1)
            d0 = get_day_count(subject_dates, x - 2)

            if d1 is None or d0 is None:
                skip_reasons["missing_followup_date"] += 1
                continue

            day_val = (d0 + d1) / 2

            death_day = row.get('Death_Day', np.nan)
            if pd.notna(death_day) and day_val >= death_day:
                day_val = (d0 + death_day) / 2

            death_data.at[idx, 'Unplanned_HF_hos_fu_Day'] = round(day_val, 2)
            imported_with_day += 1

        # Stderr summary so an all-skip cohort never silently looks "successful".
        skipped_total = sum(skip_reasons.values())
        print(
            f"  [HF event audit] total={total_subjects}, "
            f"imported_with_day={imported_with_day}, skipped={skipped_total} "
            f"(no_hf_event={skip_reasons['no_hf_event']}, "
            f"missing_visit_dates={skip_reasons['missing_visit_dates']}, "
            f"missing_followup_date={skip_reasons['missing_followup_date']})",
            file=sys.stderr,
        )

    return death_data


def merge_paired_columns(df, pairs=None):
    """
    Merge paired columns (e.g., admission/outpatient) into unified columns.
    Uses coalesce: takes the first non-null value.
    """
    if pairs is None:
        # Auto-detect common pairs
        pairs = {}
        suffixes_priority = [('_Ad', '_opd'), ('_ad', '_opd'), ('_Ad', '_Opd')]
        seen_bases = set()

        for col in df.columns:
            for s1, s2 in suffixes_priority:
                if col.endswith(s1):
                    base = col[:-len(s1)]
                    partner = base + s2
                    if partner in df.columns and base not in seen_bases:
                        pairs[base] = [col, partner]
                        seen_bases.add(base)

    if not pairs:
        return df

    cols_to_delete = []
    for new_col, sources in pairs.items():
        existing_sources = [s for s in sources if s in df.columns]
        if len(existing_sources) >= 2:
            df[new_col] = df[existing_sources[0]].combine_first(df[existing_sources[1]])
            cols_to_delete.extend(existing_sources)
        elif len(existing_sources) == 1:
            df[new_col] = df[existing_sources[0]]
            cols_to_delete.extend(existing_sources)

    if cols_to_delete:
        df = df.drop(columns=cols_to_delete, errors='ignore')
        print(f"  Merged {len(pairs)} column pairs: {list(pairs.keys())}")

    return df


def compute_derived_variables(df):
    """Compute derived clinical variables if source columns exist."""
    computed = []

    # BSA (Mosteller formula) - keep full precision for downstream calculations
    if 'Height' in df.columns and 'Weight' in df.columns:
        df['BSA'] = np.sqrt((df['Height'] * df['Weight']) / 3600)
        computed.append('BSA')

    # LAVi
    if 'LA' in df.columns and 'BSA' in df.columns:
        df['LAVi'] = df['LA'] / df['BSA']
        computed.append('LAVi')

    # RAP (from JVP_over_6cm)
    if 'JVP_over_6cm' in df.columns:
        df['RAP'] = df['JVP_over_6cm'].map({0: 5, 1: 10})
        computed.append('RAP')

    # PASP
    if 'TR_vel' in df.columns and 'RAP' in df.columns:
        df['PASP'] = 4 * ((df['TR_vel'] / 100) ** 2) + df['RAP']
        computed.append('PASP')

    # E/e'
    if all(c in df.columns for c in ['E_vel', 'Tissue_E_Septal', 'Tissue_E_Lateral']):
        avg_e = (df['Tissue_E_Septal'] + df['Tissue_E_Lateral']) / 2
        df["E/e'"] = df['E_vel'] / avg_e
        computed.append("E/e'")

    # LVEF
    if 'LVEDV' in df.columns and 'LVESV' in df.columns:
        df['LVEF'] = 100 * (df['LVEDV'] - df['LVESV']) / df['LVEDV']
        computed.append('LVEF')

    # RWT
    if 'LVPW' in df.columns and 'LVEDD' in df.columns:
        df['RWT'] = 2 * df['LVPW'] / df['LVEDD']
        computed.append('RWT')

    # LVM and LVMi
    if all(c in df.columns for c in ['IVS', 'LVEDD', 'LVPW']):
        ivs_cm = df['IVS'] / 10
        lvedd_cm = df['LVEDD'] / 10
        lvpw_cm = df['LVPW'] / 10
        df['LVM'] = 0.8 * 1.04 * ((ivs_cm + lvedd_cm + lvpw_cm)**3 - lvedd_cm**3) + 0.6
        computed.append('LVM')
        if 'BSA' in df.columns:
            df['LVMi'] = df['LVM'] / df['BSA']
            computed.append('LVMi')

    # Round all derived variables at the end (after all calculations use full precision)
    for col in computed:
        if col in df.columns:
            df[col] = df[col].round(2)

    if computed:
        print(f"  Computed derived variables: {computed}")

    return df


def main():
    parser = argparse.ArgumentParser(description='Merge multi-sheet Excel to single CSV')
    parser.add_argument('input_excel', help='Path to input Excel file')
    parser.add_argument('output_csv', help='Path to output CSV file')
    parser.add_argument('--subject-col', default='Subject_num', help='Subject ID column name')
    args = parser.parse_args()

    subject_col = args.subject_col

    print(f"Loading {args.input_excel}...")
    xl = pd.ExcelFile(args.input_excel)
    print(f"Found {len(xl.sheet_names)} sheets: {xl.sheet_names}")

    # ---- Classify sheets ----
    sheets_data = {}
    for name in xl.sheet_names:
        df = read_sheet(xl, name, subject_col)
        n_rows = len(df)
        n_unique = df[subject_col].nunique() if subject_col in df.columns else 0
        is_long = n_rows > n_unique * 1.2 if n_unique > 0 else False

        # Detect visit column
        visit_col = None
        for c in df.columns:
            if c.lower().startswith('visit'):
                visit_col = c
                break

        sheets_data[name] = {
            'df': df, 'rows': n_rows, 'unique': n_unique,
            'is_long': is_long, 'visit_col': visit_col
        }
        marker = " [LONG]" if is_long else ""
        print(f"  {name}: {n_rows} rows, {n_unique} subjects{marker}")

    # ---- Find master sheet (Visit Date or equivalent) ----
    master_sheet = None
    for name in xl.sheet_names:
        lower = name.lower()
        if 'visit' in lower and 'date' in lower:
            master_sheet = name
            break
    if master_sheet is None:
        # Fallback: use the first sheet
        master_sheet = xl.sheet_names[0]
        print(f"  Warning: No 'Visit Date' sheet found, using '{master_sheet}' as master")

    print(f"\nMaster sheet: {master_sheet}")
    df_master = sheets_data[master_sheet]['df'].copy()
    df_master = deduplicate(df_master, subject_col)

    # Keep enrollment info from master
    enrollment_cols = [subject_col]
    for c in df_master.columns:
        if c != subject_col:
            enrollment_cols.append(c)
    df_visit_full = df_master.copy()  # Keep full visit dates for outcome computation

    # Start with key columns from master (not all follow-up dates in final output)
    keep_master_cols = []
    for c in df_master.columns:
        cl = c.lower()
        if 'follow_up' in cl and 'date' in cl:
            continue  # Skip follow-up date columns from final output
        keep_master_cols.append(c)
    df_merged = df_master[keep_master_cols].copy()

    # ---- Process and merge each sheet ----
    follow_up_sheet = None
    for name in xl.sheet_names:
        if name == master_sheet:
            continue

        info = sheets_data[name]
        df = info['df'].copy()

        # Detect Follow Up sheet
        if 'follow' in name.lower() and 'up' in name.lower():
            follow_up_sheet = name
            continue  # Process separately

        print(f"\nProcessing: {name}")

        # Drop helper columns
        df = drop_helper_cols(df)

        # Handle longitudinal sheets
        if info['is_long'] and info['visit_col']:
            df = extract_baseline_from_longitudinal(df, info['visit_col'], subject_col)
        else:
            df = deduplicate(df, subject_col)

        # Remove Enrollment_Date if already in merged
        if 'Enrollment_Date' in df.columns and 'Enrollment_Date' in df_merged.columns:
            df = df.drop(columns=['Enrollment_Date'])

        # Remove duplicate columns
        dup_cols = [c for c in df.columns if c in df_merged.columns and c != subject_col]
        if dup_cols:
            df = df.drop(columns=dup_cols)

        # Left join
        df_merged = df_merged.merge(df, on=subject_col, how='left')

    # ---- Process Follow Up outcomes ----
    if follow_up_sheet:
        print(f"\nProcessing outcomes from: {follow_up_sheet}")
        df_fu = sheets_data[follow_up_sheet]['df'].copy()
        outcome_data = process_follow_up(df_fu, df_visit_full, subject_col)

        # Remove duplicate columns before merge
        dup_cols = [c for c in outcome_data.columns if c in df_merged.columns and c != subject_col]
        if dup_cols:
            outcome_data = outcome_data.drop(columns=dup_cols)

        df_merged = df_merged.merge(outcome_data, on=subject_col, how='left')

    # ---- Merge paired columns ----
    print("\nMerging paired columns (admission/outpatient)...")
    # Explicit pairs that are commonly found
    explicit_pairs = {
        'HR': ['HR_Ad', 'HR_opd'],
        'SBP': ['SBP_Ad', 'SBP_opd'],
        'DBP': ['DBP_Ad', 'DBP_opd'],
        'Height': ['Height_Ad', 'Height_opd'],
        'Weight': ['Weight_Ad', 'Weight_opd'],
        'NYHA': ['NYHA_Ad', 'NYHA_opd'],
    }
    # Filter to only pairs where both sources exist
    valid_pairs = {k: v for k, v in explicit_pairs.items()
                   if any(s in df_merged.columns for s in v)}
    if valid_pairs:
        df_merged = merge_paired_columns(df_merged, valid_pairs)
    else:
        # Try auto-detection
        df_merged = merge_paired_columns(df_merged)

    # ---- Compute derived variables ----
    print("\nComputing derived variables...")
    df_merged = compute_derived_variables(df_merged)

    # ---- Save ----
    print(f"\nSaving to {args.output_csv}...")
    df_merged.to_csv(args.output_csv, index=False)

    print(f"\nDone!")
    print(f"  Rows: {len(df_merged)}")
    print(f"  Columns: {len(df_merged.columns)}")
    print(f"  Unique subjects: {df_merged[subject_col].nunique()}")


if __name__ == '__main__':
    main()
