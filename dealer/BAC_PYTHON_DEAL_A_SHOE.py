import random
import pymysql

# BaccaratGame 类，用于生成 Scorecard
class BaccaratGame:
    suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    rank_values = {
        '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 0, 'J': 0, 'Q': 0, 'K': 0, 'A': 1
    }

    def __init__(self):
        self.shoe_id = 1

    def create_deck(self):
        return [f'{rank} of {suit}' for suit in self.suits for rank in self.ranks]

    def create_shoe(self):
        return [card for _ in range(8) for card in self.create_deck()]

    def shuffle_shoe(self, shoe):
        random.shuffle(shoe)
        return shoe

    def player_draw(self, player_value):
        return player_value <= 5

    def banker_draw(self, banker_value, player_third_card):
        if banker_value <= 2:
            return True
        if banker_value < 6 and (player_third_card is None):
            return True
        elif banker_value == 3 and (player_third_card is None or player_third_card != 8):
            return True
        elif banker_value == 4 and player_third_card is not None and 2 <= player_third_card <= 7:
            return True
        elif banker_value == 5 and player_third_card is not None and 4 <= player_third_card <= 7:
            return True
        elif banker_value == 6 and player_third_card is not None and player_third_card in [6, 7]:
            return True
        return False

    def calculate_hand_value(self, cards):
        return sum(self.rank_values[card.split()[0]] for card in cards) % 10

    def deal_cards(self, shoe):
        result_list = []
        while len(shoe) >= 14:
            # ✅ 正确交替发牌：闲-庄-闲-庄
            player_cards = [shoe.pop(0)]
            banker_cards = [shoe.pop(0)]
            player_cards.append(shoe.pop(0))
            banker_cards.append(shoe.pop(0))

            banker_value = self.calculate_hand_value(banker_cards)
            player_value = self.calculate_hand_value(player_cards)

            # Natural 8/9 直接结算
            if player_value >= 8 or banker_value >= 8:
                result_list.append(self.determine_winner(banker_value, player_value))
                continue

            player_third_card = None

            # 闲家补牌
            if self.player_draw(player_value):
                player_third_card = shoe.pop(0)
                player_cards.append(player_third_card)
                player_value = self.calculate_hand_value(player_cards)

            # 庄家补牌
            if self.banker_draw(
                banker_value,
                self.rank_values[player_third_card.split()[0]] if player_third_card else None
            ):
                banker_cards.append(shoe.pop(0))
                banker_value = self.calculate_hand_value(banker_cards)

            result_list.append(self.determine_winner(banker_value, player_value))

        return result_list


    def determine_winner(self, banker_value, player_value):
        return 1 if banker_value > player_value else -1 if banker_value < player_value else 0

    def generate_scorecard(self, v_list):
        scorecard = []
        v_list = [v for v in v_list if v != 0]
        if not v_list:
            return scorecard
        current_value = v_list[0]
        current_count = 1

        for v in v_list[1:]:
            if v == current_value:
                current_count += 1
            else:
                scorecard.append(min(max(current_count, 1), 15))
                current_value = v
                current_count = 1
        scorecard.append(min(max(current_count, 1), 15))
        return scorecard


# MySQL 数据库配置
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'holybaby',
    'database': 'PY_BAC',
    'charset': 'utf8mb4'
}

# 插入汇总数据到 MySQL 数据库
def insert_bpt_into_db(shoe, b, p, t):
    """
    将 BPT_SUM 数据插入到 MySQL 数据库，包含 shoe 总数
    """
    connection = pymysql.connect(**db_config)
    try:
        with connection.cursor() as cursor:
            # 调用存储过程，将 shoe 总数和结果插入到数据库
            cursor.callproc(
                'INSERT_INTO_BAC_BPT_POSSIBILITIES',
                (shoe, b, p, t)
            )
            connection.commit()  # 提交事务
    finally:
        connection.close()


# Baccarat BPT 验证块
def summarize_results(result_list):
    summary = {-1: 0, 0: 0, 1: 0}
    for num in result_list:
        if num in summary:
            summary[num] += 1
    return summary

def merge_summaries(summary1, summary2):
    return {
        -1: summary1.get(-1, 0) + summary2.get(-1, 0),  # P
        0: summary1.get(0, 0) + summary2.get(0, 0),    # T
        1: summary1.get(1, 0) + summary2.get(1, 0),    # B
    }
def calculate_percentage(summary):
    """
    根据当前 ScorecardProcessor 数据，计算 SUM 和百分比
    """

    total = sum(summary.values())

    # 计算百分比
    percentages = {k: (v / total) * 100 if total > 0 else 0 for k, v in summary.items()}
    return percentages

def bpt_verify_process(total_shoes):
    """
    处理所有鞋的发牌并统计总汇总
    """
    BPT_SUM = {-1: 0, 0: 0, 1: 0}
    game = BaccaratGame()

    for shoe_id in range(1, total_shoes + 1):
        shoe = game.create_shoe()
        shoe = game.shuffle_shoe(shoe)
        results = game.deal_cards(shoe)
        BPT = summarize_results(results)
        BPT_SUM = merge_summaries(BPT_SUM, BPT)

        if shoe_id % 1000 == 0:
            print(f" SUM after {shoe_id} shoes: {BPT_SUM}")
            print(f" {calculate_percentage(BPT_SUM)}")
    # 将最终汇总结果写入数据库，包括 total_shoes 总数
    b, p, t = BPT_SUM[1], BPT_SUM[-1], BPT_SUM[0]
    print(f"Final SUM after {total_shoes} shoes: {BPT_SUM}")
    #insert_bpt_into_db(total_shoes, b, p, t)


# 运行 BPT 验证
bpt_verify_process(1000000000)  # 示例运行 10,000 双鞋
