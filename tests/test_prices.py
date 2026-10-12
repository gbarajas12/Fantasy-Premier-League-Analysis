"""Tests for compareStrategies' use of the per-gameweek cost file: the price
tables (Analyzer._ensurePriceTables / _setPricesForWeek), the per-squad bank, and
a simulation that buys, sells and wildcards at each week's prices
(_evaluateStrategy(simulatePrices=True)).
"""
import random
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "season_2025_26"
sys.path.insert(0, str(REPO_ROOT / "lib"))

import analyzer
import fpl_data_files
import strategies

WINDOW = 5


def _load_analyzer(dataDir=FIXTURE_DIR):
    a = analyzer.Analyzer()
    a.readDataFromDir(str(dataDir))
    return a


@pytest.fixture(scope="module")
def loaded_analyzer():
    return _load_analyzer()


def _current_prices(a):
    return {p.playerId: p.nowCost for p in a.playerNameTbl.values()}


def _starting_squad(a, seed):
    # what compareStrategies does: buy the squad at the starting prices
    a._ensurePriceTables()
    try:
        a._setPricesForWeek(a._getStartWeek())
        return a._generateRandomSquad(a._buildRandomSquadCandidatePool(), random.Random(seed))
    finally:
        a._setPricesForWeek(None)


def _tiny_analyzer(costHistory):
    a = analyzer.Analyzer()
    for name, playerId, nowCost in (("A", 1, 60), ("B", 2, 50), ("C", 3, 40)):
        p = analyzer.PlayerData(name, "X", playerId, 10, nowCost, 1, 1)
        p.updateGameWeekTbl(1, 1, nowCost, 90)
        a.playerNameTbl[p.name] = p
    a.lastCompletedGameWeek = 5
    a.costHistoryTbl = costHistory
    return a


# --- price tables --------------------------------------------------------------

def test_price_tables_carry_forward_and_forward_fill():
    # A has no entry in gameweek 4; B's first entry is in gameweek 3; C has none at all
    a = _tiny_analyzer({1: {1: 55, 2: 55, 3: 56, 5: 61}, 2: {3: 45}})
    a._ensurePriceTables()
    snapshots = a.priceTbls['snapshots']
    assert [snapshots[w][1] for w in range(1, 6)] == [55, 55, 56, 56, 61]
    assert [snapshots[w][2] for w in range(1, 6)] == [45, 45, 45, 45, 45]
    assert [snapshots[w][3] for w in range(1, 6)] == [40] * 5
    assert a.priceTbls['hasPriceChanges']


def test_set_prices_moves_nowcost_and_restores_the_base_prices():
    a = _tiny_analyzer({1: {1: 55, 2: 55, 3: 56, 5: 61}, 2: {3: 45}})
    base = _current_prices(a)
    snapshots = None
    for week in (1, 2, 3, 4, 5, 2, 5): # forward one at a time, then jumps
        a._setPricesForWeek(week)
        snapshots = a.priceTbls['snapshots']
        assert _current_prices(a) == snapshots[week]
        assert a._priceWeek == week
    a._setPricesForWeek(None)
    assert _current_prices(a) == base
    assert a._priceWeek is None


def test_set_prices_clamps_to_the_available_gameweeks():
    a = _tiny_analyzer({1: {1: 55, 5: 61}})
    a._setPricesForWeek(99)
    assert a._priceWeek == 5
    assert a.playerNameTbl["A X"].nowCost == 61


def test_without_a_cost_file_prices_never_change():
    a = _tiny_analyzer(None)
    a._ensurePriceTables()
    assert not a.priceTbls['hasPriceChanges']
    base = _current_prices(a)
    a._setPricesForWeek(3)
    assert _current_prices(a) == base
    assert a._priceWeek is None


def test_price_tables_use_the_raw_cost_file_not_the_filled_in_stat(loaded_analyzer):
    # The cost file has holes (blank gameweeks) that readDataFromDir fills with the
    # player's FINAL price in StatType.COST. The price tables must carry the last real
    # price forward instead.
    a = loaded_analyzer
    a._ensurePriceTables()
    holes = [(pid, week) for pid, weeks in a.costHistoryTbl.items() for week in range(2, 39)
             if week not in weeks and week - 1 in weeks]
    assert holes
    for pid, week in holes[:300]:
        assert a.priceTbls['snapshots'][week][pid] == a.priceTbls['snapshots'][week - 1][pid]


# --- bank and transfers --------------------------------------------------------

def _squad_with(players, bank):
    squad = analyzer.SquadData(4)
    squad.positionTbl[0] = list(players)
    squad.totalCost = sum(p.nowCost for p in players)
    squad.bank = bank
    return squad


def test_replacement_affordability_uses_the_bank():
    a = _tiny_analyzer(None)
    cheap, rich = a.playerNameTbl["B X"], analyzer.PlayerData("D", "X", 4, 10, 90, 2, 1)
    rich.updateGameWeekTbl(1, 1, 90, 90)
    outPlayer = a.playerNameTbl["A X"] # costs 60
    pool = [rich, cheap]
    assert a._findReplacementPlayer(analyzer.StatType.FORM, 1, pool, _squad_with([outPlayer], bank=5), outPlayer) is cheap
    assert a._findReplacementPlayer(analyzer.StatType.FORM, 1, pool, _squad_with([outPlayer], bank=30), outPlayer) in (rich, cheap)
    assert a._findReplacementPlayer(analyzer.StatType.FORM, 1, [rich], _squad_with([outPlayer], bank=29), outPlayer) is None


def test_replacement_affordability_without_a_bank_falls_back_to_the_budget():
    a = _tiny_analyzer(None)
    rich = analyzer.PlayerData("D", "X", 4, 10, 90, 2, 1)
    rich.updateGameWeekTbl(1, 1, 90, 90)
    outPlayer = a.playerNameTbl["A X"]
    a.budget = 80 # 60 spent, 20 left: not enough for +30
    assert a._findReplacementPlayer(analyzer.StatType.FORM, 1, [rich], _squad_with([outPlayer], bank=None), outPlayer) is None
    a.budget = 95
    assert a._findReplacementPlayer(analyzer.StatType.FORM, 1, [rich], _squad_with([outPlayer], bank=None), outPlayer) is rich


def test_transfers_keep_wealth_constant():
    a = _tiny_analyzer(None)
    outPlayer, inPlayer = a.playerNameTbl["A X"], a.playerNameTbl["B X"]
    squad = _squad_with([outPlayer], bank=10)
    wealth = squad.bank + squad.totalCost
    a._applyTransfers(squad, [(outPlayer, inPlayer)])
    assert squad.bank == 20 and squad.totalCost == 50
    assert squad.bank + squad.totalCost == wealth
    noBank = _squad_with([outPlayer], bank=None)
    a._applyTransfers(noBank, [(outPlayer, inPlayer)])
    assert noBank.bank is None


# --- the simulation --------------------------------------------------------------

class _SpyPolicy(strategies.TransferPolicy):
    def __init__(self, inner, a):
        self.inner = inner
        self.a = a
        self.calls = 0

    def prepare(self, analyzer):
        self.inner.prepare(analyzer)

    def selectTransfers(self, analyzer, squadData, weekIdx, weekSquad, weekSubs, rng):
        a = self.a
        prices = a.priceTbls['snapshots'][weekIdx + 1]
        owned = [p for posList in squadData.positionTbl for p in posList]
        assert all(p.nowCost == prices[p.playerId] for p in a.playerNameTbl.values())  # prices are next week's
        assert squadData.totalCost == sum(p.nowCost for p in owned)
        assert squadData.bank >= 0
        transfers = self.inner.selectTransfers(analyzer, squadData, weekIdx, weekSquad, weekSubs, rng)
        assert squadData.bank + sum(out.nowCost - inn.nowCost for out, inn in transfers) >= 0  # affordable
        self.calls += 1
        return transfers


def test_simulation_buys_and_sells_at_each_weeks_prices(loaded_analyzer):
    a = loaded_analyzer
    base = _current_prices(a)
    squad = _starting_squad(a, 3)
    wealthAtStart = squad.bank + squad.totalCost
    assert wealthAtStart == a.budget
    spy = _SpyPolicy(strategies.WildcardTransferPolicy(strategies.WorstFormTransferPolicy(WINDOW), [10, 30], WINDOW), a)
    selector = strategies.WindowedFormSquadSelector(WINDOW)
    selector.prepare(a)
    spy.prepare(a)
    (statSquad, statCaptain) = selector.getStatTypes()
    a._evaluateStrategy(statSquad, statCaptain, squad, transferPolicy=spy, rng=random.Random(0), simulatePrices=True)
    assert spy.calls == a.lastCompletedGameWeek - 1
    assert squad.bank >= 0
    assert _current_prices(a) == base and a._priceWeek is None  # restored


def test_prices_are_restored_when_a_policy_raises(loaded_analyzer):
    class Boom(strategies.NoTransferPolicy):
        def selectTransfers(self, analyzer, squadData, weekIdx, weekSquad, weekSubs, rng):
            if weekIdx == 3:
                raise RuntimeError("boom")
            return []
    a = loaded_analyzer
    base = _current_prices(a)
    with pytest.raises(RuntimeError):
        a._evaluateStrategy(analyzer.StatType.TOTAL_POINTS, analyzer.StatType.TOTAL_POINTS, _starting_squad(a, 1),
                            transferPolicy=Boom(), rng=random.Random(0), simulatePrices=True)
    assert _current_prices(a) == base and a._priceWeek is None


def test_simulate_prices_does_nothing_without_price_changes(tmp_path):
    for fn in (fpl_data_files.TOP_LEVEL_FN, fpl_data_files.GAMEWEEK_PLAYER_FN, fpl_data_files.GAMEWEEK_FIXTURE_FN):
        shutil.copy(FIXTURE_DIR / fn, tmp_path / fn) # no cost file
    a = _load_analyzer(tmp_path)
    squad1 = _starting_squad(a, 2)
    squad2 = analyzer.SquadData(a.numPositions)
    squad1.copyTo(squad2)
    policy = strategies.WorstFormTransferPolicy(WINDOW)
    policy.prepare(a)
    results = []
    for squad, simulate in ((squad1, False), (squad2, True)):
        points = a._evaluateStrategy(analyzer.StatType.FORM, analyzer.StatType.FORM, squad, transferPolicy=policy,
                                     rng=random.Random(0), simulatePrices=simulate)
        results.append((points, [[p.playerId for p in posList] for posList in squad.positionTbl]))
    assert results[0] == results[1]


def test_compare_strategies_uses_the_prices_and_restores_them(loaded_analyzer, tmp_path, capsys):
    def build():
        return [strategies.Strategy("t", strategies.FixedStatSquadSelector(analyzer.StatType.TOTAL_POINTS),
                                    strategies.WorstFormTransferPolicy(WINDOW)),
                strategies.Strategy("wc", strategies.WindowedFormSquadSelector(WINDOW),
                                    strategies.WildcardTransferPolicy(strategies.WorstFormTransferPolicy(WINDOW), [10, 30], WINDOW))]
    a = loaded_analyzer
    base = _current_prices(a)
    withPrices = a.compareStrategies(build(), numTrials=3, seed=7)
    assert "Using per-gameweek prices" in capsys.readouterr().out
    assert _current_prices(a) == base and a._priceWeek is None
    assert a.compareStrategies(build(), numTrials=3, seed=7) == withPrices # deterministic
    capsys.readouterr() # discard that run's output

    for fn in (fpl_data_files.TOP_LEVEL_FN, fpl_data_files.GAMEWEEK_PLAYER_FN, fpl_data_files.GAMEWEEK_FIXTURE_FN):
        shutil.copy(FIXTURE_DIR / fn, tmp_path / fn)
    withoutPrices = _load_analyzer(tmp_path).compareStrategies(build(), numTrials=3, seed=7)
    assert "Using per-gameweek prices" not in capsys.readouterr().out
    assert withoutPrices != withPrices


def test_wildcard_tables_are_per_money_and_price_week(loaded_analyzer):
    a = loaded_analyzer
    rich = a.getBestSquadForWeek(9, WINDOW, 1000)
    richCost = sum(p.nowCost for posList in rich for p in posList)
    poorer = a.getBestSquadForWeek(9, WINDOW, 900)
    assert sum(p.nowCost for posList in poorer for p in posList) <= 900
    # a squad that costs c and is best for budget B is reused for every budget from c to B
    assert (poorer is rich) == (richCost <= 900)
    assert a.getBestSquadForWeek(9, WINDOW, 1000) is rich
    assert a.getBestSquadForWeek(9, WINDOW, richCost) is rich
    a._setPricesForWeek(10)
    try:
        assert a.getBestSquadForWeek(9, WINDOW, 1000) is not rich  # prices moved: its own cache entry
    finally:
        a._setPricesForWeek(None)
    assert a.getBestSquadForWeek(9, WINDOW, 1000) is rich


def test_reused_wildcard_table_is_as_good_as_a_fresh_search(loaded_analyzer):
    # A reused or warm-started search may pick a different squad among equally good ones
    # (the search's cost tie-break is best-effort), but never a worse or unaffordable one.
    a = loaded_analyzer
    a.getBestSquadForWeek(14, WINDOW, 1000) # seed the cache with a rich search
    fresh = _load_analyzer()
    tbl = fresh._buildTrailingPointsObjectiveTbl(14, WINDOW)
    for budget in (1010, 995, 980, 960):
        reused = a.getBestSquadForWeek(14, WINDOW, budget)
        direct = fresh.getBestSquadForWeek(14, WINDOW, budget)
        assert sum(p.nowCost for posList in reused for p in posList) <= budget
        assert sum(tbl[p.playerId] for posList in reused for p in posList) == sum(tbl[p.playerId] for posList in direct for p in posList)
