import discord
import os
import math
from discord import app_commands
from discord.ext import commands
import sqlite3
from typing import Literal
from flask import Flask
from threading import Thread

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

tree = app_commands.CommandTree(client)

TOKEN = os.getenv("TOKEN")

# ───────────── Keep‑alive server ─────────────
app = Flask(__name__)
@app.route("/", methods=["GET", "HEAD"])
def home():
    return "Bot is running!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
threading.Thread(target=run_flask, daemon=True).start()

connection = sqlite3.connect("duelist.db")
cursor = connection.cursor()
role = None

serverID = 1490855505000796262  # if its a new server, put it in here
logschannelID = 1513934803412713592 # same with logs channel id 

@client.event
async def on_ready():
    print(f'{client.user} has connected to discord.')
    cursor.execute("CREATE TABLE IF NOT EXISTS UserData (discordID INTEGER, elo INTEGER)")
    connection.commit()
    await tree.sync(guild=discord.Object(id=serverID))

@client.event
async def on_member_join(member):
    cursor.execute(f'SELECT discordID FROM UserData WHERE discordID = {member.id};')
    MemberExists = cursor.fetchone()
    if MemberExists == None:
        cursor.execute(f'INSERT INTO UserData VALUES({member.id}, 400)')
        connection.commit()
        
@client.event
async def on_message(ctx):
    if(ctx.author.id == 1286730886074597389):
        if ctx.content == "say it":
            logschannel = await client.fetch_channel(logschannelID) 
            await logschannel.send("soup is the GOAT!!!!! :fire:")
@tree.command(
    name = "elo_set",
    description = "Set the elo of a user.",
    guild = discord.Object(id=serverID))
async def setelo(ctx, member: discord.Member, elo: int):
    logschannel = await client.fetch_channel(logschannelID)
    role = discord.utils.get(ctx.guild.roles, name = "Duelist Moderator")
    if role in ctx.user.roles:
        cursor.execute(f'UPDATE UserData SET elo = {elo} WHERE discordID = {member.id};')
        connection.commit()
        await updateRoles(ctx, member)
        embedVar = discord.Embed(title = f"{member.display_name}'s points have been set.", description = f"<@{ctx.user.id}> set <@{member.id}>'s points to {elo}.")
        await ctx.response.send_message(embed=embedVar)
        await logschannel.send(embed=embedVar)

@tree.command(
    name = "elo_add",
    description = "Add elo to a user.",
    guild = discord.Object (id=serverID))
async def addelo(ctx, member: discord.Member, elo: int):
    logschannel = await client.fetch_channel(logschannelID)
    role = discord.utils.get(ctx.guild.roles, name = "Duelist Moderator")
    if role in ctx.user.roles:
        cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {member.id};')
        userElo = cursor.fetchone()
        eloIncrease = userElo[0] + elo
        cursor.execute(f'UPDATE UserData SET elo = {eloIncrease} WHERE discordID = {member.id};')
        connection.commit()
        await updateRoles(ctx, member)
        embedVar = discord.Embed(title = f"{member.display_name}'s points have been updated.", description = f"<@{ctx.user.id}> has added {elo} to <@{member.id}>'s elo.")
        await ctx.response.send_message(embed=embedVar)
        await logschannel.send(embed=embedVar)


@tree.command(
    name = "elo_remove",
    description = "Remove elo from a user.",
    guild = discord.Object(id=serverID))
async def removelo(ctx, member: discord.Member, elo: int):
    logschannel = await client.fetch_channel(logschannelID)
    role = discord.utils.get(ctx.guild.roles, name = "Duelist Moderator")
    if role in ctx.user.roles:
        cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {member.id};')
        userElo = cursor.fetchone()
        eloDecrease = userElo[0] - elo
        cursor.execute(f'UPDATE UserData SET elo = {eloDecrease} WHERE discordID = {member.id};')
        connection.commit()
        await updateRoles(ctx, member)
        embedVar = discord.Embed(title = f"{member.display_name}'s points have been updated.", description = f"<@{ctx.user.id}> has removed {elo} from <@{member.id}>'s elo.")
        await ctx.response.send_message(embed=embedVar)
        await logschannel.send(embed=embedVar)

@tree.command(
    name = "elo_check",
    description = "Check your elo or another users elo.",
    guild = discord.Object(id=serverID))
async def elocheck(ctx, member: discord.Member = None):
    if member == None:
        member = ctx.user
    userElo = cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {member.id};')
    userElo = cursor.fetchone()
    await updateRoles(ctx, member)
    embedVar = discord.Embed(title = f"{member.display_name}'s Elo", description = f"<@{member.id}> has an elo of {userElo[0]}.")
    await ctx.response.send_message(embed=embedVar)


K = 110

@tree.command(
    name = "submit_match",
    description = "Submit a match for an overview by duelist moderators.",
    guild = discord.Object(id=serverID))
async def submit(ctx, winner: discord.Member, loser: discord.Member, proof: discord.Attachment):
    role = discord.utils.get(ctx.guild.roles, name = "Duelist Moderator")
    logschannel = await client.fetch_channel(logschannelID)
    if role in ctx.user.roles:
        WinnerRating = cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {winner.id};')
        WinnerRating = cursor.fetchone()
        LoserRating = cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {loser.id};')
        LoserRating = cursor.fetchone()
        WinnerElo, LoserElo = elo_rating(WinnerRating[0], LoserRating[0], K, 1)
        cursor.execute(f'UPDATE UserData SET elo = {WinnerElo} WHERE discordID = {winner.id};')
        cursor.execute(f'UPDATE UserData SET elo = {LoserElo} WHERE discordID = {loser.id};')
        connection.commit()
        WinnerRating = cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {winner.id};')
        WinnerRating = cursor.fetchone()
        LoserRating = cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {loser.id};')
        LoserRating = cursor.fetchone()

        embedVar = discord.Embed(title = f"{winner.display_name} VS {loser.display_name}", description = f"A duel has concluded. \n \n Winner: {winner.display_name} - New Elo: {WinnerRating[0]} \n Loser: {loser.display_name} - New Elo: {LoserRating[0]} \n \n Proof can be seen below.")
        embedVar.set_image(url = proof.url)
        await ctx.response.send_message(embed=embedVar)
        await updateranksets(ctx, winner, loser)
        await logschannel.send(embed=embedVar)

@tree.command(
    name = "submit_tiered_match",
    description = "Submit a tiered match for an overview by duelist moderators.",
    guild = discord.Object(id=serverID))
async def tieredsubmit(ctx, winner: discord.Member, loser: discord.Member, proof: discord.Attachment, challengerstatus: Literal["Challenger Won", "Challenger Lost"]):
    role = discord.utils.get(ctx.guild.roles, name = "Duelist Moderator")
    logschannel = await client.fetch_channel(logschannelID)
    if role in ctx.user.roles:
        if challengerstatus == "Challenger Won":
            UnrankedRole = discord.utils.get(ctx.guild.roles, name = "Unranked")
            NoviceRole = discord.utils.get(ctx.guild.roles, name = "C-Tier")
            PracticionerRole = discord.utils.get(ctx.guild.roles, name = "B-Tier")
            QuasiRole = discord.utils.get(ctx.guild.roles, name = "Quasi-Elite")
            AtierRole = discord.utils.get(ctx.guild.roles, name = "A-Tier")
            if QuasiRole in loser.roles:
                cursor.execute(f'UPDATE UserData SET elo = {1850} WHERE discordID = {winner.id};')
            elif AtierRole in loser.roles:
                cursor.execute(f'UPDATE UserData SET elo = {1450} WHERE discordID = {winner.id};')
            elif PracticionerRole in loser.roles:
                cursor.execute(f'UPDATE UserData SET elo = {1050} WHERE discordID = {winner.id};')
            elif NoviceRole in loser.roles:
                cursor.execute(f'UPDATE UserData SET elo = {750} WHERE discordID = {winner.id};')
            LoserRating = cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {loser.id};')
            LoserRating = cursor.fetchone()
            newLoserElo = LoserRating[0] - 250
            cursor.execute(f'UPDATE UserData SET elo = {newLoserElo} WHERE discordID = {loser.id};')
            connection.commit()
        elif challengerstatus == "Challenger Lost":
            WinnerRating = cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {winner.id};')
            WinnerRating = cursor.fetchone()
            LoserRating = cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {loser.id};')
            LoserRating = cursor.fetchone()
            WinnerElo, LoserElo = elo_rating(WinnerRating[0], LoserRating[0], K, 1)
            cursor.execute(f'UPDATE UserData SET elo = {WinnerElo} WHERE discordID = {winner.id};')
            cursor.execute(f'UPDATE UserData SET elo = {LoserElo} WHERE discordID = {loser.id};')
            connection.commit()

            
        WinnerRating = cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {winner.id};')
        WinnerRating = cursor.fetchone()
        LoserRating = cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {loser.id};')
        LoserRating = cursor.fetchone()
        embedVar = discord.Embed(title = f"{winner.display_name} VS {loser.display_name} [TIERED]", description = f"A duel has concluded. \n \n Winner: {winner.display_name} - New Elo: {WinnerRating[0]} \n Loser: {loser.display_name} - New Elo: {LoserRating[0]} \n \n Proof can be seen below.")
        embedVar.set_image(url = proof.url)
        await ctx.response.send_message(embed=embedVar)
        await updateranksets(ctx, winner, loser)
        await logschannel.send(embed=embedVar)

        
async def updateranksets(ctx, winner, loser):
    await updateRoles(ctx, winner)
    await updateRoles(ctx, loser)
@tree.command(
    name = "check_leaderboard",
    description = "Check the current standings!",
    guild = discord.Object(id=serverID))
async def showleaderboard(ctx):
    embedVar = discord.Embed(title = "Current Leaderboard Rankings")
    Leaderboard = cursor.execute(f'SELECT elo, discordID FROM UserData ORDER BY elo DESC;')
    Leaderboard = cursor.fetchall()
    for value in range(10):
        embedVar.add_field(name = f"#{value + 1}", value = f"<@{Leaderboard[value][1]}> - {Leaderboard[value][0]}", inline = False)
    await ctx.response.send_message(embed=embedVar)

@tree.command(
    name = "update_user",
    description = "Update user role according to elo.",
    guild = discord.Object(id=serverID)
)
async def updateuser(ctx, member: discord.Member):
    await updateRoles(ctx, member)
    await ctx.response.send_message("Updated user roles.")
    
        
#@tree.command(
#    name = "update_users",
#    description = "Update all users to the original elo/rank match.",
#    guild = discord.Object(id=serverID))
#async def updateusers(ctx):
##    role = discord.utils.get(ctx.guild.roles, name = "big z")
 #   if role in ctx.user.roles:
  #      duelistGuild = client.get_guild(serverID)
   #     UnrankedRole = discord.utils.get(ctx.guild.roles, name = "Unranked")
    #    NoviceRole = discord.utils.get(ctx.guild.roles, name = "Novice")
     #   PracticionerRole = discord.utils.get(ctx.guild.roles, name = "Practitioner")
      #  QuasiRole = discord.utils.get(ctx.guild.roles, name = "Quasi-Elite")
       # ProbationaryRole = discord.utils.get(ctx.guild.roles, name = "Probationary Elite")
        #EliteRole = discord.utils.get(ctx.guild.roles, name = "Elite")
        #HighEliteRole = discord.utils.get(ctx.guild.roles, name = "High Elite")
        #GrandmasterRole = discord.utils.get(ctx.guild.roles, name = "Grandmaster")
        #for member in duelistGuild.members:
        #    if GrandmasterRole in member.roles:
        #        cursor.execute(f'INSERT INTO UserData VALUES({member.id}, 2801)')
        #        connection.commit()
        #    elif HighEliteRole in member.roles:
        #        cursor.execute(f'INSERT INTO UserData VALUES({member.id}, 2400)')
        #        connection.commit()
        #    elif EliteRole in member.roles:
        #        cursor.execute(f'INSERT INTO UserData VALUES({member.id}, 2001)')
        #        connection.commit()
        #    elif ProbationaryRole in member.roles:
        #        cursor.execute(f'INSERT INTO UserData VALUES({member.id}, 1501)')
        #        connection.commit()
        #    elif QuasiRole in member.roles:
        #        cursor.execute(f'INSERT INTO UserData VALUES({member.id}, 1001)')
         #       connection.commit()
         #   elif PracticionerRole in member.roles:
         #       cursor.execute(f'INSERT INTO UserData VALUES({member.id}, 1000)')
         #       connection.commit()
         #   elif NoviceRole in member.roles:
         #       cursor.execute(f'INSERT INTO UserData VALUES({member.id}, 601)')
         #       connection.commit()
         #   elif UnrankedRole in member.roles:
         #       cursor.execute(f'INSERT INTO UserData VALUES({member.id}, 0)')
        #print("Update done.")

async def updateRoles(ctx, user):
    UserRating = cursor.execute(f'SELECT elo FROM UserData WHERE discordID = {user.id};')
    UserRating = cursor.fetchone()
    NoviceRole = discord.utils.get(ctx.guild.roles, name = "C-Tier")
    PracticionerRole = discord.utils.get(ctx.guild.roles, name = "B-Tier")
    QuasiRole = discord.utils.get(ctx.guild.roles, name = "Quasi-S-Tier")
    ProbationaryRole = discord.utils.get(ctx.guild.roles, name = "Probationary S-Tier")
    EliteRole = discord.utils.get(ctx.guild.roles, name = "S-Tier")
    HighEliteRole = discord.utils.get(ctx.guild.roles, name = "SS-Tier")
    GrandmasterRole = discord.utils.get(ctx.guild.roles, name = "SSS-Tier")
    AtierRole = discord.utils.get(ctx.guild.roles, name = "A-Tier")
    if(UserRating[0] >= 2800):
        if HighEliteRole in user.roles:
            if HighEliteRole in user.roles:
                await user.remove_roles(HighEliteRole)
            if EliteRole in user.roles:
                await user.remove_roles(EliteRole)
            if ProbationaryRole in user.roles:
                await user.remove_roles(ProbationaryRole)
            if QuasiRole in user.roles:
                await user.remove_roles(QuasiRole)
            if PracticionerRole in user.roles:
                await user.remove_roles(PracticionerRole)
            if NoviceRole in user.roles:
                await user.remove_roles(NoviceRole)
            if UnrankedRole in user.roles:
                await user.remove_roles(UnrankedRole)
            await user.add_roles(GrandmasterRole)
    elif(UserRating[0] >= 2400):
        if EliteRole in user.roles:
            await user.add_roles(HighEliteRole)
            if HighEliteRole in user.roles:
                await user.remove_roles(HighEliteRole)
            if EliteRole in user.roles:
                await user.remove_roles(EliteRole)
            if ProbationaryRole in user.roles:
                await user.remove_roles(ProbationaryRole)
            if QuasiRole in user.roles:
                await user.remove_roles(QuasiRole)
            if PracticionerRole in user.roles:
                await user.remove_roles(PracticionerRole)
            if NoviceRole in user.roles:
                await user.remove_roles(NoviceRole)
            if UnrankedRole in user.roles:
                await user.remove_roles(UnrankedRole)
            if GrandmasterRole in user.roles:
                await user.remove_roles(GrandmasterRole)
    elif(UserRating[0] >= 2001):
        if EliteRole not in user.roles:
            await user.add_roles(ProbationaryRole)
            if HighEliteRole in user.roles:
                await user.remove_roles(HighEliteRole)
            if QuasiRole in user.roles:
                await user.remove_roles(QuasiRole)
            if PracticionerRole in user.roles:
                await user.remove_roles(PracticionerRole)
            if NoviceRole in user.roles:
                await user.remove_roles(NoviceRole)
            if UnrankedRole in user.roles:
                await user.remove_roles(UnrankedRole)
            if GrandmasterRole in user.roles:
                await user.remove_roles(GrandmasterRole)
    elif(UserRating[0] >= 1501):
        if EliteRole in user.roles:
        	await user.remove_roles(EliteRole)
        if HighEliteRole in user.roles:
                await user.remove_roles(HighEliteRole)
        if ProbationaryRole in user.roles:
        	await user.remove_roles(ProbationaryRole)
        await user.add_roles(QuasiRole)
        if PracticionerRole in user.roles:
            await user.remove_roles(PracticionerRole)
        if NoviceRole in user.roles:
            await user.remove_roles(NoviceRole)
        if UnrankedRole in user.roles:
            await user.remove_roles(UnrankedRole)
        if GrandmasterRole in user.roles:
            await user.remove_roles(GrandmasterRole)
    elif(UserRating[0] >= 1001):
        if EliteRole in user.roles:
        	await user.remove_roles(EliteRole)
        if HighEliteRole in user.roles:
                await user.remove_roles(HighEliteRole)
        if ProbationaryRole in user.roles:
        	await user.remove_roles(ProbationaryRole)
        if QuasiRole in user.roles:
        	await user.remove_roles(QuasiRole)
        await user.add_roles(AtierRole)
        if PracticionerRole in user.roles:
            await user.remove_roles(PracticionerRole)
        if NoviceRole in user.roles:
            await user.remove_roles(NoviceRole)
        if UnrankedRole in user.roles:
            await user.remove_roles(UnrankedRole)
        if GrandmasterRole in user.roles:
            await user.remove_roles(GrandmasterRole)
    elif(UserRating[0] >= 601):
        if HighEliteRole in user.roles:
                await user.remove_roles(HighEliteRole)
        if EliteRole in user.roles:
        	await user.remove_roles(EliteRole)
        if ProbationaryRole in user.roles:
        	await user.remove_roles(ProbationaryRole)
        if QuasiRole in user.roles:
        	await user.remove_roles(QuasiRole)
        await user.add_roles(PracticionerRole)
        if NoviceRole in user.roles:
            await user.remove_roles(NoviceRole)
        if UnrankedRole in user.roles:
            await user.remove_roles(UnrankedRole)
        if GrandmasterRole in user.roles:
            await user.remove_roles(GrandmasterRole)
    elif(UserRating[0] >= 301):
        if HighEliteRole in user.roles:
                await user.remove_roles(HighEliteRole)
        if EliteRole in user.roles:
        	await user.remove_roles(EliteRole)
        if ProbationaryRole in user.roles:
        	await user.remove_roles(ProbationaryRole)
        if QuasiRole in user.roles:
        	await user.remove_roles(QuasiRole)
        if PracticionerRole in user.roles:
            await user.remove_roles(PracticionerRole)
        await user.add_roles(NoviceRole)
        if UnrankedRole in user.roles:
            await user.remove_roles(UnrankedRole)
        if GrandmasterRole in user.roles:
            await user.remove_roles(GrandmasterRole)
    elif(UserRating[0] >= 0):
        if HighEliteRole in user.roles:
                await user.remove_roles(HighEliteRole)
        if EliteRole in user.roles:
        	await user.remove_roles(EliteRole)
        if ProbationaryRole in user.roles:
        	await user.remove_roles(ProbationaryRole)
        if QuasiRole in user.roles:
        	await user.remove_roles(QuasiRole)
        if PracticionerRole in user.roles:
            await user.remove_roles(PracticionerRole)
        if NoviceRole in user.roles:
            await user.remove_roles(NoviceRole)
        await user.add_roles(UnrankedRole)
        if GrandmasterRole in user.roles:
            await user.remove_roles(GrandmasterRole)
        
        
def probability(rating1, rating2):
    return 1.0 / (1 + math.pow(10, (rating1 - rating2) / 1500.0))


def elo_rating(Ra, Rb, K, outcome):

    Pb = probability(Ra, Rb)

    # Calculate the Winning Probability of Player A
    Pa = probability(Rb, Ra)

    rating_diff = abs(Ra - Rb)
    multiplier = pow(1.05, rating_diff // 100)

    if Ra < Rb:
        underdog = 'player1'
    elif Rb < Ra:
        underdog = 'player2'
    else:
        underdog = None
    
    if underdog == 'player1':
        Ra = round(Ra + (K * multiplier) * (outcome - Pa))
        Rb = round(Rb + (K * multiplier) * ((1 - outcome) - Pb))
    else:
        Ra = round(Ra + K * (outcome - Pa))
        Rb = round(Rb + K * ((1 - outcome) - Pb))                   
    # Update the Elo Ratings
	
    if Ra < 20:
        Ra = 20
    if Rb < 20:
        Rb = 20
    return(Ra, Rb)
    # Print updated ratings
    print("Updated Ratings:-")
    print(f"Ra = {Ra} Rb = {Rb}")

client.run(TOKEN)
