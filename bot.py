# See LICENSE for details.

from __future__ import print_function

# twisted imports
from twisted.words.protocols import irc
from twisted.internet import reactor, protocol
from twisted.python import log

# system imports
import time, sys, requests, re, urllib, math, traceback, slider, sqlite3  # sqlite for saving user prefs

try:
	import config, calc
except ImportError:
	print("No modules. Please redownload and make a config.py.")
	input()
	sys.exit()

userdb = sqlite3.connect('userpref.db')
cur = userdb.cursor()
userdb.execute("CREATE TABLE IF NOT EXISTS userdb (user int PRIMARY KEY, mode int)")
userdb.commit()

beatmap_data_s = {}
acm_data_s = {}
mod_data_s = {}
first_time = time.time()


class ModeError(Exception):
	pass


class MsgError(Exception):
	pass


class NpError(Exception):
	pass


class AttrError(Exception):
	pass


class TopPlayError(Exception):
	pass


class ComboError(Exception):
	pass


class ProgramLogic:
	"""An independent logic class (because separation of application and protocol logic is a good thing)."""

	def __init__(self, file):
		self.file = file
		self.repfile = open("reports.log", "a")
		self.UPDATE_MSG = "eyo, its boterino here with an update ([https://aeverr.s-ul.eu/CpdBefOU sic]). Added mod support (HD FL for catch, NF EZ for mania). Added Mania Gamemode support. Change mode with !set mode [catch|mania]. Suspect to bugs, please help me test"
		self.FIRST_TIME_MSG = "Welcome, and thanks for using my bot! Check out [https://github.com/de-odex/aEverrBot/wiki the wiki] for commands. !botreport to report a bug."

	def log(self, message):
		"""Write a message to the file."""
		print(message)
		timestamp = time.strftime("[%H:%M:%S]", time.localtime(time.time()))
		self.file.write('%s %s\n' % (timestamp, message))
		self.file.flush()

	def close(self):
		self.file.close()
		self.repfile.close()

	# my commands now :3

	def isfloat(self, value):
		try:
			float(value)
			return True
		except ValueError:
			return False

	def savetofile(self, msg, file):
		timestamp = time.strftime("[%H:%M:%S]", time.localtime(time.time()))
		file.write('%s %s\n' % (timestamp, msg))
		file.flush()
		pass

	def report(self, msg):
		self.savetofile(msg, self.repfile)

	# api ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	def get_b_data(self, api_key, beatmap_id, mode=None):
		# request for data
		if not mode:
			parameters = {
				"k": api_key,
				"b": beatmap_id,
				"a": 1  # allow converts
			}
		elif mode:
			parameters = {
				"k": api_key,
				"b": beatmap_id,
				"a": 1,  # allow converts
				"m": mode  # gamemode
			}
		osuresponse = requests.get("https://osu.ppy.sh/api/get_beatmaps", params=parameters)
		return osuresponse.json()

	def get_tu_data(self, api_key, user_id):  # unused
		# request for data
		parameters = {
			"k": api_key,
			"u": user_id,
			"m": 2,  # pick ctb game mode
			"limit": 25  # limit to number
		}
		osuresponse = requests.get("https://osu.ppy.sh/api/get_user_best", params=parameters)
		return osuresponse.json()

	def get_tb_data(self, api_key, beatmap_id):  # unused
		# request for data
		parameters = {
			"k": api_key,
			"b": beatmap_id,
			"m": 2,  # pick ctb game mode
			"limit": 100  # limit to number
		}
		osuresponse = requests.get("https://osu.ppy.sh/api/get_scores", params=parameters)
		return osuresponse.json()

	# calc ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	def calculatepp(self, osubdata, mode, beatmap=0, **kwargs):
		# kwarg setting

		acc = kwargs.get('acc', 100)
		max_player_combo = kwargs.get('max_player_combo', 0)
		miss = kwargs.get('miss', 0)
		score = kwargs.get('score', 1000000)
		mods = kwargs.get('mods', 0)
		# pp returning
		if mode == 2:
			r = calc.CatchTheBeat()
			return r.calculatepp(acc=acc, max_player_combo=max_player_combo, miss=miss, mods=mods, osubdata=osubdata)
		elif mode == 3:
			r = calc.Mania()
			return r.calculatepp(acc=acc, score=score, mods=mods, osubdata=osubdata, beatmap=beatmap)

	# message sending ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	def sendstore(self, message, name, file1):
		temp = open(file1, "a")										# if file doesn't exist, make it
		temp.close()												# close file
		names_file = open(file1, "r")								# read file data
		all_names = names_file.read().splitlines()					# split to lines
		names_file.close()											# close reading, for writing
		if name not in all_names:
			names_file = open(file1, "a+")							# write file data
			names_file.write(name + "\n")							# write file data
			names_file.close()										# close file for resources
			return message
		else:
			return False

	def setpref(self, message, name):
		global userdb, cur
		split_msg = message.split()

		if split_msg[0] == "mode":
			if split_msg[1] == "catch":
				mode = 2
			elif split_msg[1] == "mania":
				mode = 3
			else:
				return "Invalid command"

			cur.execute("SELECT * FROM userdb WHERE user=?", (name,))
			if cur.fetchone() is None:
				userdb.execute("INSERT INTO userdb (user, mode) VALUES (?,?)", (name, mode))
				userdb.commit()
			else:
				userdb.execute("UPDATE userdb set mode = ? where user = ?", (mode, name))
				userdb.commit()
			return "Set <" + split_msg[0] + "> to <" + split_msg[1] + ">"
		else:
			return "Invalid command"

	def sendpp(self, message, name, ident="np"):
		global beatmap_data_s, mod_data_s, userdb, cur
		try:
			# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			if ident == "np":
				link = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', message)
				mod_data_s[name] = 0
				acm_data_s[name] = 0
				beatmap_id = urllib.parse.urlparse(link[0]).path.split("/")[2]
				if urllib.parse.urlparse(link[0]).path.split("/")[1] != "b":
					return "This is a beatmapset, not a beatmap"
				beatmap_data = self.get_b_data(config.api_key, beatmap_id)
				if not beatmap_data:
					raise ModeError

				# mode checking
				if beatmap_data[0]["mode"] != "0":
					mode = int(beatmap_data[0]["mode"])
					
				else:
					cur.execute("SELECT * FROM userdb WHERE user=?", (name,))
					modedb = cur.fetchone()
					if modedb is None:
						return "Please set a mode with !set mode [catch|mania]"
					else:
						cur.execute("SELECT mode FROM userdb WHERE user=?", (name,))
						mode = modedb[1]
				beatmap_data[0] = self.get_b_data(config.api_key, beatmap_data[0]["beatmap_id"], mode)[0]
				beatmap_data_s[name] = beatmap_data

				if mode == 2:
					artist_name = beatmap_data[0]["artist"] + " - " + beatmap_data[0]["title"] + " [" + beatmap_data[0]["version"] + "]"
					pp_vals = (str(self.calculatepp(beatmap_data[0], mode)), str(self.calculatepp(beatmap_data[0], mode, acc=99.5)), str(self.calculatepp(beatmap_data[0], mode, acc=99)), str(self.calculatepp(beatmap_data[0], mode, acc=98.5)))
					end_props = str(round(float(beatmap_data[0]["difficultyrating"]), 2)) + "* " + time.strftime("%M:%S", time.gmtime(int(beatmap_data[0]["total_length"]))) + " AR" + str(beatmap_data[0]["diff_approach"]) + " MAX" + str(beatmap_data[0]["max_combo"])
					sent = artist_name + " | osu!catch | SS: " + pp_vals[0] + "pp | 99.5% FC: " + pp_vals[1] + "pp | 99% FC: " + pp_vals[2] + "pp | 98.5% FC: " + pp_vals[3] + "pp | " + end_props
				elif mode == 3:
				
					# Check whether the map is converted or not
					# If the map is converted, take the keyamount from OD, else, take from CS
					od = int(str(beatmap_data[0]["diff_overall"]))
					if beatmap_data[0]["mode"] != "0":
						keyamount = str(beatmap_data[0]["diff_size"])
					else:
						if od <= 4:
							keyamount = str(4)
						if od > 4 and od < 7:
							keyamount = str(od)
						if od >= 7:
							keyamount = str(7)
						
					l = slider.library.Library("/osulib")
					beatmap = l.download(beatmap_id=int(beatmap_data[0]["beatmap_id"]))

					artist_name = beatmap_data[0]["artist"] + " - " + beatmap_data[0]["title"] + " [" + beatmap_data[0]["version"] + "]"
					pp_vals = (str(self.calculatepp(beatmap_data[0], beatmap=beatmap, mode=mode)), str(self.calculatepp(beatmap_data[0], beatmap=beatmap, mode=mode, acc=99, score=970000)), str(self.calculatepp(beatmap_data[0], beatmap=beatmap, mode=mode, acc=97, score=900000)))
					end_props = str(round(float(beatmap_data[0]["difficultyrating"]), 2)) + "* " + time.strftime("%M:%S", time.gmtime(int(beatmap_data[0]["total_length"]))) + " OD" + str(beatmap_data[0]["diff_overall"]) + " " + keyamount + "key OBJ" + str(len(beatmap.hit_objects))
					sent = artist_name + " | osu!mania | SS: " + pp_vals[0] + "pp | 99% 970k: " + pp_vals[1] + "pp | 97% 900k: " + pp_vals[2] + "pp | " + end_props
			# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			elif ident == "acm":
				mods_name = ""
				if name not in beatmap_data_s:
					raise NpError
				if name not in mod_data_s:
					mods = 0
				else:
					mods = mod_data_s[name]

				beatmap_data = beatmap_data_s[name]

				split_msg = message.split()
				del split_msg[0]
				if not split_msg:
					raise MsgError
				acc = 'hi'
				combo = 'hi'
				miss = 'hi'
				score = 'hi'
				for i in split_msg:
					if self.isfloat(i):
						acc = i
					elif i.endswith(("x", )):
						combo = i.rstrip("x")
					elif i.endswith(("m", )):
						miss = i.rstrip("m")
					elif i.endswith(("s", )):
						score = i.rstrip("s")
					else:
						pass

				if acc == 'hi' and combo == 'hi' and miss == 'hi' and score == 'hi':
					raise AttrError

				if mods & 1 == 1:
					mods_name += "NF"
				if mods & 2 == 2:
					mods_name += "EZ"
				if mods & 8 == 8:
					mods_name += "HD"
				if mods & 1024 == 1024:
					mods_name += "FL"
				if mods == 0:
					return "These mods are not supported yet!"

				# Attribute testing
				cur.execute("SELECT * FROM userdb WHERE user=?", (name,))
				modedb = cur.fetchone()
				if modedb is None:
					return "Please set a mode with !set mode [catch|mania]"
				else:
					cur.execute("SELECT mode FROM userdb WHERE user=?", (name,))
					mode = modedb[1]

				# mode checking
				if beatmap_data[0]["mode"] != "0":
					mode = int(beatmap_data[0]["mode"])
				beatmap_data[0] = self.get_b_data(config.api_key, beatmap_data[0]["beatmap_id"], mode)[0]

				max_combo = int(beatmap_data[0]["max_combo"]) if beatmap_data[0]["max_combo"] is not None else "err"
				artist_name = beatmap_data[0]["artist"] + " - " + beatmap_data[0]["title"] + " [" + beatmap_data[0]["version"] + "]"
				l = slider.library.Library("/osulib")
				beatmap = l.download(beatmap_id=int(beatmap_data[0]["beatmap_id"]))

				if mode == 2:
					try:
						miss = int(miss)
						if miss < max_combo or miss >= 0:
							miss = miss
						else:
							raise SyntaxError
					except:
						return "You MISSed something there"
					try:
						combo = int(combo)
						if combo <= max_combo and combo > 0:
							combo = combo
						else:
							raise SyntaxError
					except:
						return "You made a mistake with your combo!"
					try:
						acc = float(acc)
						if acc >= 0 and acc <= 100:
							acc = acc
						else:
							raise SyntaxError
					except:
						return "Check your accuracy again, please"

					acm_data_s[name] = [acc, combo, miss]
					pp_vals = (str(self.calculatepp(beatmap_data[0], mode, acc=acc, combo=combo, miss=miss, mods=mods)), )
					acccombomiss = str(acc) + "% " + str(combo) + "x " + str(miss) + "miss " + mods_name
					end_props = str(round(float(beatmap_data[0]["difficultyrating"]), 2)) + "* " + time.strftime("%M:%S", time.gmtime(int(beatmap_data[0]["total_length"]))) + " AR" + str(beatmap_data[0]["diff_approach"]) + " MAX" + str(beatmap_data[0]["max_combo"])
					sent = artist_name + " | osu!catch | " + acccombomiss + ": " + pp_vals[0] + "pp | " + end_props
				elif mode == 3:
					try:
						score = int(score)
						if score <= 1000000 and score >= 0:
							score = score
						else:
							raise SyntaxError
					except:
						return "You messed up your score there..."
					try:
						acc = float(acc)
						if acc >= 0 and acc <= 100:  # and acc <= float(((max_combo - miss) / max_combo) * 100)
							acc = acc
						else:
							raise SyntaxError
					except:
						return "Check your accuracy again, please"

					# Check whether the map is converted or not
					# If the map is converted, take the keyamount from OD, else, take from CS
					od = int(str(beatmap_data[0]["diff_overall"]))
					if beatmap_data[0]["mode"] != "0":
						keyamount = str(beatmap_data[0]["diff_size"])
					else:
						if od <= 4:
							keyamount = str(4)
						if od > 4 and od < 7:
							keyamount = str(od)
						if od >= 7:
							keyamount = str(7)
						
					acm_data_s[name] = [acc, score]
					pp_vals = (str(self.calculatepp(beatmap_data[0], beatmap=beatmap, mode=mode, acc=acc, score=score, mods=mods)), )
					accscore = str(acc) + "% " + str(score) + " " + mods_name
					end_props = str(round(float(beatmap_data[0]["difficultyrating"]), 2)) + "* " + time.strftime("%M:%S", time.gmtime(int(beatmap_data[0]["total_length"]))) + " OD" + str(beatmap_data[0]["diff_overall"]) + " " + keyamount + "key OBJ" + str(len(beatmap.hit_objects))
					sent = artist_name + " | osu!mania | " + accscore + ": " + pp_vals[0] + "pp | " + end_props
			# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			elif ident == "mod":
				mods_name = ""
				if name not in beatmap_data_s:
					raise NpError

				beatmap_data = beatmap_data_s[name]
				if name not in acm_data_s:
					pass
				else:
					acm_data = acm_data_s[name]
				mods = 0

				split_msg = message.split()
				del split_msg[0]
				if not split_msg:
					raise MsgError
				if split_msg[0].lower().find("hd") != -1:
					mods += 8
				if split_msg[0].lower().find("fl") != -1:
					mods += 1024
				if split_msg[0].lower().find("ez") != -1:
					mods += 2
				if split_msg[0].lower().find("nf") != -1:
					mods += 1

				if mods & 1 == 1:
					mods_name += "NF"
				if mods & 2 == 2:
					mods_name += "EZ"
				if mods & 8 == 8:
					mods_name += "HD"
				if mods & 1024 == 1024:
					mods_name += "FL"
				if mods == 0:
					return "These mods are not supported yet!"

				# Attribute testing
				cur.execute("SELECT * FROM userdb WHERE user=?", (name,))
				modedb = cur.fetchone()
				if modedb is None:
					return "Please set a mode with !set mode [catch|mania]"
				else:
					cur.execute("SELECT mode FROM userdb WHERE user=?", (name,))
					mode = modedb[1]

				# mode checking
				if beatmap_data[0]["mode"] != "0":
					mode = int(beatmap_data[0]["mode"])
				beatmap_data[0] = self.get_b_data(config.api_key, beatmap_data[0]["beatmap_id"], mode)[0]

				max_combo = int(beatmap_data[0]["max_combo"]) if beatmap_data[0]["max_combo"] is not None else "err"
				artist_name = beatmap_data[0]["artist"] + " - " + beatmap_data[0]["title"] + " [" + beatmap_data[0]["version"] + "]"
				l = slider.library.Library("/osulib")
				beatmap = l.download(beatmap_id=int(beatmap_data[0]["beatmap_id"]))

				mod_data_s[name] = mods
				if mode == 2:
					if acm_data in locals():
						acc, combo, miss = acm_data
					else:
						acc, combo, miss = (100, beatmap_data[0]["max_combo"], 0)
					pp_vals = (str(self.calculatepp(beatmap_data[0], mode, acc=acc, combo=combo, miss=miss, mods=mods)), )
					acccombomiss = str(acc) + "% " + str(combo) + "x " + str(miss) + "miss " + mods_name
					end_props = str(round(float(beatmap_data[0]["difficultyrating"]), 2)) + "* " + time.strftime("%M:%S", time.gmtime(int(beatmap_data[0]["total_length"]))) + " AR" + str(beatmap_data[0]["diff_approach"]) + " MAX" + str(beatmap_data[0]["max_combo"])
					sent = artist_name + " | osu!catch | " + acccombomiss + ": " + pp_vals[0] + "pp | " + end_props
				elif mode == 3:
					if acm_data in locals():
						acc, score = acm_data
					else:
						acc, score = (100, 1000000)
						
					# Check whether the map is converted or not
					# If the map is converted, take the keyamount from OD, else, take from CS
					od = int(str(beatmap_data[0]["diff_overall"]))
					if beatmap_data[0]["mode"] != "0":
						keyamount = str(beatmap_data[0]["diff_size"])
					else:
						if od <= 4:
							keyamount = str(4)
						if od > 4 and od < 7:
							keyamount = str(od)
						if od >= 7:
							keyamount = str(7)
						
					pp_vals = (str(self.calculatepp(beatmap_data[0], beatmap=beatmap, mode=mode, acc=acc, score=score, mods=mods)), )
					accscore = str(acc) + "% " + str(score) + " " + mods_name
					end_props = str(round(float(beatmap_data[0]["difficultyrating"]), 2)) + "* " + time.strftime("%M:%S", time.gmtime(int(beatmap_data[0]["total_length"]))) + " OD" + str(beatmap_data[0]["diff_overall"]) + " " + keyamount + "key OBJ" + str(len(beatmap.hit_objects))
					sent = artist_name + " | osu!mania | " + accscore + ": " + pp_vals[0] + "pp | " + end_props
			# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
			return sent

		except IndexError:
			return "There seems to be no link in your /np... Is this a beatmap you made?"
		except ModeError:
			return "Something really bad went wrong, and I don't know what it is yet. Wait for my creator ^-^. Ident:ModeError"
		except MsgError:
			return "Somehow your message got lost in my head... Send it again?"
		except NpError:
			return "You haven't /np'd me anything yet!"
		except AttrError:
			return "Do it like me, \"!acc 95 200x 1m\". Or something, I dunno. Please recheck [https://github.com/de-odex/aEverrBot/wiki the wiki] for more details"
		except ComboError:
			return "Something's up, or I guess in this case, down, with your combo."
		except:
			traceback.print_exc(file=open("err.log", "a"))
			return "Something really bad went wrong, and I don't know what it is yet. Wait for my creator ^-^. Ident:" + ident


class Bot(irc.IRCClient):
	"""An IRC bot."""

	nickname = config.botnick
	password = config.password
	lineRate = 1
	heartbeatInterval = 64

	def connectionMade(self):
		irc.IRCClient.connectionMade(self)
		self.logic = ProgramLogic(open(self.factory.filename, "a"))
		self.logic.log("[connected at %s]" % time.asctime(time.localtime(time.time())))

	def connectionLost(self, reason):
		irc.IRCClient.connectionLost(self, reason)
		self.logic.log("[disconnected at %s]" % time.asctime(time.localtime(time.time())))
		self.logic.close()

	# callbacks for events

	def signedOn(self):
		"""Called when bot has successfully signed on to server."""
		# self.join(self.factory.channel)  # DO NOT JOIN ANY CHANNEL

	def joined(self, channel):
		"""Called when the bot joins the channel."""
		self.logic.log("[I have joined %s]" % channel)

	def privmsg(self, user, channel, msg):
		"""Called when the bot receives a message."""
		user = user.split('!', 1)[0]
		self.logic.log("<%s> %s" % (user, msg))

		# Check to see if they're sending me a private message
		if channel == self.nickname:
			if msg.startswith("!"):
				ftm = self.logic.sendstore(self.logic.FIRST_TIME_MSG, user, "firsttime.txt")
				um = self.logic.sendstore(self.logic.UPDATE_MSG, user, "updates.txt")
				if ftm:
					self.msg(user, ftm)
				if um:
					self.msg(user, um)
				command = msg.split('!', 1)[1].split()[0]

				# ~~~~~~~~~~~~~~~~~~~~~~~~ THE COMMANDS ~~~~~~~~~~~~~~~~~~~~~~~~
				if command == "set":
					msg = msg.split("!set ")[1]
					self.msg(user, self.logic.setpref(msg, user))
				elif command == "acc":
					try:
						sentmsg = self.logic.sendpp(msg, user, "acm")
						if sentmsg:
							self.msg(user, sentmsg)
							self.logic.savetofile(sentmsg, open("sentcommands.txt", "a"))
					except:
						traceback.print_exc(file=open("err.log", "a"))
						self.msg(user, "You didn't give me accuracy, combo, or misses?")
				elif command == "with":
					try:
						sentmsg = self.logic.sendpp(msg, user, "mod")
						if sentmsg:
							self.msg(user, sentmsg)
							self.logic.savetofile(sentmsg, open("sentcommands.txt", "a"))
					except:
						traceback.print_exc(file=open("err.log", "a"))
						self.msg(user, "No mods?")
				elif command == "h":
					self.msg(user, "Need help? Check [https://github.com/de-odex/aEverrBot/wiki the wiki] for commands. ~~Most commands work now.~~")
				elif command == "help":
					self.msg(user, "Need help? Check [https://github.com/de-odex/aEverrBot/wiki the wiki] for commands. ~~Most commands work now.~~")
				elif command == "r":
					self.msg(user, "Command doesn't work yet, stay tuned! Under development.")
				elif command == "uptime":
					self.msg(user, time.strftime("%H;%M;%S", time.gmtime(time.time() - first_time)) + " since start.")
				elif command == "time":
					self.msg(user, "Local time: " + time.strftime("%B %d %H:%M:%S", time.localtime(time.time())))
				elif command == "botreport":
					try:
						attr = msg.split(" ", 1)[1]
						self.msg(user, "Reported: " + attr)
						self.logic.report(attr)
					except:
						self.msg(user, "What are you reporting?")
				else:
					self.msg(user, "Invalid command. !h for help.")

			return

	def action(self, user, channel, msg):
		"""Called when the bot sees someone do an action."""
		user = user.split('!', 1)[0]
		self.logic.log("* %s %s" % (user, msg))
		if channel == self.nickname:
			ftm = self.logic.sendstore(self.logic.FIRST_TIME_MSG, user, "firsttime.txt")
			um = self.logic.sendstore(self.logic.UPDATE_MSG, user, "updates.txt")
			if ftm:
				self.msg(user, ftm)
			if um:
				self.msg(user, um)

			sentmsg = self.logic.sendpp(msg, user, "np")
			if sentmsg:
				self.msg(user, sentmsg)
				self.logic.savetofile(sentmsg, open("sentcommands.txt", "a"))
			return


class BotFactory(protocol.ReconnectingClientFactory):
	"""A factory for Bots.

	A new protocol instance will be created each time we connect to the server.
	"""

	maxDelay = 5
	initialDelay = 5

	def __init__(self, channel, filename):
		self.channel = channel
		self.filename = filename

	def buildProtocol(self, addr):
		p = Bot()
		p.factory = self
		return p

	def clientConnectionLost(self, connector, reason):
		print('Lost connection.  Reason:', reason)
		protocol.ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

	def clientConnectionFailed(self, connector, reason):
		print('Connection failed. Reason:', reason)
		protocol.ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

if __name__ == '__main__':
	# initialize logging
	log.startLogging(sys.stdout)

	# create factory protocol and application
	f = BotFactory("bottest", "logs.log")

	# connect factory to this host and port
	reactor.connectTCP(config.server, 6667, f)

	# run bot
	reactor.run()
