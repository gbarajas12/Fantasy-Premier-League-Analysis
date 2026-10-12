"""Tests for the wildcard chip: Analyzer.getBestSquadForWeek (the cached
best-squad table) and strategies.WildcardTransferPolicy.

Real-data tests use the committed 2025-26 fixture directory. The objective
table's edge cases (windowing, players not in the game yet) are checked on a
tiny hand-built analyzer.
"""
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "season_2025_26"
sys.path.insert(0, str(REPO_ROOT / "lib"))

import analyzer
import strategies

WINDOW = 5


def _load_analyzer():
    a = analyzer.Analyzer()
    a.readDataFromDir(str(FIXTURE_DIR))
    return a


@pytest.fixture(scope="module")
def loaded_analyzer():
    return _load_analyzer()


def _is_legal(a, squadPlayersByPosition):
    flat = [p for posList in squadPlayersByPosition for p in posList]
    clubCounts = {}
    for p in flat:
        clubCounts[p.teamId] = clubCounts.get(p.teamId, 0) + 1
    return ([len(posList) for posList in squadPlayersByPosition] == a.positionCountTbl
            and len({p.playerId for p in flat}) == len(flat)
            and sum(p.nowCost for p in flat) <= a.budget
            and max(clubCounts.values()) <= a.maxNumPlayersPerTeam)


def _wildcard_policy(weeks):
    return strategies.WildcardTransferPolicy(strategies.WorstFormTransferPolicy(windowSize=WINDOW), weeks, WINDOW)


# --- objective table ---------------------------------------------------------

def _tiny_analyzer():
    a = analyzer.Analyzer()
    # points by gameweek; "late" first appears in gameweek 5
    for name, playerId, points in (("Early", 1, {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}), ("Late", 2, {5: 7, 6: 8})):
        p = analyzer.PlayerData(name, "X", playerId, sum(points.values()), 50, 1, 1)
        for week, pts in points.items():
            p.updateGameWeekTbl(week, pts, 50, 90)
        a.playerNameTbl[p.name] = p
    a.lastCompletedGameWeek = 6
    return a


def test_objective_table_sums_points_over_the_trailing_window():
    tbl = _tiny_analyzer()._buildTrailingPointsObjectiveTbl(4, 3)
    assert tbl[1] == 2 + 3 + 4


def test_objective_table_window_longer_than_the_data_sums_everything_so_far():
    tbl = _tiny_analyzer()._buildTrailingPointsObjectiveTbl(4, 25)
    assert tbl[1] == 1 + 2 + 3 + 4


def test_objective_table_never_reads_past_the_week():
    tbl = _tiny_analyzer()._buildTrailingPointsObjectiveTbl(5, 3)
    assert tbl[1] == 3 + 4 + 5
    assert tbl[2] == 7  # week 6's points are not included


def test_objective_table_marks_players_not_yet_in_the_game_as_unselectable():
    tbl = _tiny_analyzer()._buildTrailingPointsObjectiveTbl(3, 3)
    assert tbl[2] < -1000


# --- best squad table ---------------------------------------------------------

def test_best_squad_for_week_is_legal_optimal_and_cached(loaded_analyzer):
    a = loaded_analyzer
    table = a.getBestSquadForWeek(9, 10)
    assert _is_legal(a, table)
    tbl = a._buildTrailingPointsObjectiveTbl(9, 10)
    tableValue = sum(tbl[p.playerId] for posList in table for p in posList)
    pool = a._buildRandomSquadCandidatePool()
    rng = random.Random(0)
    for _ in range(200):
        squad = a._generateRandomSquad(pool, rng)
        assert tableValue >= sum(tbl[p.playerId] for posList in squad.positionTbl for p in posList)
    assert a.getBestSquadForWeek(9, 10) is table


def test_best_squad_for_week_leaves_analyzer_state_alone(loaded_analyzer):
    a = loaded_analyzer
    before = (a.objectiveTbl, a.requiredPlayerData, a.inputSquadData, a.squadOptimizationStat)
    a.getBestSquadForWeek(14, 7)
    assert (a.objectiveTbl, a.requiredPlayerData, a.inputSquadData, a.squadOptimizationStat) == before


# --- policy ------------------------------------------------------------------

@pytest.mark.parametrize("weeks", [[1], [39], [5, 10], [25, 30], [10, 10], ["10"]])
def test_invalid_schedules_are_rejected(weeks):
    with pytest.raises(AssertionError):
        _wildcard_policy(weeks)


@pytest.mark.parametrize("weeks", [[], [10], [30], [10, 30], [19, 20], [2, 38]])
def test_valid_schedules_are_accepted(weeks):
    _wildcard_policy(weeks)


def test_wildcard_week_rebuilds_the_squad_into_the_table_squad(loaded_analyzer):
    a = loaded_analyzer
    policy = _wildcard_policy([10, 30])
    policy.prepare(a)
    squad = a._generateRandomSquad(a._buildRandomSquadCandidatePool(), random.Random(3))
    transfers = policy.selectTransfers(a, squad, 9, [], [], None)  # the chip is played in gameweek 10
    assert len(transfers) > 1
    a._applyTransfers(squad, transfers)
    table = a.getBestSquadForWeek(9, WINDOW)
    assert [{p.playerId for p in posList} for posList in squad.positionTbl] == [{p.playerId for p in posList} for posList in table]
    assert _is_legal(a, squad.positionTbl)
    assert squad.totalCost == sum(p.nowCost for posList in table for p in posList)


class _RecordingPolicy(strategies.TransferPolicy):
    def __init__(self, inner):
        self.inner = inner
        self.numTransfersByWeek = {}

    def prepare(self, analyzer):
        self.inner.prepare(analyzer)

    def selectTransfers(self, analyzer, squadData, weekIdx, weekSquad, weekSubs, rng):
        transfers = self.inner.selectTransfers(analyzer, squadData, weekIdx, weekSquad, weekSubs, rng)
        self.numTransfersByWeek[weekIdx] = len(transfers)
        return transfers


def test_only_scheduled_weeks_make_more_than_one_transfer(loaded_analyzer):
    a = loaded_analyzer
    recorder = _RecordingPolicy(_wildcard_policy([10, 30]))
    selector = strategies.WindowedFormSquadSelector(WINDOW)
    selector.prepare(a)
    recorder.prepare(a)
    squad = a._generateRandomSquad(a._buildRandomSquadCandidatePool(), random.Random(4))
    (statSquad, statCaptain) = selector.getStatTypes()
    a._evaluateStrategy(statSquad, statCaptain, squad, transferPolicy=recorder, rng=random.Random(0))
    bigWeeks = {week for week, n in recorder.numTransfersByWeek.items() if n > 1}
    assert bigWeeks == {9, 29}  # chip played in gameweeks 10 and 30
    assert _is_legal(a, squad.positionTbl)


def test_schedule_weeks_past_the_data_are_ignored_with_a_warning(capsys):
    # (_evaluateStrategy never asks for transfers at or after lastCompletedGameWeek,
    # so a week past the data can't fire; prepare() just must not build a table for it)
    a = _load_analyzer()
    a.lastCompletedGameWeek = 20
    _wildcard_policy([10, 30]).prepare(a)
    assert "wildcard week 30" in capsys.readouterr().out
    assert a.bestSquadTbl == {}  # tables are built when the chip is played, for that trial's money


def test_comparison_with_a_wildcard_strategy_is_deterministic(loaded_analyzer):
    def build():
        return [strategies.Strategy("wc", strategies.WindowedFormSquadSelector(WINDOW), _wildcard_policy([10, 30]))]
    results1 = loaded_analyzer.compareStrategies(build(), numTrials=3, seed=5)
    results2 = loaded_analyzer.compareStrategies(build(), numTrials=3, seed=5)
    assert results1 == results2
