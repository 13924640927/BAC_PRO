# tools/insert_streak_raw.py
import re
import sys
import pymysql

RUN_ID = "STREAK_1B_001"
CHECKPOINT_TAG = "@ checkpoint shoes_done=1,000,000,000/1,000,000,000"

RAW_TEXT = r"""[@ checkpoint shoes_done=1,000,000,000/1,000,000,000]
raw B/P/T: 37,609,479,916 / 36,596,463,926 / 7,803,707,648
censored streaks: 1,000,000,000  censored_hands B/P: 1,022,815,024 / 977,857,974
post-censored B/P (raw - censored_last_streak_hands): 36,586,664,892 / 35,618,605,952

VALID B streak dist (eq & ge, show len<= 30):
  len= 1: eq=9,150,773,532  ge=18,299,257,921
  len= 2: eq=4,575,681,268  ge=9,148,484,389
  len= 3: eq=2,287,560,290  ge=4,572,803,121
  len= 4: eq=1,143,473,444  ge=2,285,242,831
  len= 5: eq=571,434,428  ge=1,141,769,387
  len= 6: eq=285,495,502  ge=570,334,959
  len= 7: eq=142,619,872  ge=284,839,457
  len= 8: eq=71,216,748  ge=142,219,585
  len= 9: eq=35,566,166  ge=71,002,837
  len=10: eq=17,753,724  ge=35,436,671
  len=11: eq=8,863,328  ge=17,682,947
  len=12: eq=4,422,375  ge=8,819,619
  len=13: eq=2,205,671  ge=4,397,244
  len=14: eq=1,097,288  ge=2,191,573
  len=15: eq=548,222  ge=1,094,285
  len=16: eq=273,735  ge=546,063
  len=17: eq=136,490  ge=272,328
  len=18: eq=68,255  ge=135,838
  len=19: eq=34,074  ge=67,583
  len=20: eq=16,843  ge=33,509
  len=21: eq=8,453  ge=16,666
  len=22: eq=4,211  ge=8,213
  len=23: eq=2,027  ge=4,002
  len=24: eq=1,010  ge=1,975
  len=25: eq=501  ge=965
  len=26: eq=233  ge=464
  len=27: eq=104  ge=231
  len=28: eq=72  ge=127
  len=29: eq=27  ge=55
  len=30: eq=19  ge=28

CENSORED B streak dist (eq & ge, show len<= 30):
  len= 1: eq=248,755,082  ge=504,409,802
  len= 2: eq=126,074,239  ge=255,654,720
  len= 3: eq=63,907,066  ge=129,580,481
  len= 4: eq=32,391,008  ge=65,673,415
  len= 5: eq=16,410,918  ge=33,282,407
  len= 6: eq=8,320,158  ge=16,871,489
  len= 7: eq=4,216,181  ge=8,551,331
  len= 8: eq=2,136,732  ge=4,335,150
  len= 9: eq=1,085,381  ge=2,198,418
  len=10: eq=548,193  ge=1,113,037
  len=11: eq=278,524  ge=564,844
  len=12: eq=141,225  ge=286,320
  len=13: eq=71,701  ge=145,095
  len=14: eq=36,075  ge=73,394
  len=15: eq=18,471  ge=37,319
  len=16: eq=9,327  ge=18,848
  len=17: eq=4,763  ge=9,521
  len=18: eq=2,444  ge=4,758
  len=19: eq=1,168  ge=2,314
  len=20: eq=552  ge=1,146
  len=21: eq=272  ge=594
  len=22: eq=171  ge=322
  len=23: eq=79  ge=151
  len=24: eq=33  ge=72
  len=25: eq=19  ge=39
  len=26: eq=12  ge=20
  len=27: eq=4  ge=8
  len=28: eq=1  ge=4
  len=29: eq=2  ge=3
  len=30: eq=0  ge=1

VALID P streak dist (eq & ge, show len<= 30):
  len= 1: eq=9,397,211,361  ge=18,296,831,280
  len= 2: eq=4,571,621,860  ge=8,899,619,919
  len= 3: eq=2,223,689,471  ge=4,327,998,059
  len= 4: eq=1,081,325,563  ge=2,104,308,588
  len= 5: eq=525,772,683  ge=1,022,983,025
  len= 6: eq=255,627,806  ge=497,210,342
  len= 7: eq=124,252,001  ge=241,582,536
  len= 8: eq=60,353,993  ge=117,330,535
  len= 9: eq=29,304,512  ge=56,976,542
  len=10: eq=14,237,201  ge=27,672,030
  len=11: eq=6,915,407  ge=13,434,829
  len=12: eq=3,356,857  ge=6,519,422
  len=13: eq=1,628,821  ge=3,162,565
  len=14: eq=791,253  ge=1,533,744
  len=15: eq=381,934  ge=742,491
  len=16: eq=185,590  ge=360,557
  len=17: eq=89,975  ge=174,967
  len=18: eq=43,754  ge=84,992
  len=19: eq=21,391  ge=41,238
  len=20: eq=10,265  ge=19,847
  len=21: eq=4,992  ge=9,582
  len=22: eq=2,358  ge=4,590
  len=23: eq=1,163  ge=2,232
  len=24: eq=559  ge=1,069
  len=25: eq=280  ge=510
  len=26: eq=110  ge=230
  len=27: eq=59  ge=120
  len=28: eq=29  ge=61
  len=29: eq=22  ge=32
  len=30: eq=5  ge=10

CENSORED P streak dist (eq & ge, show len<= 30):
  len= 1: eq=251,173,386  ge=495,590,198
  len= 2: eq=123,875,638  ge=244,416,812
  len= 3: eq=61,092,489  ge=120,541,174
  len= 4: eq=30,123,330  ge=59,448,685
  len= 5: eq=14,862,847  ge=29,325,355
  len= 6: eq=7,328,800  ge=14,462,508
  len= 7: eq=3,617,578  ge=7,133,708
  len= 8: eq=1,781,475  ge=3,516,130
  len= 9: eq=879,161  ge=1,734,655
  len=10: eq=433,426  ge=855,494
  len=11: eq=213,766  ge=422,068
  len=12: eq=105,772  ge=208,302
  len=13: eq=51,806  ge=102,530
  len=14: eq=25,748  ge=50,724
  len=15: eq=12,507  ge=24,976
  len=16: eq=6,226  ge=12,469
  len=17: eq=3,168  ge=6,243
  len=18: eq=1,588  ge=3,075
  len=19: eq=784  ge=1,487
  len=20: eq=349  ge=703
  len=21: eq=186  ge=354
  len=22: eq=87  ge=168
  len=23: eq=38  ge=81
  len=24: eq=26  ge=43
  len=25: eq=8  ge=17
  len=26: eq=7  ge=9
  len=27: eq=0  ge=2
  len=28: eq=0  ge=2
  len=29: eq=2  ge=2

=== FINAL SUMMARY ===
run_id=STREAK_1B_001
shoes_done=1,000,000,000 / shoes_target=1,000,000,000 master_seed=17940980040936673589
raw B/P/T: 37,609,479,916 / 36,596,463,926 / 7,803,707,648
censored streaks: 1,000,000,000  censored_hands B/P: 1,022,815,024 / 977,857,974
post-censored B/P: 36,586,664,892 / 35,618,605,952
[1]    done       nohup python3 -m pipeline.streak_distribution_run --shoes 1000000000  1000000"""
# ↑ 把你那整段输出原文，完整粘贴进来替换 PASTE_HERE（不要删任何行）

def num(s: str):
    return int(s.replace(",", ""))

def pick(pattern, text, group=1, default=None):
    m = re.search(pattern, text)
    return m.group(group) if m else default

def main():
    shoes_done = num(pick(r"shoes_done=([\d,]+)\s*/\s*([\d,]+)", RAW_TEXT, 1) or "0")
    shoes_target = num(pick(r"shoes_done=([\d,]+)\s*/\s*([\d,]+)", RAW_TEXT, 2) or "0")
    master_seed = pick(r"master_seed=([0-9]+)", RAW_TEXT)  # very large -> store as string

    raw_b = num(pick(r"raw B/P/T:\s*([\d,]+)\s*/\s*([\d,]+)\s*/\s*([\d,]+)", RAW_TEXT, 1) or "0")
    raw_p = num(pick(r"raw B/P/T:\s*([\d,]+)\s*/\s*([\d,]+)\s*/\s*([\d,]+)", RAW_TEXT, 2) or "0")
    raw_t = num(pick(r"raw B/P/T:\s*([\d,]+)\s*/\s*([\d,]+)\s*/\s*([\d,]+)", RAW_TEXT, 3) or "0")

    censored_streaks = num(pick(r"censored streaks:\s*([\d,]+)", RAW_TEXT) or "0")
    censored_hands_b = num(pick(r"censored_hands B/P:\s*([\d,]+)\s*/\s*([\d,]+)", RAW_TEXT, 1) or "0")
    censored_hands_p = num(pick(r"censored_hands B/P:\s*([\d,]+)\s*/\s*([\d,]+)", RAW_TEXT, 2) or "0")

    post_censored_b = num(pick(r"post-censored B/P.*?:\s*([\d,]+)\s*/\s*([\d,]+)", RAW_TEXT, 1) or "0")
    post_censored_p = num(pick(r"post-censored B/P.*?:\s*([\d,]+)\s*/\s*([\d,]+)", RAW_TEXT, 2) or "0")

    conn = pymysql.connect(
        host="localhost",
        user="root",
        password="holybaby",
        database="BAC_PRO",
        charset="utf8mb4",
        autocommit=True,
    )

    sql = """
    INSERT INTO streak_run_raw
    (run_id, checkpoint_tag, shoes_done, shoes_target, master_seed,
     raw_b, raw_p, raw_t,
     censored_streaks, censored_hands_b, censored_hands_p,
     post_censored_b, post_censored_p,
     raw_text)
    VALUES
    (%s,%s,%s,%s,%s,
     %s,%s,%s,
     %s,%s,%s,
     %s,%s,
     %s)
    ON DUPLICATE KEY UPDATE
      shoes_done=VALUES(shoes_done),
      shoes_target=VALUES(shoes_target),
      master_seed=VALUES(master_seed),
      raw_b=VALUES(raw_b), raw_p=VALUES(raw_p), raw_t=VALUES(raw_t),
      censored_streaks=VALUES(censored_streaks),
      censored_hands_b=VALUES(censored_hands_b),
      censored_hands_p=VALUES(censored_hands_p),
      post_censored_b=VALUES(post_censored_b),
      post_censored_p=VALUES(post_censored_p),
      raw_text=VALUES(raw_text);
    """

    with conn.cursor() as cur:
        cur.execute(sql, (
            RUN_ID, CHECKPOINT_TAG, shoes_done, shoes_target, master_seed,
            raw_b, raw_p, raw_t,
            censored_streaks, censored_hands_b, censored_hands_p,
            post_censored_b, post_censored_p,
            RAW_TEXT
        ))

    print("OK: inserted/updated", RUN_ID, CHECKPOINT_TAG)

if __name__ == "__main__":
    main()