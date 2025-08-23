import os
import discord
import random
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
print("DEBUG TOKEN:", TOKEN)

# ----------- 遊戲設定 -----------
games = {}          # 儲存遊戲角色分配
votes = {}          # 一般投票
mission_votes = {}  # 任務投票
setup_roles = {}    # 自訂角色池 per guild

# ===== 角色補全邏輯 =====
def auto_fill_roles(selected_roles, num_players):
    roles = selected_roles.copy()
    # 計算壞人與好人數
    num_good = 0
    num_evil = 0
    for r in roles:
        if r in ["梅林", "派西維爾", "忠臣"]:
            num_good += 1
        else:
            num_evil += 1
    # 補忠臣
    while num_good + num_evil < num_players:
        roles.append("忠臣")  # 好人補忠臣
        num_good += 1
    return roles

@bot.event
async def on_ready():
    print(f"✅ 已登入 {bot.user}")

# ===== 設定角色池 =====
@bot.command()
async def setup(ctx, *roles):
    """設定這局的角色池（自訂角色名稱）"""
    if len(roles) == 0:
        await ctx.send("⚠️ 請輸入角色名稱，例如：梅林 派西維爾 莫甘娜 刺客 奧伯倫")
        return
    setup_roles[ctx.guild.id] = list(roles)
    await ctx.send(f"✅ 角色池已設定：{', '.join(roles)}")

# ===== 發牌 =====
@bot.command()
async def deal(ctx, *players: discord.Member):
    """發牌，將角色私訊給玩家"""
    player_list = list(players)
    if len(player_list) < 5:
        await ctx.send("玩家不足（至少 5 人）")
        return

    # 使用自訂角色池，如果沒設定就用預設
    roles_pool = setup_roles.get(ctx.guild.id, ["梅林", "派西維爾", "莫甘娜", "刺客", "奧伯倫"])
    roles_pool = auto_fill_roles(roles_pool, len(player_list))
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
    """發送特殊視野訊息給有能力的玩家"""
    if ctx.guild.id not in games:
        await ctx.send("⚠️ 尚未開始遊戲")
        return

    assignment = games[ctx.guild.id]

    # 玩家分類
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
        # 梅林看到所有壞人，除了莫德雷德
        names = [ctx.guild.get_member(e).display_name for e in evil_team if e not in modred and ctx.guild.get_member(e) is not None]
        # 加上奧伯倫
        names += [ctx.guild.get_member(o).display_name for o in oberon if ctx.guild.get_member(o) is not None]
        await user.send(f"👀 你知道壞人有：{', '.join(names)}")

    # --- 壞人視野 ---
    # 壞人看到其他壞人（身份不明），奧伯倫除外
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


# ===== 普通投票 =====
@bot.command()
async def votestart(ctx):
    votes[ctx.guild.id] = {}
    await ctx.send("🗳️ 匿名投票開始！請使用 `!vote 同意` 或 `!vote 否決`")

@bot.command()
async def vote(ctx, choice: str):
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
    if ctx.guild.id not in votes:
        await ctx.send("⚠️ 尚未開始投票")
        return
    result = votes.pop(ctx.guild.id)
    agree = sum(1 for v in result.values() if v == "同意")
    reject = sum(1 for v in result.values() if v == "否決")
    await ctx.send(f"📊 投票結果：同意 {agree} 票，否決 {reject} 票")

# ===== 任務投票 =====
@bot.command()
async def missionstart(ctx, *players: discord.Member):
    """開始任務投票，將任務玩家私訊投票選項"""
    if len(players) == 0:
        await ctx.send("⚠️ 請指定參與任務的玩家")
        return

    guild_id = ctx.guild.id
    mission_votes[guild_id] = {}

    for p in players:
        try:
            await p.send(
                "🗳️ 任務投票開始！請私訊我 `!missionvote 成功` 或 `!missionvote 失敗`"
            )
        except:
            await ctx.send(f"無法私訊 {p.mention}")

    await ctx.send(f"✅ 任務投票已開始，已私訊 {len(players)} 位玩家")

@bot.command()
async def missionvote(ctx, choice: str):
    """玩家私訊投票任務成功/失敗"""
    guild_id = ctx.guild.id
    if guild_id not in mission_votes:
        await ctx.send("⚠️ 尚未開始任務投票")
        return
    if choice not in ["成功", "失敗"]:
        await ctx.send("⚠️ 只能輸入 `成功` 或 `失敗`")
        return
    mission_votes[guild_id][ctx.author.id] = choice
    await ctx.send("✅ 你的任務投票已紀錄")

@bot.command()
async def missionresult(ctx):
    """統計並公布任務投票結果"""
    guild_id = ctx.guild.id
    if guild_id not in mission_votes:
        await ctx.send("⚠️ 尚未開始任務投票")
        return
    result = mission_votes.pop(guild_id)
    success_count = sum(1 for v in result.values() if v == "成功")
    fail_count = sum(1 for v in result.values() if v == "失敗")
    await ctx.send(f"📊 任務投票結果：成功 {success_count} 票，失敗 {fail_count} 票")

# ===== 啟動 Bot =====
if __name__ == "__main__":
    bot.run(TOKEN)
