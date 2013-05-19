def HTMLReplaceSection(LoggedIn, SectionName, HTMLData, Params):
	HTMLStart = HTMLData.find("[" + SectionName + "_begin]")
	HTMLEnd = HTMLData.find("[" + SectionName + "_end]", HTMLStart)
	if(HTMLStart == -1 or HTMLEnd == -1 or HTMLEnd < HTMLStart):
		return display_message(LoggedIn, "Error parsing section " + SectionName)

	HTMLEnd = HTMLEnd + len(SectionName) + 6

	#pull out the section then loop thru all entries filling them in
	HTMLSection = HTMLData[HTMLStart+8+len(SectionName):HTMLEnd-6-len(SectionName)]
	NewHTML = ""
	if(len(Params) == 0):
		NewHTML = HTMLSection
	else:
		for Entry in Params:
			TempHTML = HTMLSection

			#if there is a sub section, handle it first then update the rest of the current section
			if("SubSection" in Entry):
				TempHTML = HTMLSection
				for (SectionName, SectionParams) in Entry["SubSection"]:
					if(len(SectionParams) == 0):
						TempHTML = HTMLRemoveSection(LoggedIn, SectionName, TempHTML)
					else:
						TempHTML = HTMLReplaceSection(LoggedIn, SectionName, TempHTML, SectionParams)
				Entry.pop("SubSection")

			NewHTML = NewHTML + HTMLReplace(LoggedIn, TempHTML, **Entry)

	#now replace the section with the proper data and return it all
	return HTMLData[:HTMLStart] + NewHTML + HTMLData[HTMLEnd:]

def HTMLRemoveSection(LoggedIn, SectionName, HTMLData):
	HTMLStart = HTMLData.find("[" + SectionName + "_begin]")
	HTMLEnd = HTMLData.find("[" + SectionName + "_end]", HTMLStart)
	if(HTMLStart == -1 or HTMLEnd == -1 or HTMLEnd < HTMLStart):
		return display_message(LoggedIn, "Error removing section " + SectionName)

	HTMLEnd = HTMLEnd + len(SectionName) + 6

	#now chop the section out
	return HTMLData[:HTMLStart] + HTMLData[HTMLEnd:]

def HTMLReplace(LoggedIn, HTMLData, **Entries):
	for Entry in Entries:
		if(Entries[Entry] == None):
			Entries[Entry] = ""
		HTMLData = HTMLData.replace("{" + str(Entry) + "}", str(Entries[Entry]))
	return HTMLData

def HTMLCheckLoggedIn(LoggedIn, HTML):
	if(LoggedIn):
		HTML = HTMLReplaceSection(LoggedIn, "loggedin",HTML, [{"url":"/profile", "text":"View Profile","logout":"<a href=\"logout\">Logout</a>"}])
	else:
		HTML = HTMLReplaceSection(LoggedIn, "loggedin",HTML, [{"url":"/login.html", "text":"Login", "logout":""}])
	return HTML

def display_message(LoggedIn, message):
	return HTMLCheckLoggedIn(LoggedIn, HTMLReplace(open("static/message.html","r").read(), message=message))

def ordinal(num):
	if num == None or num == 0:
		return ""

	if num == 11 or num == 12 or num == 13:
		return str(num) + "th"
	elif(num % 10 == 1):
		return str(num) + "st"
	elif(num % 10 == 2):
		return str(num) + "nd"
	elif(num % 10 == 3):
		return str(num) + "rd"
	else:
		return str(num) + "th"

