from analyzer import StatType


class SquadSelector:
	# Called once per strategy (not per trial/week), for expensive-but-shared
	# setup, e.g. recomputing StatType.FORM for a non-default window. No-op by default.
	def prepare(self, analyzer):
		pass

	# Returns (statTypeForSquad, statTypeForCaptain). Called once per strategy,
	# not once per week - none of the built-in strategies need the stat choice
	# to vary mid-season. A future strategy that does would need
	# _evaluateStrategy's loop to call this per-week instead of using fixed values.
	def getStatTypes(self):
		raise NotImplementedError


class FixedStatSquadSelector(SquadSelector):
	def __init__(self, statTypeForSquad, statTypeForCaptain=None):
		self.statTypeForSquad = statTypeForSquad
		self.statTypeForCaptain = statTypeForCaptain if statTypeForCaptain is not None else statTypeForSquad

	def prepare(self, analyzer):
		# StatType.FORM is shared, mutable, per-player state (see
		# WindowedFormSquadSelector below) - a strategy using plain FORM must not
		# silently inherit whatever window a previously-run strategy in the same
		# compareStrategies() call left it in. Reset to the default window so
		# this selector's behavior doesn't depend on run order.
		if StatType.FORM in (self.statTypeForSquad, self.statTypeForCaptain):
			analyzer._computeFormStat()

	def getStatTypes(self):
		return (self.statTypeForSquad, self.statTypeForCaptain)


class WindowedFormSquadSelector(FixedStatSquadSelector):
	"""'Highest points over the past N game weeks.' Reuses StatType.FORM as the
	storage slot; prepare() recomputes it for window=windowSize (a uniform
	divisor never changes relative order, so this is equivalent to ranking by
	the raw N-week point sum)."""
	def __init__(self, windowSize):
		super().__init__(StatType.FORM, StatType.FORM)
		self.windowSize = windowSize

	def prepare(self, analyzer):
		analyzer._computeFormStat(self.windowSize)


class TransferPolicy:
	# Called once per strategy (not per trial/week), for expensive-but-shared
	# setup - mirrors SquadSelector.prepare(). No-op by default.
	def prepare(self, analyzer):
		pass

	# Returns [(playerOut, playerIn), ...] to apply for the upcoming week, or [].
	# Must stay cheap (O(squad size * candidate pool size) at most) - never call
	# _dfsFindBestSquad/findBestTransferOptions from here.
	def selectTransfers(self, analyzer, squadData, weekIdx, weekSquad, weekSubs, rng):
		raise NotImplementedError


class NoTransferPolicy(TransferPolicy):
	def selectTransfers(self, analyzer, squadData, weekIdx, weekSquad, weekSubs, rng):
		return []


class WorstFormTransferPolicy(TransferPolicy):
	"""Each week, sell the single lowest-StatType.FORM squad member and buy the
	best-FORM same-position replacement not already owned that fits budget and
	the per-club cap. Exactly one transfer/week, matching FPL's one free
	transfer/week, so no points-hit accounting is needed.

	windowSize controls which trailing-N-week FORM window drives both the sell
	and buy decision (None = analyzer's default window). prepare() always sets
	it explicitly, rather than trusting the paired SquadSelector to have set up
	the window as a side effect - StatType.FORM is shared, mutable, per-player
	state, so this policy must not silently inherit whatever window a
	previously-run strategy in the same compareStrategies() call left it in."""
	def __init__(self, windowSize=None):
		self.windowSize = windowSize
		self._candidatePool = None  # lazily built once, shared across all trials/weeks

	def prepare(self, analyzer):
		analyzer._computeFormStat(self.windowSize)

	def selectTransfers(self, analyzer, squadData, weekIdx, weekSquad, weekSubs, rng):
		if self._candidatePool is None:
			self._candidatePool = analyzer._buildRandomSquadCandidatePool()
		allPlayers = [p for posList in squadData.positionTbl for p in posList]
		outPlayer = min(allPlayers, key=lambda p: analyzer._getStatValueForWeek(p, StatType.FORM, weekIdx))
		posIdx = outPlayer.positionId - 1
		replacement = analyzer._findReplacementPlayer(
			StatType.FORM, weekIdx, self._candidatePool[posIdx], squadData, outPlayer)
		if replacement is None:
			return []
		return [(outPlayer, replacement)]


class WildcardTransferPolicy(TransferPolicy):
	"""Plays the wildcard chip: in the gameweeks in wildcardWeeks, unlimited
	transfers rebuild the squad into the best squad by points over the trailing
	windowSize weeks (see Analyzer.getBestSquadForWeek, an exhaustive search
	computed once and cached, shared by every trial); in every other week it defers to
	baseTransferPolicy. FPL allows one wildcard in each half of the season, so at
	most one of wildcardWeeks may be in gameweeks 1-19 and one in 20-38.

	wildcardWeeks are the gameweeks the chip is played IN. Transfers chosen after
	gameweek G-1 take effect in gameweek G, so the chip can't be played in
	gameweek 1 (the starting squad is fixed before it). The rebuild uses the
	data up to gameweek G-1 only. Weeks past the available data are ignored with
	a warning. Stateless across trials."""
	NUM_GAMEWEEKS = 38
	LAST_FIRST_HALF_WEEK = 19

	def __init__(self, baseTransferPolicy, wildcardWeeks, windowSize):
		wildcardWeeks = list(wildcardWeeks)
		for week in wildcardWeeks:
			assert isinstance(week, int) and 2 <= week <= self.NUM_GAMEWEEKS, f"Error: wildcard week must be an integer from 2 to {self.NUM_GAMEWEEKS}, got {week!r}"
		assert len(set(wildcardWeeks)) == len(wildcardWeeks), f"Error: duplicate wildcard weeks: {wildcardWeeks}"
		assert sum(1 for week in wildcardWeeks if week <= self.LAST_FIRST_HALF_WEEK) <= 1, f"Error: at most one wildcard may be played in gameweeks 1-{self.LAST_FIRST_HALF_WEEK}: {wildcardWeeks}"
		assert sum(1 for week in wildcardWeeks if week > self.LAST_FIRST_HALF_WEEK) <= 1, f"Error: at most one wildcard may be played in gameweeks {self.LAST_FIRST_HALF_WEEK + 1}-{self.NUM_GAMEWEEKS}: {wildcardWeeks}"
		assert isinstance(windowSize, int) and windowSize >= 1, f"Error: wildcard windowSize must be a positive integer, got {windowSize!r}"
		self.baseTransferPolicy = baseTransferPolicy
		self.wildcardWeeks = frozenset(wildcardWeeks)
		self.windowSize = windowSize

	def prepare(self, analyzer):
		self.baseTransferPolicy.prepare(analyzer)
		for week in sorted(self.wildcardWeeks):
			if week - 1 < analyzer._getStartWeek() or week > analyzer.lastCompletedGameWeek:
				print(f"WARNING: wildcard week {week} is outside the available data (gameweeks {analyzer._getStartWeek()+1}-{analyzer.lastCompletedGameWeek}), so it will never be played")
			else:
				analyzer.getBestSquadForWeek(week - 1, self.windowSize) # build/cache now rather than mid-trial

	def selectTransfers(self, analyzer, squadData, weekIdx, weekSquad, weekSubs, rng):
		if weekIdx + 1 not in self.wildcardWeeks:
			return self.baseTransferPolicy.selectTransfers(analyzer, squadData, weekIdx, weekSquad, weekSubs, rng)
		targetSquad = analyzer.getBestSquadForWeek(weekIdx, self.windowSize)
		transfers = []
		for posIdx, targetPlayers in enumerate(targetSquad):
			currentPlayers = squadData.positionTbl[posIdx]
			targetIds = {p.playerId for p in targetPlayers}
			currentIds = {p.playerId for p in currentPlayers}
			outPlayers = [p for p in currentPlayers if p.playerId not in targetIds]
			inPlayers = [p for p in targetPlayers if p.playerId not in currentIds]
			assert len(outPlayers) == len(inPlayers)
			transfers.extend(zip(outPlayers, inPlayers))
		return transfers


class Strategy:
	# A complete strategy is always both a squad selection AND a transfer
	# policy - pass NoTransferPolicy() explicitly for a strategy that never
	# transfers, rather than leaving transfers out as if they were optional.
	def __init__(self, name, squadSelector, transferPolicy):
		self.name = name
		self.squadSelector = squadSelector
		self.transferPolicy = transferPolicy


# Squad-selection form windows to compare, in gameweeks. Each gets its own
# strategy: pick the squad by highest points over the trailing N weeks, never
# transfer. Add/remove numbers here to change what compareStrategies() runs.
SQUAD_FORM_WINDOWS = [3, 5, 10, 12, 15, 20, 25]

# Transfer-policy form windows to compare, in gameweeks. Each gets its own
# strategy: keep the baseline (total-points) squad selection, but sell the
# worst-FORM player each week using a trailing N-week window.
TRANSFER_FORM_WINDOWS = [3, 5, 10, 12, 15, 20, 25]


# Wildcard comparisons: each schedule (the gameweeks the chip is played in, at
# most one per half-season) is paired with each window, giving the strategy
# squad_transfer_form_<N>w plus a wildcard. Use windows that are also in
# SQUAD_FORM_WINDOWS to have the matching no-wildcard strategy to compare to.
WILDCARD_WINDOWS = [10]
WILDCARD_SCHEDULES = [[10, 30]]


def buildDefaultStrategies():
	strategies = [
		# No squad-selection or transfer policy beyond the simplest possible
		# choice - everything else is compared against this.
		Strategy("baseline", FixedStatSquadSelector(StatType.TOTAL_POINTS), NoTransferPolicy()),
	]
	for windowSize in SQUAD_FORM_WINDOWS:
		strategies.append(Strategy(
			f"squad_form_{windowSize}w",
			WindowedFormSquadSelector(windowSize=windowSize),
			NoTransferPolicy(),
		))
	for windowSize in TRANSFER_FORM_WINDOWS:
		strategies.append(Strategy(
			f"transfer_form_{windowSize}w",
			FixedStatSquadSelector(StatType.TOTAL_POINTS),
			WorstFormTransferPolicy(windowSize=windowSize),
		))
	for windowSize in SQUAD_FORM_WINDOWS:
		strategies.append(Strategy(
			f"squad_transfer_form_{windowSize}w",
			WindowedFormSquadSelector(windowSize=windowSize),
			WorstFormTransferPolicy(windowSize=windowSize),
		))
	for windowSize in WILDCARD_WINDOWS:
		for schedule in WILDCARD_SCHEDULES:
			strategies.append(Strategy(
				f"squad_transfer_form_{windowSize}w_wc{'_'.join(str(week) for week in schedule)}",
				WindowedFormSquadSelector(windowSize=windowSize),
				WildcardTransferPolicy(WorstFormTransferPolicy(windowSize=windowSize), schedule, windowSize),
			))
	return strategies
