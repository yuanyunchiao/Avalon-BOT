import os
import discord
import random
import asyncio
from discord.ext import commands
from aiohttp import web

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
print("DEBUG TOKEN:", TOKEN)

# ----------- Avalon Roles -----------
DEFAULT_ROLES = {
    "good": ["梅林", "派西維爾"],
    "evil": ["莫甘娜", "刺客", "莫德雷德", "奧伯倫"],
    "others": ["忠臣", "爪牙"]
}

# ----------- 遊戲狀態 -----------
games = {}          # { guild_id: {player_id: role} }
games_members = {}  # { guild_id: {player_id: Member} }
mission_votes = {}  # { guild_id: {player_id: '成功'/'失敗'} }
custom_role_pool = {}  # { guild_id: [roles...] }
server_locks = {}      # { guild_id: {"deal": False, "vision": False} }

# ----------- Bot Events -----------
@bot.event
async def on_ready():
    await bot.tree.sync()  # 🔑 同步 /指令
    print(f"✅ 已登入 {bot.user}，/指令已同步")

# ----------- 自訂角色池 -----------
@bot.tree.command(name="setroles", description="設定本局自訂角色池")
async def setroles_slash(interaction: discord.Interaction, roles: str):
    role_list = roles.split()
    if not role_list:
        await interaction.response.send_message("⚠️ 請輸入至少一個角色名稱", ephemeral=True)
        return
    valid_roles = DEFAULT_ROLES["good"] + DEFAULT_ROLES["evil"] + DEFAULT_ROLES["others"]
    for r in role_list:
        if r not in valid_roles:
            await interaction.response.send_message(f"⚠️ 角色 {r} 不合法", ephemeral=True)
            return
    custom_role_pool[interaction.guild_id] = list(role_list)
    await interaction.response.send_message(f"✅ 本局自訂角色池已設定：{', '.join(role_list)}")

# ----------- 發牌 -----------
@bot.tree.command(name="deal", description="發牌，將角色私訊給玩家")
async def deal_slash(interaction: discord.Interaction, players: str):
    guild_id = interaction.guild_id
    lock = server_locks.setdefault(guild_id, {"deal": False, "vision": False})
    if lock["deal"]:
        await interaction.response.send_message("⚠️ 發牌中，請稍等")
        return
    lock["deal"] = True

    # 解析 mentions
    player_list = interaction.message.mentions if interaction.message else []
    if not player_list:
        await interaction.response.send_message("⚠️ 請輸入至少 5 個玩家（使用 @）", ephemeral=True)
        lock["deal"] = False
        return

    if len(player_list) < 5:
        await interaction.response.send_message("⚠️ 玩家不足（至少 5 人）")
        lock["deal"] = False
        return

    # 強制使用自訂角色池
    if guild_id not in custom_role_pool or not custom_role_pool[guild_id]:
        await interaction.response.send_message("⚠️ 尚未設定自訂角色池，請使用 /setroles 設定")
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
            await interaction.followup.send(f"無法私訊 {p.mention}")

    games[guild_id] = assignment
    games_members[guild_id] = members_map
    await interaction.response.send_message("✅ 已經發牌完成！")
    lock["deal"] = False

# ----------- 特殊視野 -----------
@bot.tree.command(name="vision", description="分發特殊視野")
async def vision_slash(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id not in games or guild_id not in games_members:
        await interaction.response.send_message("⚠️ 尚未開始遊戲或缺少會員資料")
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
@bot.tree.command(name="missionstart", description="開始一個任務並私訊投票")
async def missionstart_slash(interaction: discord.Interaction, players: str):
    guild_id = interaction.guild_id
    mission_votes[guild_id] = {}

    player_list = interaction.message.mentions if interaction.message else []
    if not player_list:
        await interaction.response.send_message("⚠️ 請 @ 參與任務的玩家", ephemeral=True)
        return

    for p in player_list:
        try:
            await p.send(f"🗳️ {interaction.guild.name} 任務開始！請回覆 `/vote 成功` 或 `/vote 失敗`")
        except:
            await interaction.followup.send(f"無法私訊 {p.mention}")
    await interaction.response.send_message("✅ 任務投票已經私訊給玩家！")

@bot.tree.command(name="vote", description="對任務投票（僅限私訊使用）")
async def vote_slash(interaction: discord.Interaction, choice: str):
    if interaction.guild is not None:
        await interaction.response.send_message("⚠️ 請私訊我投票，不要在伺服器頻道使用此指令", ephemeral=True)
        return
    if choice not in ["成功", "失敗"]:
        await interaction.response.send_message("只能輸入 `成功` 或 `失敗`", ephemeral=True)
        return

    for guild_id, votes in mission_votes.items():
        if interaction.user.id in votes:
            votes[interaction.user.id] = choice
            await interaction.response.send_message(f"✅ 你的投票已更新為：{choice}", ephemeral=True)
            return
        elif interaction.user.id not in votes:
            votes[interaction.user.id] = choice
            await interaction.response.send_message(f"✅ 你的投票已紀錄：{choice}", ephemeral=True)
            return

    await interaction.response.send_message("⚠️ 目前沒有任務要求你投票", ephemeral=True)

@bot.tree.command(name="missionresult", description="查看任務投票結果")
async def missionresult_slash(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id not in mission_votes or len(mission_votes[guild_id]) == 0:
        await interaction.response.send_message("⚠️ 尚未開始任務或沒有玩家投票")
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
