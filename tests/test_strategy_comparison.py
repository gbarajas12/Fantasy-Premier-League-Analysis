"""Tests for season-long strategy comparison (Analyzer.compareStrategies,
Analyzer._generateRandomSquad, and lib/strategies.py).

Unlike test_best_team_regression.py, results here are randomized, so
assertions are structural (legality, determinism under a fixed seed, sane
bounds) rather than exact-value. We never assert one strategy beats another -
that's the actual output the tool exists to discover.
"""
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "season_2025_26"
TEAM_OF_SEASON_FILE = REPO_ROOT / "2025-26" / "team_of_the_season.txt"

sys.path.insert(0, str(REPO_ROOT / "lib"))

import analyzer
import strategies


def _season_ceiling_active_points():
    for line in TEAM_OF_SEASON_FILE.read_text().splitlines():
        if line.startswith("Active Squad Points:"):
            return int(line.split(":")[1])
    raise AssertionError("Active Squad Points line not found in " + str(TEAM_OF_SEASON_FILE))


def _assert_squad_is_legal(a, squadData):
    counts = [len(posList) for posList in squadData.positionTbl]
    assert counts == a.positionCountTbl
    assert squadData.totalCost <= a.budget
    teamCounts = {}
    seenIds = set()
    for posList in squadData.positionTbl:
        for playerData in posList:
            assert playerData.playerId not in seenIds, "duplicate player in squad"
            seenIds.add(playerData.playerId)
            teamCounts[playerData.teamId] = teamCounts.get(playerData.teamId, 0) + 1
    assert max(teamCounts.values()) <= a.maxNumPlayersPerTeam


@pytest.fixture(scope="module")
def loaded_analyzer():
    a = analyzer.Analyzer()
    a.readDataFromJSON(
        str(FIXTURE_DIR / "top_level.json"),
        str(FIXTURE_DIR / "gameweek_player.json"),
        str(FIXTURE_DIR / "gameweek_fixture.json"),
    )
    return a


def test_compare_strategies_is_deterministic_given_a_seed(loaded_analyzer):
    results1 = loaded_analyzer.compareStrategies(strategies.buildDefaultStrategies(), numTrials=5, seed=42)
    results2 = loaded_analyzer.compareStrategies(strategies.buildDefaultStrategies(), numTrials=5, seed=42)
    assert results1 == results2


def test_random_squads_are_legal_and_spend_most_of_the_budget(loaded_analyzer):
    a = loaded_analyzer
    pool = a._buildRandomSquadCandidatePool()
    costs = []
    for seed in range(50):
        rng = random.Random(seed)
        squad = a._generateRandomSquad(pool, rng)
        _assert_squad_is_legal(a, squad)
        costs.append(squad.totalCost)
    meanUtilization = (sum(costs) / len(costs)) / a.budget
    assert meanUtilization >= 0.9


def test_strategy_points_never_exceed_season_optimal_ceiling(loaded_analyzer):
    ceiling = _season_ceiling_active_points()
    results = loaded_analyzer.compareStrategies(strategies.buildDefaultStrategies(), numTrials=5, seed=7)
    for name, pointsList in results.items():
        for points in pointsList:
            assert points <= ceiling, f"{name} scored {points}, above the season-optimal ceiling of {ceiling}"


def test_no_transfer_strategy_never_mutates_the_squad(loaded_analyzer):
    a = loaded_analyzer
    pool = a._buildRandomSquadCandidatePool()
    rng = random.Random(3)
    baseSquad = a._generateRandomSquad(pool, rng)
    originalIds = {playerData.playerId for posList in baseSquad.positionTbl for playerData in posList}

    trialSquad = analyzer.SquadData(a.numPositions)
    baseSquad.copyTo(trialSquad)
    strategy = strategies.Strategy("highest_total_points", strategies.FixedStatSquadSelector(analyzer.StatType.TOTAL_POINTS))
    strategy.squadSelector.prepare(a)
    (statSquad, statCaptain) = strategy.squadSelector.getStatTypes()
    a._evaluateStrategy(statSquad, statCaptain, trialSquad, transferPolicy=strategy.transferPolicy, rng=rng)

    finalIds = {playerData.playerId for posList in trialSquad.positionTbl for playerData in posList}
    assert finalIds == originalIds


def test_worst_form_transfer_strategy_stays_legal_after_a_full_season(loaded_analyzer):
    a = loaded_analyzer
    pool = a._buildRandomSquadCandidatePool()
    rng = random.Random(5)
    baseSquad = a._generateRandomSquad(pool, rng)

    trialSquad = analyzer.SquadData(a.numPositions)
    baseSquad.copyTo(trialSquad)
    strategy = strategies.Strategy(
        "worst_form_transfer_out",
        strategies.FixedStatSquadSelector(analyzer.StatType.FORM),
        strategies.WorstFormTransferPolicy(),
    )
    strategy.squadSelector.prepare(a)
    (statSquad, statCaptain) = strategy.squadSelector.getStatTypes()
    a._evaluateStrategy(statSquad, statCaptain, trialSquad, transferPolicy=strategy.transferPolicy, rng=rng)

    _assert_squad_is_legal(a, trialSquad)


def test_worst_form_transfer_strategy_changes_the_squad(loaded_analyzer):
    # Sanity check that the transfer policy actually does something over a full
    # season - guards against a no-op transferPolicy silently passing the
    # "stays legal" test above for the wrong reason.
    a = loaded_analyzer
    pool = a._buildRandomSquadCandidatePool()
    rng = random.Random(11)
    baseSquad = a._generateRandomSquad(pool, rng)
    originalIds = {playerData.playerId for posList in baseSquad.positionTbl for playerData in posList}

    trialSquad = analyzer.SquadData(a.numPositions)
    baseSquad.copyTo(trialSquad)
    strategy = strategies.Strategy(
        "worst_form_transfer_out",
        strategies.FixedStatSquadSelector(analyzer.StatType.FORM),
        strategies.WorstFormTransferPolicy(),
    )
    strategy.squadSelector.prepare(a)
    (statSquad, statCaptain) = strategy.squadSelector.getStatTypes()
    a._evaluateStrategy(statSquad, statCaptain, trialSquad, transferPolicy=strategy.transferPolicy, rng=rng)

    finalIds = {playerData.playerId for posList in trialSquad.positionTbl for playerData in posList}
    assert finalIds != originalIds
