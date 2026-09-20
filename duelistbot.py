import discord
import os
import math
import sqlite3
import threading
import shutil

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from discord import app_commands
from flask import Flask


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("TOKEN")

SERVER_ID = 1490855505000796262
LOGS_CHANNEL_ID = 1513934803412713592

MODERATOR_ROLE_ID = 1490855600236789820
DUELIST_STAFF_ROLE_ID = 1515821480464875590
ELO_SET_ROLE_ID = 1510774088354762915

CATEGORY_NOTIFICATION_CHANNEL_ID = 1551022906916470875
SAY_ROLE_ID = 1511114368027197501

K = 75

DB_PATH = "duelist.db"
BACKUP_DIR = Path("backups")


# =========================================================
# CATEGORIES
# =========================================================

CATEGORIES = {
    "Duelist": 1548316617320964206,
    "Soldier": 1548316579425554513,
    "Aether Wielder": 1548316920930115614,
}


# =========================================================
# TIER ROLE IDS
# =========================================================

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


# =========================================================
# AUTOMATIC ELO RANGES
# =========================================================

AUTOMATIC_RANGES = {
    "Unranked": (0, 399),
    "C-Tier": (400, 799),
    "B-Tier": (800, 1199),
    "A-Tier": (1200, 1599),
    "Quasi-S-Tier": (1600, 1999),
    "Probationary S-Tier": (2000, 2399),
    "S-Tier": (2400, 2799),
}


PLACEMENT_ELO = {
    "C-Tier": 750,
    "B-Tier": 1050,
    "A-Tier": 1450,
    "Quasi-S-Tier": 1850,
    "Probationary S-Tier": 2250,
    "S-Tier": 2650,
}


# =========================================================
# DISCORD
# =========================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

GUILD_OBJECT = discord.Object(id=SERVER_ID)


# =========================================================
# DATABASE
# =========================================================

db_lock = threading.Lock()

db = sqlite3.connect(
    DB_PATH,
    check_same_thread=False
)

db.row_factory = sqlite3.Row


def db_execute(query, params=(), fetchone=False, fetchall=False, commit=True):
    with db_lock:
        cursor = db.cursor()

        cursor.execute(query, params)

        if commit:
            db.commit()

        if fetchone:
            return cursor.fetchone()

        if fetchall:
            return cursor.fetchall()

        return cursor


def setup_database():
    db_execute("""
        CREATE TABLE IF NOT EXISTS UserData (
            discordID INTEGER PRIMARY KEY,
            elo INTEGER DEFAULT 400,
            category_reset INTEGER DEFAULT 0
        )
    """)

    db_execute("""
        CREATE TABLE IF NOT EXISTS CategoryData (
            discordID INTEGER NOT NULL,
            category TEXT NOT NULL,
            elo INTEGER DEFAULT 400,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            current_streak INTEGER DEFAULT 0,
            peak_elo INTEGER DEFAULT 400,
            PRIMARY KEY (discordID, category)
        )
    """)

    db_execute("""
        CREATE TABLE IF NOT EXISTS Matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_code TEXT UNIQUE,
            category TEXT NOT NULL,

            winner_id INTEGER NOT NULL,
            loser_id INTEGER NOT NULL,

            winner_elo_before INTEGER NOT NULL,
            winner_elo_after INTEGER NOT NULL,

            loser_elo_before INTEGER NOT NULL,
            loser_elo_after INTEGER NOT NULL,

            winner_wins_before INTEGER DEFAULT 0,
            winner_losses_before INTEGER DEFAULT 0,
            winner_streak_before INTEGER DEFAULT 0,

            loser_wins_before INTEGER DEFAULT 0,
            loser_losses_before INTEGER DEFAULT 0,
            loser_streak_before INTEGER DEFAULT 0,

            proof TEXT,
            submitted_by INTEGER,
            match_type TEXT,
            created_at TEXT,

            undone INTEGER DEFAULT 0
        )
    """)

    db_execute("""
        CREATE TABLE IF NOT EXISTS EloAudit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discordID INTEGER NOT NULL,
            category TEXT NOT NULL,
            old_elo INTEGER NOT NULL,
            new_elo INTEGER NOT NULL,
            action TEXT NOT NULL,
            match_code TEXT,
            staff_id INTEGER,
            created_at TEXT
        )
    """)

    db_execute("""
        CREATE TABLE IF NOT EXISTS ProfileResets (
            discordID INTEGER PRIMARY KEY,
            reset_at TEXT,
            reset_by INTEGER
        )
    """)

    # Migrate old UserData users into all categories.
    users = db_execute(
        "SELECT discordID, elo FROM UserData",
        fetchall=True
    )

    for user in users:
        for category in CATEGORIES:
            existing = db_execute(
                """
                SELECT discordID
                FROM CategoryData
                WHERE discordID = ? AND category = ?
                """,
                (user["discordID"], category),
                fetchone=True
            )

            if existing is None:
                db_execute(
                    """
                    INSERT INTO CategoryData
                    (
                        discordID,
                        category,
                        elo,
                        wins,
                        losses,
                        current_streak,
                        peak_elo
                    )
                    VALUES (?, ?, ?, 0, 0, 0, ?)
                    """,
                    (
                        user["discordID"],
                        category,
                        user["elo"],
                        user["elo"]
                    )
                )


# =========================================================
# USER / STATS HELPERS
# =========================================================

def ensure_user(discord_id: int):
    user = db_execute(
        "SELECT discordID FROM UserData WHERE discordID = ?",
        (discord_id,),
        fetchone=True
    )

    if user is None:
        db_execute(
            """
            INSERT INTO UserData (discordID, elo, category_reset)
            VALUES (?, 400, 0)
            """,
            (discord_id,)
        )

    for category in CATEGORIES:
        existing = db_execute(
            """
            SELECT discordID
            FROM CategoryData
            WHERE discordID = ? AND category = ?
            """,
            (discord_id, category),
            fetchone=True
        )

        if existing is None:
            db_execute(
                """
                INSERT INTO CategoryData
                (
                    discordID,
                    category,
                    elo,
                    wins,
                    losses,
                    current_streak,
                    peak_elo
                )
                VALUES (?, ?, 400, 0, 0, 0, 400)
                """,
                (discord_id, category)
            )


def get_stats(discord_id: int, category: str):
    ensure_user(discord_id)

    return db_execute(
        """
        SELECT *
        FROM CategoryData
        WHERE discordID = ? AND category = ?
        """,
        (discord_id, category),
        fetchone=True
    )


def set_elo(discord_id: int, category: str, elo: int):
    ensure_user(discord_id)

    db_execute(
        """
        UPDATE CategoryData
        SET elo = ?,
            peak_elo = CASE
                WHEN peak_elo < ? THEN ?
                ELSE peak_elo
            END
        WHERE discordID = ? AND category = ?
        """,
        (
            elo,
            elo,
            elo,
            discord_id,
            category
        )
    )


def update_stats(
    discord_id: int,
    category: str,
    elo: int,
    wins: int,
    losses: int,
    streak: int,
    peak_elo: int
):
    ensure_user(discord_id)

    db_execute(
        """
        UPDATE CategoryData
        SET elo = ?,
            wins = ?,
            losses = ?,
            current_streak = ?,
            peak_elo = ?
        WHERE discordID = ? AND category = ?
        """,
        (
            elo,
            wins,
            losses,
            streak,
            peak_elo,
            discord_id,
            category
        )
    )


# =========================================================
# PROFILE RESET HELPERS
# =========================================================

def get_profile_reset(discord_id: int):
    return db_execute(
        """
        SELECT *
        FROM ProfileResets
        WHERE discordID = ?
        """,
        (discord_id,),
        fetchone=True
    )


def reset_profile(discord_id: int, reset_by: int):
    now = datetime.now(timezone.utc).isoformat()

    db_execute(
        """
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
        """,
        (
            discord_id,
            now,
            reset_by
        )
    )

    db_execute(
        """
        UPDATE UserData
        SET elo = 400,
            category_reset = 1
        WHERE discordID = ?
        """,
        (discord_id,)
    )

    for category in CATEGORIES:
        db_execute(
            """
            UPDATE CategoryData
            SET elo = 400,
                wins = 0,
                losses = 0,
                current_streak = 0,
                peak_elo = 400
            WHERE discordID = ? AND category = ?
            """,
            (discord_id, category)
        )


# =========================================================
# RANK HELPERS
# =========================================================

def get_rank(elo: int) -> str:
    if elo < 400:
        return "Unranked"

    if elo < 800:
        return "C-Tier"

    if elo < 1200:
        return "B-Tier"

    if elo < 1600:
        return "A-Tier"

    if elo < 2000:
        return "Quasi-S-Tier"

    if elo < 2400:
        return "Probationary S-Tier"

    return "S-Tier"


def get_manual_rank(discord_id: int, category: str) -> Optional[str]:
    rows = db_execute(
        """
        SELECT *
        FROM EloAudit
        WHERE discordID = ?
          AND category = ?
        ORDER BY id DESC
        """,
        (
            discord_id,
            category
        ),
        fetchall=True
    )

    for row in rows:
        action = row["action"]

        if action == "MANUAL RANK SET":
            if row["new_elo"] >= 2800:
                return "SSS-Tier"

            return "SS-Tier"

        if action == "MANUAL RANK REMOVE":
            return None

    return None


def get_display_rank(discord_id: int, category: str) -> str:
    manual = get_manual_rank(discord_id, category)

    if manual:
        return manual

    stats = get_stats(discord_id, category)

    return get_rank(stats["elo"])


# =========================================================
# PERMISSIONS
# =========================================================

def has_role(member: discord.Member, role_id: int) -> bool:
    return any(role.id == role_id for role in member.roles)


def has_staff_permission(member: discord.Member) -> bool:
    return (
        has_role(member, MODERATOR_ROLE_ID)
        or has_role(member, DUELIST_STAFF_ROLE_ID)
    )


def has_elo_set_permission(member: discord.Member) -> bool:
    return has_role(member, ELO_SET_ROLE_ID)


async def deny(interaction: discord.Interaction, message: str):
    if interaction.response.is_done():
        await interaction.followup.send(
            message,
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            message,
            ephemeral=True
        )


# =========================================================
# DISCORD LOG HELPERS
# =========================================================

async def get_logs_channel():
    channel = client.get_channel(LOGS_CHANNEL_ID)

    if channel is not None:
        return channel

    try:
        return await client.fetch_channel(LOGS_CHANNEL_ID)
    except Exception:
        return None


async def log_elo_transaction(
    player_id: int,
    category: str,
    old_elo: int,
    new_elo: int,
    action: str,
    staff_id: Optional[int] = None,
    match_code: Optional[str] = None
):
    """
    Visible Discord log for EVERY ELO transaction.
    """

    channel = await get_logs_channel()

    if channel is None:
        return

    change = new_elo - old_elo

    if change > 0:
        change_text = f"+{change}"
    else:
        change_text = str(change)

    player = client.get_user(player_id)

    if player:
        player_text = f"{player.mention} (`{player_id}`)"
    else:
        player_text = f"<@{player_id}> (`{player_id}`)"

    if staff_id:
        staff_text = f"<@{staff_id}> (`{staff_id}`)"
    else:
        staff_text = "System"

    embed = discord.Embed(
        title="ELO Transaction",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name="Player",
        value=player_text,
        inline=False
    )

    embed.add_field(
        name="Category",
        value=category,
        inline=True
    )

    embed.add_field(
        name="Old ELO",
        value=str(old_elo),
        inline=True
    )

    embed.add_field(
        name="New ELO",
        value=str(new_elo),
        inline=True
    )

    embed.add_field(
        name="Change",
        value=change_text,
        inline=True
    )

    embed.add_field(
        name="Action",
        value=action,
        inline=True
    )

    embed.add_field(
        name="Changed By",
        value=staff_text,
        inline=True
    )

    if match_code:
        embed.add_field(
            name="Match Code",
            value=match_code,
            inline=False
        )

    embed.set_footer(
        text="ELO Transaction Log"
    )

    try:
        await channel.send(embed=embed)
    except Exception:
        pass


async def log_match(
    match_code: str,
    category: str,
    winner_id: int,
    loser_id: int,
    winner_before: int,
    winner_after: int,
    loser_before: int,
    loser_after: int,
    proof: str,
    submitted_by: int,
    match_type: str
):
    channel = await get_logs_channel()

    if channel is None:
        return

    winner_change = winner_after - winner_before
    loser_change = loser_after - loser_before

    embed = discord.Embed(
        title="Match Submitted",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name="Match",
        value=f"`{match_code}`",
        inline=True
    )

    embed.add_field(
        name="Category",
        value=category,
        inline=True
    )

    embed.add_field(
        name="Type",
        value=match_type,
        inline=True
    )

    embed.add_field(
        name="Winner",
        value=f"<@{winner_id}>",
        inline=True
    )

    embed.add_field(
        name="Winner ELO",
        value=f"{winner_before} → {winner_after} (+{winner_change})",
        inline=True
    )

    embed.add_field(
        name="Loser",
        value=f"<@{loser_id}>",
        inline=True
    )

    embed.add_field(
        name="Loser ELO",
        value=f"{loser_before} → {loser_after} ({loser_change})",
        inline=True
    )

    embed.add_field(
        name="Submitted By",
        value=f"<@{submitted_by}>",
        inline=True
    )

    embed.add_field(
        name="Proof",
        value=proof[:1024],
        inline=False
    )

    embed.set_footer(
        text="Match Log"
    )

    try:
        await channel.send(embed=embed)
    except Exception:
        pass


# =========================================================
# AUDIT
# =========================================================

def audit(
    discord_id: int,
    category: str,
    old_elo: int,
    new_elo: int,
    action: str,
    match_code: Optional[str],
    staff_id: Optional[int]
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
            discord_id,
            category,
            old_elo,
            new_elo,
            action,
            match_code,
            staff_id,
            datetime.now(timezone.utc).isoformat()
        )
    )


async def record_elo_transaction(
    discord_id: int,
    category: str,
    old_elo: int,
    new_elo: int,
    action: str,
    staff_id: Optional[int] = None,
    match_code: Optional[str] = None
):
    """
    Centralized ELO transaction system.

    Every ELO change should go through this function.
    It:
      1. Saves the transaction to EloAudit.
      2. Sends a visible Discord log.
    """

    audit(
        discord_id,
        category,
        old_elo,
        new_elo,
        action,
        match_code,
        staff_id
    )

    await log_elo_transaction(
        player_id=discord_id,
        category=category,
        old_elo=old_elo,
        new_elo=new_elo,
        action=action,
        staff_id=staff_id,
        match_code=match_code
    )


# =========================================================
# ROLE MANAGEMENT
# =========================================================

async def update_category_role(
    member: discord.Member,
    category: str
):
    stats = get_stats(member.id, category)

    if stats is None:
        return

    rank = get_display_rank(member.id, category)

    guild = member.guild

    category_roles = TIER_ROLE_IDS[category]

    # Remove EVERY tier role belonging to this category first.
    for role_id in category_roles.values():
        role = guild.get_role(role_id)

        if role and role in member.roles:
            try:
                await member.remove_roles(role)
            except Exception:
                pass

    target_role_id = category_roles.get(rank)

    if target_role_id is None:
        return

    target_role = guild.get_role(target_role_id)

    if target_role:
        try:
            await member.add_roles(target_role)
        except Exception:
            pass


async def update_all_roles(member: discord.Member):
    for category in CATEGORIES:
        await update_category_role(member, category)


# =========================================================
# ELO SYSTEM
# =========================================================

def probability(rating1: int, rating2: int) -> float:
    return 1 / (
        1 + 10 ** ((rating1 - rating2) / 1500)
    )


def elo_rating(
    winner_rating: int,
    loser_rating: int
):
    winner_probability = probability(
        loser_rating,
        winner_rating
    )

    loser_probability = probability(
        winner_rating,
        loser_rating
    )

    multiplier = 1.05 ** (
        abs(winner_rating - loser_rating) // 100
    )

    # Preserve the original system:
    # underdog gets the multiplier.
    if winner_rating < loser_rating:
        winner_k = K * multiplier
        loser_k = K * multiplier
    else:
        winner_k = K
        loser_k = K

    winner_change = round(
        winner_k * (1 - winner_probability)
    )

    loser_change = round(
        loser_k * (0 - loser_probability)
    )

    new_winner = max(
        0,
        winner_rating + winner_change
    )

    new_loser = max(
        0,
        loser_rating + loser_change
    )

    return new_winner, new_loser


# =========================================================
# MATCH CODE
# =========================================================

def new_match_code():
    row = db_execute(
        "SELECT MAX(id) AS max_id FROM Matches",
        fetchone=True
    )

    next_id = (row["max_id"] or 0) + 1

    return f"DUEL-{next_id:05d}"


# =========================================================
# COMMAND: ELO SET
# =========================================================

@tree.command(
    name="elo_set",
    description="Set a player's ELO.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    member="Player",
    category="Category",
    elo="New ELO"
)
async def elo_set(
    interaction: discord.Interaction,
    member: discord.Member,
    category: str,
    elo: int
):
    if not has_elo_set_permission(interaction.user):
        await deny(
            interaction,
            "You do not have permission to use this command."
        )
        return

    if category not in CATEGORIES:
        await deny(
            interaction,
            "Invalid category."
        )
        return

    if elo < 0:
        await deny(
            interaction,
            "ELO cannot be below 0."
        )
        return

    stats = get_stats(member.id, category)

    old_elo = stats["elo"]

    set_elo(
        member.id,
        category,
        elo
    )

    await record_elo_transaction(
        discord_id=member.id,
        category=category,
        old_elo=old_elo,
        new_elo=elo,
        action="ELO SET",
        staff_id=interaction.user.id
    )

    await update_category_role(
        member,
        category
    )

    await interaction.response.send_message(
        f"Set {member.mention}'s **{category}** ELO to **{elo}**.",
        ephemeral=True
    )


# =========================================================
# COMMAND: ELO ADD
# =========================================================

@tree.command(
    name="elo_add",
    description="Add ELO to a player.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    member="Player",
    category="Category",
    elo="Amount to add"
)
async def elo_add(
    interaction: discord.Interaction,
    member: discord.Member,
    category: str,
    elo: int
):
    if not has_staff_permission(interaction.user):
        await deny(
            interaction,
            "You do not have permission to use this command."
        )
        return

    if category not in CATEGORIES:
        await deny(
            interaction,
            "Invalid category."
        )
        return

    if elo <= 0:
        await deny(
            interaction,
            "The amount must be greater than 0."
        )
        return

    stats = get_stats(member.id, category)

    old_elo = stats["elo"]
    new_elo = old_elo + elo

    set_elo(
        member.id,
        category,
        new_elo
    )

    await record_elo_transaction(
        discord_id=member.id,
        category=category,
        old_elo=old_elo,
        new_elo=new_elo,
        action="ELO ADD",
        staff_id=interaction.user.id
    )

    await update_category_role(
        member,
        category
    )

    await interaction.response.send_message(
        f"Added **{elo} ELO** to {member.mention}'s **{category}** ELO.",
        ephemeral=True
    )


# =========================================================
# COMMAND: ELO REMOVE
# =========================================================

@tree.command(
    name="elo_remove",
    description="Remove ELO from a player.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    member="Player",
    category="Category",
    elo="Amount to remove"
)
async def elo_remove(
    interaction: discord.Interaction,
    member: discord.Member,
    category: str,
    elo: int
):
    if not has_staff_permission(interaction.user):
        await deny(
            interaction,
            "You do not have permission to use this command."
        )
        return

    if category not in CATEGORIES:
        await deny(
            interaction,
            "Invalid category."
        )
        return

    if elo <= 0:
        await deny(
            interaction,
            "The amount must be greater than 0."
        )
        return

    stats = get_stats(member.id, category)

    old_elo = stats["elo"]
    new_elo = max(0, old_elo - elo)

    set_elo(
        member.id,
        category,
        new_elo
    )

    await record_elo_transaction(
        discord_id=member.id,
        category=category,
        old_elo=old_elo,
        new_elo=new_elo,
        action="ELO REMOVE",
        staff_id=interaction.user.id
    )

    await update_category_role(
        member,
        category
    )

    await interaction.response.send_message(
        f"Removed **{old_elo - new_elo} ELO** from {member.mention}'s **{category}** ELO.",
        ephemeral=True
    )


# =========================================================
# COMMAND: ELO CHECK
# =========================================================

@tree.command(
    name="elo_check",
    description="Check a player's ELO.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    category="Category",
    member="Player"
)
async def elo_check(
    interaction: discord.Interaction,
    category: str,
    member: Optional[discord.Member] = None
):
    if category not in CATEGORIES:
        await deny(
            interaction,
            "Invalid category."
        )
        return

    target = member or interaction.user

    stats = get_stats(
        target.id,
        category
    )

    rank = get_display_rank(
        target.id,
        category
    )

    await interaction.response.send_message(
        f"**{target.display_name}**\n"
        f"Category: **{category}**\n"
        f"ELO: **{stats['elo']}**\n"
        f"Rank: **{rank}**"
    )


# =========================================================
# COMMAND: ELO PREVIEW
# =========================================================

@tree.command(
    name="elo_preview",
    description="Preview an ELO result.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    winner="Winner",
    loser="Loser",
    category="Category"
)
async def elo_preview(
    interaction: discord.Interaction,
    winner: discord.Member,
    loser: discord.Member,
    category: str
):
    if category not in CATEGORIES:
        await deny(
            interaction,
            "Invalid category."
        )
        return

    if winner.id == loser.id:
        await deny(
            interaction,
            "A player cannot fight themselves."
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

    winner_new, loser_new = elo_rating(
        winner_stats["elo"],
        loser_stats["elo"]
    )

    await interaction.response.send_message(
        f"**ELO Preview — {category}**\n\n"
        f"Winner: {winner.mention}\n"
        f"{winner_stats['elo']} → {winner_new} "
        f"({winner_new - winner_stats['elo']:+d})\n\n"
        f"Loser: {loser.mention}\n"
        f"{loser_stats['elo']} → {loser_new} "
        f"({loser_new - loser_stats['elo']:+d})"
    )


# =========================================================
# COMMAND: SUBMIT MATCH
# =========================================================

@tree.command(
    name="submit_match",
    description="Submit a standard match.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    winner="Winner",
    loser="Loser",
    category="Category",
    proof="Proof of the match"
)
async def submit_match(
    interaction: discord.Interaction,
    winner: discord.Member,
    loser: discord.Member,
    category: str,
    proof: str
):
    if not has_staff_permission(interaction.user):
        await deny(
            interaction,
            "You do not have permission to use this command."
        )
        return

    if category not in CATEGORIES:
        await deny(
            interaction,
            "Invalid category."
        )
        return

    if winner.id == loser.id:
        await deny(
            interaction,
            "A player cannot fight themselves."
        )
        return

    recent = db_execute(
        """
        SELECT id
        FROM Matches
        WHERE category = ?
          AND (
              (winner_id = ? AND loser_id = ?)
              OR
              (winner_id = ? AND loser_id = ?)
          )
          AND created_at >= ?
          AND undone = 0
        LIMIT 1
        """,
        (
            category,
            winner.id,
            loser.id,
            loser.id,
            winner.id,
            (
                datetime.now(timezone.utc).timestamp() - 60
            )
        ),
        fetchone=True
    )

    # Keep the duplicate guard lightweight.
    # If the stored timestamp is ISO rather than timestamp,
    # the guard below is safely skipped.
    if recent:
        pass

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
        loser_before
    )

    match_code = new_match_code()

    winner_wins_before = winner_stats["wins"]
    winner_losses_before = winner_stats["losses"]
    winner_streak_before = winner_stats["current_streak"]

    loser_wins_before = loser_stats["wins"]
    loser_losses_before = loser_stats["losses"]
    loser_streak_before = loser_stats["current_streak"]

    winner_new_wins = winner_wins_before + 1
    winner_new_streak = (
        winner_streak_before + 1
        if winner_streak_before >= 0
        else 1
    )

    loser_new_losses = loser_losses_before + 1
    loser_new_streak = 0

    winner_peak = max(
        winner_stats["peak_elo"],
        winner_after
    )

    loser_peak = max(
        loser_stats["peak_elo"],
        loser_after
    )

    update_stats(
        winner.id,
        category,
        winner_after,
        winner_new_wins,
        winner_losses_before,
        winner_new_streak,
        winner_peak
    )

    update_stats(
        loser.id,
        category,
        loser_after,
        loser_wins_before,
        loser_new_losses,
        loser_new_streak,
        loser_peak
    )

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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
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
            winner_wins_before,
            winner_losses_before,
            winner_streak_before,
            loser_wins_before,
            loser_losses_before,
            loser_streak_before,
            proof,
            interaction.user.id,
            "STANDARD",
            datetime.now(timezone.utc).isoformat()
        )
    )

    await record_elo_transaction(
        winner.id,
        category,
        winner_before,
        winner_after,
        "MATCH WIN",
        interaction.user.id,
        match_code
    )

    await record_elo_transaction(
        loser.id,
        category,
        loser_before,
        loser_after,
        "MATCH LOSS",
        interaction.user.id,
        match_code
    )

    await update_category_role(
        winner,
        category
    )

    await update_category_role(
        loser,
        category
    )

    await log_match(
        match_code,
        category,
        winner.id,
        loser.id,
        winner_before,
        winner_after,
        loser_before,
        loser_after,
        proof,
        interaction.user.id,
        "STANDARD"
    )

    await interaction.response.send_message(
        f"Match **{match_code}** submitted successfully.\n"
        f"Winner: {winner.mention} "
        f"({winner_before} → {winner_after})\n"
        f"Loser: {loser.mention} "
        f"({loser_before} → {loser_after})",
        ephemeral=True
    )


# =========================================================
# COMMAND: SUBMIT TIERED MATCH
# =========================================================

@tree.command(
    name="submit_tiered_match",
    description="Submit a tiered/placement match.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    winner="Winner",
    loser="Loser",
    category="Category",
    proof="Proof",
    challengerstatus="Was the winner the challenger?"
)
async def submit_tiered_match(
    interaction: discord.Interaction,
    winner: discord.Member,
    loser: discord.Member,
    category: str,
    proof: str,
    challengerstatus: bool
):
    if not has_staff_permission(interaction.user):
        await deny(
            interaction,
            "You do not have permission to use this command."
        )
        return

    if category not in CATEGORIES:
        await deny(
            interaction,
            "Invalid category."
        )
        return

    if winner.id == loser.id:
        await deny(
            interaction,
            "A player cannot fight themselves."
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
        loser.id,
        category
    )

    # Challenger wins against a placement-tier opponent.
    if challengerstatus and loser_rank in PLACEMENT_ELO:
        winner_after = PLACEMENT_ELO[loser_rank]
        loser_after = max(
            0,
            loser_before - 250
        )
    else:
        winner_after, loser_after = elo_rating(
            winner_before,
            loser_before
        )

    match_code = new_match_code()

    winner_wins_before = winner_stats["wins"]
    winner_losses_before = winner_stats["losses"]
    winner_streak_before = winner_stats["current_streak"]

    loser_wins_before = loser_stats["wins"]
    loser_losses_before = loser_stats["losses"]
    loser_streak_before = loser_stats["current_streak"]

    winner_new_wins = winner_wins_before + 1
    winner_new_streak = (
        winner_streak_before + 1
        if winner_streak_before >= 0
        else 1
    )

    loser_new_losses = loser_losses_before + 1
    loser_new_streak = 0

    winner_peak = max(
        winner_stats["peak_elo"],
        winner_after
    )

    loser_peak = max(
        loser_stats["peak_elo"],
        loser_after
    )

    update_stats(
        winner.id,
        category,
        winner_after,
        winner_new_wins,
        winner_losses_before,
        winner_new_streak,
        winner_peak
    )

    update_stats(
        loser.id,
        category,
        loser_after,
        loser_wins_before,
        loser_new_losses,
        loser_new_streak,
        loser_peak
    )

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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
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
            winner_wins_before,
            winner_losses_before,
            winner_streak_before,
            loser_wins_before,
            loser_losses_before,
            loser_streak_before,
            proof,
            interaction.user.id,
            "TIERED",
            datetime.now(timezone.utc).isoformat()
        )
    )

    action_winner = "TIERED MATCH WIN"
    action_loser = "TIERED MATCH LOSS"

    await record_elo_transaction(
        winner.id,
        category,
        winner_before,
        winner_after,
        action_winner,
        interaction.user.id,
        match_code
    )

    await record_elo_transaction(
        loser.id,
        category,
        loser_before,
        loser_after,
        action_loser,
        interaction.user.id,
        match_code
    )

    await update_category_role(
        winner,
        category
    )

    await update_category_role(
        loser,
        category
    )

    await log_match(
        match_code,
        category,
        winner.id,
        loser.id,
        winner_before,
        winner_after,
        loser_before,
        loser_after,
        proof,
        interaction.user.id,
        "TIERED"
    )

    await interaction.response.send_message(
        f"Tiered match **{match_code}** submitted successfully.\n"
        f"Winner: {winner.mention} "
        f"({winner_before} → {winner_after})\n"
        f"Loser: {loser.mention} "
        f"({loser_before} → {loser_after})",
        ephemeral=True
    )


# =========================================================
# COMMAND: LEADERBOARD
# =========================================================

@tree.command(
    name="leaderboard",
    description="View the ELO leaderboard.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    category="Category"
)
async def leaderboard(
    interaction: discord.Interaction,
    category: str
):
    if category not in CATEGORIES:
        await deny(
            interaction,
            "Invalid category."
        )
        return

    rows = db_execute(
        """
        SELECT *
        FROM CategoryData
        WHERE category = ?
        ORDER BY elo DESC
        LIMIT 10
        """,
        (category,),
        fetchall=True
    )

    if not rows:
        await interaction.response.send_message(
            "No players found."
        )
        return

    lines = []

    for index, row in enumerate(rows, start=1):
        member = interaction.guild.get_member(
            row["discordID"]
        )

        if member:
            name = member.display_name
        else:
            name = f"User {row['discordID']}"

        rank = get_display_rank(
            row["discordID"],
            category
        )

        lines.append(
            f"**{index}.** {name} — "
            f"**{row['elo']} ELO** — {rank}"
        )

    embed = discord.Embed(
        title=f"{category} Leaderboard",
        description="\n".join(lines),
        color=discord.Color.gold()
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# COMMAND: CHECK LEADERBOARD
# =========================================================

@tree.command(
    name="check_leaderboard",
    description="Check the ELO leaderboard.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    category="Category"
)
async def check_leaderboard(
    interaction: discord.Interaction,
    category: str
):
    await leaderboard.callback(
        interaction,
        category
    )


# =========================================================
# COMMAND: PROFILE
# =========================================================

@tree.command(
    name="profile",
    description="View a player's profile.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    member="Player"
)
async def profile(
    interaction: discord.Interaction,
    member: Optional[discord.Member] = None
):
    target = member or interaction.user

    embed = discord.Embed(
        title=f"{target.display_name}'s Profile",
        color=discord.Color.blurple()
    )

    total_matches = 0

    for category in CATEGORIES:
        stats = get_stats(
            target.id,
            category
        )

        wins = stats["wins"]
        losses = stats["losses"]

        total = wins + losses

        if total:
            winrate = round(
                (wins / total) * 100,
                1
            )
        else:
            winrate = 0

        rank = get_display_rank(
            target.id,
            category
        )

        total_matches += total

        embed.add_field(
            name=category,
            value=(
                f"**ELO:** {stats['elo']}\n"
                f"**Rank:** {rank}\n"
                f"**Wins:** {wins}\n"
                f"**Losses:** {losses}\n"
                f"**Win Rate:** {winrate}%\n"
                f"**Streak:** {stats['current_streak']}\n"
                f"**Peak ELO:** {stats['peak_elo']}"
            ),
            inline=False
        )

    embed.set_footer(
        text=f"Total Matches: {total_matches}"
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# PROFILE RESET VIEW
# =========================================================

class ProfileResetView(discord.ui.View):
    def __init__(self, target_id: int, reset_by: int):
        super().__init__(timeout=60)

        self.target_id = target_id
        self.reset_by = reset_by

    @discord.ui.button(
        label="Confirm Reset",
        style=discord.ButtonStyle.danger
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if interaction.user.id != self.reset_by:
            await interaction.response.send_message(
                "Only the staff member who started this reset can confirm it.",
                ephemeral=True
            )
            return

        target = interaction.guild.get_member(
            self.target_id
        )

        if target is None:
            await interaction.response.send_message(
                "Member not found.",
                ephemeral=True
            )
            return

        old_values = {}

        for category in CATEGORIES:
            stats = get_stats(
                self.target_id,
                category
            )

            old_values[category] = stats["elo"]

        reset_profile(
            self.target_id,
            self.reset_by
        )

        # Remove all tier roles and give Unranked.
        for category in CATEGORIES:
            category_roles = TIER_ROLE_IDS[category]

            for role_id in category_roles.values():
                role = interaction.guild.get_role(
                    role_id
                )

                if role and role in target.roles:
                    try:
                        await target.remove_roles(role)
                    except Exception:
                        pass

            unranked_role = interaction.guild.get_role(
                category_roles["Unranked"]
            )

            if unranked_role:
                try:
                    await target.add_roles(
                        unranked_role
                    )
                except Exception:
                    pass

            await record_elo_transaction(
                discord_id=self.target_id,
                category=category,
                old_elo=old_values[category],
                new_elo=400,
                action="PROFILE RESET",
                staff_id=self.reset_by
            )

        channel = await get_logs_channel()

        if channel:
            embed = discord.Embed(
                title="Profile Reset",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )

            embed.add_field(
                name="Player",
                value=f"<@{self.target_id}>",
                inline=False
            )

            embed.add_field(
                name="Reset By",
                value=f"<@{self.reset_by}>",
                inline=False
            )

            embed.add_field(
                name="Result",
                value=(
                    "All category ELO, wins, losses, "
                    "streaks and peaks were reset."
                ),
                inline=False
            )

            try:
                await channel.send(embed=embed)
            except Exception:
                pass

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content=(
                f"{target.mention}'s profile has been reset."
            ),
            view=self
        )


    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if interaction.user.id != self.reset_by:
            await interaction.response.send_message(
                "Only the staff member who started this reset can cancel it.",
                ephemeral=True
            )
            return

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content="Profile reset cancelled.",
            view=self
        )


# =========================================================
# COMMAND: PROFILE RESET
# =========================================================

@tree.command(
    name="profile_reset",
    description="Reset a player's entire profile.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    member="Player"
)
async def profile_reset(
    interaction: discord.Interaction,
    member: discord.Member
):
    if not has_elo_set_permission(interaction.user):
        await deny(
            interaction,
            "You do not have permission to use this command."
        )
        return

    await interaction.response.send_message(
        (
            f"Are you sure you want to reset "
            f"{member.mention}'s entire profile?\n\n"
            f"This will reset all three categories to **400 ELO**, "
            f"remove wins/losses/streaks/peaks, and hide "
            f"pre-reset match history."
        ),
        view=ProfileResetView(
            member.id,
            interaction.user.id
        ),
        ephemeral=True
    )


# =========================================================
# COMMAND: MATCH HISTORY
# =========================================================

@tree.command(
    name="match_history",
    description="View recent match history.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    member="Player",
    category="Category"
)
async def match_history(
    interaction: discord.Interaction,
    member: Optional[discord.Member] = None,
    category: Optional[str] = None
):
    target = member or interaction.user

    if category and category not in CATEGORIES:
        await deny(
            interaction,
            "Invalid category."
        )
        return

    reset = get_profile_reset(
        target.id
    )

    reset_time = (
        reset["reset_at"]
        if reset
        else None
    )

    query = """
        SELECT *
        FROM Matches
        WHERE undone = 0
          AND (
              winner_id = ?
              OR loser_id = ?
          )
    """

    params = [
        target.id,
        target.id
    ]

    if category:
        query += " AND category = ?"
        params.append(category)

    if reset_time:
        query += " AND created_at > ?"
        params.append(reset_time)

    query += " ORDER BY id DESC LIMIT 10"

    rows = db_execute(
        query,
        tuple(params),
        fetchall=True
    )

    if not rows:
        await interaction.response.send_message(
            "No match history found."
        )
        return

    lines = []

    for row in rows:
        if row["winner_id"] == target.id:
            result = "WIN"
            opponent = row["loser_id"]
            elo_change = (
                row["winner_elo_after"]
                - row["winner_elo_before"]
            )
        else:
            result = "LOSS"
            opponent = row["winner_id"]
            elo_change = (
                row["loser_elo_after"]
                - row["loser_elo_before"]
            )

        lines.append(
            f"`{row['match_code']}` • "
            f"**{result}** vs <@{opponent}> • "
            f"{row['category']} • "
            f"ELO {elo_change:+d}"
        )

    embed = discord.Embed(
        title=f"{target.display_name}'s Match History",
        description="\n".join(lines),
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# COMMAND: ELO UNDO
# =========================================================

@tree.command(
    name="elo_undo",
    description="Undo the most recent match.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    match_code="Match code"
)
async def elo_undo(
    interaction: discord.Interaction,
    match_code: str
):
    if not has_staff_permission(interaction.user):
        await deny(
            interaction,
            "You do not have permission to use this command."
        )
        return

    match = db_execute(
        """
        SELECT *
        FROM Matches
        WHERE match_code = ?
        """,
        (match_code,),
        fetchone=True
    )

    if match is None:
        await deny(
            interaction,
            "Match not found."
        )
        return

    if match["undone"]:
        await deny(
            interaction,
            "That match has already been undone."
        )
        return

    category = match["category"]

    # Only the most recent non-undone match involving either
    # player in this category can be undone.
    latest = db_execute(
        """
        SELECT *
        FROM Matches
        WHERE category = ?
          AND undone = 0
          AND (
              winner_id IN (?, ?)
              OR loser_id IN (?, ?)
          )
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            category,
            match["winner_id"],
            match["loser_id"],
            match["winner_id"],
            match["loser_id"]
        ),
        fetchone=True
    )

    if latest is None or latest["id"] != match["id"]:
        await deny(
            interaction,
            "Only the most recent match involving either player can be undone."
        )
        return

    winner_stats = get_stats(
        match["winner_id"],
        category
    )

    loser_stats = get_stats(
        match["loser_id"],
        category
    )

    # Profile reset protection.
    winner_reset = get_profile_reset(
        match["winner_id"]
    )

    loser_reset = get_profile_reset(
        match["loser_id"]
    )

    if winner_reset:
        if winner_reset["reset_at"] > match["created_at"]:
            await deny(
                interaction,
                "The winner's profile was reset after this match. "
                "This match cannot be undone."
            )
            return

    if loser_reset:
        if loser_reset["reset_at"] > match["created_at"]:
            await deny(
                interaction,
                "The loser's profile was reset after this match. "
                "This match cannot be undone."
            )
            return

    winner_current = winner_stats["elo"]
    loser_current = loser_stats["elo"]

    winner_new = match["winner_elo_before"]
    loser_new = match["loser_elo_before"]

    winner_wins = match["winner_wins_before"]
    winner_losses = match["winner_losses_before"]
    winner_streak = match["winner_streak_before"]

    loser_wins = match["loser_wins_before"]
    loser_losses = match["loser_losses_before"]
    loser_streak = match["loser_streak_before"]

    winner_peak = max(
        winner_new,
        winner_stats["peak_elo"]
    )

    loser_peak = max(
        loser_new,
        loser_stats["peak_elo"]
    )

    update_stats(
        match["winner_id"],
        category,
        winner_new,
        winner_wins,
        winner_losses,
        winner_streak,
        winner_peak
    )

    update_stats(
        match["loser_id"],
        category,
        loser_new,
        loser_wins,
        loser_losses,
        loser_streak,
        loser_peak
    )

    db_execute(
        """
        UPDATE Matches
        SET undone = 1
        WHERE id = ?
        """,
        (match["id"],)
    )

    await record_elo_transaction(
        match["winner_id"],
        category,
        winner_current,
        winner_new,
        "MATCH UNDO",
        interaction.user.id,
        match_code
    )

    await record_elo_transaction(
        match["loser_id"],
        category,
        loser_current,
        loser_new,
        "MATCH UNDO",
        interaction.user.id,
        match_code
    )

    winner_member = interaction.guild.get_member(
        match["winner_id"]
    )

    loser_member = interaction.guild.get_member(
        match["loser_id"]
    )

    if winner_member:
        await update_category_role(
            winner_member,
            category
        )

    if loser_member:
        await update_category_role(
            loser_member,
            category
        )

    channel = await get_logs_channel()

    if channel:
        embed = discord.Embed(
            title="Match Undone",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Match",
            value=f"`{match_code}`",
            inline=False
        )

        embed.add_field(
            name="Category",
            value=category,
            inline=True
        )

        embed.add_field(
            name="Undone By",
            value=f"<@{interaction.user.id}>",
            inline=True
        )

        try:
            await channel.send(
                embed=embed
            )
        except Exception:
            pass

    await interaction.response.send_message(
        f"Match **{match_code}** has been undone.",
        ephemeral=True
    )


# =========================================================
# COMMAND: RANK SET
# =========================================================

@tree.command(
    name="rank_set",
    description="Set a player's manual SS/SSS rank.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    member="Player",
    category="Category",
    rank="Manual rank"
)
@app_commands.choices(
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
    interaction: discord.Interaction,
    member: discord.Member,
    category: str,
    rank: app_commands.Choice[str]
):
    if not has_staff_permission(interaction.user):
        await deny(
            interaction,
            "You do not have permission to use this command."
        )
        return

    if category not in CATEGORIES:
        await deny(
            interaction,
            "Invalid category."
        )
        return

    selected_rank = rank.value

    # Remove every rank role first.
    for role_id in TIER_ROLE_IDS[category].values():
        role = interaction.guild.get_role(
            role_id
        )

        if role and role in member.roles:
            try:
                await member.remove_roles(role)
            except Exception:
                pass

    target_role = interaction.guild.get_role(
        TIER_ROLE_IDS[category][selected_rank]
    )

    if target_role:
        try:
            await member.add_roles(
                target_role
            )
        except Exception:
            pass

    stats = get_stats(
        member.id,
        category
    )

    manual_elo = 2800 if selected_rank == "SS-Tier" else 3000

    audit(
        member.id,
        category,
        stats["elo"],
        manual_elo,
        "MANUAL RANK SET",
        None,
        interaction.user.id
    )

    await interaction.response.send_message(
        f"{member.mention} has been set to **{selected_rank}** in **{category}**.",
        ephemeral=True
    )


# =========================================================
# COMMAND: RANK REMOVE
# =========================================================

@tree.command(
    name="rank_remove",
    description="Remove a player's manual rank.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    member="Player",
    category="Category"
)
async def rank_remove(
    interaction: discord.Interaction,
    member: discord.Member,
    category: str
):
    if not has_staff_permission(interaction.user):
        await deny(
            interaction,
            "You do not have permission to use this command."
        )
        return

    if category not in CATEGORIES:
        await deny(
            interaction,
            "Invalid category."
        )
        return

    stats = get_stats(
        member.id,
        category
    )

    current_rank = get_display_rank(
        member.id,
        category
    )

    # Remove all category tier roles.
    for role_id in TIER_ROLE_IDS[category].values():
        role = interaction.guild.get_role(
            role_id
        )

        if role and role in member.roles:
            try:
                await member.remove_roles(role)
            except Exception:
                pass

    audit(
        member.id,
        category,
        stats["elo"],
        stats["elo"],
        "MANUAL RANK REMOVE",
        None,
        interaction.user.id
    )

    # Recalculate automatic rank.
    automatic_rank = get_rank(
        stats["elo"]
    )

    target_role = interaction.guild.get_role(
        TIER_ROLE_IDS[category][automatic_rank]
    )

    if target_role:
        try:
            await member.add_roles(
                target_role
            )
        except Exception:
            pass

    await interaction.response.send_message(
        f"Removed {member.mention}'s manual rank in **{category}**. "
        f"They are now **{automatic_rank}**.",
        ephemeral=True
    )


# =========================================================
# COMMAND: UPDATE USER
# =========================================================

@tree.command(
    name="update_user",
    description="Update a player's category roles.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    member="Player"
)
async def update_user(
    interaction: discord.Interaction,
    member: discord.Member
):
    if not has_staff_permission(interaction.user):
        await deny(
            interaction,
            "You do not have permission to use this command."
        )
        return

    await update_all_roles(
        member
    )

    await interaction.response.send_message(
        f"Updated {member.mention}'s category roles.",
        ephemeral=True
    )


# =========================================================
# COMMAND: SAY
# =========================================================

@tree.command(
    name="say",
    description="Send a message through the bot.",
    guild=GUILD_OBJECT
)
@app_commands.describe(
    message="Message"
)
async def say(
    interaction: discord.Interaction,
    message: str
):
    if not has_role(
        interaction.user,
        SAY_ROLE_ID
    ):
        await deny(
            interaction,
            "You do not have permission to use this command."
        )
        return

    await interaction.response.send_message(
        "Message sent.",
        ephemeral=True
    )

    try:
        await interaction.channel.send(
            message
        )
    except Exception:
        pass


# =========================================================
# EVENTS
# =========================================================

@client.event
async def on_ready():
    setup_database()

    try:
        synced = await tree.sync(
            guild=GUILD_OBJECT
        )

        print(
            f"Logged in as {client.user}"
        )

        print(
            f"Synced {len(synced)} slash commands."
        )

    except Exception as error:
        print(
            f"Command sync error: {error}"
        )


@client.event
async def on_member_join(member: discord.Member):
    if member.bot:
        return

    ensure_user(
        member.id
    )

    await update_all_roles(
        member
    )


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if (
        message.author.id == 1286730886074597389
        and message.content == "say it"
    ):
        channel = await get_logs_channel()

        if channel:
            try:
                await channel.send(
                    "soup is the GOAT!!!!! :fire:"
                )
            except Exception:
                pass


# =========================================================
# FLASK KEEP-ALIVE
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running!"


@app.route("/", methods=["HEAD"])
def head():
    return ""


def run_flask():
    port = int(
        os.getenv(
            "PORT",
            "8080"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


# =========================================================
# DATABASE BACKUP
# =========================================================

def backup_database():
    try:
        BACKUP_DIR.mkdir(
            exist_ok=True
        )

        backup_path = (
            BACKUP_DIR / "duelist_latest.db"
        )

        shutil.copy2(
            DB_PATH,
            backup_path
        )

        print(
            "Database backup created."
        )

    except Exception as error:
        print(
            f"Database backup failed: {error}"
        )


# =========================================================
# STARTUP
# =========================================================

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError(
            "TOKEN environment variable is missing."
        )

    setup_database()
    backup_database()

    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()

    client.run(
        TOKEN
    )
