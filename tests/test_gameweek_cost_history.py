"""Tests for per-gameweek player cost history (Analyzer._getHistoricalCost,
wired through readDataFromJSON's optional costHistoryJsonFn param).

Fully synthetic and self-contained - no network access, no dependency on
tests/fixtures/season_2025_26/ (whose gameweek_player.json has no cost data
and never can, since the FPL API only exposes per-gameweek price history for
the currently in-progress season - see CLAUDE.md/season_strategy_prompt.txt
context). Files are written to tmp_path and loaded through the real
readDataFromJSON entry point, so the int-player-ID/int-gameweek-ID keys used
when building the data round-trip through json.dump/json.load exactly like a
real fpl_gameweek_cost_data.json would - this is the class of bug
_getHistoricalCost's str(...) lookups need to be safe against.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

import analyzer

ALICE_ID, BOB_ID, CAROL_ID = 101, 102, 103
ALICE_NOW_COST, BOB_NOW_COST, CAROL_NOW_COST = 55, 60, 75
PLAYER_NAMES = {ALICE_ID: "Alice Alpha", BOB_ID: "Bob Beta", CAROL_ID: "Carol Gamma"}

# week1, week2 points per player - sums must match total_points below, or
# _examineGameWeekData prints a "total points mismatch" warning.
WEEK_POINTS = {
    ALICE_ID: [6, 8],
    BOB_ID: [4, 0],
    CAROL_ID: [5, 3],
}


def _write_fixture_files(tmp_path, cost_history_data=None):
    top_level = {
        "teams": [{"id": 1, "name": "Team One"}, {"id": 2, "name": "Team Two"}],
        "elements": [
            {"id": ALICE_ID, "first_name": "Alice", "second_name": "Alpha",
             "total_points": sum(WEEK_POINTS[ALICE_ID]), "now_cost": ALICE_NOW_COST,
             "team": 1, "element_type": 1, "points_per_game": "0.0"},
            {"id": BOB_ID, "first_name": "Bob", "second_name": "Beta",
             "total_points": sum(WEEK_POINTS[BOB_ID]), "now_cost": BOB_NOW_COST,
             "team": 2, "element_type": 1, "points_per_game": "0.0"},
            {"id": CAROL_ID, "first_name": "Carol", "second_name": "Gamma",
             "total_points": sum(WEEK_POINTS[CAROL_ID]), "now_cost": CAROL_NOW_COST,
             "team": 1, "element_type": 1, "points_per_game": "0.0"},
        ],
        "events": [{"id": 1, "finished": True}, {"id": 2, "finished": True}],
    }
    gameweek_player = {
        str(week): {
            "elements": [
                {"id": playerId, "stats": {"minutes": 90, "total_points": points[week - 1]}}
                for playerId, points in WEEK_POINTS.items()
            ]
        }
        for week in (1, 2)
    }
    gameweek_fixture = {
        "1": [{"finished": True, "team_h": 1, "team_a": 2, "team_h_score": 1, "team_a_score": 0}],
        "2": [{"finished": True, "team_h": 2, "team_a": 1, "team_h_score": 2, "team_a_score": 2}],
    }

    top_level_fn = tmp_path / "top_level.json"
    gameweek_player_fn = tmp_path / "gameweek_player.json"
    gameweek_fixture_fn = tmp_path / "gameweek_fixture.json"
    top_level_fn.write_text(json.dumps(top_level))
    gameweek_player_fn.write_text(json.dumps(gameweek_player))
    gameweek_fixture_fn.write_text(json.dumps(gameweek_fixture))

    cost_history_fn = None
    if cost_history_data is not None:
        cost_history_fn = tmp_path / "gameweek_cost.json"
        cost_history_fn.write_text(json.dumps(cost_history_data))

    return top_level_fn, gameweek_player_fn, gameweek_fixture_fn, cost_history_fn


def _cost(a, playerId, week):
    return a.playerNameTbl[PLAYER_NAMES[playerId]].gameWeekTbl[week].statTbl[analyzer.StatType.COST]


def _load_analyzer(top_level_fn, gameweek_player_fn, gameweek_fixture_fn, cost_history_fn):
    a = analyzer.Analyzer()
    if cost_history_fn is not None:
        a.readDataFromJSON(str(top_level_fn), str(gameweek_player_fn), str(gameweek_fixture_fn), str(cost_history_fn))
    else:
        a.readDataFromJSON(str(top_level_fn), str(gameweek_player_fn), str(gameweek_fixture_fn))
    return a


def test_historical_cost_used_when_present(tmp_path):
    costHistoryData = {str(ALICE_ID): {"1": 54, "2": 56}}
    files = _write_fixture_files(tmp_path, costHistoryData)
    a = _load_analyzer(*files)

    assert _cost(a, ALICE_ID, 1) == 54
    assert _cost(a, ALICE_ID, 2) == 56


def test_fallback_to_now_cost_when_cost_file_not_provided(tmp_path):
    files = _write_fixture_files(tmp_path, cost_history_data=None)
    a = _load_analyzer(*files)

    for playerId, nowCost in ((ALICE_ID, ALICE_NOW_COST), (BOB_ID, BOB_NOW_COST), (CAROL_ID, CAROL_NOW_COST)):
        assert _cost(a, playerId, 1) == nowCost
        assert _cost(a, playerId, 2) == nowCost


def test_fallback_when_player_missing_from_cost_file(tmp_path):
    # cost file provided, but Bob has no entry in it at all
    costHistoryData = {str(ALICE_ID): {"1": 54, "2": 56}}
    files = _write_fixture_files(tmp_path, costHistoryData)
    a = _load_analyzer(*files)

    assert _cost(a, BOB_ID, 1) == BOB_NOW_COST
    assert _cost(a, BOB_ID, 2) == BOB_NOW_COST


def test_fallback_when_week_missing_from_players_cost_entry(tmp_path):
    # Carol's entry only covers week 1
    costHistoryData = {str(CAROL_ID): {"1": 70}}
    files = _write_fixture_files(tmp_path, costHistoryData)
    a = _load_analyzer(*files)

    assert _cost(a, CAROL_ID, 1) == 70
    assert _cost(a, CAROL_ID, 2) == CAROL_NOW_COST
