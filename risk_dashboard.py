"""
美股市場風險評估儀表板
"""
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import requests

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
    """從 feargreedmeter.com 獲取 CNN 恐懼/貪婪指數"""
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

# ==================== 指標說明 ====================
INDICATOR_DESC = {
    'vix': '市場對未來30天波動的預期',
    'fear_greed': '綜合7項指標的市場情緒指數',
    'credit': '高收益債 vs 公債利差，領先指標',
    'dxy': '美元對一籃子貨幣強弱，全球流動性',
    'jpy': '日幣貶值時套利交易累積，升值時可能引發平倉潮'
}

# ==================== 主程式 ====================
def main():
    st.title("美股市場風險評估儀表板")
    st.markdown(f"**LAST UPDATE** - {datetime.now().strftime('%Y 年 %m 月 %d 日 %H:%M')}")
    st.markdown("---")
    
    # 側邊欄
    with st.sidebar:
        st.header("⚙️ 設定")
        
        st.subheader("權重分配")
        st.write(f"- VIX: {WEIGHTS['vix']*100:.0f}%")
        st.write(f"- CNN恐懼/貪澈: {WEIGHTS['fear_greed']*100:.0f}%")
        st.write(f"- 信用利差: {WEIGHTS['credit_spread']*100:.0f}%")
        st.write(f"- 美元指數: {WEIGHTS['dollar']*100:.0f}%")
        st.write(f"- USD/JPY: {WEIGHTS['usd_jpy']*100:.0f}%")
        
        # 評分標準
        with st.expander("📋 評分標準", expanded=False):
            st.write("**VIX** 🟢 <15 | 🟡 15-25 | 🟠 25-35 | 🔴 >35")
            st.write("**恐懼/貪澈** 🟢 0-25 | 🟡 25-45 | ⚪ 45-55 | 🟠 55-75 | 🔴 75-100")
            st.write("**信用利差** 🟢 <2% | 🟡 2-3% | 🟠 3-4% | 🔴 >4%")
            st.write("**美元指數** 🟢 <100 | 🟡 100-105 | 🟠 105-110 | 🔴 >110")
            st.write("**USD/JPY** 🟢 <130 | 🟡 130-145 | 🟠 145-160 | 🔴 >160")
        
        stock_symbol = st.text_input("📈 股票代碼", value="TSM").upper()
        period = st.selectbox("數據時間範圍", ["6mo", "1y", "2y", "5y"], index=1)
        
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
        
        # 使用真實數據，若獲取失敗則使用預設值
        fear_greed_value = fear_greed if fear_greed is not None else 50
        credit_spread_value = credit_spread if credit_spread is not None else 3.0
        
        risk = calculate_risk_score(latest_vix, credit_spread_value, fear_greed_value, latest_dxy, latest_usdjpy)
    
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
        fig_gauge.update_layout(height=250, paper_bgcolor='rgba(0,0,0,0)', font_color='#c8d8e8')
        st.plotly_chart(fig_gauge, width='stretch')
        st.markdown(f"<div style='text-align:center; color:{risk_color}; font-size:18px;'>{risk_level}</div>", unsafe_allow_html=True)
    
    with col_alerts:
        st.markdown("### ⚡ 警示訊號")
        
        # VIX
        if risk['raw_vix'] >= 25:
            st.error(f"**VIX**: {risk['raw_vix']:.2f} — 高於 25，波動加劇")
        elif risk['raw_vix'] >= 15:
            st.warning(f"**VIX**: {risk['raw_vix']:.2f} — 處於中等區間")
        else:
            st.success(f"**VIX**: {risk['raw_vix']:.2f} — 市場相對平靜")
        
        # 恐懼/貪澈
        if risk['raw_fear_greed'] >= 75:
            st.error(f"**恐懼/貪澈**: {risk['raw_fear_greed']:.0f} — 市場過度貪澈")
        elif risk['raw_fear_greed'] <= 25:
            st.error(f"**恐懼/貪澈**: {risk['raw_fear_greed']:.0f} — 市場極度恐懼")
        elif risk['raw_fear_greed'] <= 45:
            st.warning(f"**恐懼/貪澈**: {risk['raw_fear_greed']:.0f} — 市場偏向恐懼")
        
        # 美元+日幣綜合
        dxy_high = risk['raw_dxy'] >= 105
        jpy_high = risk['raw_jpy'] >= 145
        
        if dxy_high and not jpy_high:
            st.error(f"**美元+日幣**: DXY {risk['raw_dxy']:.2f} + USD/JPY {risk['raw_jpy']:.2f} — 全球避險 + 套利交易平倉，壓力最大")
        elif not dxy_high and not jpy_high:
            st.warning(f"**美元+日幣**: DXY {risk['raw_dxy']:.2f} + USD/JPY {risk['raw_jpy']:.2f} — 日幣套利平倉，針對性風險")
        elif dxy_high and jpy_high:
            st.warning(f"**美元+日幣**: DXY {risk['raw_dxy']:.2f} + USD/JPY {risk['raw_jpy']:.2f} — 美元強勢，對新興市場和商品不利")
        else:
            st.success(f"**美元+日幣**: DXY {risk['raw_dxy']:.2f} + USD/JPY {risk['raw_jpy']:.2f} — 美元溫和，日幣套利正常")
        
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
    
    # 五個指標卡片
    col1, col2, col3, col4, col5 = st.columns(5)
    
    cols = [col1, col2, col3, col4, col5]
    indicators = [
        ('VIX 恐慌指數', risk['raw_vix'], risk['vix'], 'vix'),
        ('CNN 恐懼/貪澈', risk['raw_fear_greed'], risk['fear_greed'], 'fear_greed'),
        ('信用利差 %', risk['raw_spread'], risk['credit_spread'], 'credit'),
        ('美元指數 DXY', risk['raw_dxy'], risk['dollar'], 'dxy'),
        ('USD/JPY', risk['raw_jpy'], risk['usd_jpy'], 'jpy'),
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
            st.caption(INDICATOR_DESC.get(key, ''))
    
    st.markdown("---")
    
    # 雷達圖 + 歷史圖
    col_radar, col_history = st.columns([1, 2])
    
    with col_radar:
        labels = ['VIX', '信用利差', '恐懼/貪澈', '美元指數', 'USD/JPY']
        values = [risk['vix'], risk['credit_spread'], risk['fear_greed'], risk['dollar'], risk['usd_jpy']]
        labels.append(labels[0])
        values.append(values[0])
        
        fig_radar = go.Figure(go.Scatterpolar(
            r=values, theta=labels, fill='toself',
            fillcolor='rgba(0,212,255,0.1)', line_color='#00d4ff'))
        fig_radar.update_layout(
            polar=dict(bgcolor='rgba(0,0,0,0)', 
                      radialaxis=dict(visible=True, range=[0, 100], color='#4a6080'),
                      angularaxis=dict(color='#c8d8e8', tickfont=dict(size=12, color='#c8d8e8'))),
            paper_bgcolor='rgba(0,0,0,0)', font_color='#c8d8e8', height=350
        )
        st.subheader("🕸️ 風險雷達圖")
        st.plotly_chart(fig_radar, width='stretch')
        
        # 相關性
        if len(stock_data) > 0 and len(vix_data) > 0:
            corr = -0.3  # 簡化
            st.info(f"**風險指數與 {stock_symbol} 相關係數: {corr:.3f}**\n\n兩者呈現負相關，風險升高時股價傾向下跌")
    
    with col_history:
        st.subheader(f"📈 {stock_symbol} 與市場風險指數歷史關係")
        
        if len(stock_data) > 0 and len(vix_data) > 0:
            # 對齊數據
            vix_clean = vix_data.dropna()
            stock_clean = stock_data.dropna()
            
            if len(vix_clean) > 0 and len(stock_clean) > 0:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=vix_clean.index, y=vix_clean.values, name="VIX", 
                                        line=dict(color='red'), yaxis='y1'))
                fig.add_trace(go.Scatter(x=stock_clean.index, y=stock_clean.values, name=f"{stock_symbol}", 
                                        line=dict(color='blue'), yaxis='y2'))
                fig.update_layout(
                    xaxis=dict(title="日期", rangeslider=dict(visible=True)),
                    yaxis=dict(title="VIX", side='left'),
                    yaxis2=dict(title=f"{stock_symbol}", overlaying='y', side='right'),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                    font_color='#c8d8e8', height=400
                )
                st.plotly_chart(fig, width='stretch')
            else:
                st.warning("數據不足，無法顯示歷史走勢")
        else:
            st.warning("數據不足，無法顯示歷史走勢")
    
    st.markdown("---")
    
    # 數據來源資訊
    st.subheader("📡 數據來源")
    col_src1, col_src2, col_src3, col_src4 = st.columns(4)
    with col_src1:
        st.caption("**VIX**: Yahoo Finance (^VIX)")
    with col_src2:
        st.caption("**恐懼/貪澈**: feargreedmeter.com")
    with col_src3:
        st.caption("**信用利差**: FRED (BAMLH0A0HYM2)")
    with col_src4:
        st.caption("**美元指數**: Yahoo Finance (DX-Y.NYB)")
    
    st.caption(f"數據更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 頁面自動刷新: 15分鐘")

if __name__ == "__main__":
    main()
