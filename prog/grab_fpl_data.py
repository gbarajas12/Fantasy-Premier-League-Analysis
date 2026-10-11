import argparse
import os
import sys
import pathlib
import requests
import json
sys.path.insert(0, "%s/../lib" % pathlib.Path(__file__).parent.resolve())
import fpl_data_files

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Grabs all data from the FPL website and dumps it to JSON files in a data directory.')
	parser.add_argument('fplDataDir', help='Directory to write the FPL data files to (created if needed). Existing files are overwritten.')
	parser.add_argument('--grabCost', action='store_true', help='Also grab per-gameweek player cost history (about 1 extra request per player, so it is slow). Only available for the current in-progress season.')
	args = parser.parse_args()
	os.makedirs(args.fplDataDir, exist_ok=True)

	fplUrl = 'https://fantasy.premierleague.com/api/'
	data = requests.get(f"{fplUrl}bootstrap-static/").json()
	topOutFn = os.path.join(args.fplDataDir, fpl_data_files.TOP_LEVEL_FN)
	gameweekPlayerFn = os.path.join(args.fplDataDir, fpl_data_files.GAMEWEEK_PLAYER_FN)
	gameweekFixtureFn = os.path.join(args.fplDataDir, fpl_data_files.GAMEWEEK_FIXTURE_FN)
	with open(topOutFn, 'w') as fOut:
		json.dump(data, fOut)

	# write gameweek player data to a file
	gameweekPlayerDataTbl = {}
	with open(gameweekPlayerFn, 'w') as fOut:
		for event in data['events']:
			gameweekId = event['id']
			gameweekPlayerDataTbl[gameweekId] = requests.get(f"{fplUrl}event/{gameweekId}/live/").json()
		json.dump(gameweekPlayerDataTbl, fOut)

	# write gameweek fixture data to a file
	gameweekFixtureDataTbl = {}
	with open(gameweekFixtureFn, 'w') as fOut:
		for event in data['events']:
			gameweekId = event['id']
			gameweekFixtureDataTbl[gameweekId] = requests.get(f"{fplUrl}fixtures/?event={gameweekId}").json()
		json.dump(gameweekFixtureDataTbl, fOut)

	if args.grabCost:
		# write player cost history data to a file. The FPL API only exposes this
		# per-gameweek breakdown for the currently in-progress season - once a
		# season ends it collapses to a start/end-of-season aggregate only.
		costHistoryFn = os.path.join(args.fplDataDir, fpl_data_files.GAMEWEEK_COST_FN)
		costHistoryTbl = {}
		numPlayers = len(data['elements'])
		with open(costHistoryFn, 'w') as fOut:
			for i, element in enumerate(data['elements']):
				playerId = element['id']
				playerSummary = requests.get(f"{fplUrl}element-summary/{playerId}/").json()
				costHistoryTbl[playerId] = {entry['round']: entry['value'] for entry in playerSummary['history']}
				if (i + 1) % 100 == 0 or (i + 1) == numPlayers:
					print(f"Fetched cost history for {i + 1}/{numPlayers} players")
			json.dump(costHistoryTbl, fOut)

