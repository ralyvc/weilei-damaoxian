"""
味蕾大冒险 - Flask 后端服务（盲猜模式）
玩法：AI 不给线索，玩家盲猜菜品名，DeepSeek 根据答案接近度给出渐进式反馈
得分规则：本题得分 = max(10, 110 - 猜测次数 * 10)
"""
from flask import Flask, send_from_directory, jsonify, request
import json
import urllib.request
import urllib.error
import uuid
import time
import os
import re
from datetime import datetime

app = Flask(__name__)

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'
IP_API_URL = 'https://ipapi.co/json/'

# ===== 内存数据存储 =====
sessions = {}
user_stats = {}
used_dishes_global = set()

# ===== 成就定义（100个） =====
ACHIEVEMENTS_DEF = [
    # === 新手入门（10个） ===
    {"id": "first_bite", "name": "初尝美味", "desc": "完成第1道题", "emoji": "🍜", "rarity": "common", "secret": False, "cond": "total_answered", "threshold": 1},
    {"id": "first_correct", "name": "首战告捷", "desc": "第一次猜对", "emoji": "🎉", "rarity": "common", "secret": False, "cond": "total_correct", "threshold": 1},
    {"id": "apprentice", "name": "美食学徒", "desc": "完成首次完整挑战（5题）", "emoji": "🔰", "rarity": "common", "secret": False, "cond": "games_completed", "threshold": 1},
    {"id": "score_50", "name": "小试牛刀", "desc": "单局总分达到50", "emoji": "🥉", "rarity": "common", "secret": False, "cond": "best_score", "threshold": 50},
    {"id": "score_100", "name": "初露锋芒", "desc": "单局总分达到100", "emoji": "🥈", "rarity": "common", "secret": False, "cond": "best_score", "threshold": 100},
    {"id": "score_200", "name": "崭露头角", "desc": "单局总分达到200", "emoji": "🥇", "rarity": "common", "secret": False, "cond": "best_score", "threshold": 200},
    {"id": "correct_3", "name": "三连胜", "desc": "累计猜对3道菜", "emoji": "✅", "rarity": "common", "secret": False, "cond": "total_correct", "threshold": 3},
    {"id": "correct_5", "name": "五星好评", "desc": "累计猜对5道菜", "emoji": "⭐", "rarity": "common", "secret": False, "cond": "total_correct", "threshold": 5},
    {"id": "play_3", "name": "乐此不疲", "desc": "完成3局挑战", "emoji": "🕹️", "rarity": "common", "secret": False, "cond": "games_completed", "threshold": 3},
    {"id": "play_5", "name": "铁杆玩家", "desc": "完成5局挑战", "emoji": "💪", "rarity": "common", "secret": False, "cond": "games_completed", "threshold": 5},

    # === 盲猜技巧（15个） ===
    {"id": "one_shot", "name": "一击命中", "desc": "1次盲猜就猜对", "emoji": "🎯", "rarity": "rare", "secret": False, "cond": "one_shot_count", "threshold": 1},
    {"id": "sharp_tongue", "name": "神射手", "desc": "累计3次一击命中", "emoji": "🏹", "rarity": "rare", "secret": False, "cond": "one_shot_count", "threshold": 3},
    {"id": "sniper", "name": "盲猜狙击手", "desc": "累计5次一击命中", "emoji": "🔫", "rarity": "epic", "secret": False, "cond": "one_shot_count", "threshold": 5},
    {"id": "two_shots", "name": "二次命中", "desc": "2次盲猜就猜对", "emoji": "🪄", "rarity": "common", "secret": False, "cond": "two_shot_count", "threshold": 1},
    {"id": "three_shots", "name": "三思后行", "desc": "3次盲猜猜对", "emoji": "🔮", "rarity": "common", "secret": False, "cond": "three_shot_count", "threshold": 1},
    {"id": "patient", "name": "耐心猎手", "desc": "某道题猜了5次以上才中", "emoji": "😅", "rarity": "common", "secret": False, "cond": "max_guesses_5", "threshold": 1},
    {"id": "stubborn", "name": "锲而不舍", "desc": "某道题猜了10次以上才中", "emoji": "😤", "rarity": "rare", "secret": False, "cond": "max_guesses_10", "threshold": 1},
    {"id": "never_give_up", "name": "永不放弃", "desc": "某道题猜了15次以上才中", "emoji": "🦾", "rarity": "epic", "secret": False, "cond": "max_guesses_15", "threshold": 1},
    {"id": "blind_master", "name": "盲猜大师", "desc": "单局5题平均不超过3次猜测", "emoji": "👑", "rarity": "legendary", "secret": False, "cond": "avg_guesses_le3", "threshold": 1},
    {"id": "blind_legend", "name": "盲猜传说", "desc": "单局5题平均不超过2次猜测", "emoji": "🌟", "rarity": "legendary", "secret": False, "cond": "avg_guesses_le2", "threshold": 1},
    {"id": "no_wrong", "name": "零失误", "desc": "单局5道题全部一次猜对", "emoji": "💎", "rarity": "legendary", "secret": False, "cond": "perfect_all_one", "threshold": 1},
    {"id": "speed_demon", "name": "闪电答手", "desc": "30秒内盲猜命中", "emoji": "⚡", "rarity": "rare", "secret": False, "cond": "speed_perfect", "threshold": 1},
    {"id": "speed_king", "name": "极速之王", "desc": "累计3次30秒内命中", "emoji": "🚀", "rarity": "epic", "secret": False, "cond": "speed_perfect", "threshold": 3},
    {"id": "high_score_80", "name": "高分选手", "desc": "单题得分达到80以上", "emoji": "📈", "rarity": "common", "secret": False, "cond": "single_score_80", "threshold": 1},
    {"id": "high_score_100", "name": "满分选手", "desc": "单题得分达到100", "emoji": "💯", "rarity": "rare", "secret": False, "cond": "single_score_100", "threshold": 1},

    # === 连击成就（10个） ===
    {"id": "streak_2", "name": "二连击", "desc": "连续猜对2题", "emoji": "🔥", "rarity": "common", "secret": False, "cond": "max_streak", "threshold": 2},
    {"id": "streak_3", "name": "三连击", "desc": "连续猜对3题", "emoji": "💥", "rarity": "common", "secret": False, "cond": "max_streak", "threshold": 3},
    {"id": "streak_4", "name": "四连击", "desc": "连续猜对4题", "emoji": "☄️", "rarity": "rare", "secret": False, "cond": "max_streak", "threshold": 4},
    {"id": "streak_5", "name": "五连绝世", "desc": "连续猜对5题（完美通关）", "emoji": "🌀", "rarity": "epic", "secret": False, "cond": "max_streak", "threshold": 5},
    {"id": "perfect_game", "name": "完美一局", "desc": "单局5道全部猜对", "emoji": "🏅", "rarity": "rare", "secret": False, "cond": "perfect_games", "threshold": 1},
    {"id": "perfect_3", "name": "完美猎手", "desc": "累计3次完美通关", "emoji": "🏆", "rarity": "epic", "secret": False, "cond": "perfect_games", "threshold": 3},
    {"id": "streak_life", "name": "连胜达人", "desc": "累计达成10次连击", "emoji": "🔥", "rarity": "rare", "secret": False, "cond": "total_streaks", "threshold": 10},
    {"id": "no_skip", "name": "全勤选手", "desc": "单局没有放弃任何一题", "emoji": "📋", "rarity": "common", "secret": False, "cond": "no_skip_game", "threshold": 1},
    {"id": "comeback", "name": "逆风翻盘", "desc": "第一题放弃后，剩余全对", "emoji": "🔄", "rarity": "epic", "secret": False, "cond": "comeback_win", "threshold": 1},
    {"id": "last_second", "name": "绝杀时刻", "desc": "最后一题猜对且是第5题", "emoji": "⏰", "rarity": "common", "secret": False, "cond": "last_second", "threshold": 1},

    # === 地域探索（20个） ===
    {"id": "city_explore_2", "name": "城市新手", "desc": "累计答对2个不同城市的菜", "emoji": "🗺️", "rarity": "common", "secret": False, "cond": "unique_cities", "threshold": 2},
    {"id": "city_explore_5", "name": "城市探索者", "desc": "累计答对5个不同城市的菜", "emoji": "🌍", "rarity": "rare", "secret": False, "cond": "unique_cities", "threshold": 5},
    {"id": "city_explore_10", "name": "城市旅行家", "desc": "累计答对10个不同城市的菜", "emoji": "✈️", "rarity": "epic", "secret": False, "cond": "unique_cities", "threshold": 10},
    {"id": "city_explore_20", "name": "城市收藏家", "desc": "累计答对20个不同城市的菜", "emoji": "🗺️", "rarity": "legendary", "secret": False, "cond": "unique_cities", "threshold": 20},
    {"id": "province_3", "name": "跨省吃货", "desc": "累计答对3个不同省市的菜", "emoji": "🚂", "rarity": "common", "secret": False, "cond": "unique_provinces", "threshold": 3},
    {"id": "province_8", "name": "吃遍全国", "desc": "累计答对8个不同省市的菜", "emoji": "🇨🇳", "rarity": "epic", "secret": False, "cond": "unique_provinces", "threshold": 8},
    {"id": "province_15", "name": "中华美食家", "desc": "累计答对15个不同省市的菜", "emoji": "🧭", "rarity": "legendary", "secret": False, "cond": "unique_provinces", "threshold": 15},
    {"id": "sichuan_1", "name": "川味初体验", "desc": "答对1道川菜", "emoji": "🌶️", "rarity": "common", "secret": False, "cond": "sichuan_dishes", "threshold": 1},
    {"id": "sichuan_3", "name": "川菜达人", "desc": "累计答对3道川菜", "emoji": "🔥", "rarity": "rare", "secret": False, "cond": "sichuan_dishes", "threshold": 3},
    {"id": "sichuan_5", "name": "川菜大师", "desc": "累计答对5道川菜", "emoji": "🌶️", "rarity": "epic", "secret": False, "cond": "sichuan_dishes", "threshold": 5},
    {"id": "gd_1", "name": "粤味初体验", "desc": "答对1道粤菜", "emoji": "🦐", "rarity": "common", "secret": False, "cond": "guangdong_dishes", "threshold": 1},
    {"id": "gd_3", "name": "粤菜达人", "desc": "累计答对3道粤菜", "emoji": "🥟", "rarity": "rare", "secret": False, "cond": "guangdong_dishes", "threshold": 3},
    {"id": "gd_5", "name": "粤菜大师", "desc": "累计答对5道粤菜", "emoji": "🫖", "rarity": "epic", "secret": False, "cond": "guangdong_dishes", "threshold": 5},
    {"id": "shandong_3", "name": "鲁菜通", "desc": "累计答对3道鲁菜", "emoji": "🫕", "rarity": "rare", "secret": False, "cond": "shandong_dishes", "threshold": 3},
    {"id": "jiangsu_3", "name": "淮扬通", "desc": "累计答对3道淮扬菜", "emoji": "🦢", "rarity": "rare", "secret": False, "cond": "jiangsu_dishes", "threshold": 3},
    {"id": "hunan_3", "name": "湘菜通", "desc": "累计答对3道湘菜", "emoji": "🫑", "rarity": "rare", "secret": False, "cond": "hunan_dishes", "threshold": 3},
    {"id": "zhejiang_3", "name": "浙菜通", "desc": "累计答对3道浙菜", "emoji": "🐟", "rarity": "rare", "secret": False, "cond": "zhejiang_dishes", "threshold": 3},
    {"id": "fujian_3", "name": "闽菜通", "desc": "累计答对3道闽菜", "emoji": "🍜", "rarity": "rare", "secret": False, "cond": "fujian_dishes", "threshold": 3},
    {"id": "anhui_3", "name": "徽菜通", "desc": "累计答对3道徽菜", "emoji": "🍄", "rarity": "rare", "secret": False, "cond": "anhui_dishes", "threshold": 3},
    {"id": "beijing_3", "name": "京味儿专家", "desc": "累计答对3道北京菜", "emoji": "🦆", "rarity": "rare", "secret": False, "cond": "beijing_dishes", "threshold": 3},
    {"id": "eight_cuisines", "name": "八大菜系通", "desc": "在8大菜系中各有答对记录", "emoji": "🥘", "rarity": "legendary", "secret": False, "cond": "eight_cuisines", "threshold": 8},

    # === 高分挑战（10个） ===
    {"id": "score_300", "name": "美食猎人", "desc": "单局总分超过300", "emoji": "🎖️", "rarity": "rare", "secret": False, "cond": "best_score", "threshold": 300},
    {"id": "score_400", "name": "美食专家", "desc": "单局总分超过400", "emoji": "🏅", "rarity": "rare", "secret": False, "cond": "best_score", "threshold": 400},
    {"id": "score_500", "name": "接近满分", "desc": "单局总分超过500", "emoji": "🏅", "rarity": "legendary", "secret": False, "cond": "best_score", "threshold": 500},
    {"id": "cumulative_500", "name": "积少成多", "desc": "累计总分超过500", "emoji": "🪙", "rarity": "common", "secret": False, "cond": "cumulative_score", "threshold": 500},
    {"id": "cumulative_1000", "name": "千金食客", "desc": "累计总分超过1000", "emoji": "💰", "rarity": "rare", "secret": False, "cond": "cumulative_score", "threshold": 1000},
    {"id": "cumulative_2000", "name": "万贯食神", "desc": "累计总分超过2000", "emoji": "👑", "rarity": "epic", "secret": False, "cond": "cumulative_score", "threshold": 2000},
    {"id": "cumulative_5000", "name": "传奇食神", "desc": "累计总分超过5000", "emoji": "🏆", "rarity": "legendary", "secret": False, "cond": "cumulative_score", "threshold": 5000},
    {"id": "total_1500", "name": "千分王者", "desc": "累计答对30道且总分过1500", "emoji": "🏆", "rarity": "legendary", "secret": False, "cond": "total_correct", "threshold": 30},

    # === 猜测次数成就（10个） ===
    {"id": "total_guesses_200", "name": "苦思冥想", "desc": "累计猜测200次", "emoji": "🧐", "rarity": "rare", "secret": False, "cond": "total_guesses", "threshold": 200},
    {"id": "min_guess_game", "name": "高效通关", "desc": "单局总猜测不超过8次", "emoji": "⚡", "rarity": "rare", "secret": False, "cond": "min_guess_game", "threshold": 1},
    {"id": "min_guess_game_5", "name": "超级高效", "desc": "单局总猜测不超过5次", "emoji": "💨", "rarity": "epic", "secret": False, "cond": "min_guess_game_5", "threshold": 1},
    {"id": "single_guess_2", "name": "快速响应", "desc": "某题2次以内猜对", "emoji": "👆", "rarity": "common", "secret": False, "cond": "fast_guess", "threshold": 1},
    {"id": "give_up_1", "name": "知难而退", "desc": "第一次放弃", "emoji": "🏳️", "rarity": "common", "secret": False, "cond": "give_up_count", "threshold": 1},
    {"id": "give_up_5", "name": "佛系玩家", "desc": "累计放弃5次", "emoji": "🧘", "rarity": "common", "secret": False, "cond": "give_up_count", "threshold": 5},
    {"id": "never_give_up_5", "name": "绝不认输", "desc": "连续5局不放弃", "emoji": "😤", "rarity": "rare", "secret": False, "cond": "never_give_up_streak", "threshold": 5},

    # === 成就收集（10个） ===
    {"id": "ach_5", "name": "初出茅庐", "desc": "解锁5个成就", "emoji": "🌟", "rarity": "common", "secret": False, "cond": "achievements_count", "threshold": 5},
    {"id": "ach_10", "name": "收藏大师", "desc": "解锁10个成就", "emoji": "✨", "rarity": "rare", "secret": False, "cond": "achievements_count", "threshold": 10},
    {"id": "ach_20", "name": "成就猎人", "desc": "解锁20个成就", "emoji": "🎖️", "rarity": "rare", "secret": False, "cond": "achievements_count", "threshold": 20},
    {"id": "ach_30", "name": "成就收藏家", "desc": "解锁30个成就", "emoji": "🏅", "rarity": "epic", "secret": False, "cond": "achievements_count", "threshold": 30},
    {"id": "ach_50", "name": "成就狂人", "desc": "解锁50个成就", "emoji": "👑", "rarity": "epic", "secret": False, "cond": "achievements_count", "threshold": 50},
    {"id": "ach_70", "name": "成就大师", "desc": "解锁70个成就", "emoji": "🏆", "rarity": "legendary", "secret": False, "cond": "achievements_count", "threshold": 70},
    {"id": "ach_90", "name": "接近完美", "desc": "解锁90个成就", "emoji": "💎", "rarity": "legendary", "secret": False, "cond": "achievements_count", "threshold": 90},
    {"id": "ach_100", "name": "全成就达成", "desc": "解锁全部100个成就", "emoji": "🏆", "rarity": "legendary", "secret": True, "cond": "achievements_count", "threshold": 100},
    {"id": "secret_first", "name": "秘密发现者", "desc": "解锁第1个隐藏成就", "emoji": "🔍", "rarity": "rare", "secret": False, "cond": "secret_count", "threshold": 1},
    {"id": "secret_5", "name": "秘密猎人", "desc": "解锁5个隐藏成就", "emoji": "🕵️", "rarity": "epic", "secret": False, "cond": "secret_count", "threshold": 5},

    # === 隐藏成就（25个） ===
    {"id": "easter_egg", "name": "彩蛋发现者", "desc": "答对一道彩蛋题目", "emoji": "🥚", "rarity": "epic", "secret": True, "cond": "easter_eggs", "threshold": 1},
    {"id": "midnight", "name": "深夜食堂", "desc": "在凌晨0-5点完成一局游戏", "emoji": "🌙", "rarity": "epic", "secret": True, "cond": "midnight_play", "threshold": 1},
    {"id": "early_bird", "name": "早起鸟儿", "desc": "在早上5-7点完成一局游戏", "emoji": "🐦", "rarity": "rare", "secret": True, "cond": "early_bird_play", "threshold": 1},
    {"id": "weekend", "name": "周末美食家", "desc": "在周末完成一局游戏", "emoji": "🎉", "rarity": "common", "secret": True, "cond": "weekend_play", "threshold": 1},
    {"id": "food_god", "name": "食神降世", "desc": "累计答对50道菜", "emoji": "👨‍🍳", "rarity": "legendary", "secret": True, "cond": "total_correct", "threshold": 50},
    {"id": "one_city_5", "name": "在地美食家", "desc": "答对同一城市的5道不同菜", "emoji": "🏠", "rarity": "epic", "secret": True, "cond": "one_city_5", "threshold": 1},
    {"id": "all_correct_10", "name": "十全十美", "desc": "连续2局全部猜对", "emoji": "💯", "rarity": "legendary", "secret": True, "cond": "double_perfect", "threshold": 1},
    {"id": "low_score_win", "name": "险胜", "desc": "单局总分刚好在100-150之间", "emoji": "😬", "rarity": "common", "secret": True, "cond": "low_score_win", "threshold": 1},
    {"id": "duck_fan", "name": "烤鸭狂热粉", "desc": "猜对北京烤鸭", "emoji": "🦆", "rarity": "common", "secret": True, "cond": "duck_fan", "threshold": 1},
    {"id": "tofu_lover", "name": "豆腐爱好者", "desc": "猜对3道含豆腐的菜", "emoji": "🧈", "rarity": "rare", "secret": True, "cond": "tofu_dishes", "threshold": 3},
    {"id": "noodle_master", "name": "面条大王", "desc": "猜对3道面条类菜品", "emoji": "🍝", "rarity": "rare", "secret": True, "cond": "noodle_dishes", "threshold": 3},
    {"id": "soup_lover", "name": "汤品达人", "desc": "猜对3道汤类菜品", "emoji": "🍲", "rarity": "rare", "secret": True, "cond": "soup_dishes", "threshold": 3},
    {"id": "spicy_5", "name": "无辣不欢", "desc": "猜对5道辣味菜", "emoji": "🌶️", "rarity": "epic", "secret": True, "cond": "spicy_dishes", "threshold": 5},
    {"id": "sweet_3", "name": "甜蜜蜜", "desc": "猜对3道甜品类", "emoji": "🍰", "rarity": "rare", "secret": True, "cond": "sweet_dishes", "threshold": 3},
    {"id": "seafood_3", "name": "海鲜达人", "desc": "猜对3道海鲜菜", "emoji": "🦀", "rarity": "rare", "secret": True, "cond": "seafood_dishes", "threshold": 3},
    {"id": "dumpling_3", "name": "饺子大王", "desc": "猜对3道饺子/包子类", "emoji": "🥟", "rarity": "rare", "secret": True, "cond": "dumpling_dishes", "threshold": 3},
    {"id": "rice_3", "name": "米饭杀手", "desc": "猜对3道米饭类菜品", "emoji": "🍚", "rarity": "common", "secret": True, "cond": "rice_dishes", "threshold": 3},
    {"id": "streak_5_total", "name": "连击之王", "desc": "单局连击达到5且不止一次", "emoji": "🌟", "rarity": "epic", "secret": True, "cond": "perfect_games", "threshold": 2},
    {"id": "play_10", "name": "持之以恒", "desc": "完成10局挑战", "emoji": "📅", "rarity": "rare", "secret": True, "cond": "games_completed", "threshold": 10},
    {"id": "play_20", "name": "美食老饕", "desc": "完成20局挑战", "emoji": "📜", "rarity": "epic", "secret": True, "cond": "games_completed", "threshold": 20},
    {"id": "play_50", "name": "味蕾传说", "desc": "完成50局挑战", "emoji": "🌟", "rarity": "legendary", "secret": True, "cond": "games_completed", "threshold": 50},
    {"id": "first_giveup_correct", "name": "浪子回头", "desc": "放弃一题后紧接着一击命中", "emoji": "🔄", "rarity": "rare", "secret": True, "cond": "comeback_one_shot", "threshold": 1},
    {"id": "all_rarity", "name": "大满贯", "desc": "拥有所有4种稀有度的成就", "emoji": "🌈", "rarity": "legendary", "secret": True, "cond": "all_rarity", "threshold": 1},
]

RARITY_COLORS = {
    "common": "#8C7B72",
    "rare": "#4A90D9",
    "epic": "#9B59B6",
    "legendary": "#F5A623"
}

# ===== 本题得分计算：基于猜测次数 =====
def calc_question_score(guess_count):
    """本题得分 = max(10, 110 - 猜测次数 * 10)"""
    return max(10, 110 - guess_count * 10)

# ===== 统计数据 =====
def get_or_create_stats(session_id):
    if session_id not in user_stats:
        user_stats[session_id] = {
            "total_answered": 0,
            "total_correct": 0,
            "games_completed": 0,
            "best_score": 0,
            "max_streak": 0,
            "perfect_games": 0,
            "one_shot_count": 0,
            "two_shot_count": 0,
            "three_shot_count": 0,
            "max_guesses_5": 0,
            "max_guesses_10": 0,
            "max_guesses_15": 0,
            "avg_guesses_le3": 0,
            "avg_guesses_le2": 0,
            "perfect_all_one": 0,
            "speed_perfect": 0,
            "single_score_80": 0,
            "single_score_100": 0,
            "cumulative_score": 0,
            "total_guesses": 0,
            "min_guess_game": 0,
            "min_guess_game_5": 0,
            "fast_guess": 0,
            "give_up_count": 0,
            "never_give_up_streak": 0,
            "total_streaks": 0,
            "no_skip_game": 0,
            "comeback_win": 0,
            "last_second": 0,
            "unique_cities": set(),
            "unique_provinces": set(),
            "sichuan_dishes": 0,
            "guangdong_dishes": 0,
            "shandong_dishes": 0,
            "jiangsu_dishes": 0,
            "hunan_dishes": 0,
            "zhejiang_dishes": 0,
            "fujian_dishes": 0,
            "anhui_dishes": 0,
            "beijing_dishes": 0,
            "eight_cuisines": 0,
            "easter_eggs": 0,
            "total_dishes_seen": 0,
            "one_city_5": 0,
            "double_perfect": 0,
            "low_score_win": 0,
            "duck_fan": 0,
            "tofu_dishes": 0,
            "noodle_dishes": 0,
            "soup_dishes": 0,
            "spicy_dishes": 0,
            "sweet_dishes": 0,
            "seafood_dishes": 0,
            "dumpling_dishes": 0,
            "rice_dishes": 0,
            "comeback_one_shot": 0,
            "secret_count": 0,
            "midnight_play": 0,
            "early_bird_play": 0,
            "weekend_play": 0,
            "all_rarity": 0,
            "city_dish_counts": {},  # city -> count of correct
            "achievements_unlocked": set(),
            "used_dishes": set(),
            "first_play": datetime.now().isoformat()
        }
    return user_stats[session_id]

def classify_dish(dish, source):
    """根据菜名和来源分类，用于隐藏成就统计"""
    tags = set()
    d = dish.lower()
    if "豆腐" in d: tags.add("tofu")
    if any(w in d for w in ["面", "粉", "米线", "拉面", "刀削面", "担担面", "炸酱面"]): tags.add("noodle")
    if any(w in d for w in ["汤", "羹", "煲"]): tags.add("soup")
    if any(w in d for w in ["辣", "椒", "麻", "火锅", "水煮", "干锅"]): tags.add("spicy")
    if any(w in d for w in ["甜", "糖", "糕", "饼", "酥", "汤圆", "月饼"]): tags.add("sweet")
    if any(w in d for w in ["鱼", "虾", "蟹", "贝", "海参", "鱿鱼", "鲍鱼", "扇贝"]): tags.add("seafood")
    if any(w in d for w in ["饺子", "包子", "馒头", "馄饨", "烧麦", "小笼"]): tags.add("dumpling")
    if any(w in d for w in ["饭", "炒饭", "盖浇", "煲仔"]): tags.add("rice")
    if d == "北京烤鸭": tags.add("duck")
    return tags

def classify_province(source):
    """根据来源判断菜系"""
    if not source: return None
    s = source
    if any(w in s for w in ["四川", "成都", "重庆", "川"]): return "sichuan"
    if any(w in s for w in ["广东", "广州", "深圳", "潮汕", "粤"]): return "guangdong"
    if any(w in s for w in ["山东", "济南", "鲁"]): return "shandong"
    if any(w in s for w in ["江苏", "南京", "扬州", "淮扬", "苏"]): return "jiangsu"
    if any(w in s for w in ["湖南", "长沙", "湘"]): return "hunan"
    if any(w in s for w in ["浙江", "杭州", "浙"]): return "zhejiang"
    if any(w in s for w in ["福建", "福州", "厦门", "闽"]): return "fujian"
    if any(w in s for w in ["安徽", "徽"]): return "anhui"
    if any(w in s for w in ["北京", "京"]): return "beijing"
    return None

def update_dish_stats(stats, dish, source):
    """更新菜品分类统计"""
    tags = classify_dish(dish, source)
    if "tofu" in tags: stats["tofu_dishes"] += 1
    if "noodle" in tags: stats["noodle_dishes"] += 1
    if "soup" in tags: stats["soup_dishes"] += 1
    if "spicy" in tags: stats["spicy_dishes"] += 1
    if "sweet" in tags: stats["sweet_dishes"] += 1
    if "seafood" in tags: stats["seafood_dishes"] += 1
    if "dumpling" in tags: stats["dumpling_dishes"] += 1
    if "rice" in tags: stats["rice_dishes"] += 1
    if "duck" in tags: stats["duck_fan"] += 1

    province = classify_province(source)
    if province:
        stats[province + "_dishes"] = stats.get(province + "_dishes", 0) + 1

    # 城市统计
    city = source.split("市")[0] if source else ""
    if city:
        stats["city_dish_counts"][city] = stats["city_dish_counts"].get(city, 0) + 1
        if stats["city_dish_counts"][city] >= 5:
            stats["one_city_5"] = max(stats["one_city_5"], 1)

    stats["total_dishes_seen"] += 1

def check_achievements(stats):
    unlocked = []
    checks = {
        "total_answered": stats["total_answered"],
        "total_correct": stats["total_correct"],
        "games_completed": stats["games_completed"],
        "best_score": stats["best_score"],
        "max_streak": stats["max_streak"],
        "perfect_games": stats["perfect_games"],
        "one_shot_count": stats["one_shot_count"],
        "two_shot_count": stats["two_shot_count"],
        "three_shot_count": stats["three_shot_count"],
        "max_guesses_5": stats["max_guesses_5"],
        "max_guesses_10": stats["max_guesses_10"],
        "max_guesses_15": stats["max_guesses_15"],
        "avg_guesses_le3": stats["avg_guesses_le3"],
        "avg_guesses_le2": stats["avg_guesses_le2"],
        "perfect_all_one": stats["perfect_all_one"],
        "speed_perfect": stats["speed_perfect"],
        "single_score_80": stats["single_score_80"],
        "single_score_100": stats["single_score_100"],
        "cumulative_score": stats["cumulative_score"],
        "total_guesses": stats["total_guesses"],
        "min_guess_game": stats["min_guess_game"],
        "min_guess_game_5": stats["min_guess_game_5"],
        "fast_guess": stats["fast_guess"],
        "give_up_count": stats["give_up_count"],
        "never_give_up_streak": stats["never_give_up_streak"],
        "total_streaks": stats["total_streaks"],
        "no_skip_game": stats["no_skip_game"],
        "comeback_win": stats["comeback_win"],
        "last_second": stats["last_second"],
        "unique_cities": len(stats["unique_cities"]),
        "unique_provinces": len(stats["unique_provinces"]),
        "sichuan_dishes": stats["sichuan_dishes"],
        "guangdong_dishes": stats["guangdong_dishes"],
        "shandong_dishes": stats["shandong_dishes"],
        "jiangsu_dishes": stats["jiangsu_dishes"],
        "hunan_dishes": stats["hunan_dishes"],
        "zhejiang_dishes": stats["zhejiang_dishes"],
        "fujian_dishes": stats["fujian_dishes"],
        "anhui_dishes": stats["anhui_dishes"],
        "beijing_dishes": stats["beijing_dishes"],
        "eight_cuisines": sum(1 for k in ["sichuan_dishes","guangdong_dishes","shandong_dishes","jiangsu_dishes","hunan_dishes","zhejiang_dishes","fujian_dishes","anhui_dishes"] if stats.get(k,0) > 0),
        "easter_eggs": stats["easter_eggs"],
        "total_dishes_seen": stats["total_dishes_seen"],
        "one_city_5": stats["one_city_5"],
        "double_perfect": stats["double_perfect"],
        "low_score_win": stats["low_score_win"],
        "duck_fan": stats["duck_fan"],
        "tofu_dishes": stats["tofu_dishes"],
        "noodle_dishes": stats["noodle_dishes"],
        "soup_dishes": stats["soup_dishes"],
        "spicy_dishes": stats["spicy_dishes"],
        "sweet_dishes": stats["sweet_dishes"],
        "seafood_dishes": stats["seafood_dishes"],
        "dumpling_dishes": stats["dumpling_dishes"],
        "rice_dishes": stats["rice_dishes"],
        "comeback_one_shot": stats["comeback_one_shot"],
        "secret_count": stats["secret_count"],
        "midnight_play": stats["midnight_play"],
        "early_bird_play": stats["early_bird_play"],
        "weekend_play": stats["weekend_play"],
        "all_rarity": stats["all_rarity"],
        "achievements_count": len(stats["achievements_unlocked"]),
    }
    for ach in ACHIEVEMENTS_DEF:
        if ach["id"] not in stats["achievements_unlocked"]:
            val = checks.get(ach["cond"], 0)
            if val >= ach["threshold"]:
                stats["achievements_unlocked"].add(ach["id"])
                if ach.get("secret", False):
                    stats["secret_count"] = stats.get("secret_count", 0) + 1
                unlocked.append(ach)

    # 检查 all_rarity（拥有所有4种稀有度）
    unlocked_rarities = set()
    for ach_id in stats["achievements_unlocked"]:
        for a in ACHIEVEMENTS_DEF:
            if a["id"] == ach_id:
                unlocked_rarities.add(a["rarity"])
                break
    if len(unlocked_rarities) >= 4:
        stats["all_rarity"] = 1

    return unlocked

# ===== DeepSeek 调用 =====
def call_deepseek_chat(system_msg, user_msg, temperature=1.0):
    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            "temperature": temperature,
            "max_tokens": 2000
        }).encode('utf-8'),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + DEEPSEEK_API_KEY},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        return data["choices"][0]["message"]["content"]

def parse_json_response(content):
    content = content.strip()
    if "```" in content:
        m = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if m: content = m.group(1).strip()
    m = re.search(r'\[\s*\{', content)
    if m: content = content[m.start():]
    m2 = re.search(r'\}\s*\]\s*$', content)
    if m2: content = content[:m2.end()]
    content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', content)
    return json.loads(content)

def build_dish_prompt(city, used_dishes_set):
    exclude = '\n8. 严格不要出现以下已出过的菜品：' + '、'.join(list(used_dishes_set)[:30]) if used_dishes_set else ''
    location = f'玩家位于【{city}】，优先出{city}及周边特色美食（至少2道）。' if city else '从中国各大菜系中随机选题。'
    return (
        f'你是"味蕾大冒险"盲猜美食游戏的AI出题官。\n\n'
        f'{location}\n'
        f'请生成5道中国美食的谜题数据。\n\n'
        f'要求：\n'
        f'1. 必须是真实存在的经典名菜或特色小吃\n'
        f'2. 每道菜准备4条渐进式线索（从最模糊到最明显）\n'
        f'3. 给出2-3个别名/俗称\n'
        f'4. 给出来源地（省市）和当地知名餐厅推荐\n'
        f'5. 其中1道设计为彩蛋题' + exclude + '\n\n'
        f'严格返回JSON数组：\n'
        f'[{{"dish":"菜名","aliases":["别名"],"clues":["模糊","较具体","接近","揭晓"],"source":"省市","restaurant":"餐厅","addr":"地址","is_easter":false}}]'
    )

def build_blind_feedback_prompt(dish, aliases, clues, guess, guess_count, history):
    history_str = '\n'.join([f'  第{h["round"]}次猜：{h["guess"]}' for h in history])
    return (
        f'你是"味蕾大冒险"盲猜美食游戏的AI评审官。\n\n'
        f'当前谜底：{dish}（别名：{", ".join(aliases)}）\n'
        f'玩家第{guess_count}次猜测：{guess}\n\n'
        f'之前的猜测记录：\n{history_str if history_str else "  无（这是第一次猜）"}\n\n'
        f'渐进线索（按模糊到明显排列）：\n'
        f'1. {clues[0]}\n2. {clues[1]}\n3. {clues[2]}\n4. {clues[3]}\n\n'
        f'请根据玩家的猜测与谜底的【语义相关性】给出评分（0-100整数）和反馈。\n\n'
        f'评分标准（综合判断）：\n'
        f'- 90-100：完全猜对\n'
        f'- 70-89：非常接近\n'
        f'- 50-69：高度相关（同菜系/同主料/同烹饪法）\n'
        f'- 30-49：方向正确（同一菜系或同类食材）\n'
        f'- 15-29：略微沾边（中国菜大类）\n'
        f'- 5-14：完全不对（保底5分）\n\n'
        f'反馈规则（15-40字）：\n'
        f'- score>=70：祝贺+揭示答案\n'
        f'- score 50-69：鼓励+细微提示\n'
        f'- score 30-49：方向不错+模糊提示\n'
        f'- score 15-29：幽默调侃+方向提示\n'
        f'- score<15：幽默吐槽+最模糊提示\n'
        f'- 猜测越多提示越明显\n'
        f'- 【重要】score<70时，反馈中绝对不能包含谜底「{dish}」的任何一个字！\n'
        f'- 【重要】score<70时，不能直接或间接说出答案，只能给方向性提示\n'
        f'- 提示用"菜系""烹饪方式""食材大类""口感"等抽象描述，不要具体菜名\n\n'
        f'严格返回JSON：\n{{"score":65,"feedback":"反馈文字"}}'
    )

# ===== Flask 路由 =====
@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), filename)

@app.route('/api/ip/locate', methods=['GET'])
def ip_locate():
    try:
        req = urllib.request.Request(IP_API_URL)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return jsonify({"city": data.get("city"), "region": data.get("region")})
    except:
        return jsonify({"city": None, "region": None})

@app.route('/api/game/start', methods=['POST'])
def game_start():
    session_id = str(uuid.uuid4())
    city = None
    try:
        city = (request.get_json() or {}).get("city")
    except:
        pass

    stats = get_or_create_stats(session_id)
    used = stats["used_dishes"]
    global used_dishes_global
    used_combined = used | used_dishes_global

    try:
        prompt = build_dish_prompt(city, used_combined)
        raw = call_deepseek_chat(
            "你是专业美食文化AI出题官，严格按JSON格式返回。",
            prompt, temperature=1.2
        )
        questions = parse_json_response(raw)
        valid = []
        for q in questions:
            if q.get("dish") and q.get("clues") and len(q.get("clues", [])) >= 4:
                if not q.get("aliases"): q["aliases"] = [q["dish"]]
                if not q.get("source"): q["source"] = "中国"
                if not q.get("restaurant"): q["restaurant"] = "当地知名餐厅"
                if not q.get("addr"): q["addr"] = "请咨询当地人"
                q["is_easter"] = q.get("is_easter", False)
                valid.append(q)
        questions = valid[:5]
    except Exception as e:
        import traceback
        print(f"[ERROR] DeepSeek failed: {e}")
        traceback.print_exc()
        return jsonify({"error": "AI出题失败", "detail": str(e)}), 500

    if not questions:
        return jsonify({"error": "AI出题失败", "detail": "未能生成有效题目"}), 500

    for q in questions:
        used.add(q["dish"])
        used_dishes_global.add(q["dish"])

    sessions[session_id] = {
        "questions": questions,
        "current_q": 0,
        "total_score": 0,
        "streak": 0,
        "max_streak": 0,
        "results": [],
        "start_time": time.time(),
        "city": city,
        "guess_history": [],
        "guess_count": 0,
        "skipped": False,  # 本局是否有过放弃
        "first_q_gave_up": False,
        "prev_gave_up": False,
        "total_guesses_this_game": 0,
    }

    return jsonify({
        "session_id": session_id,
        "question_preview": [{
            "index": i,
            "source": q["source"],
            "is_easter": q.get("is_easter", False),
        } for i, q in enumerate(questions)],
        "city": city,
    })

@app.route('/api/game/blind-guess', methods=['POST'])
def blind_guess():
    data = request.get_json() or {}
    session_id = data.get("session_id")
    guess = data.get("guess", "").strip()

    if not session_id or session_id not in sessions:
        return jsonify({"error": "会话不存在"}), 400

    sess = sessions[session_id]
    stats = get_or_create_stats(session_id)
    q_idx = sess["current_q"]
    if q_idx >= len(sess["questions"]):
        return jsonify({"error": "题目已结束"}), 400

    q = sess["questions"][q_idx]
    dish = q["dish"]
    aliases = q.get("aliases", [])
    clues = q.get("clues", [])

    def calc_sim(inp, d, als):
        inp = inp.replace(' ', '').lower()
        d = d.replace(' ', '').lower()
        if inp == d: return 100
        if d in inp or inp in d:
            r = min(len(inp), len(d)) / max(len(inp), len(d))
            return round(70 + r * 30)
        for a in als:
            a = a.replace(' ', '').lower()
            if a == inp: return 95
            if a in inp or inp in a:
                r = min(len(inp), len(a)) / max(len(inp), len(a))
                return round(65 + r * 30)
        match_c = sum(1 for c in inp if c in d)
        char_over = match_c / len(inp) if inp else 0
        best_sub = 0
        for length in range(2, len(d)+1):
            for si in range(len(d)-length+1):
                sub = d[si:si+length]
                if sub in inp:
                    best_sub = max(best_sub, (length / len(d)) * 60)
        raw = max(char_over * 50, best_sub)
        if raw < 5: return 5
        if raw < 25: return round(10 + raw * 1.2)
        if raw < 50: return round(25 + raw * 0.7)
        return round(raw)

    sess["guess_count"] += 1
    sess["total_guesses_this_game"] += 1
    guess_count = sess["guess_count"]

    ai_score = None
    feedback = None
    try:
        raw_resp = call_deepseek_chat(
            "你是味蕾大冒险的AI评审官。根据语义相关性评分并生成反馈。严格返回JSON。",
            build_blind_feedback_prompt(dish, aliases, clues, guess, guess_count, sess["guess_history"]),
            temperature=0.7
        )
        raw_resp = raw_resp.strip()
        if "```" in raw_resp:
            m = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw_resp)
            if m: raw_resp = m.group(1).strip()
        m = re.search(r'\{[^{}]*"score"[^{}]*\}', raw_resp, re.DOTALL)
        if m:
            parsed = json.loads(m.group(0))
            ai_score = int(parsed.get("score", 0))
            feedback = parsed.get("feedback", "").strip().strip('"').strip("'").strip('\u201c').strip('\u201d')
        else:
            parsed = json.loads(raw_resp)
            ai_score = int(parsed.get("score", 0))
            feedback = parsed.get("feedback", "").strip()
    except Exception as e:
        print(f"[WARN] AI scoring failed: {e}")

    if ai_score is not None:
        sim = max(5, min(100, ai_score))
    else:
        sim = calc_sim(guess, dish, aliases)
        if not feedback:
            if sim >= 70:
                feedback = f"恭喜你猜对了！答案就是「{dish}」！"
            elif sim >= 40:
                feedback = "方向越来越近了，再想想看..."
            else:
                feedback = "这道题有点难度，换个角度试试？"

    is_correct = sim >= 70

    sess["guess_history"].append({"round": guess_count, "guess": guess, "sim": sim})
    stats["total_guesses"] += 1

    if is_correct:
        # ===== 本题得分：基于猜测次数 =====
        final_score = calc_question_score(guess_count)

        sess["total_score"] += final_score
        sess["streak"] += 1
        sess["max_streak"] = max(sess["max_streak"], sess["streak"])
        stats["total_answered"] += 1
        stats["total_correct"] += 1
        stats["cumulative_score"] += final_score
        stats["unique_cities"].add(q.get("source", ""))
        stats["unique_provinces"].add(q.get("source", ""))

        update_dish_stats(stats, dish, q.get("source", ""))

        # 盲猜技巧统计
        if guess_count == 1:
            stats["one_shot_count"] += 1
            stats["fast_guess"] += 1
            if sess["prev_gave_up"]:
                stats["comeback_one_shot"] += 1
                sess["prev_gave_up"] = False
        elif guess_count == 2:
            stats["two_shot_count"] += 1
        elif guess_count == 3:
            stats["three_shot_count"] += 1

        if guess_count >= 5:
            stats["max_guesses_5"] += 1
        if guess_count >= 10:
            stats["max_guesses_10"] += 1
        if guess_count >= 15:
            stats["max_guesses_15"] += 1

        elapsed = int((time.time() - sess["start_time"]) * 1000)
        if elapsed <= 30000:
            stats["speed_perfect"] += 1

        if final_score >= 80:
            stats["single_score_80"] += 1
        if final_score >= 100:
            stats["single_score_100"] += 1

        if q.get("is_easter"):
            stats["easter_eggs"] += 1

        result = {
            "dish": dish,
            "source": q.get("source", ""),
            "restaurant": q.get("restaurant", ""),
            "addr": q.get("addr", ""),
            "guess": guess,
            "sim": sim,
            "final_score": final_score,
            "guess_count": guess_count,
            "is_correct": True,
            "is_easter": q.get("is_easter", False),
            "all_guesses": list(sess["guess_history"]),
        }
        sess["results"].append(result)

        new_achievements = check_achievements(stats)

        is_last = q_idx >= 4
        if not is_last:
            sess["current_q"] += 1
            sess["guess_history"] = []
            sess["guess_count"] = 0
            sess["start_time"] = time.time()

        return jsonify({
            "result": result,
            "feedback": feedback,
            "current_score": sess["total_score"],
            "streak": sess["streak"],
            "max_streak": sess["max_streak"],
            "new_achievements": new_achievements,
            "is_last": is_last,
            "next_source": sess["questions"][q_idx + 1]["source"] if not is_last else None,
        })
    else:
        return jsonify({
            "result": {
                "guess": guess,
                "sim": sim,
                "guess_count": guess_count,
                "is_correct": False,
            },
            "feedback": feedback,
            "current_score": sess["total_score"],
            "streak": 0,
        })

@app.route('/api/game/give-up', methods=['POST'])
def give_up():
    data = request.get_json() or {}
    session_id = data.get("session_id")
    if not session_id or session_id not in sessions:
        return jsonify({"error": "会话不存在"}), 400

    sess = sessions[session_id]
    stats = get_or_create_stats(session_id)
    q_idx = sess["current_q"]
    if q_idx >= len(sess["questions"]):
        return jsonify({"error": "题目已结束"}), 400

    q = sess["questions"][q_idx]
    dish = q["dish"]
    guess_count = sess["guess_count"]

    stats["total_answered"] += 1
    stats["give_up_count"] += 1
    sess["streak"] = 0
    sess["skipped"] = True
    sess["prev_gave_up"] = True
    if q_idx == 0:
        sess["first_q_gave_up"] = True

    result = {
        "dish": dish, "source": q.get("source", ""),
        "restaurant": q.get("restaurant", ""), "addr": q.get("addr", ""),
        "guess_count": guess_count, "is_correct": False, "given_up": True,
        "is_easter": q.get("is_easter", False),
    }
    sess["results"].append(result)

    feedback = None
    try:
        feedback = call_deepseek_chat(
            "你是味蕾大冒险的AI评审官。玩家放弃了这道题，用幽默风趣的语气公布答案并安慰玩家，20-40字。",
            f'谜底是「{dish}」（{q.get("source","")}）。玩家猜了{guess_count}次后放弃了。请公布答案并说一句有趣的话。',
            temperature=0.9
        )
        feedback = feedback.strip().strip('"').strip("'").strip('\u201c').strip('\u201d')
    except:
        feedback = f'答案是「{dish}」！没关系，下次继续努力！'

    new_achievements = check_achievements(stats)

    is_last = q_idx >= 4
    if not is_last:
        sess["current_q"] += 1
        sess["guess_history"] = []
        sess["guess_count"] = 0
        sess["start_time"] = time.time()

    return jsonify({
        "result": result, "feedback": feedback,
        "current_score": sess["total_score"], "streak": 0,
        "new_achievements": new_achievements, "is_last": is_last,
    })

@app.route('/api/game/finish', methods=['POST'])
def game_finish():
    data = request.get_json() or {}
    session_id = data.get("session_id")
    if not session_id or session_id not in sessions:
        return jsonify({"error": "会话不存在"}), 400

    sess = sessions[session_id]
    stats = get_or_create_stats(session_id)

    stats["games_completed"] += 1
    stats["best_score"] = max(stats["best_score"], sess["total_score"])
    stats["max_streak"] = max(stats["max_streak"], sess["max_streak"])

    # 完美通关
    correct_count = len([r for r in sess["results"] if r.get("is_correct")])
    if correct_count == 5:
        stats["perfect_games"] += 1
        if correct_count == 5 and all(r.get("guess_count", 99) == 1 for r in sess["results"]):
            stats["perfect_all_one"] += 1

    # 平均猜测次数
    if correct_count == 5:
        total_guesses = sum(r.get("guess_count", 1) for r in sess["results"])
        avg = total_guesses / 5
        if avg <= 3: stats["avg_guesses_le3"] += 1
        if avg <= 2: stats["avg_guesses_le2"] += 1

    # 高效通关
    total_all_guesses = sess["total_guesses_this_game"]
    if correct_count == 5 and total_all_guesses <= 8:
        stats["min_guess_game"] += 1
    if correct_count == 5 and total_all_guesses <= 5:
        stats["min_guess_game_5"] += 1

    # 不放弃
    if not sess["skipped"]:
        stats["no_skip_game"] += 1
        stats["never_give_up_streak"] += 1
    else:
        stats["never_give_up_streak"] = 0

    # 逆风翻盘
    if sess.get("first_q_gave_up") and correct_count == 4:
        stats["comeback_win"] += 1

    # 险胜
    if 100 <= sess["total_score"] <= 150:
        stats["low_score_win"] += 1

    # 时间成就
    hour = datetime.now().hour
    if 0 <= hour < 5:
        stats["midnight_play"] += 1
    elif 5 <= hour < 7:
        stats["early_bird_play"] += 1
    if datetime.now().weekday() >= 5:
        stats["weekend_play"] += 1

    # 最后一题猜对
    if len(sess["results"]) == 5 and sess["results"][4].get("is_correct"):
        stats["last_second"] += 1

    new_achievements = check_achievements(stats)

    del sessions[session_id]

    return jsonify({
        "total_score": sess["total_score"],
        "correct_count": correct_count,
        "max_streak": sess["max_streak"],
        "results": sess["results"],
        "new_achievements": new_achievements,
        "stats": {
            "total_correct": stats["total_correct"],
            "games_completed": stats["games_completed"],
            "best_score": stats["best_score"],
            "achievements_count": len(stats["achievements_unlocked"]),
            "achievements_total": len(ACHIEVEMENTS_DEF),
        }
    })

@app.route('/api/achievements', methods=['GET'])
def achievements_list():
    session_id = request.args.get("session_id", "")
    stats = get_or_create_stats(session_id)
    unlocked = stats["achievements_unlocked"]
    result = []
    for ach in ACHIEVEMENTS_DEF:
        item = dict(ach)
        item["unlocked"] = ach["id"] in unlocked
        item["color"] = RARITY_COLORS.get(ach["rarity"], "#8C7B72")
        result.append(item)
    return jsonify({"achievements": result, "unlocked_count": len(unlocked), "total_count": len(ACHIEVEMENTS_DEF)})

@app.route('/api/stats', methods=['GET'])
def user_stats_api():
    session_id = request.args.get("session_id", "")
    stats = get_or_create_stats(session_id)
    return jsonify({
        "total_correct": stats["total_correct"],
        "games_completed": stats["games_completed"],
        "best_score": stats["best_score"],
        "max_streak": stats["max_streak"],
        "one_shot_count": stats["one_shot_count"],
        "achievements_count": len(stats["achievements_unlocked"]),
        "achievements_total": len(ACHIEVEMENTS_DEF),
    })

if __name__ == '__main__':
    print('[INFO] 味蕾大冒险（盲猜模式）Flask 后端启动中...')
    print('[INFO] 访问 http://localhost:8080/')
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
