import random
import discord
from discord import app_commands
from discord.ext import commands
from tortoise.exceptions import DoesNotExist
from random import sample

from ballsdex.core.models import Ball, BallInstance
from ballsdex.core.models import Player

AUTHORIZED_GIVERS = {767663084890226689, 749658746535280771, 1096501882224136222}

def format_ball_embed_field(ball, atk, hp):
    emoji = f"<:{ball.country.lower()}:{ball.emoji_id}>" if ball.emoji_id else ""
    return f"{emoji} **{ball.country}**\nRarity: `{ball.rarity}`\nATK: `{atk}` | HP: `{hp}`"

class ChooseButton(discord.ui.Button):
    def __init__(self, ball, atk, hp, view):
        super().__init__(label=f"Pick {ball.country}", style=discord.ButtonStyle.green)
        self.ball = ball
        self.atk = atk
        self.hp = hp
        self.view_obj = view

    async def callback(self, interaction: discord.Interaction):
        if self.view_obj.picked_user_id and self.view_obj.picked_user_id != interaction.user.id:
            return await interaction.response.send_message("Someone already picked a footballer!", ephemeral=True)

        self.view_obj.picked_user_id = interaction.user.id
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        await BallInstance.create(
            ball=self.ball,
            player=player,
            attack_bonus=self.atk,
            health_bonus=self.hp,
        )

        for item in self.view_obj.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        await interaction.response.edit_message(
            content=f"You picked **{self.ball.country}**! 🎉", view=self.view_obj
        )
        self.view_obj.stop()

class ChooseView(discord.ui.View):
    def __init__(self, ball_choices):
        super().__init__(timeout=60)
        self.picked_user_id = None
        for ball, atk, hp in ball_choices:
            self.add_item(ChooseButton(ball=ball, atk=atk, hp=hp, view=self))

class ChoosePack(commands.GroupCog, name="pick"):
    def __init__(self, bot):
        self.bot = bot
        self.wallet = {}
        self.claimed_once = set()

    @app_commands.command(name="choose", description="Pick 1 out of 3 footballers.")
    async def choose(self, interaction: discord.Interaction):
        uid = interaction.user.id
        if uid in self.claimed_once:
            if self.wallet.get(uid, 0) <= 0:
                return await interaction.response.send_message("You don't have any pick credits left!", ephemeral=True)
            self.wallet[uid] -= 1
        else:
            self.claimed_once.add(uid)

        balls = await Ball.filter(rarity__gte=2.5, rarity__lte=30.0)
        # Shuffle and grab 3 random balls
        random.shuffle(balls)
        if len(balls) < 3:
            await interaction.response.send_message("Not enough valid balls available to choose from.", ephemeral=True)
            return
        selected = random.sample(balls, 3)

        selected = random.sample(balls, 3)
        choices = [(ball, random.randint(1, 10), random.randint(1, 10)) for ball in selected]

        embed = discord.Embed(
            title="Choose a Ball!",
            description="Pick one of the following options:",
            color=discord.Color.gold(),
        )
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        for i, (ball, atk, hp) in enumerate(choices):
            embed.add_field(name=f"Option #{i + 1}", value=format_ball_embed_field(ball, atk, hp), inline=False)

        await interaction.response.send_message(
            content=f"{interaction.user.mention}, choose wisely!",
            embed=embed,
            view=ChooseView(choices)
        )

    @app_commands.command(name="wallet", description="Check your pick balance.")
    async def balance(self, interaction: discord.Interaction):
        uid = interaction.user.id
        picks = self.wallet.get(uid, 0)
        embed = discord.Embed(title="🤑 Pick Balance", color=discord.Color.blurple())
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        embed.description = f"You have **{picks}** pick(s) left."
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="add", description="Give someone more pick credits.")
    @app_commands.describe(user="User to give picks to", amount="Number of picks to add")
    async def add(self, interaction: discord.Interaction, user: discord.User, amount: int):
        if interaction.user.id not in AUTHORIZED_GIVERS:
            return await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

        self.wallet[user.id] = self.wallet.get(user.id, 0) + amount

        embed = discord.Embed(
            title="Picks Added",
            description=f"**{user.mention}** received **{amount}** pick(s)!",
            color=discord.Color.green(),
        )
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

