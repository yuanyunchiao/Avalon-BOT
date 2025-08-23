import os
import discord
import random
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # 取得完整成員列表
bot = commands.Bot(command_prefix="!", intents=intents)
print("DEBUG TOKEN:", TOKEN)

# ----------- Avalon Roles -----------
BASE_ROLES = {
    "good": ["梅林", "派西維爾"],
    "evil": ["莫甘娜", "刺客", "莫德雷德", "奧伯倫"],
    "others": ["忠臣", "爪牙"]
}

# 儲存遊戲狀態
games = {}

# ===== 發牌指令 =====
@bot.command()
async def deal(ctx, *players: discord.Member):
    """發牌，玩家清單可自由選擇，程式自動補忠臣/爪牙"""
    player_list = list(players)
    if len(player_list) < 5:
        await ctx.send("玩家不足（至少 5 人）")
        return

    # 遊戲人數對應好人壞人數
    total_players = len(player_list)
    # 簡單示範：5~10人
    roles_pool = []

    # 固定角色
    roles_pool.extend(["梅林", "派西維爾", "莫甘娜", "刺客", "莫德雷德", "奧伯倫"])

    # 自動補忠臣/爪牙
    remaining = total_players - len(roles_pool)
    if remaining > 0:
        # 平均補充好人忠臣與壞人爪牙
        for i in range(remaining):
            if i % 2 == 0:
                roles_pool.append("忠臣")
            else:
                roles_pool.append("爪牙")

    random.shuffle(roles_pool)

    # 發牌
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
    """發送特殊視野訊息給有能力的玩家"""
    if ctx.guild.id not in games:
        await ctx.send("⚠️ 尚未開始遊戲")
        return

    assignment = games[ctx.guild.id]

    merlin = [pid for pid, r in assignment.items() if r == "梅林"]
    percival = [pid for pid, r in assignment.items() if r == "派西維爾"]
    evil_team = [pid for pid, r in assignment.items() if r in ["莫甘娜", "刺客", "莫德雷德", "爪牙"]]
    oberon = [pid for pid, r in assignment.items() if r == "奧伯倫"]
    modred = [pid for pid, r in assignment.items() if r == "莫德雷德"]

    # --- 梅林視野 ---
    for pid in merlin:
        user = ctx.guild.get_member(pid)
        if user is None:
            continue
        names = [ctx.guild.get_member(e).display_name for e in evil_team if e not in modred and ctx.guild.get_member(e) is not None]
        names += [ctx.guild.get_member(o).display_name for o in oberon if ctx.guild.get_member(o) is not None]
        await user.send(f"👀 你知道壞人有：{', '.join(names)}")

    # --- 壞人視野 ---
    visible_evil = [pid for pid in evil_team + modred if pid not in oberon]
    for pid in visible_evil:
        user = ctx.guild.get_member(pid)
        if user is None:
            continue
        names = [ctx.guild.get_member(e).display_name for e in visible_evil if e != pid and ctx.guild.get_member(e) is not None]
        await user.send(f"😈 你知道的同伴有：{', '.join(names) if names else '沒人'}")

    # --- 派西維爾視野 ---
    for pid in percival:
        user = ctx.guild.get_member(pid)
        if user is None:
            continue
        names = [ctx.guild.get_member(uid).display_name for uid, r in assignment.items() if r in ["梅林", "莫甘娜"] and ctx.guild.get_member(uid) is not None]
        await user.send(f"🔮 你知道梅林/莫甘娜有：{', '.join(names)}")

    await ctx.send("✨ 特殊視野已經分發完畢！")

# ===== 任務投票 =====
mission_votes = {}

@bot.command()
async def missionstart(ctx, *players: discord.Member):
    """開始一個任務，玩家私訊投票"""
    if len(players) == 0:
        await ctx.send("⚠️ 必須指定任務玩家")
        return
    mission_votes[ctx.guild.id] = {p.id: None for p in players}
    for p in players:
        try:
            await p.send("🗳️ 任務開始！請使用 `!missionvote 成功` 或 `!missionvote 失敗` 投票")
        except:
            await ctx.send(f"無法私訊 {p.mention}")
    await ctx.send("✅ 任務已開始，已私訊指定玩家投票。")

@bot.command()
async def missionvote(ctx, choice: str):
    """玩家私訊投票任務成功/失敗"""
    if ctx.guild.id not in mission_votes:
        await ctx.send("⚠️ 尚未開始任務")
        return
    if ctx.author.id not in mission_votes[ctx.guild.id]:
        await ctx.send("⚠️ 你不是這次任務的玩家")
        return
    if choice not in ["成功", "失敗"]:
        await ctx.send("⚠️ 只能輸入 成功 或 失敗")
        return
    mission_votes[ctx.guild.id][ctx.author.id] = choice
    await ctx.send("✅ 已投票（內容保密）")

@bot.command()
async def missionresult(ctx):
    """公布任務結果"""
    if ctx.guild.id not in mission_votes:
        await ctx.send("⚠️ 尚未開始任務")
        return
    result = mission_votes.pop(ctx.guild.id)
    success = sum(1 for v in result.values() if v == "成功")
    fail = sum(1 for v in result.values() if v == "失敗")
    await ctx.send(f"📊 任務結果：成功 {success} 票，失敗 {fail} 票")

# ===== 主程式 =====
if __name__ == "__main__":
    bot.run(TOKEN)

