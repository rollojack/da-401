"""
Build the FanGraphs batted-ball table for the matched controls.

Reads data/Matched_Pairs.csv (from code/matching.R) and the FanGraphs Splits
Leaderboard copies in data/fangraphs_exports/{season}_{1st|2nd}.csv, and
writes data/FanGraphs_Batted_Ball_Splits_Controls.csv in the same layout as
data/FanGraphs_Batted_Ball_Splits_WithID.csv (the participants' table).

The exports have no player IDs, so controls are matched by accent-insensitive
name + season. Every match is checked against the MLB Stats API plate
appearances in data/Control_Pool.csv; a name match whose PA differs by more
than 5 is reported instead of written. FanGraphs IDs come from the Chadwick
register via pybaseball.

K% is not in the Batted Ball preset, so it is left blank here and taken from
Statcast (which matched FanGraphs K% exactly in spot checks).

Usage (from the repo root):
    python code/build_control_fangraphs.py
"""
import unicodedata
import pandas as pd
from pybaseball import playerid_reverse_lookup

SEASONS = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
STATS = ["Pull%", "Cent%", "Oppo%", "GB%", "FB%", "LD%", "HR/FB"]


def norm(name):
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return s.replace(".", "").replace(" jr", "").strip()


def load_exports():
    frames = []
    for season in SEASONS:
        for half in ("1st", "2nd"):
            f = pd.read_csv(f"data/fangraphs_exports/{season}_{half}.csv", encoding="utf-8-sig")
            for c in STATS:
                f[c] = f[c].astype(str).str.rstrip("%").astype(float)
            f["Season"], f["Half"] = season, half
            frames.append(f)
    ex = pd.concat(frames, ignore_index=True)
    ex["key"] = ex["Name"].map(norm)
    return ex


def main():
    pairs = pd.read_csv("data/Matched_Pairs.csv")
    pool = pd.read_csv("data/Control_Pool.csv")
    ex = load_exports()

    ids = playerid_reverse_lookup(pairs["control_id"].unique().tolist(), key_type="mlbam")
    fg_id = dict(zip(ids["key_mlbam"], ids["key_fangraphs"]))

    rows, problems = [], []
    for p in pairs.itertuples(index=False):
        for half in ("1st", "2nd"):
            hit = ex[(ex.key == norm(p.control)) & (ex.Season == p.season) & (ex.Half == half)]
            api_pa = pool.loc[(pool["MLBAM ID"] == p.control_id) & (pool.Season == p.season),
                              f"{half} PA"].iloc[0]
            if len(hit) > 1:   # same name, different players: keep the one whose PA fits
                hit = hit[(hit.PA - api_pa).abs() <= 5]
            if len(hit) != 1 or abs(hit.PA.iloc[0] - api_pa) > 5:
                problems.append(f"{p.control} {p.season} {half}: {len(hit)} match(es), API PA {api_pa}")
                continue
            r = hit.iloc[0]
            rows.append({"Player": p.control, "MLBAM ID": p.control_id,
                         "FanGraphs ID": fg_id.get(p.control_id), "Season": p.season,
                         "Half": half, "PA": int(r.PA), **{c: r[c] for c in STATS},
                         "K%": None, "Matched To": p.participant})

    out = pd.DataFrame(rows)
    out["FanGraphs ID"] = out["FanGraphs ID"].astype("Int64")
    out.to_csv("data/FanGraphs_Batted_Ball_Splits_Controls.csv", index=False)
    print(f"Wrote {len(out)} rows ({out['MLBAM ID'].nunique()} players) "
          f"to data/FanGraphs_Batted_Ball_Splits_Controls.csv")
    if problems:
        print("Could not match:")
        print("\n".join("  " + x for x in problems))


if __name__ == "__main__":
    main()
