import streamlit as st
import pandas as pd
import os

# 1. 页面配置与 Logo
st.set_page_config(page_title="BAC_PRO 策略看板", layout="wide", page_icon="🃏")

# 加载你的个人 Logo (ME.PNG)
logo_path = "app/PIC/ME.PNG"
if os.path.exists(logo_path):
    st.sidebar.image(logo_path, width=200)

# 2. 数据加载
@st.cache_data
def load_data():
    csv_path = "data/premax_summary.csv.gz"
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path)
    return None

df_ev = load_data()

# 3. Session State 初始化 (存储路单)
if 'road_history' not in st.session_state:
    st.session_state.road_history = []

# 4. 侧边栏：操作与配置
st.sidebar.title("🎮 实战操作")

# 自定义红蓝按钮样式
st.markdown("""
<style>
    .stButton>button { width: 100%; height: 60px; font-size: 20px; font-weight: bold; border-radius: 10px; }
    div[data-testid="column"]:nth-of-type(1) button { background-color: #D32F2F; color: white; } /* Banker Red */
    div[data-testid="column"]:nth-of-type(2) button { background-color: #1976D2; color: white; } /* Player Blue */
</style>
""", unsafe_allow_html=True)

col_b, col_p = st.sidebar.columns(2)
if col_b.button("BANKER (B)"):
    st.session_state.road_history.append("B")
if col_p.button("PLAYER (P)"):
    st.session_state.road_history.append("P")

if st.sidebar.button("RESET SHOE", type="primary"):
    st.session_state.road_history = []
    st.rerun()

# 5. 核心逻辑：计算当前状态
def get_status(history):
    if not history: return None, 0
    last = history[-1]
    length = 0
    for s in reversed(history):
        if s == last: length += 1
        else: break
    return last, length

cur_side, cur_len = get_status(st.session_state.road_history)

# 6. 主界面展示
st.title("🃏 BAC_PRO 策略看板")
st.caption("基于 10亿次 模拟数据的实时策略建议 (Free Tier版)")

if cur_side:
    # 模仿 bac_pro.py 的指标展示
    st.subheader(f"当前路单：{' -> '.join(st.session_state.road_history[-10:])}")
    
    # 检索数据
    res = df_ev[(df_ev['cur_side'] == cur_side) & (df_ev['cur_len'] == cur_len)] if df_ev is not None else pd.DataFrame()
    
    c1, c2, c3 = st.columns(3)
    if not res.empty:
        row = res.iloc[0]
        edge = row['edge']
        # 自动变色：Edge 为正则绿，为负则红
        delta_val = f"{edge:.2%}"
        c1.metric("边缘优势 (Edge)", f"{edge:.4%}", delta=delta_val if edge > 0 else f"-{abs(edge):.2%}")
        c2.metric("建议动作", row['best_action'])
        c3.metric("样本量 (n_ge)", f"{int(row['n_ge']):,}")
        
        # 概率进度条
        st.write("### 概率分析")
        p_cut = row['p_cut']
        st.progress(p_cut, text=f"切牌概率 (Cut): {p_cut:.2%}")
        st.progress(1 - p_cut, text=f"连牌概率 (Continue): {1-p_cut:.2%}")
    else:
        st.info(f"💡 当前状态 ({cur_side}{cur_len}) 暂无核心 Edge 数据。")
else:
    st.info("👈 请在侧边栏点击 B 或 P 开始记录。")

# 7. 底层数据查看
with st.expander("查看 5000 条核心 Snapshot 备份"):
    st.dataframe(df_ev)