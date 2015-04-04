import sys
import sqlite3

class ConfigVals:
	def __init__(self, Val, Desc):
		self.Value = Val
		self.Description = Desc

def sanitize(**params):
	for Entry in params:
		if(type(params[Entry]) is str):
			params[Entry] = params[Entry].replace("<","&lt;")
			params[Entry] = params[Entry].replace(">","&gt;")
			params[Entry] = params[Entry].replace("'","&#039;")
			params[Entry] = params[Entry].replace("\"","&quot;")
			params[Entry] = params[Entry].replace("{","&#123;")
			params[Entry] = params[Entry].replace("}","&#125;")
			params[Entry] = params[Entry].replace("[","&#091;")
			params[Entry] = params[Entry].replace("]","&#093;")
			params[Entry] = params[Entry].strip()
	return params

def fetchAll(conn, query, keys=None):
	ret = True
	results = dict()
	sys.stdout.flush()
	cur = conn.cursor()
	try:
		if(keys == None):
			cur.execute(query)
		else:
			cur.execute(query, keys)
		results = cur.fetchall()
	except Exception as e:
		sys.stdout.flush()
		ret = False

	if results is None:
		ret = False

	return (ret, results)

def fetchOne(conn, query, keys=None):
	ret = True
	results = dict()
	sys.stdout.flush()
	cur = conn.cursor()
	try:
		if(keys == None):
			cur.execute(query)
		else:
			cur.execute(query, keys)
		results = cur.fetchone()
	except Exception as e:
		sys.stdout.flush()
		ret = False

	if results is None:
		ret = False

	return (ret, results)

def execute(conn, query, *args):
	ret = True
	results = dict()
	cur = conn.cursor()
	row_count = 0
	try:
		cur.execute(query, *args)
		row_count = cur.rowcount
		conn.commit()
	except Exception as e:
		print "ERROR WITH QUERY '", query,"' : ", e
		sys.stdout.flush()

	return row_count

def GetConfig(conn, Entries):
	HasEntries = True
	if type(Entries) == list:
		ConfigNames = "'" + "','".join(Entries).lower() + "'"
	elif type(Entries) == type(None):
		HasEntries = False
	else:
		ConfigNames = "'%s'" % (Entries)
	ret = True
	results = dict()
	sys.stdout.flush()
	cur = conn.cursor()

	if HasEntries:
		query = "select name, value, description from config where name in (" + ConfigNames + ")"
	else:
		#no entries specified, get all of them
		query = "select name, value, description from config"

	cur.execute(query)
	results = cur.fetchall()

	#return a dictionary of entries if a number of them were requested
	#otherwise just return the one entry
	if type(Entries) in (type(None), list):
		ConfigResult = dict()
		for i in xrange(0, len(results)):
			ConfigResult[results[i][0]] = ConfigVals(results[i][1], results[i][2])
	else:
		ConfigResult = ConfigVals(results[0][1], results[0][2])

	return ConfigResult

def make_connect():
	print "Making a new database connection"
	return sqlite3.connect('nerf-assassin.db', detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)

