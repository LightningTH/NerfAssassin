class NerfGame:
	GameType = "empty"
	Description = "Empty Holder"
	GameDetails = "No Details"

	GameID = -1
	GameTypeID = -1
	db = None
	NerfAssassin = None

	def IsGameOver(self):
		return True

	def CheckConfirmationTimeout(self):
		return

	def AssignPlayers(self, players):
		return

	def _CalcRating(self, positive, negative):
		return 0

	def CalculateStats(self):
		return

