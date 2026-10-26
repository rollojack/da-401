"""
HR Derby Savant batted-ball puller.

Reads Participants.csv (Year, Player) and ID_Crosswalk.csv (Player -> MLBAM ID),
pulls Statcast pitch-level data for each player for the first and second half of
each Derby season via pybaseball, aggregates it into batted-ball metrics, and
writes Savant_Batted_Ball.csv.

WHAT THIS SCRIPT FILLS IN AUTOMATICALLY:
    PA, Avg EV, Max EV, Avg LA, Barrel%, HardHit%, SweetSpot%, GB%, FB%, LD%,
    Bat Speed, Swing Length (the last two only exist in Statcast data from
    2024 onward - they'll come back blank for earlier seasons).

WHAT THIS SCRIPT LEAVES BLANK ON PURPOSE, AND WHY:
    Pull% / Straight% / Oppo% - Statcast's spray-angle bucketing isn't
        precisely documented publicly. Every "reproduce it from hc_x/hc_y"
        formula floating around the sabermetrics community is an
        approximation, and a subtly wrong one would quietly put wrong
        numbers into your actual research data with no error message.
        Baseball Savant's own Custom Leaderboards tool computes these
        correctly - see the printed instructions below.
    xwOBA / xSLG - the season/half aggregate Savant displays on its site
        is not simply the average of the per-batted-ball expected wOBA
        column; it blends in the actual wOBA value of non-batted-ball
        outcomes (walks, strikeouts, HBP) using MLB average constants.
        Getting this exactly right requires replicating Savant's formula
        constants for the specific season, which isn't worth the risk of a
        silent mismatch - pull it from Custom Leaderboards instead.
    Attack Angle - not a standard column in the public Statcast pitch-level
        export as of this writing.
    HR Pull%/Middle%/Oppo% (manual) - already labeled manual in the
        original template; unchanged here.

For everything left blank, the script prints a checklist per player-season-half
with the exact filters to use in Baseball Savant's Custom Leaderboards
(https://baseballsavant.mlb.com/leaderboard/custom) and FanGraphs' Splits
Leaderboards tool, plus a clickable Statcast Search link so you can eyeball
the underlying batted balls for that date range if you want to sanity-check
anything.

Run this on your own machine, not in a sandbox without internet access -
pybaseball hits Baseball Savant's Statcast Search endpoint directly and
downloads a few MB per player-half.

Setup (one time):
    pip install pybaseball pandas

Usage:
    python savant_pull.py
        (reads Participants.csv and ID_Crosswalk.csv from the current
        directory, writes Savant_Batted_Ball.csv and prints the manual-pull
        checklist to the console and to manual_pull_checklist.csv)

    python savant_pull.py Participants.csv ID_Crosswalk.csv Savant_Batted_Ball.csv
        (explicit paths, in case you're not running it from the data folder)
"""

import sys
import csv
import time
from datetime import date, timedelta

try:
    import pandas as pd
    from pybaseball import statcast_batter
except ImportError:
    sys.exit(
        "pybaseball is not installed. Run: pip install pybaseball pandas\n"
        "Then re-run this script."
    )

# All-Star Game date per season - this defines the 1st/2nd half boundary used
# below (1st half = through the ASG date, 2nd half = the day after through
# year end). VERIFY AGAINST BASEBALL-REFERENCE'S SEASON SCHEDULE before
# trusting these, per the README - these were pulled from public sources but
# not independently re-checked against Baseball-Reference game logs.
ALL_STAR_GAME_DATE = {
    2015: date(2015, 7, 14),
    2016: date(2016, 7, 12),
    2017: date(2017, 7, 11),
    2018: date(2018, 7, 17),
    2019: date(2019, 7, 9),
    # 2020 Derby cancelled - excluded.
    2021: date(2021, 7, 13),
    2022: date(2022, 7, 19),
    2023: date(2023, 7, 11),
    2024: date(2024, 7, 16),
    2025: date(2025, 7, 15),
    2026: date(2026, 7, 14),
}

SAVANT_FIELDNAMES = [
    "Player", "MLBAM ID", "Season", "Half", "PA", "Avg EV", "Max EV", "Avg LA",
    "Barrel%", "HardHit%", "SweetSpot%", "Pull%", "Straight%", "Oppo%",
    "GB%", "FB%", "LD%", "xwOBA", "xSLG", "Bat Speed", "Swing Length",
    "Attack Angle", "HR Pull% (manual)", "HR Middle% (manual)", "HR Oppo% (manual)",
    "Notes",
]

CHECKLIST_FIELDNAMES = [
    "Player", "Season", "Half", "MLBAM ID", "FanGraphs ID",
    "Date Range", "Savant Statcast Search Link", "Savant Custom Leaderboard Instructions",
    "FanGraphs Splits Instructions",
]


def half_date_range(season, half):
    asg = ALL_STAR_GAME_DATE.get(int(season))
    if asg is None:
        return None, None
    if half == "1st":
        return date(int(season), 1, 1), asg
    return asg + timedelta(days=1), date(int(season), 12, 31)


def savant_search_link(mlbam_id, start, end):
    return (
        "https://baseballsavant.mlb.com/statcast_search?"
        f"hfGT=R%7C&game_date_gt={start}&game_date_lt={end}"
        f"&player_type=batter&batters_lookup%5B%5D={mlbam_id}#results"
    )


def pull_one(player, mlbam_id, season, half):
    start, end = half_date_range(season, half)
    base = {"Player": player, "MLBAM ID": mlbam_id, "Season": season, "Half": half}

    if start is None:
        return {**base, "Notes": f"No All-Star date on file for {season} - "
                                  f"add it to ALL_STAR_GAME_DATE in this script."}

    if not mlbam_id:
        return {**base, "Notes": "No MLBAM ID in the crosswalk - fill that in first."}

    try:
        df = statcast_batter(start.isoformat(), end.isoformat(), int(mlbam_id))
    except Exception as e:
        return {**base, "Notes": f"Pull error ({e}) - resolve by hand."}

    if df is None or len(df) == 0:
        return {**base, "Notes": "No Statcast rows returned for this range - "
                                  "check the MLBAM ID and date range."}

    # Regular season only - drop spring training / All-Star Game / postseason.
    if "game_type" in df.columns:
        df = df[df["game_type"] == "R"]

    pa = int(df["events"].notna().sum()) if "events" in df.columns else None

    bb = df[df["type"] == "X"].copy() if "type" in df.columns else df.iloc[0:0].copy()
    n_bb = len(bb)

    def pct(mask):
        return round(100 * mask.sum() / n_bb, 1) if n_bb else None

    def avg(col):
        return round(bb[col].mean(), 1) if col in bb.columns and n_bb and bb[col].notna().any() else None

    row = {
        **base,
        "PA": pa,
        "Avg EV": avg("launch_speed"),
        "Max EV": round(bb["launch_speed"].max(), 1) if "launch_speed" in bb.columns and n_bb and bb["launch_speed"].notna().any() else None,
        "Avg LA": avg("launch_angle"),
        "Barrel%": pct(bb["launch_speed_angle"] == 6) if "launch_speed_angle" in bb.columns else None,
        "HardHit%": pct(bb["launch_speed"] >= 95) if "launch_speed" in bb.columns else None,
        "SweetSpot%": pct(bb["launch_angle"].between(8, 32)) if "launch_angle" in bb.columns else None,
        "GB%": pct(bb["bb_type"] == "ground_ball") if "bb_type" in bb.columns else None,
        "FB%": pct(bb["bb_type"].isin(["fly_ball", "popup"])) if "bb_type" in bb.columns else None,
        "LD%": pct(bb["bb_type"] == "line_drive") if "bb_type" in bb.columns else None,
        "Bat Speed": avg("bat_speed") if "bat_speed" in bb.columns else None,
        "Swing Length": avg("swing_length") if "swing_length" in bb.columns else None,
        # Left blank on purpose - see module docstring and the printed checklist.
        "Pull%": None, "Straight%": None, "Oppo%": None,
        "xwOBA": None, "xSLG": None, "Attack Angle": None,
        "HR Pull% (manual)": None, "HR Middle% (manual)": None, "HR Oppo% (manual)": None,
        "Notes": f"Auto-pulled: {n_bb} batted balls, {pa if pa is not None else '?'} PA "
                 f"({start} to {end}). Pull/Straight/Oppo, xwOBA, xSLG, Attack Angle "
                 f"left blank - see manual_pull_checklist.csv.",
    }
    return row


def build_checklist_row(player, mlbam_id, fangraphs_id, season, half):
    start, end = half_date_range(season, half)
    date_range = f"{start} to {end}" if start else "unknown - add ASG date for this season"
    return {
        "Player": player,
        "Season": season,
        "Half": half,
        "MLBAM ID": mlbam_id,
        "FanGraphs ID": fangraphs_id,
        "Date Range": date_range,
        "Savant Statcast Search Link": savant_search_link(mlbam_id, start, end) if mlbam_id and start else "",
        "Savant Custom Leaderboard Instructions": (
            "NOTE: Baseball Savant's Custom Leaderboards tool (baseballsavant.mlb.com/leaderboard/custom) "
            "only filters by whole season, not a custom date range - it can't give a half-season "
            "breakdown. Use the Statcast Search link in the previous column instead to spot-check "
            "individual batted balls for this date range (PA, Avg EV, Max EV, Avg LA, Barrel%, "
            "HardHit%, SweetSpot%, GB%/FB%/LD% - all computed from this same data in Savant_Batted_Ball.csv). "
            "For Pull%/Straight%/Oppo% and xwOBA/xSLG, use the FanGraphs Splits instructions in the next "
            "column instead (FanGraphs' Pull%/Cent%/Oppo% is the source for those three columns in "
            "Savant_Batted_Ball.csv too - see README.txt's Data Provenance section)."
        ),
        "FanGraphs Splits Instructions": (
            f"fangraphs.com -> search this player (FanGraphs ID {fangraphs_id}) -> "
            f"Splits tab -> Stat Presets: Batted Ball, Split (under Monthly): "
            f"{'1st Half' if half == '1st' else '2nd Half'}, Season: {season}. "
            f"Gives Pull%, Cent%, Oppo%, GB%, FB%, LD%, HR/FB, K% for this half."
        ),
    }


def main():
    participants_path = sys.argv[1] if len(sys.argv) > 1 else "Participants.csv"
    crosswalk_path = sys.argv[2] if len(sys.argv) > 2 else "ID_Crosswalk.csv"
    out_path = sys.argv[3] if len(sys.argv) > 3 else "Savant_Batted_Ball.csv"

    with open(crosswalk_path, newline="", encoding="utf-8") as f:
        crosswalk = {r["Player"]: r for r in csv.DictReader(f)}

    with open(participants_path, newline="", encoding="utf-8") as f:
        participants = [r for r in csv.DictReader(f) if r.get("Player")]

    # One row per player-season (both halves), de-duplicated in case a
    # player appears more than once in a season.
    pairs = sorted({(r["Player"], r["Year"]) for r in participants})

    savant_rows = []
    checklist_rows = []
    print(f"Pulling Statcast data for {len(pairs)} player-seasons (2 halves each)...")
    for i, (player, season) in enumerate(pairs, start=1):
        mlbam_id = crosswalk.get(player, {}).get("MLBAM ID (Savant)", "")
        fangraphs_id = crosswalk.get(player, {}).get("FanGraphs ID", "")
        for half in ("1st", "2nd"):
            print(f"  [{i}/{len(pairs)}] {player} {season} {half} half")
            savant_rows.append(pull_one(player, mlbam_id, season, half))
            checklist_rows.append(build_checklist_row(player, mlbam_id, fangraphs_id, season, half))
            time.sleep(0.3)  # be polite to Savant's search endpoint

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SAVANT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(savant_rows)

    checklist_path = "manual_pull_checklist.csv"
    with open(checklist_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CHECKLIST_FIELDNAMES)
        writer.writeheader()
        writer.writerows(checklist_rows)

    flagged = [r for r in savant_rows if r.get("Notes", "").startswith(("No ", "Pull error"))]
    print(f"\nWrote {len(savant_rows)} rows to {out_path}")
    print(f"Wrote the manual-pull checklist to {checklist_path} "
          f"({len(checklist_rows)} player-season-half rows).")
    if flagged:
        print(f"\n{len(flagged)} row(s) failed to pull (see Notes column):")
        for r in flagged:
            print(f"  - {r['Player']} {r['Season']} {r['Half']}: {r['Notes']}")


if __name__ == "__main__":
    main()
