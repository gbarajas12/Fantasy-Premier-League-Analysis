import sys
import requests
import json

if __name__ == '__main__':
	if len(sys.argv) > 1 and sys.argv[1] == '-h':
		print('Function: Grabs all data from the FPL website and dumps it to a JSON file.')
		sys.exit()

	fplUrl = 'https://fantasy.premierleague.com/api/'
	data = requests.get(fplUrl+'bootstrap-static/').json()
	outFn = 'fpl_data.json'
	with open(outFn, 'w') as fOut:
		json.dump(data, fOut)
