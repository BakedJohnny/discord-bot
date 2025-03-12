
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from sqlalchemy.orm import Session
from models import SoloFight, SessionLocal

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

bot = commands.Bot(command_prefix='!')

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.command(name='addsolo')
async def add_solo(ctx, *, entry: str):
    try:
        world, location, dungeon, mob_name, mob_types, notes = map(str.strip, entry.split('-'))
        db: Session = next(get_db())
        solo_fight = SoloFight(world=world, location=location, dungeon=dungeon, mob_name=mob_name, mob_types=mob_types, notes=notes)
        db.add(solo_fight)
        db.commit()
        await ctx.send(f"Entry added: {solo_fight}")
    except ValueError:
        await ctx.send("Invalid entry format. Please use: /addsolo <world> - <location> - <dungeon> - <mob name> - <mob type(s)> - <notes>")

@bot.command(name='soloview')
async def solo_view(ctx, *, criteria: str):
    criteria = criteria.strip().lower()
    db: Session = next(get_db())
    results = db.query(SoloFight).filter(
        (SoloFight.world.ilike(f"%{criteria}%")) |
        (SoloFight.location.ilike(f"%{criteria}%")) |
        (SoloFight.dungeon.ilike(f"%{criteria}%")) |
        (SoloFight.mob_name.ilike(f"%{criteria}%")) |
        (SoloFight.mob_types.ilike(f"%{criteria}%"))
    ).all()
    
    if results:
        response = "\n".join([f"{entry.world} - {entry.location} - {entry.dungeon} - {entry.mob_name} - {entry.mob_types} - {entry.notes}" for entry in results])
        await ctx.send(f"Entries matching '{criteria}':\n{response}")
    else:
        await ctx.send(f"No entries found matching '{criteria}'")

bot.run(TOKEN)