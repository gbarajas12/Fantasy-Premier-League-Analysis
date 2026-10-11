"""Tests for the optional squad JSON output of findBestSquad and
findBestTransferOptions (Analyzer._writeSquadToJSON), which is written in the
input squad file format so it can be fed straight back in.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "season_2025_26"
TEAM_OF_SEASON_FILE = REPO_ROOT / "2025-26" / "team_of_the_season.txt"
sys.path.insert(0, str(REPO_ROOT / "lib"))

import analyzer


def _build_small_analyzer(budget=100):
    # 1 player per position (4 total); GK PlayerA is the better but pricier of two GKs
    a = analyzer.Analyzer()
    a.teamIdTbl = {1: analyzer.TeamData("Team One", 1), 2: analyzer.TeamData("Team Two", 2)}
    a.budget = budget
    a.positionCountTbl = [1, 1, 1, 1]
    a.minPositionCountTbl = [1, 1, 1, 1]
    a.maxPositionCountTbl = [1, 1, 1, 1]
    a.startingSquadSize = 4
    a.fullSquadSize = 4
    a.lastCompletedGameWeek = 1  # _evaluateStrategy does an unconditional week-1 lookup

    def addPlayer(name, playerId, totalPoints, nowCost, teamId, positionId):
        playerData = analyzer.PlayerData(name, "X", playerId, totalPoints, nowCost, teamId, positionId)
        playerData.updateGameWeekTbl(1, totalPoints, nowCost, minutesPlayed=90)
        a.playerNameTbl[playerData.name] = playerData

    addPlayer("PlayerA", 101, totalPoints=10, nowCost=35, teamId=1, positionId=1)
    addPlayer("PlayerB", 102, totalPoints=8, nowCost=25, teamId=1, positionId=1)
    addPlayer("PlayerC", 103, totalPoints=5, nowCost=20, teamId=1, positionId=2)
    addPlayer("PlayerD", 104, totalPoints=5, nowCost=20, teamId=1, positionId=3)
    addPlayer("PlayerE", 105, totalPoints=5, nowCost=20, teamId=2, positionId=4)
    return a


def _write_input_squad(tmp_path, keeper, bank):
    squadFn = tmp_path / "input_squad.json"
    squadFn.write_text(json.dumps({"keepers": [keeper + " X"], "defenders": ["PlayerC X"],
                                   "midfielders": ["PlayerD X"], "forwards": ["PlayerE X"], "bank": bank}))
    return squadFn


def test_best_squad_json_round_trips_through_score_squad(tmp_path):
    expected = {}
    for line in TEAM_OF_SEASON_FILE.read_text().splitlines():
        if line.startswith("Full Squad Points:"):
            expected["full"] = int(line.split(":")[1])
        elif line.startswith("Active Squad Points:"):
            expected["active"] = int(line.split(":")[1])

    a = analyzer.Analyzer()
    a.readDataFromDir(str(FIXTURE_DIR))
    squadJsonFn = tmp_path / "squad.json"
    a.findBestSquad(str(tmp_path / "best.txt"), outSquadJsonFn=str(squadJsonFn))

    squadJson = json.loads(squadJsonFn.read_text(encoding='utf-8'))
    assert [len(squadJson[k]) for k in ("keepers", "defenders", "midfielders", "forwards")] == [2, 5, 5, 3]
    assert squadJson["bank"] == 0.0  # the best squad spends the whole 100.0m budget

    b = analyzer.Analyzer()
    b.readDataFromDir(str(FIXTURE_DIR))
    assert b.scoreSquad(str(squadJsonFn)) == (expected["full"], expected["active"])


def test_transfers_json_is_input_squad_with_transfers_applied(tmp_path):
    a = _build_small_analyzer()
    squadJsonFn = tmp_path / "after.json"
    # budget becomes 25+20+20+20 + 10 bank = 95, exactly enough to swap PlayerB for PlayerA
    a.findBestTransferOptions(str(_write_input_squad(tmp_path, "PlayerB", 1.0)), 1,
                              str(tmp_path / "transfers.txt"), str(squadJsonFn))
    assert json.loads(squadJsonFn.read_text()) == {
        "keepers": ["PlayerA X"], "defenders": ["PlayerC X"],
        "midfielders": ["PlayerD X"], "forwards": ["PlayerE X"], "bank": 0.0}


def test_transfers_json_without_transfers_is_the_input_squad(tmp_path):
    a = _build_small_analyzer()
    squadJsonFn = tmp_path / "after.json"
    a.findBestTransferOptions(str(_write_input_squad(tmp_path, "PlayerB", 1.0)), 0,
                              str(tmp_path / "transfers.txt"), str(squadJsonFn))
    assert json.loads(squadJsonFn.read_text()) == {
        "keepers": ["PlayerB X"], "defenders": ["PlayerC X"],
        "midfielders": ["PlayerD X"], "forwards": ["PlayerE X"], "bank": 1.0}


def test_no_complete_squad_gives_clear_error_instead_of_empty_json(tmp_path):
    # every synthetic player has points_per_match 0.0, so all squads tie at 0 and none
    # strictly beats the empty starting squad - findBestSquad finds nothing to write
    a = _build_small_analyzer()
    squadJsonFn = tmp_path / "squad.json"
    try:
        a.findBestSquad(str(tmp_path / "best.txt"), squadStat='points_per_match', outSquadJsonFn=str(squadJsonFn))
        assert False, "expected an AssertionError"
    except AssertionError as e:
        assert "no complete squad" in str(e)
    assert not squadJsonFn.exists()
