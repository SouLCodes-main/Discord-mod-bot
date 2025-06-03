import discord
from discord.ext import commands, tasks
import asyncio
import json
import sqlite3
from datetime import datetime, timedelta
import logging
import os
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") 

debug_mode = os.getenv("DEBUG")

print(f"BOT_TOKEN: {BOT_TOKEN}")
print(f"Debug Mode: {debug_mode}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "" 
OWNER_ID =   
PREFIX = '!'

# Database setup
def init_database():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    # Warnings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guild_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Reaction roles table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reaction_roles (
            message_id INTEGER,
            emoji TEXT,
            role_id INTEGER,
            guild_id INTEGER,
            PRIMARY KEY (message_id, emoji)
        )
    ''')
    
    # Muted users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS muted_users (
            user_id INTEGER,
            guild_id INTEGER,
            unmute_time DATETIME,
            PRIMARY KEY (user_id, guild_id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database
init_database()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Service pricing data
SERVICES = {
    "logo_design": {
        "name": "Logo Design",
        "price": "$150 - $300",
        "description": "Professional logo design with 3 revisions included",
        "image": "https://via.placeholder.com/400x300/7289da/ffffff?text=Logo+Design",
        "delivery": "3-5 business days"
    },
    "banner_design": {
        "name": "Banner/Header Design",
        "price": "$75 - $150",
        "description": "Custom banners for social media, websites, or Discord servers",
        "image": "https://via.placeholder.com/400x300/43b581/ffffff?text=Banner+Design",
        "delivery": "1-3 business days"
    },
    "business_card": {
        "name": "Business Card Design",
        "price": "$50 - $100",
        "description": "Professional business card design with print-ready files",
        "image": "https://via.placeholder.com/400x300/faa61a/ffffff?text=Business+Card",
        "delivery": "2-4 business days"
    },
    "branding_package": {
        "name": "Complete Branding Package",
        "price": "$500 - $1000",
        "description": "Logo, business cards, letterhead, and brand guidelines",
        "image": "https://via.placeholder.com/400x300/f04747/ffffff?text=Branding+Package",
        "delivery": "7-10 business days"
    }
}

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_mutes.start()
    
    def cog_unload(self):
        self.check_mutes.cancel()
    
    @tasks.loop(minutes=1)
    async def check_mutes(self):
        """Check for expired mutes"""
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, guild_id FROM muted_users 
            WHERE unmute_time <= datetime('now')
        ''')
        
        expired_mutes = cursor.fetchall()
        
        for user_id, guild_id in expired_mutes:
            guild = self.bot.get_guild(guild_id)
            if guild:
                member = guild.get_member(user_id)
                if member:
                    muted_role = discord.utils.get(guild.roles, name="Muted")
                    if muted_role and muted_role in member.roles:
                        await member.remove_roles(muted_role)
        
        cursor.execute('DELETE FROM muted_users WHERE unmute_time <= datetime("now")')
        conn.commit()
        conn.close()
    
    @check_mutes.before_loop
    async def before_check_mutes(self):
        await self.bot.wait_until_ready()
    
    @commands.slash_command(name="ban", description="Ban a user from the server")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        try:
            await member.ban(reason=f"{ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="🔨 User Banned",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="User", value=f"{member.mention} ({member})", inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=True)
            embed.set_footer(text=f"ID: {member.id}")
            
            await ctx.respond(embed=embed)
            logger.info(f"{ctx.author} banned {member} for: {reason}")
            
        except discord.Forbidden:
            await ctx.respond("❌ I don't have permission to ban this user.", ephemeral=True)
        except Exception as e:
            await ctx.respond(f"❌ An error occurred: {str(e)}", ephemeral=True)
    
    @commands.slash_command(name="kick", description="Kick a user from the server")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        try:
            await member.kick(reason=f"{ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="👢 User Kicked",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="User", value=f"{member.mention} ({member})", inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=True)
            embed.set_footer(text=f"ID: {member.id}")
            
            await ctx.respond(embed=embed)
            logger.info(f"{ctx.author} kicked {member} for: {reason}")
            
        except discord.Forbidden:
            await ctx.respond("❌ I don't have permission to kick this user.", ephemeral=True)
        except Exception as e:
            await ctx.respond(f"❌ An error occurred: {str(e)}", ephemeral=True)
    
    @commands.slash_command(name="mute", description="Mute a user for a specific duration")
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        try:
            # Parse duration (e.g., "1h", "30m", "1d")
            time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
            duration_seconds = 0
            
            if duration[-1] in time_units:
                duration_seconds = int(duration[:-1]) * time_units[duration[-1]]
            else:
                await ctx.respond("❌ Invalid duration format. Use s/m/h/d (e.g., 1h, 30m)", ephemeral=True)
                return
            
            # Get or create muted role
            muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
            if not muted_role:
                muted_role = await ctx.guild.create_role(name="Muted", color=discord.Color.dark_grey())
                
                # Set permissions for muted role
                for channel in ctx.guild.channels:
                    await channel.set_permissions(muted_role, send_messages=False, speak=False)
            
            await member.add_roles(muted_role)
            
            # Store mute in database
            unmute_time = datetime.utcnow() + timedelta(seconds=duration_seconds)
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO muted_users (user_id, guild_id, unmute_time)
                VALUES (?, ?, ?)
            ''', (member.id, ctx.guild.id, unmute_time))
            conn.commit()
            conn.close()
            
            embed = discord.Embed(
                title="🔇 User Muted",
                color=discord.Color.dark_grey(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="User", value=f"{member.mention} ({member})", inline=False)
            embed.add_field(name="Duration", value=duration, inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"ID: {member.id}")
            
            await ctx.respond(embed=embed)
            
        except Exception as e:
            await ctx.respond(f"❌ An error occurred: {str(e)}", ephemeral=True)
    
    @commands.slash_command(name="unmute", description="Remove mute from a user")
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member):
        try:
            muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
            if muted_role and muted_role in member.roles:
                await member.remove_roles(muted_role)
                
                # Remove from database
                conn = sqlite3.connect('bot_data.db')
                cursor = conn.cursor()
                cursor.execute('DELETE FROM muted_users WHERE user_id = ? AND guild_id = ?',
                             (member.id, ctx.guild.id))
                conn.commit()
                conn.close()
                
                embed = discord.Embed(
                    title="🔊 User Unmuted",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="User", value=f"{member.mention} ({member})", inline=False)
                embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
                
                await ctx.respond(embed=embed)
            else:
                await ctx.respond("❌ This user is not muted.", ephemeral=True)
                
        except Exception as e:
            await ctx.respond(f"❌ An error occurred: {str(e)}", ephemeral=True)
    
    @commands.slash_command(name="warn", description="Warn a user and log the warning")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str):
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO warnings (user_id, guild_id, moderator_id, reason)
            VALUES (?, ?, ?, ?)
        ''', (member.id, ctx.guild.id, ctx.author.id, reason))
        
        cursor.execute('''
            SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?
        ''', (member.id, ctx.guild.id))
        
        warning_count = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="⚠️ User Warned",
            color=discord.Color.yellow(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="User", value=f"{member.mention} ({member})", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Warning Count", value=f"{warning_count}", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"ID: {member.id}")
        
        await ctx.respond(embed=embed)
        
        # Try to DM the user
        try:
            dm_embed = discord.Embed(
                title="⚠️ You have been warned",
                description=f"You have been warned in **{ctx.guild.name}**",
                color=discord.Color.yellow()
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Total Warnings", value=f"{warning_count}", inline=True)
            await member.send(embed=dm_embed)
        except:
            pass
    
    @commands.slash_command(name="clear", description="Delete a number of messages from the channel")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int):
        if amount < 1 or amount > 100:
            await ctx.respond("❌ Amount must be between 1 and 100.", ephemeral=True)
            return
        
        try:
            deleted = await ctx.channel.purge(limit=amount)
            
            embed = discord.Embed(
                title="🧹 Messages Cleared",
                description=f"Deleted {len(deleted)} messages",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
            
            await ctx.respond(embed=embed, delete_after=5)
            
        except Exception as e:
            await ctx.respond(f"❌ An error occurred: {str(e)}", ephemeral=True)
    
    @commands.slash_command(name="lock", description="Lock the channel (remove send permissions)")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
            
            embed = discord.Embed(
                title="🔒 Channel Locked",
                description=f"{ctx.channel.mention} has been locked",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            
            await ctx.respond(embed=embed)
            
        except Exception as e:
            await ctx.respond(f"❌ An error occurred: {str(e)}", ephemeral=True)
    
    @commands.slash_command(name="unlock", description="Unlock the channel (restore send permissions)")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
            
            embed = discord.Embed(
                title="🔓 Channel Unlocked",
                description=f"{ctx.channel.mention} has been unlocked",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            
            await ctx.respond(embed=embed)
            
        except Exception as e:
            await ctx.respond(f"❌ An error occurred: {str(e)}", ephemeral=True)

class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command(name="say", description="Bot repeats your message")
    @commands.has_permissions(manage_messages=True)
    async def say(self, ctx, *, message: str):
        await ctx.channel.send(message)
        await ctx.respond("✅ Message sent!", ephemeral=True)
    
    @commands.slash_command(name="poll", description="Create a poll with options")
    async def poll(self, ctx, question: str, options: str):
        option_list = [opt.strip() for opt in options.split(',')]
        
        if len(option_list) < 2 or len(option_list) > 10:
            await ctx.respond("❌ Please provide 2-10 options separated by commas.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📊 Poll",
            description=question,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
        
        for i, option in enumerate(option_list):
            embed.add_field(name=f"{reactions[i]} {option}", value="\u200b", inline=False)
        
        embed.set_footer(text=f"Poll by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        
        await ctx.respond("Poll created!", ephemeral=True)
        message = await ctx.followup.send(embed=embed)
        
        for i in range(len(option_list)):
            await message.add_reaction(reactions[i])
    
    @commands.slash_command(name="giveaway", description="Start a giveaway")
    @commands.has_permissions(manage_messages=True)
    async def giveaway(self, ctx, duration: str, *, prize: str):
        # Parse duration
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        duration_seconds = 0
        
        if duration[-1] in time_units:
            duration_seconds = int(duration[:-1]) * time_units[duration[-1]]
        else:
            await ctx.respond("❌ Invalid duration format. Use s/m/h/d (e.g., 1h, 30m)", ephemeral=True)
            return
        
        end_time = datetime.utcnow() + timedelta(seconds=duration_seconds)
        
        embed = discord.Embed(
            title="🎉 GIVEAWAY! 🎉",
            description=f"**Prize:** {prize}\n\n**How to enter:** React with 🎉\n**Ends:** <t:{int(end_time.timestamp())}:R>",
            color=discord.Color.gold(),
            timestamp=end_time
        )
        embed.set_footer(text="Ends at")
        
        await ctx.respond("Giveaway started!", ephemeral=True)
        message = await ctx.followup.send(embed=embed)
        await message.add_reaction("🎉")
        
        # Schedule giveaway end (simplified - in production, use a proper task scheduler)
        await asyncio.sleep(duration_seconds)
        
        # Get updated message
        try:
            message = await ctx.channel.fetch_message(message.id)
            reaction = discord.utils.get(message.reactions, emoji="🎉")
            
            if reaction and reaction.count > 1:
                users = [user async for user in reaction.users() if not user.bot]
                if users:
                    import random
                    winner = random.choice(users)
                    
                    embed = discord.Embed(
                        title="🎉 Giveaway Ended! 🎉",
                        description=f"**Winner:** {winner.mention}\n**Prize:** {prize}",
                        color=discord.Color.gold()
                    )
                    await ctx.followup.send(embed=embed)
                else:
                    await ctx.followup.send("❌ No valid entries for the giveaway.")
            else:
                await ctx.followup.send("❌ No one entered the giveaway.")
        except:
            pass
    
    @commands.slash_command(name="botinfo", description="Shows information about the bot")
    async def botinfo(self, ctx):
        embed = discord.Embed(
            title="🤖 Bot Information",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="Bot Name", value=self.bot.user.name, inline=True)
        embed.add_field(name="Bot ID", value=self.bot.user.id, inline=True)
        embed.add_field(name="Created", value=f"<t:{int(self.bot.user.created_at.timestamp())}:F>", inline=True)
        embed.add_field(name="Servers", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="Users", value=len(self.bot.users), inline=True)
        embed.add_field(name="Python Version", value="3.8+", inline=True)
        embed.add_field(name="Discord.py Version", value=discord.__version__, inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.set_footer(text="Professional Discord Bot for Graphic Design Services")
        
        await ctx.respond(embed=embed)

class ServicesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command(name="services", description="Display available graphic design services")
    async def services(self, ctx):
        embed = discord.Embed(
            title="🎨 Graphic Design Services",
            description="Professional design services available",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        
        for service_key, service in SERVICES.items():
            embed.add_field(
                name=f"{service['name']} - {service['price']}",
                value=f"{service['description']}\n⏱️ {service['delivery']}",
                inline=False
            )
        
        embed.set_footer(text="Use /service [name] for detailed information about a specific service")
        await ctx.respond(embed=embed)
    
    @commands.slash_command(name="service", description="Get detailed information about a specific service")
    async def service_detail(self, ctx, service_name: str):
        # Find service by name (case insensitive partial match)
        service = None
        service_key = None
        
        for key, svc in SERVICES.items():
            if service_name.lower() in svc['name'].lower() or service_name.lower() in key.lower():
                service = svc
                service_key = key
                break
        
        if not service:
            available_services = ", ".join([svc['name'] for svc in SERVICES.values()])
            await ctx.respond(f"❌ Service not found. Available services: {available_services}", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"🎨 {service['name']}",
            description=service['description'],
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="💰 Pricing", value=service['price'], inline=True)
        embed.add_field(name="⏱️ Delivery Time", value=service['delivery'], inline=True)
        embed.add_field(name="📞 Contact", value="DM for quotes and inquiries", inline=True)
        
        embed.set_image(url=service['image'])
        embed.set_footer(text="Professional graphic design services • High quality guaranteed")
        
        await ctx.respond(embed=embed)

class ReactionRolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command(name="reactionrole", description="Set up reaction roles")
    @commands.has_permissions(manage_roles=True)
    async def setup_reaction_role(self, ctx, message_id: str, emoji: str, role: discord.Role):
        try:
            message_id_int = int(message_id)
            message = await ctx.channel.fetch_message(message_id_int)
            
            # Add reaction to the message
            await message.add_reaction(emoji)
            
            # Store in database
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO reaction_roles (message_id, emoji, role_id, guild_id)
                VALUES (?, ?, ?, ?)
            ''', (message_id_int, emoji, role.id, ctx.guild.id))
            conn.commit()
            conn.close()
            
            embed = discord.Embed(
                title="✅ Reaction Role Set",
                description=f"Reaction {emoji} will give role {role.mention}",
                color=discord.Color.green()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            
        except discord.NotFound:
            await ctx.respond("❌ Message not found.", ephemeral=True)
        except ValueError:
            await ctx.respond("❌ Invalid message ID.", ephemeral=True)
        except Exception as e:
            await ctx.respond(f"❌ An error occurred: {str(e)}", ephemeral=True)
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return
        
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role_id FROM reaction_roles 
            WHERE message_id = ? AND emoji = ? AND guild_id = ?
        ''', (reaction.message.id, str(reaction.emoji), reaction.message.guild.id))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            role = reaction.message.guild.get_role(result[0])
            if role:
                try:
                    await user.add_roles(role)
                except discord.Forbidden:
                    pass
    
    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        if user.bot:
            return
        
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role_id FROM reaction_roles 
            WHERE message_id = ? AND emoji = ? AND guild_id = ?
        ''', (reaction.message.id, str(reaction.emoji), reaction.message.guild.id))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            role = reaction.message.guild.get_role(result[0])
            if role:
                try:
                    await user.remove_roles(role)
                except discord.Forbidden:
                    pass

# Event handlers
@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is in {len(bot.guilds)} guilds')
    
    # Set bot status
    activity = discord.Activity(type=discord.ActivityType.watching, name="for design requests | /services")
    await bot.change_presence(activity=activity)

@bot.event
async def on_member_join(member):
    """Welcome new members"""
    # Find welcome channel (customize channel name as needed)
    welcome_channel = discord.utils.get(member.guild.channels, name='welcome') or \
                     discord.utils.get(member.guild.channels, name='general') or \
                     member.guild.system_channel
    
    if welcome_channel:
        embed = discord.Embed(
            title="🎨 Welcome to the Server!",
            description=f"Hey {member.mention}! Welcome to **{member.guild.name}**!",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="🔍 Check out our services",
            value="Use `/services` to see our graphic design offerings",
            inline=False
        )
        
        embed.add_field(
            name="📞 Need custom work?",
            value="Feel free to DM for custom quotes and consultations",
            inline=False
        )
        
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        embed.set_footer(text=f"Member #{len(member.guild.members)}")
        
        try:
            await welcome_channel.send(embed=embed)
        except discord.Forbidden:
            pass

@bot.event
async def on_application_command_error(ctx, error):
    """Global error handler for slash commands"""
    if isinstance(error, commands.MissingPermissions):
        await ctx.respond("❌ You don't have permission to use this command.", ephemeral=True)
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.respond("❌ I don't have the required permissions to execute this command.", ephemeral=True)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.respond(f"❌ This command is on cooldown. Try again in {error.retry_after:.2f} seconds.", ephemeral=True)
    else:
        logger.error(f"Unhandled error in {ctx.command}: {error}")
        await ctx.respond("❌ An unexpected error occurred. Please try again later.", ephemeral=True)

# Add cogs
bot.add_cog(ModerationCog(bot))
bot.add_cog(UtilityCog(bot))
bot.add_cog(ServicesCog(bot))
bot.add_cog(ReactionRolesCog(bot))

# Help command
@bot.slash_command(name="help", description="Show all available commands")
async def help_command(ctx):
    embed = discord.Embed(
        title="🤖 Bot Commands Help",
        description="Here are all the available commands:",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    # Moderation Commands
    mod_commands = [
        "`/ban [user] [reason]` - Ban a user from the server",
        "`/kick [user] [reason]` - Kick a user from the server", 
        "`/mute [user] [duration] [reason]` - Mute a user for specific time",
        "`/unmute [user]` - Remove mute from a user",
        "`/warn [user] [reason]` - Warn a user and log it",
        "`/clear [amount]` - Delete messages from channel",
        "`/lock` - Lock the current channel",
        "`/unlock` - Unlock the current channel"
    ]
    embed.add_field(name="🛡️ Moderation", value="\n".join(mod_commands), inline=False)
    
    # Utility Commands
    util_commands = [
        "`/say [message]` - Bot repeats your message",
        "`/poll [question] [options]` - Create a poll",
        "`/giveaway [duration] [prize]` - Start a giveaway",
        "`/botinfo` - Show bot information"
    ]
    embed.add_field(name="🔧 Utility", value="\n".join(util_commands), inline=False)
    
    # Service Commands
    service_commands = [
        "`/services` - Display all available services",
        "`/service [name]` - Get detailed service info"
    ]
    embed.add_field(name="🎨 Services", value="\n".join(service_commands), inline=False)
    
    # Reaction Roles
    rr_commands = [
        "`/reactionrole [message_id] [emoji] [role]` - Setup reaction roles"
    ]
    embed.add_field(name="⚡ Reaction Roles", value="\n".join(rr_commands), inline=False)
    
    embed.set_footer(text="Professional Discord Bot • Use slash commands")
    await ctx.respond(embed=embed)

# Additional utility functions
def parse_time(time_str):
    """Parse time string like '1h30m' into seconds"""
    import re
    time_regex = re.compile(r'(\d+)([dhms])')
    matches = time_regex.findall(time_str.lower())
    
    total_seconds = 0
    time_units = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}
    
    for amount, unit in matches:
        total_seconds += int(amount) * time_units.get(unit, 0)
    
    return total_seconds

# Owner-only commands
@bot.slash_command(name="shutdown", description="Shutdown the bot (Owner only)")
async def shutdown(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.respond("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🔌 Shutting Down",
        description="Bot is shutting down...",
        color=discord.Color.red()
    )
    await ctx.respond(embed=embed)
    await bot.close()

@bot.slash_command(name="reload", description="Reload bot cogs (Owner only)")
async def reload_cogs(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.respond("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    try:
        # Remove and re-add cogs
        bot.remove_cog("ModerationCog")
        bot.remove_cog("UtilityCog") 
        bot.remove_cog("ServicesCog")
        bot.remove_cog("ReactionRolesCog")
        
        bot.add_cog(ModerationCog(bot))
        bot.add_cog(UtilityCog(bot))
        bot.add_cog(ServicesCog(bot))
        bot.add_cog(ReactionRolesCog(bot))
        
        await ctx.respond("✅ Cogs reloaded successfully!", ephemeral=True)
    except Exception as e:
        await ctx.respond(f"❌ Error reloading cogs: {str(e)}", ephemeral=True)

# Statistics command
@bot.slash_command(name="stats", description="Show server statistics")
async def stats(ctx):
    guild = ctx.guild
    
    # Count members by status
    online = len([m for m in guild.members if m.status == discord.Status.online])
    idle = len([m for m in guild.members if m.status == discord.Status.idle])
    dnd = len([m for m in guild.members if m.status == discord.Status.dnd])
    offline = len([m for m in guild.members if m.status == discord.Status.offline])
    
    embed = discord.Embed(
        title=f"📊 {guild.name} Statistics",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(name="👥 Total Members", value=guild.member_count, inline=True)
    embed.add_field(name="🟢 Online", value=online, inline=True)
    embed.add_field(name="🟡 Idle", value=idle, inline=True)
    embed.add_field(name="🔴 DND", value=dnd, inline=True)
    embed.add_field(name="⚫ Offline", value=offline, inline=True)
    embed.add_field(name="📁 Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="📝 Text Channels", value=len(guild.text_channels), inline=True)
    embed.add_field(name="🔊 Voice Channels", value=len(guild.voice_channels), inline=True)
    embed.add_field(name="🎭 Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)
    embed.add_field(name="🚀 Boosts", value=guild.premium_subscription_count, inline=True)
    embed.add_field(name="📅 Created", value=f"<t:{int(guild.created_at.timestamp())}:F>", inline=True)
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.set_footer(text=f"Server ID: {guild.id}")
    await ctx.respond(embed=embed)

# User info command
@bot.slash_command(name="userinfo", description="Get information about a user")
async def userinfo(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    
    embed = discord.Embed(
        title=f"👤 User Information - {member}",
        color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(name="🆔 User ID", value=member.id, inline=True)
    embed.add_field(name="📅 Account Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=True)
    embed.add_field(name="📅 Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:F>", inline=True)
    embed.add_field(name="🏆 Highest Role", value=member.top_role.mention, inline=True)
    embed.add_field(name="📱 Status", value=str(member.status).title(), inline=True)
    embed.add_field(name="🤖 Bot", value="Yes" if member.bot else "No", inline=True)
    
    if member.activities:
        activities = []
        for activity in member.activities:
            if isinstance(activity, discord.Game):
                activities.append(f"🎮 Playing {activity.name}")
            elif isinstance(activity, discord.Streaming):
                activities.append(f"📺 Streaming {activity.name}")
            elif isinstance(activity, discord.Listening):
                activities.append(f"🎵 Listening to {activity.name}")
            elif isinstance(activity, discord.Watching):
                activities.append(f"📺 Watching {activity.name}")
        
        if activities:
            embed.add_field(name="🎯 Activities", value="\n".join(activities), inline=False)
    
    # Get warning count
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?', 
                  (member.id, ctx.guild.id))
    warning_count = cursor.fetchone()[0]
    conn.close()
    
    if warning_count > 0:
        embed.add_field(name="⚠️ Warnings", value=warning_count, inline=True)
    
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
    
    embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.respond(embed=embed)

# Avatar command
@bot.slash_command(name="avatar", description="Get a user's avatar")
async def avatar(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    
    embed = discord.Embed(
        title=f"🖼️ {member}'s Avatar",
        color=discord.Color.purple()
    )
    
    if member.avatar:
        embed.set_image(url=member.avatar.url)
        embed.add_field(name="🔗 Avatar URL", value=f"[Click here]({member.avatar.url})", inline=False)
    else:
        embed.description = "This user doesn't have a custom avatar."
    
    await ctx.respond(embed=embed)

# Server info command  
@bot.slash_command(name="serverinfo", description="Get information about the server")
async def serverinfo(ctx):
    guild = ctx.guild
    
    embed = discord.Embed(
        title=f"🏰 {guild.name}",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(name="🆔 Server ID", value=guild.id, inline=True)
    embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
    embed.add_field(name="📅 Created", value=f"<t:{int(guild.created_at.timestamp())}:F>", inline=True)
    embed.add_field(name="👥 Members", value=guild.member_count, inline=True)
    embed.add_field(name="🚀 Boost Level", value=guild.premium_tier, inline=True)
    embed.add_field(name="💎 Boosts", value=guild.premium_subscription_count, inline=True)
    embed.add_field(name="📁 Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="🎭 Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)
    
    if guild.description:
        embed.add_field(name="📝 Description", value=guild.description, inline=False)
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    if guild.banner:
        embed.set_image(url=guild.banner.url)
    
    embed.set_footer(text=f"Verification Level: {guild.verification_level}")
    await ctx.respond(embed=embed)

# Run the bot
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("ERROR: Please set the DISCORD_BOT_TOKEN environment variable")
        print("You can get a bot token from https://discord.com/developers/applications")
        exit(1)
    
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("ERROR: Invalid bot token")
        exit(1)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        exit(1)