"""Tests for the required_players config option (Analyzer._resolveRequiredPlayers /
Analyzer._seedMandatoryPlayers), which forces findBestSquad's DFS to include a
specific set of players in the final squad. findBestTransferOptions uses the
same two calls, so required_players also forces a player to survive the
transfer search even if transferring them out would otherwise score higher.

Fully synthetic, same style as tests/test_squad_optimization_stat.py: constructs
PlayerData objects by hand and shrinks the squad shape to 1 player per position,
so the DFS search space is small enough to trace and verify by hand.
"""
import json
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

    def addPlayer(firstName, lastName, playerId, totalPoints, nowCost, teamId, positionId, weekPoints):
        playerData = analyzer.PlayerData(firstName, lastName, playerId, totalPoints, nowCost, teamId, positionId)
        playerData.updateGameWeekTbl(1, weekPoints, nowCost, minutesPlayed=90)
        a.playerNameTbl[playerData.name] = playerData

    # GK: A is the objective-optimal pick (more total points); B is worse but cheaper
    addPlayer("PlayerA", "Alpha", 101, totalPoints=10, nowCost=35, teamId=1, positionId=1, weekPoints=10)
    addPlayer("PlayerB", "Beta", 102, totalPoints=8, nowCost=25, teamId=1, positionId=1, weekPoints=8)
    # DEF/MID: sole candidates, always picked regardless of objective
    addPlayer("PlayerC", "Gamma", 103, totalPoints=5, nowCost=20, teamId=1, positionId=2, weekPoints=5)
    addPlayer("PlayerD", "Delta", 104, totalPoints=5, nowCost=20, teamId=1, positionId=3, weekPoints=5)
    # FWD: sole candidate, different team so team1 stays at exactly 3 (maxNumPlayersPerTeam default)
    addPlayer("PlayerE", "Epsilon", 105, totalPoints=5, nowCost=20, teamId=2, positionId=4, weekPoints=5)

    return a


def _assert_raises(fn, expectedSubstring):
    try:
        fn()
        assert False, f"expected an AssertionError containing {expectedSubstring!r}"
    except AssertionError as e:
        assert expectedSubstring in str(e), str(e)


def test_required_player_overrides_objective_optimal_choice(tmp_path):
    # PlayerB is worse than PlayerA under total_points, so the DFS would never
    # pick B on its own - forcing it via required_players proves the seeding
    # actually overrides the optimizer, not just "happened to already win".
    a = _build_analyzer()
    a.requiredPlayers = {GK_B}
    outFn = tmp_path / "out.txt"
    a.findBestSquad(str(outFn))

    content = outFn.read_text()
    assert GK_B in content
    assert GK_A not in content


def test_no_required_players_is_unaffected(tmp_path):
    a = _build_analyzer()
    outFn = tmp_path / "out.txt"
    a.findBestSquad(str(outFn))

    content = outFn.read_text()
    assert GK_A in content
    assert GK_B not in content


def test_unknown_required_player_name_rejected(tmp_path):
    a = _build_analyzer()
    a.requiredPlayers = {"Nobody Nonexistent"}
    outFn = tmp_path / "out.txt"
    _assert_raises(lambda: a.findBestSquad(str(outFn)), "Nobody Nonexistent")


def test_required_player_also_excluded_is_rejected(tmp_path):
    a = _build_analyzer()
    a.requiredPlayers = {GK_A}
    a.playersToExclude = {GK_A}
    outFn = tmp_path / "out.txt"
    _assert_raises(lambda: a.findBestSquad(str(outFn)), GK_A)


def test_too_many_required_players_at_one_position_rejected(tmp_path):
    a = _build_analyzer()
    a.requiredPlayers = {GK_A, GK_B}  # positionCountTbl[0] only allows 1 GK
    outFn = tmp_path / "out.txt"
    _assert_raises(lambda: a.findBestSquad(str(outFn)), "GK")


def test_required_players_exceeding_budget_alone_rejected(tmp_path):
    a = _build_analyzer()
    a.budget = 30  # PlayerA alone costs 35
    a.requiredPlayers = {GK_A}
    outFn = tmp_path / "out.txt"
    _assert_raises(lambda: a.findBestSquad(str(outFn)), "budget")


def test_required_players_leaving_insufficient_budget_for_rest_rejected(tmp_path):
    # PlayerA (35) fits under this budget on its own, but the cheapest
    # possible DEF+MID+FWD (20 each = 60) pushes the total to 95, over budget.
    a = _build_analyzer()
    a.budget = 40
    a.requiredPlayers = {GK_A}
    outFn = tmp_path / "out.txt"
    _assert_raises(lambda: a.findBestSquad(str(outFn)), "cheapest possible remaining squad")


def test_required_player_survives_transfer_search(tmp_path):
    # Owns PlayerB at GK. Budget (95 = 25+20+20+20 squad value + 10 bank) is
    # exactly enough to also afford switching to PlayerA, who scores higher -
    # without required_players the transfer search would make that swap.
    a = _build_analyzer()
    a.requiredPlayers = {GK_B}
    squadFn = tmp_path / "input_squad.json"
    squadFn.write_text(json.dumps({"keepers": [GK_B], "defenders": [DEF_C],
                                    "midfielders": [MID_D], "forwards": [FWD_E], "bank": 1.0}))
    outFn = tmp_path / "transfers.txt"
    a.findBestTransferOptions(str(squadFn), 1, str(outFn))

    content = outFn.read_text()
    assert "Players Out:\n\n" in content  # nothing transferred out - GK_B stays required


def test_no_required_players_leaves_transfer_search_unaffected(tmp_path):
    # Same setup with no required_players: the transfer search is free to
    # swap in the objectively-better PlayerA, proving the prior test's "stays
    # put" result comes from required_players and not from the search simply
    # not wanting to transfer.
    a = _build_analyzer()
    squadFn = tmp_path / "input_squad.json"
    squadFn.write_text(json.dumps({"keepers": [GK_B], "defenders": [DEF_C],
                                    "midfielders": [MID_D], "forwards": [FWD_E], "bank": 1.0}))
    outFn = tmp_path / "transfers.txt"
    a.findBestTransferOptions(str(squadFn), 1, str(outFn))

    content = outFn.read_text()
    assert "Players In:\nPlayerA Alpha" in content
