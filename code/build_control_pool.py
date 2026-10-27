"""
Build the matched-control candidate pool.

For each Derby year, pulls the All-Star Game roster from the public MLB Stats
API (statsapi.mlb.com), keeps position players only, and removes that year's
Derby participants (from data/Participants.csv, matched by MLBAM ID via
data/ID_Crosswalk.csv). Adds each candidate's plate appearances in each half
for the minimum-PA eligibility rule. Writes data/Control_Pool.csv.

"All-Star roster" here means players on the game's active roster. Selected
All-Stars who were injured and replaced do not appear, which is intended:
they are poor controls anyway.

PA is not an outcome variable, so using 2nd-half PA for eligibility does not
leak outcome information into the matching.

Usage (from the repo root):
    python code/build_control_pool.py
"""
import os
import json
import importlib.util
import urllib.request
import pandas as pd

API = "https://statsapi.mlb.com/api/v1"

# Half-season boundaries are shared with savant_pull.py.
_spec = importlib.util.spec_from_file_location(
    "savant_pull", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "data", "savant_pull.py"))
savant_pull = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(savant_pull)


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def asg_game(season):
    d = get(f"{API}/schedule?sportId=1&season={season}&gameType=A")
    games = [g for dt in d["dates"] for g in dt["games"]]
    return games[0]["gamePk"], games[0]["officialDate"]


def half_pa(mlbam_id, season, half):
    start, end = savant_pull.half_date_range(season, half)
    d = get(f"{API}/people/{mlbam_id}/stats?stats=byDateRange&group=hitting"
            f"&startDate={start}&endDate={end}&gameType=R")
    splits = d["stats"][0]["splits"] if d.get("stats") else []
    # The API returns one line per MLB team (sport id 1) plus a combined total
    # (sport id 0); use the total so traded players are counted once.
    total = [s for s in splits if s.get("sport", {}).get("id") == 0]
    lines = total or [s for s in splits if s.get("sport", {}).get("id") == 1]
    return sum(s["stat"]["plateAppearances"] for s in lines)


def main():
    parts = pd.read_csv("data/Participants.csv")
    xw = pd.read_csv("data/ID_Crosswalk.csv")
    parts = parts.merge(xw[["Player", "MLBAM ID (Savant)"]], on="Player", how="left")
    rows = []
    for season in sorted(parts.Year.unique()):
        pk, date = asg_game(season)
        box = get(f"{API}/game/{pk}/boxscore")
        derby_ids = set(parts.loc[parts.Year == season, "MLBAM ID (Savant)"])
        for side in ("away", "home"):
            league = box["teams"][side]["team"]["name"].split()[0][0] + "L"
            for p in box["teams"][side]["players"].values():
                pos = p["position"]["abbreviation"]
                pid = p["person"]["id"]
                if pos == "P" or pid in derby_ids:
                    continue
                rows.append({"Season": season, "Player": p["person"]["fullName"],
                             "MLBAM ID": pid, "League": league, "ASG Position": pos,
                             "ASG Date": date})
    out = pd.DataFrame(rows).sort_values(["Season", "Player"])
    for half in ("1st", "2nd"):
        out[f"{half} PA"] = [half_pa(pid, season, half)
                             for pid, season in zip(out["MLBAM ID"], out["Season"])]
    out.to_csv("data/Control_Pool.csv", index=False)
    print(out.groupby("Season").size().to_string())
    print(f"{len(out)} candidate player-seasons written to data/Control_Pool.csv")


if __name__ == "__main__":
    main()
