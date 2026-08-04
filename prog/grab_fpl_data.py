import sys
import requests
import json

if __name__ == '__main__':
	if len(sys.argv) > 1 and sys.argv[1] == '-h':
		print('Function: Grabs all data from the FPL website and dumps it to a JSON file.')
		sys.exit()

	fplUrl = 'https://fantasy.premierleague.com/api/'
	data = requests.get(f"{fplUrl}bootstrap-static/").json()
	topOutFn = 'fpl_top_data.json'
	gameweekPlayerFn = 'fpl_gameweek_player_data.json'
	gameweekFixtureFn = 'fpl_gameweek_fixture_data.json'
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

	# write player cost history data to a file. The FPL API only exposes this
	# per-gameweek breakdown for the currently in-progress season - once a
	# season ends it collapses to a start/end-of-season aggregate only.
	costHistoryFn = 'fpl_gameweek_cost_data.json'
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

