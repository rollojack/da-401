HR Derby Data Collection Files (CSV)
=====================================

Participants.csv                    - all 88 Derby appearances, 2015-2026 (2020 cancelled/excluded)
ID_Crosswalk.csv                    - 67 unique players; run crosswalk_lookup.py to fill in the ID columns
Savant_Batted_Ball.csv              - one row per player-season-half; pull from Baseball Savant
FanGraphs_Batted_Ball_Splits.csv    - one row per player-season-half; pull via FanGraphs' Splits Leaderboards (stat group "Batted Ball", Split = 1st/2nd Half)
Controls.csv                        - candidate non-participant controls, matched by approach cluster

Each file's first data row (after the header) is a worked example - overwrite or delete it once
you start entering real rows. Do not edit the Player/Year columns in Participants.csv or
ID_Crosswalk.csv; other files will eventually key off these exact names.

Dates in Participants.csv should be verified against Baseball-Reference's season schedule before
you use them to define first-half/second-half splits.
