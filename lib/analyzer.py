import sys
import os
from enum import Enum
import json

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
	def __init__(self, weekIdx):
		self.statTbl = dict()
		self.weekIdx = weekIdx
		self.statTbl[StatType.WEEK_POINTS] = 0
		self.statTbl[StatType.COST] = 0 # cost of the player at the start of this week
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
		self.gameWeekTbl = dict() # map from game week idx to PlayerGameWeekData 
	def copyTo(self, other):
		other = PlayerData(self.firstName, self.lastName, self.playerId, self.totalPoints, self.nowCost, self.teamId, self.positionId)
		other.gameWeekTbl[:] = self.gameWeekTbl.copy()
	# Updates the entry for the week (this could happen for double gameweek).
	def updateGameWeekTbl(self, weekIdx, weekPoints, weekCost, minutesPlayed):
		gwData = self.gameWeekTbl.setdefault(weekIdx, PlayerGameWeekData(weekIdx))
		gwData.statTbl[StatType.WEEK_POINTS] += weekPoints
		gwData.statTbl[StatType.COST] = weekCost
		gwData.statTbl[StatType.MINUTES_PLAYED] += minutesPlayed
			

class TeamData:
	def __init__(self, numPositions):
		self.positionTbl = list() # map from position idx to list of players for that position
		self.totalCost = 0
		self.totalPoints = 0
		for i in range(numPositions):
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
		self.positionIdTbl = { 1 : "GK", 2 : "DEF", 3 : "MID", 4 : "FWD" }
		self.playersToExclude = {}
		self.budget = 1000 # in hundreds of thousands of Euros
		self.maxNumPlayersPerTeam = 3
		self.numWeeksForForm = 3 # number of weeks before current week to calculate form
		# number of players per position in a Fantasy team, including subs
		# order is GoalKeeper, Defender, Midfielder, Forward, Manager
		self.positionCountTbl = [ 2, 5, 5, 3, 0 ]
		self.minPositionCountTbl = [ 1, 3, 1, 1, 0 ] # minimum number of players required per position in a game week
		self.maxConsecutiveBadSearches = 100000000
		self.seasonStr = '2025-26'
		self.numPositions = len(self.positionIdTbl)
 		# number of weeks before the present to include when gathering data for
		# analysis. If -1 is specified, or if the number is larger than the total
		# number of weeks in the database, all week data will be used.
		self.numPrevWeeksForData = -1
		self.lastCompletedGameweek = -1

	def _readColumnLabels(self, colLabelLine, fn, colLabelTbl):
		colLabels = colLabelLine.split(',')
		for i in range(len(colLabels)):
			if colLabels[i] in colLabelTbl:
				colLabelTbl[colLabels[i]] = i
		# check that all necessary labels were found
		for label,colIdx in colLabelTbl.items():
			assert colIdx != None, "Error: could not find column label %s in file %s" % (label, fn)

	def _readTeamDataFromJSON(self, data):
		for teamData in data['teams']:
			teamName = teamData['name']
			teamId = teamData['id']
			self.teamIdTbl[teamId] = teamName
	
	def _readPlayerDataFromJSON(self, data):
		for playerData in data['elements']:
			firstName = playerData['first_name']
			lastName = playerData['second_name']
			playerId = playerData['id']
			totalPoints = playerData['total_points']
			nowCost = playerData['now_cost']
			teamId = playerData['team']
			positionId = playerData['element_type']
			self.playerNameTbl['%s %s' % (firstName, lastName)] = PlayerData(firstName, lastName, playerId, totalPoints, nowCost, teamId, positionId)

	def _readGameWeekDataFromJSON(self, topLevelData, allGameweekData):
		# make map from player ID to JSON top-level player data
		playerIdToDataTbl = {}
		for playerData in topLevelData['elements']:
			playerIdToDataTbl[playerData['id']] = playerData

		for event in topLevelData['events']:
			gameweekId = event['id'] # this should be the same as the game week number
			gameweekData = allGameweekData[str(gameweekId)]
			for gwPlayerData in gameweekData['elements']:
				playerId = gwPlayerData['id']
				topLevelPlayerData = playerIdToDataTbl[playerId]
				assert topLevelPlayerData['id'] == playerId
				firstName = topLevelPlayerData['first_name']
				lastName = topLevelPlayerData['second_name']
				playerName = "%s %s" % (firstName, lastName)
				minutesPlayed = int(gwPlayerData['stats']['minutes'])
				totalPoints = int(gwPlayerData['stats']['total_points'])
				playerData = self.playerNameTbl.get(playerName)
				if playerData == None:
					print("WARNING: no top-level data for %s (data found in week id %d)" % (playerName, gameweekId))
					continue
				nowCost = playerData.nowCost # FIXME: replace with actual cost this week
				playerData.updateGameWeekTbl(gameweekId, totalPoints, nowCost, minutesPlayed)
	
	def _getMedian(self, numList):
		sortedList = sorted(numList)
		midIdx = len(sortedList) // 2
		if len(sortedList) % 2 == 0:
			return (sortedList[midIdx] + sortedList[midIdx - 1]) / 2
		# else, odd
		return sortedList[midIdx]

	def _getStartWeek(self, numGameWeeks):
		if self.numPrevWeeksForData == -1 or self.numPrevWeeksForData > numGameWeeks:
			return 1
		else:
			return numGameWeeks - self.numPrevWeeksForData + 1
	
	def _examineGameWeekData(self):
		for name,playerData in self.playerNameTbl.items():
			pointsSum = 0
			formSum = 0
			pointsList = list() # list of points for all weeks up to current week
			startWeek = self._getStartWeek(len(playerData.gameWeekTbl))
			for weekIdx in range(startWeek, self.lastCompletedGameweek + 1):
				gwData = playerData.gameWeekTbl.get(weekIdx)
				if gwData == None:
					continue
				weekPoints = gwData.statTbl[StatType.WEEK_POINTS]
				pointsSum += weekPoints
				pointsList.append(weekPoints)
				gwData.statTbl[StatType.TOTAL_POINTS] = pointsSum
				if weekIdx >= self.numWeeksForForm:
					prevWeekIdx = weekIdx - self.numWeeksForForm
					prevWeekData = playerData.gameWeekTbl.get(prevWeekIdx)
					if prevWeekData != None:
						formSum -= prevWeekData.statTbl[StatType.WEEK_POINTS]
				formSum += gwData.statTbl[StatType.WEEK_POINTS]
				gwData.statTbl[StatType.FORM] = formSum / self.numWeeksForForm
				gwData.statTbl[StatType.MEDIAN_POINTS] = self._getMedian(pointsList)
			if self.numPrevWeeksForData == -1:
				if pointsSum != playerData.totalPoints:
					print("WARNING: Player %s (id: %d, Team: %s) total points mismatch: %d (reported total) vs. %d (summed total)" % (name, playerData.playerId, self.teamIdTbl[playerData.teamId], playerData.totalPoints, pointsSum))
			else:
				playerData.totalPoints = pointsSum
	
	def _getStatSortedPlayerListForWeek(self, statType, weekIdx, playerList, result):
		tempList = list() # list of (weekStat, playerData) for each player of the position in the given week
		for playerData in playerList:
			if weekIdx in playerData.gameWeekTbl:
				statVal = playerData.gameWeekTbl[weekIdx].statTbl[statType]
				tempList.append((statVal, playerData))
		tempList.sort(key=lambda x: x[0], reverse=True) # sort entries by player week statVal
		result[:] = tempList.copy()
	
	def _getBestTeamByStat(self, statTypeForTeam, statTypeForCaptain, weekIdx, teamData, weekTeam, weekSubs, weekCaptain):
		numGameWeeks = len(teamData.positionTbl[0][0].gameWeekTbl)
		assert numGameWeeks >= weekIdx, "Error: asked for data for week idx: %d, but we only have data for %d weeks!" % (weekIdx, numGameWeeks)
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
		minNumDefenders = min(len(defenderList), self.minPositionCountTbl[1])
		if len(keeperList) != 0:
			weekTeam.append(keeperList[0][1])
		for i in range(minNumDefenders):
			weekTeam.append(defenderList[i][1])
		if len(midfieldList) != 0:
			weekTeam.append(midfieldList[0][1])
		if len(forwardList) != 0:
			weekTeam.append(forwardList[0][1])
		# now we need 5 more players, which could be defenders, mid, or forwards.
		# Choose the best out of the remaining options.
		remainingPlayerList = defenderList[minNumDefenders:] + midfieldList[1:] + forwardList[1:]
		remainingPlayerList.sort(key=lambda x: x[0], reverse=True)
		for i in range(min(len(remainingPlayerList), 5)):
			weekTeam.append(remainingPlayerList[i][1])
		# add the remaining players as subs
		for i in remainingPlayerList[5:]:
			weekSubs.append(i[1])
		if len(keeperList) > 1:
			weekSubs.append(keeperList[1][1])
		# now choose the captain based on the chosen stat type
		captainSortedWeekTeam = list()
		self._getStatSortedPlayerListForWeek(statTypeForCaptain, weekIdx, weekTeam, captainSortedWeekTeam)
		return (captainSortedWeekTeam[0][1], captainSortedWeekTeam[1][1])

	def _getTeamPointsForGameWeek(self, weekIdx, weekTeam, weekSubs, weekCaptain, weekViceCaptain):
		finalWeekTeam = list() # final list of players selected after any substitutions
		result = 0
		posCountTbl = [0, 0, 0, 0] # number of players who did play, per position
		for playerData in weekTeam:
			if weekIdx in playerData.gameWeekTbl and playerData.gameWeekTbl[weekIdx].statTbl[StatType.MINUTES_PLAYED] != 0:
				result += playerData.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
				posCountTbl[playerData.positionId-1] += 1
				finalWeekTeam.append(playerData)

		usedSubIdxs = set()
		# first, try to add subs to fill missing position quotas
		for i in range(len(posCountTbl)):
			for j in range(len(weekSubs)):
				if posCountTbl[i] >= self.minPositionCountTbl[i]:
					break
				if j not in usedSubIdxs:
					if weekSubs[j].positionId-1 == i:
						if weekIdx in weekSubs[j].gameWeekTbl:
							result += weekSubs[j].gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
							usedSubIdxs.add(j)
							posCountTbl[i] += 1
							finalWeekTeam.append(weekSubs[j])

		# next, try to add subs in order of priority
		for j in range(len(weekSubs)):
			if len(finalWeekTeam) == 11:
				break
			if j not in usedSubIdxs:
				if weekSubs[j].positionId == 1:
					continue # don't add extra keeper
				if weekIdx in weekSubs[j].gameWeekTbl:
					result += weekSubs[j].gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
					usedSubIdxs.add(j)
					posCountTbl[weekSubs[j].positionId-1] += 1
					finalWeekTeam.append(weekSubs[j])
		# replace week team with final week team
		weekTeam[:] = finalWeekTeam.copy()
		
		# add the captain's week points to double-count them. If captain did not play,
		# add vice captain's points instead
		if weekIdx not in weekCaptain.gameWeekTbl or weekCaptain.gameWeekTbl[weekIdx].statTbl[StatType.MINUTES_PLAYED] == 0:
			if weekIdx in weekViceCaptain.gameWeekTbl:
				result += weekViceCaptain.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
		elif weekIdx in weekCaptain.gameWeekTbl:
			result += weekCaptain.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
		return result
	
	def _writeTeamWeekPerformanceToFile(self, weekIdx, totalPoints, weekPoints, weekTeam, weekSubs, weekCaptain, weekViceCaptain, fOut):
		fOut.write("Week: %d\n" % (weekIdx+1))
		fOut.write("Team Points This Week: %d\n" % weekPoints)
		fOut.write("Total Team Points After This Week: %d\n" % totalPoints)
		fOut.write("Captain: %s\n" % weekCaptain.name)
		fOut.write("Vice Captain: %s\n" % weekViceCaptain.name)
		fOut.write("Player\tWeekPoints\tMinutesPlayed\n")
		for playerData in weekTeam:
			if weekIdx in playerData.gameWeekTbl:
				weekPoints = playerData.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
				minutesPlayed = playerData.gameWeekTbl[weekIdx].statTbl[StatType.MINUTES_PLAYED]
			else:
				weekPoints = 0
				minutesPlayed = 0
			fOut.write("%s\t%d\t%d\n" % (playerData.name, weekPoints, minutesPlayed))
		fOut.write("SUBS:\n")
		for playerData in weekSubs:
			if weekIdx in playerData.gameWeekTbl:
				weekPoints = playerData.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
				minutesPlayed = playerData.gameWeekTbl[weekIdx].statTbl[StatType.MINUTES_PLAYED]
			else:
				weekPoints = 0
				minutesPlayed = 0
			fOut.write("%s\t%d\t%d\n" % (playerData.name, weekPoints, minutesPlayed))
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
		weekSubs = list() # substitutes, ordered by decreasing stat of choice
		weekCaptain = None
		weekViceCaptain = None
		(weekCaptain, weekViceCaptain) = self._getBestTeamByStat(StatType.COST, StatType.COST, 1, teamData, weekTeam, weekSubs, weekCaptain)
		# for each week, find number of points for all players in that week's team
		startWeek = self._getStartWeek(numGameWeeks)
		for weekIdx in range(startWeek, numGameWeeks):
			weekPoints = self._getTeamPointsForGameWeek(weekIdx, weekTeam, weekSubs, weekCaptain, weekViceCaptain)
			totalPoints += weekPoints
			# choose team for next week
			if DebugFn != None:
				self._writeTeamWeekPerformanceToFile(weekIdx, totalPoints, weekPoints, weekTeam, weekSubs, weekCaptain, weekViceCaptain, fOut)
			weekTeam = list()
			weekSubs = list()
			(weekCaptain, weekViceCaptain) = self._getBestTeamByStat(statTypeForTeam, statTypeForCaptain, weekIdx, teamData, weekTeam, weekSubs, weekCaptain)
	
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
				idx = curIdxList[posIdx]
				for i in range(idx, idx+numRemainingForPosition):
					testPointSum += self.playerPositionTbl[posIdx][i].totalPoints
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
		#totalStrategyPoints = 0 # FIXME: remove and uncomment above
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
		
	def _getLastCompletedGameweek(self, topLevelData):
		# find first week whose data is not finished
		for idx in range(len(topLevelData['events'])):
			if not topLevelData['events'][idx]['finished']:
				return topLevelData['events'][idx]['id'] # return week id, which should be same as week idx

	def readDataFromJSON(self, topLevelJsonFn, gameweekJsonFn):
		fTop = open(topLevelJsonFn, 'r')
		topLevelData = json.load(fTop)
		self.lastCompletedGameweek = self._getLastCompletedGameweek(topLevelData)
		self._readTeamDataFromJSON(topLevelData)
		self._readPlayerDataFromJSON(topLevelData) # read cumulative data for each player
		fGw = open(gameweekJsonFn, 'r')
		gameweekData = json.load(fGw)
		self._readGameWeekDataFromJSON(topLevelData, gameweekData)
		self._examineGameWeekData()
		self._createPlayerPositionTbl()

	def findBestTeam(self, outFn):
		bestTeamData = TeamData(self.numPositions)
		curTeamData = TeamData(self.numPositions)
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
		bestTeamData = TeamData(self.numPositions)
		# create team data without the given player
		curTeamData = TeamData(self.numPositions)
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
		curTeamData = TeamData(self.numPositions)
		playerList = list()
		# initialize budget to 0. Will be set to total cost of players + remaining in bank
		self.budget = 0
		# read team data from file
		self._readInCustomTeam(teamFn, playerList, curTeamData)
		# find metadata of team
		self._findCustomTeamMetadata(curTeamData)
		self.budget += curTeamData.totalCost
		print("Budget: %.1fm euros" % (self.budget/10.0))
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
