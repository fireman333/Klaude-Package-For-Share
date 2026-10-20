#!/usr/bin/env python3
"""End-to-end demo: synthesize a small KM dataset and render the curve under
all 4 journal themes. Outputs PNGs to ./out/.

This stands in for the full HF dataset → biostats pipeline; the integration
is identical (same `apply_journal_theme` context manager).
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Make academic-style importable without pip install
_AS_DIR = Path(__file__).resolve().parents[2]  # academic-style/
if str(_AS_DIR) not in sys.path:
    sys.path.insert(0, str(_AS_DIR))

from core.matplotlib_applier import (  # noqa: E402
    apply_journal_theme,
    figure_size,
    palette,
)


def synth_km(n: int, hr: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Generate a Kaplan-Meier-style step curve via exponential survival."""
    rng = np.random.default_rng(seed)
    times_event = rng.exponential(scale=12.0 / hr, size=n)
    times = np.sort(np.minimum(times_event, 60.0))  # admin censor at 60
    surv = 1 - np.arange(1, n + 1) / n
    return times, surv


def main() -> int:
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)

    t1, s1 = synth_km(200, hr=1.0, seed=1)
    t2, s2 = synth_km(200, hr=0.7, seed=2)

    for journal in ("nature", "jama", "nejm", "lancet"):
        with apply_journal_theme(journal, column="single") as spec:
            w, h = figure_size(journal, "single")
            fig, ax = plt.subplots(figsize=(w, h * 1.3))
            ax.step(t1, s1, where="post",
                    color=palette(journal, "control_or_negative"),
                    label="Control")
            ax.step(t2, s2, where="post",
                    color=palette(journal, "primary_method"),
                    label="Treatment")
            ax.set_xlabel("Time (months)")
            ax.set_ylabel("Survival probability")
            ax.set_title(f"Kaplan-Meier — {spec['journal']['name']} style")
            ax.set_ylim(0, 1.02)
            ax.legend(loc="upper right")
            outfile = out / f"km_{journal}.png"
            fig.savefig(outfile, dpi=spec["dimensions"]["dpi_raster"])
            plt.close(fig)
            print(f"Wrote {outfile}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
