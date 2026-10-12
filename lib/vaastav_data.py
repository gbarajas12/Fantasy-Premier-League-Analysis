import csv
import os
import re

# Reads per-gameweek data from a season directory of the vaastav/Fantasy-Premier-League
# repo (e.g. data/2025-26), whose gws/ subdirectory has one gw<N>.csv per gameweek
# with a row per player (per fixture) including the player's "element" (FPL player
# id), "round" (gameweek) and "value" (price that gameweek, in tenths of a million).

# Returns {playerId: {gameweek: price}} - the content of the fpl_gameweek_cost_data.json
# written by grab_fpl_data.py (--grabCost), sorted by player id and gameweek.
# As in the FPL API, a player has no entry for a gameweek in which he has no row (e.g. his
# team has no fixture). For a double gameweek the price at the last fixture is kept.
def readGameweekCosts(seasonDir):
	gwsDir = os.path.join(seasonDir, 'gws')
	assert os.path.isdir(gwsDir), f"Error: no gws directory in {seasonDir}. Expected a season directory of the vaastav/Fantasy-Premier-League repo, e.g. data/2025-26."
	gwFiles = dict()
	for fn in os.listdir(gwsDir):
		match = re.fullmatch(r'gw(\d+)\.csv', fn) # not merged_gw.csv or the xP<N>.csv files
		if match:
			gwFiles[int(match.group(1))] = os.path.join(gwsDir, fn)
	assert gwFiles, f"Error: no gw<N>.csv files found in {gwsDir}."
	costTbl = dict()
	for gw in sorted(gwFiles):
		with open(gwFiles[gw], newline='', encoding='utf-8') as fIn:
			reader = csv.DictReader(fIn)
			missingColumns = [col for col in ('element', 'round', 'value') if col not in (reader.fieldnames or [])]
			assert not missingColumns, f"Error: {gwFiles[gw]} has no {', '.join(missingColumns)} column(s)."
			rows = list(reader)
		rows.sort(key=lambda row: row.get('kickoff_time') or '') # stable; ISO timestamps sort chronologically
		for row in rows:
			assert int(row['round']) == gw, f"Error: {gwFiles[gw]} has a row for round {row['round']}."
			costTbl.setdefault(int(row['element']), dict())[gw] = int(row['value'])
	return {playerId: dict(sorted(costTbl[playerId].items())) for playerId in sorted(costTbl)}
