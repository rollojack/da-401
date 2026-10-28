"""
Classify every home run as pull / middle / oppo from Statcast hit coordinates.

Automated alternative to hand-coding HR spray from Savant spray charts. For
each player-season, pulls the season's Statcast data once, keeps regular-season
home runs, assigns each to a half using savant_pull.py's All-Star dates, and
computes the spray angle from (hc_x, hc_y), flipped by the batter's side for
that pitch so "pull" always means the batter's pull side.

Classification: pull if the pull-side angle is more than THRESHOLD degrees,
oppo if less than -THRESHOLD, middle otherwise. The angle itself is saved, so
other thresholds can be checked without re-pulling.

Input CSV needs columns: Player, MLBAM ID, Season
Output: one row per home run (appended; re-running skips player-seasons
already in the output).

Usage (from the repo root):
    python code/hr_spray_statcast.py data/Participants_WithID.csv data/Statcast_HR_Participants.csv
"""
import os
import sys
import math
import importlib.util
from datetime import date

import pandas as pd
from pybaseball import statcast_batter

THRESHOLD = 15

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "savant_pull", os.path.join(HERE, "..", "data", "savant_pull.py"))
savant_pull = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(savant_pull)

COLUMNS = ["Player", "MLBAM ID", "Season", "Half", "game_date", "stand",
           "hc_x", "hc_y", "pull_angle", "direction"]


def classify(angle):
    if pd.isna(angle):
        return None
    if angle > THRESHOLD:
        return "pull"
    if angle < -THRESHOLD:
        return "oppo"
    return "middle"


def pull_season(player, mlbam_id, season):
    asg = savant_pull.ALL_STAR_GAME_DATE[int(season)]
    df = statcast_batter(f"{season}-01-01", f"{season}-12-31", int(mlbam_id))
    df = df[(df["game_type"] == "R") & (df["events"] == "home_run")].copy()
    angle = (df["hc_x"] - 125.42).combine(198.27 - df["hc_y"], math.atan2) * 180 / math.pi
    # Negative angle = toward left field, which is a RHB's pull side.
    df["pull_angle"] = angle.where(df["stand"] == "L", -angle).round(1)
    df["direction"] = df["pull_angle"].map(classify)
    df["Half"] = ["1st" if d <= asg else "2nd"
                  for d in pd.to_datetime(df["game_date"]).dt.date]
    df["Player"], df["MLBAM ID"], df["Season"] = player, mlbam_id, season
    return df[COLUMNS]


def main():
    in_path, out_path = sys.argv[1], sys.argv[2]
    todo = pd.read_csv(in_path)[["Player", "MLBAM ID", "Season"]].drop_duplicates()
    done = set()
    if os.path.exists(out_path):
        prev = pd.read_csv(out_path)
        done = set(zip(prev["MLBAM ID"], prev["Season"]))
    else:
        pd.DataFrame(columns=COLUMNS).to_csv(out_path, index=False)
    # A player-season with zero home runs writes no rows; track it separately.
    done_path = out_path.replace(".csv", "_done.txt")
    if os.path.exists(done_path):
        done |= {tuple(map(int, l.split(","))) for l in open(done_path) if l.strip()}

    todo = [r for r in todo.itertuples(index=False) if (r[1], r[2]) not in done]
    print(f"{len(todo)} player-seasons to pull", flush=True)
    for i, (player, pid, season) in enumerate(todo, 1):
        try:
            hrs = pull_season(player, pid, season)
        except Exception as e:
            print(f"[{i}/{len(todo)}] {player} {season}: ERROR {e}", flush=True)
            continue
        hrs.to_csv(out_path, mode="a", header=False, index=False)
        with open(done_path, "a") as f:
            f.write(f"{pid},{season}\n")
        print(f"[{i}/{len(todo)}] {player} {season}: {len(hrs)} HR", flush=True)


if __name__ == "__main__":
    main()
