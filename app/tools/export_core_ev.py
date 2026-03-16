import pandas as pd
import pymysql
import os

def export_data():
    try:
        # 请确保这里的 password 是你本地 MySQL 的密码
        conn = pymysql.connect(
            host="localhost", 
            user="root", 
            password="holybaby", 
            database="BAC_PRO"
        )
        print("正在从 MySQL 提取核心 EV 数据...")
        
        # 提取前 5000 条最常出现的状态
        query = "SELECT * FROM premax_state_ev ORDER BY n_ge DESC LIMIT 5000"
        df = pd.read_sql(query, conn)
        
        # 保存压缩文件
        output_path = "data/premax_summary.csv.gz"
        df.to_csv(output_path, index=False, compression='gzip')
        print(f"✅ 成功导出 {len(df)} 条数据至 {output_path}")
        conn.close()
    except Exception as e:
        print(f"❌ 导出失败: {e}")

if __name__ == "__main__":
    export_data()
