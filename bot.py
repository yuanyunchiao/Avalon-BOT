import os
import discord
import random
import asyncio
from discord.ext import commands
from discord import app_commands
from aiohttp import web

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree  # 用於斜線指令
print("DEBUG TOKEN:", TOKEN)

# ----------- Avalon Roles -----------
DEFAULT_ROLES = {
    "good": ["梅林", "派西維爾"],
    "evil": ["莫甘娜", "刺客", "莫德雷德", "奧伯倫"],
    "others": ["忠臣", "爪牙"]
}

# ----------- 遊戲狀態 -----------
games = {}  # { guild_id: {player_id: role} }
games_members = {}  # { guild_id: {player_id: Member} }
mission_votes = {}  # { guild_id: {player_id: '成功'/'失敗'} }
custom_role_pool = {}  # { guild_id: [roles...] }
server_locks = {}  # { guild_id: {"deal": False, "vision": False} }

# ----------- Bot Events -----------
@bot.event
async def on_ready():
    await tree.sync()  # 同步斜線指令
    print(f"✅ 已登入 {bot.user}，斜線指令已同步")

# ----------- 自訂角色池 -----------
@tree.command(name="setroles", description="設定本局自訂角色池")
@app_commands.describe(roles="輸入要使用的角色名稱，以空格分隔")
async def setroles(interaction: discord.Interaction, roles: str):
    roles_list = roles.split()
    if not roles_list:
        await interaction.response.send_message("⚠️ 請輸入至少一個角色名稱", ephemeral=True)
        return
    valid_roles = DEFAULT_ROLES["good"] + DEFAULT_ROLES["evil"] + DEFAULT_ROLES["others"]
    for r in roles_list:
        if r not in valid_roles:
            await interaction.response.send_message(f"⚠️ 角色 {r} 不合法", ephemeral=True)
            return
    custom_role_pool[interaction.guild.id] = list(roles_list)
    await interaction.response.send_message(f"✅ 本局自訂角色池已設定：{', '.join(roles_list)}")

# ----------- 發牌 -----------
@tree.command(name="deal", description="發牌，私訊給玩家")
@app_commands.describe(players="標註玩家，例如 @玩家1 @玩家2")
async def deal(interaction: discord.Interaction, players: str):
    guild_id = interaction.guild.id
    lock = server_locks.setdefault(guild_id, {"deal": False, "vision": False})
    if lock["deal"]:
        await interaction.response.send_message("⚠️ 發牌中，請稍等", ephemeral=True)
        return
    lock["deal"] = True

    # 解析 @玩家，Discord會把輸入轉成 Member 物件，如果是純文字，嘗試從 mentions 裡找
    player_list = interaction.user.mentionable_mentions if hasattr(interaction, 'mentionable_mentions') else []
    if not player_list:  # fallback
        player_list = [m for m in interaction.guild.members if str(m) in players]

    if len(player_list) < 5:
        await interaction.response.send_message("玩家不足（至少 5 人）", ephemeral=True)
        lock["deal"] = False
        return

    if guild_id not in custom_role_pool or not custom_role_pool[guild_id]:
        await interaction.response.send_message("⚠️ 尚未設定自訂角色池，請使用 /setroles 設定", ephemeral=True)
        lock["deal"] = False
        return

    roles_pool = custom_role_pool[guild_id].copy()

    # 補齊人數
    needed = len(player_list) - len(roles_pool)
    good_count = sum(1 for r in roles_pool if r in DEFAULT_ROLES["good"])
    evil_count = sum(1 for r in roles_pool if r in DEFAULT_ROLES["evil"])
    for _ in range(needed):
        if good_count <= evil_count:
            roles_pool.append("忠臣")
            good_count += 1
        else:
            roles_pool.append("爪牙")
            evil_count += 1

    random.shuffle(roles_pool)
    assignment = {}
    members_map = {}
    for p in player_list:
        role = roles_pool.pop()
        assignment[p.id] = role
        members_map[p.id] = p
        try:
            await p.send(f"🎭 你的身份是：**{role}**")
        except:
            await interaction.followup.send(f"無法私訊 {p.mention}", ephemeral=True)

    games[guild_id] = assignment
    games_members[guild_id] = members_map
    await interaction.response.send_message("✅ 已經發牌完成！")
    lock["deal"] = False

# ----------- 特殊視野 -----------
@tree.command(name="vision", description="發送特殊視野訊息給玩家")
async def vision(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in games or guild_id not in games_members:
        await interaction.response.send_message("⚠️ 尚未開始遊戲或缺少會員資料", ephemeral=True)
        return

    assignment = games[guild_id]
    members = games_members[guild_id]

    evil_team = [pid for pid, r in assignment.items() if r in ["莫甘娜", "刺客", "爪牙"]]
    modred = [pid for pid, r in assignment.items() if r == "莫德雷德"]
    oberon = [pid for pid, r in assignment.items() if r == "奧伯倫"]
    merlin = [pid for pid, r in assignment.items() if r == "梅林"]
    percival = [pid for pid, r in assignment.items() if r == "派西維爾"]

    for pid in merlin:
        user = members.get(pid)
        if user:
            names = [members[e].display_name for e in evil_team if e not in modred] + \
                    [members[o].display_name for o in oberon]
            await user.send(f"👀 你知道壞人有：{', '.join(names)}")

    for pid in evil_team + modred:
        user = members.get(pid)
        if user:
            names = [members[e].display_name for e in evil_team + modred if e != pid]
            await user.send(f"😈 你知道的同伴有：{', '.join(names) if names else '沒人'}")

    for pid in oberon:
        user = members.get(pid)
        if user:
            await user.send("😈 你是隱蔽壞人，看不到任何隊友")

    for pid in percival:
        user = members.get(pid)
        if user:
            names = [members[uid].display_name for uid, r in assignment.items() if r in ["梅林", "莫甘娜"]]
            await user.send(f"🔮 你知道梅林/莫甘娜有：{', '.join(names)}")

    await interaction.response.send_message("✨ 特殊視野已經分發完畢！")

# ----------- 任務投票（DM） -----------
@tree.command(name="missionstart", description="開始任務投票")
@app_commands.describe(players="標註玩家，例如 @玩家1 @玩家2")
async def missionstart(interaction: discord.Interaction, players: str):
    guild_id = interaction.guild.id
    mission_votes[guild_id] = {}

    player_list = interaction.user.mentionable_mentions if hasattr(interaction, 'mentionable_mentions') else []
    if not player_list:
        player_list = [m for m in interaction.guild.members if str(m) in players]

    for p in player_list:
        try:
            await p.send(f"🗳️ {interaction.guild.name} 任務開始！請回覆 `/vote 成功` 或 `/vote 失敗`")
        except:
            await interaction.followup.send(f"無法私訊 {p.mention}", ephemeral=True)
    await interaction.response.send_message("✅ 任務投票已經私訊給玩家！")

@tree.command(name="vote", description="投票 (DM使用)")
@app_commands.describe(choice="選擇成功或失敗")
async def vote(interaction: discord.Interaction, choice: str):
    if interaction.guild is not None:
        await interaction.response.send_message("⚠️ 請私訊我投票，不要在伺服器頻道使用此指令", ephemeral=True)
        return
    if choice not in ["成功", "失敗"]:
        await interaction.response.send_message("只能輸入 `成功` 或 `失敗`", ephemeral=True)
        return
    for guild_id, votes in mission_votes.items():
        if interaction.user.id in votes:
            votes[interaction.user.id] = choice
            await interaction.response.send_message(f"✅ 你的投票已紀錄：{choice}")
            return
        elif interaction.user.id not in votes:
            votes[interaction.user.id] = choice
            await interaction.response.send_message(f"✅ 你的投票已紀錄：{choice}")
            return
    await interaction.response.send_message("⚠️ 目前沒有任務要求你投票，請等待主持人開始任務", ephemeral=True)

@tree.command(name="missionresult", description="查看任務投票結果")
async def missionresult(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("⚠️ 請在伺服器頻道使用此指令", ephemeral=True)
        return
    guild_id = interaction.guild.id
    if guild_id not in mission_votes or len(mission_votes[guild_id]) == 0:
        await interaction.response.send_message("⚠️ 尚未開始任務或沒有玩家投票", ephemeral=True)
        return
    result = mission_votes.pop(guild_id)
    success = sum(1 for v in result.values() if v == "成功")
    fail = sum(1 for v in result.values() if v == "失敗")
    await interaction.response.send_message(f"📊 任務投票結果：成功 {success} 票，失敗 {fail} 票")

# ----------- Render Web Server 保活 -----------
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_app():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 5000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await asyncio.gather(
        bot.start(TOKEN),
        start_web_app()
    )

if __name__ == "__main__":
    asyncio.run(main())
