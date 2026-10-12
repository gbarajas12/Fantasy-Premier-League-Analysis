import argparse
import json
import os
import sys
import pathlib
sys.path.insert(0, "%s/../lib" % pathlib.Path(__file__).parent.resolve())
import fpl_data_files
import vaastav_data

if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Creates the per-gameweek player cost file (the one grab_fpl_data.py --grabCost writes) from a season directory of the vaastav/Fantasy-Premier-League repo. Unlike the FPL API, that repo keeps past seasons, so this works for seasons that have ended.')
	parser.add_argument('vaastavSeasonDir', help='Season directory of the vaastav/Fantasy-Premier-League repo, e.g. vaastav/Fantasy-Premier-League/data/2025-26 (must contain gws/gw<N>.csv files)')
	parser.add_argument('fplDataDir', help='FPL data directory to write the cost file to (created if needed). An existing cost file is overwritten.')
	args = parser.parse_args()

	costTbl = vaastav_data.readGameweekCosts(args.vaastavSeasonDir)
	os.makedirs(args.fplDataDir, exist_ok=True)
	outFn = os.path.join(args.fplDataDir, fpl_data_files.GAMEWEEK_COST_FN)
	with open(outFn, 'w') as fOut:
		json.dump(costTbl, fOut)
	numGameweeks = len({gw for playerCosts in costTbl.values() for gw in playerCosts})
	print(f"Wrote costs for {len(costTbl)} players over {numGameweeks} gameweeks to {outFn}")
