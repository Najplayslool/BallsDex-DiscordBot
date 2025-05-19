import discord
from discord.ext import commands
from discord.ui import View, Button, button
from discord import app_commands, Interaction, Embed, ButtonStyle
from discord.ext import commands


class FaqView(View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=120)
        self.user = user
        self.current_page = 0
        self.pages = self.build_pages()

    def build_pages(self):
        return [
            discord.Embed(
                title="❓ What is FootballDex?",
                description=(
                    "FootballDex is a collectible football-themed game. You collect, trade, "
                    "unique footballers with stats and rarities!"
                ),
                color=discord.Color.blurple()
            ).set_footer(text="Page 1 of 4"),

            discord.Embed(
                title="📦 How do I get packs?",
                description=(
                    "Use `/packs daily` and `/packs weekly` to claim free packs. You can also earn more via giveaways, or join the discord server **[FootballDex](https://discord.gg/fotoballdex). **"
                ),
                color=discord.Color.green()
            ).set_footer(text="Page 2 of 4"),

            discord.Embed(
                title="⚔️ What can I do with my footballers?",
                description=(
                    "You can view them with `/players list`, trade them with others using `/trade begin`, "
                    "or view with them using `/players info`. More features coming soon!"
                ),
                color=discord.Color.orange()
            ).set_footer(text="Page 3 of 4"),

            discord.Embed(
                title="🤔 How can i get more footballers?",
                description=(
                    "You can get more Footballers by catching them when the bot spawns the Footballers, and join the discord **[FootballDex](https://discord.gg/footballdex)** "
                    "to take part in gieaways and daily admin spawns!"
                ),
                color=discord.Color.yellow()
            ).set_footer(text="Page 4 of 4"),
        ]

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This is not your FAQ menu.", ephemeral=True)
            return False
        return True

    @button(label="Previous", style=ButtonStyle.primary, row=0)
    async def previous_button(self, interaction: Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @button(label="Next", style=ButtonStyle.success, row=0)
    async def next_button(self, interaction: Interaction, button: Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @button(label="Close", style=ButtonStyle.danger, row=1)
    async def close_button(self, interaction: Interaction, button: Button):
        await interaction.response.edit_message(content="Closed.", embed=None, view=None)


class GuideView(View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=120)
        self.user = user
        self.pages = [
            self.page_intro(),
            self.page_players(),
            self.page_packs(),
            self.page_profile(),
        ]
        self.current_page = 0
        self.message = None  # will be set after sending the message
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()

        if self.current_page > 0:
            prev_btn = Button(label="Previous", style=discord.ButtonStyle.primary, custom_id="prev")
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)

        if self.current_page < len(self.pages) - 1:
            next_btn = Button(label="Next", style=discord.ButtonStyle.success, custom_id="next")
            next_btn.callback = self.next_page
            self.add_item(next_btn)

        close_btn = Button(label="Close", style=discord.ButtonStyle.danger, custom_id="close")
        close_btn.callback = self.close_view
        self.add_item(close_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("You can't interact with this guide.", ephemeral=True)
            return False
        return True

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    async def close_view(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Closed.", embed=None, view=None)


    async def on_timeout(self):
        self.clear_items()
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

    def page_intro(self):
        embed = discord.Embed(
            title="📘 Welcome to FootballDex!",
            description=(
                "**What is FootballDex?**\n"
                "FootballDex is a collectible football-themed game where players collect, trade, and show off "
                "unique countryball-style footballers with stats, rarities, and special features. You can open packs, "
                "complete your FootballDex completion, customize your profile, and interact with other players. Strategies like gambling to "
                "keep the game dynamic and rewarding. Every player can get their favourite Footballer, "
                "Stay active, check your dailys, weeklys, and become a top collector!"
            ),
            color=discord.Color.blue()
        )
        embed.set_image(url="https://i.imgur.com/EBFu8IX.png")
        embed.set_footer(text="Page 1 of 4 - Introduction")
        return embed

    def page_players(self):
        embed = discord.Embed(
            title="👥 Player Commands",
            description=(
                "`/players last` - See the last player you caught.\n"
                "`/players list` - List all the players you've collected.\n"
                "`/players completion` - View your completion stats for your Footballers."
            ),
            color=discord.Color.green()
        )
        embed.set_image(url="https://i.imgur.com/rSzVNPi.png")
        embed.set_footer(text="Page 2 of 4 - Player Commands")
        return embed

    def page_packs(self):
        embed = discord.Embed(
            title="🎁 Pack Commands",
            description=(
                "`/packs daily` - Claim a daily pack (account must be 14 days old).\n"
                "`/packs weekly` - Claim a weekly pack (account must be 14 days old)."
            ),
            color=discord.Color.orange()
        )
        embed.set_image(url="https://i.imgur.com/cokBPUf.png")
        embed.set_footer(text="Page 3 of 4 - Pack Commands")
        return embed

    def page_profile(self):
        embed = discord.Embed(
            title="👤 Profile Commands",
            description=(
                "`/profile view` - View your profile.\n"
                "`/profile change` - Change your profile avatar, banner.\n"
                "`/profile bio` - Set a bio.\n"
                "`/profile block` - Block another user.\n"
                "`/profile unblock` - Unblock a previously blocked user."
            ),
            color=discord.Color.purple()
        )
        embed.set_image(url="https://i.imgur.com/wSnTTyj.png")
        embed.set_footer(text="Page 4 of 4 - Profile Commands")
        return embed

class Guide(commands.GroupCog, name="guide"):
    def __init__(self, bot):
        self.bot = bot


    @app_commands.command(name="begin", description="Open the guide for FootballDex.")
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def guide(self, interaction: discord.Interaction):
        view = GuideView(user=interaction.user)
        await interaction.response.send_message(embed=view.pages[0], view=view, ephemeral=True)
        view.message = await interaction.original_response()

    @app_commands.command(name="faq", description="Read the most frequently asked questions.")
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def faq(self, interaction: Interaction):
        view = FaqView(user=interaction.user)
        await interaction.response.send_message(embed=view.pages[0], view=view, ephemeral=True)
