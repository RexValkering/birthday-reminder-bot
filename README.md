# BirthdayReminderBot

This repository contains a Telegram bot which allows for adding birthdays and receiving reminders. I wrote this as a solution to my inability to remember birthdays and as an alternative to cluttering my calendar.

## Installation

### Required packages

Python3 is required. Use of a virtualenv is encouraged. 

Install the required packages:

```bash
pip install Flask
pip install telepot
```

### Generating a token

Use telegram's @BotFather to generate a token for your bot and store it in token.txt.
If you wish, you can put your own chat_id in maintainer.txt for debugging.

### Setting up your web url and generating logging.conf.

Put the weburl (without /) in weburl.txt. Make a copy of logging.conf-example and change the path to the logfile.

### Setting up your webserver.

Look at apache2.conf for an example file you can place in your sites-available folder (under a different name). I recommend generating certificates using letsencrypt.

### Testing your birthdaybot.

You can test your birthdaybot by going to `https://your.birthdaybot.domain.com/{token}/updates`. This will attempt to retrieve updates from telegram and process them. This will become unavailable once your webhook is set up.

### Setting up your webhook.

You can set up the webhook by navigating to `https://your.birthdaybot.domain.com/{token}/initwebhook`.
You can deactivate the webhook by navigating to `https://your.birthdaybot.domain.com/{token}/deletewebhook`.
You can get information about the webhook by going to `https://your.birthdaybot.domain.com/{token}/showwebhook`.

### Setting up a cronjob.

You can hook the reminders.py file into a cronjob.

## Contributing

Feel free to make contributions. This was just a small fun project and not at all an attempt to make serious software.
