"""Buggy fixture script — fits logistic regression on a time-to-event outcome.
A correct implementation would use lifelines.CoxPHFitter.
"""
import json
import sys
import pandas as pd
import statsmodels.api as sm


def main(config_path: str) -> None:
    with open(config_path) as f:
        cfg = json.load(f)

    df = pd.read_excel(cfg["data_file"])
    y = df[cfg["outcome"]["event_col"]].astype(int)

    rows = []
    for cov in cfg["covariates"]:
        X = sm.add_constant(df[[cov["column"]]])
        # WRONG: outcome is time-to-event but we ignore time_col and run logistic
        model = sm.Logit(y, X).fit(disp=0)
        params = model.params[cov["column"]]
        ci = model.conf_int().loc[cov["column"]]
        p = model.pvalues[cov["column"]]
        rows.append({
            "term": cov["column"],
            "OR": float(params),
            "CI_low": float(ci[0]),
            "CI_high": float(ci[1]),
            "p_value": float(p),
        })

    pd.DataFrame(rows).to_excel(cfg["output_file"], index=False)


if __name__ == "__main__":
    main(sys.argv[1])
