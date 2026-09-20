import discord
import os
import math
import sqlite3
import threading
import shutil

from datetime import datetime, timezone
from pathlib import Path

from discord import app_commands
from typing import Optional
from flask import Flask


# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = os.environ.get("TOKEN")

SERVER_ID = 1490855505000796262
LOGS_CHANNEL_ID = 1513934803412713592

MODERATOR_ROLE_ID = 1490855600236789820
DUELIST_STAFF_ROLE_ID = 1515821480464875590

# ONLY this role can use /elo_set
ELO_SET_ROLE_ID = 1510774088354762915

CATEGORY_NOTIFICATION_CHANNEL_ID = 1551022906916470875
SAY_ROLE_ID = 1511114368027197501

K = 75


# ============================================================
# CATEGORY ROLES
# ============================================================

CATEGORY_ROLES = {
    "Duelist": 1548316617320964206,
    "Soldier": 1548316579425554513,
    "Aether Wielder": 1548316920930115614,
}


# ============================================================
# TIER ROLE IDS
# ============================================================

TIER_NAMES = [
    "Unranked",
    "C-Tier",
    "B-Tier",
    "A-Tier",
    "Quasi-S-Tier",
    "Probationary S-Tier",
    "S-Tier",
    "SS-Tier",
    "SSS-Tier",
]


TIER_ROLE_IDS = {

    "Duelist": {
        "Unranked": 1523740132904276068,
        "C-Tier": 1490855609212600390,
        "B-Tier": 1551179564988891136,
        "A-Tier": 1490855607236956284,
        "Quasi-S-Tier": 1510752029579149423,
        "Probationary S-Tier": 1490855607123841044,
        "S-Tier": 1490855606251425923,
        "SS-Tier": 1490855603642306602,
        "SSS-Tier": 1490855602744987858,
    },

    "Soldier": {
        "Unranked": 1523740132904276068,
        "C-Tier": 1551177908024905808,
        "B-Tier": 1551178052208300092,
        "A-Tier": 1551178205442867200,
        "Quasi-S-Tier": 1551178459714293950,
        "Probationary S-Tier": 1551180196097556500,
        "S-Tier": 1551178760768716892,
        "SS-Tier": 1551178866934939668,
        "SSS-Tier": 1551178892952477726,
    },

    "Aether Wielder": {
        "Unranked": 1523740132904276068,
        "C-Tier": 1551178107770109972,
        "B-Tier": 1551178623304605787,
        "A-Tier": 1551178673447763968,
        "Quasi-S-Tier": 1551180036319613018,
        "Probationary S-Tier": 1551180991203381258,
        "S-Tier": 1551178722256621641,
        "SS-Tier": 1551178780041809950,
        "SSS-Tier": 1551178825860259870,
    },
}


# ============================================================
# AUTOMATIC ELO RANGES
# ============================================================

AUTOMATIC_RANKS = {
    "Unranked": (0, 399),
    "C-Tier": (400, 799),
    "B-Tier": (800, 1199),
    "A-Tier": (1200, 1599),
    "Quasi-S-Tier": (1600, 1999),
    "Probationary S-Tier": (2000, 2399),
    "S-Tier": (2400, 2799),
}


# ============================================================
# TIERED MATCH PLACEMENTS
# ============================================================

PLACEMENT_ELO = {
    "C-Tier": 750,
    "B-Tier": 1050,
    "A-Tier": 1450,
    "Quasi-S-Tier": 1850,
    "Probationary S-Tier": 2250,
    "S-Tier": 2650,
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

db_lock = threading.Lock()

connection = sqlite3.connect(
    "duelist.db",
    check_same_thread=False
)

connection.row_factory = sqlite3.Row


def db_execute(
    sql,
    params=(),
    fetchone=False,
    fetchall=False,
    commit=False
):

    with db_lock:

        cursor = connection.cursor()

        cursor.execute(sql, params)

        if fetchone:
            result = cursor.fetchone()

        elif fetchall:
            result = cursor.fetchall()

        else:
            result = None

        if commit:
            connection.commit()

        return result


def create_database():

    with db_lock:

        cursor = connection.cursor()


        # ----------------------------------------------------
        # OLD TABLE
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS UserData (
                discordID INTEGER PRIMARY KEY,
                elo INTEGER NOT NULL DEFAULT 400,
                category_reset INTEGER NOT NULL DEFAULT 0
            )
        """)


        # ----------------------------------------------------
        # CATEGORY ELO / STATS
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS CategoryData (
                discordID INTEGER NOT NULL,
                category TEXT NOT NULL,

                elo INTEGER NOT NULL DEFAULT 400,

                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,

                current_streak INTEGER NOT NULL DEFAULT 0,
                peak_elo INTEGER NOT NULL DEFAULT 400,

                PRIMARY KEY (discordID, category)
            )
        """)


        # ----------------------------------------------------
        # MATCH HISTORY
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Matches (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                match_code TEXT UNIQUE NOT NULL,

                category TEXT NOT NULL,

                winner_id INTEGER NOT NULL,
                loser_id INTEGER NOT NULL,

                winner_elo_before INTEGER NOT NULL,
                winner_elo_after INTEGER NOT NULL,

                loser_elo_before INTEGER NOT NULL,
                loser_elo_after INTEGER NOT NULL,

                winner_wins_before INTEGER NOT NULL,
                winner_losses_before INTEGER NOT NULL,
                winner_streak_before INTEGER NOT NULL,

                loser_wins_before INTEGER NOT NULL,
                loser_losses_before INTEGER NOT NULL,
                loser_streak_before INTEGER NOT NULL,

                proof TEXT NOT NULL,

                submitted_by INTEGER NOT NULL,

                match_type TEXT NOT NULL,

                created_at TEXT NOT NULL,

                undone INTEGER NOT NULL DEFAULT 0
            )
        """)


        # ----------------------------------------------------
        # ELO AUDIT LOG
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS EloAudit (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                discordID INTEGER NOT NULL,

                category TEXT NOT NULL,

                old_elo INTEGER NOT NULL,
                new_elo INTEGER NOT NULL,

                action TEXT NOT NULL,

                match_code TEXT,

                staff_id INTEGER NOT NULL,

                created_at TEXT NOT NULL
            )
        """)


        # ----------------------------------------------------
        # PROFILE RESET TRACKING
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ProfileResets (

                discordID INTEGER PRIMARY KEY,

                reset_at TEXT NOT NULL,

                reset_by INTEGER NOT NULL
            )
        """)


        # ----------------------------------------------------
        # MIGRATE OLD ELO SYSTEM
        # ----------------------------------------------------

        users = cursor.execute(
            "SELECT discordID, elo FROM UserData"
        ).fetchall()


        for user in users:

            user_id = user[0]

            old_elo = max(
                0,
                int(user[1])
            )


            for category in CATEGORY_ROLES:

                cursor.execute("""
                    INSERT OR IGNORE INTO CategoryData
                    (
                        discordID,
                        category,
                        elo,
                        peak_elo
                    )

                    VALUES (?, ?, ?, ?)
                """, (
                    user_id,
                    category,
                    old_elo,
                    old_elo
                ))


        connection.commit()


def ensure_user(member_id):

    with db_lock:

        cursor = connection.cursor()


        cursor.execute("""
            INSERT OR IGNORE INTO UserData
            (
                discordID,
                elo,
                category_reset
            )

            VALUES (?, 400, 0)
        """, (
            member_id,
        ))


        for category in CATEGORY_ROLES:

            cursor.execute("""
                INSERT OR IGNORE INTO CategoryData
                (
                    discordID,
                    category,
                    elo,
                    peak_elo
                )

                VALUES (?, ?, 400, 400)
            """, (
                member_id,
                category
            ))


        connection.commit()


def get_stats(
    member_id,
    category
):

    ensure_user(
        member_id
    )


    return db_execute(
        """
        SELECT *

        FROM CategoryData

        WHERE discordID = ?
        AND category = ?
        """,
        (
            member_id,
            category
        ),
        fetchone=True
    )


def set_elo(
    member_id,
    category,
    elo
):

    ensure_user(
        member_id
    )


    elo = max(
        0,
        int(elo)
    )


    db_execute(
        """
        UPDATE CategoryData

        SET
            elo = ?,
            peak_elo = MAX(peak_elo, ?)

        WHERE discordID = ?
        AND category = ?
        """,
        (
            elo,
            elo,
            member_id,
            category
        ),
        commit=True
    )


def update_stats(
    member_id,
    category,
    elo=None,
    wins=None,
    losses=None,
    streak=None,
    peak=None
):

    ensure_user(
        member_id
    )


    current = get_stats(
        member_id,
        category
    )


    new_elo = (
        current["elo"]
        if elo is None
        else max(0, int(elo))
    )


    new_wins = (
        current["wins"]
        if wins is None
        else int(wins)
    )


    new_losses = (
        current["losses"]
        if losses is None
        else int(losses)
    )


    new_streak = (
        current["current_streak"]
        if streak is None
        else int(streak)
    )


    new_peak = max(
        current["peak_elo"],
        new_elo if peak is None else int(peak)
    )


    db_execute(
        """
        UPDATE CategoryData

        SET
            elo = ?,
            wins = ?,
            losses = ?,
            current_streak = ?,
            peak_elo = ?

        WHERE discordID = ?
        AND category = ?
        """,
        (
            new_elo,
            new_wins,
            new_losses,
            new_streak,
            new_peak,
            member_id,
            category
        ),
        commit=True
    )


# ============================================================
# PROFILE RESET SYSTEM
# ============================================================

def get_profile_reset(member_id):

    return db_execute(
        """
        SELECT *

        FROM ProfileResets

        WHERE discordID = ?
        """,
        (
            member_id,
        ),
        fetchone=True
    )


def reset_profile(
    member_id,
    staff_id
):

    ensure_user(
        member_id
    )


    reset_time = datetime.now(
        timezone.utc
    ).isoformat()


    old_elos = {}


    with db_lock:

        cursor = connection.cursor()


        for category in CATEGORY_ROLES:

            row = cursor.execute("""
                SELECT elo

                FROM CategoryData

                WHERE discordID = ?
                AND category = ?
            """, (
                member_id,
                category
            )).fetchone()


            if row:

                old_elos[category] = int(
                    row["elo"]
                )

            else:

                old_elos[category] = 400


            cursor.execute("""
                UPDATE CategoryData

                SET
                    elo = 400,
                    wins = 0,
                    losses = 0,
                    current_streak = 0,
                    peak_elo = 400

                WHERE discordID = ?
                AND category = ?
            """, (
                member_id,
                category
            ))


        cursor.execute("""
            INSERT INTO ProfileResets
            (
                discordID,
                reset_at,
                reset_by
            )

            VALUES (?, ?, ?)

            ON CONFLICT(discordID)

            DO UPDATE SET
                reset_at = excluded.reset_at,
                reset_by = excluded.reset_by
        """, (
            member_id,
            reset_time,
            staff_id
        ))


        connection.commit()


    return (
        reset_time,
        old_elos
    )


# ============================================================
# RANK SYSTEM
# ============================================================

def get_rank(elo):

    if elo >= 2800:

        return "S-Tier"


    for rank, (
        minimum,
        maximum
    ) in reversed(
        list(AUTOMATIC_RANKS.items())
    ):

        if minimum <= elo <= maximum:

            return rank


    return "Unranked"


def get_manual_rank(
    member,
    category
):

    role_ids = TIER_ROLE_IDS[
        category
    ]


    sss_role = member.guild.get_role(
        role_ids["SSS-Tier"]
    )


    if (
        sss_role
        and
        sss_role in member.roles
    ):

        return "SSS-Tier"


    ss_role = member.guild.get_role(
        role_ids["SS-Tier"]
    )


    if (
        ss_role
        and
        ss_role in member.roles
    ):

        return "SS-Tier"


    return None


def get_display_rank(
    member,
    category
):

    manual_rank = get_manual_rank(
        member,
        category
    )


    if manual_rank:

        return manual_rank


    stats = get_stats(
        member.id,
        category
    )


    return get_rank(
        stats["elo"]
    )


# ============================================================
# PERMISSIONS
# ============================================================

def has_role(
    member,
    role_id
):

    role = member.guild.get_role(
        role_id
    )


    if role is None:

        return False


    return role in member.roles


def has_staff_permission(
    member
):

    return (
        has_role(
            member,
            MODERATOR_ROLE_ID
        )

        or

        has_role(
            member,
            DUELIST_STAFF_ROLE_ID
        )
    )


def has_elo_set_permission(
    member
):

    return has_role(
        member,
        ELO_SET_ROLE_ID
    )


async def deny(ctx):

    await ctx.response.send_message(
        "You do not have permission to use this command.",
        ephemeral=True
    )


# ============================================================
# ROLE MANAGEMENT
# ============================================================

async def update_category_role(
    guild,
    user,
    category
):

    ensure_user(
        user.id
    )


    stats = get_stats(
        user.id,
        category
    )


    rank = get_display_rank(
        user,
        category
    )


    role_ids = TIER_ROLE_IDS[
        category
    ]


    # --------------------------------------------------------
    # SS / SSS ARE MANUALLY CONTROLLED
    # --------------------------------------------------------

    manual_rank = get_manual_rank(
        user,
        category
    )


    if manual_rank:

        return manual_rank


    # --------------------------------------------------------
    # REMOVE OTHER CATEGORY TIER ROLES
    # --------------------------------------------------------

    for tier_name, role_id in role_ids.items():

        role = guild.get_role(
            role_id
        )


        if role is None:

            continue


        if (
            role in user.roles
            and
            tier_name != rank
        ):

            try:

                await user.remove_roles(
                    role
                )

            except discord.HTTPException as error:

                print(
                    f"Could not remove {role.name} "
                    f"from {user}: {error}"
                )


    # --------------------------------------------------------
    # ADD CURRENT RANK
    # --------------------------------------------------------

    target_role = guild.get_role(
        role_ids[rank]
    )


    if target_role is not None:

        if target_role not in user.roles:

            try:

                await user.add_roles(
                    target_role
                )

            except discord.HTTPException as error:

                print(
                    f"Could not add {target_role.name} "
                    f"to {user}: {error}"
                )


    return rank


async def update_all_roles(
    guild,
    user
):

    ensure_user(
        user.id
    )


    ranks = {}


    for category in CATEGORY_ROLES:

        ranks[category] = await update_category_role(
            guild,
            user,
            category
        )


    return ranks


# ============================================================
# LOG CHANNEL
# ============================================================

async def get_logs_channel():

    try:

        return await client.fetch_channel(
            LOGS_CHANNEL_ID
        )

    except (
        discord.NotFound,
        discord.Forbidden,
        discord.HTTPException
    ):

        return None


# ============================================================
# ELO CALCULATION
# ============================================================

def probability(
    rating1,
    rating2
):

    return 1.0 / (
        1
        +
        math.pow(
            10,
            (rating1 - rating2) / 1500.0
        )
    )


def elo_rating(
    Ra,
    Rb,
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

        Ra = round(
            Ra
            +
            (K * multiplier)
            *
            (outcome - Pa)
        )


        Rb = round(
            Rb
            +
            (K * multiplier)
            *
            ((1 - outcome) - Pb)
        )


    else:

        Ra = round(
            Ra
            +
            K
            *
            (outcome - Pa)
        )


        Rb = round(
            Rb
            +
            K
            *
            ((1 - outcome) - Pb)
        )


    return (
        max(0, Ra),
        max(0, Rb)
    )


# ============================================================
# MATCH IDS
# ============================================================

def new_match_code():

    row = db_execute(
        """
        SELECT
            COALESCE(MAX(id), 0) + 1 AS next_id

        FROM Matches
        """,
        fetchone=True
    )


    return f"DUEL-{row['next_id']:05d}"


# ============================================================
# AUDIT SYSTEM
# ============================================================

def audit(
    member_id,
    category,
    old_elo,
    new_elo,
    action,
    match_code,
    staff_id
):

    db_execute(
        """
        INSERT INTO EloAudit
        (
            discordID,
            category,
            old_elo,
            new_elo,
            action,
            match_code,
            staff_id,
            created_at
        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            member_id,
            category,
            old_elo,
            new_elo,
            action,
            match_code,
            staff_id,
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        commit=True
    )


# ============================================================
# CATEGORY CHOICES
# ============================================================

CATEGORY_CHOICES = [

    app_commands.Choice(
        name=category,
        value=category
    )

    for category in CATEGORY_ROLES
]


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


@client.event
async def on_member_join(member):

    ensure_user(
        member.id
    )


    await update_all_roles(
        member.guild,
        member
    )


# ============================================================
# /ELO_SET
# ============================================================

@tree.command(
    name="elo_set",
    description="Set a user's ELO.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    member="The user whose ELO you want to set.",
    category="The category.",
    elo="The new ELO."
)

@app_commands.choices(
    category=CATEGORY_CHOICES
)

async def elo_set(
    ctx,
    member: discord.Member,
    category: str,
    elo: int
):

    if not has_elo_set_permission(
        ctx.user
    ):

        await deny(ctx)
        return


    old_elo = get_stats(
        member.id,
        category
    )["elo"]


    new_elo = max(
        0,
        elo
    )


    set_elo(
        member.id,
        category,
        new_elo
    )


    audit(
        member.id,
        category,
        old_elo,
        new_elo,
        "ELO SET",
        None,
        ctx.user.id
    )


    rank = await update_category_role(
        ctx.guild,
        member,
        category
    )


    await ctx.response.send_message(
        f"{member.mention}'s **{category}** ELO "
        f"was set to **{new_elo}**.\n"
        f"Rank: **{rank}**"
    )


# ============================================================
# /ELO_ADD
# ============================================================

@tree.command(
    name="elo_add",
    description="Add ELO to a user.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    member="The user.",
    category="The category.",
    elo="The amount of ELO to add."
)

@app_commands.choices(
    category=CATEGORY_CHOICES
)

async def elo_add(
    ctx,
    member: discord.Member,
    category: str,
    elo: int
):

    if not has_staff_permission(
        ctx.user
    ):

        await deny(ctx)
        return


    if elo < 0:

        await ctx.response.send_message(
            "ELO amount cannot be negative.",
            ephemeral=True
        )

        return


    old_elo = get_stats(
        member.id,
        category
    )["elo"]


    new_elo = old_elo + elo


    set_elo(
        member.id,
        category,
        new_elo
    )


    audit(
        member.id,
        category,
        old_elo,
        new_elo,
        "ELO ADD",
        None,
        ctx.user.id
    )


    rank = await update_category_role(
        ctx.guild,
        member,
        category
    )


    await ctx.response.send_message(
        f"Added **{elo} ELO** to "
        f"{member.mention}'s **{category}** rating.\n"
        f"**{old_elo} → {new_elo}**\n"
        f"Rank: **{rank}**"
    )


# ============================================================
# /ELO_REMOVE
# ============================================================

@tree.command(
    name="elo_remove",
    description="Remove ELO from a user.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    member="The user.",
    category="The category.",
    elo="The amount of ELO to remove."
)

@app_commands.choices(
    category=CATEGORY_CHOICES
)

async def elo_remove(
    ctx,
    member: discord.Member,
    category: str,
    elo: int
):

    if not has_staff_permission(
        ctx.user
    ):

        await deny(ctx)
        return


    if elo < 0:

        await ctx.response.send_message(
            "ELO amount cannot be negative.",
            ephemeral=True
        )

        return


    old_elo = get_stats(
        member.id,
        category
    )["elo"]


    new_elo = max(
        0,
        old_elo - elo
    )


    set_elo(
        member.id,
        category,
        new_elo
    )


    audit(
        member.id,
        category,
        old_elo,
        new_elo,
        "ELO REMOVE",
        None,
        ctx.user.id
    )


    rank = await update_category_role(
        ctx.guild,
        member,
        category
    )


    await ctx.response.send_message(
        f"Removed **{elo} ELO** from "
        f"{member.mention}'s **{category}** rating.\n"
        f"**{old_elo} → {new_elo}**\n"
        f"Rank: **{rank}**"
    )


# ============================================================
# /ELO_CHECK
# ============================================================

@tree.command(
    name="elo_check",
    description="Check a user's ELO.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    category="The category.",
    member="The user."
)

@app_commands.choices(
    category=CATEGORY_CHOICES
)

async def elo_check(
    ctx,
    category: str,
    member: Optional[discord.Member] = None
):

    member = member or ctx.user


    stats = get_stats(
        member.id,
        category
    )


    rank = get_display_rank(
        member,
        category
    )


    await ctx.response.send_message(
        f"{member.mention}\n"
        f"**Category:** {category}\n"
        f"**ELO:** {stats['elo']}\n"
        f"**Rank:** {rank}"
    )


# ============================================================
# /ELO_PREVIEW
# ============================================================

@tree.command(
    name="elo_preview",
    description="Preview the ELO change for a match.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    winner="The winner.",
    loser="The loser.",
    category="The category."
)

@app_commands.choices(
    category=CATEGORY_CHOICES
)

async def elo_preview(
    ctx,
    winner: discord.Member,
    loser: discord.Member,
    category: str
):

    if winner.id == loser.id:

        await ctx.response.send_message(
            "Winner and loser must be different users.",
            ephemeral=True
        )

        return


    winner_stats = get_stats(
        winner.id,
        category
    )


    loser_stats = get_stats(
        loser.id,
        category
    )


    winner_after, loser_after = elo_rating(
        winner_stats["elo"],
        loser_stats["elo"],
        1
    )


    await ctx.response.send_message(
        f"**{category} ELO Preview**\n\n"
        f"{winner.mention}: "
        f"**{winner_stats['elo']} → {winner_after}** "
        f"({winner_after - winner_stats['elo']:+d})\n"
        f"{loser.mention}: "
        f"**{loser_stats['elo']} → {loser_after}** "
        f"({loser_after - loser_stats['elo']:+d})"
    )


# ============================================================
# /SUBMIT_MATCH
# ============================================================

@tree.command(
    name="submit_match",
    description="Submit a standard match.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    winner="The winner.",
    loser="The loser.",
    category="The category.",
    proof="Proof of the duel."
)

@app_commands.choices(
    category=CATEGORY_CHOICES
)

async def submit_match(
    ctx,
    winner: discord.Member,
    loser: discord.Member,
    category: str,
    proof: str
):

    if not has_staff_permission(
        ctx.user
    ):

        await deny(ctx)
        return


    if winner.id == loser.id:

        await ctx.response.send_message(
            "Winner and loser must be different users.",
            ephemeral=True
        )

        return


    winner_stats = get_stats(
        winner.id,
        category
    )


    loser_stats = get_stats(
        loser.id,
        category
    )


    winner_before = winner_stats["elo"]
    loser_before = loser_stats["elo"]


    winner_after, loser_after = elo_rating(
        winner_before,
        loser_before,
        1
    )


    match_code = new_match_code()


    created_at = datetime.now(
        timezone.utc
    ).isoformat()


    duplicate = db_execute(
        """
        SELECT match_code

        FROM Matches

        WHERE category = ?

        AND undone = 0

        AND (
            (winner_id = ? AND loser_id = ?)
            OR
            (winner_id = ? AND loser_id = ?)
        )

        AND created_at >= datetime('now', '-60 seconds')

        LIMIT 1
        """,
        (
            category,
            winner.id,
            loser.id,
            loser.id,
            winner.id
        ),
        fetchone=True
    )


    if duplicate:

        await ctx.response.send_message(
            f"A very recent match already exists for these "
            f"players: **{duplicate['match_code']}**.\n"
            f"If this is a separate duel, wait before submitting it.",
            ephemeral=True
        )

        return


    db_execute(
        """
        INSERT INTO Matches
        (
            match_code,
            category,

            winner_id,
            loser_id,

            winner_elo_before,
            winner_elo_after,

            loser_elo_before,
            loser_elo_after,

            winner_wins_before,
            winner_losses_before,
            winner_streak_before,

            loser_wins_before,
            loser_losses_before,
            loser_streak_before,

            proof,
            submitted_by,
            match_type,
            created_at,
            undone
        )

        VALUES
        (
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, 0
        )
        """,
        (
            match_code,
            category,

            winner.id,
            loser.id,

            winner_before,
            winner_after,

            loser_before,
            loser_after,

            winner_stats["wins"],
            winner_stats["losses"],
            winner_stats["current_streak"],

            loser_stats["wins"],
            loser_stats["losses"],
            loser_stats["current_streak"],

            proof,
            ctx.user.id,

            "Standard",
            created_at
        ),
        commit=True
    )


    update_stats(
        winner.id,
        category,

        elo=winner_after,
        wins=winner_stats["wins"] + 1,
        losses=winner_stats["losses"],
        streak=winner_stats["current_streak"] + 1,
        peak=winner_after
    )


    update_stats(
        loser.id,
        category,

        elo=loser_after,
        wins=loser_stats["wins"],
        losses=loser_stats["losses"] + 1,
        streak=0,
        peak=loser_stats["peak_elo"]
    )


    audit(
        winner.id,
        category,
        winner_before,
        winner_after,
        "MATCH WIN",
        match_code,
        ctx.user.id
    )


    audit(
        loser.id,
        category,
        loser_before,
        loser_after,
        "MATCH LOSS",
        match_code,
        ctx.user.id
    )


    await update_category_role(
        ctx.guild,
        winner,
        category
    )


    await update_category_role(
        ctx.guild,
        loser,
        category
    )


    embed = discord.Embed(
        title=f"Match {match_code}",
        description=(
            f"**Category:** {category}\n\n"

            f"**Winner:** {winner.mention}\n"
            f"ELO: **{winner_before} → {winner_after}** "
            f"({winner_after - winner_before:+d})\n\n"

            f"**Loser:** {loser.mention}\n"
            f"ELO: **{loser_before} → {loser_after}** "
            f"({loser_after - loser_before:+d})\n\n"

            f"**Proof:** {proof}\n"
            f"**Submitted by:** {ctx.user.mention}"
        )
    )


    await ctx.response.send_message(
        embed=embed
    )


    logs = await get_logs_channel()


    if logs:

        await logs.send(
            embed=embed
        )


# ============================================================
# /SUBMIT_TIERED_MATCH
# ============================================================

@tree.command(
    name="submit_tiered_match",
    description="Submit a tiered match.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    winner="The winner.",
    loser="The loser.",
    category="The category.",
    proof="Proof of the duel.",
    challengerstatus="Whether the challenger won or lost."
)

@app_commands.choices(
    category=CATEGORY_CHOICES,

    challengerstatus=[
        app_commands.Choice(
            name="Challenger Won",
            value="won"
        ),

        app_commands.Choice(
            name="Challenger Lost",
            value="lost"
        )
    ]
)

async def submit_tiered_match(
    ctx,
    winner: discord.Member,
    loser: discord.Member,
    category: str,
    proof: str,
    challengerstatus: str
):

    if not has_staff_permission(
        ctx.user
    ):

        await deny(ctx)
        return


    if winner.id == loser.id:

        await ctx.response.send_message(
            "Winner and loser must be different users.",
            ephemeral=True
        )

        return


    winner_stats = get_stats(
        winner.id,
        category
    )


    loser_stats = get_stats(
        loser.id,
        category
    )


    winner_before = winner_stats["elo"]
    loser_before = loser_stats["elo"]


    loser_rank = get_display_rank(
        loser,
        category
    )


    if (
        challengerstatus == "won"
        and
        loser_rank in PLACEMENT_ELO
    ):

        winner_after = PLACEMENT_ELO[
            loser_rank
        ]


        loser_after = max(
            0,
            loser_before - 250
        )


        match_type = (
            "Tiered - Challenger Won"
        )


    else:

        winner_after, loser_after = elo_rating(
            winner_before,
            loser_before,
            1
        )


        match_type = (
            "Tiered - Challenger Lost"
        )


    match_code = new_match_code()


    created_at = datetime.now(
        timezone.utc
    ).isoformat()


    db_execute(
        """
        INSERT INTO Matches
        (
            match_code,
            category,

            winner_id,
            loser_id,

            winner_elo_before,
            winner_elo_after,

            loser_elo_before,
            loser_elo_after,

            winner_wins_before,
            winner_losses_before,
            winner_streak_before,

            loser_wins_before,
            loser_losses_before,
            loser_streak_before,

            proof,
            submitted_by,
            match_type,
            created_at,
            undone
        )

        VALUES
        (
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, 0
        )
        """,
        (
            match_code,
            category,

            winner.id,
            loser.id,

            winner_before,
            winner_after,

            loser_before,
            loser_after,

            winner_stats["wins"],
            winner_stats["losses"],
            winner_stats["current_streak"],

            loser_stats["wins"],
            loser_stats["losses"],
            loser_stats["current_streak"],

            proof,
            ctx.user.id,

            match_type,
            created_at
        ),
        commit=True
    )


    update_stats(
        winner.id,
        category,

        elo=winner_after,
        wins=winner_stats["wins"] + 1,
        losses=winner_stats["losses"],
        streak=winner_stats["current_streak"] + 1,
        peak=winner_after
    )


    update_stats(
        loser.id,
        category,

        elo=loser_after,
        wins=loser_stats["wins"],
        losses=loser_stats["losses"] + 1,
        streak=0,
        peak=loser_stats["peak_elo"]
    )


    audit(
        winner.id,
        category,
        winner_before,
        winner_after,
        "TIERED MATCH WIN",
        match_code,
        ctx.user.id
    )


    audit(
        loser.id,
        category,
        loser_before,
        loser_after,
        "TIERED MATCH LOSS",
        match_code,
        ctx.user.id
    )


    await update_category_role(
        ctx.guild,
        winner,
        category
    )


    await update_category_role(
        ctx.guild,
        loser,
        category
    )


    embed = discord.Embed(
        title=f"Tiered Match {match_code}",
        description=(
            f"**Category:** {category}\n"
            f"**Type:** {match_type}\n\n"

            f"**Winner:** {winner.mention}\n"
            f"ELO: **{winner_before} → {winner_after}**\n\n"

            f"**Loser:** {loser.mention}\n"
            f"ELO: **{loser_before} → {loser_after}**\n\n"

            f"**Proof:** {proof}\n"
            f"**Submitted by:** {ctx.user.mention}"
        )
    )


    await ctx.response.send_message(
        embed=embed
    )


    logs = await get_logs_channel()


    if logs:

        await logs.send(
            embed=embed
        )


# ============================================================
# /LEADERBOARD
# ============================================================

@tree.command(
    name="leaderboard",
    description="Check the category leaderboard.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    category="The category."
)

@app_commands.choices(
    category=CATEGORY_CHOICES
)

async def leaderboard(
    ctx,
    category: str
):

    rows = db_execute(
        """
        SELECT
            discordID,
            elo,
            wins,
            losses

        FROM CategoryData

        WHERE category = ?

        ORDER BY elo DESC

        LIMIT 10
        """,
        (
            category,
        ),
        fetchall=True
    )


    if not rows:

        await ctx.response.send_message(
            "No players found."
        )

        return


    lines = []


    for index, row in enumerate(
        rows,
        start=1
    ):

        lines.append(
            f"**{index}.** "
            f"<@{row['discordID']}> — "
            f"**{row['elo']} ELO** "
            f"({row['wins']}W / {row['losses']}L)"
        )


    await ctx.response.send_message(
        f"**{category} Leaderboard**\n\n"
        +
        "\n".join(lines)
    )


# ============================================================
# /CHECK_LEADERBOARD
# ============================================================

@tree.command(
    name="check_leaderboard",
    description="Check the current standings.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    category="The category."
)

@app_commands.choices(
    category=CATEGORY_CHOICES
)

async def check_leaderboard(
    ctx,
    category: str
):

    rows = db_execute(
        """
        SELECT
            discordID,
            elo,
            wins,
            losses

        FROM CategoryData

        WHERE category = ?

        ORDER BY elo DESC

        LIMIT 10
        """,
        (
            category,
        ),
        fetchall=True
    )


    if not rows:

        await ctx.response.send_message(
            "No players found."
        )

        return


    lines = []


    for index, row in enumerate(
        rows,
        start=1
    ):

        lines.append(
            f"**{index}.** "
            f"<@{row['discordID']}> — "
            f"**{row['elo']} ELO** "
            f"({row['wins']}W / {row['losses']}L)"
        )


    await ctx.response.send_message(
        f"**{category} Leaderboard**\n\n"
        +
        "\n".join(lines)
    )


# ============================================================
# /PROFILE
# ============================================================

@tree.command(
    name="profile",
    description="Show a player's competitive profile.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    member="The user."
)

async def profile(
    ctx,
    member: Optional[discord.Member] = None
):

    member = member or ctx.user


    ensure_user(
        member.id
    )


    embed = discord.Embed(
        title=f"{member.display_name}'s Profile"
    )


    for category in CATEGORY_ROLES:

        stats = get_stats(
            member.id,
            category
        )


        rank = get_display_rank(
            member,
            category
        )


        total_matches = (
            stats["wins"]
            +
            stats["losses"]
        )


        if total_matches > 0:

            winrate = (
                stats["wins"]
                /
                total_matches
                *
                100
            )

        else:

            winrate = 0


        embed.add_field(
            name=category,

            value=(
                f"**ELO:** {stats['elo']}\n"
                f"**Rank:** {rank}\n"
                f"**Wins:** {stats['wins']}\n"
                f"**Losses:** {stats['losses']}\n"
                f"**Win Rate:** {winrate:.1f}%\n"
                f"**Current Win Streak:** "
                f"{stats['current_streak']}\n"
                f"**Peak ELO:** {stats['peak_elo']}\n"
                f"**Matches:** {total_matches}"
            ),

            inline=False
        )


    await ctx.response.send_message(
        embed=embed
    )


# ============================================================
# /PROFILE_RESET
# ============================================================

@tree.command(
    name="profile_reset",
    description="Completely reset a player's competitive profile.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    member="The user whose profile you want to reset."
)

async def profile_reset(
    ctx,
    member: discord.Member
):

    if not has_elo_set_permission(
        ctx.user
    ):

        await deny(ctx)
        return

    if member.bot:

        await ctx.response.send_message(
            "You cannot reset a bot's profile.",
            ephemeral=True
        )

        return


        # ----------------------------------------------------
        # REMOVE ALL TIER ROLES AND GIVE UNRANKED
        # ----------------------------------------------------

        role_errors = 0


        for category in CATEGORY_ROLES:

            role_ids = TIER_ROLE_IDS[
                category
            ]


            for tier_name, role_id in role_ids.items():

                role = ctx.guild.get_role(
                    role_id
                )


                if role is None:

                    continue


                if role in member.roles:

                    try:

                        await member.remove_roles(
                            role
                        )

                    except discord.HTTPException as error:

                        role_errors += 1

                        print(
                            f"Could not remove {role.name} "
                            f"from {member}: {error}"
                        )


            unranked_role = ctx.guild.get_role(
                role_ids["Unranked"]
            )


            if (
                unranked_role
                and
                unranked_role not in member.roles
            ):

                try:

                    await member.add_roles(
                        unranked_role
                    )

                except discord.HTTPException as error:

                    role_errors += 1

                    print(
                        f"Could not add {unranked_role.name} "
                        f"to {member}: {error}"
                    )


            # ------------------------------------------------
            # AUDIT RESET
            # ------------------------------------------------

            audit(
                member.id,
                category,
                old_elos[category],
                400,
                "PROFILE RESET",
                None,
                ctx.user.id
            )


        # ----------------------------------------------------
        # LOG
        # ----------------------------------------------------

        reset_embed = discord.Embed(
            title="Profile Reset",
            description=(
                f"**User:** {member.mention}\n"
                f"**Reset by:** {ctx.user.mention}\n\n"

                f"**Duelist:** "
                f"{old_elos['Duelist']} → 400\n"

                f"**Soldier:** "
                f"{old_elos['Soldier']} → 400\n"

                f"**Aether Wielder:** "
                f"{old_elos['Aether Wielder']} → 400"
            )
        )


        logs = await get_logs_channel()


        if logs:

            await logs.send(
                embed=reset_embed
            )


        # ----------------------------------------------------
        # DISABLE BUTTONS
        # ----------------------------------------------------

        confirm_button.disabled = True
        cancel_button.disabled = True


        if role_errors:

            result_text = (
                f"Profile for {member.mention} has been reset.\n\n"
                f"All ELO/stats were reset to **400/0**.\n"
                f"Old match history remains stored but is hidden "
                f"from the reset profile.\n\n"
                f"⚠️ {role_errors} role update(s) failed. "
                f"Check the bot's role hierarchy."
            )

        else:

            result_text = (
                f"Profile for {member.mention} has been reset.\n\n"
                f"All categories are now **400 ELO** and **Unranked**.\n"
                f"Wins, losses, streaks and peak ELO were reset.\n"
                f"Previous match history remains stored but is hidden "
                f"from the reset profile."
            )


        await interaction.response.edit_message(
            content=result_text,
            view=view
        )


        view.stop()


    async def cancel_callback(
        interaction
    ):

        confirm_button.disabled = True
        cancel_button.disabled = True


        await interaction.response.edit_message(
            content="Profile reset cancelled.",
            view=view
        )


        view.stop()


    confirm_button.callback = confirm_callback
    cancel_button.callback = cancel_callback


    view.add_item(
        confirm_button
    )

    view.add_item(
        cancel_button
    )


    await ctx.response.send_message(
        f"⚠️ **Profile Reset Confirmation**\n\n"
        f"You are about to completely reset "
        f"{member.mention}'s competitive profile.\n\n"
        f"This will reset:\n"
        f"• Duelist ELO/stats\n"
        f"• Soldier ELO/stats\n"
        f"• Aether Wielder ELO/stats\n"
        f"• Wins and losses\n"
        f"• Current streaks\n"
        f"• Peak ELO\n"
        f"• All tier roles\n\n"
        f"The player will be returned to **Unranked**.\n\n"
        f"Are you sure?",
        view=view,
        ephemeral=True
    )


# ============================================================
# /MATCH_HISTORY
# ============================================================

@tree.command(
    name="match_history",
    description="Show a player's recent matches.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    member="The user.",
    category="Optional category."
)

async def match_history(
    ctx,
    member: Optional[discord.Member] = None,
    category: Optional[str] = None
):

    member = member or ctx.user


    if (
        category is not None
        and
        category not in CATEGORY_ROLES
    ):

        await ctx.response.send_message(
            "Invalid category.",
            ephemeral=True
        )

        return


    reset = get_profile_reset(
        member.id
    )


    reset_time = (
        reset["reset_at"]
        if reset
        else None
    )


    if category:

        rows = db_execute(
            """
            SELECT *

            FROM Matches

            WHERE category = ?

            AND undone = 0

            AND (
                winner_id = ?
                OR
                loser_id = ?
            )

            AND (
                ? IS NULL
                OR
                created_at > ?
            )

            ORDER BY id DESC

            LIMIT 10
            """,
            (
                category,
                member.id,
                member.id,
                reset_time,
                reset_time
            ),
            fetchall=True
        )


    else:

        rows = db_execute(
            """
            SELECT *

            FROM Matches

            WHERE undone = 0

            AND (
                winner_id = ?
                OR
                loser_id = ?
            )

            AND (
                ? IS NULL
                OR
                created_at > ?
            )

            ORDER BY id DESC

            LIMIT 10
            """,
            (
                member.id,
                member.id,
                reset_time,
                reset_time
            ),
            fetchall=True
        )


    if not rows:

        await ctx.response.send_message(
            "No match history found."
        )

        return


    lines = []


    for row in rows:

        is_winner = (
            row["winner_id"]
            ==
            member.id
        )


        if is_winner:

            opponent = row["loser_id"]

            before = (
                row["winner_elo_before"]
            )

            after = (
                row["winner_elo_after"]
            )

            result = "WIN"


        else:

            opponent = row["winner_id"]

            before = (
                row["loser_elo_before"]
            )

            after = (
                row["loser_elo_after"]
            )

            result = "LOSS"


        lines.append(
            f"**{row['match_code']}** • "
            f"{row['category']} • "
            f"**{result}** vs "
            f"<@{opponent}> • "
            f"{before} → {after}"
        )


    await ctx.response.send_message(
        f"**{member.display_name}'s Match History**\n\n"
        +
        "\n".join(lines)
    )


# ============================================================
# /ELO_UNDO
# ============================================================

@tree.command(
    name="elo_undo",
    description="Undo a match.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    match_code="The match ID, e.g. DUEL-00001."
)

async def elo_undo(
    ctx,
    match_code: str
):

    if not has_staff_permission(
        ctx.user
    ):

        await deny(ctx)
        return


    match_code = match_code.upper().strip()


    row = db_execute(
        """
        SELECT *

        FROM Matches

        WHERE match_code = ?
        """,
        (
            match_code,
        ),
        fetchone=True
    )


    if row is None:

        await ctx.response.send_message(
            "Match not found.",
            ephemeral=True
        )

        return


    if row["undone"]:

        await ctx.response.send_message(
            "That match has already been undone.",
            ephemeral=True
        )

        return


    # --------------------------------------------------------
    # PROFILE RESET PROTECTION
    # --------------------------------------------------------

    winner_reset = get_profile_reset(
        row["winner_id"]
    )


    loser_reset = get_profile_reset(
        row["loser_id"]
    )


    if (
        winner_reset
        and
        row["created_at"] <= winner_reset["reset_at"]
    ):

        await ctx.response.send_message(
            "That match occurred before the winner's "
            "profile reset and cannot be undone.",
            ephemeral=True
        )

        return


    if (
        loser_reset
        and
        row["created_at"] <= loser_reset["reset_at"]
    ):

        await ctx.response.send_message(
            "That match occurred before the loser's "
            "profile reset and cannot be undone.",
            ephemeral=True
        )

        return


    # --------------------------------------------------------
    # ONLY ALLOW UNDOING THE MOST RECENT MATCH INVOLVING
    # EITHER PLAYER IN THAT CATEGORY.
    # --------------------------------------------------------

    latest = db_execute(
        """
        SELECT id

        FROM Matches

        WHERE category = ?

        AND undone = 0

        AND (
            winner_id IN (?, ?)
            OR
            loser_id IN (?, ?)
        )

        ORDER BY id DESC

        LIMIT 1
        """,
        (
            row["category"],

            row["winner_id"],
            row["loser_id"],

            row["winner_id"],
            row["loser_id"]
        ),
        fetchone=True
    )


    if (
        latest is None
        or
        latest["id"] != row["id"]
    ):

        await ctx.response.send_message(
            "Only the most recent match involving either "
            "player in that category can be undone.",
            ephemeral=True
        )

        return


    # --------------------------------------------------------
    # RESTORE WINNER
    # --------------------------------------------------------

    update_stats(
        row["winner_id"],
        row["category"],

        elo=row["winner_elo_before"],

        wins=row["winner_wins_before"],

        losses=row["winner_losses_before"],

        streak=row["winner_streak_before"],

        peak=row["winner_elo_before"]
    )


    # --------------------------------------------------------
    # RESTORE LOSER
    # --------------------------------------------------------

    update_stats(
        row["loser_id"],
        row["category"],

        elo=row["loser_elo_before"],

        wins=row["loser_wins_before"],

        losses=row["loser_losses_before"],

        streak=row["loser_streak_before"],

        peak=row["loser_elo_before"]
    )


    # --------------------------------------------------------
    # MARK MATCH AS UNDONE
    # --------------------------------------------------------

    db_execute(
        """
        UPDATE Matches

        SET undone = 1

        WHERE id = ?
        """,
        (
            row["id"],
        ),
        commit=True
    )


    # --------------------------------------------------------
    # AUDIT
    # --------------------------------------------------------

    audit(
        row["winner_id"],
        row["category"],

        row["winner_elo_after"],
        row["winner_elo_before"],

        "MATCH UNDO",

        row["match_code"],

        ctx.user.id
    )


    audit(
        row["loser_id"],
        row["category"],

        row["loser_elo_after"],
        row["loser_elo_before"],

        "MATCH UNDO",

        row["match_code"],

        ctx.user.id
    )


    # --------------------------------------------------------
    # UPDATE ROLES
    # --------------------------------------------------------

    winner = ctx.guild.get_member(
        row["winner_id"]
    )


    loser = ctx.guild.get_member(
        row["loser_id"]
    )


    if winner:

        await update_category_role(
            ctx.guild,
            winner,
            row["category"]
        )


    if loser:

        await update_category_role(
            ctx.guild,
            loser,
            row["category"]
        )


    await ctx.response.send_message(
        f"Match **{row['match_code']}** has been undone."
    )


# ============================================================
# /RANK_SET
# ============================================================

@tree.command(
    name="rank_set",
    description="Manually assign SS or SSS.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    member="The user.",
    category="The category.",
    rank="The manual rank."
)

@app_commands.choices(
    category=CATEGORY_CHOICES,

    rank=[
        app_commands.Choice(
            name="SS-Tier",
            value="SS-Tier"
        ),

        app_commands.Choice(
            name="SSS-Tier",
            value="SSS-Tier"
        )
    ]
)

async def rank_set(
    ctx,
    member: discord.Member,
    category: str,
    rank: str
):

    if not has_staff_permission(
        ctx.user
    ):

        await deny(ctx)
        return


    role_ids = TIER_ROLE_IDS[
        category
    ]


    for other_rank in (
        "SS-Tier",
        "SSS-Tier"
    ):

        role = ctx.guild.get_role(
            role_ids[other_rank]
        )


        if (
            role
            and
            role in member.roles
        ):

            await member.remove_roles(
                role
            )


    target_role = ctx.guild.get_role(
        role_ids[rank]
    )


    if target_role is None:

        await ctx.response.send_message(
            "That tier role could not be found.",
            ephemeral=True
        )

        return


    await member.add_roles(
        target_role
    )


    await ctx.response.send_message(
        f"{member.mention} is now "
        f"**{rank}** in **{category}**."
    )


# ============================================================
# /RANK_REMOVE
# ============================================================

@tree.command(
    name="rank_remove",
    description="Remove a manual SS or SSS rank.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    member="The user.",
    category="The category."
)

@app_commands.choices(
    category=CATEGORY_CHOICES
)

async def rank_remove(
    ctx,
    member: discord.Member,
    category: str
):

    if not has_staff_permission(
        ctx.user
    ):

        await deny(ctx)
        return


    role_ids = TIER_ROLE_IDS[
        category
    ]


    for rank in (
        "SS-Tier",
        "SSS-Tier"
    ):

        role = ctx.guild.get_role(
            role_ids[rank]
        )


        if (
            role
            and
            role in member.roles
        ):

            await member.remove_roles(
                role
            )


    automatic_rank = await update_category_role(
        ctx.guild,
        member,
        category
    )


    await ctx.response.send_message(
        f"Removed the manual SS/SSS rank from "
        f"{member.mention}.\n"
        f"Automatic rank: **{automatic_rank}**"
    )


# ============================================================
# /UPDATE_USER
# ============================================================

@tree.command(
    name="update_user",
    description="Update all category roles for a user.",
    guild=discord.Object(id=SERVER_ID)
)

@app_commands.describe(
    member="The user."
)

async def update_user(
    ctx,
    member: discord.Member
):

    if not has_staff_permission(
        ctx.user
    ):

        await deny(ctx)
        return


    ranks = await update_all_roles(
        ctx.guild,
        member
    )


    result = " | ".join(
        f"{category}: **{rank}**"
        for category, rank in ranks.items()
    )


    await ctx.response.send_message(
        f"Updated {member.mention}:\n{result}"
    )


# ============================================================
# /SAY
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
    ctx,
    message: str
):

    required_role = ctx.guild.get_role(
        SAY_ROLE_ID
    )


    if required_role is None:

        await ctx.response.send_message(
            "The required /say role could not be found.",
            ephemeral=True
        )

        return


    if required_role not in ctx.user.roles:

        await deny(ctx)
        return


    await ctx.response.send_message(
        "Message sent.",
        ephemeral=True
    )


    await ctx.channel.send(
        message
    )


# ============================================================
# SPECIAL MESSAGE
# ============================================================

@client.event
async def on_message(message):

    if message.author.bot:

        return


    if (
        message.author.id
        ==
        1286730886074597389

        and

        message.content == "say it"
    ):

        logs_channel = await get_logs_channel()


        if logs_channel:

            await logs_channel.send(
                "soup is the GOAT!!!!! :fire:"
            )


# ============================================================
# DATABASE BACKUP
# ============================================================

def backup_database():

    try:

        source = Path(
            "duelist.db"
        )


        if not source.exists():

            return


        backup_directory = Path(
            "backups"
        )


        backup_directory.mkdir(
            exist_ok=True
        )


        destination = (
            backup_directory
            /
            "duelist_latest.db"
        )


        shutil.copy2(
            source,
            destination
        )


        print(
            "Database backup created."
        )


    except OSError as error:

        print(
            f"Database backup failed: {error}"
        )


# ============================================================
# FLASK KEEP-ALIVE
# ============================================================

app = Flask(__name__)


@app.route(
    "/",
    methods=["GET", "HEAD"]
)

def home():

    return (
        "Bot is running!",
        200
    )


def run_flask():

    port = int(
        os.environ.get(
            "PORT",
            8080
        )
    )


    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )


# ============================================================
# START BOT
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "TOKEN environment variable is not set."
    )


create_database()


backup_database()


threading.Thread(
    target=run_flask,
    daemon=True
).start()


client.run(
    TOKEN
)
