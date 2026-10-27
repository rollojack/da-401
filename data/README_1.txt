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

Data provenance (important for the methods section - these two files mix sources)
-----------------------------------------------------------------------------------
Savant_Batted_Ball.csv and FanGraphs_Batted_Ball_Splits.csv are NOT two independent
measurements of the same thing - they use different classification systems, and (as of the
savant_pull.py script) one file even contains columns sourced from the other site. Cite each
column by its actual source, not just by the file it lives in:

  Statcast / Baseball Savant sourced (via savant_pull.py, pybaseball's statcast_batter):
      PA, Avg EV, Max EV, Avg LA, Barrel%, HardHit%, SweetSpot%, Bat Speed, Swing Length.
      These are direct physical measurements / Statcast's own algorithmic classification
      (e.g. Barrel = launch_speed_angle == 6). They should match Baseball Savant's site
      numbers closely for the same date range - if they don't, that's a pull bug, not a
      methodology choice.

  FanGraphs / Baseball Info Solutions (BIS) sourced:
      - Everything in FanGraphs_Batted_Ball_Splits.csv (Pull%, Cent%, Oppo%, GB%, FB%, LD%,
        HR/FB, K%) comes from FanGraphs' Splits Leaderboards, which for the "Batted Ball"
        stat group uses BIS's human-scored batted-ball classifications, not Statcast.
      - Pull% / Straight% / Oppo% in Savant_Batted_Ball.csv are ALSO filled from FanGraphs'
        Pull%/Cent%/Oppo% (see manual_pull_checklist.csv), because Baseball Savant has no
        built-in tool for a custom half-season spray-direction breakdown. So despite living
        in the "Savant" file, these three columns are BIS-sourced, not Statcast-sourced.

  Known, expected disagreement - not a bug:
      GB%/FB%/LD% in Savant_Batted_Ball.csv (computed from Statcast's bb_type field) will
      NOT match GB%/FB%/LD% in FanGraphs_Batted_Ball_Splits.csv (BIS-scored) for the same
      player-season-half. This is a well-documented difference between the two
      classification systems, not an error in either pull. Cite Baseball Savant/Statcast as
      the source for the Savant file's GB%/FB%/LD%, and BIS/FanGraphs for the FanGraphs
      file's version, rather than treating either as a check on the other.

  What SHOULD match closely between the two files, and is worth checking if it doesn't:
      PA for the same player-season-half. This is a plain count, not a classification call,
      so Statcast and FanGraphs should agree almost exactly. A real mismatch here (more than
      a couple of PA) points to a wrong half-boundary date or a pull error, not a methodology
      difference - go back and check ALL_STAR_GAME_DATE in savant_pull.py for that season.
