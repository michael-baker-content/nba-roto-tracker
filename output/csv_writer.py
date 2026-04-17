from datetime import date
from pathlib import Path

import pandas as pd

from config.roster import OUTPUT_COLS, PCT_COLS


def write_csv(df: pd.DataFrame, target_date: date, out_path: Path):
    """Write game log DataFrame to a flat CSV file."""
    cols = [c for c in OUTPUT_COLS if c in df.columns]
    output = df[cols].copy()

    for col in PCT_COLS:
        if col in output.columns:
            output[col] = (output[col] * 100).round(1).astype(str) + "%"

    output.to_csv(out_path, index=False)
    print(f"\n✅  Saved → {out_path}")
