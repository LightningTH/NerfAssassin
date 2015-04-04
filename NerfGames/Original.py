class NerfGame:
	GameType = "Original"
	Description = "Original Nerf Assassin"
	GameDetails = "Each person is assigned a target, last man standing wins"

	GameID = -1
	GameTypeID = -1
	db = None
	NerfAssassin = None

	def IsGameOver(self):
		#if no players left then return that the game is over
		(ret, playersleft) = self.db.fetchOne(cherrypy.thread_data.conn,"select count(id) from gameinfo where game_id=? and killer_id is null and target_id is not null", (self.GameID,))
		(playercount, ) = playersleft
		if(playercount == 0):
			return False
		return True

	def CheckConfirmationTimeout(self):
		#see if any confirmations are out of time and auto-confirm them
		(ret, confirms) = self.db.fetchAll(cherrypy.thread_data.conn,"select id, kill_datetime [timestamp], reporting_killer from gameinfo where game_id=? and assassin_id is not null and target_id is not null and reporting_killer is not null and confirm_hash is not null and killer_id is null", (self.GameID,))

		if(len(confirms) == 0):
			return

		#get the config default time
		auto_confirm_time = int(db.GetConfig(cherrypy.thread_data.conn, "auto_confirm_time").Value)

		#if the confirm is old then act as if it was reported
		for Entry in confirms:
			(kill_id, kill_datetime, reporting_killer) = Entry
			TimeDiff = datetime.datetime.utcnow() - kill_datetime
			if (TimeDiff.total_seconds() / 60) >= auto_confirm_time:
				self.KillPlayer(reporting_killer)

		return

	def AssignPlayers(self, players):
		#game doesn't have assignments yet

		Cur = random.randint(0, len(players)-1)
		(first_id, first_assassin_id, first_target_id) = players[Cur]
		while(len(players) > 1):
			(cur_id, cur_assassin_id, cur_target_id) = players.pop(Cur)

			Next = random.randint(0, len(players)-1)
			(next_id, next_assassin_id, next_target_id) = players[Next]
			self.db.execute(cherrypy.thread_data.conn,"Update gameinfo set target_id=? where id=?", (next_assassin_id, cur_id))
			Cur = Next

		#update the last assassin
		(cur_id, cur_assassin_id, cur_target_id) = players.pop()
		self.db.execute(cherrypy.thread_data.conn,"Update gameinfo set target_id=? where id=?", (first_assassin_id, cur_id))
	
		#now email out the targets
		(ret, players) = self.db.fetchAll(cherrypy.thread_data.conn,"select a.firstname, a.lastname, a.nickname, a.email_address, b.firstname, b.lastname, b.nickname, b.picture_filename from assassins a, assassins b, gameinfo gi where gi.game_id=? and b.id=gi.target_id and a.id=gi.assassin_id", (self.GameID,))

		for Entry in players:
			(assassin_first, assassin_last, assassin_nick, assassin_email, target_first, target_last, target_nick, target_picture) = Entry
			self.NerfAssassin.SendEmail(assassin_email, "%s,\nYour target is %s, also known as %s %s. Attached is your target's picture" % (assassin_nick, target_nick, target_first, target_last), target_picture) 
		return

	def _CalcRating(self, positive, negative):
		#Score = Lower bound of Wilson score confidence interval for a Bernoulli parameter
		#based on information from http://www.evanmiller.org/how-not-to-sort-by-average-rating.html
		#positive = sum of inverse position across all games played
		#negative = sum of inverse number of positions below player across all games played
		#example: 3rd in a game of 10 people, positive 8, negative 2
		#	5th in a game of 20 people, positive 16, negative 4
		#	combined would give positive 24, negative 6
		#This allows overall ranking across games to impact for a player playing a lot of games and varying number of people per game
		#vs the player that played 1 game and came in first in a group of 5 people
		return ((positive + 1.9208) / (positive + negative) - \
			(1.98 * math.sqrt((positive * negative) / (positive + negative) + 0.9604) / (positive + negative)) / (1+(3.8416 / (positive+negative))))

	def CalculateStats(self):
		(ret, players) = self.db.fetchAll("select id from assassins")

		#add up all positive and negative entries for people
		Stats = dict()
		for (player_id,) in players:
			(ret, games) = self.db.fetchAll("select distinct gi.game_id, gi.ranking, g.start_datetime [timestamp] from gameinfo gi, games g where gi.target_id=? and gi.ranking is not null and gi.game_id = g.game_id and g.gametype_id=?", (player_id, self.GameTypeID))

			#if no games, ignore them
			if(len(games) == 0):
				continue

			Stats[player_id] = (1,1)
			for (game_id,ranking,start_datetime) in games:
				(ret, gamestats) = self.db.fetchOne("select count(distinct(target_id)) from gameinfo where game_id=?", (game_id,))
				(totalcount,) = gamestats

				(positive,negative) = Stats[player_id]

				positive = positive + (totalcount - ranking) 
				negative = negative + ranking
				timediff = datetime.datetime.utcnow() - start_datetime
				timediff = timediff.days()

				#if they have played in the last 2 months they get full score, otherwise a sliding scale of 10% per month loss
				if timediff < 60:
					totalamount = 1.0
				else:
					totalamount = 1.0 - (0.1 * (float(timediff - 60) / 30.0))
				Stats[player_id] = (positive,negative, totalamount)


		#go thru and calculate percentages for everyone
		NewStats = []
		for Entry in Stats:
			(positive, negative, totalamount) = Stats[Entry]
			if(positive == negative):
				negative = negative + 1

			NewStats.append((self._CalcRating(positive, negative) * totalamount, Entry))

		#sort the new list by percentages then update the database
		NewStats.sort()
		NewStats.reverse()
		Ranking = 0
		LastRating = 0
		for (rating, id) in NewStats:
			if(rating != LastRating):
				Ranking = Ranking + 1
				LastRating = rating

			self.NerfAssassin.UpdateRank(id, self.GameTypeID, Ranking)
		return

