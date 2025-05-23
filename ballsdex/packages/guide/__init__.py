from typing import TYPE_CHECKING

from ballsdex.packages.guide.cog import Guide

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Guide(bot))