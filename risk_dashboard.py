"""
美股市場風險評估
"""
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import os
CSV_FILE = "risk_history.csv"

# ==================== 頁面設定 ====================
st.set_page_config(
    page_title="美股風險儀表板",
    page_icon="📊",
    layout="wide"
)

# ==================== 深色主題樣式 ====================
st.markdown("""
<style>
    .stApp { background-color: #0a0e17; }
    .stMetric { background: #0f1520 !important; border: 1px solid #1e2d45 !important; }
    h1, h2, h3, h4, p, div, span { color: #c8d8e8 !important; }
    section[data-testid="stSidebar"] { background-color: #0f1520; }
    .streamlit-expanderHeader { background-color: #0f1520 !important; color: #c8d8e8 !important; }
    hr { border-color: #1e2d45 !important; }
    
    /* 手機平板響應式 */
    @media (max-width: 768px) {
        .block-container { padding: 0.5rem !important; }
        div[data-testid="stColumn"] { min-width: 100% !important; margin-bottom: 8px; }
        div[data-testid="stVerticalBlock"] { gap: 0.3rem !important; }
        .stSubheader { font-size: 0.9rem !important; }
        div[data-testid="stMetricValue"] { font-size: 1.2rem !important; }
    }
</style>
""", unsafe_allow_html=True)

# ==================== 權重設定 ====================
WEIGHTS = {
    'vix': 0.25,
    'credit_spread': 0.25,
    'fear_greed': 0.20,
    'dollar': 0.15,
    'usd_jpy': 0.15,
}

# ==================== 數據獲取函數 ====================
@st.cache_data(ttl=900)
def get_vix_data(period="1y"):
    try:
        vix = yf.download("^VIX", period=period, progress=False)
        if len(vix) > 0 and 'Close' in vix.columns:
            return vix['Close']
        return pd.Series([])
    except:
        return pd.Series([])

@st.cache_data(ttl=900)
def get_fear_greed_index():
    """從 feargreedmeter.com 獲取 CNN恐懼/貪婪指數"""
    try:
        import re
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        response = requests.get("https://feargreedmeter.com/", headers=headers, timeout=10)
        if response.status_code == 200:
            # 嘗試多種匹配方式
            match = re.search(r'>(\d+)<.*?fear.*?greed', response.text, re.IGNORECASE)
            if match:
                return int(match.group(1))
            match = re.search(r'fear.*?greed.*?>(\d+)<', response.text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None
    except:
        return None

@st.cache_data(ttl=3600)
def get_fear_greed_history():
    """從 feargreedmeter.com 獲取CNN恐懼/貪婪指數歷史數據"""
    try:
        import json
        import re
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        response = requests.get("https://feargreedmeter.com/", headers=headers, timeout=10)
        if response.status_code == 200:
            # 解析 __NEXT_DATA__ JSON
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', response.text)
            if match:
                data = json.loads(match.group(1))
                fgi = data['props']['pageProps']['data']['fgi']['latest']
                return {
                    'now': fgi.get('now'),
                    'yesterday': fgi.get('previous_close'),
                    'one_week_ago': fgi.get('one_week_ago'),
                    'one_month_ago': fgi.get('one_month_ago'),
                }
        return None
    except:
        return None

@st.cache_data(ttl=3600)
def get_credit_spread():
    """從 FRED 獲取信用利差 (BAMLH0A0HYM2) - 使用直接 HTTP 請求"""
    try:
        # 直接從 FRED API 獲取（無需 API key 的公開數據）
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"
        df = pd.read_csv(url)
        if len(df) > 0:
            latest = df.iloc[-1]
            return float(latest['BAMLH0A0HYM2'])
        return None
    except Exception as e:
        return None

@st.cache_data(ttl=3600)
def get_stock_data(symbol, period="1y"):
    try:
        data = yf.download(symbol, period=period, progress=False)
        if len(data) > 0 and 'Close' in data.columns:
            return data['Close']
        return pd.Series([])
    except:
        return pd.Series([])

@st.cache_data(ttl=3600)
def get_indicator_history(symbol, days=7):
    """獲取指標過去N天的歷史數據"""
    try:
        data = yf.download(symbol, period=f"{days}d", progress=False)
        if len(data) > 0:
            # 處理 MultiIndex columns
            if isinstance(data.columns, pd.MultiIndex):
                # 取得 Close 欄位（可能是 ('Close', symbol) 格式）
                close = data['Close'] if 'Close' in data.columns.get_level_values(0) else data.iloc[:, 0]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]  # 取第一個 Close 欄位
                return close
            elif 'Close' in data.columns:
                return data['Close']
            return data.iloc[:, 0]  # fallback: 取第一欄
        return pd.Series([])
    except:
        return pd.Series([])

def get_sparkline_data():
    """獲取所有指標的7天歷史數據用於趨勢圖"""
    vix_7d = get_indicator_history("^VIX", 7)
    dxy_7d = get_indicator_history("DX-Y.NYB", 7)
    jpy_7d = get_indicator_history("JPY=X", 7)
    credit_7d = get_credit_spread_history(7)
    fear_greed_history = get_fear_greed_history()
    
    # 將 fear_greed 轉為 Series（4個點：1月前、1週前、昨日、今日）
    import pandas as pd
    fear_greed_series = None
    if fear_greed_history:
        values = [
            fear_greed_history.get('one_month_ago'),
            fear_greed_history.get('one_week_ago'),
            fear_greed_history.get('yesterday'),
            fear_greed_history.get('now'),
        ]
        # 只保留有效的值
        values = [v for v in values if v is not None]
        if values:
            fear_greed_series = pd.Series(values)
    
    return {
        'vix': vix_7d,
        'dxy': dxy_7d,
        'usd_jpy': jpy_7d,
        'credit': credit_7d,
        'fear_greed': fear_greed_series,
    }

def calculate_trend(current, week_ago):
    """計算趨勢方向：up=紅色向上, down/flat=白色"""
    if current is None or week_ago is None or week_ago == 0:
        return None, "neutral"
    
    change_pct = ((current - week_ago) / week_ago) * 100
    
    # 超過 2% 視為明顯趨勢
    if change_pct > 2:
        return change_pct, "up"
    elif change_pct < -2:
        return change_pct, "down"
    else:
        return change_pct, "neutral"

@st.cache_data(ttl=3600)
def get_credit_spread_history(days=7):
    """獲取信用利差歷史數據"""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"
        df = pd.read_csv(url)
        if len(df) > days:
            # 取得最近 days 天的數據，返回 pandas Series
            return df.iloc[-days:]['BAMLH0A0HYM2'].reset_index(drop=True)
        return pd.Series([])
    except:
        return pd.Series([])

# ==================== 風險評分計算 ====================
def calculate_risk_score(vix, credit_spread, fear_greed, dxy, usd_jpy):
    vix_score = min(100, max(0, (vix / 40) * 100)) if vix else 50
    spread_score = min(100, max(0, (credit_spread / 10) * 100)) if credit_spread else 50
    fear_greed_score = fear_greed if fear_greed else 50
    dxy_score = min(100, max(0, ((dxy - 90) / 30) * 100)) if dxy else 50
    jpy_score = min(100, max(0, ((usd_jpy - 130) / 40) * 100)) if usd_jpy else 50
    
    total = (vix_score * WEIGHTS['vix'] + spread_score * WEIGHTS['credit_spread'] + 
             fear_greed_score * WEIGHTS['fear_greed'] + 
             (dxy_score + jpy_score) * (WEIGHTS['dollar'] + WEIGHTS['usd_jpy']) / 2)
    
    return {'total': total, 'vix': vix_score, 'credit_spread': spread_score, 
            'fear_greed': fear_greed_score, 'dollar': dxy_score, 'usd_jpy': jpy_score,
            'raw_vix': vix or 20, 'raw_spread': credit_spread or 3, 
            'raw_fear_greed': fear_greed or 50, 'raw_dxy': dxy or 100, 'raw_jpy': usd_jpy or 150}

@st.cache_data(ttl=3600)
def get_risk_index_history(period="1y"):
    """計算綜合風險指數歷史"""
    try:
        # 獲取所有需要的數據
        vix_data = yf.download("^VIX", period=period, progress=False)
        dxy_data = yf.download("DX-Y.NYB", period=period, progress=False)  # 美元指數
        jpy_data = yf.download("JPY=X", period=period, progress=False)
        
        # 處理 MultiIndex
        def get_close(data):
            if len(data) == 0:
                return pd.Series([])
            if isinstance(data.columns, pd.MultiIndex):
                close = data['Close'] if 'Close' in data.columns.get_level_values(0) else data.iloc[:, 0]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                return close
            elif 'Close' in data.columns:
                return data['Close']
            return data.iloc[:, 0]
        
        vix = get_close(vix_data)
        dxy = get_close(dxy_data)
        jpy = get_close(jpy_data)
        
        # 信用利差
        try:
            credit_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"
            credit_df = pd.read_csv(credit_url)
            credit_df['DATE'] = pd.to_datetime(credit_df['DATE'])
            credit_df = credit_df.set_index('DATE')
        except:
            credit_df = pd.DataFrame()
        
        # 對齊數據
        common_idx = vix.index.intersection(dxy.index).intersection(jpy.index)
        
        risk_history = []
        dates = []
        
        for date in common_idx:
            # 取得當天數據
            v = float(vix.loc[date]) if date in vix.index else None
            d = float(dxy.loc[date]) if date in dxy.index else None
            j = float(jpy.loc[date]) if date in jpy.index else None
            
            # 信用利差
            c = None
            if len(credit_df) > 0 and date in credit_df.index:
                c = float(credit_df.loc[date, 'BAMLH0A0HYM2'])
            
            # CNN恐懼/貪婪用50（無法取得歷史）
            fg = 50
            
            if v and d and j:
                risk = calculate_risk_score(v, c, fg, d, j)
                risk_history.append(risk['total'])
                dates.append(date)
        
        return pd.Series(risk_history, index=dates)
    except Exception as e:
        st.error(f"計算風險指數歷史失敗: {e}")
        return pd.Series([])

# ==================== 指標說明 ====================
INDICATOR_DESC = {
    'vix': '市場對未來30天波動的預期',
    'fear_greed': '綜合7項指標的市場情緒指數',
    'credit': '高收益債 vs 公債利差，領先指標',
    'dxy': '美元對一籃子貨幣強弱，全球流動性',
    'usd_jpy': '日幣貶值時套利交易累積，升值時可能引發平倉潮'
}

# ==================== 主程式 ====================
def main():
    st.title("美股市場風險評估")
    st.markdown(f"**LAST UPDATE** - {datetime.now().strftime('%Y 年 %m 月 %d 日 %H:%M')}")
    st.markdown("---")
    
    # 側邊欄
    with st.sidebar:
        st.header("⚙️ 設定")
        
        st.subheader("權重分配")
        st.write(f"- VIX: {WEIGHTS['vix']*100:.0f}%")
        st.write(f"- CNN恐懼/貪婪: {WEIGHTS['fear_greed']*100:.0f}%")
        st.write(f"- 信用利差: {WEIGHTS['credit_spread']*100:.0f}%")
        st.write(f"- 美元指數: {WEIGHTS['dollar']*100:.0f}%")
        st.write(f"- USD/JPY: {WEIGHTS['usd_jpy']*100:.0f}%")
        
        # 評分標準
        with st.expander("📋 評分標準", expanded=False):
            st.write("**VIX** 🟢 <15 | 🟡 15-25 | 🟠 25-35 | 🔴 >35")
            st.write("**CNN恐懼/貪婪** 🟢 0-25 | 🟡 25-45 | ⚪ 45-55 | 🟠 55-75 | 🔴 75-100")
            st.write("**信用利差** 🟢 <2% | 🟡 2-3% | 🟠 3-4% | 🔴 >4%")
            st.write("**美元指數** 🟢 <100 | 🟡 100-105 | 🟠 105-110 | 🔴 >110")
            st.write("**USD/JPY** 🟢 <130 | 🟡 130-145 | 🟠 145-160 | 🔴 >160")
        
        # 隱藏股票代碼和時間範圍（使用預設值）
        stock_symbol = "TSM"  # 隱藏輸入
        period = "6mo"  # 隱藏選擇
        
        if st.button("🔄 刷新數據"):
            st.cache_data.clear()
            st.rerun()
    
    # 載入數據
    with st.spinner("正在載入市場數據..."):
        vix_data = get_vix_data(period)
        stock_data = get_stock_data(stock_symbol, period)
        fear_greed = get_fear_greed_index()
        credit_spread = get_credit_spread()
        
        latest_vix = float(vix_data.iloc[-1]) if len(vix_data) > 0 else 20.0
        
        # 獲取美元指數和 USD/JPY
        dxy_data = get_stock_data("DX-Y.NYB", period)  # 美元指數
        usdjpy_data = get_stock_data("JPY=X", period)  # USD/JPY
        
        latest_dxy = float(dxy_data.iloc[-1]) if len(dxy_data) > 0 else 102.0
        latest_usdjpy = float(usdjpy_data.iloc[-1]) if len(usdjpy_data) > 0 else 150.0
        
        # 獲取一週前的數據用於趨勢計算
        vix_week_ago = float(vix_data.iloc[0]) if len(vix_data) > 1 else None
        dxy_week_ago = float(dxy_data.iloc[0]) if len(dxy_data) > 1 else None
        usdjpy_week_ago = float(usdjpy_data.iloc[0]) if len(usdjpy_data) > 1 else None
        credit_history = get_credit_spread_history(7)
        credit_week_ago = float(credit_history.iloc[0]) if credit_history is not None and len(credit_history) > 1 else None
        
        # 使用真實數據，若獲取失敗則使用預設值
        fear_greed_value = fear_greed if fear_greed is not None else 50
        credit_spread_value = credit_spread if credit_spread is not None else 3.0
        
        # 計算趨勢
        trends = {
            'vix': calculate_trend(latest_vix, vix_week_ago),
            'dxy': calculate_trend(latest_dxy, dxy_week_ago),
            'usd_jpy': calculate_trend(latest_usdjpy, usdjpy_week_ago),
            'credit': calculate_trend(credit_spread_value, credit_week_ago),
            'fear_greed': (None, "neutral"),  # 無法取得歷史數據
        }
        
        risk = calculate_risk_score(latest_vix, credit_spread_value, fear_greed_value, latest_dxy, latest_usdjpy)
        
        # 儲存當天數據到 CSV
        save_today_data(latest_vix, fear_greed_value, credit_spread_value, latest_dxy, latest_usdjpy, risk['total'])
    
    # 風險等級
    if risk['total'] < 40:
        risk_color = "#00ff9d"
        risk_level = "🟢 低風險"
    elif risk['total'] < 60:
        risk_color = "#ffb347"
        risk_level = "🟡 中等風險"
    elif risk['total'] < 80:
        risk_color = "#ff8c00"
        risk_level = "🟠 高風險"
    else:
        risk_color = "#ff4d6d"
        risk_level = "🔴 極高風險"
    
    # 綜合風險分數
    col_gauge, col_alerts = st.columns([1, 1])
    
    with col_gauge:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=risk['total'],
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "綜合風險指數", 'font': {'size': 20, 'color': '#c8d8e8'}},
            number={'font': {'size': 40, 'color': risk_color}},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': '#4a6080'},
                'bar': {'color': risk_color},
                'steps': [
                    {'range': [0, 40], 'color': 'rgba(0,255,157,0.15)'},
                    {'range': [40, 60], 'color': 'rgba(255,179,71,0.15)'},
                    {'range': [60, 100], 'color': 'rgba(255,77,109,0.15)'},
                ],
            }
        ))
        fig_gauge.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', font_color='#c8d8e8')
        st.plotly_chart(fig_gauge, width='stretch')
        st.markdown(f"<div style='text-align:center; color:{risk_color}; font-size:18px;'>{risk_level}</div>", unsafe_allow_html=True)
    
    with col_alerts:
        st.markdown("### ⚡ 警示訊號")
        
        # VIX 警示（根據 OANDA 標準）
        vix = risk['raw_vix']
        if vix < 10:
            vix_msg = "⚠️ 極度樂觀信號 - 市場過度自信，警惕反轉"
            vix_color = "error"
        elif vix < 20:
            vix_msg = "✅ 正常/穩定 - 市場波動適中，適合風險資產"
            vix_color = "success"
        elif vix < 30:
            vix_msg = "⚠️ 稍微不穩定 - 警惕風險，持續觀察變化"
            vix_color = "warning"
        elif vix < 40:
            vix_msg = "🔶 高波動 - 市場恐懼上升，保守操作"
            vix_color = "error"
        else:
            vix_msg = "🔴 接近恐慌 - 歷史性危機信號，準備進場機會"
            vix_color = "error"
        
        if vix_color == "error":
            st.error(f"**VIX**: {vix:.2f} — {vix_msg}")
        elif vix_color == "warning":
            st.warning(f"**VIX**: {vix:.2f} — {vix_msg}")
        else:
            st.success(f"**VIX**: {vix:.2f} — {vix_msg}")
        
        # CNN 恐懼/貪腐警示（根據記憶標準）
        fgi = risk['raw_fear_greed']
        if fgi <= 25:
            fgi_msg = "🔴 極度恐懼 - 恐慌拋售，通常是逆勢進場機會"
            fgi_color = "error"
        elif fgi <= 45:
            fgi_msg = "⚠️ 恐懼 - 市場偏向恐懼，可逐步布局"
            fgi_color = "warning"
        elif fgi <= 55:
            fgi_msg = "⚪ 中性 - 沒有明顯傾向，股價可能被合理定價"
            fgi_color = "success"
        elif fgi <= 75:
            fgi_msg = "⚠️ 貪腐 - 市場偏向樂觀，留意回調風險"
            fgi_color = "warning"
        else:
            fgi_msg = "🔴 極度貪腐 - 市場過度樂觀，警惕反轉，可考慮離場"
            fgi_color = "error"
        
        if fgi_color == "error":
            st.error(f"**CNN恐懼/貪腐**: {fgi:.0f} — {fgi_msg}")
        elif fgi_color == "warning":
            st.warning(f"**CNN恐懼/貪腐**: {fgi:.0f} — {fgi_msg}")
        else:
            st.success(f"**CNN恐懼/貪腐**: {fgi:.0f} — {fgi_msg}")

        # CNN恐懼/貪婪
        if risk['raw_fear_greed'] >= 75:
            st.error(f"**CNN恐懼/貪婪**: {risk['raw_fear_greed']:.0f} — 市場過度貪婪")
        elif risk['raw_fear_greed'] <= 25:
            st.error(f"**CNN恐懼/貪婪**: {risk['raw_fear_greed']:.0f} — 市場極度恐懼")
        elif risk['raw_fear_greed'] <= 45:
            st.warning(f"**CNN恐懼/貪婪**: {risk['raw_fear_greed']:.0f} — 市場偏向恐懼")
        
        # 美元+日幣綜合（根據趨勢判斷）
        dxy_trend_val, dxy_trend = trends.get('dxy', (0, 'neutral'))
        jpy_trend_val, jpy_trend = trends.get('usd_jpy', (0, 'neutral'))
        
        # 趨勢箭頭
        dxy_arrow = "↗" if dxy_trend == "up" else "↘" if dxy_trend == "down" else "→"
        jpy_arrow = "↗" if jpy_trend == "up" else "↘" if jpy_trend == "down" else "→"
        
        # 判斷組合趨勢
        if dxy_trend == "up" and jpy_trend == "down":
            # DXY 上漲 + USD/JPY 下跌 = 日圓升值 + 美元強 = 壓力最大
            scenario_name = "🔴 全球避險 + 日圓套利同時平倉"
            st.error(f"**美元+日幣**: DXY {risk['raw_dxy']:.2f} {dxy_arrow} + USD/JPY {risk['raw_jpy']:.2f} {jpy_arrow} — {scenario_name}，壓力最大")
        elif dxy_trend == "down" and jpy_trend == "down":
            # DXY 下跌 + USD/JPY 下跌 = 日圓升值 = 純日圓套利平倉
            scenario_name = "🟠 純粹日圓套利平倉"
            st.error(f"**美元+日幣**: DXY {risk['raw_dxy']:.2f} {dxy_arrow} + USD/JPY {risk['raw_jpy']:.2f} {jpy_arrow} — {scenario_name}驅動，針對性風險")
        elif dxy_trend == "up" and jpy_trend == "up":
            # 兩者同向上漲 = 美元全面強勢
            scenario_name = "🟡 美元全面強勢"
            st.warning(f"**美元+日幣**: DXY {risk['raw_dxy']:.2f} {dxy_arrow} + USD/JPY {risk['raw_jpy']:.2f} {jpy_arrow} — {scenario_name}，對新興市場和商品不利")
        else:
            # 中性或其他組合
            scenario_name = "🟢 趨勢不明顯"
            st.success(f"**美元+日幣**: DXY {risk['raw_dxy']:.2f} {dxy_arrow} + USD/JPY {risk['raw_jpy']:.2f} {jpy_arrow} — {scenario_name}或無趨勢")
        
        # 總體建議
        if risk['total'] < 40:
            st.success("**積極立場** - 市場風險偏低，可適度增加風險資產")
        elif risk['total'] < 60:
            st.warning("**謹慎立場** - 市場處於中性，保持觀望")
        elif risk['total'] < 80:
            st.error("**保守立場** - 市場風險偏高，建議降低曝險")
        else:
            st.error("**規避立場** - 市場風險極高，建議大幅降低股票曝險")
    
    st.markdown("---")
    
    # 獲取 sparkline 數據
    sparkline_data = get_sparkline_data()
    
    # 五個指標卡片
    col1, col2, col3, col4, col5 = st.columns(5)
    
    cols = [col1, col2, col3, col4, col5]
    indicators = [
        ('VIX 恐慌指數', risk['raw_vix'], risk['vix'], 'vix'),
        ('CNN恐懼/貪婪', risk['raw_fear_greed'], risk['fear_greed'], 'fear_greed'),
        ('信用利差 %', risk['raw_spread'], risk['credit_spread'], 'credit'),
        ('美元指數 DXY', risk['raw_dxy'], risk['dollar'], 'dxy'),
        ('USD/JPY', risk['raw_jpy'], risk['usd_jpy'], 'usd_jpy'),
    ]
    
    for i, (name, value, score, key) in enumerate(indicators):
        with cols[i]:
            # 燈號
            if key == 'vix':
                light = '🟢' if value < 15 else '🟡' if value < 25 else '🟠' if value < 35 else '🔴'
            elif key == 'fear_greed':
                light = '🟢' if value < 25 else '🟡' if value < 45 else '⚪' if value < 55 else '🟠' if value < 75 else '🔴'
            elif key == 'credit':
                light = '🟢' if value < 2 else '🟡' if value < 3 else '🟠' if value < 4 else '🔴'
            elif key == 'dxy':
                light = '🟢' if value < 100 else '🟡' if value < 105 else '🟠' if value < 110 else '🔴'
            else:
                light = '🟢' if value < 130 else '🟡' if value < 145 else '🟠' if value < 160 else '🔴'
            
            unit = '%' if key == 'credit' else ''
            st.metric(f"{light} {name}", f"{value:.2f}{unit}", delta=f"{score:.1f}分", delta_color="inverse")
            
            # Sparkline 趨勢圖
            trend_data = trends.get(key, (None, "neutral"))
            change_pct, trend_type = trend_data
            
            hist_data = sparkline_data.get(key)
            
            if hist_data is not None and len(hist_data) > 1:
                # 決定顏色：紅色=向上，白色=向下/中性
                if trend_type == "up":
                    line_color = "#ff4d6d"  # 紅色
                else:
                    line_color = "#8a9bb0"  # 白色/灰色
                
                # 轉為百分比變化（相對於第一天）
                y_values = [float(x) for x in hist_data.values.flatten()] if len(hist_data.shape) > 1 else [float(x) for x in hist_data.values]
                base_value = y_values[0]
                y_pct = [(v - base_value) / base_value * 100 for v in y_values]
                
                fig_spark = go.Figure()
                fig_spark.add_trace(go.Scatter(
                    x=list(range(len(y_pct))),
                    y=y_pct,
                    mode="lines",
                    line=dict(color=line_color, width=2),
                    fill='tozeroy',
                    fillcolor=f"rgba({int(line_color[1:3],16)},{int(line_color[3:5],16)},{int(line_color[5:7],16)},0.1)"
                ))
                fig_spark.update_layout(
                    height=60,
                    margin=dict(l=0, r=0, t=0, b=0),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(visible=False, showgrid=False),
                    yaxis=dict(visible=False, showgrid=False, range=[min(y_pct)-0.5, max(y_pct)+0.5]),
                    showlegend=False,
                    autosize=True,
                )
                st.plotly_chart(fig_spark, use_container_width=True, config={'displayModeBar': False})
            else:
                # 無數據時顯示文字
                st.markdown(f"<div style='color:#8a9bb0; font-size:11px; text-align:center;'>➖ 無趨勢</div>", unsafe_allow_html=True)
            
            st.caption(INDICATOR_DESC.get(key, ''))
    
    st.markdown("---")
    
    # 一週風險指數趨勢
    st.markdown("---")
    st.subheader("一週風險指數趨勢")
    
    try:
        csv_df = get_fear_greed_history_from_csv()
        
        if len(csv_df) > 0:
            today = datetime.now()
            week_ago = today - timedelta(days=7)
            recent_data = csv_df[csv_df.index >= week_ago]
            
            if len(recent_data) > 0:
                weekly_risk = []
                for idx, row in recent_data.iterrows():
                    risk = calculate_risk_score(
                        row.get('vix', 18), row.get('credit_spread', 3.0),
                        row.get('fear_greed', 50), row.get('dxy', 100),
                        row.get('usd_jpy', 150)
                    )
                    weekly_risk.append({'date': idx, 'risk_index': risk['total']})
                
                if weekly_risk:
                    weekly_df = pd.DataFrame(weekly_risk).set_index('date')
                    
                    fig_weekly = go.Figure()
                    fig_weekly.add_trace(go.Scatter(
                        x=weekly_df.index, y=weekly_df['risk_index'],
                        mode='lines+markers', name='風險指數',
                        line=dict(color='#00d4ff', width=3),
                        marker=dict(size=8, color='#00d4ff')
                    ))
                    
                    # 計算y軸範圍，讓波動更明顯
                    if len(weekly_df) > 1:
                        data_min = weekly_df['risk_index'].min()
                        data_max = weekly_df['risk_index'].max()
                        data_range = data_max - data_min
                        # 範圍至少拉開 20，才能看出變化
                        y_min = max(0, data_min - max(10, data_range * 0.5))
                        y_max = min(100, data_max + max(10, data_range * 0.5))
                    else:
                        y_min = 0
                        y_max = 100
                    
                    fig_weekly.update_layout(
                        xaxis=dict(title="日期", color='#c8d8e8'),
                        yaxis=dict(title="風險指數", range=[y_min, y_max], color='#c8d8e8', showgrid=True, gridcolor='#1e2d45'),
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        font_color='#c8d8e8', height=300,
                        margin=dict(l=20, r=20, t=20, b=20)
                    )
                    st.plotly_chart(fig_weekly, use_container_width=True)
                    
                    avg_week = weekly_df['risk_index'].mean()
                    max_week = weekly_df['risk_index'].max()
                    min_week = weekly_df['risk_index'].min()
                    st.markdown(f'''
                    <div style='text-align:center; color:#c8d8e8; font-size:13px;'>
                        <span>平均: {avg_week:.1f}</span> | 
                        <span>最高: {max_week:.1f}</span> | 
                        <span>最低: {min_week:.1f}</span>
                    </div>''', unsafe_allow_html=True)
                else:
                    st.info("一週內尚無完整數據")
            else:
                st.info("一週內尚無足夠數據，請持續記錄以建立歷史")
        else:
            st.info("尚無歷史數據，請先啟用 app 以建立記錄")
    except Exception as e:
        st.error(f"載入一週數據失敗: {e}")

    # 雷達圖 + 柱狀圖
    col_radar, col_bar = st.columns([1, 1])
    
    with col_radar:
        labels = ['VIX', '信用利差', 'CNN恐懼/貪婪', '美元指數', 'USD/JPY']
        values = [risk['vix'], risk['credit_spread'], risk['fear_greed'], risk['dollar'], risk['usd_jpy']]
        labels.append(labels[0])
        values.append(values[0])
        
        fig_radar = go.Figure(go.Scatterpolar(
            r=values, theta=labels, fill='toself',
            fillcolor='rgba(0,212,255,0.1)', line_color='#00d4ff'))
        fig_radar.update_layout(
            polar=dict(bgcolor='rgba(0,0,0,0)', 
                      radialaxis=dict(visible=True, range=[0, 100], color='#4a6080'),
                      angularaxis=dict(color='#c8d8e8', tickfont=dict(size=10, color='#c8d8e8'))),
            paper_bgcolor='rgba(0,0,0,0)', font_color='#c8d8e8', height=380
        )
        st.subheader("風險雷達圖")
        st.plotly_chart(fig_radar, use_container_width=True)
    
    with col_bar:
        st.subheader("風險指標分數")
        
        # 柱狀圖（垂直）- 使用各指標燈號顏色（用原始值判斷）
        indicator_names = ['VIX', 'CNN恐懼/貪婪', '信用利差', '美元指數', 'USD/JPY']
        raw_values = [risk['raw_vix'], risk['raw_fear_greed'], risk['raw_spread'], risk['raw_dxy'], risk['raw_jpy']]
        score_values = [risk['vix'], risk['fear_greed'], risk['credit_spread'], risk['dollar'], risk['usd_jpy']]
        
        # 根據原始值設定顏色
        def get_light_color(key, value):
            if key == 'vix':
                return '#00ff9d' if value < 15 else '#FFD700' if value < 25 else '#FF6B00' if value < 35 else '#ff4d6d'
            elif key == 'fear_greed':
                return '#00ff9d' if value < 25 else '#FFD700' if value < 45 else '#8a9bb0' if value < 55 else '#FF6B00' if value < 75 else '#ff4d6d'
            elif key == 'credit':
                return '#00ff9d' if value < 2 else '#FFD700' if value < 3 else '#FF6B00' if value < 4 else '#ff4d6d'
            elif key == 'dxy':
                return '#00ff9d' if value < 100 else '#FFD700' if value < 105 else '#FF6B00' if value < 110 else '#ff4d6d'
            else:  # usd_jpy
                return '#00ff9d' if value < 130 else '#FFD700' if value < 145 else '#FF6B00' if value < 160 else '#ff4d6d'
        
        keys = ['vix', 'fear_greed', 'credit', 'dxy', 'usd_jpy']
        indicator_colors = [get_light_color(k, v) for k, v in zip(keys, raw_values)]
        
        fig_bar = go.Figure(go.Bar(
            x=indicator_names,
            y=score_values,
            marker_color=indicator_colors,
            text=[f'{v:.1f}' for v in score_values],
            textposition='outside',
            textfont=dict(color='#c8d8e8', size=11)
        ))
        fig_bar.update_layout(
            height=300,
            yaxis=dict(range=[0, 100], showgrid=True, gridcolor='#1e2d45', color='#c8d8e8'),
            xaxis=dict(showgrid=False, color='#c8d8e8', tickangle=30),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#c8d8e8',
            margin=dict(l=30, r=30, t=30, b=50),
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    
    # 歷史圖放下一行
    st.markdown("---")
    st.subheader("綜合風險指數歷史")
    
    # 時間區間和股票代碼選擇（對齊）
    col_period1, col_stock = st.columns([1, 2])
    with col_period1:
        st.markdown("<span style='color:#c8d8e8; font-size:14px;'>時間範圍</span>", unsafe_allow_html=True)
        period = st.selectbox("選擇時間區間", 
                              ["1mo", "3mo", "6mo", "1y", "2y", "5y"], 
                              index=2, 
                              label_visibility="collapsed")
    with col_stock:
        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)  # 對齊間距
        compare_stock = st.text_input("輸入股票代碼比較（選填）", value="SPY", placeholder="如: AAPL, NVDA, SPY, TSM, 2330.TW").upper()
    
    # 獲取風險指數歷史
    risk_history = get_risk_index_history_v2(period)
    
    # 獲取股票數據（如果有輸入）
    stock_data = None
    if compare_stock:
        stock_data = get_stock_data(compare_stock, period)
    
    if len(risk_history) > 0:
        # 根據風險等級設定顏色
        def get_risk_color(value):
            if value < 40:
                return '#00ff9d'  # 綠色
            elif value < 60:
                return '#FFD700'  # 亮黃色
            elif value < 80:
                return '#FF6B00'  # 橘色
            else:
                return '#ff4d6d'  # 紅色
        
        # 創建彩色漸變
        colors = [get_risk_color(v) for v in risk_history.values]
        
        # 計算y軸範圍（根據實際數據調整，使波動更明顯）
        y_min = risk_history.min() - 10
        y_max = risk_history.max() + 10
        
        fig_risk = go.Figure()
        
        # 添加風險指數線
        fig_risk.add_trace(go.Scatter(
            x=risk_history.index, 
            y=risk_history.values,
            mode='lines+markers',
            name='綜合風險指數',
            line=dict(color='#00d4ff', width=3, shape='spline'),
            marker=dict(color=colors, size=3),
            yaxis='y1'
        ))
        
        # 如果，添加股票有股票數據線
        if stock_data is not None and len(stock_data) > 0:
            # 處理 MultiIndex
            if isinstance(stock_data, pd.DataFrame):
                if 'Close' in stock_data.columns:
                    stock_clean = stock_data['Close']
                else:
                    stock_clean = stock_data.iloc[:, 0]
            else:
                stock_clean = stock_data
            
            if len(stock_clean) > 0:
                # 對齊日期
                common_idx = risk_history.index.intersection(stock_clean.index)
                if len(common_idx) > 0:
                    stock_aligned = stock_clean.loc[common_idx]
                    
                    # 標準化股票數據到風險指數範圍
                    stock_min = stock_aligned.min()
                    stock_max = stock_aligned.max()
                    if stock_max > stock_min:
                        stock_normalized = (stock_aligned - stock_min) / (stock_max - stock_min) * (y_max - y_min) + y_min
                    else:
                        stock_normalized = stock_aligned
                    
                    fig_risk.add_trace(go.Scatter(
                        x=common_idx,
                        y=stock_normalized.values,
                        mode='lines',
                        name=f'{compare_stock} (標準化)',
                        line=dict(color='#E0E0E0', width=2, shape='spline'),  # 亮灰色
                        yaxis='y1'
                    ))
        
        # 添加風險區間背景
        fig_risk.add_hrect(y0=0, y1=40, fillcolor="rgba(0,255,157,0.1)", line_width=0, annotation_text="低風險", annotation_position="top left")
        fig_risk.add_hrect(y0=40, y1=60, fillcolor="rgba(255,179,71,0.1)", line_width=0, annotation_text="中等", annotation_position="top left")
        fig_risk.add_hrect(y0=60, y1=80, fillcolor="rgba(255,140,0,0.1)", line_width=0, annotation_text="高風險", annotation_position="top left")
        fig_risk.add_hrect(y0=80, y1=100, fillcolor="rgba(255,77,109,0.1)", line_width=0, annotation_text="極高", annotation_position="top left")
        
        fig_risk.update_layout(
            xaxis=dict(title="日期", rangeslider=dict(visible=True), color='#c8d8e8'),
            yaxis=dict(title="風險指數", range=[y_min, y_max], color='#c8d8e8', showgrid=True, gridcolor='#1e2d45'),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
            font_color='#c8d8e8', height=350,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_risk, use_container_width=True)
        
        # 統計數據（包含今天的即時數據）
        # 加入今天的即時風險指數
        all_risk = list(risk_history.values) + [risk['total']]
        
        avg_risk = sum(all_risk) / len(all_risk)
        max_risk = max(all_risk)
        min_risk = min(all_risk)
        current_risk = risk['total']
        
        st.markdown(f"""
        <div style='text-align:center; color:#c8d8e8; margin-top:10px;'>
            <span style='font-size:14px;'>📊 統計數據</span><br>
            <span style='color:#E0E0E0;'>今日: {current_risk:.1f}</span> | 
            <span style='color:#00d4ff;'>平均: {avg_risk:.1f}</span> | 
            <span style='color:#ff4d6d;'>最高: {max_risk:.1f}</span> | 
            <span style='color:#00ff9d;'>最低: {min_risk:.1f}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.warning("數據不足，無法顯示歷史走勢")
    
    # 數據來源資訊
    st.subheader("數據來源")
    col_src1, col_src2, col_src3, col_src4 = st.columns(4)
    with col_src1:
        st.caption("**VIX**: Yahoo Finance (^VIX)")
    with col_src2:
        st.caption("**CNN恐懼/貪婪**: feargreedmeter.com")
    with col_src3:
        st.caption("**信用利差**: FRED (BAMLH0A0HYM2)")
    with col_src4:
        st.caption("**美元指數**: Yahoo Finance (DX-Y.NYB)")
    
    st.caption(f"數據更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 頁面自動刷新: 15分鐘")


# ==================== CSV 歷史數據 ====================

def get_fear_greed_history_from_csv():
    """從 CSV 讀取 CNN恐懼/貪戻歷史"""
    try:
        if os.path.exists(CSV_FILE):
            df = pd.read_csv(CSV_FILE)
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def save_today_data(vix, fear_greed, credit_spread, dxy, usd_jpy, risk_index):
    """儲存當天數據到 CSV"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        if os.path.exists(CSV_FILE):
            df = pd.read_csv(CSV_FILE)
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            
            if today in df['date'].values:
                df.loc[df['date'] == today, 'fear_greed'] = fear_greed
                df.loc[df['date'] == today, 'vix'] = vix
                df.loc[df['date'] == today, 'credit_spread'] = credit_spread
                df.loc[df['date'] == today, 'dxy'] = dxy
                df.loc[df['date'] == today, 'usd_jpy'] = usd_jpy
                df.loc[df['date'] == today, 'risk_index'] = risk_index
            else:
                new_row = pd.DataFrame([{
                    'date': today, 'vix': vix, 'fear_greed': fear_greed,
                    'credit_spread': credit_spread, 'dxy': dxy, 
                    'usd_jpy': usd_jpy, 'risk_index': risk_index
                }])
                df = pd.concat([df, new_row], ignore_index=True)
        else:
            df = pd.DataFrame([{
                'date': today, 'vix': vix, 'fear_greed': fear_greed,
                'credit_spread': credit_spread, 'dxy': dxy, 
                'usd_jpy': usd_jpy, 'risk_index': risk_index
            }])
        
        df.to_csv(CSV_FILE, index=False)
        return True
    except Exception as e:
        return False

def get_risk_index_history_v2(period="1y"):
    """計算綜合風險指數歷史（使用真實 CNN恐懼/貪徊數據）"""
    try:
        csv_df = get_fear_greed_history_from_csv()
        
        vix_data = yf.download("^VIX", period=period, progress=False)
        dxy_data = yf.download("DX-Y.NYB", period=period, progress=False)
        jpy_data = yf.download("JPY=X", period=period, progress=False)
        
        def get_close(data):
            if len(data) == 0:
                return pd.Series([])
            if isinstance(data.columns, pd.MultiIndex):
                close = data['Close'] if 'Close' in data.columns.get_level_values(0) else data.iloc[:, 0]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                return close
            elif 'Close' in data.columns:
                return data['Close']
            return data.iloc[:, 0]
        
        vix = get_close(vix_data)
        dxy = get_close(dxy_data)
        jpy = get_close(jpy_data)
        
        try:
            credit_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"
            credit_df = pd.read_csv(credit_url)
            credit_df['DATE'] = pd.to_datetime(credit_df['DATE'])
            credit_df = credit_df.set_index('DATE')
        except:
            credit_df = pd.DataFrame()
        
        common_idx = vix.index.intersection(dxy.index).intersection(jpy.index)
        
        risk_history = []
        dates = []
        
        for date in common_idx:
            v = float(vix.loc[date]) if date in vix.index else None
            d = float(dxy.loc[date]) if date in dxy.index else None
            j = float(jpy.loc[date]) if date in jpy.index else None
            
            c = None
            if len(credit_df) > 0 and date in credit_df.index:
                c = float(credit_df.loc[date, 'BAMLH0A0HYM2'])
            
            fg = 50
            if len(csv_df) > 0:
                date_str = date.strftime('%Y-%m-%d')
                if date_str in csv_df.index:
                    fg = csv_df.loc[date_str, 'fear_greed']
            
            if v and d and j:
                risk = calculate_risk_score(v, c, fg, d, j)
                risk_history.append(risk['total'])
                dates.append(date)
        
        return pd.Series(risk_history, index=dates)
    except Exception as e:
        return pd.Series([])

if __name__ == "__main__":
    main()
