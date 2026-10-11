import argparse
import sys
import pathlib
sys.path.insert(0, "%s/../lib" % pathlib.Path(__file__).parent.resolve())
import analyzer

if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Prints the total score of a squad over the season in the FPL database. Run grab_fpl_data.py to generate the data directory')
	parser.add_argument('fplDataDir', help='Directory of FPL data files, as written by grab_fpl_data.py')
	parser.add_argument('inputSquad', help='Name of file containing the squad to score (same format as the findBestTeam.py --inputSquad file)')
	parser.add_argument('-c', '--configFile', required=False, help='Name of the file that configures analysis (e.g. the weekly squad and captain selection strategies)')
	args = parser.parse_args()

	analyzer = analyzer.Analyzer()
	if args.configFile is not None:
		analyzer.readConfigFile(args.configFile)
	analyzer.readDataFromDir(args.fplDataDir)
	(fullSquadPoints, activeSquadPoints) = analyzer.scoreSquad(args.inputSquad)
	print("Full Squad Points: %d" % fullSquadPoints)
	print("Active Squad Points: %d" % activeSquadPoints)
