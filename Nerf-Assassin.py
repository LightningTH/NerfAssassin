import sys, os
import cherrypy
import sqlite3
import random
import string
import smtplib  
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import datetime
import pprint
import math

import NerfGames
import html
import db

try:
	import bcrypt
except:
	print "Missing py-bcrypt: http://code.google.com/p/py-bcrypt/"
	sys.exit(0)

class NerfAssassin:
	@cherrypy.expose
	def gamecheck(self):
		#check on any games that are active or becoming active for assignment
		(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select id, start_datetime [timestamp], gametype from games where end_datetime is null")
		if(row == None or len(row) == 0):
			return

		#we have a game that will start or is running, determine and assign accordingly
		(gameid, starttime, gametype) = row

		#if the time is in the future, exit
		if(starttime > datetime.datetime.utcnow()):
			return

		#see if we need to do assignments
		(ret, players) = db.fetchAll(cherrypy.thread_data.conn,"select id, assassin_id, target_id from gameinfo where game_id=? order by target_id desc", (gameid,))
		if(len(players) <= 1):
			#no players or only 1 player, time is past, remove the game
			db.execute(cherrypy.thread_data.conn,"delete from games where id=?", (gameid,))
			return

		Game = NerfGames.GetGameByID(gametype)
		Game.NerfAssassin = NerfAssassin
		Game.db = db
		Game.GameID = gameid
		Game.GameTypeID = gametype

		(id, assassin_id, target_id) = players[0]
		if(target_id == None):
			Game.AssignPlayers(players)
	
		else:
			#game has assignments, see if the game is over yet
			Game = NerfAssassin.GetGameByID(gametype)
			Game.NerfAssassin = NerfAssassin
			Game.db = db
			Game.GameID = gameid
			Game.GameTypeID = gametype
			if(Game.IsGameOver()):
				#if no one left to kill, game over
				db.execute(cherrypy.thread_data.conn,"update games set end_datetime=datetime(\"now\") where id=?", (gameid,))

				#remove any outstanding reports
				db.execute(cherrypy.thread_data.conn,"delete from gameinfo where reporting_killer is not null and target_id is null and game_id=?",(gameid,))

				#do a stats update for the game type
				Game.CalculateStats()
			else:
				Game.CheckConfirmationTimeout()

		del Game
		return

	def SendEmail(self, toemail, msgtext, picture=None):
		msg = MIMEMultipart()
		msg["To"] = toemail

		msgtext = MIMEText(msgtext)
		msg.attach(msgtext)

		if(picture != None):
			pic = MIMEImage(open("profile-images/" + picture,"r").read())
			msg.attach(pic)

		#go get the config settings
		(ret, Config) = db.fetchAll(cherrypy.thread_data.conn,"Select name, value from config where name in ('from_email', 'email_subject', 'email_server')")

		for (conf_name, conf_value) in Config:
			if(conf_name == "from_email"):
				msg["From"] = conf_value
			else if(conf_name == "email_subject"):
				msg["Subject"] = conf_value
			else if(conf_name == "email_server"):
				msg["Server"] = conf_value
 
		# Send the email message
		server = smtplib.SMTP(msg["Server"])
		server.ehlo()
		server.sendmail(msg["From"], [msg["To"]], msg.as_string())
		server.quit()

		return

	def ValidateLogin(self, nickname="", password=""):
		cherrypy.session.load()
		if((nickname == "") and (password == "")):
			try:
				nickname = cherrypy.session.get("Nickname")
				password = cherrypy.session.get("Password")
				if(nickname == None or password == None):
					return False
			except:
				return False

		(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select id, password from assassins where lower(nickname)=?", (nickname.lower(),))
		if(row != None and len(row) != 0):
			(profileid, dbpass) = row
			if(bcrypt.hashpw(password,str(dbpass)) == str(dbpass)):
				cherrypy.session["Nickname"] = nickname
				cherrypy.session["Password"] = password
				cherrypy.session["ProfileID"] = profileid
				cherrypy.session.save()
				return True
			else:
				return False

		return False

	@cherrypy.expose
	def logout(self):
		cherrypy.session.clear()
		raise cherrypy.HTTPRedirect("/")

	@cherrypy.expose
	def target_killed(self, id):
		if(self.ValidateLogin()):
			#make sure that the request is valid
			(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select gi.id, a.email_address from gameinfo gi, games g, assassins a where gi.assassin_id=? and gi.target_id=? and gi.game_id=g.id and g.end_datetime is null and a.id=gi.target_id", (cherrypy.session.get("ProfileID"), id))
			if row != None and len(row) != 0:
				(gameinfo_id, email_address) = row

				gamehash = ''.join([random.choice(string.letters + string.digits) for i in range(32)])
				db.execute(cherrypy.thread_data.conn,"update gameinfo set confirm_hash=?, reporting_killer=? where id=?", (gamehash, cherrypy.session.get("ProfileID"), gameinfo_id))

				self.SendEmail(email_address, "It was reported that you have been assassinated. Please goto the following link to confirm your assassination.\n%s" % ("http://tank:8080/confirm_kill?confirm=" + gamehash))
				return html.display_message(self.ValidateLogin(), "Email sent")
			else:
				return html.display_message(self.ValidateLogin(), "Invalid ID")
		else:
			raise cherrypy.HTTPRedirect("/")

	@cherrypy.expose
	def report_killed(self):
		if(self.ValidateLogin()):
			gamehash = ''.join([random.choice(string.letters + string.digits) for i in range(32)])
			(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select id from games where end_datetime is null")
			if(row == None or len(row) == 0):
				return html.display_message(self.ValidateLogin(), "Invalid ID")

			(game_id, ) = row
			db.execute(cherrypy.thread_data.conn,"insert into gameinfo(game_id, assassin_id, confirm_hash, reporting_killer) values(?,?,?,?)", (game_id, cherrypy.session.get("ProfileID"), gamehash, cherrypy.session.get("ProfileID")))

			return html.display_message(self.ValidateLogin(), "Please provide the following URL to the person you killed<br>%s" % ("http://tank:8080/confirm_kill?confirm=" + gamehash))
		else:
			raise cherrypy.HTTPRedirect("/")

	@cherrypy.expose
	def confirm_kill(self, **args):
		if(self.ValidateLogin()):
			if "confirm" in args:
				confirm = args["confirm"]
			else:
				confirm = cherrypy.session.pop("confirm_hash", None)

			if(confirm == None):
				return self.profile()

			if "confirmed" not in args:
				return html.HTMLReplaceSection(self.ValidateLogin(), "confirm", open("static/confirm.html","r").read(), [{"confirm":confirm, "url":"confirm_kill"}])
			else:
				if(args["confirmed"] == 0):
					#email the assassin and notify them
					(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select a.nickname, a.email_address, gi.target_id, gi.id from assassins a, gameinfo gi, games g where gi.game_id = g.id and g.end_datetime is null and gi.confirm_hash=? and a.id=gi.reporting_killer", (confirm,))
					if(row != None and len(row) != 0):
						(nickname, assassin_email, target_id, gameinfo_id) = row
						if(target_id == None):
							db.execute(cherrypy.thread_data.conn,"delete from gameinfo where id=?", (gameinfo_id,))

						self.SendEmail(assassin_email, "%s\nThe target did not confirm your kill" % (nickname))

					return html.display_message(self.ValidateLogin(), "Kill not confirmed")

			(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select gi.id, gi.target_id, gi.reporting_killer from gameinfo gi, games g where gi.game_id = g.id and g.end_datetime is null and gi.confirm_hash=? and killer_id is null", (confirm,))

			if(confirm == None or row == None or len(row) == 0):
				return html.display_message(self.ValidateLogin(), "Invalid confirmation code")

			(gameinfo_id, target_id, reporting_killer) = row

			#if no target then this was a kill without it being a known target
			if(target_id == None):
				db.execute(cherrypy.thread_data.conn,"delete from gameinfo where id=?", (gameinfo_id,))

			return self.kill_player(reporting_killer)

		elif("confirm" in args):
			cherrypy.session["confirm_hash"] = args["confirm"]
			raise cherrypy.HTTPRedirect("/login.html")

		return html.display_message(self.ValidateLogin(), "Invalid confirmation code")

	@cherrypy.expose
	def assassin_killed(self, **args):
		#indicates the assassin was killed by their target
		print "assassin_killed", args
		if(self.ValidateLogin()):
			if "confirmed" not in args:
				return html.HMTLReplaceSection(self.ValidateLogin(), "confirm", open("static/confirm.html","r").read(), [{"confirm":args["id"], "url":"assassin_killed"}])

			#kill the player based on the id they confirmed
			if args["confirmed"] == "1":
				return self.kill_player(args["confirm"])
			else:
				return self.profile()
			
		else:
			print "ValidateLogin failed"
			raise cherrypy.HTTPRedirect("/")

	def kill_player(self, killer_id):
		#called when we are to kill the local player
		profile_id = cherrypy.session.get("ProfileID")
		(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select gi.id, g.id, gi.assassin_id from games g, gameinfo gi where gi.game_id = g.id and gi.target_id=? and g.end_datetime is null and gi.killer_id is null", (profile_id,))
		if(row == None or len(row) == 0):
			return html.display_message(self.ValidateLogin(), "Error updating kills")
		(gameinfo_id, game_id, assassin_id) = row

		#figure out the ranking
		(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select min(ranking) from gameinfo where game_id=?", (game_id,))
		(ranking,) = row
		if(row == None or len(row) == 0 or ranking == None):
			(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select count(distinct(target_id))+1 from gameinfo where game_id=?", (game_id,))

		(ranking,) = row
		ranking = int(ranking)
		ranking = ranking - 1

		db.execute(cherrypy.thread_data.conn,"update gameinfo set killer_id=?, kill_datetime=datetime('now'), ranking=? where id=?", (killer_id, ranking, gameinfo_id))

		#lookup who this player's target was
		(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select target_id from gameinfo where assassin_id=? and game_id=? and killer_id is null", (profile_id,game_id))
		(target_id,) = row

		#mark the record for this player to be no kill
		db.execute(cherrypy.thread_data.conn,"update gameinfo set killer_id=0 where game_id=? and target_id=? and assassin_id=? and killer_id is null", (game_id, target_id, profile_id)) 

		#don't insert if the assassin and target match as it is end of the game
		if(target_id != assassin_id):
			db.execute(cherrypy.thread_data.conn,"insert into gameinfo (game_id, assassin_id, target_id) values(?,?,?)", (game_id, assassin_id, target_id))

			#report the new target to the assassin
			(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select a.nickname, a.firstname, a.lastname, a.email_address, b.firstname, b.lastname, b.nickname, b.picture_filename from assassins a, assassins b, gameinfo gi where gi.game_id=? and a.id=gi.assassin_id and gi.assassin_id=? and b.id=gi.target_id and gi.killer_id is null", (game_id, assassin_id))
			(assassin_nick, assassin_first, assassin_last, assassin_email, target_first, target_last, target_nick, target_picture) = row
			self.SendEmail(assassin_email, "%s, your target is now %s, also known as %s %s. Attached is your target's picture" % (assassin_nick, target_nick, target_first, target_last), target_picture) 
		else:
			#update the last player to be first
			db.execute(cherrypy.thread_data.conn,"Update gameinfo set ranking=1 where killer_id=0 and target_id=? and game_id=? and assassin_id=?", (assassin_id, game_id, profile_id))

		return html.display_message(self.ValidateLogin(), "Thank you for confirming your death")

	@cherrypy.expose
	def stats(self):
		(ret, rows) = db.fetchAll(cherrypy.thread_data.conn,"select id, firstname, lastname, nickname, ranking from assassins where ranking is not null order by ranking, firstname, lastname, nickname")

		(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select id from games where end_datetime is null")
		if(row == None or len(row) == 0):
			game_id = 0
		else:
			(game_id,) = row

		StatData = []
		for Entry in rows:
			(id, firstname, lastname, nickname, ranking) = Entry
			dictEntry = dict()
			dictEntry["profile_id"] = id
			dictEntry["firstname"] = firstname
			dictEntry["lastname"] = lastname
			dictEntry["nickname"] = nickname
			dictEntry["rank"] = html.ordinal(ranking)
			dictEntry["total_assassinations"] = 0
			(ret, rowcount) = db.fetchOne(cherrypy.thread_data.conn,"Select count(killer_id) from gameinfo where killer_id=? and game_id != ?", (id, game_id))
			if(ret == True and rowcount != None):
				(dictEntry["total_assassinations"],) = rowcount
			(ret, rowcount) = db.fetchOne(cherrypy.thread_data.conn,"Select count(target_id) from gameinfo where target_id=? and killer_id is not null and killer_id != 0 and game_id != ?", (id, game_id))
			if(ret == True and rowcount != None):
				(dictEntry["total_deaths"],) = rowcount
			StatData.append(dictEntry)

		(ret, rows) = db.fetchAll(cherrypy.thread_data.conn,"select id, firstname, lastname, nickname, ranking from assassins where ranking is null order by ranking, firstname, lastname, nickname")
		for Entry in rows:
			(id, firstname, lastname, nickname, ranking) = Entry
			dictEntry = dict()
			dictEntry["profile_id"] = id
			dictEntry["firstname"] = firstname
			dictEntry["lastname"] = lastname
			dictEntry["nickname"] = nickname
			dictEntry["rank"] = html.ordinal(ranking)
			dictEntry["total_assassinations"] = 0
			(ret, rowcount) = db.fetchOne(cherrypy.thread_data.conn,"Select count(killer_id) from gameinfo where killer_id=? and game_id != ?", (id, game_id))
			if(ret == True and rowcount != None):
				(dictEntry["total_assassinations"],) = rowcount
			(ret, rowcount) = db.fetchOne(cherrypy.thread_data.conn,"Select count(target_id) from gameinfo where target_id=? and killer_id is not null and killer_id != 0 and game_id != ?", (id, game_id))
			if(ret == True and rowcount != None):
				(dictEntry["total_deaths"],) = rowcount
			StatData.append(dictEntry)

		StatHTML = open("static/stats.html","r").read()
		StatHTML = html.HTMLCheckLoggedIn(self.ValidateLogin(), StatHTML)

		return html.HTMLReplaceSection(self.ValidateLogin(), "stat", StatHTML, StatData)

	@cherrypy.expose
	def creategame(self, **args):
		if(self.ValidateLogin()):
			args = db.sanitize(**args)

			#make sure the user is allowed to create a game
			(ret, createcheck) = db.fetchOne(cherrypy.thread_data.conn,"select picture_filename, firstname, lastname from assassins where id=? and (firstname is Null or lastname is Null or picture_filename is Null)", (cherrypy.session.get("ProfileID"),))
			if(createcheck != None and len(createcheck) != 0):
				return html.display_message(self.ValidateLogin(), "You can not create a game until your full first and last name is filled in and a face picture is provided")

			(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"Select id from games where end_datetime is null")
			if(row == None or len(row) == 0):
				if(args["gamerules"] == "0"):
					if(args["newrules_name"] == "" or args["newrules"] == ""):
						return html.display_message(self.ValidateLogin(), "No name specified or new rules are empty")

					(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select id from rules where lower(rulename) = ?", (args["newrules_name"].lower(),))
					if(row != None and len(row) != 0):
						return html.display_message(self.ValidateLogin(), "Rule already exists")

					args["newrules"] = args["newrules"].replace("\r","")
					db.execute(cherrypy.thread_data.conn,"insert into rules(rulename, rules) values(?,?)", (args["newrules_name"], args["newrules"]))
					(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select id from rules where lower(rulename) = ?", (args["newrules_name"].lower(),))
					(args["gamerules"], ) = row

				try:
					Date = args["gamestart_date"].split("/")
					NewDate = "%02d/%02d/%04d" % (int(Date[0]), int(Date[1]), int(Date[2]))
					Time = args["gamestart_time"].split(":")
					if(Time[1].find(" ") != -1):
						Time2 = Time[1].split(" ")
					else:
						Time2 = []
						Time2.append(Time[1][0:2])
						Time2.append(Time[1][2:4])

					NewTime = "%02d:%02d %s" % (int(Time[0]), int(Time2[0]), Time2[1])
					
					StartDate = datetime.datetime.strptime(NewDate + " " + NewTime, "%m/%d/%Y %I:%M %p")
				except Exception, ex:
					print ex
					return html.display_message(self.ValidateLogin(), "Error converting specified date and time")

				if(StartDate < datetime.datetime.now()):
					return html.display_message(self.ValidateLogin(), "Start date and time can not be in the past")

				(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select id from rules where id = ?", (args["gamerules"],))
				if(row == None or len(row) == 0):
					return html.display_message(self.ValidateLogin(), "Invalid rule")

				#adjust for utc
				LocalStartDate = StartDate
				StartDate = StartDate + (datetime.datetime.utcnow() - datetime.datetime.now())
				db.execute(cherrypy.thread_data.conn,"insert into games(start_datetime, rule_id) values(datetime(?),?)", (StartDate.strftime("%Y-%m-%d %H:%M"), args["gamerules"]))

				(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select id from games where end_datetime is null")
				(game_id,) = row
				db.execute(cherrypy.thread_data.conn,"insert into gameinfo(game_id, assassin_id) values(?,?)", (game_id, cherrypy.session.get("ProfileID")))

				#now email everyone
				(ret, players) = db.fetchAll(cherrypy.thread_data.conn,"select nickname, email_address from assassins where email_newgames=1")
				for Entry in players:
					(nickname, email) = Entry
					self.SendEmail(email, "%s:\nA new game is starting at %s. Login and join if you wish to play." % (nickname, LocalStartDate.strftime("%b %d, %Y %I:%M %p")))

		raise cherrypy.HTTPRedirect("/games")

	@cherrypy.expose
	def games(self, **args):
		(ret, rows) = db.fetchAll(cherrypy.thread_data.conn,"select g.id, g.start_datetime [timestamp], g.end_datetime [timestamp], r.rules from games g left join rules r on g.rule_id=r.id order by g.start_datetime desc")

		GameHTML = open("static/games.html", "r").read()
		GameHTML = html.HTMLCheckLoggedIn(self.ValidateLogin(), GameHTML)

		ProfileID = cherrypy.session.get("ProfileID")
		if(ProfileID == None):
			ProfileID = 0
			GameHTML = html.HTMLRemoveSection(self.ValidateLogin(), "joingame", GameHTML)
			GameHTML = html.HTMLRemoveSection(self.ValidateLogin(), "newgame", GameHTML)
			GameHTML = html.HTMLRemoveSection(self.ValidateLogin(), "creategame", GameHTML)

		#the very first row is the latest game
		if(len(rows) == 0):
			#no games, fake some data so we will still create the labels as needed
			start_datetime = datetime.datetime(2000,1,1)
			end_datetime = start_datetime
		else:
			(gameid, start_datetime, end_datetime, rules) = rows[0]

		if(start_datetime > datetime.datetime.utcnow()):
			#convert back to our timezone
			curtime = datetime.datetime.utcnow() - datetime.datetime.now()
			start_datetime = start_datetime - curtime

			CounterData = [{"year":start_datetime.year, "month":start_datetime.month-1, "day":start_datetime.day, "hour":start_datetime.hour, "minute":start_datetime.minute, "serveryear":curtime.year, "servermonth":curtime.month-1,"serverday":curtime.day, "serverhour":curtime.hour, "serverminute":curtime.minute}]
			GameHTML = html.HTMLReplaceSection(self.ValidateLogin(), "counter", GameHTML, CounterData)

			if(ProfileID != 0):
				#if we have a status update, do it here as it is allowed
				if("status" in args):
					if args["status"] == "join":
						#asking to join, make sure that a profile picture and full name exists
						(ret, joincheck) = db.fetchOne(cherrypy.thread_data.conn,"select picture_filename, firstname, lastname from assassins where id=? and (firstname is Null or lastname is Null or picture_filename is Null or firstname='' or lastname='')", (ProfileID,))
						if(joincheck != None and len(joincheck) != 0):
							return html.display_message(self.ValidateLogin(), "You can not join a game until your full first and last name is filled in and a face picture is provided")

						db.execute(cherrypy.thread_data.conn,"insert into gameinfo(game_id, assassin_id) values(?,?)", (gameid, ProfileID))
					elif args["status"] == "leave":
						db.execute(cherrypy.thread_data.conn,"delete from gameinfo where game_id=? and assassin_id=?", (gameid, ProfileID))

				(ret, ingame) = db.fetchOne(cherrypy.thread_data.conn,"select id from gameinfo where game_id=? and assassin_id=?", (gameid, ProfileID))
				if(ingame != None and len(ingame) != 0):
					GameHTML = html.HTMLReplaceSection(self.ValidateLogin(), "joingame", GameHTML, [{"url":"games?status=leave","text":"Leave Game","id":""}])
				else:
					GameHTML = html.HTMLReplaceSection(self.ValidateLogin(), "joingame", GameHTML, [{"url":"games?status=join","text":"Join Game","id":""}])

				GameHTML = html.HTMLRemoveSection(self.ValidateLogin(), "newgame", GameHTML)
				GameHTML = html.HTMLRemoveSection(self.ValidateLogin(), "creategame", GameHTML)
		else:
			GameHTML = html.HTMLRemoveSection(self.ValidateLogin(), "counter", GameHTML)
			if(ProfileID != 0):
				if(end_datetime == None):
					GameHTML = html.HTMLRemoveSection(self.ValidateLogin(), "joingame", GameHTML)
					GameHTML = html.HTMLRemoveSection(self.ValidateLogin(), "newgame", GameHTML)
					GameHTML = html.HTMLRemoveSection(self.ValidateLogin(), "creategame", GameHTML)
				else:
					GameHTML = html.HTMLReplaceSection(self.ValidateLogin(), "joingame", GameHTML, [{"url":"#newgame", "text":"Start Game","id":"newgame-link"}])
					GameHTML = html.HTMLReplaceSection(self.ValidateLogin(), "newgame", GameHTML, [{"d":"d"}])

					#fill in data to allow a new game
					GameData = []
					dictEntry = dict()
					NewDate = datetime.datetime.now() + datetime.timedelta(3,60*60)
					dictEntry["startdate"] = NewDate.strftime("%m/%d/%Y")
					dictEntry["starttime"] = NewDate.strftime("%I:00 %p")
					dictEntry["SubSection"] = []

					#setup the rules
					RuleNames = []
					RuleData = []
					(ret, rulerows) = db.fetchAll(cherrypy.thread_data.conn,"select id, rulename, rules from rules order by rulename")
					for Entry in rulerows:
						NewEntry = dict()
						NewDataEntry = dict()
						(NewEntry["id"], NewEntry["name"], NewDataEntry["rules"]) = Entry
						NewDataEntry["rules"] = NewDataEntry["rules"].replace("\r","")
						NewDataEntry["rules"] = NewDataEntry["rules"].replace("\n","\\n")
						RuleNames.append(NewEntry)
						RuleData.append(NewDataEntry)

					dictEntry["SubSection"].append(("rulelist", RuleNames))
					dictEntry["SubSection"].append(("ruledata", RuleData))

					if(len(RuleData) != 0):
						dictEntry["firstindex"] = 1;
					else:
						dictEntry["firstindex"] = 0;

					GameData.append(dictEntry)
					
					GameHTML = html.HTMLReplaceSection(self.ValidateLogin(), "creategame", GameHTML, GameData)

		#if the game hasn't ended then display info about it
		if(end_datetime == None):
			rows.pop(0)

			#fill in the current game
			StatData = []
			dictEntry = dict()

			dictEntry["game_start"] = start_datetime.strftime("%b %d, %Y")
			if(rules != None):
				dictEntry["rules"] = rules.replace("\n","<br>")
			else:
				dictEntry["rules"] = ""

			#see if anyone is assigned yet as target should have a value and are either still alive or last one standing has no killer and is ranked already
			(ret, players) = db.fetchAll(cherrypy.thread_data.conn,"select distinct a.id from assassins a, gameinfo gi where gi.game_id=? and gi.target_id=a.id and ((gi.killer_id is null) or (gi.killer_id = 0 and gi.ranking = 1))", (gameid,))
			if(len(players) == 0):
				#possible that no one is assigned yet, get those that are about to play
				(ret, players) = db.fetchAll(cherrypy.thread_data.conn,"select distinct a.id from assassins a, gameinfo gi where gi.game_id=? and gi.assassin_id=a.id", (gameid,))

			dictEntry["SubSection"] = []
			SubSection = []
			AlivePlayers = []

			#set a flag as we remove the current profile from AlivePlayers so the player can see their kills
			if(players == None or len(players) == 0):
				HavePlayers = 0
			else:
				HavePlayers = 1

			for Entry in players:
				(player_id,) = Entry
				SubSection.append({"name":"Assassin"})
				if(player_id != ProfileID):
					AlivePlayers.append(player_id)
			dictEntry["SubSection"].append(("winner", SubSection))

			(ret, players) = db.fetchAll(cherrypy.thread_data.conn,"select gi.kill_datetime [timestamp], a.id, a.firstname, a.lastname, a.nickname, b.id, b.firstname, b.lastname, b.nickname, gi.ranking from assassins a, assassins b, gameinfo gi where gi.target_id=a.id and gi.killer_id=b.id and gi.game_id=? and gi.killer_id != 0 and gi.kill_datetime is not null order by gi.ranking asc", (gameid,))
			SubSection = []
			if(len(players) == 0 and HavePlayers == 0):
				SubSection.append({"kill_date":"","profile_id":"","name":"","killer_name":"","killer_profile_id":"","rank":""})
			else:
				for Entry in players:
					NewEntry = dict()
					(NewEntry["kill_date"], NewEntry["profile_id"], firstname, lastname, nickname, NewEntry["killer_profile_id"], killer_fname, killer_lname, killer_nname, ranking) = Entry
					NewEntry["name"] = str(firstname) + " " + str(lastname) + " (" + str(nickname) + ")"
					if(NewEntry["killer_profile_id"] in AlivePlayers):
						NewEntry["killer_profile_id"] = 0
						NewEntry["killer_name"] = "Assassin"
					else:
						NewEntry["killer_name"] = str(killer_fname) + " " + str(killer_lname) + " (" + str(killer_nname) + ")"
					NewEntry["rank"] = html.ordinal(ranking)
					NewEntry["kill_date"] = NewEntry["kill_date"].strftime("%b %d, %Y %H:%M")
					SubSection.append(NewEntry)
			dictEntry["SubSection"].append(("players", SubSection))

			StatData.append(dictEntry)
			GameHTML = html.HTMLReplaceSection(self.ValidateLogin(), "latest_game", GameHTML, StatData)

		else:
			GameHTML = html.HTMLRemoveSection(self.ValidateLogin(), "latest_game", GameHTML)

		#if no games, remove the game block
		if(len(rows) == 0):
			return html.HTMLRemoveSection(self.ValidateLogin(), "games", GameHTML)

		StatData = []
		for Entry in rows:
			(gameid, start_datetime, end_datetime, rules) = Entry
			dictEntry = dict()
			if(rules != None):
				dictEntry["rules"] = rules.replace("\n", "<br>")
			else:
				dictEntry["rules"] = ""

			dictEntry["game_start"] = start_datetime.strftime("%b %d, %Y")
			if(end_datetime != None):
				dictEntry["game_end"] = end_datetime.strftime("%b %d, %Y")
			else:
				dictEntry["game_end"] = ""

			(ret, players) = db.fetchAll(cherrypy.thread_data.conn,"select a.id, a.firstname, a.lastname, a.nickname, a.smack, a.picture_filename, gi.ranking from assassins a, gameinfo gi where gi.target_id = a.id and gi.game_id=? and gi.ranking = 1 order by gi.ranking asc", (gameid,))
			dictEntry["SubSection"] = []
			SubSection = []
			if(len(players) == 0):
				SubSection.append({"kill_date":"","name":"","profile_id":"","profile_image":"","nickname":"","smack":"","rank":""})
			else:
				for Entry in players:
					NewEntry = dict()
					(NewEntry["profile_id"],firstname, lastname, nickname, NewEntry["smack"], NewEntry["profile_image"], ranking) = Entry
					NewEntry["kill_date"] = "Winner"
					NewEntry["name"] = str(firstname) + " " + str(lastname) + " (" + str(nickname) + ")"
					if(NewEntry["profile_image"] == None):
						NewEntry["profile_image"] = "images/bio-pic.jpg"
					else:
						NewEntry["profile_image"] = "profile-images/" + NewEntry["profile_image"]
					NewEntry["nickname"] = nickname
					NewEntry["rank"] = html.ordinal(ranking)
					SubSection.append(NewEntry)

			dictEntry["SubSection"].append(("winner", SubSection))
			(ret, players) = db.fetchAll(cherrypy.thread_data.conn,"select gi.kill_datetime [timestamp], a.id, a.firstname, a.lastname, a.nickname, b.id, b.firstname, b.lastname, b.nickname, gi.ranking from assassins a, assassins b, gameinfo gi where gi.target_id=a.id and gi.killer_id=b.id and gi.game_id=? and gi.killer_id != 0 order by gi.ranking asc", (gameid,))

			SubSection = []
			if(len(players) == 0):
				SubSection.append({"kill_date":"","profile_id":"","name":"","killer_name":"","killer_profile_id":"","rank":""})
			else:
				for Entry in players:
					NewEntry = dict()
					(NewEntry["kill_date"], NewEntry["profile_id"], firstname, lastname, nickname, NewEntry["killer_profile_id"], killer_fname, killer_lname, killer_nname, ranking) = Entry
					NewEntry["name"] = str(firstname) + " " + str(lastname) + " (" + str(nickname) + ")"
					NewEntry["killer_name"] = str(killer_fname) + " " + str(killer_lname) + " (" + str(killer_nname) + ")"
					NewEntry["rank"] = html.ordinal(ranking)
					NewEntry["kill_date"] = NewEntry["kill_date"].strftime("%b %d, %Y %H:%M")
					SubSection.append(NewEntry)
			dictEntry["SubSection"].append(("players", SubSection))
			StatData.append(dictEntry)

		return html.HTMLReplaceSection(self.ValidateLogin(), "games", GameHTML, StatData)

	@cherrypy.expose
	def change_password(self, currentpassword="", newpassword="", confirmpassword=""):
		if(self.ValidateLogin()):
			if(cherrypy.session["Password"] == currentpassword):
				if(newpassword == confirmpassword):
					passwordhash = bcrypt.hashpw(newpassword, bcrypt.gensalt())
					db.execute(cherrypy.thread_data.conn,"update assassins set password=? where id=?", (passwordhash, cherrypy.session["ProfileID"]))
					cherrypy.session["Password"] = newpassword
					return html.display_message(self.ValidateLogin(), "Password updated")
				else:
					return html.display_message(self.ValidateLogin(), "New and confim passwords do not match")
			else:
				return html.display_message(self.ValidateLogin(), "Current password does not match")
		else:
			return html.display_message(self.ValidateLogin(), "")

	@cherrypy.expose
	def update_profile(self, **args):
		if(self.ValidateLogin()):
			if "photo" in args:
				photo = args.pop("photo")
			else:
				photo = None
			args = db.sanitize(**args)

			if(photo == None or len(photo.filename) == 0):
				args["picture_filename"] = None
			else:
				if(photo.type in ["image/jpeg", "image/pjpeg"]):
					extension = ".jpg"
				elif(photo.type in ["image/png", "image/x-png"]):
					extension = ".png"
				else:
					return html.display_message(self.ValidateLogin(), "Invalid file format. Only JPEG and PNG are supported.")

				ProfileID = cherrypy.session["ProfileID"]

				#limit to 64k picture sizes
				PictureData = ""
				while(len(PictureData) < (64*1024)):
					NewData = photo.file.read(4096)
					PictureData = PictureData + NewData
					if(len(NewData) < 4096):
						break

				#if we can still get more data then error about the file being too large
				if(len(photo.file.read(4096))):
					return html.display_message(self.ValidateLogin(), "File size is larger than 64k.")

				#make sure no files exist for either extension
				if(os.path.isfile("profile-images/" + str(ProfileID) + ".jpg")):
					os.remove("profile-images/" + str(ProfileID) + ".jpg")

				if(os.path.isfile("profile-images/" + str(ProfileID) + ".png")):
					os.remove("profile-images/" + str(ProfileID) + ".png")

				args["picture_filename"] = str(ProfileID) + extension
				open("profile-images/" + args["picture_filename"], "w").write(PictureData)


			if("email_newgames" in args):
				if(args["email_newgames"] == "checked" or args["email_newgames"] == "on" or args["email_newgames"] == 1):
					args["email_newgames"] = 1;
				else:
					args["email_newgames"] = 0;
			else:
				args["email_newgames"] = 0;

			sql = "update assassins set "
			EntryList = ()
			for Entry in ["smack","nickname","firstname","lastname","email_address", "email_updates", "email_newgames"]:
				if Entry in args:
					sql = sql + Entry + "=?, "
					EntryList = EntryList + (args[Entry],)

			if(args["picture_filename"] != None):
				sql = sql + "picture_filename=?, "
				EntryList = EntryList + (args["picture_filename"],)

			if(len(EntryList)):
				sql = sql[:-2] + " where id=?"
				EntryList = EntryList + (cherrypy.session["ProfileID"],)
				if(db.execute(cherrypy.thread_data.conn,sql, EntryList)):
					raise cherrypy.HTTPRedirect("/profile")
				else:
					return html.display_message(self.ValidateLogin(), "Error updating profile")
			else:
				raise cherrypy.HTTPRedirect("/profile")
		else:
			return html.display_message(self.ValidateLogin(), "")

	@cherrypy.expose
	def profile(self, id=None):
		ProfileHTML = open("static/profile.html","r").read()
		ProfileHTML = html.HTMLCheckLoggedIn(self.ValidateLogin(), ProfileHTML)

		if(id == None):
			id = cherrypy.session.get("ProfileID")

		(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select nickname, firstname, lastname, email_address, ranking, smack, picture_filename, email_newgames from assassins where id=?", (id,))
		if(ret == False or row == None or len(row) == 0):
			return html.display_message(self.ValidateLogin(), "Error accessing profile")
		(nickname, firstname, lastname, email, ranking, smack, picture_filename, email_newgames) = row
		if(picture_filename == None):
			picture_filename = "images/bio-pic.jpg"
		else:
			picture_filename = "profile-images/" + picture_filename

		ranking = html.ordinal(ranking)

		if(email_newgames):
			email_newgames="checked"
		else:
			email_newgames=""

		if((cherrypy.session.get("ProfileID") == None) or (int(id) != int(cherrypy.session.get("ProfileID")))):
			ProfileHTML = html.HTMLRemoveSection(self.ValidateLogin(), "edit", ProfileHTML)
			ProfileHTML = html.HTMLRemoveSection(self.ValidateLogin(), "target_header", ProfileHTML)
			ProfileHTML = html.HTMLRemoveSection(self.ValidateLogin(), "target", ProfileHTML)
		else:
			(ret, reportrow) = db.fetchOne(cherrypy.thread_data.conn,"select gi.id from gameinfo gi, games g where gi.game_id=g.id and g.end_datetime is null and gi.target_id=? and gi.killer_id is null", (id,))
			EditDict = dict()
			EditDict["nickname"] = nickname
			EditDict["firstname"] = firstname
			EditDict["lastname"] = lastname
			EditDict["email"] = email
			EditDict["smacktalk"] = smack
			EditDict["email_newgames"] = email_newgames

			EditDict["SubSection"] = []
			if(reportrow == None or len(reportrow) == 0):
				EditDict["SubSection"].append(("report_kill", []))
			else:
				EditDict["SubSection"].append(("report_kill", [{"id":""}]))
			
			ProfileHTML = html.HTMLReplaceSection(self.ValidateLogin(), "edit", ProfileHTML, [EditDict])

			#see if we have a target
			(ret, rows) = db.fetchAll(cherrypy.thread_data.conn,"select a.firstname, a.lastname, a.nickname, a.picture_filename, gi.killer_id, gi.target_id, ifnull(gi.kill_datetime, datetime('now')) as killdatetime from assassins a, gameinfo gi, games g where g.end_datetime is null and gi.game_id = g.id and gi.assassin_id=? and a.id=gi.target_id order by killdatetime desc", (id,))
			if(len(rows) == 0):
				ProfileHTML = html.HTMLRemoveSection(self.ValidateLogin(), "target", ProfileHTML)
				ProfileHTML = html.HTMLRemoveSection(self.ValidateLogin(), "target_header", ProfileHTML)
			else:
				ProfileHTML = html.HTMLReplaceSection(self.ValidateLogin(), "target_header", ProfileHTML, [{"id":""}])

				targets = []
				for Entry in rows:
					NewTarget = dict()
					(NewTarget["firstname"], NewTarget["lastname"], NewTarget["nickname"], NewTarget["target_pic"], killer_id, target_id, kill_datetime) = Entry
					if(NewTarget["target_pic"] == None):
						NewTarget["target_pic"] = "images/bio-pic.jpg"
					else:
						NewTarget["target_pic"] = "profile-images/" + NewTarget["target_pic"]

					NewTarget["SubSection"] = []
					if(killer_id == None):
						NewTarget["SubSection"].append(("kill_target", [{"id":target_id}]))
						NewTarget["SubSection"].append(("target_killed", []))
					elif(killer_id == id):
						#report if we killed them
						NewTarget["SubSection"].append(("kill_target", []))
						NewTarget["SubSection"].append(("target_killed", [{"notice":"Target Assassinated"}]))
					elif(killer_id == 0):
						#report if they survived our encounter
						NewTarget["SubSection"].append(("kill_target", []))
						NewTarget["SubSection"].append(("target_killed", [{"notice":"Target Survived"}]))
					else:
						#someone else killed them
						NewTarget["SubSection"].append(("kill_target", []))
						NewTarget["SubSection"].append(("target_killed", [{"notice":"Target Assassinated by Another Assassin"}]))
						

					if(killer_id == None):
						targets.insert(0, NewTarget)
					else:
						targets.append(NewTarget)

				ProfileHTML = html.HTMLReplaceSection(self.ValidateLogin(), "target", ProfileHTML, targets)

		(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select count(killer_id) from gameinfo where killer_id=?", (id,))
		if(ret == False or row == None or len(row) == 0):
			return html.display_message(self.ValidateLogin(), "Error getting kill list")
		(total_assassinations,) = row

                (ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select count(target_id) from gameinfo where target_id=? and killer_id != 0", (id,))
		if(ret == False or row == None or len(row) == 0):
                        return html.display_message(self.ValidateLogin(), "Error getting death list")
                (total_deaths,) = row

		ProfileHTML = html.HTMLReplaceSection(self.ValidateLogin(), "profile", ProfileHTML, [{"nickname":nickname, "firstname":firstname, "lastname":lastname, "email":email, "rank":ranking, "smacktalk":smack, "total_assassinations":total_assassinations, "total_deaths":total_deaths, "profile_pic": picture_filename}])

		StatData = []

		sql = "select g.id, g.start_datetime [timestamp], g.end_datetime [timestamp], a.nickname, a.firstname, a.lastname, gi.killer_id, gi.ranking from games g, gameinfo gi left join assassins a on gi.killer_id=a.id where gi.game_id=g.id and gi.target_id=? and gi.ranking is not null"
		if(id != cherrypy.session.get("ProfileID")):
			sql = sql + " and g.end_datetime is not null"
		sql = sql + " order by g.id desc"
		(ret, rows) = db.fetchAll(cherrypy.thread_data.conn,sql, (id,))

		if(len(rows) == 0):
			ProfileHTML = html.HTMLRemoveSection(self.ValidateLogin(), "game", ProfileHTML)
		else:
			for Entry in rows:
				dictEntry = dict()
				(game_id, dictEntry["game_start"], dictEntry["game_end"], killer_nickname, killer_firstname, killer_lastname, killer_id, ranking) = Entry
				dictEntry["game_start"] = dictEntry["game_start"].strftime("%b %d, %Y")
				if(dictEntry["game_end"] != None):
					dictEntry["game_end"] = dictEntry["game_end"].strftime("%b %d, %Y")
				dictEntry["rank"] = html.ordinal(ranking)
				if(killer_id == None or killer_id == 0):
					dictEntry["assassinated_by"] = ""
				else:
					dictEntry["assassinated_by"] = str(killer_firstname) + " " + str(killer_lastname) + " (" + str(killer_nickname) + ")"		

				(ret, subrows) = db.fetchAll(cherrypy.thread_data.conn,"select a.nickname, a.firstname, a.lastname, gi.kill_datetime [timestamp], a.id from assassins a, gameinfo gi where gi.killer_id=? and gi.game_id=? and a.id=gi.target_id order by gi.kill_datetime asc", (id, game_id))
				dictEntry["total_assassinations"] = len(subrows)
				dictEntry["SubSection"] = []
				SubSection = []
				if(len(subrows) == 0):
					SubSection.append({"kill_date":"", "rank":"", "name":"", "profile_id":""})
				else:
					for SubEntry in subrows:
						NewEntry = dict()
						(killed_nickname, killed_firstname, killed_lastname, NewEntry["kill_date"], NewEntry["profile_id"]) = SubEntry
						NewEntry["rank"] = html.ordinal(0)
						NewEntry["name"] = str(killed_firstname) + " " + str(killed_lastname) + " (" + str(killed_nickname) + ")"
						NewEntry["kill_date"] = NewEntry["kill_date"].strftime("%b %d, %Y %H:%M")
						SubSection.append(NewEntry)
				dictEntry["SubSection"].append(("game_player", SubSection))

				StatData.append(dictEntry)

			ProfileHTML = html.HTMLReplaceSection(self.ValidateLogin(), "game", ProfileHTML, StatData)

		return ProfileHTML

	def register_complete(self, register_message, return_url="register.html"):
		return open("static/register-complete.html","r").read().format(message=register_message, back=return_url)

	@cherrypy.expose
	def login(self, nickname=None, password=None, login=None):
		cherrypy.session.load()
		if(self.ValidateLogin(nickname, password)):
			#if a hash is stored, confirm the kill for it
			if cherrypy.session.has_key("confirm_hash"):
				return self.confirm_kill()
			
			return self.profile()
		else:
			return self.register_complete("Invalid login", "login.html")

	@cherrypy.expose
	def register(self, nickname="", email_reg="", **args):
		if (nickname == "" or nickname == "Nickname"):
			return self.register_complete("Username is empty")
		if (email_reg == "") or (email_reg == "E-Mail Address") or (email_reg.lower()[-7:] != "@si.lan"):
			return self.register_complete("Email address is invalid, must be @si.lan")

		SanitizeValues = dict()
		SanitizeValues["nickname"] = nickname
		SanitizeValues["email_reg"] = email_reg
		SanitizeValues = db.sanitize(**SanitizeValues)
		nickname = SanitizeValues["nickname"]
		email_reg = SanitizeValues["email_reg"]

		(ret, row) = db.fetchOne(cherrypy.thread_data.conn,'SELECT id FROM assassins WHERE lower(nickname)=?', (nickname.lower(),))
		if row != None and len(row) != 0:
			return self.register_complete("Nickname already in use")

		(ret, row) = db.fetchOne(cherrypy.thread_data.conn,'SELECT id FROM assassins WHERE email_address=?', (email_reg.lower(),))
		if row != None and len(row) != 0:
			return self.register_complete("Email address already in use")

		password = ''.join([random.choice(string.letters + string.digits) for i in range(8)])
		passwordhash = bcrypt.hashpw(password, bcrypt.gensalt())
		try:
			db.execute(cherrypy.thread_data.conn,"insert into Assassins(nickname, email_address, password) values(?, ?, ?)", (nickname, email_reg.lower(), passwordhash))
			self.SendEmail(email_reg.lower(), "Welcome to Nerf Assassin.\r\nYour nickname is: %s\r\nYour password is: %s\r\n\r\nPasswords are case sensitive\r\n" % (nickname, password))
			return self.register_complete("New assassin created, email sent to %s" % (email_reg), "")
		except Exception, ex:
			return self.register_complete("Error creating a new assassin")

	@cherrypy.expose
	def showpics(self):
		HTML = open("static/pictures.html","r").read()
		HTML = html.HTMLCheckLoggedIn(self.ValidateLogin(), HTML)

		(ret, rows) = db.fetchAll(cherrypy.thread_data.conn,"select firstname, lastname, picture_filename, id from assassins where picture_filename is not null order by firstname, lastname")
		Pictures = []
		for Entry in rows:
			PicEntry = dict()
			(PicEntry["firstname"], PicEntry["lastname"], PicEntry["picture"], PicEntry["id"]) = Entry
			Pictures.append(PicEntry)

		return html.HTMLReplaceSection(self.ValidateLogin(), "picture", HTML, Pictures)

	@cherrypy.expose
	def invalidpic(self, id):
		if(self.ValidateLogin() and cherrypy.session.get("ProfileID") == 1):
			(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select nickname, email_address, picture_filename from assassins where picture_filename is not null and id=?", (id,))
			(nickname, email, picture) = row
			if(picture == None):
				return html.display_message(self.ValidateLogin(), "No picture found")

			db.execute(cherrypy.thread_data.conn,"Update assassins set picture_filename=Null where id=?", (id,))
			(ret, row) = db.fetchOne(cherrypy.thread_data.conn,"select id from games where end_datetime is null")
			if(row != None and len(row) != 0):
				(gameid,) = row
				db.execute(cherrypy.thread_data.conn,"delete from gameinfo where assassin_id=? and target_id=Null and game_id=?", (id, gameid))

			os.remove("profile-images/" + picture)
			self.SendEmail(email, "Your picture was invalid and removed. If you were part of a game then you have been removed from the game for an invalid profile picture")

			return html.display_message(self.ValidateLogin(), "Picture removed and email sent")

		else:
			return html.display_message(self.ValidateLogin(), "No access")	

	@cherrypy.expose
	def config(self, **params):

		HTML = """
		<html>
		<body>
		<center>Config for Nerf Assassin</center>
		"""
		HTMLFoot = """
		</body>
		</html>
		"""

		password = ""
		if("password" in params):
			password = params.pop("password")

		HTMLData = "<form action='config' method='POST'><table border=0>"
		Hash = ""
		if(bcrypt.hashpw(password, Hash) == Hash):
			if len(params):
				for Entry in params:
					db.execute(cherrypy.thread_data.conn,"Update config set value = ? where name = ?", (params[Entry], Entry));
				HTMLData = HTMLData + "<center>Config updated</center><br>"

			(ret, Config) = db.fetchAll(cherrypy.thread_data.conn,"Select name, value from config")
			for (conf_name, conf_value) in Config:
				HTMLData = HTMLData + "<tr><td>" + conf_name + "</td><td><input name=" + conf_name + " value='" + conf_value + "'></td></tr>"
			HTMLData = HTMLData + "<tr><td height=20>----------------------</td></tr>"

		HTMLData = HTMLData + """
					<tr>
						<td>Password:</td>
						<td><input type='password' name='password'></td>
					</tr>
					<tr>
						<td colspan=2 align=left><input type='submit' value="Submit"></td>
					</tr>
				</table>
			</form>
			"""

		return HTML + HTMLData + HTMLFoot

	@cherrypy.expose
	def stop(self, Message=""):
		sys.exit()

	@cherrypy.expose
	def index(self):
		return open("index.html","r").read()

def handle_errors():
	cherrypy.response.status=500
	cherrypy.response.body = ['<html><body>An error occurred</body></html>']

def error_page(status, message, traceback, version):
	return "<html><body>An error occurred</body></html>"

def make_connect(thread_index):
	cherrypy.thread_data.conn = db.make_connect()

current_dir = os.path.dirname(os.path.abspath(__file__))
config = {
	'/':
	{
	        'tools.trailing_slash.on': False,
		'tools.sessions.on': True,
		'tools.sessions.storage_type': 'ram',
		'tools.sessions.timeout': 60,
		'tools.sessions.name': 'NerfAssassin',
		'tools.staticdir.root': os.path.join(current_dir, "static")
	},
	'/css':
	{
		'tools.staticdir.on': True,
		'tools.staticdir.dir': "css"
	},
	'/js':
	{
		'tools.staticdir.on': True,
		'tools.staticdir.dir': "js"
	},
	'/images':
	{
		'tools.staticdir.on': True,
		'tools.staticdir.dir': "images"
	},
	'/login.html':
	{
		'tools.staticfile.on': True,
		'tools.staticfile.filename': os.path.join(current_dir, "login.html")
	},
	'/register.html':
	{
		'tools.staticfile.on': True,
		'tools.staticfile.filename': os.path.join(current_dir, "register.html")
	},
	'/favicon.ico':
	{
		'tools.staticfile.on': True,
		'tools.staticfile.filename': os.path.join(current_dir, "favicon.ico")
	},
	'/profile-images':
	{
		'tools.staticdir.on': True,
		'tools.staticdir.root': current_dir,
		'tools.staticdir.dir': "profile-images"
	}
}
cherrypy.tree.mount(NerfAssassin(), "/", config=config)

cherrypy.config.update({
		'request.error_response': handle_errors,
		'error_page.default': error_page,
		'server.socket_host': '127.0.0.1',
		'server.socket_port': 8080})

cherrypy.engine.subscribe('start_thread',make_connect)
cherrypy.server.start()
