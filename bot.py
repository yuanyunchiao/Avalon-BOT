import os
import discord
import random
import asyncio
from discord.ext import commands
from aiohttp import web

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
print("DEBUG TOKEN:", TOKEN)

# ----------- Avalon Roles -----------
DEFAULT_ROLES = {
    "good": ["梅林", "派西維爾"],
    "evil": ["莫甘娜", "刺客", "莫德雷德", "奧伯倫"],
    "others": ["忠臣", "爪牙"]
}

# ----------- 遊戲狀態 -----------
games = {}  # { guild_id: {player_id: role} }
mission_votes = {}  # { guild_id: {player_id: '成功'/'失敗'} }
custom_role_pool = {}  # { guild_id: [roles...] }
server_locks = {}  # { guild_id: {"deal": False, "vision": False} }

# ----------- Bot Events -----------
@bot.event
async def on_ready():
    print(f"✅ 已登入 {bot.user}")

# ----------- 自訂角色池 -----------
@bot.command()
async def setroles(ctx, *roles):
    """設定本局自訂角色池"""
    if not roles:
        await ctx.send("⚠️ 請輸入至少一個角色名稱")
        return
    valid_roles = DEFAULT_ROLES["good"] + DEFAULT_ROLES["evil"] + DEFAULT_ROLES["others"]
    for r in roles:
        if r not in valid_roles:
            await ctx.send(f"⚠️ 角色 {r} 不合法")
            return
    custom_role_pool[ctx.guild.id] = list(roles)
    await ctx.send(f"✅ 本局自訂角色池已設定：{', '.join(roles)}")

# ----------- 發牌 -----------
@bot.command()
async def deal(ctx, *players: discord.Member):
    """發牌，將角色私訊給玩家"""
    guild_id = ctx.guild.id
    lock = server_locks.setdefault(guild_id, {"deal": False, "vision": False})
    if lock["deal"]:
        await ctx.send("⚠️ 發牌中，請稍等")
        return
    lock["deal"] = True

    player_list = list(players)
    if len(player_list) < 5:
        await ctx.send("玩家不足（至少 5 人）")
        lock["deal"] = False
        return

    # 強制使用自訂角色池
    if guild_id not in custom_role_pool or not custom_role_pool[guild_id]:
        await ctx.send("⚠️ 尚未設定自訂角色池，請使用 !setroles 設定")
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
    for p in player_list:
        role = roles_pool.pop()
        assignment[p.id] = role
        try:
            await p.send(f"🎭 你的身份是：**{role}**")
        except:
            await ctx.send(f"無法私訊 {p.mention}")

    games[guild_id] = assignment
    await ctx.send("✅ 已經發牌完成！")
    lock["deal"] = False

# ----------- 特殊視野 -----------
@bot.command()
async def vision(ctx):
    """讓有特殊視野的人收到訊息"""
    guild_id = ctx.guild.id
    lock = server_locks.setdefault(guild_id, {"deal": False, "vision": False})
    if lock["vision"]:
        await ctx.send("⚠️ 特殊視野正在發送中，請稍等")
        return
    lock["vision"] = True

    if guild_id not in games:
        await ctx.send("⚠️ 尚未開始遊戲")
        lock["vision"] = False
        return
    assignment = games[guild_id]

    evil_team = [pid for pid, r in assignment.items() if r in ["莫甘娜", "刺客", "爪牙"]]
    modred = [pid for pid, r in assignment.items() if r == "莫德雷德"]
    oberon = [pid for pid, r in assignment.items() if r == "奧伯倫"]
    merlin = [pid for pid, r in assignment.items() if r == "梅林"]
    percival = [pid for pid, r in assignment.items() if r == "派西維爾"]

    # 梅林看到壞人（含奧伯倫，不含莫德雷德）
    for pid in merlin:
        user = bot.get_user(pid)
        if user:
            names = [bot.get_user(e).display_name for e in evil_team if e not in modred]
            names += [bot.get_user(o).display_name for o in oberon]
            try:
                await user.send(f"👀 你知道壞人有：{', '.join(names)}")
            except: pass

    # 壞人互相知道（奧伯倫除外，包括莫德雷德）
    for pid in evil_team + modred:
        user = bot.get_user(pid)
        if user:
            names = [bot.get_user(e).display_name for e in evil_team + modred if e != pid]
            try:
                await user.send(f"😈 你知道的同伴有：{', '.join(names) if names else '沒人'}")
            except: pass

    # 奧伯倫看不到任何隊友
    for pid in oberon:
        user = bot.get_user(pid)
        if user:
            try:
                await user.send("😈 你是隱蔽壞人，看不到任何隊友")
            except: pass

    # 派西維爾看到梅林/莫甘娜
    for pid in percival:
        user = bot.get_user(pid)
        if user:
            names = [bot.get_user(uid).display_name for uid, r in assignment.items() if r in ["梅林", "莫甘娜"]]
            try:
                await user.send(f"🔮 你知道梅林/莫甘娜有：{', '.join(names)}")
            except: pass

    await ctx.send("✨ 特殊視野已經分發完畢！")
    lock["vision"] = False

# ----------- 任務投票（DM） -----------
@bot.command()
async def missionstart(ctx, *players: discord.Member):
    if len(players) == 0:
        await ctx.send("⚠️ 請指定參與任務的玩家")
        return

    guild_id = ctx.guild.id
    mission_votes[guild_id] = {}

    for p in players:
        try:
            await p.send(f"🗳️ {ctx.guild.name} 任務開始！請回覆 `!vote 成功` 或 `!vote 失敗`")
        except:
            await ctx.send(f"無法私訊 {p.mention}")
    await ctx.send("✅ 任務投票已經私訊給玩家！")

@bot.command()
async def vote(ctx, choice: str):
    if ctx.guild is not None:
        await ctx.send("⚠️ 請私訊我投票，不要在伺服器頻道使用此指令")
        return
    if choice not in ["成功", "失敗"]:
        await ctx.send("只能輸入 `成功` 或 `失敗`")
        return

    for guild_id, votes in mission_votes.items():
        if ctx.author.id in votes:
            votes[ctx.author.id] = choice
            await ctx.send(f"✅ 你的投票已紀錄：{choice}")
            return
        elif ctx.author.id not in votes:
            votes[ctx.author.id] = choice
            await ctx.send(f"✅ 你的投票已紀錄：{choice}")
            return

    await ctx.send("⚠️ 目前沒有任務要求你投票，請等待主持人開始任務")

@bot.command()
async def missionresult(ctx):
    if ctx.guild is None:
        await ctx.send("⚠️ 請在伺服器頻道使用此指令")
        return
    guild_id = ctx.guild.id
    if guild_id not in mission_votes or len(mission_votes[guild_id]) == 0:
        await ctx.send("⚠️ 尚未開始任務或沒有玩家投票")
        return
    result = mission_votes.pop(guild_id)
    success = sum(1 for v in result.values() if v == "成功")
    fail = sum(1 for v in result.values() if v == "失敗")
    await ctx.send(f"📊 任務投票結果：成功 {success} 票，失敗 {fail} 票")

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
