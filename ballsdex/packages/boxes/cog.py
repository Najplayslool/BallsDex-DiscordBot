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

# Track last claim times
last_daily_times = {}
last_weekly_times = {}
wallet_balance = defaultdict(int)
packly_pool = defaultdict(int)

# Owners who can give packs
ownersid = {
    1096501882224136222,
    767663084890226689,
    749658746535280771
}

# Cooldowns
DAILY_COOLDOWN = timedelta(hours=24)
WEEKLY_COOLDOWN = timedelta(days=7)


class Claim(commands.GroupCog, name="packs"):
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


    async def getdasigmaballmate(self, player: Player) -> Ball | None:
        owned_ids = await BallInstance.filter(player=player).values_list("ball_id", flat=True)
        all_balls = await Ball.filter(rarity__gte=0.1, rarity__lte=5.0).all()

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
    async def daily(self, interaction: discord.Interaction[BallsDexBot]):
        user_id = str(interaction.user.id)
        username = interaction.user.name

        if user_id in last_daily_times:
            last = last_daily_times[user_id]
            if datetime.now() - last < DAILY_COOLDOWN:
                remaining = DAILY_COOLDOWN - (datetime.now() - last)
                await interaction.response.send_message(
                    f"You must wait {remaining} before claiming your next daily reward! • Made by drift",
                    ephemeral=True
                )
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

        # ✅ Log the daily pack grant to a specific channel and the bot's logger
        log_channel_id = 1361522228021297404  # <- Replace with your logging channel ID
        log_channel = self.bot.get_channel(log_channel_id)
        account_created = interaction.user.created_at.strftime("%Y-%m-%d %H:%M:%S")

        if log_channel:
            await log_channel.send(
                f"**{interaction.user.mention}** claimed a daily pack and got **{ball.country}**\n"
                f"• Rarity: `{ball.rarity}` 💖 `{instance.attack_bonus}` ⚽ `{instance.health_bonus}`\n"
                f"• Account created: `{account_created}`"
            )

        logger.info(
            f"[DAILY PACK] {interaction.user} ({interaction.user.id}) received {ball.country} "
            f"(Rarity: {ball.rarity}) | Account created: {account_created}"
        )

        last_daily_times[user_id] = datetime.now()


    @app_commands.command(name="weekly", description="Claim your weekly Footballer!")
    async def weekly(self, interaction: discord.Interaction[BallsDexBot]):
        user_id = str(interaction.user.id)
        username = interaction.user.name

        now = datetime.now()
        last_claim = last_weekly_times.get(user_id)

        if last_claim:
            time_since_last = now - last_claim
            if time_since_last < WEEKLY_COOLDOWN:
                remaining = WEEKLY_COOLDOWN - time_since_last
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                await interaction.response.send_message(
                    f"You must wait **{hours}h {minutes}m** before claiming your next weekly reward! • Made by drift",
                    ephemeral=True
                )
                return

        player, _ = await Player.get_or_create(discord_id=str(interaction.user.id))
        ball = await self.getdasigmaballmate(player)

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
            title=f"{username}'s Weekly Pack!",
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
        embed.set_footer(text="Come back in 7 days for your next claim! • Made by drift")

        await interaction.response.send_message(embed=embed, file=file, view=view)
        file.close()

        last_weekly_times[user_id] = now

        # ✅ Log the weekly pack grant to a specific channel and the bot's logger
        log_channel_id = 1361522228021297404  # <- Replace with your logging channel ID
        log_channel = self.bot.get_channel(log_channel_id)
        account_created = interaction.user.created_at.strftime("%Y-%m-%d %H:%M:%S")

        if log_channel:
            await log_channel.send(
                f"**{interaction.user.mention}** claimed a Weekly pack and got **{ball.country}**\n"
                f"• Rarity: `{ball.rarity}` 💖 `{instance.attack_bonus}` ⚽ `{instance.health_bonus}`\n"
                f"• Account created: `{account_created}`"
            )

        logger.info(
            f"[WEEKLY PACK] {interaction.user} ({interaction.user.id}) received {ball.country} "
            f"(Rarity: {ball.rarity}) | Account created: {account_created}"
        )



        last_weekly_times[user_id] = datetime.now()


    # Main /packly command to claim a ball after using a pack
    @app_commands.command(name="packly", description="Claim your ball from the packly!")
    async def packly(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        # Ensure user starts with 1 pack if no balance is set
        if user_id not in wallet_balance:
            wallet_balance[user_id] = 1  # Initialize with 1 pack

        # Check if the user has enough packs to claim
        if wallet_balance[user_id] < 1:
            await interaction.response.send_message(
                "You don't have enough packs!",
                ephemeral=True
            )
            return

        # Deduct 1 pack from user's wallet for claiming a ball
        wallet_balance[user_id] -= 1

        # Assign a random ball to the user
        player, _ = await Player.get_or_create(discord_id=str(interaction.user.id))
        ball = await self.get_random_ball(player)

        if not ball:
            await interaction.response.send_message("No balls are available.", ephemeral=True)
            return

        # Create an instance of the ball for the user
        instance = await BallInstance.create(
            ball=ball,
            player=player,
            attack_bonus=random.randint(-20, 20),
            health_bonus=random.randint(-20, 20),
        )

        emoji = self.bot.get_emoji(ball.emoji_id)
        color_choice = random.choice([discord.Color.from_rgb(229, 255, 0),
                                      discord.Color.from_rgb(255, 0, 0),
                                      discord.Color.from_rgb(0, 17, 255)])

        embed = discord.Embed(
            title=f"{interaction.user.name}'s Packly Claim!",
            description=f"You received **{ball.country}**!",
            color=color_choice
        )
        embed.add_field(
            name=f"{emoji} **{ball.country}** (Rarity: {ball.rarity})",
            value=f"``💖 {instance.attack_bonus}`` ``⚽ {instance.health_bonus}``"
        )

        # Attach the image of the ball to the embed
        content, file, view = await instance.prepare_for_message(interaction)
        embed.set_image(url="attachment://" + file.filename)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="Made by drift")

        await interaction.response.send_message(embed=embed, file=file, view=view)
        file.close()

        # Main /multipackly command to claim multiple balls after using multiple packs
    @app_commands.command(name="multipackly", description="Claim multiple footballers from the multipackly!")
    @app_commands.describe(packs="Number of packs to open (1-5)")
    async def multipackly(self, interaction: discord.Interaction, packs: int):
        user_id = str(interaction.user.id)

        # Ensure user starts with 1 pack if no balance is set
        if user_id not in wallet_balance:
            wallet_balance[user_id] = 1  # Initialize with 1 pack

        # Check if the user has enough packs to claim the selected number
        if packs < 1 or packs > 5:
            await interaction.response.send_message(
                "You can only open between 1 and 5 packs!",
                ephemeral=True
            )
            return

        if wallet_balance[user_id] < packs:
            await interaction.response.send_message(
                "You don't have enough packs!",
                ephemeral=True
            )
            return

        # Deduct the selected number of packs from user's wallet for claiming balls
        wallet_balance[user_id] -= packs

        # Prepare the response embed
        embed = discord.Embed(
            title=f"{interaction.user.name}'s Multipackly Claim!",
            description=f"You received **{packs}** footballers from your packs!",
            color=discord.Color.random()
        )

        files = []

        for _ in range(packs):
            # Assign a random ball to the user
            player, _ = await Player.get_or_create(discord_id=str(interaction.user.id))
            ball = await self.get_random_ball(player)

            if not ball:
                await interaction.response.send_message("No balls are available.", ephemeral=True)
                return

            # Create an instance of the ball for the user
            instance = await BallInstance.create(
                ball=ball,
                player=player,
                attack_bonus=random.randint(-20, 20),
                health_bonus=random.randint(-20, 20),
            )

            emoji = self.bot.get_emoji(ball.emoji_id)
            color_choice = random.choice([discord.Color.from_rgb(229, 255, 0),
                                        discord.Color.from_rgb(255, 0, 0),
                                        discord.Color.from_rgb(0, 17, 255)])

            # Add each ball claim to the embed
            embed.add_field(
                name=f"{emoji} **{ball.country}** (Rarity: {ball.rarity})",
                value=f"``💖 {instance.attack_bonus}`` ``⚽ {instance.health_bonus}``"
            )


        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="Made by drift")

        await interaction.response.send_message(embed=embed, files=files)
        for file in files:
            file.close()

    
    # Command to add packs to a user's wallet
    @app_commands.command(name="packly_add", description="Add packs to another user's wallet")
    async def packly_add(self, interaction: discord.Interaction, user: discord.User, packs: int):
        user_id = str(interaction.user.id)
        username = interaction.user.name

        # Check if the user issuing the command is allowed to add packs
        if interaction.user.id not in ownersid:
            await interaction.response.send_message(
                "You are not allowed to add packly's to other people or youself ❌",
                ephemeral=True
            )
            return

        # Ensure the target user has a wallet entry
        target_user_id = str(user.id)
        if target_user_id not in wallet_balance:
            wallet_balance[target_user_id] = 1  # Initialize with 1 pack if no balance exists

        # Add packs to the target user's wallet
        wallet_balance[target_user_id] += packs

        embed = discord.Embed(
            title="FootballDex Packs Added!",
            description=(
                f"{interaction.user.mention} has added **{packs}** pack(s) to {user.mention}'s wallet.\n"
                f"🪙 **{user.name}'s New Balance**: `{wallet_balance[target_user_id]} packs`"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="Packly System • Made by drift")
        embed.set_thumbnail(url=user.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    # Command to check wallet balance
    @app_commands.command(name="wallet", description="Check your wallet balance")
    async def wallet(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        username = interaction.user.name
        
        # Get the user's pack balance (defaults to 0 if they haven't added any packs)
        balance = wallet_balance.get(user_id, 0)
        
        embed = discord.Embed(
            title=f"{username}'s Wallet",
            description=f"You currently have **{balance}** pack(s).",
            color=discord.Color.green()
        )
        embed.set_footer(text="Made by drift")
        
        # Send the wallet balance as an embed
        await interaction.response.send_message(embed=embed, ephemeral=False)