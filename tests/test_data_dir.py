"""Tests for Analyzer.readDataFromDir, which reads the standard-named files
(lib/fpl_data_files.py) out of an FPL data directory.

Uses copies of the committed 2025-26 fixture files (the fixture directory is
itself a valid FPL data directory).
"""
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "season_2025_26"
sys.path.insert(0, str(REPO_ROOT / "lib"))

import analyzer
import fpl_data_files


def _make_data_dir(tmp_path, includeCost=False):
    dataDir = tmp_path / "data"
    dataDir.mkdir()
    for fn in (fpl_data_files.TOP_LEVEL_FN, fpl_data_files.GAMEWEEK_PLAYER_FN, fpl_data_files.GAMEWEEK_FIXTURE_FN):
        shutil.copy(FIXTURE_DIR / fn, dataDir / fn)
    if includeCost:
        # player 1 (David Raya Martín), gameweek 1 only
        (dataDir / fpl_data_files.GAMEWEEK_COST_FN).write_text(json.dumps({"1": {"1": 1}}))
    return dataDir


def _gw1_cost(a):
    return a.playerNameTbl["David Raya Martín"].gameWeekTbl[1].statTbl[analyzer.StatType.COST]


def test_reads_all_files_from_directory(tmp_path):
    a = analyzer.Analyzer()
    a.readDataFromDir(str(_make_data_dir(tmp_path)))
    assert a.lastCompletedGameWeek == 38
    assert len(a.playerNameTbl) == 841
    # no cost file in the directory: falls back to the player's current price
    assert _gw1_cost(a) == a.playerNameTbl["David Raya Martín"].nowCost


def test_cost_file_in_directory_is_used_when_present(tmp_path):
    a = analyzer.Analyzer()
    a.readDataFromDir(str(_make_data_dir(tmp_path, includeCost=True)))
    assert _gw1_cost(a) == 1


def test_missing_required_file_gives_clear_error(tmp_path):
    dataDir = _make_data_dir(tmp_path)
    (dataDir / fpl_data_files.GAMEWEEK_PLAYER_FN).unlink()
    a = analyzer.Analyzer()
    try:
        a.readDataFromDir(str(dataDir))
        assert False, "expected an AssertionError for the missing file"
    except AssertionError as e:
        assert fpl_data_files.GAMEWEEK_PLAYER_FN in str(e)
        assert str(dataDir) in str(e)


def test_warns_when_the_cost_file_is_missing(tmp_path, capsys):
    dataDir = _make_data_dir(tmp_path)
    analyzer.Analyzer().readDataFromDir(str(dataDir))
    out = capsys.readouterr().out
    assert "WARNING" in out and fpl_data_files.GAMEWEEK_COST_FN in out and str(dataDir) in out


def test_no_cost_file_warning_when_it_is_present(tmp_path, capsys):
    analyzer.Analyzer().readDataFromDir(str(_make_data_dir(tmp_path, includeCost=True)))
    assert fpl_data_files.GAMEWEEK_COST_FN not in capsys.readouterr().out
