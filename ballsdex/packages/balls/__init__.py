from typing import TYPE_CHECKING

from ballsdex.packages.balls.cog import Bɑlls

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Balls(bot))
