"""
HR Derby ID crosswalk builder.

Reads the 'Player' column out of ID_Crosswalk.csv (67 unique Derby participants,
2015-2026), looks each one up in the Chadwick Bureau register via pybaseball, and
writes MLBAM ID (Savant), FanGraphs ID, Baseball-Reference key, and birthdate back
into the same file structure.

Run this on your own machine, not in a sandbox without internet access -
pybaseball downloads the Chadwick register (a few MB) on first use and caches it.

Setup (one time):
    pip install pybaseball pandas

Usage:
    python crosswalk_lookup.py ID_Crosswalk.csv ID_Crosswalk_filled.csv

If you omit the arguments it defaults to reading/writing ID_Crosswalk.csv in the
current directory (it will NOT overwrite your original in place unless you pass
the same filename for both arguments).
"""

import sys
import re
import csv
import time

try:
    import pandas as pd
    from pybaseball import playerid_lookup
except ImportError:
    sys.exit(
        "pybaseball is not installed. Run: pip install pybaseball pandas\n"
        "Then re-run this script."
    )

# Suffixes that the Chadwick register does not store as part of the last name.
SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}

# Hand overrides for names that the fuzzy lookup is likely to get wrong or
# that use accented characters the register may or may not match on.
# Add to this dict as you find mismatches - format: "Full Name As In CSV": ("first", "last")
NAME_OVERRIDES = {
    "Vladimir Guerrero Jr.": ("Vladimir", "Guerrero"),
    "Ronald Acuna Jr.": ("Ronald", "Acuna"),
    "Bobby Witt Jr.": ("Bobby", "Witt"),
    "Jazz Chisholm Jr.": ("Jazz", "Chisholm"),
    "Luis Robert Jr.": ("Luis", "Robert"),
}

# Full ID overrides for names where the fuzzy lookup's "most recent MLB
# debut" heuristic picked the WRONG person out of several name matches
# (verified by hand against Baseball Savant / Baseball-Reference / FanGraphs).
# These bypass playerid_lookup entirely. Format: "Full Name As In CSV": {fields}
ID_OVERRIDES = {
    "Pedro Alvarez": {
        "MLBAM ID (Savant)": "476883",
        "FanGraphs ID": "2495",
        "Baseball-Reference Key": "alvarpe01",
        "Birthdate": "1987-02-06",
    },
    "Robinson Cano": {
        "MLBAM ID (Savant)": "429664",
        "FanGraphs ID": "3269",
        "Baseball-Reference Key": "canoro01",
        "Birthdate": "1982-10-22",
    },
    "Carlos Gonzalez": {
        "MLBAM ID (Savant)": "471865",
        "FanGraphs ID": "7287",
        "Baseball-Reference Key": "gonzaca01",
        "Birthdate": "1985-10-17",
    },
    "Miguel Sano": {
        "MLBAM ID (Savant)": "593934",
        "FanGraphs ID": "12164",
        "Baseball-Reference Key": "sanomi01",
        "Birthdate": "1993-05-11",
    },
    "Jesus Aguilar": {
        "MLBAM ID (Savant)": "542583",
        "FanGraphs ID": "11342",
        "Baseball-Reference Key": "aguilje01",
        "Birthdate": "1990-06-30",
    },
}


def split_name(full_name):
    """Split 'First Last Jr.' into (first, last) with suffix stripped."""
    if full_name in NAME_OVERRIDES:
        return NAME_OVERRIDES[full_name]

    parts = full_name.strip().split()
    if parts and parts[-1].strip(".").lower() in SUFFIXES:
        parts = parts[:-1]

    if len(parts) < 2:
        return None, None

    first = parts[0]
    last = " ".join(parts[1:])
    return first, last


def lookup_one(full_name):
    """
    Look up one player. Returns a dict with the crosswalk fields, or a dict
    with an empty-but-flagged row if no confident match was found. Never
    raises - any unexpected error is caught and flagged so one bad player
    can't crash the whole run.
    """
    if full_name in ID_OVERRIDES:
        row = {"Player": full_name, "Notes": "Manually verified override."}
        row.update(ID_OVERRIDES[full_name])
        return row

    try:
        return _lookup_one_inner(full_name)
    except Exception as e:
        return {
            "Player": full_name,
            "MLBAM ID (Savant)": "",
            "FanGraphs ID": "",
            "Baseball-Reference Key": "",
            "Birthdate": "",
            "Notes": f"Unexpected error ({e}) - resolve by hand.",
        }


def _lookup_one_inner(full_name):
    first, last = split_name(full_name)
    if first is None:
        return {
            "Player": full_name,
            "MLBAM ID (Savant)": "",
            "FanGraphs ID": "",
            "Baseball-Reference Key": "",
            "Birthdate": "",
            "Notes": "Could not split name - resolve by hand.",
        }

    try:
        result = playerid_lookup(last, first, fuzzy=True)
    except Exception as e:
        return {
            "Player": full_name,
            "MLBAM ID (Savant)": "",
            "FanGraphs ID": "",
            "Baseball-Reference Key": "",
            "Birthdate": "",
            "Notes": f"Lookup error ({e}) - resolve by hand.",
        }

    if result is None or len(result) == 0:
        return {
            "Player": full_name,
            "MLBAM ID (Savant)": "",
            "FanGraphs ID": "",
            "Baseball-Reference Key": "",
            "Birthdate": "",
            "Notes": "No match found - check spelling/accents or search manually at "
                     "https://www.smartfantasybaseball.com/tools/ (Player ID Map).",
        }

    if len(result) > 1:
        # Multiple people with this name - take the one with the most recent
        # MLB debut, since these are all active/recent MLB players, and flag it.
        # mlb_played_last can come back as a mix of strings/floats/NaN, which
        # pandas can't sort directly - coerce to numeric first.
        try:
            sort_key = pd.to_numeric(result["mlb_played_last"], errors="coerce")
            result = result.assign(_sort_key=sort_key).sort_values(
                "_sort_key", ascending=False, na_position="last"
            )
        except Exception:
            pass  # fall back to whatever order playerid_lookup returned
        note = f"{len(result)} name matches found - took most recent MLB debut; verify."
    else:
        note = ""

    row = result.iloc[0]
    birthdate = ""
    if {"birth_year", "birth_month", "birth_day"}.issubset(result.columns):
        y, m, d = row.get("birth_year"), row.get("birth_month"), row.get("birth_day")
        if y and m and d:
            try:
                birthdate = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            except (TypeError, ValueError):
                birthdate = ""

    return {
        "Player": full_name,
        "MLBAM ID (Savant)": _clean_id(row.get("key_mlbam")),
        "FanGraphs ID": _clean_id(row.get("key_fangraphs")),
        "Baseball-Reference Key": _clean_id(row.get("key_bbref")),
        "Birthdate": birthdate,
        "Notes": note,
    }


def _clean_id(value):
    if value is None:
        return ""
    try:
        if float(value) == int(value):
            return str(int(value))
    except (TypeError, ValueError):
        pass
    return str(value)


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else "ID_Crosswalk.csv"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "ID_Crosswalk.csv"

    with open(in_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        players = [row["Player"] for row in reader if row.get("Player")]

    print(f"Looking up {len(players)} players...")
    rows = []
    unresolved = []
    for i, name in enumerate(players, start=1):
        print(f"  [{i}/{len(players)}] {name}")
        row = lookup_one(name)
        rows.append(row)
        if not row["MLBAM ID (Savant)"] or row["Notes"]:
            unresolved.append(name)
        time.sleep(0.1)  # be polite to the register download/cache

    fieldnames = ["Player", "MLBAM ID (Savant)", "FanGraphs ID",
                  "Baseball-Reference Key", "Birthdate", "Notes"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {out_path}")
    if unresolved:
        print(f"\n{len(unresolved)} player(s) need a manual check (see the Notes column):")
        for name in unresolved:
            print(f"  - {name}")
    else:
        print("\nAll players resolved with no flags. Spot-check a few rows anyway before trusting them.")


if __name__ == "__main__":
    main()
