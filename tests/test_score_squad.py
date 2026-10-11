"""Tests for Analyzer.scoreSquad. Scores the squad checked in at
2025-26/team_of_the_season.txt and expects the point totals recorded in that
file (the same ones test_best_team_regression.py checks findBestSquad against).
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "season_2025_26"
TEAM_OF_SEASON_FILE = REPO_ROOT / "2025-26" / "team_of_the_season.txt"
sys.path.insert(0, str(REPO_ROOT / "lib"))

import analyzer

SECTION_KEYS = {"GK": "keepers", "DEF": "defenders", "MID": "midfielders", "FWD": "forwards"}


def _read_team_of_season():
    squad = {key: [] for key in SECTION_KEYS.values()}
    expected = {}
    section = None
    for line in TEAM_OF_SEASON_FILE.read_text().splitlines():
        if line in SECTION_KEYS:
            section = SECTION_KEYS[line]
        elif line.startswith("Full Squad Points:"):
            expected["full"] = int(line.split(":")[1])
        elif line.startswith("Active Squad Points:"):
            expected["active"] = int(line.split(":")[1])
        elif section and line.strip() and not line.startswith(("Name\t", "#")):
            squad[section].append(line.split("\t")[0])
        elif not line.strip():
            section = None
    squad["bank"] = 0
    return squad, expected


def _load_analyzer():
    a = analyzer.Analyzer()
    a.readDataFromDir(str(FIXTURE_DIR))
    return a


def test_score_squad_matches_team_of_the_season(tmp_path):
    squad, expected = _read_team_of_season()
    squadFn = tmp_path / "squad.json"
    squadFn.write_text(json.dumps(squad))
    assert (_load_analyzer().scoreSquad(str(squadFn))) == (expected["full"], expected["active"])


def test_score_squad_without_bank_gives_clear_error(tmp_path):
    squad, _ = _read_team_of_season()
    del squad["bank"]
    squadFn = tmp_path / "squad.json"
    squadFn.write_text(json.dumps(squad))
    try:
        _load_analyzer().scoreSquad(str(squadFn))
        assert False, "expected an AssertionError for the missing bank"
    except AssertionError as e:
        assert "bank" in str(e)
