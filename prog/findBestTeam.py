import sys
import pathlib
sys.path.insert(0, "%s/../lib" % pathlib.Path(__file__).parent.resolve())
import analyzer
			
if __name__ == '__main__':
	if len(sys.argv) not in [3, 4]:
		print("Usage: python3 %s fplTopDir [teamPlayerList] outFn" % sys.argv[0])
		sys.exit(1)
	fplTopDir = sys.argv[1]
	teamFn = None
	if len(sys.argv) == 3:
		outFn = sys.argv[2]
	else:
		teamFn = sys.argv[2]
		outFn = sys.argv[3]

	analyzer = analyzer.Analyzer()
	analyzer.readData(fplTopDir)
	if teamFn == None:
		analyzer.findBestTeam(outFn)
	else:
		analyzer.findBestTransferOptions(teamFn, outFn)


