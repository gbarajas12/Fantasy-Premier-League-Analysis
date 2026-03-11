import argparse
import sys
import pathlib
sys.path.insert(0, "%s/../lib" % pathlib.Path(__file__).parent.resolve())
import analyzer
			
if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Finds the best team by a specified metric, given the FPL database. Run grab_fpl_data.py to generate JSON inputs')
	parser.add_argument('fplTopLevelJSON')
	parser.add_argument('fplGameWeekPlayerJSON')
	parser.add_argument('fplGameWeekFixtureJSON')
	parser.add_argument('outputFile', help='Name of file to which best team information will be written')
	parser.add_argument('-c', '--configFile', required=False, help='Name of the file that configures analysis (e.g. which players to exclude)')
	parser.add_argument('--inputSquad', required=False, help='Name of file containing input squad. If provided, will output best transfer choices.')
	args = parser.parse_args()

	inputSquadFn = vars(args)['inputSquad']
	fplTopLevelJson = vars(args)['fplTopLevelJSON']
	fplGameweekPlayerJson = vars(args)['fplGameWeekPlayerJSON']
	fplGameweekFixtureJson = vars(args)['fplGameWeekFixtureJSON']
	outFn = vars(args)['outputFile']
	configFn = vars(args)['configFile']

	analyzer = analyzer.Analyzer()
	analyzer.readDataFromJSON(fplTopLevelJson, fplGameweekPlayerJson, fplGameweekFixtureJson)
	#analyzer._runLinearRegression()
	if inputSquadFn is None:
		analyzer.findBestSquad(outFn)
	else:
		analyzer.findBestTransferOptions(inputSquadFn, outFn)


