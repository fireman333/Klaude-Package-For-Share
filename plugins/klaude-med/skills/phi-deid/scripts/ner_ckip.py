"""
CKIP Transformers wrapper for Chinese NER.

CKIP is Academia Sinica's BERT-based tagger. It is NOT a generative LLM —
it's a task-specific classifier that runs on CPU, completely offline after the
initial model download. We use it to catch Chinese person/org/location names
that the rule-based patterns would miss.

Design:
    - Lazy import: `import ckip_transformers` is deferred until first use, so
      importing this module is cheap and doesn't crash on systems without CKIP.
    - Lazy first-run install: if CKIP is not installed, `first_time_setup()`
      invokes pip to install it. This is gated behind a CLI flag to avoid
      surprising the user.
    - Model: use the smallest viable model (`albert-tiny-chinese-ner`, ~50 MB).
      Users with more RAM can pick a larger one via PHI_DEID_CKIP_MODEL env var.
    - Output: list of patterns.Detection, with CKIP entity types mapped to our
      categories (PERSON -> PATIENT_NAME by default, since in a clinical note
      the most frequent person is the patient; downstream logic can reclassify
      via role hints).

Environment:
    PHI_DEID_CKIP_DEVICE: 'cpu' (default) or GPU index
    PHI_DEID_CKIP_MODEL: one of 'albert-tiny', 'albert-base', 'bert-base' (default 'albert-tiny')
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Import patterns.Detection without triggering heavy lexicon loads
sys.path.insert(0, str(Path(__file__).resolve().parent))
from patterns import Detection  # noqa: E402


# ---------- CKIP entity type -> our category ----------

# CKIP labels follow Academia Sinica's tagset — PERSON, ORG, LOC, GPE, etc.
# We map only the ones we care about for PHI.
CKIP_TO_CATEGORY = {
    "PERSON": "PATIENT_NAME",  # default; may be reclassified by role hint logic
    "ORG": "HOSPITAL",          # clinical ORG is usually a hospital
    "GPE": "ADDRESS",           # geo-political entity (city/country)
    "LOC": "ADDRESS",
}


# ---------- Lazy loader ----------

_CKIP_NER = None  # cached pipeline instance


def is_installed() -> bool:
    try:
        import ckip_transformers  # noqa: F401
        return True
    except ImportError:
        return False


def first_time_setup(auto: bool = False) -> None:
    """Install ckip-transformers and torch (CPU) via pip if not present.

    When auto=True (e.g. called from a CLI flag), proceeds without prompting.
    Otherwise raises an error instructing the user how to install.
    """
    if is_installed():
        return
    if not auto:
        raise RuntimeError(
            "ckip-transformers is not installed. Run one of:\n"
            "  python -m pip install ckip-transformers torch\n"
            "  python scripts/ner_ckip.py --install\n"
        )
    print("[phi-deid] Installing ckip-transformers and torch (CPU) ...", file=sys.stderr)
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", "ckip-transformers", "torch"]
    )


def _load_pipeline():
    global _CKIP_NER
    if _CKIP_NER is not None:
        return _CKIP_NER

    if not is_installed():
        raise RuntimeError("ckip-transformers not installed — call first_time_setup() first")

    from ckip_transformers.nlp import CkipNerChunker  # type: ignore

    model_size = os.environ.get("PHI_DEID_CKIP_MODEL", "albert-tiny")
    device_env = os.environ.get("PHI_DEID_CKIP_DEVICE", "cpu")
    # CKIP's CkipNerChunker accepts level: 1 (albert-tiny), 2 (albert-base), 3 (bert-base)
    level_map = {"albert-tiny": 1, "albert-base": 2, "bert-base": 3}
    level = level_map.get(model_size, 1)
    device = -1 if device_env == "cpu" else int(device_env)

    _CKIP_NER = CkipNerChunker(model_name=None, level=level, device=device)
    return _CKIP_NER


# ---------- Public API ----------

def detect(text: str) -> list[Detection]:
    """Run CKIP NER and return Detection objects mapped to our categories.

    Returns empty list if CKIP is not installed — callers should treat CKIP
    as an optional enhancement on top of rule-based detectors.
    """
    if not is_installed():
        return []

    ner = _load_pipeline()
    # CKIP expects a list of documents; we send one
    results = ner([text], use_delim=True, show_progress=False)[0]

    detections: list[Detection] = []
    for ent in results:
        # ent fields: word (str), ner (tag), idx (tuple[int, int])
        tag = ent.ner
        if tag not in CKIP_TO_CATEGORY:
            continue
        category = CKIP_TO_CATEGORY[tag]
        start, end = ent.idx
        detections.append(
            Detection(
                category=category,
                text=ent.word,
                start=start,
                end=end,
                role_hint="patient" if category == "PATIENT_NAME" else None,
            )
        )
    return detections


def main() -> None:
    """CLI: `python ner_ckip.py --install` to trigger first-time setup."""
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true", help="Install ckip-transformers + torch")
    parser.add_argument("--check", action="store_true", help="Print installation status as JSON")
    args = parser.parse_args()

    if args.install:
        first_time_setup(auto=True)
        print(json.dumps({"installed": True}))
    elif args.check:
        print(json.dumps({"installed": is_installed()}))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
