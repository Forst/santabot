from collections import OrderedDict

import asyncio
import discord
import typing


class DiscordBotCommand:
    def __init__(
            self,
            name,
            function,
            description='',
            required_permissions=discord.Permissions(),
            can_run_direct=True,
            can_run_server=True,
            is_hidden=False,
    ):
        # type: (str, typing.Callable, str, discord.Permissions, bool, bool, bool) -> None

        self.name = name
        self.function = function
        self.description = description
        self.required_permissions = required_permissions
        self.can_run_direct = can_run_direct
        self.can_run_server = can_run_server
        self.is_hidden = is_hidden


class DiscordBot:
    LENGTH_LIMIT = 1000

    def __init__(self, token, prefix='!'):
        # type: (str, str) -> None

        self.token = token
        self.prefix = prefix

        self.client = discord.Client()
        self.commands = OrderedDict()  # type: typing.Dict[str, DiscordBotCommand]

        @self.client.event
        async def on_message(message):
            # type: (discord.Message) -> None

            # Skip bot's own messages
            if message.author == self.client.user:
                return

            # Skip messages without a valid prefix
            if not message.content.startswith(self.prefix):
                return

            print(message.author.name, message.content)

            # Split message into command and payload
            message_in = message.content.strip().split(maxsplit=1)  # type: str
            command_in = message_in[0][len(self.prefix):]
            payload_in = '' if len(message_in) < 2 else message_in[1]

            if command_in not in self.commands:
                payload_out = 'The specified command was not found.'.format(command_in)

            elif len(payload_in) > DiscordBot.LENGTH_LIMIT:
                payload_out = 'Input message is too long.'

            else:
                command = self.commands[command_in]

                # Server-only commands
                if message.server is None and not command.can_run_direct:
                    payload_out = 'The specified command can be executed in servers only.'

                # Direct-only commands
                elif message.server is not None and not command.can_run_server:
                    payload_out = 'The specified command can be executed via direct messages only.'

                # Permission checking
                # TODO Implement permission checking outside of servers
                elif message.server is not None and \
                        not command.required_permissions.is_subset(message.author.server_permissions):
                    payload_out = 'You do not have permission to perform the specified command.'

                # When all checks passed, execute the command and retrieve the payload
                else:
                    if asyncio.iscoroutinefunction(command.function):
                        payload_out = await command.function(message, payload_in)
                    else:
                        payload_out = command.function(message, payload_in)

            if payload_out != '':
                # Mention user when running command in non-private channels
                if not message.channel.is_private:
                    payload_out = '<@{}> '.format(message.author.id) + payload_out

                # noinspection PyUnresolvedReferences
                await self.client.send_message(message.channel, payload_out)

        @self.client.event
        async def on_ready():
            print('Logged in as {}#{} (id {})'.format(
                self.client.user.name,
                self.client.user.discriminator,
                self.client.user.id
            ))

    def command(self, name, *args, **kwargs):
        def decorator(func):
            self.commands[name] = DiscordBotCommand(name, func, *args, **kwargs)
            return func
        return decorator
