import json
from datetime import date
from pathlib import Path

import pandas as pd

from config.roster import OUTPUT_COLS, PCT_COLS


def write_json(df: pd.DataFrame, target_date: date, out_path: Path):
    """Write game log DataFrame to a structured JSON file."""
    cols = [c for c in OUTPUT_COLS if c in df.columns]
    output = df[cols].copy()

    for col in PCT_COLS:
        if col in output.columns:
            output[col] = (output[col] * 100).round(1)

    payload = {
        "date": str(target_date),
        "generated_at": date.today().isoformat(),
        "total_players": len(output),
        "owners": {},
    }

    for owner, group in output.groupby("Fantasy_Owner"):
        payload["owners"][owner] = group.drop(columns="Fantasy_Owner").to_dict(orient="records")

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\n✅  Saved → {out_path}")
