import sys
import pathlib
sys.path.insert(0, "%s/../lib" % pathlib.Path(__file__).parent.resolve())
import analyzer
			
if __name__ == '__main__':
	if len(sys.argv) not in [4, 5]:
		print("Usage: python3 %s fplTopLevelJson fplGameweekJson [teamPlayerList] outFn" % sys.argv[0])
		sys.exit(1)
	teamFn = None
	fplTopLevelJson = sys.argv[1]
	fplGameweekJson = sys.argv[2]
	outFn = sys.argv[-1]
	if len(sys.argv) == 5:
		teamFn = sys.argv[-2]

	analyzer = analyzer.Analyzer()
	analyzer.readDataFromJSON(fplTopLevelJson, fplGameweekJson)
	if teamFn is None:
		analyzer.findBestTeam(outFn)
	else:
		analyzer.findBestTransferOptions(teamFn, outFn)


