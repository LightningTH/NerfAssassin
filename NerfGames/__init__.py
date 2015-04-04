import os, sys

#dictionary of game modules by name
_games = dict()

#dictionary of games by ID in the database
_gameids = dict()

_gamearray = []

_emptygame = None

for module in os.listdir(os.path.dirname(__file__)):
	if module == "__init__.py" or module[-3:] != ".py":
		continue

	try:
		temp = __import__(module[:-3], globals(), locals(),["NerfGame"], -1)
		if(module[:-3].lower() == 'empty'):
			_emptygame = temp
		else:
			_games[module[:-3].lower()] = temp.NerfGame
	except:
		continue

del module
del temp
del os
del sys

def InitGameIDs(db):
	(ret, rows) = db.fetchAll("select id, name from gametypes")

	MaxID = -1
	gamelist = dict(_games)
	for (game_id, gamename) in rows:
		if(game_id > MaxID):
			MaxID = game_id

		try:
			_gameids[game_id] = _games[gamename.lower()]
			_gamearray.append((game_id, gamename))
			gamelist.pop(gamename.lower())
		except:
			#found a game in the database but no longer physically exists, use our empty module so rest of the system doesn't fail
			_gameids[game_id] = _emptygame
			_games[gamename.lower()] = _emptygame
			_gamearray.append((game_id, gamename))


	#for any games not in the database, add them
	for gamename in gamelist:
		MaxID += 1
		db.execute("insert into gametypes (id, name) values(?, ?)", (MaxID, gamename))
		_gameids[MaxID] = _games[gamename.lower()]
		_gamearray.append((MaxID, gamename))
		
	return

def GetGameByID(ID):
	try:
		return _gameids[ID]()
	except:
		return None

def GetGameByName(name):
	try:
		return _games[name.lower()]()
	except:
		return None

def GetGameIDByName(name):
	for (game_id, gamename) in _gamearray:
		if(gamename.lower() == name.lower()):
			return game_id
	return -1

def GetGameNameByID(ID):
	for (game_id, gamename) in _gamearray:
		if(game_id == ID):
			return gamename
	return ""

