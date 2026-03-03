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
		
