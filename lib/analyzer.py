import sys
import os
from enum import Enum

DebugFn = "week_data.txt"
#self.positionCountTbl = [ 2, 3, 5, 3 ]
class StatType(Enum):
	COST           = 0
	WEEK_POINTS    = 1
	TOTAL_POINTS   = 2
	FORM           = 3
	MEDIAN_POINTS  = 4
	MINUTES_PLAYED = 5

class PlayerGameWeekData:
	def __init__(self, weekIdx, weekPoints, weekCost, minutesPlayed):
		self.statTbl = dict()
		self.weekIdx = weekIdx
		self.statTbl[StatType.WEEK_POINTS] = weekPoints
		self.statTbl[StatType.COST] = weekCost # cost of the player at the start of this week
		self.statTbl[StatType.TOTAL_POINTS] = 0 # sum of all points in the weeks up to and including this week
		self.statTbl[StatType.FORM] = 0 # average of points from previous self.numWeeksForForm weeks 
		self.statTbl[StatType.MEDIAN_POINTS] = 0 # median of points over all game weeks up to and including this week 
		self.statTbl[StatType.MINUTES_PLAYED] = 0 # number of minutes played this gameweek

class PlayerData:
	def __init__(self, firstName, lastName, playerId, totalPoints, nowCost, teamId, positionId):
		self.name = '%s %s' % (firstName, lastName)
		self.firstName = firstName
		self.lastName = lastName
		self.playerId = playerId
		self.totalPoints = totalPoints
		self.nowCost = nowCost
		self.teamId = teamId
		self.positionId = positionId
		self.gameWeekTbl = list() # map from game week idx (zero-indexed) to PlayerGameWeekData 
	def copyTo(self, other):
		other = PlayerData(self.firstName, self.lastName, self.playerId, self.totalPoints, self.nowCost, self.teamId, self.positionId)
		other.gameWeekTbl[:] = self.gameWeekTbl.copy()
	# If no entry at position weekIdx-1, creates a new entry with the inputs specified.
	# Else, updates the entry for the week (this could happen for double gameweek).
	def updateGameWeekTbl(self, weekIdx, weekPoints, weekCost, minutesPlayed):
		if len(self.gameWeekTbl) <= weekIdx-1:
			for i in range(len(self.gameWeekTbl), weekIdx-1):
				self.gameWeekTbl.append(PlayerGameWeekData(weekIdx, 0, 0, 0))
			self.gameWeekTbl.append(PlayerGameWeekData(weekIdx, weekPoints, weekCost, minutesPlayed))
		else:
			self.gameWeekTbl[weekIdx-1].statTbl[StatType.WEEK_POINTS] += weekPoints
			self.gameWeekTbl[weekIdx-1].statTbl[StatType.COST] = weekCost
			self.gameWeekTbl[weekIdx-1].statTbl[StatType.MINUTES_PLAYED] += minutesPlayed
			

class TeamData:
	def __init__(self):
		self.positionTbl = list() # map from position idx to list of players for that position
		self.totalCost = 0
		self.totalPoints = 0
		for i in range(5):
			self.positionTbl.append(list())
	def copyTo(self, other):
		other.positionTbl = list()
		for playerList in self.positionTbl:
			other.positionTbl.append(playerList.copy())
		other.totalCost = self.totalCost
		other.totalPoints = self.totalPoints

class Analyzer:
	def __init__(self):
		self.teamIdTbl = dict() # map from team ID number to team name
		self.playerNameTbl = dict() # map from player name to PlayerData
		self.playerPositionTbl = list() # map from position idx to list of all PlayerData for that position
		self.positionIdTbl = { 1 : "GK", 2 : "DEF", 3 : "MID", 4 : "FWD", 5 : "MGR" }
		self.playersToExclude = { 'Amad Diallo' }
		self.budget = 1000 # in hundreds of thousands of Euros
		self.maxNumPlayersPerTeam = 3
		self.numWeeksForForm = 3 # number of weeks before current week to calculate form
		# number of players per position in a Fantasy team, including subs
		# order is GoalKeeper, Defender, Midfielder, Forward, Manager
		self.positionCountTbl = [ 2, 5, 5, 3, 0 ]
		self.maxConsecutiveBadSearches = 10000000
		self.seasonStr = '2024-25'
 		# number of weeks before the present to include when gathering data for
		# analysis. If -1 is specified, or if the number is larger than the total
		# number of weeks in the database, all week data will be used.
		self.numPrevWeeksForData = -1

	def _readColumnLabels(self, colLabelLine, fn, colLabelTbl):
		colLabels = colLabelLine.split(',')
		for i in range(len(colLabels)):
			if colLabels[i] in colLabelTbl:
				colLabelTbl[colLabels[i]] = i
		# check that all necessary labels were found
		for label,colIdx in colLabelTbl.items():
			assert colIdx != None, "Error: could not find column label %s in file %s" % (label, fn)
	
	def _readTeamData(self, fn):
		teamIdLabel = "id"
		teamNameLabel = "name"
		colLabelTbl = dict() # map from column label to column idx (0-indexed)
		colLabelTbl[teamIdLabel] = None
		colLabelTbl[teamNameLabel] = None
		with open(fn,'r') as fIn:
			lines = fIn.readlines()
			self._readColumnLabels(lines[0], fn, colLabelTbl)
			for line in lines[1:]:
				tokens = line.split(',')
				if len(tokens) == 0:
					continue
				teamId = int(tokens[colLabelTbl[teamIdLabel]])
				teamName = tokens[colLabelTbl[teamNameLabel]]
				self.teamIdTbl[teamId] = teamName
	
	def _readPlayerData(self, fn):
		totPointsLabel = "total_points"
		playerIdLabel = "id"
		nowCostLabel = "now_cost"
		firstNameLabel = "first_name"
		secondNameLabel = "second_name"
		teamIdLabel = "team"
		positionIdLabel = "element_type"
		colLabelTbl = dict() # map from column label to column idx (0-indexed)
		colLabelTbl[totPointsLabel] = None
		colLabelTbl[playerIdLabel] = None
		colLabelTbl[nowCostLabel] = None
		colLabelTbl[firstNameLabel] = None
		colLabelTbl[secondNameLabel] = None
		colLabelTbl[teamIdLabel] = None
		colLabelTbl[positionIdLabel] = None
		with open(fn,'r') as fIn:
			lines = fIn.readlines()
			# read column labels on first line
			self._readColumnLabels(lines[0], fn, colLabelTbl)
			# read in all player data
			for line in lines[1:]:
				tokens = line.split(',')
				if len(tokens) == 0:
					continue
				firstName = tokens[colLabelTbl[firstNameLabel]]
				lastName = tokens[colLabelTbl[secondNameLabel]]
				playerId = int(tokens[colLabelTbl[playerIdLabel]])
				totalPoints = int(tokens[colLabelTbl[totPointsLabel]])
				nowCost = int(tokens[colLabelTbl[nowCostLabel]])
				teamId = int(tokens[colLabelTbl[teamIdLabel]])
				positionId = int(tokens[colLabelTbl[positionIdLabel]])
				self.playerNameTbl['%s %s' % (firstName, lastName)] = PlayerData(firstName, lastName, playerId, totalPoints, nowCost, teamId, positionId)
	
	def _readGameWeekData(self, gameWeekTopDir):
		colLabelTbl = dict() # map from column label to column idx (0-indexed)
		totPointsLabel = "total_points"
		nowCostLabel = "value"
		minutesLabel = "minutes"
		playerNameLabel = "name"
		colLabelTbl[totPointsLabel] = None
		colLabelTbl[nowCostLabel] = None
		colLabelTbl[minutesLabel] = None
		colLabelTbl[playerNameLabel] = None
		weekIdx = 0
		while True:
			weekIdx += 1
			weekFn = '%s/gw%d.csv' % (gameWeekTopDir, weekIdx)
			if not os.path.isfile(weekFn):
				weekIdx -= 1
				print("Read data for %d game weeks" % weekIdx)
				break
			with open(weekFn,'r') as fIn:
				lines = fIn.readlines()
				self._readColumnLabels(lines[0], weekFn, colLabelTbl)
				for line in lines[1:]:
					tokens = line.split(',')
					if len(tokens) == 0:
						continue
					playerName = tokens[colLabelTbl[playerNameLabel]]
					minutesPlayed = int(tokens[colLabelTbl[minutesLabel]])
					totalPoints = int(tokens[colLabelTbl[totPointsLabel]])
					nowCost = int(tokens[colLabelTbl[nowCostLabel]])
					playerData = self.playerNameTbl[playerName]
					playerData.updateGameWeekTbl(weekIdx, totalPoints, nowCost, minutesPlayed)
		# fill in any missing game week data (this could happen if a match is postponed)
		for name,playerData in self.playerNameTbl.items():
			if len(playerData.gameWeekTbl) != weekIdx:
				# put in blank data for the missing weeks
				testIdx = 0
				temp = playerData.gameWeekTbl.copy()
				playerData.gameWeekTbl.clear()
				prevCost = 0
				for gwData in temp:
					testIdx += 1
					if gwData.weekIdx > testIdx:
						# add blank data up until current weekIdx
						for i in range(testIdx, gwData.weekIdx):
							playerData.gameWeekTbl.append(PlayerGameWeekData(i, 0, prevCost, 0))
						testIdx = gwData.weekIdx
					playerData.gameWeekTbl.append(PlayerGameWeekData(gwData.weekIdx, gwData.statTbl[StatType.WEEK_POINTS], gwData.statTbl[StatType.COST], gwData.statTbl[StatType.MINUTES_PLAYED]))
					prevCost = gwData.statTbl[StatType.COST]

	def _getMedian(self, numList):
		sortedList = sorted(numList)
		midIdx = len(sortedList) // 2
		if len(sortedList) % 2 == 0:
			return (sortedList[midIdx] + sortedList[midIdx - 1]) / 2
		# else, odd
		return sortedList[midIdx]

	def _getStartWeek(self, numGameWeeks):
		if self.numPrevWeeksForData == -1 or self.numPrevWeeksForData > numGameWeeks:
			return  0
		else:
			return numGameWeeks - self.numPrevWeeksForData
	
	def _examineGameWeekData(self):
		for name,playerData in self.playerNameTbl.items():
			pointsSum = 0
			formSum = 0
			pointsList = list() # list of points for all weeks up to current week
			startWeek = self._getStartWeek(len(playerData.gameWeekTbl))
			for idx in range(startWeek, len(playerData.gameWeekTbl)):
				gwData = playerData.gameWeekTbl[idx]
				weekPoints = gwData.statTbl[StatType.WEEK_POINTS]
				pointsSum += weekPoints
				pointsList.append(weekPoints)
				gwData.statTbl[StatType.TOTAL_POINTS] = pointsSum
				if idx >= self.numWeeksForForm:
					formSum -= playerData.gameWeekTbl[idx - self.numWeeksForForm].statTbl[StatType.WEEK_POINTS]
				formSum += gwData.statTbl[StatType.WEEK_POINTS]
				gwData.statTbl[StatType.FORM] = formSum / self.numWeeksForForm
				gwData.statTbl[StatType.MEDIAN_POINTS] = self._getMedian(pointsList)
			if self.numPrevWeeksForData == -1:
				assert pointsSum == playerData.totalPoints
			else:
				playerData.totalPoints = pointsSum
	
	def _getStatSortedPlayerListForWeek(self, statType, weekIdx, playerList,  result):
		tempList = list() # list of (weekStat, playerData) for each player of the position in the given week
		for playerData in playerList:
			statVal = playerData.gameWeekTbl[weekIdx].statTbl[statType]
			tempList.append((statVal, playerData))
		tempList.sort(key=lambda x: x[0], reverse=True) # sort entries by player week statVal
		result[:] = tempList.copy()
	
	def _getBestTeamByStat(self, statTypeForTeam, statTypeForCaptain, weekIdx, teamData, weekTeam, weekCaptain):
		numGameWeeks = len(teamData.positionTbl[0][0].gameWeekTbl)
		assert numGameWeeks > weekIdx, "Error: asked for data for week idx: %d, but we only have data for %d weeks!" % (weekIdx, numGameWeeks)
		# get list of players fir each position, sorted by decreasing statVal for this week
		# each element is (statVal, playerData)
		keeperList = list()
		defenderList = list()
		midfieldList = list()
		forwardList = list()
		self._getStatSortedPlayerListForWeek(statTypeForTeam, weekIdx, teamData.positionTbl[0], keeperList)
		self._getStatSortedPlayerListForWeek(statTypeForTeam, weekIdx, teamData.positionTbl[1], defenderList)
		self._getStatSortedPlayerListForWeek(statTypeForTeam, weekIdx, teamData.positionTbl[2], midfieldList)
		self._getStatSortedPlayerListForWeek(statTypeForTeam, weekIdx, teamData.positionTbl[3], forwardList)
		# formation rules: must have 1 goalie, at least: 3 defenders, 1 mid, 1 forward
		# choose highest statVal goalie for week 1
		weekTeam.append(keeperList[0][1])
		for i in range(3):
			weekTeam.append(defenderList[i][1])
		weekTeam.append(midfieldList[0][1])
		weekTeam.append(forwardList[0][1])
		# now we need 5 more players, which could be defenders, mid, or forwards.
		# Choose the best out of the remaining options.
		remainingPlayerList = defenderList[3:] + midfieldList[1:] + forwardList[1:]
		remainingPlayerList.sort(key=lambda x: x[0], reverse=True)
		for i in range(5):
			weekTeam.append(remainingPlayerList[i][1])
		# now choose the captain based on the chosen stat type
		captainSortedWeekTeam = list()
		self._getStatSortedPlayerListForWeek(statTypeForCaptain, weekIdx, weekTeam, captainSortedWeekTeam)
		return captainSortedWeekTeam[0][1]
	
	def _getTeamPointsForGameWeek(self, weekIdx, weekTeam, weekCaptain):
		result = 0
		for playerData in weekTeam:
			result += playerData.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
		# add the captain's week points to double-count them
		result += weekCaptain.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
		return result
	
	def _writeTeamWeekPerformanceToFile(self, weekIdx, totalPoints, weekPoints, weekTeam, weekCaptain, fOut):
		fOut.write("Week: %d\n" % (weekIdx+1))
		fOut.write("Team Points This Week: %d\n" % weekPoints)
		fOut.write("Total Team Points After This Week: %d\n" % totalPoints)
		fOut.write("Captain: %s\n" % weekCaptain.name)
		fOut.write("Player\tWeekPoints\n")
		for playerData in weekTeam:
			weekPoints = playerData.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
			if playerData.name == weekCaptain.name:
				weekPoints += weekPoints
			fOut.write("%s\t%d\n" % (playerData.name, weekPoints))
		fOut.write("\n")
	
	# Determine the total number of points the team has acheived if the strategy
	# chosen was to pick the players each week to maximize the desired statistic
	# based on the players' performance prior to each week. For example, if
	# StatType.TOTAL_POINTS is chosen for statTypeForTeam, the starting lineup 
	# each week will be chosen based on which players had the most total points before that week.
	# A separate strategy may be chosen for choosing the captain each week.
	# NOTE: The first week's players are chose by maximizing the cost of the team.
	def _evaluateStrategy(self, statTypeForTeam, statTypeForCaptain, teamData):
		if DebugFn != None:
			fOut = open(DebugFn,'w')
		numGameWeeks = len(teamData.positionTbl[0][0].gameWeekTbl)
		totalPoints = 0
		weekTeam = list() # subset of players for current week
		weekCaptain = None
		weekCaptain = self._getBestTeamByStat(StatType.COST, StatType.COST, 0, teamData, weekTeam, weekCaptain)
		# for each week, find number of points for all players in that week's team
		startWeek = self._getStartWeek(numGameWeeks)
		for weekIdx in range(startWeek, numGameWeeks):
			weekPoints = self._getTeamPointsForGameWeek(weekIdx, weekTeam, weekCaptain)
			#print("\t%d" % weekPoints)
			totalPoints += weekPoints
			# choose team for next week
			if DebugFn != None:
				self._writeTeamWeekPerformanceToFile(weekIdx, totalPoints, weekPoints, weekTeam, weekCaptain, fOut)
			weekTeam = list()
			weekCaptain = self._getBestTeamByStat(statTypeForTeam, statTypeForCaptain, weekIdx, teamData, weekTeam, weekCaptain)
	
		if DebugFn != None:
			fOut.close()
	
		return totalPoints
	
	def _createPlayerPositionTbl(self):
		for i in range(len(self.positionIdTbl)):
			self.playerPositionTbl.append(list())
		for name,playerData in self.playerNameTbl.items():
			# skip players with no points
			if playerData.totalPoints <= 0:
				continue
			if playerData.name in self.playersToExclude:
				continue
			#if len(self.playerPositionTbl[playerData.positionId-1]) == 10:
			#	continue
			self.playerPositionTbl[playerData.positionId-1].append(playerData)
		# now prune each position's list of players by removing the worst players.
		# these are players with the lowest number of total points for their price
		for posIdx in range(len(self.playerPositionTbl)):
			# list of (playerCost, playerData), sorted by decreasing cost
			sortedCostList = sorted(self.playerPositionTbl[posIdx].copy(), key=lambda x: x.nowCost, reverse=True)
			# clear the currently stored list. It will be replaced later.
			self.playerPositionTbl[posIdx] = list()
			for i in range(len(sortedCostList)): 
				playerData = sortedCostList[i]
				# ignore this player if there are enought other players with one of the following:
				# - lower cost, at least as many points as current player
				# - equal cost, more points than current player
				# If the number of better players is at least the number of required players of that position on the team,
				# skip this player. (e.g. there are 2 required goalies and at least 2 goalies are better than the current one).
				betterPlayerCount = 0
				# only look at players that are not more expensive
				for otherPlayerData in sortedCostList[i+1:]:
					if otherPlayerData.nowCost < playerData.nowCost and otherPlayerData.totalPoints >= playerData.totalPoints:
						betterPlayerCount += 1
					elif otherPlayerData.nowCost == playerData.nowCost and otherPlayerData.totalPoints > playerData.totalPoints:
						betterPlayerCount += 1
					if betterPlayerCount == self.positionCountTbl[posIdx]:
						break
				if betterPlayerCount < self.positionCountTbl[posIdx]:
					self.playerPositionTbl[posIdx].append(playerData)
				#if betterPlayerCount == 0:
				#	self.playerPositionTbl[posIdx].append(playerData)
		# sort players by decreasing total points, and then by increasing nowCost
		for posIdx in range(len(self.playerPositionTbl)):
			self.playerPositionTbl[posIdx].sort(key = lambda x: x.nowCost)
			self.playerPositionTbl[posIdx].sort(key = lambda x: x.totalPoints, reverse=True)
		#print ("%d %d %d %d" % (len(self.playerPositionTbl[0]), len(self.playerPositionTbl[1]), len(self.playerPositionTbl[2]), len(self.playerPositionTbl[3])))
	
	# Returns True if no combination of players can be added to the current team to
	# beat the best team.
	def _cannotBeatBestTeam(self, bestTeamData, curTeamData, curIdxList):
		curToBestPointsDiff = bestTeamData.totalPoints - curTeamData.totalPoints
		testPointSum = 0
		for posIdx in range(len(curTeamData.positionTbl)):
			numRemainingForPosition = self.positionCountTbl[posIdx] - len(curTeamData.positionTbl[posIdx])
			if numRemainingForPosition > 0:
				allPlayerList = self.playerPositionTbl[posIdx]
				idx = curIdxList[posIdx]
				for i in range(idx, idx+numRemainingForPosition):
					testPointSum += allPlayerList[idx].totalPoints
		return (testPointSum <= curToBestPointsDiff)
	
	def _writeBestTeamToFile(self, bestTeamData, outFn):
		# write outfile
		totalPoints = 0
		with open(outFn,'w') as fOut:
			for posIdx in range(len(bestTeamData.positionTbl)):
				fOut.write("%s\n" % self.positionIdTbl[posIdx+1])
				fOut.write("Name\tClub\tCost\tTotal Points\n")
				for playerData in bestTeamData.positionTbl[posIdx]:
					totalPoints += playerData.totalPoints
					clubName = self.teamIdTbl[playerData.teamId]
					fOut.write("%s\t%s\t%.1f\t%d\n" % (playerData.name, clubName, playerData.nowCost/10.0, playerData.totalPoints))
				fOut.write("\n")
		assert totalPoints == bestTeamData.totalPoints
		totalStrategyPoints = self._evaluateStrategy(StatType.FORM, StatType.FORM, bestTeamData)
		print("%d %d %d" % (totalPoints, bestTeamData.totalCost, totalStrategyPoints))
	
	def _dfsFindBestTeam(self, teamCountTbl, curIdxList, bestTeamData, curTeamData, numConsecutiveBadSearches, outFn=None):
		# assemble every possible team
		#print("%d %d %d %d" % (curIdxList[0], curIdxList[1], curIdxList[2], curIdxList[3]))
		# end search if no combination of players can be added to current team to beat the best team
		if self._cannotBeatBestTeam(bestTeamData, curTeamData, curIdxList):
			return
		for posIdx in range(len(curTeamData.positionTbl)):
			curPlayerList = curTeamData.positionTbl[posIdx]
			numRemainingForPosition = self.positionCountTbl[posIdx] - len(curPlayerList)
			if numRemainingForPosition > 0:
				allPlayerList = self.playerPositionTbl[posIdx]
				endIdx = len(allPlayerList)-numRemainingForPosition+1
				if endIdx <= 0:
					endIdx = len(allPlayerList)
				for i in range(curIdxList[posIdx], endIdx):
					if numConsecutiveBadSearches[0] >= self.maxConsecutiveBadSearches:
						return
					if curTeamData.totalCost + allPlayerList[i].nowCost > self.budget:
						continue # we cannot complete the team, so end this search branch
					# check if we have reached the limit of players for the current player's club
					if teamCountTbl[allPlayerList[i].teamId] == self.maxNumPlayersPerTeam:
						continue
					teamCountTbl[allPlayerList[i].teamId] += 1
					curPlayerList.append(allPlayerList[i])
					curTeamData.totalPoints += allPlayerList[i].totalPoints
					curTeamData.totalCost += allPlayerList[i].nowCost
					newIdxList = curIdxList.copy()
					newIdxList[posIdx] = i+1
					# find all teams that include the current list of players
					self._dfsFindBestTeam(teamCountTbl, newIdxList, bestTeamData, curTeamData, numConsecutiveBadSearches, outFn)
					# remove current player before examining next player
					curPlayerList.pop()
					curTeamData.totalPoints -= allPlayerList[i].totalPoints
					curTeamData.totalCost -= allPlayerList[i].nowCost
					teamCountTbl[allPlayerList[i].teamId] -= 1
				break # we have already examined all teams with the current set of players, so we can end our search
		# here we have a complete team to compare against the best team yet found
		if bestTeamData.totalPoints < curTeamData.totalPoints:
			# update best team data
			curTeamData.copyTo(bestTeamData)
			if outFn != None:
				self._writeBestTeamToFile(bestTeamData, outFn)
			numConsecutiveBadSearches[0] += 0
		else:
			numConsecutiveBadSearches[0] += 1

	def _readInCustomTeam(self, teamFn, playerList, curTeamData):
		playerList.clear()
		with open(teamFn,'r') as fIn:
			lines = fIn.readlines()
			# first line gives remaing budget in bank, in millions of euros
			self.budget += int(float(lines[0].split()[-1]) * 10) # convert to 100,000s of euros
			for line in lines[1:]:
				tokens = line.split()
				if len(tokens) == 0:
					continue
				playerName = line.strip()
				playerData = self.playerNameTbl.get(playerName)
				assert playerData != None, "Error: no player named %s. Make sure full name is spelled correctly as it appears in the database!" % playerName
				playerList.append(playerData)
				playerPos = playerData.positionId
				curTeamData.positionTbl[playerPos-1].append(playerData)
		# make sure we have the desired distribution of positions
		for posIdx in range(len(curTeamData.positionTbl)):
			if len(curTeamData.positionTbl[posIdx]) != self.positionCountTbl[posIdx]:
				positionStr = self.positionIdTbl[posIdx+1]
				assert 0, "Error: incorrect number of %s: %d. Should be %d" % (positionStr, len(curTeamData.positionTbl[posIdx]), self.positionCountTbl[posIdx])
		

	def readData(self, fplTopDir):
		teamDataFn = "%s/data/%s/teams.csv" % (fplTopDir, self.seasonStr)
		rawPlayerDataFn = '%s/data/%s/players_raw.csv' % (fplTopDir, self.seasonStr)
		gameWeekTopDir = '%s/data/%s/gws' % (fplTopDir, self.seasonStr)
		self._readTeamData(teamDataFn)
		self._readPlayerData(rawPlayerDataFn) # read cumulative data for each player
		self._readGameWeekData(gameWeekTopDir)
		self._examineGameWeekData()
		self._createPlayerPositionTbl()

	def findBestTeam(self, outFn):
		bestTeamData = TeamData()
		curTeamData = TeamData()
		teamCountTbl = [0]*(len(self.teamIdTbl)+1) # map from team id to count of players for that team
		positionIdxList = [0, 0, 0, 0] # each element is the current idx within the full player list of the position given by that element
		numConsecutiveBadSearches = [0]
		self._dfsFindBestTeam(teamCountTbl, positionIdxList, bestTeamData, curTeamData, numConsecutiveBadSearches, outFn)

	def _findCustomTeamMetadata(self, curTeamData):
		for posIdx in range(len(curTeamData.positionTbl)):
			playerList = curTeamData.positionTbl[posIdx]
			for playerData in playerList:
				lastWeekData = playerData.gameWeekTbl[-1]
				curTeamData.totalPoints += lastWeekData.statTbl[StatType.TOTAL_POINTS]
				curTeamData.totalCost += lastWeekData.statTbl[StatType.COST]

	def _searchForBetterPlayer(self, posIdx, playerListIdx, playerList, origTeamData, transferOptions):
		bestTeamData = TeamData()
		# create team data without the given player
		curTeamData = TeamData()
		origTeamData.copyTo(bestTeamData)
		origTeamData.copyTo(curTeamData)
		playerToTransfer = curTeamData.positionTbl[posIdx].pop(playerListIdx)
		curTeamData.totalCost -= playerToTransfer.nowCost
		curTeamData.totalPoints -= playerToTransfer.totalPoints
		
		teamCountTbl = [0]*(len(self.teamIdTbl)+1) # map from team id to count of players for that team
		for playerData in playerList:
			if playerData.name != playerToTransfer.name:
				teamCountTbl[playerData.teamId] += 1

		positionIdxList = [0, 0, 0, 0] # each element is the current idx within the full player list of the position given by that element
		numConsecutiveBadSearches = [0]
		self._dfsFindBestTeam(teamCountTbl, positionIdxList, bestTeamData, curTeamData, numConsecutiveBadSearches)
		# if best team total points did not improve over original, skip
		pointsImprovement = bestTeamData.totalPoints - origTeamData.totalPoints
		if pointsImprovement <= 0:
			return
		# check if there is a new player for the position
		origPosPlayerNames = set()
		for playerData in origTeamData.positionTbl[posIdx]:
			origPosPlayerNames.add(playerData.name)
		for playerData in bestTeamData.positionTbl[posIdx]:
			if playerData.name not in origPosPlayerNames:
				transferOptions.append((playerToTransfer, playerData, pointsImprovement))
				break

	def findBestTransferOptions(self, teamFn, outFn):
		curTeamData = TeamData()
		playerList = list()
		# initialize budget to 0. Will be set to total cost of players + remaining in bank
		self.budget = 0
		# read team data from file
		self._readInCustomTeam(teamFn, playerList, curTeamData)
		# find metadata of team
		self._findCustomTeamMetadata(curTeamData)
		self.budget += curTeamData.totalCost
		transferOptions = list() # list of (origPlayer, newPlayer, pointsImprovement)
		# add all players from current team to exclusion list
		origExclusionList = self.playersToExclude.copy()
		self.playersToExclude.update(playerList)
		# for each player, search for a player that would improve the team
		for posIdx in range(len(curTeamData.positionTbl)):
			for playerListIdx in range(len(curTeamData.positionTbl[posIdx])):
				self._searchForBetterPlayer(posIdx, playerListIdx, playerList, curTeamData, transferOptions)
		# sort by points improvement
		transferOptions.sort(key=lambda x: x[2], reverse=True)
		# write data to outfile
		with open(outFn,'w') as fOut:
			fOut.write("PlayerOut\tPlayerIn\tPointsImprovement\n")
			for i in range(len(transferOptions)):
				op = transferOptions[i]
				fOut.write("%s\t%s\t%d\n" % (op[0].name, op[1].name, op[2]))

		# set exclusion list back to original value
		self.playersToExclude = origExclusionList.copy()
