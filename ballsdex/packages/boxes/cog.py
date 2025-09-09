import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone, time
import random
from discord import Embed, Color, File
from tortoise import models, fields
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw, ImageFont
from discord.ui import View
import asyncio
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
from ballsdex.core.image_generator. image_gen import draw_card
from io import BytesIO
from ballsdex.core.utils.transformers import (
    BallEnabledTransform,
    BallInstanceTransform,
    SpecialEnabledTransform,
    TradeCommandType,
)

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
    767663084890226689,
    749658746535280771
}

# Cooldowns
DAILY_COOLDOWN = timedelta(hours=24)
WEEKLY_COOLDOWN = timedelta(days=7)
gamble_cooldowns = {} 

HYPE_TAGLINES = [
    "🔥 Hot pack incoming!",
    "💥 Energy surging...",
    "✨ Luck is in the air!",
    "🎯 Precision draws!",
    "🚀 Rapid walkout!",
]

class Claim(commands.GroupCog, name="packs"):
    """
    A little simple daily pack!
    """

    def __init__(self, bot: BallsDexBot):
        self.bot = bot
        self.bot_tutorial_seen = set()
        self.bot_walletturorial_seen = set()
        super().__init__()

    def rarity_bar(rarity: float, max_rarity=10.0, length=10) -> str:
        filled = int((rarity / max_rarity) * length)
        empty = length - filled
        return "█" * filled + "░" * empty

    def resolve_emoji(self, ball):
        # full emoji if stored
        emoji_full = getattr(ball, "emoji", None)
        if isinstance(emoji_full, str) and emoji_full.startswith("<:") and emoji_full.endswith(">"):
            return emoji_full

        # name+id
        name = getattr(ball, "emoji_name", None)
        eid = getattr(ball, "emoji_id", None)
        if name and eid:
            return f"<:{name}:{eid}>"

        # lookup by ID in cache
        if getattr(ball, "emoji_id", None):
            try:
                eid_int = int(ball.emoji_id)
                for guild in self.bot.guilds:
                    match = discord.utils.get(guild.emojis, id=eid_int)
                    if match:
                        return str(match)
            except Exception:
                pass

        # fallback per country
        country = getattr(ball, "country", "").lower()
        fallback = {
            "messi": "🌟",
        }
        return fallback.get(country, "🎴")

    def build_pack_embed(self, user: discord.User, pulls: list[tuple]):
        total_atk = sum(instance.attack for _, instance in pulls)
        total_hp = sum(instance.health for _, instance in pulls)
        lines = []
        for i, (ball, instance) in enumerate(pulls, start=1):
            atk = instance.attack
            hp = instance.health
            atk_bonus = instance.attack_bonus
            hp_bonus = instance.health_bonus
            emoji = self.resolve_emoji(ball)
            lines.append(
                f"**#{i} {emoji} {ball.country.title()}**\n"
                f"• ATK: {'+' if atk_bonus >= 0 else ''}{atk_bonus}% ({atk})\n"
                f"• HP: {'+' if hp_bonus >= 0 else ''}{hp}"
            )

        tagline = random.choice([
            "🔥 Hot pack incoming!",
            "💥 Energy surging...",
            "✨ Luck is in the air!",
            "🎯 Precision draws!",
            "🚀 Rapid walkout!",
        ])
        embed = discord.Embed(
            title="🎁 Daily Triple Pack!",
            description=f"{tagline}\nHere are your new players:",
            color=0x9B59B6,
            timestamp=datetime.utcnow()
        )
        for idx, line in enumerate(lines, start=1):
            embed.add_field(name=f"Player {idx}", value=line, inline=False)
        embed.add_field(
            name="📊 Pack Statistics",
            value=f"Total ATK: **{total_atk}**\nTotal HP: **{total_hp}**",
            inline=False
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        embed.set_footer(text="Pack opening complete! ⚡ NewFramework™", icon_url=user.display_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.url)
        return embed

    def build_account_info_embed(self, user: discord.User) -> discord.Embed:
        created_at = user.created_at  # datetime object when the Discord account was created
        created_str = created_at.strftime("%B %d, %Y at %H:%M UTC")  # pretty format

        embed = discord.Embed(
            title=f"📝 Account Info: {user}",
            description=f"Here's the juicy deets about your Discord account!",
            color=0x7289DA,  # Discord blurple
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Account Created On", value=created_str, inline=False)
        embed.add_field(name="User ID", value=user.id, inline=False)
        embed.set_footer(text="Account info served fresh! 🌸")

        return embed

    async def get_random_ball(self, player: Player) -> Ball | None:
        owned_ids = set(
            await BallInstance.filter(player=player).values_list("ball__id", flat=True)
        )
        all_balls = await Ball.filter(rarity__gte=0.1, rarity__lte=30.0, enabled=True).all()

        if not all_balls:
            return None

        weighted_choices = []
        for ball in all_balls:
            # base weight based on ownership
            base_weight = 1 if ball.id in owned_ids else 5

            # rarity weight according to your tiers
            if 5.0 <= ball.rarity <= 30.0:
                rarity_weight = 16  # common
            elif 2.5 <= ball.rarity < 5.0:
                rarity_weight = 6   # decent
            elif 1.5 <= ball.rarity < 2.5:
                rarity_weight = 3   # rare
            elif 0.5 < ball.rarity < 1.5:
                rarity_weight = 1   # very rare
            else:  # ball.rarity == 0.5 exactly (very very rare)
                rarity_weight = 0.2

            final_weight = base_weight * rarity_weight
            weighted_choices.append((ball, final_weight))

        choices = []
        for ball, weight in weighted_choices:
            choices.extend([ball] * int(weight))

        if not choices:
            return None

        return random.choice(choices)


    async def getdasigmaballmate(self, player: Player) -> Ball | None:
        owned_ids = set(
            await BallInstance.filter(player=player).values_list("ball__id", flat=True)
        )
        all_balls = await Ball.filter(rarity__gte=0.03, rarity__lte=5.0, enabled=True).all()

        if not all_balls:
            return None

        weighted_choices = []
        for ball in all_balls:
            if ball.id in owned_ids:
                base_weight = 1
            else:
                base_weight = 5

            # Explicit rarity weighting
            if ball.rarity >= 4.5:  # very common
                rarity_weight = 9
            elif ball.rarity >= 1.5:  # common
                rarity_weight = 5
            elif ball.rarity >= 0.5:  # uncommon
                rarity_weight = 2
            else:  # rare (below 0.5 rarity)
                rarity_weight = 0.2

            final_weight = base_weight * rarity_weight
            weighted_choices.append((ball, final_weight))

        choices = []
        for ball, weight in weighted_choices:
            choices.extend([ball] * int(weight))

        if not choices:
            return None

        return random.choice(choices)



    @app_commands.command(name="daily", description="Claim your daily Footballer!")
    @app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
    async def daily(self, interaction: discord.Interaction[BallsDexBot]):
        user_id = str(interaction.user.id)
        username = interaction.user.name
        pulls = await self.open_daily_pack_for_user(user)

        # account age guard
        min_age = datetime.now(timezone.utc) - timedelta(days=14)
        if interaction.user.created_at > min_age:
            await interaction.response.send_message(
                "⛔ Your account must be at least 14 days old to claim daily packs.", ephemeral=True
            )
            return

        await interaction.response.defer()

        player, _ = await Player.get_or_create(discord_id=str(interaction.user.id))

        pulls = []
        for _ in range(3):
            ball = await self.get_random_ball(player)
            if not ball:
                continue
            instance = await BallInstance.create(
                ball=ball,
                player=player,
                attack_bonus=random.randint(-20, 20),
                health_bonus=random.randint(-20, 20),
            )
            pulls.append((ball, instance))

        if not pulls:
            await interaction.followup.send("No footballers available right now, try again later.", ephemeral=True)
            return

        # quick micro-reveal: send initial spark then replace with full results
        intro_embed = discord.Embed(
            title="🎁 Opening Daily Triple Pack..."
            description="Spinning up your walkout..."
            color=0x8E44AD
        )
        msg = await interaction.followup.send(embed=intro_embed)

        # tiny suspense
        await asyncio.sleep(0.7)

        final = self.build_pack_embed(interaction.user, pulls)
        await msg.edit(embed=final)

        YOUR_LOG_CHANNEL_ID = 1321133518029590648
        log_channel = self.bot.get_channel(YOUR_LOG_CHANNEL_ID)
        if log_channel:
            log_embed = build_daily_redeem_log_embed(user, pulls)
            await log_channel.send(embed=log_embed)


    @app_commands.command(name="weekly", description="Claim your weekly Footballer!")
    @app_commands.checks.cooldown(1, 604800, key=lambda i: i.user.id)
    async def weekly(self, interaction: discord.Interaction[BallsDexBot]):
        user_id = str(interaction.user.id)
        username = interaction.user.name

        min_creation = datetime.now(timezone.utc) - timedelta(days=14)
        if interaction.user.created_at > min_creation:
            await interaction.response.send_message(
                "Your account must be at least 14 days old to use this command.",
                ephemeral=True
            )
            return

        now = datetime.now()
        last_claim = last_weekly_times.get(user_id)


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

        # Walkout-style embed animation
        walkout_embed = discord.Embed(title="🎉 Weekly Pack Opening...", color=discord.Color.dark_gray())
        walkout_embed.set_footer(text="Come back in 7 days for your next claim!")
        await interaction.response.defer()
        msg = await interaction.followup.send(embed=walkout_embed)

        await asyncio.sleep(1.5)
        walkout_embed.description = f"✨ **Rarity:** `{ball.rarity}`"
        await msg.edit(embed=walkout_embed)

        await asyncio.sleep(1.5)
        regime_name = ball.cached_regime.name if ball.cached_regime else "Unknown"
        walkout_embed.description += f"\n💳 **Card:** **{regime_name}**"
        await msg.edit(embed=walkout_embed)

        await asyncio.sleep(1.5)
        walkout_embed.description += f"\n💖 **Health:** `{instance.health}`\n⚽ **Attack:** `{instance.attack}`"
        await msg.edit(embed=walkout_embed)

        await asyncio.sleep(1.5)
        walkout_embed.title = f"🎁 You got **{ball.country} {ball.id}**!"
        walkout_embed.color = discord.Color.from_rgb(229, 255, 0)  # You can randomize if you want

        content, file, view = await instance.prepare_for_message(interaction)
        walkout_embed.set_image(url="attachment://" + file.filename)
        walkout_embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        await msg.edit(embed=walkout_embed, attachments=[file], view=view)
        file.close()


        # ✅ Log the weekly pack grant to a specific channel and the bot's logger
        log_channel_id = 1361522228021297404  # <- Replace with your logging channel ID
        log_channel = self.bot.get_channel(log_channel_id)
        account_created = interaction.user.created_at.strftime("%Y-%m-%d %H:%M:%S")

        if log_channel:
            await log_channel.send(
                f"**{interaction.user.mention}** claimed a Weekly pack and got **{ball.country}**\n"
                f"• Rarity: `{ball.rarity}` 💖 `{instance.attack_bonus}` ⚽ `{instance.health_bonus}`\n"
                f"Footballer ID: `#{ball.pk:0X}`\n"
                f"• Account created: `{account_created}`"
            )

        logger.info(
            f"[WEEKLY PACK] {interaction.user} ({interaction.user.id}) received {ball.country} "
            f"(Rarity: {ball.rarity}) | Account created: {account_created}"
            f"Footballer ID: `#{ball.pk:0X}`"
        )





    # Main /packly command to claim a ball after using a pack
    @app_commands.command(name="packly", description="Claim your footballer from the packly!")
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    async def packly(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        min_creation = datetime.now(timezone.utc) - timedelta(days=14)
        if interaction.user.created_at > min_creation:
            await interaction.response.send_message(
                "Your account must be at least 14 days old to use this command.",
                ephemeral=True
            )
            return
        
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
            await interaction.response.send_message("No footballers are available.", ephemeral=True)
            return

        # Create an instance of the ball for the user
        instance = await BallInstance.create(
            ball=ball,
            player=player,
            attack_bonus=random.randint(-20, 20),
            health_bonus=random.randint(-20, 20),
        )

        # Walkout-style embed animation
        walkout_embed = discord.Embed(title="🎁 Opening Packly...", color=discord.Color.dark_gray())
        walkout_embed.set_footer(text="FootballDex Packly")
        await interaction.response.defer()
        msg = await interaction.followup.send(embed=walkout_embed)


        await asyncio.sleep(1.5)
        walkout_embed.description = f"✨ **Rarity:** `{ball.rarity}`"
        await msg.edit(embed=walkout_embed)

        await asyncio.sleep(1.5)
        regime_name = ball.cached_regime.name if ball.cached_regime else "Unknown"
        walkout_embed.description += f"\n💳 **Card:** **{regime_name}**"
        await msg.edit(embed=walkout_embed)

        await asyncio.sleep(1.5)
        walkout_embed.description += f"\n💖 **Health:** `{instance.health}`\n⚽ **Attack:** `{instance.attack}`"
        await msg.edit(embed=walkout_embed)

        await asyncio.sleep(1.5)
        walkout_embed.title = f"🎉 You claimed **{ball.country}** from Packly!"
        walkout_embed.color = discord.Color.gold()

        content, file, view = await instance.prepare_for_message(interaction)
        walkout_embed.set_image(url="attachment://" + file.filename)
        walkout_embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        await msg.edit(embed=walkout_embed, attachments=[file], view=view)
        file.close()

    @app_commands.command(name="multipackly", description="Claim multiple footballers from the multipackly!")
    @app_commands.describe(packs="Number of packs to open (1-5)")
    @app_commands.checks.cooldown(1, 25, key=lambda i: i.user.id)
    async def multipackly(self, interaction: discord.Interaction, packs: int):
        user_id = str(interaction.user.id)

        min_creation = datetime.now(timezone.utc) - timedelta(days=14)
        if interaction.user.created_at > min_creation:
            await interaction.response.send_message(
                "Your account must be at least 14 days old to use this command.",
                ephemeral=True
            )
            return

        # Ensure user starts with 1 pack if no balance is set
        if user_id not in wallet_balance:
            wallet_balance[user_id] = 1

        # Validate pack number
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

        # Deduct packs
        wallet_balance[user_id] -= packs

        # Create the first embed (opening animation)
        first_embed = discord.Embed(
            title="🎁 Opening Multipackly...",
            description="Get ready to reveal your footballers!",
            color=discord.Color.gold()
        )
        first_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        first_embed.set_footer(text="FootballDex MultiPacklys")

        # Send the first embed
        await interaction.response.send_message(embed=first_embed)
        message = await interaction.original_response()

        pulled_balls = []

        # Small pause to simulate animation
        await asyncio.sleep(4)

        # Reveal footballers one by one
        for _ in range(packs):
            player, _ = await Player.get_or_create(discord_id=str(interaction.user.id))
            ball = await self.get_random_ball(player)

            if not ball:
                await interaction.followup.send("No footballers are available.", ephemeral=True)
                return

            # Create an instance of the ball for the user
            instance = await BallInstance.create(
                ball=ball,
                player=player,
                attack_bonus=random.randint(-20, 20),
                health_bonus=random.randint(-20, 20),
            )

            # Create the walkout embed
            walkout_embed = discord.Embed(
                title=f"🏆 You pulled {ball.country}!",
                description=f"**Rarity:** {ball.rarity}\n⚽ **Attack:** {ball.attack}\n❤️ **Health:** {ball.health}",
                color=discord.Color.random()
            )
            walkout_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            walkout_embed.set_footer(text="FootballDex Pack Opening")

            # Edit the message to show the walkout
            await message.edit(embed=walkout_embed)

            pulled_balls.append(ball.country)
            balance = wallet_balance.get(user_id, 0)

            await asyncio.sleep(2)  # Pause between each reveal

        # Final message after all reveals
        final_embed = discord.Embed(
        title="🎉 All Footballers Revealed!",
        description=(
        f"Your Multi-Packly has been done!\n\n"
        f"*Here is what you got in your multipackly:*\n"
        f"**{', '.join(pulled_balls)}!**\n"
        f"**New Packly Balance: {balance}**"
        ),
        color=discord.Color.green()
)
        final_embed.set_footer(text="FootballDex MultiPacklys")
        await message.edit(embed=final_embed)


    
    # Command to add packs to a user's wallet
    @app_commands.command(name="owners-add", description="Add packs to another user's wallet")
    async def ownerspacklyadd(self, interaction: discord.Interaction, user: discord.User, packs: int):
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
        embed.set_footer(text="Packly System")
        embed.set_thumbnail(url=user.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="gamblepack", description="Gamble your packlys for a chance to win double – or lose it all!")
    @app_commands.describe(amount="How many packs to gamble (fixed 50/50 chance)")
    async def gamblepack(self, interaction: discord.Interaction, amount: int = 1):
        user_id = str(interaction.user.id)

        min_creation = datetime.now(timezone.utc) - timedelta(days=14)
        if interaction.user.created_at > min_creation:
            await interaction.response.send_message(
                "Your account must be at least 14 days old to use this command.",
                ephemeral=True
            )
            return

        now = datetime.utcnow()

        if amount < 1:
            await interaction.response.send_message("You must gamble at least 1 pack.", ephemeral=True)
            return

        if amount > 50:
            await interaction.response.send_message("❌ You can only gamble up to 50 packlys at once.", ephemeral=True)
            return


        # Ensure user has balance
        if user_id not in wallet_balance:
            wallet_balance[user_id] = 0

        if wallet_balance[user_id] < amount:
            await interaction.response.send_message("❌ You don't have enough packlys to gamble that many.", ephemeral=True)
            return

        # Deduct packs immediately
        wallet_balance[user_id] -= amount

        await interaction.response.defer()

        suspense = discord.Embed(
            title=f"🎲 Gambling {amount} packly{'s' if amount > 1 else ''}...",
            description="Rolling the dice...",
            color=discord.Color.dark_grey()
        )
        suspense.set_footer(text="Good luck...")
        msg = await interaction.followup.send(embed=suspense)

        await asyncio.sleep(2)

        # Always 50/50 win chance
        result = "win" if random.choice([True, False]) else "lose"

        if result == "win":
            reward = amount * 2
            wallet_balance[user_id] += reward
            suspense.title = f"🎉 You WON {reward} packlys!"
            suspense.color = discord.Color.green()
            suspense.description = f"Luck is on your side. You risked {amount}, and won {reward}!"
        else:
            suspense.title = f"💀 You LOST your {amount} packly{'s' if amount > 1 else ''}!"
            suspense.color = discord.Color.red()
            suspense.description = "Bad luck... you lost it all."

        await msg.edit(embed=suspenseds)

        # Optional log
        log_channel_id = 1361522228021297404
        log_channel = self.bot.get_channel(log_channel_id)
        if log_channel:
            await log_channel.send(
                f"🎲 **{interaction.user.mention}** gambled `{amount}` packlys and **{result.upper()}**.\n"
                f"🎯 Win chance: `50%`\n"
                f"📦 New balance: `{wallet_balance[user_id]}`"
            )

    
    # Command to check wallet balance
    @app_commands.command(name="wallet", description="Check your wallet balance")
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    async def wallet(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        username = interaction.user.name

        # Show tutorial once per user
        if user_id not in self.bot_walletturorial_seen:
            tutorial_embed = discord.Embed(
                title="Welcome To The Packlys Wallet Command!",
                description=(
                    "Use `/packs wallet` to check your packlys balance.\n"
                    "- You start with 0 Packlys.\n"
                    "- To get more packlys, you have to ask the owners of FootballDex to add them!\n"
                    "- Join **[FootballDex](https://discord.gg/footballdex) to get free packlys!**\n"
                    "- These packlys can be used for `/packs packlys` `/packs multipackly` and `/packs gamblepack`\n"
                    "Enjoy!"
                ),
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=tutorial_embed, ephemeral=True)
            self.bot_walletturorial_seen.add(user_id)
            return  # Stop here, so user reads tutorial first
        
        # Get the user's pack balance (defaults to 0 if they haven't added any packs)
        balance = wallet_balance.get(user_id, 0)
        
        embed = discord.Embed(
            title=f"{username}'s Wallet",
            description=f"You currently have **{balance}** packly(s).",
            color=discord.Color.green()
        )
        embed.set_footer(text="FootballDex Wallet")
        
        # Send the wallet balance as an embed
        await interaction.response.send_message(embed=embed, ephemeral=False)