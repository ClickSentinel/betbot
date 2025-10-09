import asyncio
from discord.ext import commands
from cogs.reaction_handler import ReactionHandler
from unittest.mock import MagicMock

# Mock bot
bot = MagicMock(spec=commands.Bot)

# Test the _create_fake_context method
async def test():
    handler = ReactionHandler(bot)
    
    # Test with DM channel (should create User author)
    fake_ctx = await handler._create_fake_context(123, 456)
    print('Fake context created')
    print(f'Author: {fake_ctx.author}')
    print(f'Author has roles: {hasattr(fake_ctx.author, "roles")}')
    if hasattr(fake_ctx.author, 'roles'):
        print(f'Roles: {fake_ctx.author.roles}')

if __name__ == '__main__':
    asyncio.run(test())