"""
Build the analysis dataset: one row per player-season for every eligible
Derby participant (matched or not) and every matched control.

Primary outcome (research design): Pull-Air Index = mean of standardized
FanGraphs Pull% and FB%. Both halves are standardized with the FIRST-HALF mean
and SD of the full eligible sample (all eligible participants + all eligible
All-Star candidates), so a change in the index reflects a real shift in level.

Covariates for regression adjustment are the first-half matching variables
(Statcast), since matching left some residual imbalance.

Inputs (data/): Matched_Pairs.csv, Unmatched_Participants.csv,
    FanGraphs_Batted_Ball_Splits_WithID.csv (participants),
    FanGraphs_Batted_Ball_Splits_Controls.csv (controls),
    fangraphs_exports/ (for the eligible-sample reference stats),
    Statcast_Participants_H1.csv, Statcast_Pool_H1.csv, Control_Pool.csv,
    Savant_Batted_Ball.csv (participants' PA),
    Statcast_HR_Participants.csv, Statcast_HR_Controls.csv (HR spray)
Outputs (data/): Analysis_Dataset.csv, PAI_Reference_Stats.csv

Usage (from the repo root):
    python code/build_analysis_dataset.py
"""
import pandas as pd
from build_control_fangraphs import load_exports, norm

MIN_PA = 150          # must match code/matching.R
SWING_REGIME_FROM = 2026


def main():
    pairs = pd.read_csv("data/Matched_Pairs.csv")
    unmatched = pd.read_csv("data/Unmatched_Participants.csv")
    fg_p = pd.read_csv("data/FanGraphs_Batted_Ball_Splits_WithID.csv")
    fg_c = pd.read_csv("data/FanGraphs_Batted_Ball_Splits_Controls.csv")
    sc = pd.concat([pd.read_csv("data/Statcast_Participants_H1.csv"),
                    pd.read_csv("data/Statcast_Pool_H1.csv")]).drop_duplicates(["MLBAM ID", "Season"])
    pool = pd.read_csv("data/Control_Pool.csv")
    savant = pd.read_csv("data/Savant_Batted_Ball.csv")
    ex = load_exports()

    # ---- Reference stats: first half, full eligible sample ----
    # Participants: their own FanGraphs rows. Candidates: export rows matched
    # by name + season and checked against MLB Stats API PA.
    pa_h2 = savant[savant.Half == "2nd"].set_index(["MLBAM ID", "Season"])["PA"]
    sc = sc.join(pa_h2.rename("PA_h2"), on=["MLBAM ID", "Season"])
    sc = sc.merge(pool[["MLBAM ID", "Season", "2nd PA"]], on=["MLBAM ID", "Season"], how="left")
    sc["PA_h2"] = sc["PA_h2"].fillna(sc["2nd PA"])
    elig = sc[(sc.PA >= MIN_PA) & (sc.PA_h2 >= MIN_PA)]

    ref_rows, missed = [], []
    h1 = ex[ex.Half == "1st"]
    for r in elig.itertuples(index=False):
        hit = h1[(h1.key == norm(r.Player)) & (h1.Season == r.Season)]
        hit = hit[(hit.PA - r.PA).abs() <= 5]
        if len(hit) == 1:
            ref_rows.append(hit.iloc[0][["Pull%", "FB%"]])
        else:
            missed.append(f"{r.Player} {r.Season}")
    ref_sample = pd.DataFrame(ref_rows)
    ref = pd.DataFrame({"variable": ["Pull%", "FB%"],
                        "mean": [ref_sample["Pull%"].mean(), ref_sample["FB%"].mean()],
                        "sd": [ref_sample["Pull%"].std(), ref_sample["FB%"].std()],
                        "n": len(ref_sample)})
    ref.to_csv("data/PAI_Reference_Stats.csv", index=False)
    print(f"Reference sample: {len(ref_sample)} of {len(elig)} eligible player-seasons")
    if missed:
        print("Not found in exports (left out of reference stats): " + ", ".join(missed))

    # ---- Wide table: one row per player-season ----
    fg = pd.concat([fg_p, fg_c.drop(columns=["Matched To"])], ignore_index=True)
    fg = fg.rename(columns={"MLBAM ID": "mlbam_id"})
    # participants' FanGraphs file has no MLBAM ID column - add it from Savant
    ids = savant[["Player", "MLBAM ID"]].drop_duplicates().rename(columns={"MLBAM ID": "pid"})
    fg = fg.merge(ids, on="Player", how="left")
    fg["mlbam_id"] = fg["mlbam_id"].fillna(fg["pid"]).astype(int)

    def half(h):
        cols = ["PA", "Pull%", "FB%", "HR/FB"]
        d = fg[fg.Half == h][["mlbam_id", "Season"] + cols]
        return d.rename(columns={c: f"{c}_{h}" for c in cols})

    people = pd.concat([
        pd.DataFrame({"group": "derby", "player": pairs.participant, "mlbam_id": pairs.participant_id,
                      "season": pairs.season, "pair_id": range(1, len(pairs) + 1), "matched": 1}),
        pd.DataFrame({"group": "control", "player": pairs.control, "mlbam_id": pairs.control_id,
                      "season": pairs.season, "pair_id": range(1, len(pairs) + 1), "matched": 1}),
        pd.DataFrame({"group": "derby", "player": unmatched.player, "mlbam_id": unmatched.mlbam_id,
                      "season": unmatched.season, "pair_id": pd.NA, "matched": 0}),
    ], ignore_index=True)
    people["regime"] = (people.season >= SWING_REGIME_FROM).map({True: "swing", False: "timer"})

    d = people
    for h in ("1st", "2nd"):
        d = d.merge(half(h), left_on=["mlbam_id", "season"], right_on=["mlbam_id", "Season"],
                    how="left").drop(columns="Season")

    # Pull-Air Index with first-half reference stats for BOTH halves
    m = ref.set_index("variable")
    for h in ("1st", "2nd"):
        zp = (d[f"Pull%_{h}"] - m.loc["Pull%", "mean"]) / m.loc["Pull%", "sd"]
        zf = (d[f"FB%_{h}"] - m.loc["FB%", "mean"]) / m.loc["FB%", "sd"]
        d[f"PAI_{h}"] = (zp + zf) / 2
    d["PAI_change"] = d["PAI_2nd"] - d["PAI_1st"]
    d["HR/FB_change"] = d["HR/FB_2nd"] - d["HR/FB_1st"]

    # First-half Statcast covariates (the matching variables)
    cov = sc[["MLBAM ID", "Season", "Pull%", "FB%", "K%", "HR/FB", "Avg EV", "Avg LA"]]
    cov.columns = ["mlbam_id", "season", "sc_pull_h1", "sc_fb_h1", "k_pct_h1",
                   "sc_hr_fb_h1", "avg_ev_h1", "avg_la_h1"]
    d = d.merge(cov, on=["mlbam_id", "season"], how="left")

    # HR spray (secondary outcome) - classified automatically from Statcast hit
    # coordinates for both groups (code/hr_spray_statcast.py). HR_Pull% is the
    # share of classifiable home runs that were pulled; home runs with no
    # coordinates count toward HR_{half} but not toward HR_Pull%.
    hrs = pd.concat([pd.read_csv("data/Statcast_HR_Participants.csv"),
                     pd.read_csv("data/Statcast_HR_Controls.csv")])
    hrs = hrs.drop_duplicates(["MLBAM ID", "Season", "game_date", "hc_x", "hc_y"])
    keys = ["MLBAM ID", "Season", "Half"]
    spray = pd.DataFrame({
        "HR": hrs.groupby(keys).size(),
        "classified": hrs.dropna(subset=["direction"]).groupby(keys).size(),
        "pulled": hrs[hrs.direction == "pull"].groupby(keys).size(),
    }).fillna(0).reset_index()
    spray["HR_Pull%"] = 100 * spray.pulled / spray.classified.where(spray.classified > 0)
    for h in ("1st", "2nd"):
        s = spray[spray.Half == h][["MLBAM ID", "Season", "HR_Pull%", "HR"]]
        s.columns = ["mlbam_id", "season", f"HR_Pull%_{h}", f"HR_{h}"]
        d = d.merge(s, on=["mlbam_id", "season"], how="left")
        d[f"HR_{h}"] = d[f"HR_{h}"].fillna(0).astype(int)   # no rows = no home runs
    d["HR_Pull%_change"] = d["HR_Pull%_2nd"] - d["HR_Pull%_1st"]

    d.to_csv("data/Analysis_Dataset.csv", index=False)
    print(f"Wrote {len(d)} rows to data/Analysis_Dataset.csv "
          f"({(d.group == 'derby').sum()} derby, {(d.group == 'control').sum()} control)")
    print("Rows missing the primary outcome:", d.PAI_change.isna().sum())


if __name__ == "__main__":
    main()
