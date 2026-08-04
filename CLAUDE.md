# CLAUDE.md

## Testing

After making any change to the codebase, run the regression test:

```bash
python3 -m pytest tests/test_best_team_regression.py -v
```

It runs `Analyzer.findBestSquad` against fixture data for the completed
2025-26 season and checks the result matches the squad checked in at
`2025-26/team_of_the_season.txt`.
