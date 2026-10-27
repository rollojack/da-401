"""
Pull half-season Statcast batting metrics for a list of player-seasons.

Used for the matching step, where participants and control candidates must be
measured identically. Every metric here is computed from Statcast pitch-level
data in the same way for every player:

    PA, K%, HR, Avg EV, Avg LA, GB%, FB%, LD%, HR/FB, Pull%, Straight%, Oppo%

FB% counts fly balls + popups as a share of batted balls (same as
savant_pull.py). HR/FB = home runs / (fly balls + popups).

Pull/Straight/Oppo use the standard spray-angle conversion from Statcast hit
coordinates (hc_x, hc_y), split at +/-15 degrees and flipped by the batter's
side for that pitch (so switch hitters are handled per PA). This is an
APPROXIMATION of Savant's own buckets and will not match FanGraphs exactly -
fine for matching (both groups measured the same way), but the primary
outcome should still use FanGraphs Pull%/FB% per the research design.

Half-season boundaries come from savant_pull.py's ALL_STAR_GAME_DATE.

Input CSV needs columns: Player, MLBAM ID, Season
Output is appended row by row; re-running skips rows already in the output.

Usage (from the repo root):
    python code/pull_statcast_halves.py data/Control_Pool.csv 1st data/Statcast_Pool_H1.csv
"""
import os
import sys
import math
import importlib.util

import pandas as pd
from pybaseball import statcast_batter

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "savant_pull", os.path.join(HERE, "..", "data", "savant_pull.py"))
savant_pull = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(savant_pull)

COLUMNS = ["Player", "MLBAM ID", "Season", "Half", "PA", "K%", "HR", "BBE",
           "Avg EV", "Avg LA", "GB%", "FB%", "LD%", "HR/FB",
           "Pull%", "Straight%", "Oppo%", "Notes"]


def spray_buckets(bb):
    """Pull / straight / oppo shares from hit coordinates, by batter side."""
    b = bb.dropna(subset=["hc_x", "hc_y"])
    if b.empty:
        return None, None, None
    angle = (b["hc_x"] - 125.42).combine(198.27 - b["hc_y"], math.atan2) * 180 / math.pi
    # Negative angle = toward left field. Pull for a RHB is left field.
    pull_side = angle.where(b["stand"] == "L", -angle)
    n = len(b)
    pull = (pull_side > 15).sum()
    oppo = (pull_side < -15).sum()
    return (round(100 * pull / n, 1), round(100 * (n - pull - oppo) / n, 1),
            round(100 * oppo / n, 1))


def pull_one(player, mlbam_id, season, half):
    start, end = savant_pull.half_date_range(season, half)
    base = {"Player": player, "MLBAM ID": mlbam_id, "Season": season, "Half": half}
    try:
        df = statcast_batter(start.isoformat(), end.isoformat(), int(mlbam_id))
    except Exception as e:
        return {**base, "Notes": f"Pull error: {e}"}
    if df is None or len(df) == 0:
        return {**base, "PA": 0, "Notes": "No Statcast rows in this range"}
    df = df[df["game_type"] == "R"]

    ev = df["events"].dropna()
    pa = len(ev)
    so = ev.isin(["strikeout", "strikeout_double_play"]).sum()
    hr = (ev == "home_run").sum()
    bb = df[df["type"] == "X"]
    n = len(bb)

    def pct(mask):
        return round(100 * mask.sum() / n, 1) if n else None

    fb = bb["bb_type"].isin(["fly_ball", "popup"]).sum()
    pull, straight, oppo = spray_buckets(bb) if n else (None, None, None)
    return {**base, "PA": pa,
            "K%": round(100 * so / pa, 1) if pa else None,
            "HR": int(hr), "BBE": n,
            "Avg EV": round(bb["launch_speed"].mean(), 1) if n else None,
            "Avg LA": round(bb["launch_angle"].mean(), 1) if n else None,
            "GB%": pct(bb["bb_type"] == "ground_ball"),
            "FB%": round(100 * fb / n, 1) if n else None,
            "LD%": pct(bb["bb_type"] == "line_drive"),
            "HR/FB": round(100 * hr / fb, 1) if fb else None,
            "Pull%": pull, "Straight%": straight, "Oppo%": oppo,
            "Notes": f"{start} to {end}"}


def main():
    in_path, half, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    todo = pd.read_csv(in_path)[["Player", "MLBAM ID", "Season"]].drop_duplicates()
    done = set()
    if os.path.exists(out_path):
        prev = pd.read_csv(out_path)
        prev = prev[~prev["Notes"].astype(str).str.startswith("Pull error")]
        prev.to_csv(out_path, index=False)
        done = set(zip(prev["MLBAM ID"], prev["Season"]))
    else:
        pd.DataFrame(columns=COLUMNS).to_csv(out_path, index=False)

    todo = [r for r in todo.itertuples(index=False) if (r[1], r[2]) not in done]
    print(f"{len(todo)} player-seasons to pull ({len(done)} already done)", flush=True)
    for i, (player, pid, season) in enumerate(todo, 1):
        row = pull_one(player, pid, season, half)
        pd.DataFrame([row], columns=COLUMNS).to_csv(out_path, mode="a", header=False, index=False)
        print(f"[{i}/{len(todo)}] {player} {season} {half}: PA={row.get('PA')}", flush=True)


if __name__ == "__main__":
    main()
