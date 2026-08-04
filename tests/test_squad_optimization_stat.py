"""Tests for findBestSquad's configurable optimization objective
(Analyzer.squadOptimizationStat / Analyzer._getSquadObjectiveValue).

Fully synthetic - real 2025-26 points_per_game data isn't reliably
recoverable from any archived pull on disk (checked: the only raw
bootstrap-static dump left has 274 players missing vs. our trimmed test
fixture and mismatched total_points/now_cost for most of the rest - a
different/stale pull, unsafe to use as ground truth).

Bypasses readDataFromJSON entirely - constructs PlayerData objects by hand
and shrinks the squad shape to 1 player per position (4 total), so the DFS
search space is small enough to trace and verify by hand.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

import analyzer

GK_A, GK_B, DEF_C, MID_D, FWD_E = "PlayerA Alpha", "PlayerB Beta", "PlayerC Gamma", "PlayerD Delta", "PlayerE Epsilon"


def _build_analyzer():
    a = analyzer.Analyzer()
    a.teamIdTbl = {1: analyzer.TeamData("Team One", 1), 2: analyzer.TeamData("Team Two", 2)}
    a.budget = 100
    a.positionCountTbl = [1, 1, 1, 1]
    a.minPositionCountTbl = [1, 1, 1, 1]
    a.maxPositionCountTbl = [1, 1, 1, 1]
    a.startingSquadSize = 4
    a.fullSquadSize = 4
    a.lastCompletedGameWeek = 1  # required: _evaluateStrategy (called from _writeBestSquadToFile)
    # unconditionally does a week-1 lookup before checking lastCompletedGameWeek's loop range

    def addPlayer(firstName, lastName, playerId, totalPoints, nowCost, teamId, positionId, pointsPerMatch, weekPoints):
        playerData = analyzer.PlayerData(firstName, lastName, playerId, totalPoints, nowCost, teamId, positionId, pointsPerMatch)
        playerData.updateGameWeekTbl(1, weekPoints, nowCost, minutesPlayed=90)
        a.playerNameTbl[playerData.name] = playerData

    # GK: A has more total points, B is cheaper with a higher points-per-match
    addPlayer("PlayerA", "Alpha", 101, totalPoints=10, nowCost=35, teamId=1, positionId=1, pointsPerMatch=2.0, weekPoints=10)
    addPlayer("PlayerB", "Beta", 102, totalPoints=8, nowCost=25, teamId=1, positionId=1, pointsPerMatch=8.0, weekPoints=8)
    # DEF/MID: sole candidates, always picked regardless of objective
    addPlayer("PlayerC", "Gamma", 103, totalPoints=5, nowCost=20, teamId=1, positionId=2, pointsPerMatch=5.0, weekPoints=5)
    addPlayer("PlayerD", "Delta", 104, totalPoints=5, nowCost=20, teamId=1, positionId=3, pointsPerMatch=5.0, weekPoints=5)
    # FWD: sole candidate, different team so team1 stays at exactly 3 (maxNumPlayersPerTeam default)
    addPlayer("PlayerE", "Epsilon", 105, totalPoints=5, nowCost=20, teamId=2, positionId=4, pointsPerMatch=5.0, weekPoints=5)

    return a


def test_total_points_objective_picks_higher_scoring_gk(tmp_path, capsys):
    a = _build_analyzer()
    outFn = tmp_path / "out_total_points.txt"
    a.findBestSquad(str(outFn), squadStat='total_points')

    # Neither GK dominates the other under total_points (B is cheaper but
    # scores fewer total points), so both survive dominance pruning - the DFS
    # branch-and-bound picks the winner, not the pruning step.
    assert len(a.playerPositionTbl[0]) == 2

    content = outFn.read_text()
    assert GK_A in content
    assert GK_B not in content
    assert "Points Per Match" not in content

    printed = capsys.readouterr().out
    totalPoints = int(printed.strip().split()[0])
    assert totalPoints == 25  # 10 (A) + 5 + 5 + 5


def test_points_per_match_objective_picks_better_ppm_gk(tmp_path, capsys):
    a = _build_analyzer()
    outFn = tmp_path / "out_ppm.txt"
    a.findBestSquad(str(outFn), squadStat='points_per_match')

    # B is strictly cheaper AND has a higher points-per-match than A, so A is
    # dominance-pruned in _createPlayerPositionTbl itself - real proof the
    # pruning step (not just the DFS) was correctly generalized.
    assert len(a.playerPositionTbl[0]) == 1
    assert a.playerPositionTbl[0][0].name == GK_B

    content = outFn.read_text()
    assert GK_B in content
    assert GK_A not in content
    assert "Points Per Match" in content
    assert "8.0" in content  # PlayerB's points-per-match value

    printed = capsys.readouterr().out
    totalPoints = int(printed.strip().split()[0])
    assert totalPoints == 23  # 8 (B, real total points) + 5 + 5 + 5 - stays decoupled from the objective


def test_default_squad_stat_is_total_points(tmp_path, capsys):
    # findBestSquad(outFn) with no squadStat arg must behave identically to
    # squadStat='total_points' - this is what every other real call site relies on.
    a = _build_analyzer()
    outFn = tmp_path / "out_default.txt"
    a.findBestSquad(str(outFn))

    content = outFn.read_text()
    assert GK_A in content
    assert GK_B not in content
    assert "Points Per Match" not in content


def test_invalid_squad_stat_rejected(tmp_path):
    a = _build_analyzer()
    outFn = tmp_path / "out_invalid.txt"
    try:
        a.findBestSquad(str(outFn), squadStat='not_a_real_stat')
        assert False, "expected an AssertionError for an unknown squadStat"
    except AssertionError as e:
        assert "not_a_real_stat" in str(e)
