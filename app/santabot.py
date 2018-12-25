#!/usr/bin/env python3

import asyncio
import random
import re
import sqlite3
import typing

from discord_wrapper import discord, DiscordBot


DATABASE_FILE = 'santa.db'
DATABASE_SCHEMA = 'santa.sql'
DESCRIPTION = ("This bot allows to conduct a Secret Santa event in Discord servers! "
               "It is specifically optimized for digital presents, such as game codes, gift cards etc, "
               "which the bot can send anonymously via direct messages.")
MANAGEMENT_PERMISSIONS = discord.Permissions(manage_server=True)
# noinspection SpellCheckingInspection
PREFIX = 'ss!'
STATE_MESSAGES = {
    'collecting': 'It is too early to execute this command, since people are still able to join or leave.',
    'distributed': 'It is too late to execute this command, since all Secret Santas were already assigned.',

    # Messages below do not correspond to server states
    'inconsistent': 'Something went wrong with the event on this server. It might be a good idea to reset.',
    'none': 'The Secret Santa event has not yet been started on this server or invalid server specified.',
    'not_part': 'You are not part of a Secret Santa event on this server.',
    '_': 'The secret Santa event on this server is in an unknown state, something\'s wrong.',
}
# noinspection SpellCheckingInspection
TOKEN = 'INSERT_TOKEN_HERE'

DISCORD_USER_ID_REGEX = re.compile(r'(?<=<@)\d+?(?=>)')
bot = DiscordBot(TOKEN, PREFIX)


def server_bind(allowed_states=None):
    # type: (typing.Optional[typing.Set]) -> typing.Callable

    def new_function(func):
        # type: (typing.Callable) -> typing.Callable

        def wrapper(message, data):
            # type: (discord.Message, str) -> str

            # DETERMINE THE SERVER ID
            if message.server is None:
                data = data.split(' ', 1)
                if not data[0].isnumeric():
                    return ('The first command argument has to be the server ID. '
                            'To find the server ID, use the `id` command in the server.')

                message.server = discord.Server(id=data[0])
                data = data[1] if len(data) == 2 else ''

            # DETERMINE SERVER'S CURRENT STATE
            cur.execute(
                'SELECT `state`, `budget` FROM `servers` WHERE `server_id` = ?',
                (message.server.id,)
            )
            res = cur.fetchall()

            if len(res) == 1:
                # Exactly one record exists
                state = res[0][0]
                budget = 'not set' if res[0][1] == '' else res[0][1]
            elif len(res) == 0:
                # No records exist
                state = 'none'
                budget = 'not set'
            else:
                # More than one record exist
                state = 'inconsistent'
                budget = 'not set'

            # ACT DEPENDING ON THE STATE
            if allowed_states is None or state in allowed_states:
                return func(message, data, state, budget)
            else:
                print('Got state {} with allowed states {}.'.format(state, allowed_states))
                if state in STATE_MESSAGES:
                    return STATE_MESSAGES[state]
                else:
                    return STATE_MESSAGES['_']

        return wrapper

    return new_function


async def send_info(sender_id, recipient_id, wish, budget):
    # TODO refactor
    sender = discord.User(id=sender_id)
    recipient = await bot.client.get_user_info(recipient_id)  # type: discord.User

    if wish == '':
        wish = 'not set'

    msg = 'Your secret gift recipient is <@{}> ({}). The budget is {}. Their wish is: {}'.format(
        recipient_id,
        recipient.name,
        budget,
        wish,
    )

    asyncio.run_coroutine_threadsafe(bot.client.send_message(sender, msg), asyncio.get_event_loop())


@bot.command(
    'join',
    description='Join an ongoing event (and optionally specify your wishes).',
    can_run_direct=False,
)
@server_bind({'collecting'})
def cmd_join(message, data, state, budget):
    # type: (discord.Message, str, str, str) -> str

    cur.execute(
        'SELECT `recipient_id` FROM `recipients` WHERE `server_id` = ? AND `recipient_id` = ?',
        (message.server.id, message.author.id)
    )
    res = cur.fetchall()

    # Only let through users with no records in "recipients"
    if len(res) == 1:
        return 'You have already joined this Secret Santa event.'
    elif len(res) > 1:
        return STATE_MESSAGES['inconsistent']

    cur.execute(
        'INSERT INTO `recipients` (`server_id`, `recipient_id`, `wish`) VALUES (?, ?, ?)',
        (message.server.id, message.author.id, data)
    )
    conn.commit()

    return 'You have successfully joined the Secret Santa event!'


@bot.command(
    'leave',
    description='Leave an ongoing event.',
)
@server_bind({'collecting'})
def cmd_leave(message, data, state, budget):
    # type: (discord.Message, str, str, str) -> str

    cur.execute(
        'SELECT `recipient_id` FROM `recipients` WHERE `server_id` = ? AND `recipient_id` = ?',
        (message.server.id, message.author.id)
    )
    res = cur.fetchall()

    # Only let through users with a single record in "recipients"
    if len(res) == 0:
        return STATE_MESSAGES['not_part']
    elif len(res) > 1:
        return STATE_MESSAGES['inconsistent']

    cur.execute(
        'DELETE FROM `recipients` WHERE `server_id` = ? AND `recipient_id` = ?',
        (message.server.id, message.author.id)
    )
    conn.commit()

    return 'You have successfully left the Secret Santa event. See you again soon!'


@bot.command(
    'wish',
    description='Update your wishes.',
)
@server_bind({'collecting', 'distributed'})
def cmd_wish(message, data, state, budget):
    # type: (discord.Message, str, str, str) -> str

    cur.execute(
        'SELECT `recipient_id` FROM `recipients` WHERE `server_id` = ? AND `recipient_id` = ?',
        (message.server.id, message.author.id)
    )
    res = cur.fetchall()

    # Only let through users with a single record in "recipients"
    if len(res) == 0:
        return STATE_MESSAGES['not_part']
    elif len(res) > 1:
        return STATE_MESSAGES['inconsistent']

    cur.execute(
        'UPDATE `recipients` SET `wish` = ? WHERE `server_id` = ? AND `recipient_id` = ?',
        (data, message.server.id, message.author.id)
    )
    conn.commit()

    return 'Your wishes have been updated!'


@bot.command(
    'submit',
    description='Submit your gift for the recipient (**please use direct messages**).',
    can_run_server=False,
)
@server_bind({'distributed'})
def cmd_submit(message, data, state, budget):
    # type: (discord.Message, str, str, str) -> str

    cur.execute(
        'SELECT `recipient_id` FROM `senders` WHERE `server_id` = ? AND `sender_id` = ?',
        (message.server.id, message.author.id)
    )
    res = cur.fetchall()

    # Only let through users with a single record in "senders"
    if len(res) == 0:
        return STATE_MESSAGES['not_part']
    elif len(res) > 1:
        return STATE_MESSAGES['inconsistent']

    recipient_id = res[0][0]

    cur.execute(
        'UPDATE `senders` SET `gift` = ? WHERE `server_id` = ? AND `sender_id` = ?',
        (data, message.server.id, message.author.id)
    )
    conn.commit()

    return 'Your gift for <@{}> on server with ID {} was successfully submitted!'.format(
        recipient_id,
        message.server.id
    )


@bot.command(
    'who',
    description='Find out who is your secret gift recipient (answered via direct messages).',
)
@server_bind({'distributed'})
def cmd_who(message, data, state, budget):
    # type: (discord.Message, str, str, str) -> str

    cur.execute(
        '''SELECT `senders`.`recipient_id`, `recipients`.`wish`
        FROM `senders` INNER JOIN `recipients` ON `senders`.`recipient_id` = `recipients`.`recipient_id`
        WHERE `senders`.`server_id` = ? AND `recipients`.`server_id` = ?
        AND `senders`.`sender_id` = ?''',
        (message.server.id, message.server.id, message.author.id)
    )
    res = cur.fetchall()

    if len(res) == 0:
        return STATE_MESSAGES['not_part']
    elif len(res) > 1:
        return STATE_MESSAGES['inconsistent']

    recipient_id, wish = res[0][0], res[0][1]

    asyncio.run_coroutine_threadsafe(send_info(message.author.id, recipient_id, wish, budget), asyncio.get_event_loop())

    return 'Requested information sent via DM.'


@bot.command(
    'status',
    description='Shows current event status and how many people are enrolled.',
)
@server_bind({'collecting', 'distributed'})
def cmd_status(message, data, state, budget):
    # type: (discord.Message, str, str, str) -> str

    cur.execute(
        'SELECT COUNT(`recipient_id`) FROM `recipients` WHERE `server_id` = ?',
        (message.server.id,)
    )
    count = cur.fetchall()[0][0]

    if state == 'collecting':
        state_printable = 'Waiting for users to join, so far {} are in the event. Budget is {}.'.format(count, budget)
    elif state == 'distributed':
        state_printable = ('All Secret Santas were assigned respective gift recipients, {} are taking part. '
                           'Budget is {}.').format(
            count,
            budget,
        )
    else:
        state_printable = 'Secret Santa is currently in an unknown state. Try resetting it.'

    return state_printable


@bot.command(
    'id',
    description='Shows the current server ID, can be used for interacting with the bot via direct messages.',
    can_run_direct=False,
)
@server_bind()
def cmd_id(message, data, state, budget):
    # type: (discord.Message, str, str, str) -> str

    return 'This server\'s ID is {}.'.format(message.server.id)


@bot.command(
    'howto',
    description='Displays a simple how-to for the Secret Santa bot.',
)
def cmd_howto(*_):
    # type: (...) -> str

    return ('Here is a short how-to for the Secret Santa bot:\n'
            '**Join the Secret Santa event**\n'
            '```{prefix}join <wish>```'
            'where `wish` (optional) describes what you would like to receive as a gift.\n\n'
            '**Change your wish**\n'
            '```{prefix}wish <wish>```\n'
            'If you want, you can set or update your wishes via DM with the bot, if you don\'t want '
            'others to know what you want:'
            '```{prefix}wish 123456789012345678 I want a big cat plushie```'
            'where `123456789012345678` is the server\'s numeric identifier '
            '(use the `{prefix}id` command in the server to view it).\n\n'
            '**Leave the Secret Santa event**\n'
            '```{prefix}leave```\n'
            '**Find out who is your secret gift recipient** (answer comes via DM from bot):\n'
            '```{prefix}who```\n'
            '**Submit your gift** (DM the bot):\n'
            '```{prefix}submit 123456789012345678 Here is you Steam code: ABCDE-12345```'
            'where `123456789012345678` is the server\'s numeric identifier '
            '(use the `{prefix}id` command in the server to view it), '
            'followed by the gift itself (say some kind words too, why not).\n\n').format(prefix=PREFIX)


@bot.command(
    'help',
    description='Displays this help message.',
)
def cmd_help(*_):
    # type: (...) -> str

    empty = discord.Permissions.none()

    out = '{}\n\nAvailable commands:\n'.format(DESCRIPTION)
    out += '\n'.join([
        '`{}{:6}{}` `{}` `{}`\t{}{}'.format(
            PREFIX,
            key,
            chr(0),
            'S' if value.can_run_server else '-',
            'D' if value.can_run_direct else '-',
            value.description,
            ' \\*' if value.required_permissions > empty else '',
        )
        for key, value in bot.commands.items()
        if not value.is_hidden
    ])
    out += '\n\n`S` — command can be used in a server, `D` — command can be used via direct messages.'
    return out


@bot.command(
    'squee',
    description='Show credits.',
    is_hidden=True,
)
def cmd_squee(*_):
    # type: (...) -> str

    return 'Bot crafted with love by Foster Snowhill (<@299908539940601856>) :heart:'


@bot.command(
    'start',
    description='Start a new event.',
    required_permissions=MANAGEMENT_PERMISSIONS,
    can_run_direct=False,
)
@server_bind({'none'})
def cmd_start(message, data, state, budget):
    # type: (discord.Message, str, str, str) -> str

    cur.execute(
        'INSERT INTO `servers` (`server_id`, `state`, `budget`) VALUES (?, ?, ?)',
        (message.server.id, 'collecting', data)
    )
    conn.commit()

    return 'A Secret Santa event was successfully started!'


@bot.command(
    'reset',
    description='Reset all Secret Santa data for this server.',
    required_permissions=MANAGEMENT_PERMISSIONS,
    can_run_direct=False,
)
@server_bind()
def cmd_reset(message, data, state, budget):
    # type: (discord.Message, str, str, str) -> str

    cur.execute(
        'DELETE FROM `servers` WHERE `server_id` = ?',
        (message.server.id,)
    )
    cur.execute(
        'DELETE FROM `recipients` WHERE `server_id` = ?',
        (message.server.id,)
    )
    cur.execute(
        'DELETE FROM `senders` WHERE `server_id` = ?',
        (message.server.id,)
    )
    conn.commit()

    return 'All Secret Santa data for this server has been reset.'


@bot.command(
    'assign',
    description='Assign everyone their secret gift recipient.',
    required_permissions=MANAGEMENT_PERMISSIONS,
    can_run_direct=False,
)
@server_bind({'collecting'})
def cmd_assign(message, data, state, budget):
    # type: (discord.Message, str, str, str) -> str

    cur.execute(
        'SELECT `recipient_id`, `wish` FROM `recipients` WHERE `server_id` = ?',
        (message.server.id,)
    )
    res = cur.fetchall()

    wishes = {x[0]: x[1] for x in res}

    if len(res) < 2:
        return 'There has to be at least 2 users taking part in the Secret Santa event.'

    sender_ids = [x[0] for x in res]
    recipient_ids = random.sample(sender_ids, k=len(sender_ids))
    counter = 1

    while any((sender_ids[i] == recipient_ids[i] for i in range(len(sender_ids)))):
        recipient_ids = random.sample(sender_ids, k=len(sender_ids))
        counter += 1

    mappings = []

    loop = asyncio.get_event_loop()

    for i in range(len(sender_ids)):
        sender_id = sender_ids[i]
        recipient_id = recipient_ids[i]

        mappings.append((message.server.id, sender_id, recipient_id, ''))

        wish = wishes[recipient_id]

        asyncio.run_coroutine_threadsafe(send_info(sender_id, recipient_id, wish, budget), loop)

    cur.executemany(
        'INSERT INTO `senders` VALUES (?, ?, ?, ?)',
        mappings
    )
    cur.execute(
        'UPDATE `servers` SET `state` = "distributed" WHERE `server_id` = ?',
        (message.server.id,)
    )
    conn.commit()

    return ('{} secret Santas were assigned respective gift recipients! '
            'Check your DMs. *Iterations required: {}.*').format(len(sender_ids), counter)


@bot.command(
    'send',
    description='Send everyone (or the specified user) their gifts.',
    required_permissions=MANAGEMENT_PERMISSIONS,
    can_run_direct=False,
)
@server_bind({'distributed'})
def cmd_send(message, data, state, budget):
    # type: (discord.Message, str, str, str) -> str

    loop = asyncio.get_event_loop()

    if data == '':
        cur.execute(
            'SELECT `recipient_id`, `gift` FROM `senders` WHERE `server_id` = ?',
            (message.server.id,)
        )
        res = cur.fetchall()

        for recipient_id, gift in res:
            user = discord.User(id=recipient_id)

            if gift == '':
                msg = 'Unfortunately, your Secret Santa did not provide a gift :('
            else:
                msg = 'Here is your gift from a Secret Santa!\n{}'.format(gift)

            asyncio.run_coroutine_threadsafe(bot.client.send_message(user, msg), loop)

        return 'Sent gifts to {} users!'.format(len(res))
    else:
        try:
            recipient_id = DISCORD_USER_ID_REGEX.findall(data.replace('!', ''))[0]
        except:
            return 'Invalid target user ID.'

        cur.execute(
            'SELECT `gift` FROM `senders` WHERE `server_id` = ? AND `recipient_id` = ?',
            (message.server.id, recipient_id)
        )
        res = cur.fetchall()

        if len(res) < 1:
            return "Requested user didn't take part in this Secret Santa event."

        gift = res[0][0]

        user = discord.User(id=recipient_id)

        if gift == '':
            msg = 'Unfortunately, your Secret Santa did not provide a gift :('
        else:
            msg = 'Here is your gift from a Secret Santa!\n{}'.format(gift)

        asyncio.run_coroutine_threadsafe(bot.client.send_message(user, msg), loop)

        return 'Gift sent to the requested user.'


if __name__ == '__main__':
    with sqlite3.connect(DATABASE_FILE) as conn:
        cur = conn.cursor()

        with open(DATABASE_SCHEMA, 'r') as f:
            cur.executescript(f.read())
            conn.commit()

        try:
            bot.client.run(TOKEN)
        except TypeError:
            pass
