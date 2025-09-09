from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands, Interaction
from datetime import datetime, timedelta, timezone
import random
from tortoise.exceptions import IntegrityError
from discord import Embed, Color, File, Colour
from tortoise import models, fields
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw, ImageFont
from discord.ui import View
import asyncio
import logging
from tortoise.exceptions import DoesNotExist
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

async def delete_ball_if_possible(ball, interaction) -> bool:
    trade_refs = await TradeObject.filter(ballinstance_id=ball.id).exists()
    if trade_refs:
        await interaction.followup.send(
            f"⚠️ The ball `{ball}` is currently involved in a trade and can't be deleted.",
            ephemeral=True
        )
        return False
    try:
        await ball.delete()
        return True
    except IntegrityError:
        await interaction.followup.send(
            f"⚠️ Could not delete the ball `{ball}` due to a database integrity error.",
            ephemeral=True
        )
        return False
    except Exception as e:
        await interaction.followup.send(
            f"❌ Unexpected error deleting `{ball}`: `{e}`",
            ephemeral=True
        )
        return False


class CoinFlip(commands.GroupCog, name="bet"):
    def __init__(self, bot):
        self.bot = bot
        # Active coin flips: key = channel id, value = dict with player data
        self.active_flips = {}
        self.coinflip_sessions = {}

    @app_commands.command(name="start", description="Start a Bet duel with a footballer")
    @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
    @app_commands.describe(
        countryball="Your footballer",
        opponent="pick who to challenge"
    )
    async def cf_start(
        self,
        interaction: Interaction,
        countryball: BallInstanceTransform,
        opponent: discord.Member,
    ):
        if opponent.id == interaction.user.id:
            await interaction.response.send_message("❌ You cannot bet against yourself!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        channel_id = interaction.channel_id
        user_id = interaction.user.id

        # ✅ Check if the user is already in the best trying to make a new one
        for session in self.coinflip_sessions.values():
            if session.get("challenged_user") == user_id:
                await interaction.followup.send(
                    "❌ You're already challenged in a bet! You must wait or cancel the current bet first.",
                    ephemeral=True
                )
                return

        # ✅ Check if bot can send messages before doing anything
        if not interaction.channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.followup.send("I can't send messages in this channel.", ephemeral=True)
            return

        # ✅ If opponent is provided, make sure they're still in the guild
        try:
            await interaction.guild.fetch_member(opponent.id)
        except discord.NotFound:
            await interaction.followup.send("❌ The selected opponent is no longer in this server.", ephemeral=True)
            return

        # ✅ Check if the same footballer is being used in another session
        for ch_id, s in self.coinflip_sessions.items():
            for p in s["players"].values():
                if countryball in p["balls"]:
                    await interaction.followup.send("This footballer is already used in another bet.", ephemeral=True)
                    return

        session = self.coinflip_sessions.get(channel_id)

        if session:
            # ✅ If this session is private, block other users
            if session.get("challenged_user") and user_id != session["challenged_user"]:
                await interaction.followup.send("This bet is only open to a specific opponent.", ephemeral=True)
                return

            if user_id in session["players"]:
                await interaction.followup.send("You're already part of this Bet.", ephemeral=True)
                return

            if len(session["players"]) >= 2:
                await interaction.followup.send("This Bet already has two players.", ephemeral=True)
                return

            session["players"][user_id] = {"balls": [countryball], "locked": False}

            await interaction.followup.send(
                f"🪙 <@{user_id}> joined the Bet with **{countryball}**!",
                ephemeral=False
            )
        else:
            players = {
                user_id: {"balls": [countryball], "locked": False}
            }
            if opponent:
                players[opponent.id] = {"balls": [], "locked": False}

            self.coinflip_sessions[channel_id] = {
                "players": players,
                "challenged_user": opponent.id if opponent else None
            }

        if opponent:
            challenge_embed = discord.Embed(
                title="🎯 Bet Challenge Sent!",
                description=(
                    f"**{interaction.user.display_name}** has placed **{countryball}** and is waiting for an opponent!\n"
                    f"<@{user_id}> has challenged <@{opponent.id}> to a footballer Bet!"
                ),
                color=discord.Color.orange()
            )
            challenge_embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else discord.Embed.Empty)
            challenge_embed.set_footer(text="Waiting for the opponent to join using /bet add")
            await interaction.channel.send(embed=challenge_embed)


    @app_commands.command(name="add", description="Add your footballer to the active Bet")
    @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
    @app_commands.describe(countryball="Your footballer")
    async def cf_add(self, interaction: Interaction, countryball: BallInstanceTransform):
        await interaction.response.defer(ephemeral=True)  # defer privately for errors

        channel_id = interaction.channel_id
        user_id = interaction.user.id
        session = self.coinflip_sessions.get(channel_id)

        if not session or user_id not in session["players"]:
            await interaction.followup.send("You're not part of an active Bet in this channel.", ephemeral=True)
            return

        # ✅ Duplicate check
        if any(ball.id == countryball.id for ball in session["players"][user_id]["balls"]):
            await interaction.followup.send("⚠️ You already added this footballer to the Bet!", ephemeral=True)
            return

        session["players"][user_id]["balls"].append(countryball)


        # Build a public embed showing both players & their balls
        embed = discord.Embed(
            title="🪙 FootballDex Bets",
            description="Here are the footballers each player has added so far:",
            color=discord.Color.gold()
        )

        for pid, pdata in session["players"].items():
            user = await self.bot.fetch_user(pid)
            ball_names = []
            for ball_instance in pdata["balls"]:
                ball_names.append(str(ball_instance))
            embed.add_field(
                name=f"{user.display_name}'s footballers:",
                value=", ".join(ball_names) if ball_names else "No footballers added",
                inline=False,
            )

        # ⬇️ Public embed showing current state
        embed = discord.Embed(
            title="⚽ FootballDex Bet Update",
            description="Footballers added to the current bet:",
            color=discord.Color.gold()
        )

        for pid, pdata in session["players"].items():
            user = await self.bot.fetch_user(pid)
            ball_lines = []

            for ball_instance in pdata["balls"]:
                await ball_instance.fetch_related("ball")
                emoji = self.bot.get_emoji(ball_instance.ball.emoji_id) or ""
                ball_lines.append(f"{emoji} {ball_instance}")

            embed.add_field(
                name=f"{user.display_name}'s footballers:",
                value="\n".join(ball_lines) if ball_lines else "No footballers added",
                inline=False,
            )

        embed.set_footer(text="Both players must lock in using /bet lock.")
        embed.timestamp = discord.utils.utcnow()

        # ⬇️ Ephemeral confirmation
        await interaction.followup.send(
            embed=discord.Embed(
                title="✅ Footballer Added",
                description=f"You successfully added **{countryball}** to the bet!",
                color=discord.Color.green()
            ),
            ephemeral=True
        )

        # ⬇️ Public state update
        await interaction.followup.send(embed=embed, ephemeral=False)

    @app_commands.command(name="cancel", description="Cancel the current Bet")
    @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
    async def cf_cancel(self, interaction: Interaction):
        channel_id = interaction.channel_id
        user_id = interaction.user.id

        session = self.coinflip_sessions.get(channel_id)

        if not session:
            await interaction.response.send_message("❌ There's no active Bets in this channel.", ephemeral=True)
            return

        if user_id not in session["players"]:
            await interaction.response.send_message("❌ You're not part of this Bet.", ephemeral=True)
            return

        # Optionally notify both players
        players = session["players"]
        del self.coinflip_sessions[channel_id]

        embed = discord.Embed(
            title="🪙 FootballDex Bet Cancelled",
            description=f"**{interaction.user.mention}** has cancelled the Bet.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="lock", description="Lock in your footballers and start the Bet")
    @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
    async def cf_lock(self, interaction: Interaction):
        await interaction.response.defer()

        player_id = interaction.user.id
        session = self.coinflip_sessions.get(interaction.channel_id)

        if not session or player_id not in session["players"]:
            await interaction.followup.send("⚠️ You're not part of an active Bet in this channel.", ephemeral=True)
            return

        session["players"][player_id]["locked"] = True
        players = session["players"]

        if len(players) < 2:
            await interaction.followup.send("✅ You've locked in! Waiting for another player to join...", ephemeral=True)
            return

        if all(p["locked"] for p in players.values()):
            player_ids = list(players.keys())
            random.shuffle(player_ids)
            winner_id = player_ids[0]
            loser_id = player_ids[1]

            # Log the result to log channel
            log_channel_id = 981627349869142036
            log_channel = self.bot.get_channel(log_channel_id)

            if log_channel:
                total_balls = len(players[winner_id]["balls"]) + len(players[loser_id]["balls"])
                await log_channel.send(
                    f"🪙 **FootballDex Bet Result**\n"
                    f"👑 Winner: <@{winner_id}>\n"
                    f"💀 Loser: <@{loser_id}>\n"
                    f"🎁 Winner won `{total_balls}` footballer{'s' if total_balls != 1 else ''}."
                )

            winner_balls = players[winner_id]["balls"]
            loser_balls = players[loser_id]["balls"]

            winner_player, _ = await Player.get_or_create(discord_id=winner_id)

            # Transfer loser's balls to winner
            for ball in loser_balls:
                await ball.fetch_related("ball")

                try:
                    trade_obj = await ball.tradeobject
                    await trade_obj.delete()
                except (AttributeError, DoesNotExist):
                    pass

                ball.player = winner_player
                await ball.save()

            async def ball_name(ball_instance):
                await ball_instance.fetch_related("ball")
                return ball_instance.ball.country

            winner_str = [await ball_name(b) for b in winner_balls]
            loser_str = [await ball_name(b) for b in loser_balls]

            # Send a friendly ephemeral confirmation to the winner who just locked in
            await interaction.followup.send("✅ You've locked in! Both players are locked, processing results...", ephemeral=True)

            # Create a nice embed to announce results publicly
            result_embed = Embed(
                title="⚔️ FootballDex Bet Results",
                description=(
                    f"👑 **Winner:** <@{winner_id}>\n"
                    f"💀 **Loser:** <@{loser_id}>\n\n"
                    f"🎁 **<@{winner_id}>'s Footballers:** {', '.join(winner_str)} + {', '.join(loser_str)}\n"
                    f"⚠️ **<@{loser_id}>'s Footballers:** {', '.join(loser_str)} *(lost)*"
                ),
                colour=Colour.gold(),
            )
            result_embed.set_footer(text="Thanks for playing the FootballDex Bet!")

            await interaction.channel.send(embed=result_embed)

            del self.coinflip_sessions[interaction.channel_id]

        else:
            await interaction.followup.send("✅ You've locked in! Waiting for the other player...", ephemeral=True)
