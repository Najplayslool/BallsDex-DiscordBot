from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands, Interaction
from datetime import datetime, timedelta, timezone
import random
from tortoise.exceptions import IntegrityError
from discord import Embed, Color, File
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
    @app_commands.describe(countryball="Your footballer")
    async def cf_start(self, interaction: Interaction, countryball: BallInstanceTransform):
        await interaction.response.defer(ephemeral=True)
        channel_id = interaction.channel_id
        user_id = interaction.user.id

        session = self.coinflip_sessions.get(channel_id)

        if session:
            if user_id in session["players"]:
                await interaction.followup.send("You're already part of this Bet.", ephemeral=True)
                return

            if len(session["players"]) >= 2:
                await interaction.followup.send("This Bet already has two players.", ephemeral=True)
                return

            session["players"][user_id] = {"balls": [countryball], "locked": False}

            await interaction.followup.send(
                f"🪙 <@{user_id}> started a Bet with **{countryball}**!\nAnother player can use `/Bet` to join.",
                ephemeral=False
            )

        else:
            self.coinflip_sessions[channel_id] = {
                "players": {
                    user_id: {"balls": [countryball], "locked": False}
                }
            }

            await interaction.followup.send(
                f"🪙 <@{user_id}> started a Bet with **{countryball}**!\n"
                f"Another player can use `/bet start` to join."
            )

        embed = discord.Embed(
        title="🪙 FootballDex Bet started!",
        description=f"**{interaction.user.display_name}** has placed **{countryball}** and is waiting for an opponent!\nUse `/bet start` to join.",
        color=discord.Color.gold())
        embed.set_footer(text="Once two players join, you can lock in your bet.")

        await interaction.channel.send(embed=embed)

    @app_commands.command(name="add", description="Add your footballer to the active Bet")
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

        # Send a private confirmation to the user who added the ball
        await interaction.followup.send(
            f"✅ You added **{countryball}** to your Bet!",
            ephemeral=True
        )
        # Send a public embed showing the whole current state to the channel
        await interaction.followup.send(embed=embed, ephemeral=False)

    @app_commands.command(name="cancel", description="Cancel the current Bet")
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
    async def cf_lock(self, interaction: Interaction):
        await interaction.response.defer()

        player_id = interaction.user.id
        session = self.coinflip_sessions.get(interaction.channel_id)

        if not session or player_id not in session["players"]:
            await interaction.followup.send("You're not part of an active Bet in this channel.", ephemeral=True)
            return

        session["players"][player_id]["locked"] = True
        players = session["players"]

        if all(p["locked"] for p in players.values()):
            winner_id = random.choice(list(players.keys()))
            loser_id = next(pid for pid in players.keys() if pid != winner_id)

            # Log the result
            log_channel_id = 981627349869142036
            log_channel = self.bot.get_channel(log_channel_id)

            if log_channel:
                total_balls = len(session["players"][winner_id]["balls"]) + len(session["players"][loser_id]["balls"])
                await log_channel.send(
                    f"🪙 **FootballDex Bet Result**\n"
                    f"👑 Winner: <@{winner_id}>\n"
                    f"💀 Loser: <@{loser_id}>\n"
                    f"🎁 Winner won `{total_balls}` footballer{'s' if total_balls != 1 else ''}."
                )

            winner_balls = players[winner_id]["balls"]
            loser_balls = players[loser_id]["balls"]

            winner_player, _ = await Player.get_or_create(discord_id=winner_id)

            # Transfer loser's balls to the winner
            for ball in loser_balls:
                await ball.fetch_related("ball")

                # Delete any trade object linking this ball
                try:
                    trade_obj = await ball.tradeobject
                    await trade_obj.delete()
                except (AttributeError, DoesNotExist):
                    pass

                # Instead of deleting, just reassign to winner
                ball.player = winner_player
                await ball.save()

            async def ball_name(ball_instance):
                await ball_instance.fetch_related("ball")
                return ball_instance.ball.country

            winner_str = [await ball_name(b) for b in winner_balls]
            loser_str = [await ball_name(b) for b in loser_balls]

            await interaction.followup.send(
                f"🎉 **<@{winner_id}> wins the Bet!** 🎉\n"
                f"**Winner's footballers:** {', '.join(winner_str)} + {', '.join(loser_str)}\n"
                f"**Loser's footballers:** {', '.join(loser_str)} *(lost)*"
            )

            del self.coinflip_sessions[interaction.channel_id]

        else:
            await interaction.followup.send("You've locked in! Waiting for the other player...", ephemeral=True)

