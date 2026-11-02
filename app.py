import os, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import requests
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="VENOM LIVE MARKET AI", page_icon="🐍", layout="wide")
IST = ZoneInfo("Asia/Kolkata")
st.markdown("""
<style>
.stApp{background:#08111e;color:#e8f0fa}
[data-testid="stMetric"]{background:#142338;padding:12px;border-radius:12px}
.title{font-size:32px;font-weight:900;color:#35d6ae}
.signal{font-size:38px;font-weight:900;text-align:center;padding:14px;border-radius:12px}
.buy{color:#31d6a6;background:#10352f}.sell{color:#ff6878;background:#3a1822}
.wait{color:#f5c75c;background:#382f17}
</style>
""", unsafe_allow_html=True)
st.markdown('<div class="title">🐍 VENOM LIVE MARKET AI</div>', unsafe_allow_html=True)
st.caption("Forex • Gold • Crude Oil | Live provider candles | Technical analysis | 5-minute signal refresh")

with st.sidebar:
    st.header("Settings")
    key = st.text_input("Twelve Data API key", value=os.getenv("TWELVE_DATA_API_KEY",""), type="password")
    market = st.selectbox("Market", ["EUR/USD","GBP/USD","USD/JPY","AUD/USD","XAU/USD (Gold)","WTI/USD (Crude Oil)"])
    symbol = market.replace(" (Gold)","").replace(" (Crude Oil)","")
    interval = st.selectbox("Candle timeframe", ["1min","5min","15min"])
    refresh = st.selectbox("Refresh interval", [30,60,120,300], index=1,
                           format_func=lambda n:f"{n} seconds")
    st.caption("Actual update speed and symbol access depend on your Twelve Data plan.")
    st.button("Refresh now", use_container_width=True)

if not key:
    st.warning("Enter your Twelve Data API key in the sidebar.")
    st.info("Keep the key private. Do not paste it into source code or commit it to a public repository.")
    st.stop()

@st.cache_data(ttl=25, show_spinner=False)
def get_candles(sym, tf, api_key):
    r=requests.get("https://api.twelvedata.com/time_series",
      params={"symbol":sym,"interval":tf,"outputsize":120,"timezone":"UTC","apikey":api_key},timeout=20)
    r.raise_for_status()
    j=r.json()
    if "values" not in j: raise RuntimeError(j.get("message","No candle data returned"))
    d=pd.DataFrame(j["values"])
    for col in ["open","high","low","close"]: d[col]=pd.to_numeric(d[col],errors="coerce")
    d["datetime"]=pd.to_datetime(d["datetime"],utc=True,errors="coerce")
    return d.dropna().sort_values("datetime").reset_index(drop=True)

def ema(s,n): return s.ewm(span=n,adjust=False).mean()
def rsi(s,n=14):
    delta=s.diff()
    gain=delta.clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    loss=(-delta.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    rs=gain/loss.replace(0,np.nan)
    return 100-(100/(1+rs))

try:
    df=get_candles(symbol,interval,key)
except Exception as e:
    st.error(f"Market data error: {e}")
    st.caption("Check API key, provider plan, symbol availability and internet connection.")
    st.stop()

df["ema9"]=ema(df.close,9); df["ema21"]=ema(df.close,21)
df["rsi14"]=rsi(df.close)
df["macd"]=ema(df.close,12)-ema(df.close,26)
df["macd_signal"]=ema(df.macd,9)

# Exclude the newest candle because it may still be forming.
closed=df.iloc[:-1].copy()
signal="WAIT"; reason="Need at least 30 completed candles."
if len(closed)>=30:
    last=closed.iloc[-1]; prev=closed.iloc[-2]
    bullish=(last.ema9>last.ema21 and last.close>last.ema9 and
             last.macd>last.macd_signal and 50<=last.rsi14<=70 and last.close>prev.high)
    bearish=(last.ema9<last.ema21 and last.close<last.ema9 and
             last.macd<last.macd_signal and 30<=last.rsi14<=50 and last.close<prev.low)
    if bullish: signal="BUY"; reason="EMA uptrend + MACD bullish + RSI confirmation + close above previous high."
    elif bearish: signal="SELL"; reason="EMA downtrend + MACD bearish + RSI confirmation + close below previous low."
    else: reason="Indicators are mixed or no breakout. WAIT is safer than forcing a direction."

now=datetime.now(timezone.utc).astimezone(IST)
next_ts=((int(now.timestamp())//300)+1)*300
remain=max(0,next_ts-int(now.timestamp()))
latest=df.iloc[-1]
a,b,c,d=st.columns(4)
a.metric("Market",market); b.metric("Latest price",f"{latest.close:.5f}")
c.metric("RSI 14","--" if pd.isna(latest.rsi14) else f"{latest.rsi14:.1f}")
d.metric("Next 5-min cycle",f"{remain//60:02d}:{remain%60:02d}")
klass=signal.lower()
st.markdown(f'<div class="signal {klass}">{signal}</div>',unsafe_allow_html=True)
st.write(reason)
st.caption("Analysis time: "+now.strftime("%d-%b-%Y %H:%M:%S IST")+" | Intended review: next 5-minute cycle; not a guaranteed trade outcome.")

fig=go.Figure()
fig.add_trace(go.Candlestick(x=df.datetime,open=df.open,high=df.high,low=df.low,close=df.close,name="Candles"))
fig.add_trace(go.Scatter(x=df.datetime,y=df.ema9,name="EMA 9",line=dict(width=1.5)))
fig.add_trace(go.Scatter(x=df.datetime,y=df.ema21,name="EMA 21",line=dict(width=1.5)))
fig.update_layout(template="plotly_dark",height=500,xaxis_rangeslider_visible=False,
                  title=f"{market} — {interval}",margin=dict(l=8,r=8,t=35,b=8))
st.plotly_chart(fig,use_container_width=True)

if len(closed)>=20:
    recent=closed.tail(20)
    x,y=st.columns(2)
    x.metric("Support (20 candles)",f"{recent.low.min():.5f}")
    y.metric("Resistance (20 candles)",f"{recent.high.max():.5f}")

st.subheader("Technical indicators")
x1,x2,x3,x4=st.columns(4)
x1.metric("EMA 9",f"{latest.ema9:.5f}")
x2.metric("EMA 21",f"{latest.ema21:.5f}")
x3.metric("MACD",f"{latest.macd:.6f}")
x4.metric("MACD signal",f"{latest.macd_signal:.6f}")
st.subheader("Latest candles")
v=df.tail(12).copy()
v["Time (IST)"]=v.datetime.dt.tz_convert(IST).dt.strftime("%d-%b %H:%M")
st.dataframe(v[["Time (IST)","open","high","low","close"]].iloc[::-1],use_container_width=True,hide_index=True)
st.warning("Educational technical estimates only, not guaranteed predictions or financial advice. Provider data may be delayed or unavailable for some instruments/plans. The dashboard refreshes data periodically; it is not a tick-by-tick streaming feed.")
time.sleep(int(refresh))
st.rerun()
