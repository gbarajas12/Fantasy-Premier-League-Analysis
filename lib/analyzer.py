import sys
import os
from enum import Enum
import json
from sklearn import linear_model
import matplotlib.pyplot as plt

DebugFn = "week_data.txt"
class StatType(Enum):
	COST           = 0
	WEEK_POINTS    = 1
	TOTAL_POINTS   = 2
	FORM           = 3
	MEDIAN_POINTS  = 4
	MINUTES_PLAYED = 5
	GOALS_FOR      = 6 # goals scored by a team
	GOALS_AGAINST  = 7 # goals scored against a team


class PlayerGameWeekData:
	def __init__(self, weekIdx):
		self.statTbl = dict()
		self.weekIdx = weekIdx
		self.statTbl[StatType.WEEK_POINTS] = 0
		self.statTbl[StatType.COST] = 0 # cost of the player at the start of this week
		self.statTbl[StatType.TOTAL_POINTS] = 0 # sum of all points in the weeks up to and including this week
		self.statTbl[StatType.FORM] = 0 # average of points from previous self.numWeeksForForm weeks 
		self.statTbl[StatType.MEDIAN_POINTS] = 0 # median of points over all game weeks up to and including this week 
		self.statTbl[StatType.MINUTES_PLAYED] = 0 # number of minutes played this gameWeek


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
	# Updates the entry for the week (this could happen for double gameWeek).
	def updateGameWeekTbl(self, weekIdx, weekPoints, weekCost, minutesPlayed):
		gwData = self.gameWeekTbl.setdefault(weekIdx, PlayerGameWeekData(weekIdx))
		gwData.statTbl[StatType.WEEK_POINTS] += weekPoints
		gwData.statTbl[StatType.COST] = weekCost
		gwData.statTbl[StatType.MINUTES_PLAYED] += minutesPlayed


# Data for one week for a Premier League Team
class TeamGameWeekData:
	def __init__(self, weekIdx):
		self.weekIdx = weekIdx
		self.statTbl = dict()
		self.statTbl[StatType.GOALS_FOR] = 0 # number of goals scored by this team up to and including this gameWeek
		self.statTbl[StatType.GOALS_AGAINST] = 0 # number of goals scored against this team up to and including this gameWeek
		# The below lists are usually just one element, but may be two in the case of a double game week
		self.opponentTeamIds = []
		self.isHome = [] 


# Data for an actual Premier League team.
class TeamData:
	def __init__(self, teamName, teamId):
		self.name = teamName
		self.id = teamId
		self.statTbl = dict()
		self.statTbl[StatType.GOALS_FOR] = 0 # total number of goals scored by this team
		self.statTbl[StatType.GOALS_AGAINST] = 0 # total number of goals scored against this team
		self.gameWeekTbl = dict() # map from week idx to TeamGameWeekData
	def updateGameWeekTbl(self, weekIdx, weekGoalsFor, weekGoalsAgainst, opponentTeamId, isHomeGame):
		assert weekIdx in [len(self.gameWeekTbl), len(self.gameWeekTbl) + 1]
		self.statTbl[StatType.GOALS_FOR] += weekGoalsFor
		self.statTbl[StatType.GOALS_AGAINST] += weekGoalsAgainst
		data = self.gameWeekTbl.setdefault(weekIdx, TeamGameWeekData(weekIdx))
		data.statTbl[StatType.GOALS_FOR] = self.statTbl[StatType.GOALS_FOR]
		data.statTbl[StatType.GOALS_AGAINST] = self.statTbl[StatType.GOALS_AGAINST]
		data.opponentTeamIds.append(opponentTeamId)
		data.opponentTeamIds.append(isHomeGame)


# Data for a squad, which corresponds to a Fantasy team but not a real club.
class SquadData:
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
		self.teamIdTbl = dict() # map from team ID number to TeamData
		self.playerNameTbl = dict() # map from player name to PlayerData
		self.playerPositionTbl = list() # map from position idx to list of all PlayerData for that position
		self.positionIdTbl = { 1 : "GK", 2 : "DEF", 3 : "MID", 4 : "FWD" }
		self.playersToExclude = {}
		self.teamsToExclude = {}
		self.budget = 1000 # in hundreds of thousands of Euros
		self.maxNumPlayersPerTeam = 3
		self.numWeeksForForm = 3 # number of weeks before current week to calculate form
		# number of players per position in a Fantasy team, including subs
		# order is GoalKeeper, Defender, Midfielder, Forward, Manager
		self.positionCountTbl = [ 2, 5, 5, 3, 0 ]
		self.minPositionCountTbl = [ 1, 3, 1, 1, 0 ] # minimum number of players required per position in a game week
		self.maxConsecutiveBadSearches = 100000000
		self.seasonStr = ''
		self.numPositions = len(self.positionIdTbl)
 		# number of weeks before the present to include when gathering data for
		# analysis. If -1 is specified, or if the number is larger than the total
		# number of weeks in the database, all week data will be used.
		self.numPrevWeeksForData = -1
		self.lastCompletedGameWeek = -1
		# stats to use when finding each best gameweek squad (after finding best squad in general)
		self.statTypeForSquad = StatType.FORM
		self.statTypeForCaptain = StatType.FORM

	def readConfigFile(self, fn):
		def getStatFromConfigStr(string):
			if string == "form":
				return StatType.FORM
			if string == "total_points":
				return StatType.TOTAL_POINTS
			assert 0, f"Unknown strategy type from config file: {string}"

		with open(fn, 'r') as fIn:
			configData = json.load(fIn)
			for key, val in configData.items():
				if key == 'excluded_players':
					self.playersToExclude = set(val)
				elif key == 'excluded_teams':
					self.teamsToExclude = set(val)
				elif key == 'budget':
					self.budget = val
				elif key == 'season':
					self.season = val
				elif key == 'num_prev_weeks_for_data':
					self.numPrevWeeksForData = val
				elif key == 'gameweek_squad_strategy':
					self.statTypeForSquad = getStatFromConfigStr(val)
				elif key == 'gameweek_captain_strategy':
					self.statTypeForCaptain = getStatFromConfigStr(val)
				else:
					assert 0, f"Unknown key from config file: {key}"
			print("Config File:\nKey\tVal")
			for key, val in configData.items():
				print(f"{key}\t{val}")
			print()

	def _getLinearRegObservations(self, numFeatureWeeks, numTargetWeeks):
		X = []
		y = []
		for playerName, playerData in self.playerNameTbl.items():
			if playerData.positionId != 1:
				continue
			gameWeekList = [v for v in sorted(playerData.gameWeekTbl.values(), key=lambda x: x.weekIdx)]
			for i in range(len(gameWeekList) - (numTargetWeeks + numFeatureWeeks) + 1):
				featureSum = 0
				dataMissing = False
				pointsList = []
				for j in range(i, i + numFeatureWeeks):	
					dataMissing = dataMissing or (gameWeekList[j].statTbl[StatType.MINUTES_PLAYED] == 0)
					featureSum += gameWeekList[j].statTbl[StatType.WEEK_POINTS]
					pointsList.append(gameWeekList[j].statTbl[StatType.WEEK_POINTS])
				targetSum = 0
				for j in range(i + numFeatureWeeks, i + numFeatureWeeks + numTargetWeeks):	
					dataMissing = dataMissing or (gameWeekList[j].statTbl[StatType.MINUTES_PLAYED] == 0)
					targetSum += gameWeekList[j].statTbl[StatType.WEEK_POINTS]
				if not dataMissing:
					teamData = self.teamIdTbl[playerData.teamId]
					if i + numFeatureWeeks - 1 == 0:
						teamGoalsFor = 0
						teamGoalsAgainst = 0
						opponentTeamGoalsFor = 0
						opponentTeamGoalsAgainst = 0
					else:
						gameWeekTeamData = teamData.gameWeekTbl[i + numFeatureWeeks - 1]
						teamGoalsFor = gameWeekTeamData.statTbl[StatType.GOALS_FOR]
						teamGoalsAgainst = gameWeekTeamData.statTbl[StatType.GOALS_AGAINST]
						opponentTeamData = self.teamIdTbl[gameWeekTeamData.opponentTeamIds[0]]
						opponentGameWeekTeamData = opponentTeamData.gameWeekTbl[i + numFeatureWeeks - 1]
						opponentTeamGoalsFor = opponentGameWeekTeamData.statTbl[StatType.GOALS_FOR]
						opponentTeamGoalsAgainst = opponentGameWeekTeamData.statTbl[StatType.GOALS_AGAINST]
					X.append([float(featureSum) / numFeatureWeeks, teamGoalsFor, teamGoalsAgainst, opponentTeamGoalsFor, opponentTeamGoalsAgainst])
					y.append(float(targetSum) / numTargetWeeks)
		return (X, y)

	# fit linear model to target values
	def _runLinearRegression(self):
		# choose target value
		# choose feature set
		# collect data for observations and target values
		numTargetWeeks = 1
		for a in range(1, self.lastCompletedGameWeek - numTargetWeeks):
			(X, y) = self._getLinearRegObservations(a, numTargetWeeks)
			# run linear regression
			reg = linear_model.LinearRegression(fit_intercept=True)
			reg.fit(X, y)
			rSquared = reg.score(X, y)
			print(f"{a}: {rSquared}  {len(y)}")
			#if a == 15:
			#	x = [i[0] for i in X]
			#	plt.scatter(x, y)
			#	plt.show()
			

	def _readTeamDataFromJSON(self, data):
		for teamData in data['teams']:
			teamName = teamData['name']
			teamId = teamData['id']
			self.teamIdTbl[teamId] = TeamData(teamName, teamId)
	
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

	def _readGameWeekDataFromJSON(self, topLevelData, allGameWeekPlayerData, allGameWeekFixtureData):
		# make map from player ID to JSON top-level player data
		playerIdToDataTbl = {}
		for playerData in topLevelData['elements']:
			playerIdToDataTbl[playerData['id']] = playerData

		# read player data
		for event in topLevelData['events']:
			gameWeekId = event['id'] # this should be the same as the game week number
			gameWeekPlayerData = allGameWeekPlayerData[str(gameWeekId)]
			gameWeekFixtureData = allGameWeekFixtureData[str(gameWeekId)]
			for gwPlayerData in gameWeekPlayerData['elements']:
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
					print("WARNING: no top-level data for %s (data found in week id %d)" % (playerName, gameWeekId))
					continue
				nowCost = playerData.nowCost # FIXME: replace with actual cost this week
				playerData.updateGameWeekTbl(gameWeekId, totalPoints, nowCost, minutesPlayed)

			# read fixture data
			for fixtureData in gameWeekFixtureData: 
				if not fixtureData["finished"]:
					break
				homeTeamId = fixtureData["team_h"]
				awayTeamId = fixtureData["team_a"]
				homeTeamScore = fixtureData["team_h_score"]
				awayTeamScore = fixtureData["team_a_score"]
				homeTeamData = self.teamIdTbl[homeTeamId]
				awayTeamData = self.teamIdTbl[awayTeamId]
				homeTeamData.updateGameWeekTbl(gameWeekId, homeTeamScore, awayTeamScore, awayTeamId, True)
				awayTeamData.updateGameWeekTbl(gameWeekId, awayTeamScore, homeTeamScore, homeTeamId, False)

	def _getMedian(self, numList):
		sortedList = sorted(numList)
		midIdx = len(sortedList) // 2
		if len(sortedList) % 2 == 0:
			return (sortedList[midIdx] + sortedList[midIdx - 1]) / 2
		# else, odd
		return sortedList[midIdx]

	def _getStartWeek(self):
		if self.numPrevWeeksForData == -1 or self.numPrevWeeksForData > self.lastCompletedGameWeek:
			return 1
		else:
			return self.lastCompletedGameWeek - self.numPrevWeeksForData + 1
	
	def _examineGameWeekData(self):
		for name,playerData in self.playerNameTbl.items():
			pointsSum = 0
			formSum = 0
			pointsList = list() # list of points for all weeks up to current week
			startWeek = self._getStartWeek()
			for weekIdx in range(startWeek, self.lastCompletedGameWeek + 1):
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
					print("WARNING: Player %s (id: %d, Team: %s) total points mismatch: %d (reported total) vs. %d (summed total)" % (name, playerData.playerId, self.teamIdTbl[playerData.teamId].name, playerData.totalPoints, pointsSum))
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
	
	def _getBestSquadByStat(self, statTypeForSquad, statTypeForCaptain, weekIdx, squadData, weekSquad, weekSubs, weekCaptain):
		numGameWeeks = self.lastCompletedGameWeek
		assert numGameWeeks >= weekIdx, "Error: asked for data for week idx: %d, but we only have data for %d weeks!" % (weekIdx, numGameWeeks)
		# get list of players fir each position, sorted by decreasing statVal for this week
		# each element is (statVal, playerData)
		keeperList = list()
		defenderList = list()
		midfieldList = list()
		forwardList = list()
		self._getStatSortedPlayerListForWeek(statTypeForSquad, weekIdx, squadData.positionTbl[0], keeperList)
		self._getStatSortedPlayerListForWeek(statTypeForSquad, weekIdx, squadData.positionTbl[1], defenderList)
		self._getStatSortedPlayerListForWeek(statTypeForSquad, weekIdx, squadData.positionTbl[2], midfieldList)
		self._getStatSortedPlayerListForWeek(statTypeForSquad, weekIdx, squadData.positionTbl[3], forwardList)
		# formation rules: must have 1 goalie, at least: 3 defenders, 1 mid, 1 forward
		# choose highest statVal goalie for week 1
		minNumDefenders = min(len(defenderList), self.minPositionCountTbl[1])
		if len(keeperList) != 0:
			weekSquad.append(keeperList[0][1])
		for i in range(minNumDefenders):
			weekSquad.append(defenderList[i][1])
		if len(midfieldList) != 0:
			weekSquad.append(midfieldList[0][1])
		if len(forwardList) != 0:
			weekSquad.append(forwardList[0][1])
		# now we need 5 more players, which could be defenders, mid, or forwards.
		# Choose the best out of the remaining options.
		remainingPlayerList = defenderList[minNumDefenders:] + midfieldList[1:] + forwardList[1:]
		remainingPlayerList.sort(key=lambda x: x[0], reverse=True)
		for i in range(min(len(remainingPlayerList), 5)):
			weekSquad.append(remainingPlayerList[i][1])
		# add the remaining players as subs
		for i in remainingPlayerList[5:]:
			weekSubs.append(i[1])
		if len(keeperList) > 1:
			weekSubs.append(keeperList[1][1])
		# now choose the captain based on the chosen stat type
		captainSortedWeekSquad = list()
		self._getStatSortedPlayerListForWeek(statTypeForCaptain, weekIdx, weekSquad, captainSortedWeekSquad)
		return (captainSortedWeekSquad[0][1], captainSortedWeekSquad[1][1])

	def _getSquadPointsForGameWeek(self, weekIdx, weekSquad, weekSubs, weekCaptain, weekViceCaptain):
		finalWeekSquad = list() # final list of players selected after any substitutions
		result = 0
		posCountTbl = [0, 0, 0, 0] # number of players who did play, per position
		for playerData in weekSquad:
			if weekIdx in playerData.gameWeekTbl and playerData.gameWeekTbl[weekIdx].statTbl[StatType.MINUTES_PLAYED] != 0:
				result += playerData.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
				posCountTbl[playerData.positionId-1] += 1
				finalWeekSquad.append(playerData)

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
							finalWeekSquad.append(weekSubs[j])

		# next, try to add subs in order of priority
		for j in range(len(weekSubs)):
			if len(finalWeekSquad) == 11:
				break
			if j not in usedSubIdxs:
				if weekSubs[j].positionId == 1:
					continue # don't add extra keeper
				if weekIdx in weekSubs[j].gameWeekTbl:
					result += weekSubs[j].gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
					usedSubIdxs.add(j)
					posCountTbl[weekSubs[j].positionId-1] += 1
					finalWeekSquad.append(weekSubs[j])
		# replace week squad with final week squad
		weekSquad[:] = finalWeekSquad.copy()
		
		# add the captain's week points to double-count them. If captain did not play,
		# add vice captain's points instead
		if weekIdx not in weekCaptain.gameWeekTbl or weekCaptain.gameWeekTbl[weekIdx].statTbl[StatType.MINUTES_PLAYED] == 0:
			if weekIdx in weekViceCaptain.gameWeekTbl:
				result += weekViceCaptain.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
		elif weekIdx in weekCaptain.gameWeekTbl:
			result += weekCaptain.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
		return result
	
	def _writeSquadWeekPerformanceToFile(self, weekIdx, totalPoints, weekPoints, weekSquad, weekSubs, weekCaptain, weekViceCaptain, fOut):
		fOut.write("Week: %d\n" % (weekIdx))
		fOut.write("Squad Points This Week: %d\n" % weekPoints)
		fOut.write("Total Squad Points After This Week: %d\n" % totalPoints)
		fOut.write("Captain: %s\n" % weekCaptain.name)
		fOut.write("Vice Captain: %s\n" % weekViceCaptain.name)
		fOut.write("Player\tWeekPoints\tMinutesPlayed\n")
		for playerData in weekSquad:
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
	
	# Determine the total number of points the squad has acheived if the strategy
	# chosen was to pick the players each week to maximize the desired statistic
	# based on the players' performance prior to each week. For example, if
	# StatType.TOTAL_POINTS is chosen for statTypeForSquad, the starting lineup 
	# each week will be chosen based on which players had the most total points before that week.
	# A separate strategy may be chosen for choosing the captain each week.
	# NOTE: The first week's players are chose by maximizing the cost of the squad.
	def _evaluateStrategy(self, statTypeForSquad, statTypeForCaptain, squadData):
		if DebugFn != None:
			fOut = open(DebugFn,'w')
		totalPoints = 0
		weekSquad = list() # subset of players for current week
		weekSubs = list() # substitutes, ordered by decreasing stat of choice
		weekCaptain = None
		weekViceCaptain = None
		(weekCaptain, weekViceCaptain) = self._getBestSquadByStat(StatType.COST, StatType.COST, 1, squadData, weekSquad, weekSubs, weekCaptain)
		# for each week, find number of points for all players in that week's squad
		startWeek = self._getStartWeek()
		for weekIdx in range(startWeek, self.lastCompletedGameWeek + 1):
			weekPoints = self._getSquadPointsForGameWeek(weekIdx, weekSquad, weekSubs, weekCaptain, weekViceCaptain)
			totalPoints += weekPoints
			# choose squad for next week
			if DebugFn != None:
				self._writeSquadWeekPerformanceToFile(weekIdx, totalPoints, weekPoints, weekSquad, weekSubs, weekCaptain, weekViceCaptain, fOut)
			weekSquad = list()
			weekSubs = list()
			(weekCaptain, weekViceCaptain) = self._getBestSquadByStat(statTypeForSquad, statTypeForCaptain, weekIdx, squadData, weekSquad, weekSubs, weekCaptain)
	
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
			if self.teamIdTbl[playerData.teamId].name in self.teamsToExclude:
				continue
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
				# If the number of better players is at least the number of required players of that position on the squad,
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
	
	# Returns True if no combination of players can be added to the current squad to
	# beat the best squad.
	def _cannotBeatBestSquad(self, bestSquadData, curSquadData, curIdxList):
		curToBestPointsDiff = bestSquadData.totalPoints - curSquadData.totalPoints
		testPointSum = 0
		for posIdx in range(len(curSquadData.positionTbl)):
			numRemainingForPosition = self.positionCountTbl[posIdx] - len(curSquadData.positionTbl[posIdx])
			if numRemainingForPosition > 0:
				idx = curIdxList[posIdx]
				for i in range(idx, idx+numRemainingForPosition):
					testPointSum += self.playerPositionTbl[posIdx][i].totalPoints
		return (testPointSum <= curToBestPointsDiff)
	
	def _writeBestSquadToFile(self, bestSquadData, outFn):
		# write outfile
		totalPoints = 0
		with open(outFn,'w') as fOut:
			for posIdx in range(len(bestSquadData.positionTbl)):
				fOut.write("%s\n" % self.positionIdTbl[posIdx+1])
				fOut.write("Name\tClub\tCost\tTotal Points\n")
				for playerData in bestSquadData.positionTbl[posIdx]:
					totalPoints += playerData.totalPoints
					clubName = self.teamIdTbl[playerData.teamId].name
					fOut.write("%s\t%s\t%.1f\t%d\n" % (playerData.name, clubName, playerData.nowCost/10.0, playerData.totalPoints))
				fOut.write("\n")
		assert totalPoints == bestSquadData.totalPoints
		totalStrategyPoints = self._evaluateStrategy(self.statTypeForSquad, self.statTypeForCaptain, bestSquadData)
		print("%d %d %d" % (totalPoints, bestSquadData.totalCost, totalStrategyPoints))
	
	def _dfsFindBestSquad(self, teamCountTbl, curIdxList, bestSquadData, curSquadData, numConsecutiveBadSearches, outFn=None):
		# assemble every possible squad
		#print("%d %d %d %d" % (curIdxList[0], curIdxList[1], curIdxList[2], curIdxList[3]))
		# end search if no combination of players can be added to current squad to beat the best squad
		if self._cannotBeatBestSquad(bestSquadData, curSquadData, curIdxList):
			return
		for posIdx in range(len(curSquadData.positionTbl)):
			curPlayerList = curSquadData.positionTbl[posIdx]
			numRemainingForPosition = self.positionCountTbl[posIdx] - len(curPlayerList)
			if numRemainingForPosition > 0:
				allPlayerList = self.playerPositionTbl[posIdx]
				endIdx = len(allPlayerList)-numRemainingForPosition+1
				if endIdx <= 0:
					endIdx = len(allPlayerList)
				for i in range(curIdxList[posIdx], endIdx):
					#if numConsecutiveBadSearches[0] >= self.maxConsecutiveBadSearches:
					#	return
					if curSquadData.totalCost + allPlayerList[i].nowCost > self.budget:
						continue # we cannot complete the squad, so end this search branch
					# check if we have reached the limit of players for the current player's club
					if teamCountTbl[allPlayerList[i].teamId] == self.maxNumPlayersPerTeam:
						continue
					teamCountTbl[allPlayerList[i].teamId] += 1
					curPlayerList.append(allPlayerList[i])
					curSquadData.totalPoints += allPlayerList[i].totalPoints
					curSquadData.totalCost += allPlayerList[i].nowCost
					newIdxList = curIdxList.copy()
					newIdxList[posIdx] = i+1
					# find all squads that include the current list of players
					self._dfsFindBestSquad(teamCountTbl, newIdxList, bestSquadData, curSquadData, numConsecutiveBadSearches, outFn)
					# remove current player before examining next player
					curPlayerList.pop()
					curSquadData.totalPoints -= allPlayerList[i].totalPoints
					curSquadData.totalCost -= allPlayerList[i].nowCost
					teamCountTbl[allPlayerList[i].teamId] -= 1
				break # we have already examined all squads with the current set of players, so we can end our search
		# here we have a complete squad to compare against the best squad yet found
		if bestSquadData.totalPoints < curSquadData.totalPoints:
			# update best squad data
			curSquadData.copyTo(bestSquadData)
			if outFn != None:
				self._writeBestSquadToFile(bestSquadData, outFn)
			numConsecutiveBadSearches[0] += 0
		else:
			numConsecutiveBadSearches[0] += 1

	def _readInCustomSquadJSON(self, squadFn, playerList, curSquadData):
		playerList.clear()
		squadValue = 0
		with open(squadFn, 'r') as f:
			squadData = json.load(f)
			for key, val in squadData.items():
				key = key.lower()
				if key in { "keepers", "defenders", "midfielders", "forwards" }:
					assert isinstance(val, list), "In input squad file, keepers value must be a list!"
					for playerName in val:
						playerData = self.playerNameTbl.get(playerName)
						assert playerData != None, f"Error: no player named {playerName}. Make sure full name is spelled correctly as it appears in the database!"
						playerList.append(playerData)
						playerPos = playerData.positionId
						curSquadData.positionTbl[playerPos-1].append(playerData)
						squadValue += playerData.nowCost
				elif key == "bank":
					assert isinstance(val, (int, float)), "In input squad file, bank value must be a number"
					bank = val
				else:		
					assert 0, f"Unknown key in input squad file: {key}"
		assert bank is not None, "Must specify amount in bank for input squad!"
		# calculate budget by adding squad value to bank value
		self.budget = squadValue + int(float(bank) * 10) # convert to 100,000s of euros
		# make sure we have the desired distribution of positions
		for posIdx in range(len(curSquadData.positionTbl)):
			if len(curSquadData.positionTbl[posIdx]) != self.positionCountTbl[posIdx]:
				positionStr = self.positionIdTbl[posIdx+1]
				assert 0, f"Error: incorrect number of {positionStr}: {len(curSquadData.positionTbl[posIdx])}. Should be {self.positionCountTbl[posIdx]}"
		print(f"Budget: {squadValue / 10.0}")
					
	def _getLastCompletedGameWeek(self, topLevelData):
		# find first week whose data is not finished
		for idx in range(len(topLevelData['events'])):
			if not topLevelData['events'][idx]['finished']:
				return topLevelData['events'][idx]['id'] - 1 # return week id - 1, which should be same as week idx of last completed gameweek

	def readDataFromJSON(self, topLevelJsonFn, gameWeekPlayerJsonFn, gameWeekFixtureJsonFn):
		fTop = open(topLevelJsonFn, 'r')
		topLevelData = json.load(fTop)
		self.lastCompletedGameWeek = self._getLastCompletedGameWeek(topLevelData)
		self._readTeamDataFromJSON(topLevelData)
		self._readPlayerDataFromJSON(topLevelData) # read cumulative data for each player
		fpgw = open(gameWeekPlayerJsonFn, 'r')
		gameweekPlayerData = json.load(fpgw)
		ffgw = open(gameWeekFixtureJsonFn, 'r')
		gameWeekFixtureData = json.load(ffgw)
		self._readGameWeekDataFromJSON(topLevelData, gameweekPlayerData, gameWeekFixtureData)
		self._examineGameWeekData()
		self._createPlayerPositionTbl()
		fTop.close()
		fpgw.close()
		ffgw.close()

	def findBestSquad(self, outFn):
		bestSquadData = SquadData(self.numPositions)
		curSquadData = SquadData(self.numPositions)
		teamCountTbl = [0]*(len(self.teamIdTbl)+1) # map from team id to count of players for that team
		positionIdxList = [0, 0, 0, 0] # each element is the current idx within the full player list of the position given by that element
		numConsecutiveBadSearches = [0]
		self._dfsFindBestSquad(teamCountTbl, positionIdxList, bestSquadData, curSquadData, numConsecutiveBadSearches, outFn)

	def _findCustomSquadMetadata(self, curSquadData):
		for posIdx in range(len(curSquadData.positionTbl)):
			playerList = curSquadData.positionTbl[posIdx]
			for playerData in playerList:
				curSquadData.totalPoints += playerData.totalPoints
				curSquadData.totalCost += playerData.nowCost

	def _searchForBetterPlayer(self, posIdx, playerListIdx, playerList, origSquadData, transferOptions):
		bestSquadData = SquadData(self.numPositions)
		# create squad data without the given player
		curSquadData = SquadData(self.numPositions)
		origSquadData.copyTo(bestSquadData)
		origSquadData.copyTo(curSquadData)
		playerToTransfer = curSquadData.positionTbl[posIdx].pop(playerListIdx)
		curSquadData.totalCost -= playerToTransfer.nowCost
		curSquadData.totalPoints -= playerToTransfer.totalPoints
		
		teamCountTbl = [0]*(len(self.teamIdTbl)+1) # map from team id to count of players for that team
		for playerData in playerList:
			if playerData.name != playerToTransfer.name:
				teamCountTbl[playerData.teamId] += 1

		positionIdxList = [0, 0, 0, 0] # each element is the current idx within the full player list of the position given by that element
		numConsecutiveBadSearches = [0]
		self._dfsFindBestSquad(teamCountTbl, positionIdxList, bestSquadData, curSquadData, numConsecutiveBadSearches)
		# if best squad total points did not improve over original, skip
		pointsImprovement = bestSquadData.totalPoints - origSquadData.totalPoints
		if pointsImprovement <= 0:
			return
		# check if there is a new player for the position
		origPosPlayerNames = set()
		for playerData in origSquadData.positionTbl[posIdx]:
			origPosPlayerNames.add(playerData.name)
		for playerData in bestSquadData.positionTbl[posIdx]:
			if playerData.name not in origPosPlayerNames:
				transferOptions.append((playerToTransfer, playerData, pointsImprovement))
				break

	def findBestTransferOptions(self, squadFn, outFn):
		curSquadData = SquadData(self.numPositions)
		playerList = list()
		# initialize budget to 0. Will be set to total cost of players + remaining in bank
		self.budget = 0
		# read squad data from file
		self._readInCustomSquadJSON(squadFn, playerList, curSquadData)
		# find metadata of squad
		self._findCustomSquadMetadata(curSquadData)
		print("Budget: %.1fm euros" % (self.budget/10.0))
		transferOptions = list() # list of (origPlayer, newPlayer, pointsImprovement)
		# add all players from current squad to exclusion list
		origExclusionList = self.playersToExclude.copy()
		self.playersToExclude.update(playerList)
		# for each player, search for a player that would improve the squad
		for posIdx in range(len(curSquadData.positionTbl)):
			for playerListIdx in range(len(curSquadData.positionTbl[posIdx])):
				self._searchForBetterPlayer(posIdx, playerListIdx, playerList, curSquadData, transferOptions)
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
