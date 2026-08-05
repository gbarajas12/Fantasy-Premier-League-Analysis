import sys
import os
from enum import Enum
import json
import random
from sklearn import linear_model
import matplotlib.pyplot as plt

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
	def __init__(self, firstName, lastName, playerId, totalPoints, nowCost, teamId, positionId, pointsPerMatch=0.0):
		self.name = '%s %s' % (firstName, lastName)
		self.firstName = firstName
		self.lastName = lastName
		self.playerId = playerId
		self.totalPoints = totalPoints
		self.nowCost = nowCost
		self.teamId = teamId
		self.positionId = positionId
		self.pointsPerMatch = pointsPerMatch
		self.gameWeekTbl = dict() # map from game week idx to PlayerGameWeekData
	def copyTo(self, other):
		other = PlayerData(self.firstName, self.lastName, self.playerId, self.totalPoints, self.nowCost, self.teamId, self.positionId, self.pointsPerMatch)
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
		#assert weekIdx in [len(self.gameWeekTbl), len(self.gameWeekTbl) + 1]
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
		self.totalPoints = 0 # always real total points, regardless of squadOptimizationStat
		self.objectiveValue = 0 # sum of whatever squadOptimizationStat is being optimized (see Analyzer._getSquadObjectiveValue)
		for i in range(numPositions):
			self.positionTbl.append(list())
	def copyTo(self, other):
		other.positionTbl = list()
		for playerList in self.positionTbl:
			other.positionTbl.append(playerList.copy())
		other.totalCost = self.totalCost
		other.totalPoints = self.totalPoints
		other.objectiveValue = self.objectiveValue

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
		self.positionCountTbl = [ 2, 5, 5, 3 ]
		self.minPositionCountTbl = [ 1, 3, 1, 1 ] # minimum number of players required per position in a game week
		self.maxPositionCountTbl = [ 1, 5, 5, 3 ] # maximum number of players per position in a game week
		self.startingSquadSize = 11 # size of squad on pitch
		self.fullSquadSize = sum(self.positionCountTbl)
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
		# which PlayerData stat findBestSquad's DFS optimizes for: 'total_points' or 'points_per_match'
		self.squadOptimizationStat = 'total_points'
		# squad input by user
		self.inputSquadData = None
		self.inputSquadPlayers = None  # set of all player IDs in input squad
		self.maxNumTransfers = None # max set of transfers allowed from input squad
		self.weeklyOutFn = None  # output file to write week-by-week data
		# players findBestSquad's DFS must include in the final squad
		self.requiredPlayers = set() # player names, from config file
		self.requiredPlayerData = list() # resolved PlayerData, populated by _resolveRequiredPlayers
		# santiy checks
		assert len(self.minPositionCountTbl) == len(self.maxPositionCountTbl) == len(self.positionCountTbl), "Internal error: position count mismatch"
		for minCount, maxCount in zip(self.minPositionCountTbl, self.maxPositionCountTbl):
			assert minCount <= maxCount, "Internal error: position min count > position max count"

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
				elif key == 'required_players':
					self.requiredPlayers = set(val)
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
				elif key == 'weekly_out_data_fn':
					self.weeklyOutFn = val
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
			pointsPerMatch = float(playerData['points_per_game'])
			self.playerNameTbl['%s %s' % (firstName, lastName)] = PlayerData(firstName, lastName, playerId, totalPoints, nowCost, teamId, positionId, pointsPerMatch)

	# Looks up a player's cost for a specific gameweek from costHistoryData (as
	# loaded from a fpl_gameweek_cost_data.json produced by grab_fpl_data.py).
	# Falls back to fallbackCost (the player's current price) whenever the data
	# isn't available - no cost-history file was given at all (the only option
	# for a season that has already finished, since the FPL API stops exposing
	# per-gameweek price history once a season rolls over), or this specific
	# player/week is missing from it (e.g. a player who joined mid-season).
	def _getHistoricalCost(self, costHistoryData, playerId, gameWeekId, fallbackCost):
		if costHistoryData is None:
			return fallbackCost
		playerCostHistory = costHistoryData.get(str(playerId))
		if playerCostHistory is None:
			return fallbackCost
		return playerCostHistory.get(str(gameWeekId), fallbackCost)

	def _readGameWeekDataFromJSON(self, topLevelData, allGameWeekPlayerData, allGameWeekFixtureData, costHistoryData=None):
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
				weekCost = self._getHistoricalCost(costHistoryData, playerId, gameWeekId, playerData.nowCost)
				playerData.updateGameWeekTbl(gameWeekId, totalPoints, weekCost, minutesPlayed)

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
	
	# (Re)computes StatType.FORM for every player/week using a trailing window of
	# numWeeksForForm weeks (defaults to self.numWeeksForForm). Extracted out of
	# _examineGameWeekData so it can be re-run with a different window (e.g. a
	# "last N weeks" squad-selection strategy) without re-deriving
	# TOTAL_POINTS/MEDIAN_POINTS. A uniform divisor never changes relative order,
	# so "highest points over the last N weeks" is exactly "highest FORM with
	# window=N" - no new StatType needed.
	def _computeFormStat(self, numWeeksForForm=None):
		windowSize = numWeeksForForm if numWeeksForForm is not None else self.numWeeksForForm
		startWeek = self._getStartWeek()
		for name,playerData in self.playerNameTbl.items():
			formSum = 0
			for weekIdx in range(startWeek, self.lastCompletedGameWeek + 1):
				gwData = playerData.gameWeekTbl.get(weekIdx)
				if gwData == None:
					continue
				if weekIdx >= windowSize:
					prevWeekIdx = weekIdx - windowSize
					prevWeekData = playerData.gameWeekTbl.get(prevWeekIdx)
					if prevWeekData != None:
						formSum -= prevWeekData.statTbl[StatType.WEEK_POINTS]
				formSum += gwData.statTbl[StatType.WEEK_POINTS]
				gwData.statTbl[StatType.FORM] = formSum / windowSize

	def _examineGameWeekData(self):
		for name,playerData in self.playerNameTbl.items():
			pointsSum = 0
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
				gwData.statTbl[StatType.MEDIAN_POINTS] = self._getMedian(pointsList)
			if self.numPrevWeeksForData == -1:
				if pointsSum != playerData.totalPoints:
					print("WARNING: Player %s (id: %d, Team: %s) total points mismatch: %d (reported total) vs. %d (summed total)" % (name, playerData.playerId, self.teamIdTbl[playerData.teamId].name, playerData.totalPoints, pointsSum))
			else:
				playerData.totalPoints = pointsSum
		self._computeFormStat()
	
	def _getStatSortedPlayerListForWeek(self, statType, weekIdx, playerList, result):
		tempList = list() # list of (weekStat, playerData) for each player of the position in the given week
		for playerData in playerList:
			if weekIdx in playerData.gameWeekTbl:
				statVal = playerData.gameWeekTbl[weekIdx].statTbl[statType]
			else:
				# search forward from weekIdx to find stat value
				newWeekIdx = -1
				for i in range(weekIdx + 1, self.lastCompletedGameWeek + 1):
					if i in playerData.gameWeekTbl:
						newWeekIdx = i
						break
				if newWeekIdx == -1:
					# search backward from weekIdx to find stat value
					for i in range(weekIdx - 1, -1, -1):
						if i in playerData.gameWeekTbl:
							newWeekIdx = i
							break
				assert newWeekIdx != -1
				statVal = playerData.gameWeekTbl[newWeekIdx].statTbl[statType]
			tempList.append((statVal, playerData))
		tempList.sort(key=lambda x: x[0], reverse=True) # sort entries by player week statVal
		result[:] = tempList.copy()
	
	def _getBestSquadByStat(self, statTypeForSquad, statTypeForCaptain, weekIdx, squadData, weekSquad, weekSubs, weekCaptain):
		numGameWeeks = self.lastCompletedGameWeek
		assert numGameWeeks >= weekIdx, "Error: asked for data for week idx: %d, but we only have data for %d weeks!" % (weekIdx, numGameWeeks)
		# get list of players for each position, sorted by decreasing statVal for this week
		# each element is (statVal, playerData)
		weekSquadData = [list() for i in range(len(self.positionCountTbl))]
		for i in range(len(weekSquadData)):
			self._getStatSortedPlayerListForWeek(statTypeForSquad, weekIdx, squadData.positionTbl[i], weekSquadData[i])

		# choose the minimum number of players per position based on FPL rules (stored in self.minPositionCountTbl).
		# choose the best players for each position to fill those spots.
		weekSquadCountTbl = [0 for i in range(len(self.positionCountTbl))]			
		for i, posList in enumerate(weekSquadData):
			for j in range(min(self.minPositionCountTbl[i], len(posList))):
				weekSquad.append(posList[j][1])
				weekSquadCountTbl[i] += 1
		# fill the rest of the squad by choosing the best out of the remaining options, which could be any available position.
		remainingPlayerList = []
		for i, posList in enumerate(weekSquadData):
			if weekSquadCountTbl[i] == self.maxPositionCountTbl[i]:
				continue
			remainingPlayerList += posList[weekSquadCountTbl[i]:]
	    
		# get best of remaining players by sorting them
		remainingPlayerList.sort(key=lambda x: x[0], reverse=True)
		numSpotsToFill = self.startingSquadSize - len(weekSquad)
		for i in range(numSpotsToFill):
			weekSquad.append(remainingPlayerList[i][1])
		# add the remaining players as subs
		for i in range(numSpotsToFill, len(remainingPlayerList)):
			weekSubs.append(remainingPlayerList[i][1])
		for i, posList in enumerate(weekSquadData):
			if weekSquadCountTbl[i] == self.maxPositionCountTbl[i]:
				for j in range(self.maxPositionCountTbl[i], len(posList)):
					weekSubs.append(posList[j][1])
		assert len(weekSquad) == self.startingSquadSize
		assert len(weekSubs) == self.fullSquadSize - self.startingSquadSize, f"Internal error: number of subs in gameweek {weekIdx}: {len(weekSubs)}"
		# now choose the captain based on the chosen stat type
		captainSortedWeekSquad = list()
		self._getStatSortedPlayerListForWeek(statTypeForCaptain, weekIdx, weekSquad, captainSortedWeekSquad)
		return (captainSortedWeekSquad[0][1], captainSortedWeekSquad[1][1])

	def _getSquadPointsForGameWeek(self, weekIdx, weekSquad, weekSubs, weekCaptain, weekViceCaptain):
		finalWeekSquad = list() # final list of players selected after any substitutions
		finalWeekSubs = list()
		result = 0
		posCountTbl = [0]*len(self.positionCountTbl) # number of players who did play, per position
		missingPositionTbl = [list() for i in range(len(self.positionCountTbl))] # players who did not play, per position
		usedPlayerIds = set()
		for playerData in weekSquad:
			if weekIdx in playerData.gameWeekTbl and playerData.gameWeekTbl[weekIdx].statTbl[StatType.MINUTES_PLAYED] != 0:
				result += playerData.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
				posCountTbl[playerData.positionId-1] += 1
				finalWeekSquad.append(playerData)
				usedPlayerIds.add(playerData.playerId)
			else:
				missingPositionTbl[playerData.positionId-1].append(playerData)

		# weekSubPosTbl = [[i for i in weekSubs if i.positionId - 1 == j] for j in range(len(self.positionCountTbl))]
		# add subs to fill missing position quotas
		for i in range(len(posCountTbl)):
			subIdx = 0
			while posCountTbl[i] < self.minPositionCountTbl[i]:
				if subIdx < len(weekSubs):
					# add from subs
					if weekSubs[subIdx].positionId - 1 == i:
						if weekIdx in weekSubs[subIdx].gameWeekTbl:
							result += weekSubs[subIdx].gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
						posCountTbl[i] += 1
						finalWeekSquad.append(weekSubs[subIdx])
						usedPlayerIds.add(weekSubs[subIdx].playerId)
					subIdx += 1
				else:
					# add from missing players
					assert len(missingPositionTbl[i]) >= self.minPositionCountTbl[i] - posCountTbl[i]
					for j in range(self.minPositionCountTbl[i] - posCountTbl[i]):
						posCountTbl[i] += 1
						finalWeekSquad.append(missingPositionTbl[i][j])
						usedPlayerIds.add(missingPositionTbl[i][j].playerId)
					break

		# next, try to fill squad with any position
		subIdx = 0
		while len(finalWeekSquad) < self.startingSquadSize:
			if subIdx < len(weekSubs):
				# use sub
				if weekSubs[subIdx].playerId not in usedPlayerIds:
					if weekIdx in weekSubs[subIdx].gameWeekTbl:
						result += weekSubs[subIdx].gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
					finalWeekSquad.append(weekSubs[subIdx])
					usedPlayerIds.add(weekSubs[subIdx].playerId)
				subIdx += 1
			else:
				break
		# fill squad with missing players
		for posList in missingPositionTbl:
			if len(finalWeekSquad) == self.startingSquadSize:
				break
			for playerData in posList:
				if len(finalWeekSquad) == self.startingSquadSize:
					break
				if playerData.playerId not in usedPlayerIds:
					finalWeekSquad.append(playerData)
					usedPlayerIds.add(playerData.playerId)

		# put any remaining players in finalWeekSubs
		for playerData in weekSubs:
			if playerData.playerId not in usedPlayerIds:
				finalWeekSubs.append(playerData)
				usedPlayerIds.add(playerData.playerId)
		for posList in missingPositionTbl:
			for playerData in posList:
				if playerData.playerId not in usedPlayerIds:
					finalWeekSubs.append(playerData)
					usedPlayerIds.add(playerData.playerId)
				
		# replace week squad with final week squad
		weekSquad[:] = finalWeekSquad.copy()
		weekSubs[:] = finalWeekSubs.copy()

		assert len(weekSquad) == self.startingSquadSize
		assert len(weekSubs) == self.fullSquadSize - self.startingSquadSize, f"Internal error: number of subs in gameweek {weekIdx}: {len(weekSubs)}"
		
		# add the captain's week points to double-count them. If captain did not play,
		# add vice captain's points instead
		if weekIdx in weekCaptain.gameWeekTbl and weekCaptain.gameWeekTbl[weekIdx].statTbl[StatType.MINUTES_PLAYED] != 0:
			result += weekCaptain.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
		elif weekIdx in weekViceCaptain.gameWeekTbl:
			result += weekViceCaptain.gameWeekTbl[weekIdx].statTbl[StatType.WEEK_POINTS]
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
	# transferPolicy, if given, is called once per week (except the final week)
	# with (self, squadData, weekIdx, weekSquad, weekSubs, rng) and must return a
	# list of (playerOut, playerIn) pairs, applied to squadData in place via
	# _applyTransfers before the next week's squad is chosen. Defaults to no-op,
	# so every existing caller's behavior is unchanged.
	def _evaluateStrategy(self, statTypeForSquad, statTypeForCaptain, squadData, transferPolicy=None, rng=None):
		if self.lastCompletedGameWeek < 1:
			return 0 # no completed gameweeks yet (e.g. season hasn't started) - nothing to simulate
		if self.weeklyOutFn != None:
			fOut = open(self.weeklyOutFn,'w')
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
			if self.weeklyOutFn is not None:
				self._writeSquadWeekPerformanceToFile(weekIdx, totalPoints, weekPoints, weekSquad, weekSubs, weekCaptain, weekViceCaptain, fOut)
			if transferPolicy is not None and weekIdx < self.lastCompletedGameWeek:
				transfers = transferPolicy.selectTransfers(self, squadData, weekIdx, weekSquad, weekSubs, rng)
				self._applyTransfers(squadData, transfers)
			weekSquad = list()
			weekSubs = list()
			(weekCaptain, weekViceCaptain) = self._getBestSquadByStat(statTypeForSquad, statTypeForCaptain, weekIdx, squadData, weekSquad, weekSubs, weekCaptain)

		if self.weeklyOutFn is not None:
			fOut.close()

		return totalPoints

	# Applies a list of (playerOut, playerIn) pairs to squadData in place.
	def _applyTransfers(self, squadData, transfers):
		for outPlayer, inPlayer in transfers:
			posIdx = outPlayer.positionId - 1
			squadData.positionTbl[posIdx].remove(outPlayer)
			squadData.positionTbl[posIdx].append(inPlayer)
			squadData.totalCost += inPlayer.nowCost - outPlayer.nowCost
			squadData.totalPoints += inPlayer.totalPoints - outPlayer.totalPoints

	# Thin wrapper around the forward/backward-search fallback logic already in
	# _getStatSortedPlayerListForWeek, for looking up a single player's stat value.
	def _getStatValueForWeek(self, playerData, statType, weekIdx):
		result = list()
		self._getStatSortedPlayerListForWeek(statType, weekIdx, [playerData], result)
		return result[0][0]

	# Cheap O(pool size for this position) scan for a same-position replacement
	# for outPlayerData: sorts candidatePosPool by statType for weekIdx, then
	# returns the first candidate that (a) isn't already in squadData, (b) keeps
	# the per-club cap satisfied after the swap, and (c) keeps totalCost within
	# self.budget. Returns None if no valid replacement exists this week.
	def _findReplacementPlayer(self, statType, weekIdx, candidatePosPool, squadData, outPlayerData):
		sortedCandidates = list()
		self._getStatSortedPlayerListForWeek(statType, weekIdx, candidatePosPool, sortedCandidates)
		existingIds = {playerData.playerId for posList in squadData.positionTbl for playerData in posList}
		teamCountTbl = dict()
		for posList in squadData.positionTbl:
			for playerData in posList:
				teamCountTbl[playerData.teamId] = teamCountTbl.get(playerData.teamId, 0) + 1
		for statVal, candidate in sortedCandidates:
			if candidate.playerId in existingIds:
				continue
			clubCountAfter = teamCountTbl.get(candidate.teamId, 0)
			if candidate.teamId == outPlayerData.teamId:
				clubCountAfter -= 1
			if clubCountAfter >= self.maxNumPlayersPerTeam:
				continue
			if squadData.totalCost - outPlayerData.nowCost + candidate.nowCost > self.budget:
				continue
			return candidate
		return None

	# The scalar findBestSquad's DFS optimizes/prunes/sorts on, per
	# self.squadOptimizationStat.
	def _getSquadObjectiveValue(self, playerData):
		if self.squadOptimizationStat == 'points_per_match':
			return playerData.pointsPerMatch
		return playerData.totalPoints

	# Resolves self.requiredPlayers (names, from config) into self.requiredPlayerData
	# (PlayerData objects), for findBestSquad's DFS to force-include (see
	# _seedMandatoryPlayers). Rebuilt fresh every call, so it's safe to call
	# findBestSquad more than once on the same Analyzer instance. Called before
	# _createPlayerPositionTbl, since excluded_players/excluded_teams filtering
	# there is unconditional - a contradictory config would otherwise silently
	# filter a required player out and crash confusingly later.
	def _resolveRequiredPlayers(self):
		self.requiredPlayerData = list()
		for name in self.requiredPlayers:
			playerData = self.playerNameTbl.get(name)
			assert playerData is not None, f"Error: no player named {name} in required_players. Make sure full name is spelled correctly as it appears in the database!"
			assert name not in self.playersToExclude, f"Error: {name} is in both required_players and excluded_players."
			assert self.teamIdTbl[playerData.teamId].name not in self.teamsToExclude, f"Error: {name}'s team is in excluded_teams, but {name} is also required."
			self.requiredPlayerData.append(playerData)

	# Returns a fresh list of per-position player lists passing the exclusion
	# filters (excluded_players/excluded_teams, must have scored this season
	# unless in curSquadPlayerIds). No dominance pruning, no sorting: reused
	# unpruned by the random squad generator, which doesn't need the search-space
	# reduction that _createPlayerPositionTbl's pruning below provides, and
	# shouldn't lose cheap differentials to it.
	def _buildFilteredPlayerPositionLists(self, curSquadPlayerIds):
		positionLists = [list() for i in range(len(self.positionIdTbl))]
		for name,playerData in self.playerNameTbl.items():
			# skip players with no points
			if playerData.totalPoints <= 0 and playerData.playerId not in curSquadPlayerIds:
				continue
			# NOTE: the following exclusion reasons supercede keeping players on the current squad
			if playerData.name in self.playersToExclude:
				continue
			if self.teamIdTbl[playerData.teamId].name in self.teamsToExclude:
				continue
			positionLists[playerData.positionId-1].append(playerData)
		return positionLists

	def _createPlayerPositionTbl(self):
		curSquadPlayerIds = set()
		if self.inputSquadData is not None:
			# must include these players in output table
			for posList in self.inputSquadData.positionTbl:
				for playerData in posList:
					curSquadPlayerIds.add(playerData.playerId)
		for playerData in self.requiredPlayerData:
			curSquadPlayerIds.add(playerData.playerId)
		self.playerPositionTbl = self._buildFilteredPlayerPositionLists(curSquadPlayerIds)
		# now prune each position's list of players by removing the worst players.
		# these are players with the lowest squadOptimizationStat value for their price
		for posIdx in range(len(self.playerPositionTbl)):
			# list of (playerCost, playerData), sorted by decreasing cost
			sortedCostList = sorted(self.playerPositionTbl[posIdx].copy(), key=lambda x: x.nowCost, reverse=True)
			# clear the currently stored list. It will be replaced later.
			self.playerPositionTbl[posIdx] = list()
			for i in range(len(sortedCostList)):
				playerData = sortedCostList[i]
				if playerData.playerId in curSquadPlayerIds:
					self.playerPositionTbl[posIdx].append(playerData)  # must add player if in current squad
					continue
				# ignore this player if there are enough other players with one of the following:
				# - lower cost, at least as good squadOptimizationStat value as current player
				# - equal cost, better squadOptimizationStat value than current player
				# If the number of better players is at least the number of required players of that position on the squad,
				# skip this player. (e.g. there are 2 required goalies and at least 2 goalies are better than the current one).
				betterPlayerCount = 0
				# only look at players that are not more expensive
				for otherPlayerData in sortedCostList[i+1:]:
					if otherPlayerData.nowCost < playerData.nowCost and self._getSquadObjectiveValue(otherPlayerData) >= self._getSquadObjectiveValue(playerData):
						betterPlayerCount += 1
					elif otherPlayerData.nowCost == playerData.nowCost and self._getSquadObjectiveValue(otherPlayerData) > self._getSquadObjectiveValue(playerData):
						betterPlayerCount += 1
					if betterPlayerCount == self.positionCountTbl[posIdx]:
						break
				if betterPlayerCount < self.positionCountTbl[posIdx]:
					self.playerPositionTbl[posIdx].append(playerData)
				#if betterPlayerCount == 0:
				#	self.playerPositionTbl[posIdx].append(playerData)
		# sort players by decreasing squadOptimizationStat value, and then by increasing nowCost
		for posIdx in range(len(self.playerPositionTbl)):
			self.playerPositionTbl[posIdx].sort(key = lambda x: x.nowCost)
			self.playerPositionTbl[posIdx].sort(key = lambda x: self._getSquadObjectiveValue(x), reverse=True)
		#print ("%d %d %d %d" % (len(self.playerPositionTbl[0]), len(self.playerPositionTbl[1]), len(self.playerPositionTbl[2]), len(self.playerPositionTbl[3])))

	# Candidate pool for random squad generation and for transfer-target search:
	# same exclusion filters as _createPlayerPositionTbl, without its
	# season-TOTAL_POINTS dominance pruning (see _buildFilteredPlayerPositionLists).
	# Each position's list is sorted by decreasing cost once, up front.
	def _buildRandomSquadCandidatePool(self):
		pool = self._buildFilteredPlayerPositionLists(set())
		for posList in pool:
			posList.sort(key=lambda playerData: playerData.nowCost, reverse=True)
		return pool

	# Cheap, greedy, cost-weighted random fill. No DFS/backtracking: for each
	# position slot, restrict to players that (a) aren't already picked, (b) don't
	# breach the per-club cap, and (c) are affordable while still leaving enough
	# budget to fill the remaining slots (reserving at least the cheapest
	# remaining candidate's cost per remaining slot). Then pick one at random,
	# weighted by cost, so the squad tends to use most of the budget without an
	# exhaustive search. Retries from scratch (bounded) on a rare dead-end.
	# rng must be a caller-supplied random.Random so a single top-level seed
	# makes an entire comparison run reproducible.
	def _generateRandomSquad(self, candidatePool, rng, maxAttempts=50):
		minCost = min(playerData.nowCost for posList in candidatePool for playerData in posList)
		for attempt in range(maxAttempts):
			squadData = SquadData(self.numPositions)
			teamCountTbl = dict()
			chosenIds = set()
			remainingBudget = self.budget
			ok = True
			for posIdx in range(self.numPositions):
				for _ in range(self.positionCountTbl[posIdx]):
					slotsLeftAfterThis = self.fullSquadSize - len(chosenIds) - 1
					affordableMax = remainingBudget - slotsLeftAfterThis * minCost
					eligible = [playerData for playerData in candidatePool[posIdx]
								if playerData.playerId not in chosenIds
								and teamCountTbl.get(playerData.teamId, 0) < self.maxNumPlayersPerTeam
								and playerData.nowCost <= affordableMax]
					if not eligible:
						ok = False
						break
					pick = rng.choices(eligible, weights=[e.nowCost for e in eligible])[0]
					squadData.positionTbl[posIdx].append(pick)
					squadData.totalCost += pick.nowCost
					squadData.totalPoints += pick.totalPoints
					teamCountTbl[pick.teamId] = teamCountTbl.get(pick.teamId, 0) + 1
					chosenIds.add(pick.playerId)
					remainingBudget -= pick.nowCost
				if not ok:
					break
			if ok:
				self._topUpSquadBudget(squadData, candidatePool, rng)
				return squadData
		assert 0, f"Could not generate a valid random squad after {maxAttempts} attempts"

	# Cheap, bounded hill-climb to spend more of the remaining budget after the
	# initial random fill: repeatedly picks a random occupied slot and, if a
	# same-position player not already owned is both pricier and still affordable
	# (without breaching the club cap), swaps in the priciest such upgrade found.
	# No DFS - just a fixed number of random probes.
	def _topUpSquadBudget(self, squadData, candidatePool, rng, numRounds=30):
		teamCountTbl = dict()
		for posList in squadData.positionTbl:
			for playerData in posList:
				teamCountTbl[playerData.teamId] = teamCountTbl.get(playerData.teamId, 0) + 1
		chosenIds = {playerData.playerId for posList in squadData.positionTbl for playerData in posList}
		slots = [(posIdx, idx) for posIdx in range(self.numPositions) for idx in range(len(squadData.positionTbl[posIdx]))]
		for _ in range(numRounds):
			posIdx, idx = rng.choice(slots)
			current = squadData.positionTbl[posIdx][idx]
			maxAffordableCost = current.nowCost + (self.budget - squadData.totalCost)
			candidates = [playerData for playerData in candidatePool[posIdx]
						  if playerData.playerId not in chosenIds
						  and playerData.nowCost > current.nowCost
						  and playerData.nowCost <= maxAffordableCost
						  and teamCountTbl.get(playerData.teamId, 0) - (1 if playerData.teamId == current.teamId else 0) < self.maxNumPlayersPerTeam]
			if not candidates:
				continue
			upgrade = max(candidates, key=lambda playerData: playerData.nowCost)
			squadData.positionTbl[posIdx][idx] = upgrade
			squadData.totalCost += upgrade.nowCost - current.nowCost
			squadData.totalPoints += upgrade.totalPoints - current.totalPoints
			teamCountTbl[current.teamId] -= 1
			teamCountTbl[upgrade.teamId] = teamCountTbl.get(upgrade.teamId, 0) + 1
			chosenIds.discard(current.playerId)
			chosenIds.add(upgrade.playerId)

	# Returns True if no combination of players can be added to the current squad to
	# beat the best squad.
	def _cannotBeatBestSquad(self, bestSquadData, curSquadData, curIdxList):
		curToBestValueDiff = bestSquadData.objectiveValue - curSquadData.objectiveValue
		testValueSum = 0
		for posIdx in range(len(curSquadData.positionTbl)):
			numRemainingForPosition = self.positionCountTbl[posIdx] - len(curSquadData.positionTbl[posIdx])
			if numRemainingForPosition > 0:
				idx = curIdxList[posIdx]
				for i in range(idx, idx+numRemainingForPosition):
					testValueSum += self._getSquadObjectiveValue(self.playerPositionTbl[posIdx][i])
		return (testValueSum <= curToBestValueDiff)
	
	def _writeBestSquadToFile(self, bestSquadData, outFn):
		# write outfile
		totalPoints = 0
		showPointsPerMatch = (self.squadOptimizationStat == 'points_per_match')
		with open(outFn,'w') as fOut:
			for posIdx in range(len(bestSquadData.positionTbl)):
				fOut.write("%s\n" % self.positionIdTbl[posIdx+1])
				header = "Name\tClub\tCost\tTotal Points"
				if showPointsPerMatch:
					header += "\tPoints Per Match"
				fOut.write("%s\n" % header)
				for playerData in bestSquadData.positionTbl[posIdx]:
					totalPoints += playerData.totalPoints
					clubName = self.teamIdTbl[playerData.teamId].name
					line = "%s\t%s\t%.1f\t%d" % (playerData.name, clubName, playerData.nowCost/10.0, playerData.totalPoints)
					if showPointsPerMatch:
						line += "\t%.1f" % playerData.pointsPerMatch
					fOut.write("%s\n" % line)
				fOut.write("\n")
		assert totalPoints == bestSquadData.totalPoints
		totalStrategyPoints = self._evaluateStrategy(self.statTypeForSquad, self.statTypeForCaptain, bestSquadData)
		print("%d %d %d" % (totalPoints, bestSquadData.totalCost, totalStrategyPoints))
	
	def _dfsFindBestSquad(self, teamCountTbl, curIdxList, bestSquadData, curSquadData, numConsecutiveBadSearches, numPlayersNotOnInputSquad=None, outFn=None):
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
					if numPlayersNotOnInputSquad is not None:
						if allPlayerList[i].playerId not in self.inputSquadPlayers:
							if numPlayersNotOnInputSquad == self.maxNumTransfers:
								continue
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
					curSquadData.objectiveValue += self._getSquadObjectiveValue(allPlayerList[i])
					curSquadData.totalCost += allPlayerList[i].nowCost
					newIdxList = curIdxList.copy()
					newIdxList[posIdx] = i+1
					if numPlayersNotOnInputSquad is not None:
						if allPlayerList[i].playerId not in self.inputSquadPlayers:
							numPlayersNotOnInputSquad += 1
					# find all squads that include the current list of players
					self._dfsFindBestSquad(teamCountTbl, newIdxList, bestSquadData, curSquadData, numConsecutiveBadSearches, numPlayersNotOnInputSquad, outFn)
					# remove current player before examining next player
					if numPlayersNotOnInputSquad is not None:
						if allPlayerList[i].playerId not in self.inputSquadPlayers:
							numPlayersNotOnInputSquad -= 1 # reset new player count
					curPlayerList.pop()
					curSquadData.totalPoints -= allPlayerList[i].totalPoints
					curSquadData.objectiveValue -= self._getSquadObjectiveValue(allPlayerList[i])
					curSquadData.totalCost -= allPlayerList[i].nowCost
					teamCountTbl[allPlayerList[i].teamId] -= 1
				return  # we have already examined all squads with the current set of players, so we can end our search
		# here we have a complete squad to compare against the best squad yet found
		if bestSquadData.objectiveValue < curSquadData.objectiveValue or (bestSquadData.objectiveValue == curSquadData.objectiveValue and bestSquadData.totalCost > curSquadData.totalCost):
			curSquadData.copyTo(bestSquadData)
			if outFn != None:
				self._writeBestSquadToFile(bestSquadData, outFn)
			numConsecutiveBadSearches[0] += 0
		else:
			numConsecutiveBadSearches[0] += 1

	def _readInCustomSquadJSON(self, squadFn, playerList):
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
						self.inputSquadData.positionTbl[playerPos-1].append(playerData)
						self.inputSquadPlayers.add(playerData.playerId)
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
		for posIdx in range(len(self.inputSquadData.positionTbl)):
			if len(self.inputSquadData.positionTbl[posIdx]) != self.positionCountTbl[posIdx]:
				positionStr = self.positionIdTbl[posIdx+1]
				assert 0, f"Error: incorrect number of {positionStr}: {len(self.inputSquadData.positionTbl[posIdx])}. Should be {self.positionCountTbl[posIdx]}"
					
	def _getLastCompletedGameWeek(self, topLevelData):
		# find first week whose data is not finished
		for idx in range(len(topLevelData['events'])):
			if not topLevelData['events'][idx]['finished']:
				return topLevelData['events'][idx]['id'] - 1  # return week id - 1, which should be same as week idx of last completed gameweek
		return len(topLevelData['events'])  # return last game week

	def readDataFromJSON(self, topLevelJsonFn, gameWeekPlayerJsonFn, gameWeekFixtureJsonFn, costHistoryJsonFn=None):
		fTop = open(topLevelJsonFn, 'r')
		topLevelData = json.load(fTop)
		self.lastCompletedGameWeek = self._getLastCompletedGameWeek(topLevelData)
		self._readTeamDataFromJSON(topLevelData)
		self._readPlayerDataFromJSON(topLevelData) # read cumulative data for each player
		fpgw = open(gameWeekPlayerJsonFn, 'r')
		gameweekPlayerData = json.load(fpgw)
		ffgw = open(gameWeekFixtureJsonFn, 'r')
		gameWeekFixtureData = json.load(ffgw)
		costHistoryData = None
		fCost = None
		if costHistoryJsonFn is not None:
			fCost = open(costHistoryJsonFn, 'r')
			costHistoryData = json.load(fCost)
		self._readGameWeekDataFromJSON(topLevelData, gameweekPlayerData, gameWeekFixtureData, costHistoryData)
		self._examineGameWeekData()
		fTop.close()
		fpgw.close()
		ffgw.close()
		if fCost is not None:
			fCost.close()

	# Forces self.requiredPlayerData into curSquadData/teamCountTbl before the DFS
	# starts, and removes them from self.playerPositionTbl so the DFS can't also
	# independently re-pick the same player while filling the remaining slots
	# (it has no player-identity dedup - it relies entirely on index-monotonicity
	# into self.playerPositionTbl[posIdx]). Must run after _createPlayerPositionTbl
	# (so self.playerPositionTbl exists and required players are guaranteed present
	# in it, per _createPlayerPositionTbl's curSquadPlayerIds protection) and before
	# the DFS starts.
	def _seedMandatoryPlayers(self, curSquadData, teamCountTbl):
		positionCounts = [0]*self.numPositions
		clubCounts = dict()
		requiredCost = 0
		for playerData in self.requiredPlayerData:
			posIdx = playerData.positionId - 1
			positionCounts[posIdx] += 1
			clubCounts[playerData.teamId] = clubCounts.get(playerData.teamId, 0) + 1
			requiredCost += playerData.nowCost
		for posIdx in range(self.numPositions):
			positionStr = self.positionIdTbl[posIdx+1]
			assert positionCounts[posIdx] <= self.positionCountTbl[posIdx], f"Error: too many required_players at position {positionStr}: {positionCounts[posIdx]}. Squad only has {self.positionCountTbl[posIdx]} slots for that position."
		for teamId, count in clubCounts.items():
			assert count <= self.maxNumPlayersPerTeam, f"Error: too many required_players from {self.teamIdTbl[teamId].name}: {count}. Max allowed per club is {self.maxNumPlayersPerTeam}."
		assert requiredCost <= self.budget, f"Error: required_players alone cost {requiredCost/10.0}m, exceeding the budget of {self.budget/10.0}m."
		for playerData in self.requiredPlayerData:
			posIdx = playerData.positionId - 1
			curSquadData.positionTbl[posIdx].append(playerData)
			curSquadData.totalCost += playerData.nowCost
			curSquadData.totalPoints += playerData.totalPoints
			curSquadData.objectiveValue += self._getSquadObjectiveValue(playerData)
			teamCountTbl[playerData.teamId] += 1
			self.playerPositionTbl[posIdx].remove(playerData)
		# Cheap upfront feasibility check: can the remaining slots even be afforded?
		# Without this, an infeasible required_players config doesn't crash (the
		# DFS's own budget/club-cap checks just prune every branch) - it silently
		# produces no output file after a potentially very long search. Turn that
		# into an immediate, clear error instead.
		minRemainingCost = 0
		for posIdx in range(self.numPositions):
			numRemainingForPosition = self.positionCountTbl[posIdx] - len(curSquadData.positionTbl[posIdx])
			if numRemainingForPosition > 0:
				cheapest = sorted(p.nowCost for p in self.playerPositionTbl[posIdx])[:numRemainingForPosition]
				assert len(cheapest) == numRemainingForPosition, f"Error: not enough eligible players at position {self.positionIdTbl[posIdx+1]} to complete the squad after required_players."
				minRemainingCost += sum(cheapest)
		assert curSquadData.totalCost + minRemainingCost <= self.budget, f"Error: required_players plus the cheapest possible remaining squad would cost {(curSquadData.totalCost + minRemainingCost)/10.0}m, exceeding the budget of {self.budget/10.0}m."

	def findBestSquad(self, outFn, squadStat='total_points'):
		assert squadStat in ('total_points', 'points_per_match'), f"Unknown squadStat: {squadStat}"
		self.squadOptimizationStat = squadStat
		self._resolveRequiredPlayers()
		self._createPlayerPositionTbl()
		bestSquadData = SquadData(self.numPositions)
		curSquadData = SquadData(self.numPositions)
		teamCountTbl = [0]*(len(self.teamIdTbl)+1) # map from team id to count of players for that team
		self._seedMandatoryPlayers(curSquadData, teamCountTbl)
		positionIdxList = [0, 0, 0, 0] # each element is the current idx within the full player list of the position given by that element
		numConsecutiveBadSearches = [0]
		self._dfsFindBestSquad(teamCountTbl, positionIdxList, bestSquadData, curSquadData, numConsecutiveBadSearches, None, outFn)

	def _findCustomSquadMetadata(self):
		for posIdx in range(len(self.inputSquadData.positionTbl)):
			playerList = self.inputSquadData.positionTbl[posIdx]
			for playerData in playerList:
				self.inputSquadData.totalPoints += playerData.totalPoints
				self.inputSquadData.totalCost += playerData.nowCost

	def findBestTransferOptions(self, squadFn, maxNumTransfers, outFn):
		self.squadOptimizationStat = 'total_points' # defensive: never inherit a stat left over from a prior findBestSquad call on this instance
		self.inputSquadData = SquadData(self.numPositions)
		self.inputSquadPlayers = set()
		self.maxNumTransfers = maxNumTransfers
		playerList = list()
		# initialize budget to 0. Will be set to total cost of players + remaining in bank
		self.budget = 0
		# read squad data from file
		self._readInCustomSquadJSON(squadFn, playerList)
		# find metadata of squad
		self._findCustomSquadMetadata()
		print("Budget: %.1fm euros" % (self.budget/10.0))
		self._createPlayerPositionTbl()
		# find best team given the max transfers allowed
		bestSquadData = SquadData(self.numPositions)
		self.inputSquadData.copyTo(bestSquadData)
		curSquadData = SquadData(self.numPositions)
		teamCountTbl = [0]*(len(self.teamIdTbl)+1) # map from team id to count of players for that team
		positionIdxList = [0, 0, 0, 0] # each element is the current idx within the full player list of the position given by that element
		numConsecutiveBadSearches = [0]
		self._dfsFindBestSquad(teamCountTbl, positionIdxList, bestSquadData, curSquadData, numConsecutiveBadSearches, 0, outFn)
		# find transfer options from differences between original and best squads
		transfersIn = list() # list of players to add
		transfersOut = list() # list of players to remove
		playersNotTransfered = set()
		for posList in bestSquadData.positionTbl:
			for playerData in posList:
				if playerData.playerId not in self.inputSquadPlayers:
					transfersIn.append(playerData)
				else:
					playersNotTransfered.add(playerData.playerId)
		for posList in self.inputSquadData.positionTbl:
			for playerData in posList:
				if playerData.playerId not in playersNotTransfered:
					transfersOut.append(playerData)
		totalPointsImprovement = bestSquadData.totalPoints - self.inputSquadData.totalPoints
		# write data to outfile
		with open(outFn,'w') as fOut:
			fOut.write(f"Total Points improvement: {totalPointsImprovement}\n")
			fOut.write("Players Out:\n")
			for p in transfersOut:
				fOut.write(f"{p.name}\n")
			fOut.write("\nPlayers In:\n")
			for p in transfersIn:
				fOut.write(f"{p.name}\n")

	# Compares a list of Strategy objects (see lib/strategies.py) by running each
	# against the SAME numTrials randomly generated starting squads (a paired
	# comparison: using identical starting squads for every strategy means the
	# differences in results are attributable to the strategy, not to which
	# random squads happened to be drawn, for a lower-variance comparison).
	# Returns {strategyName: [totalPoints, ...]}, one entry per trial. Writes a
	# plain-text summary to outFn if given. Nothing in this path calls
	# _dfsFindBestSquad/findBestTransferOptions - only cheap per-week heuristics.
	def compareStrategies(self, strategyList, numTrials, seed=None, outFn=None):
		rng = random.Random(seed)
		candidatePool = self._buildRandomSquadCandidatePool()
		randomSquads = [self._generateRandomSquad(candidatePool, rng) for i in range(numTrials)]
		resultsByStrategy = dict()
		for strategy in strategyList:
			strategy.squadSelector.prepare(self)
			(statTypeForSquad, statTypeForCaptain) = strategy.squadSelector.getStatTypes()
			pointsList = list()
			for squad in randomSquads:
				trialSquad = SquadData(self.numPositions)
				squad.copyTo(trialSquad)  # independent mutable copy; transfers must not leak between strategies/trials
				totalPoints = self._evaluateStrategy(statTypeForSquad, statTypeForCaptain, trialSquad,
													  transferPolicy=strategy.transferPolicy, rng=rng)
				pointsList.append(totalPoints)
			resultsByStrategy[strategy.name] = pointsList
		if outFn is not None:
			self._writeStrategyComparisonToFile(resultsByStrategy, outFn)
		return resultsByStrategy

	def _writeStrategyComparisonToFile(self, resultsByStrategy, outFn):
		import statistics
		with open(outFn, 'w') as fOut:
			fOut.write("Strategy\tNumTrials\tMeanPoints\tStdevPoints\tMinPoints\tMaxPoints\n")
			for name, pointsList in resultsByStrategy.items():
				mean = statistics.mean(pointsList)
				stdev = statistics.stdev(pointsList) if len(pointsList) > 1 else 0.0
				fOut.write("%s\t%d\t%.1f\t%.1f\t%d\t%d\n" %
							(name, len(pointsList), mean, stdev, min(pointsList), max(pointsList)))

