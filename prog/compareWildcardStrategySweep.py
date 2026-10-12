import argparse
import sys
import pathlib
sys.path.insert(0, "%s/../lib" % pathlib.Path(__file__).parent.resolve())
import analyzer
import strategies

# The strategies this script compares: a long list, kept apart from the small default
# set in lib/strategies.py (compareStrategies.py) because it takes a long time to run.
# Edit these to change the wildcard strategy sweep. Windows are in gameweeks; a wildcard schedule is the
# gameweeks the chip is played in (see strategies.buildStrategies for the names).
SQUAD_FORM_WINDOWS = [3, 5, 10, 12, 15, 20, 25]
TRANSFER_FORM_WINDOWS = [3, 5, 10, 12, 15, 20, 25]
WILDCARD_WINDOWS = [10]
# every wildcard in gameweeks 2-19 with every wildcard in gameweeks 20-38
WILDCARD_SCHEDULES = [[firstHalfWeek, secondHalfWeek] for firstHalfWeek in range(2, 20) for secondHalfWeek in range(20, 39)]


def buildWildcardSweepStrategies():
	return strategies.buildStrategies(SQUAD_FORM_WINDOWS, TRANSFER_FORM_WINDOWS, WILDCARD_WINDOWS, WILDCARD_SCHEDULES)


if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Like compareStrategies.py, but runs the wildcard strategy sweep: the long list of strategies defined in this script (hundreds of strategies, so it takes a long time) instead of the small default set. Run grab_fpl_data.py to generate the data directory')
	parser.add_argument('fplDataDir', help='Directory of FPL data files, as written by grab_fpl_data.py')
	parser.add_argument('outputFile', help='Name of file to which the strategy comparison summary will be written')
	parser.add_argument('-c', '--configFile', required=False, help='Name of the file that configures analysis (e.g. which players to exclude)')
	parser.add_argument('--numTrials', type=int, default=20, help='Number of randomly generated starting squads to run each strategy against')
	parser.add_argument('--seed', type=int, required=False, help='Random seed, for reproducible comparisons')
	args = parser.parse_args()

	analyzer = analyzer.Analyzer()
	if args.configFile is not None:
		analyzer.readConfigFile(args.configFile)
	analyzer.readDataFromDir(args.fplDataDir)
	results = analyzer.compareStrategies(buildWildcardSweepStrategies(), args.numTrials, seed=args.seed, outFn=args.outputFile)
	for name, pointsList in analyzer.sortStrategyResultsByMeanPoints(results):
		print("%s: mean=%.1f n=%d" % (name, sum(pointsList) / len(pointsList), len(pointsList)))
