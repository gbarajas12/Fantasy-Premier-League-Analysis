"""Regression test: findBestSquad() over the (now complete) 2025-26 season
should still pick the squad checked in at 2025-26/team_of_the_season.txt.

Fixture data in tests/fixtures/season_2025_26/ is a trimmed-down copy of the
real FPL API responses for the full, finished 2025-26 season (only the
fields analyzer.py actually reads are kept, to keep the fixture small).
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "season_2025_26"
EXPECTED_TEAM_FILE = REPO_ROOT / "2025-26" / "team_of_the_season.txt"

sys.path.insert(0, str(REPO_ROOT / "lib"))


def _load_analyzer_module():
    import analyzer
    return analyzer


def _parse_team_file(path):
    """Split a best-team-of-season file into its squad table and summary stats."""
    full_points = active_points = None
    squad_lines = []
    for line in path.read_text().splitlines():
        if line.startswith("Full Squad Points:"):
            full_points = int(line.split(":")[1])
        elif line.startswith("Active Squad Points:"):
            active_points = int(line.split(":")[1])
        elif line.startswith("#"):
            continue
        else:
            squad_lines.append(line)
    return "\n".join(squad_lines).strip(), full_points, active_points


@pytest.fixture(scope="module")
def analyzer_module():
    return _load_analyzer_module()


def test_best_team_matches_checked_in_team_of_the_season(analyzer_module, tmp_path, capsys):
    analyzer = analyzer_module.Analyzer()
    # matches 2025-26/analyzer_config.json as committed: full budget, no
    # exclusions, use all available weeks, rank by form.
    analyzer.budget = 1000
    analyzer.playersToExclude = set()
    analyzer.teamsToExclude = set()
    analyzer.numPrevWeeksForData = -1
    analyzer.statTypeForSquad = analyzer_module.StatType.FORM
    analyzer.statTypeForCaptain = analyzer_module.StatType.FORM

    analyzer.readDataFromJSON(
        str(FIXTURE_DIR / "top_level.json"),
        str(FIXTURE_DIR / "gameweek_player.json"),
        str(FIXTURE_DIR / "gameweek_fixture.json"),
    )

    out_file = tmp_path / "best_team.out"
    analyzer.findBestSquad(str(out_file))

    # findBestSquad prints "totalPoints totalCost totalStrategyPoints" each
    # time it finds an improved squad; the last line is the final result.
    printed_lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    total_points, total_cost, total_strategy_points = (int(x) for x in printed_lines[-1].split())

    expected_squad_text, expected_full_points, expected_active_points = _parse_team_file(EXPECTED_TEAM_FILE)
    actual_squad_text = out_file.read_text().strip()

    assert actual_squad_text == expected_squad_text
    assert total_points == expected_full_points
    assert total_strategy_points == expected_active_points
