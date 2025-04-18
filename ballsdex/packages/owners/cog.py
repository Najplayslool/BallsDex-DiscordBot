import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import random
from tortoise import models, fields
import logging
logger = logging.getLogger(__name__)
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
    Special,
)
from ballsdex.settings import settings
from ballsdex.core.bot import BallsDexBot
import ballsdex.packages.config.components as Components
from collections import defaultdict

# Credits
# -------
# - crashtestalex
# - hippopotis
# - dot_zz
# -------

# Owners who can give packs
ownersid = {
    1096501882224136222,
    767663084890226689,
    749658746535280771
}

# Cooldowns
DAILY_COOLDOWN = timedelta(hours=24)

class Owners(commands.GroupCog, name="owners"):
    """
    A little simple daily pack!
    """

    def __init__(self, bot: BallsDexBot):
        self.bot = bot
        super().__init__()

    async def get_random_ball(self, player: Player) -> Ball | None:
        owned_ids = await BallInstance.filter(player=player).values_list("ball_id", flat=True)
        all_balls = await Ball.filter(rarity__gte=5.0, rarity__lte=30.0).all()

        if not all_balls:
            return None

        # Weight unowned balls higher
        weighted_choices = []
        for ball in all_balls:
            if ball.id in owned_ids:
                # Already owned — add fewer times (e.g. 1 weight)
                weighted_choices.append((ball, 1))
            else:
                # Not owned — higher chance (e.g. 5 weight)
                weighted_choices.append((ball, 5))

        # Flatten the weighted list
        choices = []
        for ball, weight in weighted_choices:
            choices.extend([ball] * weight)

        if not choices:
            return None

        return random.choice(choices)
    
    @app_commands.command(name="daily", description="Claim your daily Footballer!")
    async def dailys(self, interaction: discord.Interaction[BallsDexBot]):
        user_id = str(interaction.user.id)
        username = interaction.user.name

        if interaction.user.id not in ownersid:
            await interaction.response.send_message(
                "❌ You’re not allowed to use this command.", ephemeral=True)
            return

        player, _ = await Player.get_or_create(discord_id=str(interaction.user.id))
        ball = await self.get_random_ball(player)

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
        color_choice = random.choice([
            discord.Color.from_rgb(229, 255, 0),
            discord.Color.from_rgb(255, 0, 0),
            discord.Color.from_rgb(0, 17, 255)
        ])

        embed = discord.Embed(
            title=f"{username}'s Daily Pack!",
            description=f"You received **{ball.country}**!",
            color=color_choice
        )
        embed.add_field(
            name=f"{emoji} **{ball.country}** (Rarity: {ball.rarity})",
            value=f"``💖 {instance.attack_bonus}`` ``⚽ {instance.health_bonus}``"
        )

        content, file, view = await instance.prepare_for_message(interaction)
        embed.set_image(url="attachment://" + file.filename)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="Come back in 24 hours for your next claim! • Made by drift")

        await interaction.response.send_message(embed=embed, file=file, view=view)
        file.close()
