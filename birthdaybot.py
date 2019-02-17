from datetime import datetime
import json
import logging
import logging.config
import logging.handlers
import os
import re

from flask import Flask, request
import sqlite3
import telepot

DIRECTORY = os.path.dirname(os.path.realpath(__file__))

if not os.path.exists('{}/token.txt'.format(DIRECTORY)):
    print('Missing token.txt file, aborting...')
    exit(1)

if not os.path.exists('{}/weburl.txt'.format(DIRECTORY)):
    print('Missing weburl.txt file, aborting...')
    exit(1)

TOKEN = open('{}/token.txt'.format(DIRECTORY)).read().strip()
WEB_URL = open('{}/weburl.txt'.format(DIRECTORY)).read().strip()
API_LINK = 'https://api.telegram.org/bot{}'.format(TOKEN)
DATABASE = '{}/birthdays.db'.format(DIRECTORY)
MAINTAINER_ID = '0'

if os.path.exists('{}/maintainer.txt'.format(DIRECTORY)):
    MAINTAINER_ID = open('{}/maintainer.txt'.format(DIRECTORY)).read().strip()

app = Flask(__name__)

class BirthdayBotDatabase(object):
    """Simple controller for the birthday bot database."""

    def __init__(self, database):
        self.database = database
        self._init_db()

    def _init_db(self):
        self.query("""CREATE TABLE IF NOT EXISTS birthdays  (
            user text,
            birthday_name text,
            birthday_date date,
            service text,
            birthday_target text
        )""")

    def query(self, query, variables=tuple()):
        """Execute a query in the database."""
        conn = sqlite3.connect(self.database)
        c = conn.cursor()
        if variables:
            c.execute(query, variables)
        else:
            c.execute(query)
        conn.commit()
        c.close()
        conn.close()

    def get_rows(self, query, variables=tuple(), single=False):
        """Get one or multiple rows."""
        data = None
        conn = sqlite3.connect(self.database)
        c = conn.cursor()

        if variables:
            c.execute(query, variables)
        else:
            c.execute(query)

        if single:
            data = c.fetchone()
        else:
            data = c.fetchall()

        c.close()
        conn.close()
        return data

    def get_row(self, query, variables=tuple()):
        """Fetch a single row."""
        return self.get_rows(query, variables, single=True)


class BirthdayBot(object):

    def __init__(self, token, database):
        self.bot = telepot.Bot(token)
        self.db = BirthdayBotDatabase(database)
        logging.config.fileConfig('{}/logging.conf'.format(DIRECTORY))
        self.log = logging.getLogger('birthdaybot')

    def get_birthdays(self, chat_id):
        """Get all stored birthdays for a chat.

        Args:
            chat_id: ID of user that stored the birthdays
        """
        return self.db.get_rows("SELECT * FROM birthdays WHERE user = ?", (chat_id,))

    def get_birthday(self, chat_id, name):
        """Get a specific birthday for a chat.

        Args:
            chat_id: ID of user that stored the birthdays
            name: name of stored birthday
        """
        return self.db.get_row("SELECT * FROM birthdays WHERE user = ? AND birthday_name = ?",
                               (chat_id, name))

    def get_current_birthdays(self, chat_id):
        """Get today's birthdays for a chat.

        Args:
            chat_id: ID of user that stored the birthdays
        """
        today = datetime.now()

        return self.db.get_rows("SELECT * FROM birthdays WHERE user = ? AND birthday_date LIKE ?",
                                (chat_id, '{:02d}-{:02d}-%'.format(today.day, today.month)))

    def add_birthday(self, chat_id, name, birthday, service, service_id):
        """Store a birthday.

        Args:
            chat_id: ID of user that stored the birthdays
        """
        query = """INSERT INTO birthdays (
                user, birthday_name, birthday_date, service, birthday_target
            ) VALUES (
                ?, ?, ?, ?, ?
            )"""

        self.db.query(query, (chat_id, name, birthday, service, service_id))

    def remove_birthday(self, chat_id, name):
        """Remove a birthday.

        Args:
            chat_id: ID of user that stored the birthdays
            name: name of stored birthday
        """
        query = "DELETE FROM birthdays WHERE user = ? AND birthday_name = ?"
        self.db.query(query, (chat_id, name))

    def format_birthday(self, record, show_age=True):
        """Format a birthday with either birthday or age.

        Args:
            record: birthday record to format
            show_age (bool): whether age should be shown instead of birth date
        """
        link = ''
        name = record[1]
        date = record[2]

        now = datetime.now()
        then = datetime.strptime(date, '%d-%m-%Y')

        # Naive way of calculating someone's age
        age = now.year - then.year
        if now.month > then.month or (now.month == then.month and now.day > then.day):
            age -= 1

        # Determine the service and link
        service = record[3]
        handle = record[4]
        if service == 'whatsapp':
            link = 'https://api.whatsapp.com/send?phone={handle}'.format(handle=handle)
        elif service == 'telegram':
            link = 'https://web.telegram.org/#/im?p={handle}'.format(handle=handle)
        
        if show_age:
            if service:
                return '- {name} ({age}) - {link}'.format(name=name, age=age, link=link)
            else:
                return '- {name} ({age})'.format(name=name, age=age)
        else:
            if service:
                return '- {name} ({date}) - {link}'.format(name=name, date=date, link=link)
            else:
                return '- {name} ({date})'.format(name=name, date=date)

    def send_reminders(self):
        """Send reminders for today's birthdays to all stored users."""
        users = self.db.get_rows("""SELECT DISTINCT(user) FROM birthdays""")

        for user in users:
            chat_id = user[0]
            text = []
            birthdays = self.get_current_birthdays(chat_id)
            if not birthdays:
                continue

            text.append('The following people are celebrating their birthday today:')
            for birthday in birthdays:
                text.append(self.format_birthday(birthday))
            self.bot.sendMessage(chat_id, '\n'.join(text))

    def handle_add(self, chat_id, arguments):
        """Handler for the /add command. Adds a birthday to the database.

        Args:
            chat_id: the chat that is interacting with the bot
            arguments: list of command arguments
        """

        error_message = '{reason}\nFormat: /add <name>,dd-mm-yyyy,<service>,<handle>'

        # Validate number of arguments
        if len(arguments) not in [2, 4]:
            return self.bot.sendMessage(chat_id, error_message.format(reason='Incorrect number of arguments.'))

        if len(arguments) == 2:
            name, birthday = arguments
            service, handle = '', ''
        else:
            name, birthday, service, handle = arguments
        
        # Validate birthday
        try:
            datetime_object = datetime.strptime(birthday, '%d-%m-%Y')
        except ValueError as reason:
            return self.bot.sendMessage(chat_id, error_message.format(reason='Incorrect date.'))

        # Validate service
        if service not in ('', 'whatsapp', 'telegram'):
            return self.bot.sendMessage(chat_id, error_message.format(reason='Service must be either whatsapp or telegram.'))

        record = self.get_birthday(chat_id, name)
        if record:
            return self.bot.sendMessage(chat_id, 'There is already a birthday reminder for {name}.'.format(name=name))

        self.add_birthday(chat_id, name, birthday, service, handle)
        return self.bot.sendMessage(chat_id, '{name} has been added to your birthday reminders.'.format(name=name))

    def handle_remove(self, chat_id, arguments):
        """Handler for the /remove command. Removes a birthday from the database.

        Args:
            chat_id: the chat that is interacting with the bot
            arguments: list of command arguments
        """
        if not len(arguments) == 1:
            return self.bot.sendMessage(chat_id, 'Incorrect usage')

        name = arguments[0]
        birthday = self.get_birthday(chat_id, name)

        if not birthday:
            return self.bot.sendMessage(chat_id, 'Could not find a birthday with that name')

        self.remove_birthday(chat_id, name)
        return self.bot.sendMessage(chat_id, 'Removed birthday for `{}`'.format(name))

    def handle_start(self, chat_id, arguments):
        """Handler for the /start and /help command. Shows available commands.

        Args:
            chat_id: the chat that is interacting with the bot
            arguments: list of command arguments
        """
        text = []
        text.append('This bot sends you birthday reminders at 6:45 AM GMT')
        text.append('')
        text.append('Available commands:')
        text.append('/start - get this message')
        text.append('/help - get this message')
        text.append('/add <name>,<birthday> - add a birthday')
        text.append('/add <name>,<birthday>,<whatsapp|telegram>,<handle> - add a birthday with link')
        text.append('/remove <name> - remove a birthday')
        text.append('/get - list all birthdays')
        text.append('/list - list all birthdays')
        text.append('/get <name> - list a particular birthday')
        text.append('/today - list all birthdays today')
        return self.bot.sendMessage(chat_id, '\n'.join(text))

    def handle_get(self, chat_id, arguments):
        """Handler for the /get and /list command. Lists one or more registered birthdays.

        Args:
            chat_id: the chat that is interacting with the bot
            arguments: list of command arguments
        """
        text = []
        if not arguments or arguments == ['']:
            birthdays = self.get_birthdays(chat_id)
            text.append('You have the following birthdays registered:')
            for birthday in birthdays:
                text.append(self.format_birthday(birthday, False))
        else:
            for argument in arguments:
                birthday = self.get_birthday(chat_id, argument)
                if not birthday:
                    text.append('Could not find a birthday for `{}`'.format(argument))
                else:
                    text.append(self.format_birthday(birthday, False))
        return self.bot.sendMessage(chat_id, '\n'.join(text))

    def handle_today(self, chat_id, arguments):
        """Handler for the /today command. Lists all current birthdays.

        Args:
            chat_id: the chat that is interacting with the bot
            arguments: list of command arguments
        """
        text = []
        birthdays = self.get_current_birthdays(chat_id)
        if not birthdays:
            text.append('There are no birthdays today.')
        else:
            text.append('The following people are celebrating their birthday today:')
            for birthday in birthdays:
                text.append(self.format_birthday(birthday))
        return self.bot.sendMessage(chat_id, '\n'.join(text))

    def handle_message(self, chat_id, message):
        """Handle an incoming update.

        Args:
            chat_id: id of chat interacting with bot
            message: sent message
        """
        command = message.split(' ')[0]
        arguments = [x.strip() for x in message[len(command)+1:].strip().split(',')]

        handlers = {
            '/start': self.handle_start,
            '/help': self.handle_start,
            '/add': self.handle_add,
            '/get': self.handle_get,
            '/list': self.handle_get,
            '/today': self.handle_today,
            '/remove': self.handle_remove
        }

        try:
            if command in handlers:
                return handlers[command](chat_id, arguments)
            else:
                return self.bot.sendMessage(chat_id, 'Unknown command {}'.format(command))
        except Exception as reason:
            if chat_id == MAINTAINER_ID:
                self.bot.sendMessage(chat_id, 'Operation resulted in error. Exception: {}'.format(str(reason)))
            else:
                self.bot.sendMessage(chat_id, 'Operation resulted in an unexpected error.')
            self.log.error(str(reason))
        return False

    def handle_updates(self, data):
        """Handle incoming JSON from the webhook."""
        output = ''
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            message = data['message']['text']
            output += str(self.handle_message(chat_id, message))

        elif isinstance(data, list):
            for i, result in enumerate(data):
                chat_id = result['message']['chat']['id']
                message = result['message']['text']
                output += str(self.handle_message(chat_id, message))

        return output

    def get_updates(self):
        """Get updates manually."""
        data = self.bot.getUpdates(self.get_offset())
        if data:
            last_update_id = data[-1]['update_id']
            self.set_offset(last_update_id + 1)

        return data

bot = BirthdayBot(TOKEN, DATABASE)

@app.route('/')
def index():
    return json.dumps('Hello world')

@app.route('/{}'.format(TOKEN), methods=['POST'])
def webhook():
    update = request.get_json(force=True)
    bot.handle_updates(update)
    return json.dumps('Ok')

@app.route('/{}/updates'.format(TOKEN))
def get_updates():
    updates = bot.get_updates()
    return json.dumps(bot.handle_updates(updates))

@app.route('/{}/initwebhook'.format(TOKEN))
def init_webhook():
    return json.dumps(bot.bot.setWebhook(url='{}/{}'.format(WEBURL, TOKEN)))

@app.route('/{}/deletewebhook'.format(TOKEN))
def delete_webhook():
    return json.dumps(bot.bot.deleteWebhook())

@app.route('/{}/showwebhook'.format(TOKEN))
def webhookinfo():
    return json.dumps(bot.bot.getWebhookInfo())

if __name__ == '__main__':
    app.run(debug=True)
