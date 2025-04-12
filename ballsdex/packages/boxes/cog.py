import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import random
import ballsdex
from ballsdex.core.utils.transformers import (
    BallTransform,
    SpecialTransform,
)
from ballsdex.core.models import (
    Ball,
    balls,
    BallInstance,
    BlacklistedGuild,
    BlacklistedID,
    GuildConfig,
    Player,
    Trade,
    TradeObject,
    Special
)
from ballsdex.settings import settings
from ballsdex.core.bot import BallsDexBot
import ballsdex.packages.config.components as Components
from typing import TYPE_CHECKING, cast

# Credits
# -------
# - crashtestalex
# - hippopotis
# - dot_zz
# -------

# Track last claim times
last_daily_times = {}

# Cooldowns
DAILY_COOLDOWN = timedelta(hours=24)

class Claim(commands.GroupCog):
    def __init__(self, bot):
        self.bot = bot

    async def get_random_ball(self):
        count = await Ball.all().count()
        if count == 0:
            return None
        offset = random.randint(0, count - 1)
        return await Ball.all().offset(offset).first()

    @app_commands.command(name="daily", description="Claim your daily Footballer!")
    async def daily(self, interaction: discord.Interaction[BallsDexBot]):
        user_id = str(interaction.user.id)
        username = interaction.user.name

        if user_id in last_daily_times:
            last = last_daily_times[user_id]
            if datetime.now() - last < DAILY_COOLDOWN:
                remaining = DAILY_COOLDOWN - (datetime.now() - last)
                await interaction.response.send_message(
                    f"You must wait {remaining} before claiming your next daily reward.",
                    ephemeral=True
                )
                return

        player, _ = await Player.get_or_create(discord_id=user_id)
        ball = await self.get_random_ball()
        if not ball:
            await interaction.response.send_message("No balls are available.", ephemeral=True)
            return

        instance = await BallInstance.create(
            ball=ball,
            player=player,
            attack_bonus=random.randint(-20, 20),
            health_bonus=random.randint(-20, 20),
        )

        emoji = self.bot.get_emoji(ball.emoji_id)
        embed = discord.Embed(
            title=f"{username}'s Daily Claim",
            description=f"You received a {settings.collectible_name}!",
            color=discord.Color.from_rgb(0, 191, 255)
        )
        embed.add_field(
            name=f"{emoji} {ball.country}",
            value=f"``💖 {instance.attack_bonus}`` ``⚽ {instance.health_bonus}``"
        )
        embed.set_footer(text="Come back in 24 hours for your next claim!")

        await interaction.response.send_message(embed=embed)
        last_daily_times[user_id] = datetime.now()