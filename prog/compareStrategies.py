import argparse
import sys
import pathlib
sys.path.insert(0, "%s/../lib" % pathlib.Path(__file__).parent.resolve())
import analyzer
import strategies

if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Compares season-long FPL strategies across randomly generated starting squads. Run grab_fpl_data.py to generate JSON inputs')
	parser.add_argument('fplTopLevelJSON')
	parser.add_argument('fplGameWeekPlayerJSON')
	parser.add_argument('fplGameWeekFixtureJSON')
	parser.add_argument('outputFile', help='Name of file to which the strategy comparison summary will be written')
	parser.add_argument('-c', '--configFile', required=False, help='Name of the file that configures analysis (e.g. which players to exclude)')
	parser.add_argument('--numTrials', type=int, default=20, help='Number of randomly generated starting squads to run each strategy against')
	parser.add_argument('--seed', type=int, required=False, help='Random seed, for reproducible comparisons')
	args = parser.parse_args()

	analyzer = analyzer.Analyzer()
	if args.configFile is not None:
		analyzer.readConfigFile(args.configFile)
	analyzer.readDataFromJSON(args.fplTopLevelJSON, args.fplGameWeekPlayerJSON, args.fplGameWeekFixtureJSON)
	results = analyzer.compareStrategies(strategies.buildDefaultStrategies(), args.numTrials, seed=args.seed, outFn=args.outputFile)
	for name, pointsList in results.items():
		print("%s: mean=%.1f n=%d" % (name, sum(pointsList) / len(pointsList), len(pointsList)))
