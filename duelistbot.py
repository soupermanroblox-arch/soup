```python
import discord
import os
import math
import sqlite3
import threading

from discord import app_commands
from typing import Literal
from flask import Flask


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.environ.get("TOKEN")

SERVER_ID = 1490855505000796262
LOGS_CHANNEL_ID = 1513934803412713592

# Duelist Moderator role
MODERATOR_ROLE_ID = 1490855600236789820

# Category notification channel
CATEGORY_NOTIFICATION_CHANNEL_ID = 1551022906916470875

# Role allowed to use /say
SAY_ROLE_ID = 1511114368027197501

# ELO system
K = 75


# ============================================================
# AUTOMATIC ELO ROLES
# ============================================================

ELO_ROLES = {
    "Unranked": (0, 399),
    "C-Tier": (400, 799),
    "B-Tier": (800, 1199),
    "A-Tier": (1200, 1599),
    "Quasi-S-Tier": (1600, 1999),
    "Probationary S-Tier": (2000, 2399),
    "S-Tier": (2400, 2799),
}


# ============================================================
# MANUALLY AWARDED ROLES
# ============================================================

PERMANENT_TIER_ROLES = {
    "SS-Tier",
    "SSS-Tier",
}


# ============================================================
# CATEGORY ROLES
# ============================================================

CATEGORY_ROLES = {
    1548316579425554513: "Gunner",
    1548316920930115614: "Wielder",
    1548316617320964206: "Swordsman",
}


# ============================================================
# DISCORD SETUP
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# ============================================================
# DATABASE
# ============================================================

connection = sqlite3.connect("duelist.db")
cursor = connection.cursor()


def create_database():

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS UserData (
            discordID INTEGER PRIMARY KEY,
            elo INTEGER NOT NULL DEFAULT 400,
            category_reset INTEGER NOT NULL DEFAULT 0
        )
    """)

    # --------------------------------------------------------
    # Upgrade older databases
    # --------------------------------------------------------

    try:
        cursor.execute(
            "ALTER TABLE UserData "
            "ADD COLUMN category_reset INTEGER NOT NULL DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass

    connection.commit()


def get_elo(member_id):

    cursor.execute(
        "SELECT elo FROM UserData WHERE discordID = ?",
        (member_id,)
    )

    result = cursor.fetchone()

    if result is None:

        cursor.execute(
            "INSERT INTO UserData "
            "(discordID, elo, category_reset) "
            "VALUES (?, 400, 0)",
            (member_id,)
        )

        connection.commit()

        return 400

    return result[0]


def set_elo(member_id, elo):

    elo = max(0, int(elo))

    cursor.execute(
        "INSERT INTO UserData "
        "(discordID, elo, category_reset) "
        "VALUES (?, ?, 0) "
        "ON CONFLICT(discordID) "
        "DO UPDATE SET elo = excluded.elo",
        (member_id, elo)
    )

    connection.commit()


def is_category_reset(member_id):

    cursor.execute(
        "SELECT category_reset "
        "FROM UserData "
        "WHERE discordID = ?",
        (member_id,)
    )

    result = cursor.fetchone()

    if result is None:
        get_elo(member_id)
        return False

    return bool(result[0])


def set_category_reset(member_id, value):

    get_elo(member_id)

    cursor.execute(
        "UPDATE UserData "
        "SET category_reset = ? "
        "WHERE discordID = ?",
        (1 if value else 0, member_id)
    )

    connection.commit()


# ============================================================
# KEEP-ALIVE SERVER
# ============================================================

app = Flask(__name__)


@app.route("/", methods=["GET", "HEAD"])
def home():
    return "Bot is running!", 200


def run_flask():

    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )


threading.Thread(
    target=run_flask,
    daemon=True
).start()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_role(guild, role_name):

    return discord.utils.get(
        guild.roles,
        name=role_name
    )


def has_moderator_role(member):

    role = member.guild.get_role(
        MODERATOR_ROLE_ID
    )

    if role is None:
        return False

    return role in member.roles


async def get_logs_channel():

    try:
        return await client.fetch_channel(
            LOGS_CHANNEL_ID
        )

    except discord.NotFound:
        return None

    except discord.Forbidden:
        return None

    except discord.HTTPException:
        return None


def get_automatic_role_name(elo):

    if elo >= 2400:
        return "S-Tier"

    if elo >= 2000:
        return "Probationary S-Tier"

    if elo >= 1600:
        return "Quasi-S-Tier"

    if elo >= 1200:
        return "A-Tier"

    if elo >= 800:
        return "B-Tier"

    if elo >= 400:
        return "C-Tier"

    return "Unranked"


# ============================================================
# UPDATE ELO ROLES
# ============================================================

async def updateRoles(ctx, user):

    if user is None or ctx.guild is None:
        return

    user_elo = get_elo(user.id)

    # --------------------------------------------------------
    # Category reset protection
    # --------------------------------------------------------

    if is_category_reset(user.id):

        unranked_role = get_role(
            ctx.guild,
            "Unranked"
        )

        if unranked_role is None:
            print(
                "WARNING: Could not find Discord role "
                "'Unranked'."
            )

            return

        # Remove every automatic ELO role except Unranked.

        for role_name in ELO_ROLES:

            role = get_role(
                ctx.guild,
                role_name
            )

            if (
                role is not None
                and role != unranked_role
                and role in user.roles
            ):

                try:
                    await user.remove_roles(role)

                except discord.HTTPException:
                    pass

        # Remove SS / SSS if somehow present.

        for role_name in PERMANENT_TIER_ROLES:

            role = get_role(
                ctx.guild,
                role_name
            )

            if role is not None and role in user.roles:

                try:
                    await user.remove_roles(role)

                except discord.HTTPException:
                    pass

        # Make sure Unranked exists.

        if unranked_role not in user.roles:

            try:
                await user.add_roles(
                    unranked_role
                )

            except discord.HTTPException as error:

                print(
                    f"Could not add Unranked to "
                    f"{user}: {error}"
                )

        return

    # --------------------------------------------------------
    # Preserve manually awarded SS / SSS
    # --------------------------------------------------------

    sss_role = get_role(
        ctx.guild,
        "SSS-Tier"
    )

    ss_role = get_role(
        ctx.guild,
        "SS-Tier"
    )

    if (
        (sss_role is not None and sss_role in user.roles)
        or
        (ss_role is not None and ss_role in user.roles)
    ):

        for role_name in ELO_ROLES:

            role = get_role(
                ctx.guild,
                role_name
            )

            if role is not None and role in user.roles:

                try:
                    await user.remove_roles(role)

                except discord.HTTPException:
                    pass

        return

    # --------------------------------------------------------
    # Determine automatic rank
    # --------------------------------------------------------

    automatic_role_name = get_automatic_role_name(
        user_elo
    )

    automatic_role = get_role(
        ctx.guild,
        automatic_role_name
    )

    if automatic_role is None:

        print(
            f"WARNING: Could not find Discord role "
            f"'{automatic_role_name}'."
        )

        return

    # --------------------------------------------------------
    # Remove other automatic ELO roles
    # --------------------------------------------------------

    for role_name in ELO_ROLES:

        role = get_role(
            ctx.guild,
            role_name
        )

        if (
            role is not None
            and role != automatic_role
            and role in user.roles
        ):

            try:
                await user.remove_roles(role)

            except discord.HTTPException as error:

                print(
                    f"Could not remove {role_name} "
                    f"from {user}: {error}"
                )

    # --------------------------------------------------------
    # Add correct role
    # --------------------------------------------------------

    if automatic_role not in user.roles:

        try:
            await user.add_roles(
                automatic_role
            )

        except discord.HTTPException as error:

            print(
                f"Could not add "
                f"{automatic_role_name} "
                f"to {user}: {error}"
            )


async def update_rank_sets(
    ctx,
    winner,
    loser
):

    await updateRoles(
        ctx,
        winner
    )

    await updateRoles(
        ctx,
        loser
    )


# ============================================================
# ELO CALCULATIONS
# ============================================================

def probability(
    rating1,
    rating2
):

    return 1.0 / (
        1 + math.pow(
            10,
            (rating1 - rating2) / 1500.0
        )
    )


def elo_rating(
    Ra,
    Rb,
    K,
    outcome
):

    Pb = probability(
        Ra,
        Rb
    )

    Pa = probability(
        Rb,
        Ra
    )

    rating_diff = abs(
        Ra - Rb
    )

    multiplier = pow(
        1.05,
        rating_diff // 100
    )

    if Ra < Rb:

        underdog = "player1"

    elif Rb < Ra:

        underdog = "player2"

    else:

        underdog = None

    if underdog == "player1":

        Ra = round(
            Ra
            + (K * multiplier)
            * (outcome - Pa)
        )

        Rb = round(
            Rb
            + (K * multiplier)
            * ((1 - outcome) - Pb)
        )

    else:

        Ra = round(
            Ra
            + K * (outcome - Pa)
        )

        Rb = round(
            Rb
            + K * ((1 - outcome) - Pb)
        )

    Ra = max(
        0,
        Ra
    )

    Rb = max(
        0,
        Rb
    )

    return Ra, Rb


# ============================================================
# BOT EVENTS
# ============================================================

@client.event
async def on_ready():

    create_database()

    print(
        f"{client.user} has connected to Discord."
    )

    guild = discord.Object(
        id=SERVER_ID
    )

    try:

        await tree.sync(
            guild=guild
        )

        print(
            "Slash commands synced."
        )

    except discord.HTTPException as error:

        print(
            f"Failed to sync slash commands: {error}"
        )


# ============================================================
# MEMBER JOIN
# ============================================================

@client.event
async def on_member_join(member):

    # New members start at 400 ELO.

    get_elo(
        member.id
    )

    # New members are not category-reset.

    set_category_reset(
        member.id,
        False
    )

    await updateRoles(
        type(
            "Context",
            (),
            {
                "guild": member.guild
            }
        )(),
        member
    )


# ============================================================
# CATEGORY SWITCH DETECTION
# ============================================================

@client.event
async def on_member_update(
    before,
    after
):

    # --------------------------------------------------------
    # Find category before the change
    # --------------------------------------------------------

    before_categories = [
        role
        for role in before.roles
        if role.id in CATEGORY_ROLES
    ]

    # --------------------------------------------------------
    # Find category after the change
    # --------------------------------------------------------

    after_categories = [
        role
        for role in after.roles
        if role.id in CATEGORY_ROLES
    ]

    before_category = (
        CATEGORY_ROLES[
            before_categories[0].id
        ]
        if before_categories
        else None
    )

    after_category = (
        CATEGORY_ROLES[
            after_categories[0].id
        ]
        if after_categories
        else None
    )

    # --------------------------------------------------------
    # No actual category change
    # --------------------------------------------------------

    if before_category == after_category:
        return

    # --------------------------------------------------------
    # Only trigger when switching FROM one category
    # TO another category.
    #
    # Initial category selection does not trigger.
    # --------------------------------------------------------

    if before_category is None:
        return

    if after_category is None:
        return

    # --------------------------------------------------------
    # Make sure only the selected category remains
    # --------------------------------------------------------

    selected_role = after_categories[0]

    for role in after.guild.roles:

        if (
            role.id in CATEGORY_ROLES
            and role != selected_role
            and role in after.roles
        ):

            try:

                await after.remove_roles(
                    role
                )

            except discord.HTTPException as error:

                print(
                    f"Could not remove category role "
                    f"{role.name} from {after}: {error}"
                )

    # --------------------------------------------------------
    # Mark the player as category-reset
    # --------------------------------------------------------

    set_category_reset(
        after.id,
        True
    )

    # --------------------------------------------------------
    # Remove ALL tier roles
    # --------------------------------------------------------

    all_tier_roles = (
        set(ELO_ROLES.keys())
        | PERMANENT_TIER_ROLES
    )

    for role in after.guild.roles:

        if role.name in all_tier_roles:

            if role in after.roles:

                try:

                    await after.remove_roles(
                        role
                    )

                except discord.HTTPException as error:

                    print(
                        f"Could not remove tier role "
                        f"{role.name} from {after}: {error}"
                    )

    # --------------------------------------------------------
    # Add Unranked
    # --------------------------------------------------------

    unranked_role = get_role(
        after.guild,
        "Unranked"
    )

    if unranked_role is not None:

        if unranked_role not in after.roles:

            try:

                await after.add_roles(
                    unranked_role
                )

            except discord.HTTPException as error:

                print(
                    f"Could not add Unranked to "
                    f"{after}: {error}"
                )

    # --------------------------------------------------------
    # Get notification channel
    # --------------------------------------------------------

    notification_channel = (
        after.guild.get_channel(
            CATEGORY_NOTIFICATION_CHANNEL_ID
        )
    )

    if notification_channel is None:

        print(
            f"Could not find notification channel: "
            f"{CATEGORY_NOTIFICATION_CHANNEL_ID}"
        )

        return

    # --------------------------------------------------------
    # Get current ELO
    # --------------------------------------------------------

    current_elo = get_elo(
        after.id
    )

    # --------------------------------------------------------
    # Get moderator role
    # --------------------------------------------------------

    moderator_role = after.guild.get_role(
        MODERATOR_ROLE_ID
    )

    # --------------------------------------------------------
    # Notification
    # --------------------------------------------------------

    notification = (
        f"**Duelist Category Changed**\n\n"
        f"{after.mention} has changed their category:\n"
        f"**{before_category} → {after_category}**\n\n"
        f"Their tier has been reset to **Unranked**.\n"
        f"Their ELO remains unchanged at "
        f"**{current_elo}**."
    )

    # --------------------------------------------------------
    # Ping Duelist Moderators
    # --------------------------------------------------------

    if moderator_role is not None:

        await notification_channel.send(
            f"{moderator_role.mention}\n"
            f"{notification}",
            allowed_mentions=discord.AllowedMentions(
                roles=True,
                users=True
            )
        )

    else:

        await notification_channel.send(
            notification,
            allowed_mentions=discord.AllowedMentions(
                users=True
            )
        )


# ============================================================
# MESSAGE EVENT
# ============================================================

@client.event
async def on_message(message):

    if message.author.bot:
        return

    if message.author.id == 1286730886074597389:

        if message.content == "say it":

            logs_channel = await get_logs_channel()

            if logs_channel:

                await logs_channel.send(
                    "soup is the GOAT!!!!! :fire:"
                )

    await client.process_commands(
        message
    )


# ============================================================
# /elo_set
# ============================================================

@tree.command(
    name="elo_set",
    description="Set the ELO of a user.",
    guild=discord.Object(id=SERVER_ID)
)
@app_commands.describe(
    member="The user whose ELO you want to set.",
    elo="The new ELO."
)
async def setelo(
    ctx: discord.Interaction,
    member: discord.Member,
    elo: int
):

    if not has_moderator_role(
        ctx.user
    ):

        await ctx.response.send_message(
            "You do not have permission to use this command.",
            ephemeral=True
        )

        return

    elo = max(
        0,
        elo
    )

    set_elo(
        member.id,
        elo
    )

    # A moderator manually setting ELO
    # removes the category reset.

    set_category_reset(
        member.id,
        False
    )

    await updateRoles(
        ctx,
        member
    )

    embed = discord.Embed(
        title=(
            f"{member.display_name}'s "
            f"ELO has been set."
        ),
        description=(
            f"<@{ctx.user.id}> set "
            f"<@{member.id}>'s ELO to "
            f"**{elo}**."
        )
    )

    await ctx.response.send_message(
        embed=embed
    )

    logs_channel = await get_logs_channel()

    if logs_channel:

        await logs_channel.send(
            embed=embed
        )


# ============================================================
# /elo_add
# ============================================================

@tree.command(
    name="elo_add",
    description="Add ELO to a user.",
    guild=discord.Object(id=SERVER_ID)
)
@app_commands.describe(
    member="The user whose ELO you want to increase.",
    elo="The amount of ELO to add."
)
async def addelo(
    ctx: discord.Interaction,
    member: discord.Member,
    elo: int
):

    if not has_moderator_role(
        ctx.user
    ):

        await ctx.response.send_message(
            "You do not have permission to use this command.",
            ephemeral=True
        )

        return

    if elo < 0:

        await ctx.response.send_message(
            "ELO amount cannot be negative.",
            ephemeral=True
        )

        return

    current_elo = get_elo(
        member.id
    )

    new_elo = (
        current_elo
        + elo
    )

    set_elo(
        member.id,
        new_elo
    )

    # Moderator manually changed ELO.

    set_category_reset(
        member.id,
        False
    )

    await updateRoles(
        ctx,
        member
    )

    embed = discord.Embed(
        title=(
            f"{member.display_name}'s "
            f"ELO has been updated."
        ),
        description=(
            f"<@{ctx.user.id}> added "
            f"**{elo} ELO** to "
            f"<@{member.id}>.\n\n"
            f"Previous ELO: **{current_elo}**\n"
            f"New ELO: **{new_elo}**"
        )
    )

    await ctx.response.send_message(
        embed=embed
    )

    logs_channel = await get_logs_channel()

    if logs_channel:

        await logs_channel.send(
            embed=embed
        )


# ============================================================
# /elo_remove
# ============================================================

@tree.command(
    name="elo_remove",
    description="Remove ELO from a user.",
    guild=discord.Object(id=SERVER_ID)
)
@app_commands.describe(
    member="The user whose ELO you want to decrease.",
    elo="The amount of ELO to remove."
)
async def removelo(
    ctx: discord.Interaction,
    member: discord.Member,
    elo: int
):

    if not has_moderator_role(
        ctx.user
    ):

        await ctx.response.send_message(
            "You do not have permission to use this command.",
            ephemeral=True
        )

        return

    if elo < 0:

        await ctx.response.send_message(
            "ELO amount cannot be negative.",
            ephemeral=True
        )

        return

    current_elo = get_elo(
        member.id
    )

    new_elo = max(
        0,
        current_elo - elo
    )

    set_elo(
        member.id,
        new_elo
    )

    # Moderator manually changed ELO.

    set_category_reset(
        member.id,
        False
    )

    await updateRoles(
        ctx,
        member
    )

    embed = discord.Embed(
        title=(
            f"{member.display_name}'s "
            f"ELO has been updated."
        ),
        description=(
            f"<@{ctx.user.id}> removed "
            f"**{elo} ELO** from "
            f"<@{member.id}>.\n\n"
            f"Previous ELO: **{current_elo}**\n"
            f"New ELO: **{new_elo}**"
        )
    )

    await ctx.response.send_message(
        embed=embed
    )

    logs_channel = await get_logs_channel()

    if logs_channel:

        await logs_channel.send(
            embed=embed
        )


# ============================================================
# /elo_check
# ============================================================

@tree.command(
    name="elo_check",
    description="Check your ELO or another user's ELO.",
    guild=discord.Object(id=SERVER_ID)
)
@app_commands.describe(
    member="The user whose ELO you want to check."
)
async def elocheck(
    ctx: discord.Interaction,
    member: discord.Member = None
):

    if member is None:
        member = ctx.user

    user_elo = get_elo(
        member.id
    )

    # If category-reset, keep them Unranked.

    if is_category_reset(
        member.id
    ):

        rank = "Unranked"

    else:

        await updateRoles(
            ctx,
            member
        )

        rank = get_automatic_role_name(
            user_elo
        )

        # Display manually awarded ranks.

        sss_role = get_role(
            ctx.guild,
            "SSS-Tier"
        )

        ss_role = get_role(
            ctx.guild,
            "SS-Tier"
        )

        if (
            sss_role is not None
            and sss_role in member.roles
        ):

            rank = "SSS-Tier"

        elif (
            ss_role is not None
            and ss_role in member.roles
        ):

            rank = "SS-Tier"

    embed = discord.Embed(
        title=(
            f"{member.display_name}'s ELO"
        ),
        description=(
            f"<@{member.id}> has an ELO of "
            f"**{user_elo}**.\n"
            f"Rank: **{rank}**"
        )
    )

    await ctx.response.send_message(
        embed=embed
    )


# ============================================================
# /submit_match
# ============================================================

@tree.command(
    name="submit_match",
    description="Submit a match for an overview by Duelist Moderators.",
    guild=discord.Object(id=SERVER_ID)
)
@app_commands.describe(
    winner="The winner of the duel.",
    loser="The loser of the duel.",
    proof="Proof of the duel."
)
async def submit(
    ctx: discord.Interaction,
    winner: discord.Member,
    loser: discord.Member,
    proof: discord.Attachment
):

    if not has_moderator_role(
        ctx.user
    ):

        await ctx.response.send_message(
            "You do not have permission to use this command.",
            ephemeral=True
        )

        return

    if winner.id == loser.id:

        await ctx.response.send_message(
            "The winner and loser cannot be the same person.",
            ephemeral=True
        )

        return

    winner_elo = get_elo(
        winner.id
    )

    loser_elo = get_elo(
        loser.id
    )

    new_winner_elo, new_loser_elo = elo_rating(
        winner_elo,
        loser_elo,
        K,
        1
    )

    set_elo(
        winner.id,
        new_winner_elo
    )

    set_elo(
        loser.id,
        new_loser_elo
    )

    await update_rank_sets(
        ctx,
        winner,
        loser
    )

    embed = discord.Embed(
        title=(
            f"{winner.display_name} VS "
            f"{loser.display_name}"
        ),
        description=(
            "A duel has concluded.\n\n"
            f"Winner: {winner.display_name} "
            f"- New ELO: **{new_winner_elo}**\n"
            f"Loser: {loser.display_name} "
            f"- New ELO: **{new_loser_elo}**\n\n"
            "Proof can be seen below."
        )
    )

    embed.set_image(
        url=proof.url
    )

    await ctx.response.send_message(
        embed=embed
    )

    logs_channel = await get_logs_channel()

    if logs_channel:

        await logs_channel.send(
            embed=embed
        )


# ============================================================
# /submit_tiered_match
# ============================================================

@tree.command(
    name="submit_tiered_match",
    description="Submit a tiered match for review.",
    guild=discord.Object(id=SERVER_ID)
)
@app_commands.describe(
    winner="The winner of the duel.",
    loser="The loser of the duel.",
    proof="Proof of the duel.",
    challengerstatus="Whether the challenger won or lost."
)
async def tieredsubmit(
    ctx: discord.Interaction,
    winner: discord.Member,
    loser: discord.Member,
    proof: discord.Attachment,
    challengerstatus: Literal[
        "Challenger Won",
        "Challenger Lost"
    ]
):

    if not has_moderator_role(
        ctx.user
    ):

        await ctx.response.send_message(
            "You do not have permission to use this command.",
            ephemeral=True
        )

        return

    if winner.id == loser.id:

        await ctx.response.send_message(
            "The winner and loser cannot be the same person.",
            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # Challenger WON
    # --------------------------------------------------------

    if challengerstatus == "Challenger Won":

        loser_elo = get_elo(
            loser.id
        )

        loser_rank = get_automatic_role_name(
            loser_elo
        )

        placement_elo = {
            "Quasi-S-Tier": 1850,
            "A-Tier": 1450,
            "B-Tier": 1050,
            "C-Tier": 750,
        }

        if loser_rank in placement_elo:

            set_elo(
                winner.id,
                placement_elo[
                    loser_rank
                ]
            )

        new_loser_elo = max(
            0,
            loser_elo - 250
        )

        set_elo(
            loser.id,
            new_loser_elo
        )

    # --------------------------------------------------------
    # Challenger LOST
    # --------------------------------------------------------

    elif challengerstatus == "Challenger Lost":

        winner_elo = get_elo(
            winner.id
        )

        loser_elo = get_elo(
            loser.id
        )

        new_winner_elo, new_loser_elo = elo_rating(
            winner_elo,
            loser_elo,
            K,
            1
        )

        set_elo(
            winner.id,
            new_winner_elo
        )

        set_elo(
            loser.id,
            new_loser_elo
        )

    # --------------------------------------------------------
    # Update roles
    # --------------------------------------------------------

    await update_rank_sets(
        ctx,
        winner,
        loser
    )

    winner_elo = get_elo(
        winner.id
    )

    loser_elo = get_elo(
        loser.id
    )

    embed = discord.Embed(
        title=(
            f"{winner.display_name} VS "
            f"{loser.display_name} "
            f"[TIERED]"
        ),
        description=(
            "A tiered duel has concluded.\n\n"
            f"Winner: {winner.display_name} "
            f"- New ELO: **{winner_elo}**\n"
            f"Loser: {loser.display_name} "
            f"- New ELO: **{loser_elo}**\n\n"
            "Proof can be seen below."
        )
    )

    embed.set_image(
        url=proof.url
    )

    await ctx.response.send_message(
        embed=embed
    )

    logs_channel = await get_logs_channel()

    if logs_channel:

        await logs_channel.send(
            embed=embed
        )


# ============================================================
# /check_leaderboard
# ============================================================

@tree.command(
    name="check_leaderboard",
    description="Check the current standings!",
    guild=discord.Object(id=SERVER_ID)
)
async def showleaderboard(
    ctx: discord.Interaction
):

    cursor.execute(
        "SELECT elo, discordID "
        "FROM UserData "
        "ORDER BY elo DESC "
        "LIMIT 10"
    )

    leaderboard = cursor.fetchall()

    embed = discord.Embed(
        title="Current Leaderboard Rankings"
    )

    if not leaderboard:

        embed.description = (
            "There are currently no ranked users."
        )

        await ctx.response.send_message(
            embed=embed
        )

        return

    for index, value in enumerate(
        leaderboard,
        start=1
    ):

        embed.add_field(
            name=f"#{index}",
            value=(
                f"<@{value[1]}> - "
                f"**{value[0]} ELO**"
            ),
            inline=False
        )

    await ctx.response.send_message(
        embed=embed
    )


# ============================================================
# /update_user
# ============================================================

@tree.command(
    name="update_user",
    description="Update a user's role according to their ELO.",
    guild=discord.Object(id=SERVER_ID)
)
@app_commands.describe(
    member="The user whose role you want to update."
)
async def updateuser(
    ctx: discord.Interaction,
    member: discord.Member
):

    if not has_moderator_role(
        ctx.user
    ):

        await ctx.response.send_message(
            "You do not have permission to use this command.",
            ephemeral=True
        )

        return

    # A moderator manually updating the user
    # removes their category-reset state.

    set_category_reset(
        member.id,
        False
    )

    await updateRoles(
        ctx,
        member
    )

    await ctx.response.send_message(
        f"Updated {member.mention}'s ELO role."
    )


# ============================================================
# /say
# ============================================================

@tree.command(
    name="say",
    description="Make the bot send a message.",
    guild=discord.Object(id=SERVER_ID)
)
@app_commands.describe(
    message="The message you want the bot to send."
)
async def say(
    ctx: discord.Interaction,
    message: str
):

    required_role = ctx.guild.get_role(
        SAY_ROLE_ID
    )

    if required_role is None:

        await ctx.response.send_message(
            "The required role could not be found.",
            ephemeral=True
        )

        return

    if required_role not in ctx.user.roles:

        await ctx.response.send_message(
            "You do not have permission to use this command.",
            ephemeral=True
        )

        return

    await ctx.response.send_message(
        "Message sent.",
        ephemeral=True
    )

    await ctx.channel.send(
        message
    )


# ============================================================
# START BOT
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "TOKEN environment variable is missing. "
        "Add your Discord bot token as TOKEN "
        "in your hosting environment."
    )


client.run(TOKEN)
```
