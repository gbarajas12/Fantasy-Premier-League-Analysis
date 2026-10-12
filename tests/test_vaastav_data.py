"""Tests for vaastav_data.readGameweekCosts (behind prog/costDataFromVaastav.py),
which builds the per-gameweek cost table from a season directory of the
vaastav/Fantasy-Premier-League repo. Uses a tiny hand-made gws/ directory so the
tests don't depend on that (untracked) clone.
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "season_2025_26"
sys.path.insert(0, str(REPO_ROOT / "lib"))

import analyzer
import fpl_data_files
import vaastav_data

HEADER = "name,element,round,kickoff_time,value,total_points"


def _make_season_dir(tmp_path, gwRows, extraFiles=None):
    gwsDir = tmp_path / "season" / "gws"
    gwsDir.mkdir(parents=True)
    for gw, rows in gwRows.items():
        (gwsDir / f"gw{gw}.csv").write_text("\n".join([HEADER] + rows) + "\n")
    for fn in (extraFiles or []):
        (gwsDir / fn).write_text("not,a,gameweek,file\n1,2,3,4\n")
    return str(tmp_path / "season")


def test_reads_price_by_player_and_gameweek(tmp_path):
    seasonDir = _make_season_dir(tmp_path, {
        1: ["A,1,1,2025-08-16T14:00:00Z,55,2", "B,2,1,2025-08-16T14:00:00Z,40,0"],
        2: ["A,1,2,2025-08-23T14:00:00Z,56,5"],  # player 2 has no row this gameweek
        3: ["B,2,3,2025-08-30T14:00:00Z,41,1", "A,1,3,2025-08-30T14:00:00Z,56,1"],
    })
    assert vaastav_data.readGameweekCosts(seasonDir) == {1: {1: 55, 2: 56, 3: 56}, 2: {1: 40, 3: 41}}


def test_result_is_sorted_by_player_and_gameweek(tmp_path):
    seasonDir = _make_season_dir(tmp_path, {
        2: ["B,9,2,2025-08-23T14:00:00Z,40,0", "A,1,2,2025-08-23T14:00:00Z,56,5"],
        1: ["B,9,1,2025-08-16T14:00:00Z,40,0", "A,1,1,2025-08-16T14:00:00Z,55,2"],
    })
    costTbl = vaastav_data.readGameweekCosts(seasonDir)
    assert list(costTbl) == [1, 9]
    assert list(costTbl[1]) == [1, 2]


def test_double_gameweek_keeps_the_price_at_the_last_fixture(tmp_path):
    # rows deliberately listed latest-kickoff first
    seasonDir = _make_season_dir(tmp_path, {
        4: ["A,1,4,2025-09-21T14:00:00Z,58,2", "A,1,4,2025-09-17T19:00:00Z,57,1"],
    })
    assert vaastav_data.readGameweekCosts(seasonDir) == {1: {4: 58}}


def test_ignores_files_that_are_not_gameweek_files(tmp_path):
    seasonDir = _make_season_dir(tmp_path, {1: ["A,1,1,2025-08-16T14:00:00Z,55,2"]},
                                 extraFiles=["merged_gw.csv", "xP1.csv", "gw1.csv.bak"])
    assert vaastav_data.readGameweekCosts(seasonDir) == {1: {1: 55}}


def test_missing_gws_directory_gives_clear_error(tmp_path):
    with pytest.raises(AssertionError, match="no gws directory"):
        vaastav_data.readGameweekCosts(str(tmp_path))


def test_no_gameweek_files_gives_clear_error(tmp_path):
    seasonDir = _make_season_dir(tmp_path, {}, extraFiles=["merged_gw.csv"])
    with pytest.raises(AssertionError, match="no gw<N>.csv files"):
        vaastav_data.readGameweekCosts(seasonDir)


def test_missing_column_gives_clear_error(tmp_path):
    seasonDir = _make_season_dir(tmp_path, {})
    (Path(seasonDir) / "gws" / "gw1.csv").write_text("name,element,round\nA,1,1\n")
    with pytest.raises(AssertionError, match="value"):
        vaastav_data.readGameweekCosts(seasonDir)


def test_round_that_disagrees_with_the_file_name_gives_clear_error(tmp_path):
    seasonDir = _make_season_dir(tmp_path, {1: ["A,1,2,2025-08-16T14:00:00Z,55,2"]})
    with pytest.raises(AssertionError, match="round 2"):
        vaastav_data.readGameweekCosts(seasonDir)


def test_cost_file_round_trips_through_the_analyzer(tmp_path):
    # player 1 in the fixture is David Raya Martín; write his GW1 price as 1
    seasonDir = _make_season_dir(tmp_path, {1: ["Raya,1,1,2025-08-16T14:00:00Z,1,2"]})
    dataDir = tmp_path / "data"
    dataDir.mkdir()
    for fn in (fpl_data_files.TOP_LEVEL_FN, fpl_data_files.GAMEWEEK_PLAYER_FN, fpl_data_files.GAMEWEEK_FIXTURE_FN):
        shutil.copy(FIXTURE_DIR / fn, dataDir / fn)
    (dataDir / fpl_data_files.GAMEWEEK_COST_FN).write_text(json.dumps(vaastav_data.readGameweekCosts(seasonDir)))
    a = analyzer.Analyzer()
    a.readDataFromDir(str(dataDir))
    raya = a.playerNameTbl["David Raya Martín"]
    assert raya.gameWeekTbl[1].statTbl[analyzer.StatType.COST] == 1
    assert raya.gameWeekTbl[2].statTbl[analyzer.StatType.COST] == raya.nowCost  # no cost entry: falls back
