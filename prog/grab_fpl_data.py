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
	gameweekFn = 'fpl_gameweek_data.json'
	with open(topOutFn, 'w') as fOut:
		json.dump(data, fOut)

	# write gameweek data to a file
	gameweekDataTbl = {}
	with open(gameweekFn, 'w') as fOut:
		for event in data['events']:
			gameweekId = event['id']
			gameweekDataTbl[gameweekId] = requests.get(f"{fplUrl}event/{gameweekId}/live/").json()
		json.dump(gameweekDataTbl, fOut)
		
