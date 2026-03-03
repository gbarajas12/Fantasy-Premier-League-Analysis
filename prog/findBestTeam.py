import sys
import pathlib
sys.path.insert(0, "%s/../lib" % pathlib.Path(__file__).parent.resolve())
import analyzer
			
if __name__ == '__main__':
	if len(sys.argv) not in [5, 6]:
		print("Usage: python3 %s fplTopLevelJson fplGameweekPlayerJson fplGameweekFixtureData [teamPlayerList] outFn" % sys.argv[0])
		sys.exit(1)
	teamFn = None
	fplTopLevelJson = sys.argv[1]
	fplGameweekPlayerJson = sys.argv[2]
	fplGameweekFixtureJson = sys.argv[3]
	outFn = sys.argv[-1]
	if len(sys.argv) == 6:
		teamFn = sys.argv[-2]

	analyzer = analyzer.Analyzer()
	analyzer.readDataFromJSON(fplTopLevelJson, fplGameweekPlayerJson, fplGameweekFixtureJson)
	#analyzer._runLinearRegression()
	if teamFn is None:
		analyzer.findBestSquad(outFn)
	else:
		analyzer.findBestTransferOptions(teamFn, outFn)


