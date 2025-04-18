from typing import TYPE_CHECKING

from ballsdex.packages.choosepacks.cog import ChoosePack

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(ChoosePack(bot))