import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import json
import os

# ================= 设置页面配置 =================
st.set_page_config(page_title="加密货币事件合约模拟盘", layout="wide")

# ================= 登录拦截与多用户状态管理 =================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""

# 如果未登录，显示登录界面并停止运行后续代码
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🔐 加密货币交易模拟盘</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>请输入您的玩家昵称以建立专属独立账户</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        user_input = st.text_input("玩家昵称 (推荐使用英文或数字)", placeholder="例如: Alex888")
        if st.button("🚀 登入系统 / 创建账户", use_container_width=True):
            if user_input.strip() == "":
                st.error("⚠️ 昵称不能为空！")
            else:
                st.session_state.username = user_input.strip()
                st.session_state.logged_in = True
                # 确保进入时重新初始化对应用户的数据
                if 'initialized' in st.session_state:
                    del st.session_state['initialized']
                st.rerun()
    st.stop() # 停止执行下方的核心交易盘代码

# ================= 持久化存储配置 (多用户版) =================
DATA_DIR = "user_data"
# 自动创建存放玩家数据的文件夹
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def get_db_file():
    """获取当前玩家专属的本地存档路径"""
    return os.path.join(DATA_DIR, f"data_{st.session_state.username}.json")

def load_data():
    default_data = {
        "balance": 10000.0,
        "active_trades": [],
        "trade_history": []
    }
    db_file = get_db_file()
    if os.path.exists(db_file):
        try:
            with open(db_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for t in data.get("active_trades", []):
                    t["expiry_time"] = datetime.strptime(t["expiry_time"], "%Y-%m-%d %H:%M:%S")
                return data
        except Exception as e:
            st.error(f"读取玩家存档失败，错误: {e}")
            return default_data
    return default_data

def save_data():
    serializable_active = []
    for t in st.session_state.active_trades:
        t_copy = t.copy()
        if isinstance(t_copy["expiry_time"], datetime):
            t_copy["expiry_time"] = t_copy["expiry_time"].strftime("%Y-%m-%d %H:%M:%S")
        serializable_active.append(t_copy)

    data_to_save = {
        "balance": st.session_state.balance,
        "active_trades": serializable_active,
        "trade_history": st.session_state.trade_history
    }
    try:
        with open(get_db_file(), "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"数据保存失败: {e}")

# ================= 初始化 Session State =================
if 'initialized' not in st.session_state:
    saved_data = load_data()
    st.session_state.balance = saved_data["balance"]
    st.session_state.active_trades = saved_data["active_trades"]
    st.session_state.trade_history = saved_data["trade_history"]
    st.session_state.initialized = True

# ================= 常量与后台函数 =================
SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
TIMEFRAMES = {"5分钟": 5, "10分钟": 10, "30分钟": 30, "1小时": 60, "4小时": 240}
PAYOUT_RATIOS = {"80%": 0.80, "85%": 0.85}

def get_current_price(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        return float(requests.get(url, timeout=5).json()['price'])
    except: return None

def get_historical_price(symbol, expiry_time):
    try:
        timestamp_ms = int(expiry_time.replace(microsecond=0).timestamp() * 1000)
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1s&endTime={timestamp_ms}&limit=1"
        res = requests.get(url, timeout=5).json()
        if res and len(res) > 0: return float(res[0][4]) 
        return None
    except: return None

def get_klines(symbol, limit=100):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit={limit}"
        res = requests.get(url, timeout=5).json()
        df = pd.DataFrame(res, columns=['Open time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close time', 'Quote asset volume', 'Number of trades', 'Taker buy base asset volume', 'Taker buy quote asset volume', 'Ignore'])
        df['Open time'] = pd.to_datetime(df['Open time'], unit='ms') + timedelta(hours=8)
        for col in ['Open', 'High', 'Low', 'Close']: df[col] = df[col].astype(float)
        return df
    except: return pd.DataFrame()

def place_order(symbol, amount, timeframe_name, timeframe_mins, payout_ratio, direction, current_price):
    if amount <= 0: return st.sidebar.error("下单金额必须大于0")
    if amount > st.session_state.balance: return st.sidebar.error("余额不足！")

    st.session_state.balance -= amount
    expiry_time = datetime.now() + timedelta(minutes=timeframe_mins)
    order = {
        "id": int(time.time()), "symbol": symbol, "direction": direction,
        "strike_price": current_price, "amount": amount, "payout_ratio": payout_ratio,
        "order_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expiry_time": expiry_time, "status": "进行中"
    }
    st.session_state.active_trades.append(order)
    save_data()
    st.sidebar.success(f"成功下单：{symbol} {direction}，金额：{amount} USDT")

def settle_trades():
    now = datetime.now()
    remaining_trades = []
    has_changes = False

    for trade in st.session_state.active_trades:
        if now >= trade["expiry_time"]:
            settle_price = get_historical_price(SYMBOLS[trade["symbol"]], trade["expiry_time"])
            if not settle_price:
                remaining_trades.append(trade) 
                continue

            has_changes = True
            is_win = (trade["direction"] == "看涨" and settle_price > trade["strike_price"]) or \
                     (trade["direction"] == "看跌" and settle_price < trade["strike_price"])
            trade["settle_price"] = settle_price
            trade["status"] = "已结算"

            if is_win:
                profit = trade["amount"] * trade["payout_ratio"]
                st.session_state.balance += trade["amount"] + profit
                trade["result"] = f"盈利 +{profit:.2f} USDT"
                trade["pnl"] = profit
            else:
                trade["result"] = f"亏损 -{trade['amount']:.2f} USDT"
                trade["pnl"] = -trade["amount"]

            trade["expiry_time"] = trade["expiry_time"].strftime("%Y-%m-%d %H:%M:%S")
            st.session_state.trade_history.insert(0, trade)
        else:
            remaining_trades.append(trade)

    st.session_state.active_trades = remaining_trades
    if has_changes: save_data()

# ================= 盈亏与胜率统计计算 =================
total_pnl = 0.0
win_count = 0
total_settled = len(st.session_state.trade_history)

for t in st.session_state.trade_history:
    if "pnl" in t:
        total_pnl += t["pnl"]
        if t["pnl"] > 0: win_count += 1
    else:
        if "盈利" in t.get("result", ""):
            win_count += 1
            try: total_pnl += float(t["result"].split("+")[1].replace(" USDT", ""))
            except: pass
        elif "亏损" in t.get("result", ""):
            try: total_pnl -= float(t["result"].split("-")[1].replace(" USDT", ""))
            except: pass

win_rate = (win_count / total_settled * 100) if total_settled > 0 else 0.0

# ================= 主页面布局 =================
st.title("📈 加密货币事件合约模拟盘")

# 顶栏仪表盘与身份显示
col_info1, col_info2 = st.columns([4, 1])
with col_info1:
    st.markdown(f"**欢迎回来，<span style='color:#1E90FF;'>{st.session_state.username}</span>！**", unsafe_allow_html=True)
with col_info2:
    if st.button("🚪 退出账号", use_container_width=True):
        st.session_state.clear()
        st.rerun()

st.markdown("---")
col_metric1, col_metric2, col_metric3 = st.columns(3)
with col_metric1: st.markdown(f"### 💰 账户余额: **<span style='color:green;'>{st.session_state.balance:.2f} USDT</span>**", unsafe_allow_html=True)
with col_metric2:
    pnl_color = "green" if total_pnl >= 0 else "red"
    pnl_sign = "+" if total_pnl > 0 else ""
    st.markdown(f"### 📊 总盈亏: **<span style='color:{pnl_color};'>{pnl_sign}{total_pnl:.2f} USDT</span>**", unsafe_allow_html=True)
with col_metric3: st.markdown(f"### 🏆 历史胜率: **<span>{win_rate:.1f}%</span>** ({win_count}/{total_settled})", unsafe_allow_html=True)
st.markdown("---")

col1, col2 = st.columns([3, 1])

with col1:
    selected_asset = st.radio("选择交易币种", ["BTC", "ETH"], horizontal=True)
    symbol_code = SYMBOLS[selected_asset]
    current_price = get_current_price(symbol_code)
    df_klines = get_klines(symbol_code)

    if current_price: st.markdown(f"### {selected_asset}/USDT 最新指数价格: **{current_price}**")
    else: st.warning("网络加载中，请稍等...")

    if not df_klines.empty:
        fig = go.Figure(data=[go.Candlestick(x=df_klines['Open time'], open=df_klines['Open'], high=df_klines['High'], low=df_klines['Low'], close=df_klines['Close'], name="K线")])
        fig.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown("### ⚡ 交易面板")
    timeframe_label = st.selectbox("到期时间", list(TIMEFRAMES.keys()))
    payout_label = st.selectbox("奖金比率", list(PAYOUT_RATIOS.keys()))
    order_amount = st.number_input("下单金额 (USDT)", min_value=1.0, max_value=100000.0, value=5.0, step=10.0)
    st.markdown("<br>", unsafe_allow_html=True)
    
    col_up, col_down = st.columns(2)
    with col_up:
        if st.button("🟢 看涨 (Up)", use_container_width=True):
            if current_price: place_order(selected_asset, order_amount, timeframe_label, TIMEFRAMES[timeframe_label], PAYOUT_RATIOS[payout_label], "看涨", current_price)
            else: st.error("获取价格失败，请重试")
    with col_down:
        if st.button("🔴 看跌 (Down)", use_container_width=True):
            if current_price: place_order(selected_asset, order_amount, timeframe_label, TIMEFRAMES[timeframe_label], PAYOUT_RATIOS[payout_label], "看跌", current_price)
            else: st.error("获取价格失败，请重试")

    st.markdown("---")
    if st.button("🔄 刷新数据并检查到期合约", use_container_width=True):
        settle_trades()
        st.rerun()

    st.markdown("### ⚙️ 账户设置")
    with st.expander("管理与重置", expanded=False):
        new_balance_input = st.number_input("设置初始本金 (USDT)", min_value=0.0, value=10000.0, step=100.0)
        if st.button("⚠️ 修改账户本金", use_container_width=True):
            st.session_state.balance = new_balance_input
            st.session_state.active_trades = [] 
            save_data()
            st.success(f"本金已修改为 {new_balance_input} USDT，历史记录已保留！")
            st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ 清空历史交易数据", use_container_width=True):
            st.session_state.trade_history = []
            save_data()
            st.success("历史交易记录已清空！")
            st.rerun()

st.markdown("---")
st.markdown("### 📋 交易记录")
tab1, tab2 = st.tabs(["当前持仓 (未结算)", "历史记录 (已结算)"])

with tab1:
    if st.session_state.active_trades:
        df_active = pd.DataFrame(st.session_state.active_trades)
        df_active_show = df_active.copy()
        df_active_show['expiry_time'] = df_active_show['expiry_time'].apply(lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if isinstance(x, datetime) else x)
        df_display = df_active_show[["symbol", "direction", "strike_price", "amount", "payout_ratio", "order_time", "expiry_time"]].rename(columns={"symbol": "币种", "direction": "方向", "strike_price": "开仓价格", "amount": "下单金额", "payout_ratio": "奖金比率", "order_time": "下单时间", "expiry_time": "到期时间"})
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else: st.info("当前没有活跃订单。")

with tab2:
    if st.session_state.trade_history:
        df_history = pd.DataFrame(st.session_state.trade_history)
        df_display_hist = df_history[["symbol", "direction", "strike_price", "settle_price", "amount", "order_time", "expiry_time", "result"]].rename(columns={"symbol": "币种", "direction": "方向", "strike_price": "开仓价格", "settle_price": "结算价格", "amount": "下单金额", "order_time": "下单时间", "expiry_time": "到期时间", "result": "盈亏结果"})
        def color_profit_loss(val): return f"color: {'green' if '盈利' in val else 'red' if '亏损' in val else 'black'}"
        st.dataframe(df_display_hist.style.map(color_profit_loss, subset=['盈亏结果']), use_container_width=True, hide_index=True)
    else: st.info("暂无历史交易记录。")
