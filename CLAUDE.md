# CLAUDE.md

## Testing

After making any change to the codebase, run the full test suite:

```bash
python3 -m pytest tests/ -v
```

- `tests/test_best_team_regression.py` runs `Analyzer.findBestSquad` against
  fixture data for the completed 2025-26 season and checks the result matches
  the squad checked in at `2025-26/team_of_the_season.txt`.
- `tests/test_strategy_comparison.py` covers `Analyzer.compareStrategies`
  (season-long strategy comparison across randomly generated starting
  squads, see `lib/strategies.py`). Results are randomized, so these are
  structural/determinism checks rather than exact-value comparisons.
- `tests/test_gameweek_cost_history.py` covers `Analyzer._getHistoricalCost`
  (per-gameweek player price, via `readDataFromJSON`'s optional
  `costHistoryJsonFn` param and `grab_fpl_data.py`'s
  `fpl_gameweek_cost_data.json`). Fully synthetic - the FPL API only exposes
  per-gameweek price history for the current in-progress season, so this
  can't be tested against real 2025-26 data.
- `tests/test_squad_optimization_stat.py` covers `Analyzer.findBestSquad`'s
  `squadStat` param (`'total_points'` default, or `'points_per_match'` using
  FPL's `points_per_game` field). Fully synthetic - real 2025-26
  `points_per_game` data isn't reliably recoverable from any archived pull on
  disk (checked: stale/mismatched vs. the test fixtures).
