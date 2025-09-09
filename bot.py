import os
import discord
import random
from discord.ext import commands

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

CORE_ROLES = ["梅林", "刺客"]  # 必備角色
OPTIONAL_ROLES = ["派西維爾", "莫甘娜", "莫德雷德", "奧伯倫"]

# 儲存遊戲狀態
games = {}
mission_votes = {}
custom_role_pool = {}  # 每個伺服器自訂角色池

@bot.event
async def on_ready():
    print(f"✅ 已登入 {bot.user}")

# ===== 設定自訂角色池 =====
@bot.command()
async def setroles(ctx, *roles):
    """設定額外的特殊角色（梅林、刺客自動加入）"""
    chosen = []
    invalid = []

    for r in roles:
        if r in OPTIONAL_ROLES:
            if r not in chosen:
                chosen.append(r)
        else:
            invalid.append(r)

    # 儲存：必備角色 + 可選角色
    custom_role_pool[ctx.guild.id] = CORE_ROLES + chosen

    msg = f"✅ 已設定角色池：{', '.join(CORE_ROLES + chosen)}"
    if invalid:
        msg += f"\n⚠️ 以下角色無效已忽略：{', '.join(invalid)}"
    await ctx.send(msg)

# ===== 發牌 =====
@bot.command()
async def deal(ctx, *players: discord.Member):
    """發牌，將角色私訊給玩家"""
    player_list = list(players)
    if len(player_list) < 5:
        await ctx.send("玩家不足（至少 5 人）")
        return

    # 取出伺服器設定的角色池，沒有的話就用必備角色
    roles_pool = custom_role_pool.get(ctx.guild.id, CORE_ROLES).copy()

    # 補足角色數（自動填忠臣/爪牙）
    while len(roles_pool) < len(player_list):
        good_count = sum(1 for r in roles_pool if r in DEFAULT_ROLES["good"] or r == "忠臣")
        evil_count = sum(1 for r in roles_pool if r in DEFAULT_ROLES["evil"] or r == "爪牙")
        if good_count <= evil_count:
            roles_pool.append("忠臣")
        else:
            roles_pool.append("爪牙")

    random.shuffle(roles_pool)

    assignment = {}
    for p in player_list:
        role = roles_pool.pop()
        assignment[p.id] = role
        try:
            await p.send(f"🎭 你的身份是：**{role}**")
        except:
            await ctx.send(f"⚠️ 無法私訊 {p.mention}")

    games[ctx.guild.id] = assignment
    await ctx.send("✅ 已經發牌完成！")

# ===== 特殊視野 =====
@bot.command()
async def vision(ctx):
    """讓有特殊視野的人收到訊息"""
    if ctx.guild.id not in games:
        await ctx.send("⚠️ 尚未開始遊戲")
        return
    assignment = games[ctx.guild.id]

    evil_team = [pid for pid, r in assignment.items() if r in ["莫甘娜", "刺客", "爪牙", "奧伯倫"]]
    modred = [pid for pid, r in assignment.items() if r == "莫德雷德"]
    merlin = [pid for pid, r in assignment.items() if r == "梅林"]
    percival = [pid for pid, r in assignment.items() if r == "派西維爾"]

    # 梅林看到壞人（包含奧伯倫，不含莫德雷德）
    for pid in merlin:
        user = bot.get_user(pid)
        if user:
            names = []
            for e, r in assignment.items():
                if r in ["莫甘娜", "刺客", "爪牙", "奧伯倫"]:  # 奧伯倫加入
                    u = bot.get_user(e)
                    if u:
                        names.append(u.display_name)
            await user.send(f"👀 你知道壞人有：{', '.join(names)}")

    # 壞人互相知道（奧伯倫除外，包括莫德雷德）
    for pid, r in assignment.items():
        if r in ["莫甘娜", "刺客", "爪牙", "莫德雷德"]:
            user = bot.get_user(pid)
            if user:
                names = []
                for e, rr in assignment.items():
                    if e != pid and rr in ["莫甘娜", "刺客", "爪牙", "莫德雷德"]:
                        u = bot.get_user(e)
                        if u:
                            names.append(u.display_name)
                await user.send(f"😈 你知道的同伴有：{', '.join(names) if names else '沒人'}")

    # 奧伯倫看不到任何隊友
    for pid, r in assignment.items():
        if r == "奧伯倫":
            user = bot.get_user(pid)
            if user:
                await user.send("😈 你是隱蔽壞人，看不到任何隊友")

    # 派西維爾看到梅林/莫甘娜
    for pid in percival:
        user = bot.get_user(pid)
        if user:
            names = []
            for uid, r in assignment.items():
                if r in ["梅林", "莫甘娜"]:
                    u = bot.get_user(uid)
                    if u:
                        names.append(u.display_name)
            await user.send(f"🔮 你知道梅林/莫甘娜有：{', '.join(names)}")

    await ctx.send("✨ 特殊視野已經分發完畢！")

# ===== 任務投票（DM） =====
mission_votes = {}  # { guild_id: { player_id: '成功'/'失敗' } }

@bot.command()
async def missionstart(ctx, *players: discord.Member):
    """伺服器發起任務投票，Bot 私訊每位玩家"""
    if len(players) == 0:
        await ctx.send("⚠️ 請指定參與任務的玩家")
        return

    guild_id = ctx.guild.id
    mission_votes[guild_id] = {p.id: None for p in players}

    for p in players:
        try:
            await p.send(
                f"🗳️ {ctx.guild.name} 任務開始！請回覆 `!vote 成功` 或 `!vote 失敗`"
            )
        except:
            await ctx.send(f"無法私訊 {p.mention}")

    await ctx.send("✅ 任務投票已經私訊給玩家！")

@bot.command()
async def vote(ctx, choice: str):
    """玩家在 DM 投票"""
    if ctx.guild is not None:
        await ctx.send("⚠️ 請私訊我投票，不要在伺服器頻道使用此指令")
        return

    if choice not in ["成功", "失敗"]:
        await ctx.send("只能輸入 `成功` 或 `失敗`")
        return

    for guild_id, votes in mission_votes.items():
        if ctx.author.id in votes:
            if votes[ctx.author.id] is None:
                votes[ctx.author.id] = choice
                await ctx.send(f"✅ 你的投票已紀錄：{choice}")
            else:
                await ctx.send("⚠️ 你已經投過票了")
            return

    await ctx.send("⚠️ 目前沒有任務要求你投票，請等待主持人開始任務")

@bot.command()
async def missionresult(ctx):
    """統計任務投票結果"""
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


# ===== Web server for Render =====
import asyncio
from aiohttp import web

async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_app():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 5000))  # Render 會給 PORT
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    if not TOKEN:
        raise ValueError("❌ DISCORD_TOKEN 未設定")
    await asyncio.gather(
        bot.start(TOKEN),
        start_web_app()
    )

if __name__ == "__main__":
    asyncio.run(main())
