"""
Session and mapping management for phi-deid.

A Session represents one patient's de-identification context. All files for a
session live in a single folder under ~/phi-deid-sessions/. The global
registry.json maps a user-provided alias to the folder path, so the user can
re-open the same session (and keep pseudonyms consistent) across
admission/progress/discharge notes.

Files in each session folder (all chmod 600 except deid.txt and *_report.txt):
    raw.PHI_DO_NOT_READ.txt  - the input, kept for audit (contains PHI)
    deid.txt                 - the redacted output (SAFE to read)
    mapping.json             - pseudonym <-> real text (contains PHI)
    date_offset.txt          - integer days (contains no PHI but kept with mapping)

Registry: ~/phi-deid-sessions/registry.json (chmod 600)
    { "alias": "/path/to/session/folder/", ... }

IMPORTANT: Claude should never Read any file in a session folder except
deid.txt and files whose name ends with _report.txt. mapping.json and
raw.PHI_DO_NOT_READ.txt contain PHI. This is enforced by convention in SKILL.md,
not by the filesystem.
"""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


DEFAULT_ROOT = Path.home() / "phi-deid-sessions"
REGISTRY_FILENAME = "registry.json"

# Category -> pseudonym token prefix
# Two different categories (PHONE_MOBILE / PHONE_LANDLINE) can share a prefix
# when the distinction is clinically irrelevant.
CATEGORY_PREFIX: dict[str, str] = {
    "NATIONAL_ID": "NATIONAL_ID",
    "UI_NUMBER": "UI_NUMBER",
    "NHI_CARD": "NHICARD",
    "MRN": "MRN",
    "ADMISSION_NO": "ADM",
    "PATHOLOGY_NO": "PATH",
    "ACCESSION_NO": "ACC",
    "LAB_NO": "LAB",
    "BED": "BED",
    "PHONE_MOBILE": "PHONE",
    "PHONE_LANDLINE": "PHONE",
    "EMAIL": "EMAIL",
    "LINE_ID": "LINE",
    "PLATE_TW": "PLATE",
    "ADDRESS": "ADDRESS",
    "HOSPITAL": "HOSPITAL",
    "PATIENT_NAME": "PATIENT",
    "FAMILY_NAME": "FAMILY",
    "DOCTOR_NAME": "DOCTOR",
    "NURSE_NAME": "NURSE",
    "STAFF_NAME": "STAFF",
    "PERSON_NAME": "PERSON",
}


def _chmod_600(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # best effort — filesystem may not support (e.g. network mount)


def _chmod_700(path: Path) -> None:
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- Registry ----------

def registry_path(root: Path = DEFAULT_ROOT) -> Path:
    return root / REGISTRY_FILENAME


def ensure_root(root: Path = DEFAULT_ROOT) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _chmod_700(root)
    reg = registry_path(root)
    if not reg.exists():
        _write_json(reg, {})
        _chmod_600(reg)


def load_registry(root: Path = DEFAULT_ROOT) -> dict[str, str]:
    ensure_root(root)
    return _read_json(registry_path(root))


def save_registry(reg: dict[str, str], root: Path = DEFAULT_ROOT) -> None:
    _write_json(registry_path(root), reg)
    _chmod_600(registry_path(root))


# ---------- Session ----------

@dataclass
class Session:
    alias: str
    folder: Path
    # mapping: pseudonym_token -> real_text
    # We store pseudonym -> real (not real -> pseudonym) because reverse lookup
    # is the critical operation during reidentify. Forward lookup is handled by
    # scanning a reverse dict built on load.
    mapping: dict[str, str] = field(default_factory=dict)
    # Per-category counters for pseudonym allocation
    counters: dict[str, int] = field(default_factory=dict)
    # Date shift offset in days (applied to all dates in this session)
    date_offset: int = 0

    # ---- Pseudonym allocation ----

    def token_for(self, category: str, real_text: str) -> str:
        """Return the pseudonym token for the (category, real_text) pair.

        If this real_text has been seen in this session (possibly under a different
        category), reuse the same token to preserve anchor consistency.
        """
        # Reverse lookup: has this real_text been assigned already?
        for tok, real in self.mapping.items():
            if real == real_text:
                return tok

        prefix = CATEGORY_PREFIX.get(category, "OTHER")
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        token = f"[{prefix}_{self.counters[prefix]:02d}]"
        # In rare collisions (e.g., two categories mapping to same prefix, same
        # counter due to external state), we'd fail. Not expected here.
        self.mapping[token] = real_text
        return token

    # ---- Persistence ----

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        _chmod_700(self.folder)
        mapping_path = self.folder / "mapping.json"
        _write_json(
            mapping_path,
            {
                "alias": self.alias,
                "date_offset": self.date_offset,
                "counters": self.counters,
                "mapping": self.mapping,
            },
        )
        _chmod_600(mapping_path)
        # Keep date_offset as a separate small file for quick inspection
        # (it contains no PHI — the offset alone cannot re-identify anyone).
        (self.folder / "date_offset.txt").write_text(str(self.date_offset))

    @classmethod
    def load(cls, alias: str, root: Path = DEFAULT_ROOT) -> "Session":
        reg = load_registry(root)
        if alias not in reg:
            raise KeyError(f"Unknown session alias: {alias!r}")
        folder = Path(reg[alias])
        mapping_path = folder / "mapping.json"
        if not mapping_path.exists():
            raise FileNotFoundError(f"mapping.json missing in {folder}")
        data = _read_json(mapping_path)
        return cls(
            alias=alias,
            folder=folder,
            mapping=data.get("mapping", {}),
            counters=data.get("counters", {}),
            date_offset=data.get("date_offset", 0),
        )

    @classmethod
    def new(
        cls,
        alias: str,
        root: Path = DEFAULT_ROOT,
        date_offset: int | None = None,
    ) -> "Session":
        """Create a new session and register its alias. Fails if alias exists."""
        ensure_root(root)
        reg = load_registry(root)
        if alias in reg:
            raise FileExistsError(
                f"Alias {alias!r} already in registry. Use Session.load() to reuse it, "
                f"or pick a different --patient-key."
            )
        # Validate alias — no path separators, no spaces in folder names
        if not alias or any(c in alias for c in "/\\ \t\n\r"):
            raise ValueError(
                f"Invalid alias {alias!r}: must be non-empty with no whitespace or path separators."
            )
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = root / f"{stamp}_{alias}"
        folder.mkdir(parents=True, exist_ok=False)
        _chmod_700(folder)
        # Random per-session offset in [-365, +365] days. Using secrets (not
        # random) so the offset isn't predictable from the system time alone.
        offset = (secrets.randbelow(731) - 365) if date_offset is None else date_offset
        session = cls(alias=alias, folder=folder, date_offset=offset)
        session.save()
        reg[alias] = str(folder)
        save_registry(reg, root)
        return session

    # ---- Reverse mapping for re-identification ----

    def reverse_mapping(self) -> dict[str, str]:
        """Token -> real_text (identical to self.mapping, exposed for clarity)."""
        return dict(self.mapping)


# ---------- CLI entry for listing sessions ----------

def list_sessions(root: Path = DEFAULT_ROOT) -> list[dict]:
    """Return alias + folder info. Does NOT return any PHI."""
    reg = load_registry(root)
    out = []
    for alias, folder in reg.items():
        p = Path(folder)
        out.append(
            {
                "alias": alias,
                "folder": str(p),
                "exists": p.exists(),
                "has_mapping": (p / "mapping.json").exists(),
            }
        )
    return out


def main() -> None:
    """CLI: `python mapping.py list` - print sessions as JSON (no PHI)."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="phi-deid session manager")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("list", help="List registered session aliases")
    delete = sub.add_parser("delete", help="Delete a session folder and registry entry")
    delete.add_argument("alias")
    args = parser.parse_args()

    if args.cmd == "list":
        sessions = list_sessions()
        json.dump({"sessions": sessions}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    elif args.cmd == "delete":
        import shutil
        reg = load_registry()
        if args.alias not in reg:
            print(json.dumps({"error": f"alias {args.alias} not found"}))
            sys.exit(1)
        folder = Path(reg.pop(args.alias))
        if folder.exists():
            shutil.rmtree(folder)
        save_registry(reg)
        print(json.dumps({"deleted": args.alias, "folder": str(folder)}))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
