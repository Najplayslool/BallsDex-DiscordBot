import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import random
from tortoise import models, fields
import logging
import asyncio
from tortoise.exceptions import DoesNotExist
logger = logging.getLogger(__name__)
from ballsdex.core.utils.transformers import (
    BallTransform,
    SpecialTransform,
    SpecialEnabledTransform,
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
ownersid =[
     749658746535280771,
     767663084890226689,
     1184739489315299339,
]


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
        all_balls = await Ball.filter(rarity__gte=0.5, rarity__lte=30.0).all()

        if not all_balls:
            return None

        # Weight unowned balls higher
        weighted_choices = []
        for ball in all_balls:
            if ball.id in owned_ids:
                # Already owned — add fewer times (e.g. 1 weight)
                weighted_choices.append((ball, 2))
            else:
                # Not owned — higher chance (e.g. 5 weight)
                weighted_choices.append((ball, 2))

        # Flatten the weighted list
        choices = []
        for ball, weight in weighted_choices:
            choices.extend([ball] * weight)

        if not choices:
            return None

        return random.choice(choices)

    async def getdasigmaballmate(self, player: Player) -> Ball | None:
        owned_ids = await BallInstance.filter(player=player).values_list("ball_id", flat=True)
        all_balls = await Ball.filter(rarity__gte=0.05, rarity__lte=5.0).all() # same with the get_random_balls

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
        embed.set_footer(text="Come back in 24 hours for your next claim!")

        await interaction.response.send_message(embed=embed, file=file, view=view)
        file.close()

    @app_commands.command(name="gweekly", description="Claim your weekly Footballer!")
    async def gweeklys(self, interaction: discord.Interaction[BallsDexBot]):
        user_id = str(interaction.user.id)
        username = interaction.user.name

        if interaction.user.id not in ownersid:
            await interaction.response.send_message(
                "❌ You’re not allowed to use this command.", ephemeral=True)
            return

        await interaction.response.defer()

        player, _ = await Player.get_or_create(discord_id=user_id)
        claimed_instances = []

        for _ in range(amount):
            ball = None

            # Try for special ball
            if random.random() < 0.25:
                special_balls = await Ball.filter(rarity="Special").all()
                if special_balls:
                    ball = random.choice(special_balls)

            # Fallback to regular
            if not ball:
                ball = await self.getdasigmaballmate(player)
            
            if not ball:
                continue

            instance = await BallInstance.create(
                ball=ball,
                player=player,
                attack_bonus=random.randint(-20, 20),
                health_bonus=random.randint(-20, 20),
            )
            claimed_instances.append((ball, instance))

        if not claimed_instances:
            await interaction.followup.send("No footballers are available.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎁 You got {len(claimed_instances)} footballer{'s' if len(claimed_instances) > 1 else ''}!",
            color=discord.Color.dark_gray()
        )
        embed.set_footer(text="Come back in 7 days for your next claim!")
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        for instance in claimed_instances:
            ball = instance.ball
            emoji = self.bot.get_emoji(ball.emoji_id)
            regime_name = ball.cached_regime.name if ball.cached_regime else "Unknown"
            embed.add_field(
                name=f"{emoji} **{ball.country}**",
                value=(
                    f"Rarity: `{ball.rarity}`\n"
                    f"💳 Card: **{regime_name}**\n"
                    f"💖 `{instance.health}` ⚽ `{instance.attack}`"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="gweekly", description="Claim your weekly Footballers! (1–10 at once)")
    @app_commands.describe(amount="How many footballers to claim (1–10)")
    async def gweeklys(self, interaction: discord.Interaction[BallsDexBot], amount: int = 1):
        user_id = str(interaction.user.id)
        username = interaction.user.name

        if interaction.user.id not in ownersid:
            await interaction.response.send_message(
                "❌ You’re not allowed to use this command.", ephemeral=True)
            return

        if amount < 1 or amount > 10:
            await interaction.response.send_message("❌ You can only claim between 1 and 10 footballers.", ephemeral=True)
            return

        await interaction.response.defer()

        player, _ = await Player.get_or_create(discord_id=user_id)
        claimed_instances = []

        for _ in range(amount):
            ball = await self.getdasigmaballmate(player)
            if not ball:
                continue

            instance = await BallInstance.create(
                ball=ball,
                player=player,
                attack_bonus=random.randint(-20, 20),
                health_bonus=random.randint(-20, 20),
            )
            claimed_instances.append((ball, instance))

        if not claimed_instances:
            await interaction.followup.send("No footballers are available.", ephemeral=True)
            return

        # Embed starts here
        embed = discord.Embed(
            title=f"🎁 You got {len(claimed_instances)} footballer{'s' if len(claimed_instances) > 1 else ''}!",
            color=discord.Color.dark_gray()
        )
        embed.set_footer(text="Come back in 7 days for your next claim!")
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        for ball, instance in claimed_instances:
            emoji = self.bot.get_emoji(ball.emoji_id)
            regime_name = ball.cached_regime.name if ball.cached_regime else "Unknown"
            embed.add_field(
                name=f"{emoji} **{ball.country}**",
                value=(
                    f"Rarity: `{ball.rarity}`\n"
                    f"💳 Card: **{regime_name}**\n"
                    f"💖 `{instance.health}` ⚽ `{instance.attack}`"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="store", description="View the exclusive store packs.")
    async def store(self, interaction: discord.Interaction):
        # Check if user is allowed
        if interaction.user.id not in ownersid:
            await interaction.response.send_message("🚫 You do not have access to the store.", ephemeral=True)
            return

        loading_msg = await interaction.response.send_message("🔄 Loading store...", ephemeral=False)
        await asyncio.sleep(1.5)

        embed = discord.Embed(
            title="🛍️  Welcome to the Pack Store!",
            description="Here are the available packs you can choose from: (EDUCATIONAL PURPOSES ALL FAKE)",
            color=discord.Color.purple()
        )
        embed.add_field(name="🎁 Classic Pack", value="Contains 1 random ball\n`/buy classic`", inline=False)
        embed.add_field(name="🔥 Elite Pack", value="Guaranteed 8.0+ stats\n`/buy elite`", inline=False)
        embed.add_field(name="💎 Legendary Pack", value="Rare or higher only\n`/buy legendary`", inline=False)
        embed.add_field(name="🧪 Mystery Pack", value="??? (secret contents!)\n`/buy mystery`", inline=False)
        embed.set_footer(text="Use /buy <pack> to purchase your pack.")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        await interaction.edit_original_response(content=None, embed=embed)
