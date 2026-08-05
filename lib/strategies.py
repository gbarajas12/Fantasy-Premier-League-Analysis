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
SQUAD_FORM_WINDOWS = [3, 5, 10]

# Transfer-policy form windows to compare, in gameweeks. Each gets its own
# strategy: keep the baseline (total-points) squad selection, but sell the
# worst-FORM player each week using a trailing N-week window.
TRANSFER_FORM_WINDOWS = [3, 5, 10]


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
	return strategies
