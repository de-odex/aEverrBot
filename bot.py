import logging.config

from twisted.words.protocols import irc
from twisted.internet import reactor, protocol, threads

# mine
import os
import importlib
import datetime
import pathlib
import box
import utils
import external.jaraco_irc_to_twisted as jaraco_irc_to_twisted

logging.config.fileConfig('logging.conf')
logger = logging.getLogger(__name__)


class FruityBot(irc.IRCClient):
    try:
        nickname = utils.Config("config.json").config.main.nick
        password = utils.Config("config.json").config.osu.irc
    except FileNotFoundError:
        nickname = utils.Config("config.json.template").config.main.nick
        password = utils.Config("config.json.template").config.osu.irc
    lineRate = 1
    heartbeatInterval = 64

    def __init__(self, first_time, users, channel=None, test=False):
        logger.debug("Trying nickname " + self.nickname)
        self.test = test
        self.channel = channel

        try:
            self.Config = utils.Config("config.json")
        except FileNotFoundError:
            self.Config = utils.Config("config.json.template")

        self.UPDATE_MSG = self.Config.config.main.update_msg
        self.FIRST_TIME_MSG = self.Config.config.main.first_time_msg

        self.user_pref = utils.Utils.create_db("./userpref.db", "userpref")
        self.start_time = first_time

        self.users = users

        self.Commands = utils.Commands(self, self.Config)
        self.command_funcs = [func for func in dir(utils.Commands) if callable(getattr(utils.Commands, func))
                              and not func.startswith("_")]

    def irc_ERR_NICKNAMEINUSE(self, prefix, params):
        logger.warning("Nick error! Someone of " + self.nickname + " nickname already exists")
        self.nickname = self.nickname + "_"
        self.setNick(self.nickname)
        logger.debug("Now using " + self.nickname)

    def signedOn(self):
        logger.info("Bot started as " + self.nickname + " at " + self.Config.config.main.server)
        self.startHeartbeat()
        if self.channel is not None and self.Config.config.main.server != "cho.ppy.sh" or \
           self.Config.config.main.server != "irc.ppy.sh":
            self.join(self.channel)
        if self.test:
            self.quit()

    def joined(self, channel):
        logger.info("I have joined " + channel)

    def privmsg(self, userhost, channel, msg):
        user = userhost.split('!', 1)[0]
        logger.info(user + ": " + msg)
        if msg[0] == self.Config.config.main.prefix:
            try:
                threads.deferToThread(self.message_to_commands, userhost, msg)
            except Exception:
                logger.exception("Deferred Exception")
                self.msg(user, "Falling back to single-thread...")
                self.message_to_commands(userhost, msg)

    def action(self, userhost, channel, data):
        user = userhost.split('!', 1)[0]
        logger.info("* " + user + " " + data)
        try:
            threads.deferToThread(self.message_to_commands, userhost, "!np " + data)
        except Exception:
            logger.exception("Deferred Exception")
            self.msg(user, "Falling back to single-thread...")
            self.message_to_commands(userhost, "!np " + data)

    def message_to_commands(self, userhost, msg):
        commands = msg.split(self.Config.config.main.prefix)[1].split(";")
        for msgs in commands:
            msgs = msgs.strip()
            self.do_command(userhost, msgs)

    def do_command(self, userhost, msg):
        cmd = msg.split()[0]
        e = box.Box({'source': jaraco_irc_to_twisted.NickMask(userhost), 'arguments': [msg]})

        if cmd == "reload":
            logger.debug("Command incurred: " + cmd)
            if e.source.nick == self.Config.config.main.owner:
                self.msg(e.source.nick, "Attempting a reload...")
                try:
                    importlib.reload(utils)
                    self.user_pref = utils.Utils.create_db("./userpref.db", "userpref")
                    self.Config = utils.Config("config.json")
                    self.Commands = utils.Commands(self, self.Config)
                    self.UPDATE_MSG = self.Config.config.main.update_msg
                    self.FIRST_TIME_MSG = self.Config.config.main.first_time_msg
                    self.command_funcs = [func for func in dir(utils.Commands) if callable(
                        getattr(utils.Commands, func)) and not func.startswith("_")]
                    self.msg(e.source.nick, "Reload successful!")
                except:
                    logger.exception("Reload Exception")
                    self.msg(e.source.nick, "Reload failed! Killing bot due to possible errors.")
                    self.quit()
        else:
            for i in self.command_funcs:
                if (cmd.split()[0] == i and i[:4] != "cmd_") or (cmd.split()[0] == i[4:] and i[:4] == "cmd_"):
                    logger.debug("Command incurred: " + cmd)
                    # check if user in database
                    in_db = utils.Utils.check_user_in_db(e.source, self, "ftm")
                    if not in_db:
                        self.msg(e.source.nick, self.FIRST_TIME_MSG)
                    in_db = utils.Utils.check_user_in_db(e.source, self, "um")
                    if not in_db:
                        self.msg(e.source.nick, self.UPDATE_MSG)

                    func = getattr(utils.Commands, i)
                    func(self.Commands, self, e)
                    break
            else:
                self.msg(e.source.nick, "Invalid command: " + cmd + ". " +
                         self.Config.config.main.prefix + "h for help.")


class BotFactory(protocol.ReconnectingClientFactory):
    """A factory for Bots.

    A new protocol instance will be created each time we connect to the server.
    """

    maxDelay = 5
    initialDelay = 5

    def __init__(self, channel=None):
        self.first_time = datetime.datetime.now()
        self.channel = channel
        self.users = {}

    def buildProtocol(self, addr):
        p = FruityBot(self.first_time, self.users, self.channel)
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        logger.warning('Lost connection.  Reason:' + str(reason).replace('\n', '').replace('\r', ''))
        protocol.ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        logger.warning('Connection failed.  Reason:' + str(reason).replace('\n', '').replace('\r', ''))
        protocol.ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


def main():
    if not pathlib.Path("./log/").exists():
        os.mkdir("./log/")

    logger.debug("Start of __main__")

    # create factory protocol and application
    f = BotFactory("bottest")

    # connect factory to this host and port
    try:
        reactor.connectTCP(utils.Config("config.json").config.main.server, 6667, f)
    except FileNotFoundError:
        reactor.connectTCP(utils.Config("config.json.template").config.main.server, 6667, f)

    # run bot
    reactor.run()


if __name__ == "__main__":
    main()
