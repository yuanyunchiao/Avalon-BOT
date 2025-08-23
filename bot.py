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
    """設定本局角色池"""
    if not roles:
        await ctx.send("⚠️ 請輸入至少一個角色名稱")
        return
    custom_role_pool[ctx.guild.id] = list(roles)
    await ctx.send(f"✅ 本局自訂角色池已設定：{', '.join(roles)}")

# ===== 發牌 =====
@bot.command()
async def deal(ctx, *players: discord.Member):
    """發牌，將角色私訊給玩家"""
    player_list = list(players)
    if len(player_list) < 5:
        await ctx.send("玩家不足（至少 5 人）")
        return

    # 選用自訂角色池，如果沒有就用預設
    roles_pool = custom_role_pool.get(ctx.guild.id, DEFAULT_ROLES["good"] + DEFAULT_ROLES["evil"])
    
    # 計算需要補充的角色數
    needed = len(player_list) - len(roles_pool)
    if needed > 0:
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

    evil_team = [pid for pid, r in assignment.items() if r in ["莫甘娜", "刺客", "爪牙"]]
    modred = [pid for pid, r in assignment.items() if r == "莫德雷德"]
    oberon = [pid for pid, r in assignment.items() if r == "奧伯倫"]
    merlin = [pid for pid, r in assignment.items() if r == "梅林"]
    percival = [pid for pid, r in assignment.items() if r == "派西維爾"]

    # 梅林看到壞人（不含莫德雷德，但包含奧伯倫）
    for pid in merlin:
        user = ctx.guild.get_member(pid)
        if user:
            names = [ctx.guild.get_member(e).display_name for e in evil_team] + \
                    [ctx.guild.get_member(o).display_name for o in oberon if ctx.guild.get_member(o)]
            await user.send(f"👀 你知道壞人有：{', '.join(names)}")

    # 壞人互相知道（奧伯倫除外，包括莫德雷德）
    for pid in evil_team + modred:
        user = ctx.guild.get_member(pid)
        if user:
            names = [ctx.guild.get_member(e).display_name for e in evil_team + modred if e != pid]
            await user.send(f"😈 你知道的同伴有：{', '.join(names) if names else '沒人'}")

    # 派西維爾看到梅林/莫甘娜
    for pid in percival:
        user = ctx.guild.get_member(pid)
        if user:
            names = [ctx.guild.get_member(uid).display_name for uid, r in assignment.items() if r in ["梅林", "莫甘娜"]]
            await user.send(f"🔮 你知道梅林/莫甘娜有：{', '.join(names)}")

    await ctx.send("✨ 特殊視野已經分發完畢！")

# ===== 任務投票 =====
@bot.command()
async def missionstart(ctx, *players: discord.Member):
    """開始任務投票"""
    if not players:
        await ctx.send("⚠️ 請指定上任務的玩家")
        return
    mission_votes[ctx.guild.id] = {p.id: None for p in players}
    await ctx.send("🗳️ 任務投票開始！玩家請私訊 `!missionvote 成功` 或 `!missionvote 失敗`")

@bot.command()
async def missionvote(ctx, choice: str):
    """玩家私訊投票"""
    if ctx.guild.id not in mission_votes:
        await ctx.send("⚠️ 尚未開始任務投票")
        return
    if ctx.author.id not in mission_votes[ctx.guild.id]:
        await ctx.send("⚠️ 你不在本次任務隊伍中")
        return
    if choice not in ["成功", "失敗"]:
        await ctx.send("只能輸入 `成功` 或 `失敗`")
        return

    mission_votes[ctx.guild.id][ctx.author.id] = choice
    await ctx.send(f"✅ 你已投票：{choice}")

@bot.command()
async def missionresult(ctx):
    """公布任務投票結果"""
    if ctx.guild.id not in mission_votes:
        await ctx.send("⚠️ 尚未開始任務投票")
        return
    result = mission_votes.pop(ctx.guild.id)
    success = sum(1 for v in result.values() if v == "成功")
    fail = sum(1 for v in result.values() if v == "失敗")
    await ctx.send(f"📊 任務投票結果：成功 {success} 票，失敗 {fail} 票")

if __name__ == "__main__":
    bot.run(TOKEN)
