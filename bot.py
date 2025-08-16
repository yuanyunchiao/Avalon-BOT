import os
import discord
import random
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------- Avalon Roles -----------
ROLES = {
    "good": ["梅林", "派西維爾"],
    "evil": ["莫甘娜", "刺客", "奧伯倫"],
    "others": ["忠臣"]
}

# 儲存遊戲狀態
games = {}

@bot.event
async def on_ready():
    print(f"✅ 已登入 {bot.user}")

# ===== 角色發牌 =====
@bot.command()
async def deal(ctx, *players: discord.Member):
    """發牌，將角色私訊給玩家"""
    player_list = list(players)
    if len(player_list) < 5:
        await ctx.send("玩家不足（至少 5 人）")
        return

    roles_pool = ["梅林", "派西維爾", "莫甘娜", "刺客"] + ["忠臣"] * (len(player_list)-4)
    random.shuffle(roles_pool)

    assignment = {}
    for p in player_list:
        role = roles_pool.pop()
        assignment[p.id] = role
        try:
            await p.send(f"🎭 你的身份是：**{role}**")
        except:
            await ctx.send(f"無法私訊 {p.mention}")

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

    # 找出角色
    evil_team = [pid for pid, r in assignment.items() if r in ["莫甘娜", "刺客"]]
    merlin = [pid for pid, r in assignment.items() if r == "梅林"]
    percival = [pid for pid, r in assignment.items() if r == "派西維爾"]

    # 梅林看到壞人（不包含奧伯倫）
    for pid in merlin:
        user = ctx.guild.get_member(pid)
        names = [ctx.guild.get_member(e).display_name for e in evil_team]
        await user.send(f"👀 你知道壞人有：{', '.join(names)}")

    # 壞人互相知道（奧伯倫例外）
    for pid in evil_team:
        user = ctx.guild.get_member(pid)
        names = [ctx.guild.get_member(e).display_name for e in evil_team if e != pid]
        await user.send(f"😈 你知道的同伴有：{', '.join(names) if names else '沒人'}")

    # 派西維爾看到梅林/莫甘娜
    for pid in percival:
        user = ctx.guild.get_member(pid)
        names = [ctx.guild.get_member(uid).display_name for uid, r in assignment.items() if r in ["梅林", "莫甘娜"]]
        await user.send(f"🔮 你知道梅林/莫甘娜有：{', '.join(names)}")

    await ctx.send("✨ 特殊視野已經分發完畢！")

# ===== 匿名投票 =====
votes = {}

@bot.command()
async def votestart(ctx):
    """開始匿名投票"""
    votes[ctx.guild.id] = {}
    await ctx.send("🗳️ 匿名投票開始！請使用 `!vote 同意` 或 `!vote 否決`")

@bot.command()
async def vote(ctx, choice: str):
    """玩家投票"""
    if ctx.guild.id not in votes:
        await ctx.send("⚠️ 尚未開始投票")
        return

    if choice not in ["同意", "否決"]:
        await ctx.send("只能輸入 `同意` 或 `否決`")
        return

    votes[ctx.guild.id][ctx.author.id] = choice
    await ctx.send(f"{ctx.author.mention} ✅ 已投票（不公開內容）")

@bot.command()
async def voteresult(ctx):
    """公布投票結果"""
    if ctx.guild.id not in votes:
        await ctx.send("⚠️ 尚未開始投票")
        return
    result = votes.pop(ctx.guild.id)
    agree = sum(1 for v in result.values() if v == "同意")
    reject = sum(1 for v in result.values() if v == "否決")
    await ctx.send(f"📊 投票結果：同意 {agree} 票，否決 {reject} 票")
