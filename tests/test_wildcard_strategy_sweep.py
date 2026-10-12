"""The long strategy list in prog/compareWildcardStrategySweep.py takes too long to run in the
test suite, so this only checks that it builds (which validates every wildcard schedule)
and that the default list stays small."""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

import strategies

spec = importlib.util.spec_from_file_location("compareWildcardStrategySweep", REPO_ROOT / "prog" / "compareWildcardStrategySweep.py")
compareWildcardStrategySweep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compareWildcardStrategySweep)  # defines the wildcard strategy sweep; its main only runs as a script


def test_default_strategy_list_is_small_and_has_unique_names():
    names = [strategy.name for strategy in strategies.buildDefaultStrategies()]
    assert 1 < len(names) <= 20
    assert len(set(names)) == len(names)
    assert "baseline" in names


def test_sweep_builds_with_unique_names_and_includes_the_default_strategies():
    sweepNames = [strategy.name for strategy in compareWildcardStrategySweep.buildWildcardSweepStrategies()]
    assert len(sweepNames) > 300
    assert len(set(sweepNames)) == len(sweepNames)
    assert set(strategy.name for strategy in strategies.buildDefaultStrategies()) <= set(sweepNames)
