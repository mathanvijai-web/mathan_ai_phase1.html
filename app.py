"""
MATHAN AI — Angel One Brain
Simple HTTP polling, Render compatible
"""
import os, json, time, threading, datetime, requests
import pyotp
from flask import Flask, Response, jsonify, request

app = Flask(__name__)
PORT = int(os.environ.get("PORT", 8000))

# ── CREDENTIALS (pre-filled) ─────────────────────────────────────────
ANGEL = {
    "api_key": os.environ.get("ANGEL_API_KEY", "jYAKgdt3"),
    "client_id": os.environ.get("ANGEL_CLIENT_ID", "V542909"),
    "pin": os.environ.get("ANGEL_PIN", "1818"),
    "totp_secret": os.environ.get("ANGEL_TOTP", "KJ4MRMUWNTFTCUALRBH5ALKA7A"),
    "connected": False, "jwt_token": "", "error": None,
}

# ── STATE ────────────────────────────────────────────────────────────
M = {
    "spot": None, "vix": None, "gift": None, "gift_diff": None,
    "atm": None, "pcr": None, "call_oi": None, "put_oi": None,
    "ce_prem": None, "pe_prem": None, "support": None, "resistance": None,
    "exp_days": None, "source": "LOADING", "fetch_time": None,
}
BRAIN = {
    "signal": "WAIT", "bull_pct": 50, "bear_pct": 50,
    "confidence": "LOW", "reasons": [], "trap": False,
}
SYS = {"count": 0, "error": None, "index": "NIFTY", "angel_ok": False, "market_status": "CHECKING"}

AGENTS = {
    "l1":  {"name":"OI Analyst",     "signal":None,"detail":"","weight":1.5},
    "l2":  {"name":"Price Action",   "signal":None,"detail":"","weight":1.5},
    "l3":  {"name":"VIX Monitor",    "signal":None,"detail":"","weight":1.5},
    "l4":  {"name":"GIFT Tracker",   "signal":None,"detail":"","weight":1.0},
    "l5":  {"name":"CE Premium",     "signal":None,"detail":"","weight":1.0},
    "l6":  {"name":"PE Premium",     "signal":None,"detail":"","weight":1.0},
    "l7":  {"name":"Session Clock",  "signal":None,"detail":"","weight":0.8},
    "l8":  {"name":"Expiry Watcher", "signal":None,"detail":"","weight":0.8},
    "l9":  {"name":"Gap Detector",   "signal":None,"detail":"","weight":1.0},
    "l10": {"name":"PCR Engine",     "signal":None,"detail":"","weight":1.2},
    "l11": {"name":"Trap Detector",  "signal":None,"detail":"","weight":1.5},
    "l12": {"name":"Risk Control",   "signal":None,"detail":"","weight":1.2},
    "l13": {"name":"Behaviour AI",   "signal":None,"detail":"","weight":2.0},
}
LOCK = threading.Lock()

INDEX_CFG = {
    "NIFTY":  {"step": 50,  "lot": 65},
    "SENSEX": {"step": 100, "lot": 20},
}

def ist():
    tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(tz).strftime("%H:%M:%S")

def ist_mins():
    tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    t = datetime.datetime.now(tz)
    return t.hour * 60 + t.minute

def calc_expiry():
    tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    t = datetime.datetime.now(tz)
    d2t = (3 - t.weekday()) % 7
    if d2t == 0 and t.hour >= 15 and t.minute >= 30: d2t = 7
    return d2t

NSE_HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*", "Referer": "https://www.nseindia.com/option-chain"
}

def fetch_nse_oi(index="NIFTY"):
    """Fetch real OI from NSE — free, no auth needed."""
    try:
        s = requests.Session()
        s.get("https://www.nseindia.com", headers=NSE_HDR, timeout=6)
        r = s.get(
            f"https://www.nseindia.com/api/option-chain-indices?symbol={index}",
            headers=NSE_HDR, timeout=12
        )
        if r.status_code != 200:
            return False
        raw = r.json().get("records", {})
        spot = raw.get("underlyingValue", 0)
        data = raw.get("data", [])
        exp_dates = raw.get("expiryDates", [])
        target = exp_dates[0] if exp_dates else ""

        cfg = INDEX_CFG[index]
        atm = round(spot / cfg["step"]) * cfg["step"]

        tC = tP = mxC = mxP = mxCS = mxPS = ceLTP = peLTP = 0
        for row in data:
            if target and row.get("expiryDate", "") != target:
                continue
            st = row.get("strikePrice", 0)
            ce = row.get("CE", {})
            pe = row.get("PE", {})
            ceOI = ce.get("openInterest", 0) or 0
            peOI = pe.get("openInterest", 0) or 0
            ceLtp = ce.get("lastPrice", 0) or 0
            peLtp = pe.get("lastPrice", 0) or 0
            tC += ceOI; tP += peOI
            if ceOI > mxC: mxC = ceOI; mxCS = st
            if peOI > mxP: mxP = peOI; mxPS = st
            if abs(st - atm) < cfg["step"] + 1:
                if ceLtp: ceLTP = ceLtp
                if peLtp: peLTP = peLtp

        if tC == 0:
            return False

        with LOCK:
            M["spot"] = spot; M["atm"] = atm
            M["call_oi"] = tC; M["put_oi"] = tP
            M["pcr"] = round(tP / tC, 2) if tC else 1.0
            M["ce_prem"] = ceLTP; M["pe_prem"] = peLTP
            M["support"] = mxPS; M["resistance"] = mxCS
            M["source"] = "NSE REAL OI"
            M["exp_days"] = calc_expiry()
            M["fetch_time"] = ist()
            SYS["count"] += 1
            SYS["error"] = None
        print(f"[NSE OI] spot={spot} pcr={round(tP/tC,2)} CE={ceLTP} PE={peLTP}")
        return True
    except Exception as e:
        print(f"[NSE ERR] {e}")
        return False

def fetch_yahoo():
    """Yahoo — works even on weekends/holidays!"""
    idx = SYS.get("index", "NIFTY")
    sym = {"NIFTY": "%5ENSEI", "SENSEX": "%5EBSESN"}[idx]
    hdrs = {"User-Agent": "Mozilla/5.0"}
    
    # Check if market is open
    tz  = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now = datetime.datetime.now(tz)
    is_weekday = now.weekday() < 5   # Mon-Fri
    market_open = is_weekday and (9*60+15 <= now.hour*60+now.minute <= 15*60+30)
    
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
            params={"interval": "1d", "range": "5d"},  # 5 days — works on weekends!
            headers=hdrs, timeout=10)
        meta = r.json()["chart"]["result"][0]["meta"]
        # Use regularMarketPrice (last traded) — valid even after close
        sp = meta.get("regularMarketPrice", 0) or meta.get("previousClose", 0)
        pv = meta.get("previousClose", sp)
        if sp:
            cfg = INDEX_CFG[idx]
            atm = round(sp / cfg["step"]) * cfg["step"]
            with LOCK:
                M["spot"]   = sp
                M["atm"]    = atm
                M["gap"]    = round(sp - pv, 2) if pv else 0
                if not market_open:
                    M["source"] = f"Yahoo PREV CLOSE ({now.strftime('%a')})"
                else:
                    M["source"] = "Yahoo LIVE"
            print(f"[YAHOO] {idx}={sp} atm={atm} market_open={market_open}")
    except Exception as e:
        print(f"[YAHOO SPOT ERR] {e}")

    # Both indices always fetch
    try:
        r2 = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN",
            params={"interval": "1d", "range": "5d"},
            headers=hdrs, timeout=8)
        sp2 = r2.json()["chart"]["result"][0]["meta"].get("regularMarketPrice",0)
        if sp2:
            with LOCK:
                M["sensex"] = sp2
                M["sensex_atm"] = round(sp2/100)*100
    except: pass

    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX",
            params={"interval": "1m", "range": "1d"},
            headers=hdrs, timeout=8)
        vix = r.json()["chart"]["result"][0]["meta"].get("regularMarketPrice")
        with LOCK: M["vix"] = vix
    except: pass

    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/NIFTYFUTURES.NS",
            params={"interval": "1m", "range": "1d"},
            headers=hdrs, timeout=8)
        g = r.json()["chart"]["result"][0]["meta"].get("regularMarketPrice")
        with LOCK:
            M["gift"] = g
            if g and M["spot"]:
                M["gift_diff"] = round(g - M["spot"], 2)
    except: pass

def compute_brain():
    with LOCK:
        pcr=M["pcr"]; vix=M["vix"]; spot=M["spot"]
        atm=M["atm"]; gd=M["gift_diff"]
        ce=M["ce_prem"]; pe=M["pe_prem"]
        ce_p=M.get("ce_prev"); pe_p=M.get("pe_prev")
        sup=M["support"]; res=M["resistance"]
        exp=M["exp_days"]; gap=M.get("gap")

    mins=ist_mins(); ag={}

    # L1 OI / PCR
    if pcr:
        if pcr>1.5:   ag["l1"]=("bull",f"PCR {pcr} STRONG BULL — Put writing heavy")
        elif pcr>1.2: ag["l1"]=("bull",f"PCR {pcr} BULLISH")
        elif pcr<0.6: ag["l1"]=("bear",f"PCR {pcr} STRONG BEAR — Call writing heavy")
        elif pcr<0.8: ag["l1"]=("bear",f"PCR {pcr} BEARISH")
        else:         ag["l1"]=("neut",f"PCR {pcr} NEUTRAL")
    else: ag["l1"]=("neut","PCR N/A — Market closed / Loading")

    # L2 Price Action
    if res and spot and spot>res:      ag["l2"]=("bull",f"Broke resistance {int(res)} — Breakout")
    elif sup and spot and spot<sup:    ag["l2"]=("bear",f"Below support {int(sup)} — Breakdown")
    elif spot and atm and spot>atm+50: ag["l2"]=("bull",f"Above ATM {atm} — Upward bias")
    elif spot and atm and spot<atm-50: ag["l2"]=("bear",f"Below ATM {atm} — Downward bias")
    elif spot and atm:                 ag["l2"]=("neut",f"At ATM {atm}")
    else:                              ag["l2"]=("neut","Spot N/A — Pre market")

    # L3 VIX
    if vix:
        if vix<12:   ag["l3"]=("bull",f"VIX {vix:.1f} — Very calm, safe to trade")
        elif vix<15: ag["l3"]=("bull",f"VIX {vix:.1f} — Calm market")
        elif vix<18: ag["l3"]=("neut",f"VIX {vix:.1f} — Caution zone")
        elif vix<22: ag["l3"]=("bear",f"VIX {vix:.1f} — HIGH FEAR")
        else:        ag["l3"]=("bear",f"VIX {vix:.1f} — EXTREME DANGER, avoid buying")
    else: ag["l3"]=("neut","VIX N/A")

    # L4 GIFT
    if gd is not None:
        if gd>150:    ag["l4"]=("bull",f"GIFT +{round(gd)} — Strong gap up tomorrow")
        elif gd>60:   ag["l4"]=("bull",f"GIFT +{round(gd)} — Mild gap up")
        elif gd<-150: ag["l4"]=("bear",f"GIFT {round(gd)} — Strong gap down")
        elif gd<-60:  ag["l4"]=("bear",f"GIFT {round(gd)} — Mild gap down")
        else:         ag["l4"]=("neut",f"GIFT ±{round(abs(gd))} — Flat open")
    else: ag["l4"]=("neut","GIFT N/A")

    # L5 CE Premium
    if ce:
        chg=(ce-ce_p) if ce_p else 0
        if chg>5:    ag["l5"]=("bull",f"CE ₹{ce:.0f} +{chg:.0f} rising — Buyers active")
        elif chg<-5: ag["l5"]=("bear",f"CE ₹{ce:.0f} {chg:.0f} falling — CE sold")
        else:        ag["l5"]=("neut",f"CE ₹{ce:.0f} stable")
    else: ag["l5"]=("neut","CE N/A — Market closed")

    # L6 PE Premium
    if pe:
        chg=(pe-pe_p) if pe_p else 0
        if chg>5:    ag["l6"]=("bear",f"PE ₹{pe:.0f} +{chg:.0f} rising — Bears active")
        elif chg<-5: ag["l6"]=("bull",f"PE ₹{pe:.0f} {chg:.0f} falling — PE sold")
        else:        ag["l6"]=("neut",f"PE ₹{pe:.0f} stable")
    else: ag["l6"]=("neut","PE N/A — Market closed")

    # L7 Session Clock
    if mins<555:   ag["l7"]=("neut","Pre-market — Wait for 9:15")
    elif mins<600: ag["l7"]=("bull","OPEN HOUR 9:15 — High volatility entry")
    elif mins<660: ag["l7"]=("bull","9:15–11:00 — Best entry window")
    elif mins<780: ag["l7"]=("neut","11:00–1:00 — Mid session")
    elif mins<870: ag["l7"]=("neut","1:00–2:30 — Afternoon consolidation")
    elif mins<930: ag["l7"]=("neut","2:30–3:30 — EXPIRY WINDOW active")
    else:          ag["l7"]=("neut","Post market — Closed")

    # L8 Expiry Watcher
    if exp is not None:
        if exp==0:   ag["l8"]=("bull","TODAY EXPIRY ⚡ — Max theta decay")
        elif exp==1: ag["l8"]=("neut","PRE-EXPIRY tomorrow — Volatile")
        elif exp<=3: ag["l8"]=("neut",f"{exp} days — Near expiry caution")
        else:        ag["l8"]=("neut",f"{exp} days to expiry — Normal")
    else: ag["l8"]=("neut","Expiry N/A")

    # L9 Gap Detector
    if gap:
        if gap>100:    ag["l9"]=("bull",f"Gap UP +{round(gap)} — Strong bullish open")
        elif gap>40:   ag["l9"]=("bull",f"Gap UP +{round(gap)} — Mild")
        elif gap<-100: ag["l9"]=("bear",f"Gap DOWN {round(gap)} — Strong bearish open")
        elif gap<-40:  ag["l9"]=("bear",f"Gap DOWN {round(gap)} — Mild")
        else:          ag["l9"]=("neut",f"Flat ±{round(abs(gap))} — No gap")
    else: ag["l9"]=("neut","Gap N/A")

    # L10 PCR Engine
    if pcr:
        if pcr>1.5:   ag["l10"]=("bull",f"PCR {pcr} — Strong bull confirmation")
        elif pcr>1.2: ag["l10"]=("bull",f"PCR {pcr} — Bullish momentum")
        elif pcr<0.6: ag["l10"]=("bear",f"PCR {pcr} — Strong bear momentum")
        elif pcr<0.8: ag["l10"]=("bear",f"PCR {pcr} — Bearish bias")
        else:         ag["l10"]=("neut",f"PCR {pcr} — Neutral zone")
    else: ag["l10"]=("neut","PCR N/A")

    # L11 Trap Detector
    trap=False; trap_det=""
    if pcr and spot and atm:
        if pcr>1.3 and spot<atm-50:
            trap=True; trap_det="PCR bullish but price below ATM — BULL TRAP?"
        elif pcr<0.75 and spot>atm+50:
            trap=True; trap_det="PCR bearish but price above ATM — BEAR TRAP?"
    if vix and vix>20 and pcr and pcr>1.2:
        trap=True; trap_det=f"High VIX {vix:.1f} + Bullish PCR — Manipulation risk!"
    ag["l11"]=("neut",f"⚠️ {trap_det}") if trap else ("neut","No trap pattern detected")

    # L12 Risk Control
    if vix and vix>22:        ag["l12"]=("bear",f"VIX {vix:.1f} EXTREME — Avoid all trades!")
    elif vix and vix>18:      ag["l12"]=("neut",f"VIX {vix:.1f} HIGH — 1 lot max, tight SL")
    elif exp==0 and mins>=870:ag["l12"]=("neut","Last hour expiry — Zero decay risk")
    else:                     ag["l12"]=("bull","Risk normal — Standard position OK")

    # L13 Behaviour AI Master
    b=sum(1 for v in ag.values() if v[0]=="bull")
    r=sum(1 for v in ag.values() if v[0]=="bear")
    total=b+r; ratio=(b-r)/total if total>0 else 0
    if ratio>0.3 and (not vix or vix<18) and not trap:
        ag["l13"]=("bull",f"Context BULL ({b}↑ {r}↓) — Go Long")
    elif ratio<-0.3 and not trap:
        ag["l13"]=("bear",f"Context BEAR ({b}↑ {r}↓) — Go Short")
    else:
        ag["l13"]=("neut",f"MIXED SIGNAL ({b}↑ {r}↓) — Wait for clarity")

    # Update AGENTS
    with LOCK:
        for aid,(sig,det) in ag.items():
            AGENTS[aid]["signal"]=sig
            AGENTS[aid]["detail"]=det

    # Weighted brain decision
    bw=brw=0.0
    reasons=[]
    for aid,a in ag.items():
        sig=a[0]; w=AGENTS[aid]["weight"]; det=a[1]
        if sig=="bull":   bw+=w;  reasons.append(det)
        elif sig=="bear": brw+=w; reasons.append(det)

    tw=bw+brw or 1
    bp=round(bw/tw*100); brp=100-bp
    diff=abs(bw-brw)
    conf="HIGH" if diff>=3 else "MEDIUM" if diff>=1.5 else "LOW"

    if trap:        sig="WAIT"
    elif bp>=65:    sig="BUY CE"
    elif brp>=65:   sig="BUY PE"
    else:           sig="WAIT"

    with LOCK:
        BRAIN.update({
            "signal":sig,"bull_pct":bp,"bear_pct":brp,
            "confidence":conf,"reasons":reasons[:6],"trap":trap
        })
        M["ce_prev"]=ce; M["pe_prev"]=pe

def full_cycle():
    idx = SYS.get("index", "NIFTY")
    
    # Check market status
    tz  = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now = datetime.datetime.now(tz)
    is_weekday   = now.weekday() < 5
    market_hours = is_weekday and (9*60+15 <= now.hour*60+now.minute <= 15*60+30)
    
    day_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    day = day_names[now.weekday()]
    
    if not is_weekday:
        status = f"MARKET CLOSED — {day} (Weekend)"
    elif not market_hours:
        if now.hour*60+now.minute < 9*60+15:
            status = f"PRE-MARKET — Opens 9:15 AM"
        else:
            status = f"MARKET CLOSED — 3:30 PM"
    else:
        status = "MARKET OPEN"
    
    with LOCK:
        SYS["market_status"] = status
        SYS["error"] = None if market_hours else status
    
    # Always fetch Yahoo (works weekends too!)
    fetch_yahoo()
    
    # NSE OI only when market open
    if market_hours:
        ok = fetch_nse_oi_direct(idx)
        if not ok:
            ok = fetch_nse_oi(idx)
        if not ok:
            with LOCK: SYS["error"] = f"{status} — NSE OI unavailable"
    else:
        # Weekend/after hours — use last known or estimated OI
        with LOCK:
            if not M["call_oi"]:
                # Estimate from spot
                sp = M["spot"] or 23000
                base = sp * 200
                M["call_oi"] = int(base)
                M["put_oi"]  = int(base * 1.05)
                M["pcr"]     = 1.05
                M["support"] = round(sp/50)*50 - 100
                M["resistance"] = round(sp/50)*50 + 100
                M["ce_prem"] = round(sp * 0.004)
                M["pe_prem"] = round(sp * 0.0038)
                M["source"]  = f"ESTIMATED ({status})"
    
    compute_brain()

def poll_loop():
    while True:
        time.sleep(15)
        try:
            full_cycle()
        except Exception as e:
            print(f"[POLL ERR] {e}")

# ── HTML DASHBOARD ───────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"/>
<title>Mathan AI — Angel One Brain</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Share+Tech+Mono&family=Rajdhani:wght@600;700&display=swap" rel="stylesheet"/>
<style>
:root{--bg:#070b0f;--bg2:#0d1419;--bg3:#111820;--brd:#1e2d3d;
  --gold:#f0a500;--grn:#00e676;--red:#ff1744;--blu:#29b6f6;
  --pur:#ce93d8;--orn:#ff9800;--txt:#cdd9e5;--dim:#4a6278;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--txt);font-family:'Rajdhani',sans-serif;padding-bottom:50px;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
@keyframes spin{to{transform:rotate(360deg)}}
.hdr{position:sticky;top:0;z-index:100;background:linear-gradient(180deg,#0a1118,rgba(7,11,15,.97));
  border-bottom:2px solid var(--gold);padding:10px 14px;
  display:flex;align-items:center;justify-content:space-between;}
.logo{font-family:'Orbitron';font-size:11px;font-weight:900;color:var(--gold);letter-spacing:1px;}
.logo small{display:block;font-family:'Share Tech Mono';font-size:7px;color:var(--dim);margin-top:1px;}
.hclock{font-family:'Orbitron';font-size:12px;color:var(--gold);}
.hlive{font-size:9px;font-family:'Share Tech Mono';padding:2px 7px;border-radius:3px;}
.hlive.on{border:1px solid var(--grn);color:var(--grn);}
.hlive.off{border:1px solid var(--red);color:var(--red);}
.sbar{display:flex;justify-content:space-between;padding:4px 12px;
  background:var(--bg2);border-bottom:1px solid var(--brd);
  font-family:'Share Tech Mono';font-size:9px;}
.sdot{width:6px;height:6px;border-radius:50%;display:inline-block;margin-right:4px;vertical-align:middle;}
.sdot.ok{background:var(--grn);} .sdot.wait{background:var(--gold);animation:blink 1s infinite;} .sdot.err{background:var(--red);}
.main{padding:10px;max-width:480px;margin:0 auto;}
.card{background:var(--bg2);border:1px solid var(--brd);border-radius:12px;padding:12px;margin-bottom:9px;}
.ctitle{font-family:'Orbitron';font-size:9px;color:var(--gold);letter-spacing:1px;margin-bottom:9px;display:flex;justify-content:space-between;align-items:center;}
.badge{display:inline-flex;padding:1px 7px;border-radius:8px;font-family:'Share Tech Mono';font-size:7px;}
.badge.live{background:rgba(0,230,118,.1);border:1px solid rgba(0,230,118,.3);color:var(--grn);}
.badge.wait{background:rgba(41,182,246,.08);border:1px solid rgba(41,182,246,.2);color:var(--blu);}
.inp{width:100%;background:var(--bg3);border:1px solid var(--brd);border-radius:6px;
  color:var(--txt);padding:8px 10px;font-size:12px;font-family:'Share Tech Mono';outline:none;margin-bottom:6px;}
.inp-lbl{font-family:'Share Tech Mono';font-size:7px;color:var(--dim);letter-spacing:.5px;margin-bottom:3px;}
.cbtn{width:100%;padding:11px;border-radius:8px;cursor:pointer;
  font-family:'Orbitron';font-size:9px;font-weight:700;letter-spacing:1px;
  border:1px solid var(--orn);background:rgba(255,152,0,.08);color:var(--orn);margin-top:6px;}
.cbtn.ok{border-color:var(--pur);background:rgba(206,147,216,.08);color:var(--pur);}
.cbtn.yahoo{border-color:var(--gold);background:rgba(240,165,0,.08);color:var(--gold);}
.btn-row{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px;}
.ki{width:100%;background:var(--bg3);border:1px solid var(--brd);border-radius:6px;
  color:var(--grn);padding:8px;font-size:12px;font-family:'Share Tech Mono';outline:none;}
.idx-row{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:9px;}
.ib{background:var(--bg3);border:2px solid var(--brd);border-radius:9px;padding:9px;text-align:center;cursor:pointer;}
.ib.on{border-color:var(--gold);}
.ib-name{font-family:'Orbitron';font-size:13px;font-weight:900;}
.ib.on .ib-name{color:var(--gold);}
.ib-spot{font-family:'Share Tech Mono';font-size:11px;color:var(--grn);margin-top:2px;}
.ib-atm{font-family:'Share Tech Mono';font-size:8px;color:var(--blu);margin-top:1px;}
.gift-box{background:var(--bg2);border:1px solid var(--brd);border-radius:11px;
  padding:11px 13px;margin-bottom:9px;display:flex;justify-content:space-between;align-items:center;}
.g-lbl{font-family:'Share Tech Mono';font-size:7px;color:var(--gold);letter-spacing:1px;margin-bottom:2px;}
.g-val{font-family:'Orbitron';font-size:20px;font-weight:900;}
.g-chg{font-family:'Share Tech Mono';font-size:9px;margin-top:2px;}
.g-right{background:var(--bg3);border-radius:7px;padding:6px 9px;text-align:center;min-width:90px;}
.mstrip{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin-bottom:9px;}
.mc{background:var(--bg2);border:1px solid var(--brd);border-radius:8px;padding:7px;text-align:center;}
.mc-n{font-family:'Share Tech Mono';font-size:7px;color:var(--dim);margin-bottom:2px;}
.mc-v{font-family:'Orbitron';font-size:13px;font-weight:700;}
.mc-c{font-family:'Share Tech Mono';font-size:8px;margin-top:1px;}
.oi-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:9px;}
.oi-cell{background:var(--bg3);border-radius:7px;padding:8px;text-align:center;border:1px solid var(--brd);}
.oi-lbl{font-family:'Share Tech Mono';font-size:7px;color:var(--dim);margin-bottom:2px;}
.oi-val{font-family:'Orbitron';font-size:14px;font-weight:700;}
.pcr-wrap{background:var(--bg3);border-radius:7px;padding:8px 9px;margin-bottom:7px;}
.pcr-bg{height:10px;border-radius:5px;background:rgba(255,255,255,.05);overflow:hidden;margin-bottom:4px;}
.pcr-fill{height:100%;border-radius:5px;transition:width .8s;}
.pcr-marks{display:flex;justify-content:space-between;font-family:'Share Tech Mono';font-size:7px;color:var(--dim);}
.sr-row{display:grid;grid-template-columns:1fr 1fr;gap:6px;}
.sr-cell{border-radius:7px;padding:8px;text-align:center;}
.sr-sup{background:rgba(0,230,118,.07);border:1px solid rgba(0,230,118,.2);}
.sr-res{background:rgba(255,23,68,.07);border:1px solid rgba(255,23,68,.2);}
.prem-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;}
.prem-cell{background:var(--bg3);border-radius:8px;padding:9px;border:2px solid var(--brd);text-align:center;}
.ptype{font-family:'Orbitron';font-size:10px;font-weight:700;margin-bottom:3px;}
.pval{font-family:'Orbitron';font-size:20px;font-weight:700;}
.brain-box{border-radius:13px;padding:14px;margin-bottom:9px;border:2px solid var(--brd);}
.brain-box.bull{border-color:rgba(0,230,118,.6);background:linear-gradient(135deg,rgba(0,230,118,.07),transparent);}
.brain-box.bear{border-color:rgba(255,23,68,.6);background:linear-gradient(135deg,rgba(255,23,68,.07),transparent);}
.brain-box.wait{border-color:rgba(240,165,0,.5);background:linear-gradient(135deg,rgba(240,165,0,.05),transparent);}
.brain-sig{font-family:'Orbitron';font-size:26px;font-weight:900;margin-bottom:4px;}
.brain-sub{font-size:11px;color:var(--dim);}
.go-btn{width:100%;padding:15px;border-radius:13px;border:none;cursor:pointer;
  background:linear-gradient(135deg,#7a5200,var(--gold));
  color:#000;font-family:'Orbitron';font-size:12px;font-weight:900;letter-spacing:2px;margin-bottom:9px;}
.go-btn:disabled{background:#1a2230;color:var(--dim);}
.claude-box{background:var(--bg2);border:1px solid rgba(240,165,0,.2);border-radius:11px;padding:12px;margin-bottom:9px;}
.ref-btn{width:100%;padding:9px;border-radius:9px;cursor:pointer;
  border:1px solid rgba(41,182,246,.4);background:rgba(41,182,246,.05);
  color:var(--blu);font-family:'Orbitron';font-size:9px;letter-spacing:1px;margin-bottom:9px;}
.ag-sect{font-family:'Share Tech Mono';font-size:7px;color:var(--dim);letter-spacing:2px;margin:8px 0 5px;}
.ag-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:4px;}
.agc{background:var(--bg3);border:1px solid var(--brd);border-radius:8px;padding:7px;position:relative;overflow:hidden;}
.agc::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--brd);}
.agc.bull::before{background:var(--grn);}
.agc.bear::before{background:var(--red);}
.agc.neut::before{background:var(--gold);}
.ag-top{display:flex;justify-content:space-between;margin-bottom:2px;}
.ag-id{font-family:'Orbitron';font-size:8px;color:var(--dim);}
.ag-sig{font-family:'Share Tech Mono';font-size:9px;font-weight:700;}
.ag-sig.bull{color:var(--grn);} .ag-sig.bear{color:var(--red);} .ag-sig.neut{color:var(--gold);} .ag-sig.none{color:var(--dim);}
.ag-name{font-size:10px;font-weight:700;margin-bottom:1px;}
.ag-val{font-family:'Share Tech Mono';font-size:8px;color:var(--dim);line-height:1.3;}
.conf-bar{background:var(--bg3);border-radius:8px;padding:9px;margin-bottom:7px;}
.conf-track{height:10px;border-radius:5px;background:rgba(255,255,255,.05);overflow:hidden;display:flex;margin-bottom:3px;}
.conf-bull{height:100%;background:linear-gradient(90deg,#004d40,var(--grn));transition:width .7s;}
.conf-bear{height:100%;background:linear-gradient(90deg,var(--red),#7f0000);transition:width .7s;}
.wsbar{position:fixed;bottom:0;left:0;right:0;z-index:200;padding:4px 12px;
  font-family:'Share Tech Mono';font-size:9px;background:var(--bg2);
  border-top:1px solid var(--brd);display:flex;align-items:center;gap:6px;}
.wsdot{width:6px;height:6px;border-radius:50%;background:var(--red);flex-shrink:0;}
.wsdot.on{background:var(--grn);}
.sp{display:inline-block;width:11px;height:11px;border:2px solid rgba(0,0,0,.3);
  border-top-color:#000;border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle;margin-right:4px;}
</style>
</head>
<body>
<div class="hdr">
  <div class="logo">MATHAN AI — ANGEL ONE<small>NSE REAL OI · 13 AGENTS · LIVE</small></div>
  <div style="display:flex;align-items:center;gap:8px;">
    <div class="hclock" id="clock">--:--:--</div>
    <div class="hlive off" id="live-badge">OFFLINE</div>
  </div>
</div>
<div class="sbar">
  <div><span class="sdot wait" id="sdot"></span><span id="stxt" style="color:var(--gold)">Starting...</span></div>
  <span id="rtxt" style="color:var(--dim)">IST</span>
</div>

<div class="main">

<!-- ANGEL ONE CARD -->
<div class="card" style="border-color:rgba(206,147,216,.3);">
  <div class="ctitle" style="color:var(--pur);">ANGEL ONE — REAL DATA
    <span id="angel-st" style="font-family:'Share Tech Mono';font-size:8px;color:var(--dim)">NOT SET</span>
  </div>
  <div class="inp-lbl">API KEY</div>
  <input class="inp" id="api-key" type="password" placeholder="jYAKgdt3"/>
  <div class="inp-lbl">CLIENT ID</div>
  <input class="inp" id="client-id" type="text" placeholder="V542909"/>
  <div class="inp-lbl">PIN</div>
  <input class="inp" id="angel-pin" type="password" placeholder="1818"/>
  <div class="inp-lbl">TOTP SECRET</div>
  <input class="inp" id="totp-secret" type="password" placeholder="KJ4MRMUWNTFTCUALRBH5ALKA7A"/>
  <div class="btn-row">
    <button class="cbtn" id="angel-btn" onclick="connectAngel()">CONNECT ANGEL ONE</button>
    <button class="cbtn yahoo" onclick="setYahoo()">YAHOO FALLBACK</button>
  </div>
</div>

<!-- CLAUDE KEY -->
<div class="card" style="border-color:rgba(41,182,246,.2);">
  <div class="ctitle" style="color:var(--blu);">CLAUDE AI KEY</div>
  <input class="ki" id="ki" type="password" placeholder="sk-ant-..." oninput="saveKey()"/>
</div>

<!-- INDEX SELECT -->
<div class="idx-row">
  <div class="ib on" id="ib-nifty" onclick="setIdx('NIFTY')">
    <div class="ib-name">NIFTY 50</div>
    <div class="ib-spot" id="n-spot">—</div>
    <div class="ib-atm" id="n-atm">ATM: —</div>
  </div>
  <div class="ib" id="ib-sensex" onclick="setIdx('SENSEX')">
    <div class="ib-name">SENSEX</div>
    <div class="ib-spot" id="s-spot">—</div>
    <div class="ib-atm" id="s-atm">ATM: —</div>
  </div>
</div>

<!-- GIFT NIFTY -->
<div class="gift-box">
  <div>
    <div class="g-lbl">GIFT NIFTY — SENTIMENT</div>
    <div class="g-val" id="gv" style="color:var(--gold)">—</div>
    <div class="g-chg" id="gc">—</div>
  </div>
  <div class="g-right">
    <div style="font-family:'Share Tech Mono';font-size:7px;color:var(--dim)">MOOD</div>
    <div style="font-size:12px;font-weight:700" id="gs" style="color:var(--gold)">—</div>
  </div>
</div>

<!-- MARKET STRIP -->
<div class="mstrip">
  <div class="mc"><div class="mc-n">NIFTY 50</div><div class="mc-v" id="nv" style="color:var(--grn)">—</div><div class="mc-c" id="na" style="color:var(--blu)">ATM: —</div></div>
  <div class="mc"><div class="mc-n">SENSEX</div><div class="mc-v" id="sv" style="color:var(--grn)">—</div><div class="mc-c" id="sa" style="color:var(--blu)">ATM: —</div></div>
  <div class="mc"><div class="mc-n">INDIA VIX</div><div class="mc-v" id="vv" style="color:var(--gold)">—</div><div class="mc-c" id="vn" style="color:var(--dim)">—</div></div>
</div>

<!-- OI -->
<div class="card">
  <div class="ctitle">OI ANALYSIS <span class="badge wait" id="oi-src">LOADING</span></div>
  <div class="oi-grid">
    <div class="oi-cell"><div class="oi-lbl">CALL OI</div><div class="oi-val" id="callOI" style="color:var(--red)">—</div></div>
    <div class="oi-cell"><div class="oi-lbl">PUT OI</div><div class="oi-val" id="putOI" style="color:var(--grn)">—</div></div>
  </div>
  <div class="pcr-wrap">
    <div style="display:flex;justify-content:space-between;font-family:'Share Tech Mono';font-size:8px;color:var(--dim);margin-bottom:5px;">
      <span>PUT/CALL RATIO</span><span id="pcrVal" style="color:var(--gold)">—</span>
    </div>
    <div class="pcr-bg"><div class="pcr-fill" id="pcrFill" style="width:50%;background:var(--gold)"></div></div>
    <div class="pcr-marks"><span>BEAR &lt;0.7</span><span>NEUTRAL 1.0</span><span>BULL &gt;1.2</span></div>
    <div style="font-family:'Share Tech Mono';font-size:10px;margin-top:5px;text-align:center" id="pcrSig">—</div>
  </div>
  <div class="sr-row">
    <div class="sr-cell sr-sup">
      <div style="font-family:'Share Tech Mono';font-size:7px;color:var(--grn)">SUPPORT</div>
      <div style="font-family:'Orbitron';font-size:14px;font-weight:700;color:var(--grn)" id="support">—</div>
    </div>
    <div class="sr-cell sr-res">
      <div style="font-family:'Share Tech Mono';font-size:7px;color:var(--red)">RESISTANCE</div>
      <div style="font-family:'Orbitron';font-size:14px;font-weight:700;color:var(--red)" id="resistance">—</div>
    </div>
  </div>
</div>

<!-- PREMIUM -->
<div class="card">
  <div class="ctitle">ATM PREMIUM <span class="badge wait" id="prem-src">LOADING</span></div>
  <div class="prem-grid">
    <div class="prem-cell"><div class="ptype" style="color:var(--grn)">CALL CE</div><div class="pval" id="cePrem" style="color:var(--grn)">—</div></div>
    <div class="prem-cell"><div class="ptype" style="color:var(--red)">PUT PE</div><div class="pval" id="pePrem" style="color:var(--red)">—</div></div>
  </div>
</div>

<!-- 13 AGENTS -->
<div class="card">
  <div class="ctitle">13 AGENT SIGNALS <span class="badge wait" id="ag-badge">WAITING</span></div>
  
  <div class="ag-sect">▸ OI &amp; PRICE</div>
  <div class="ag-grid">
    <div class="agc" id="card-l1"><div class="ag-top"><span class="ag-id">L1</span><span class="ag-sig none" id="sig-l1">—</span></div><div class="ag-name">OI Analyst</div><div class="ag-val" id="val-l1">—</div></div>
    <div class="agc" id="card-l2"><div class="ag-top"><span class="ag-id">L2</span><span class="ag-sig none" id="sig-l2">—</span></div><div class="ag-name">Price Action</div><div class="ag-val" id="val-l2">—</div></div>
    <div class="agc" id="card-l3"><div class="ag-top"><span class="ag-id">L3</span><span class="ag-sig none" id="sig-l3">—</span></div><div class="ag-name">VIX Monitor</div><div class="ag-val" id="val-l3">—</div></div>
    <div class="agc" id="card-l4"><div class="ag-top"><span class="ag-id">L4</span><span class="ag-sig none" id="sig-l4">—</span></div><div class="ag-name">GIFT Tracker</div><div class="ag-val" id="val-l4">—</div></div>
  </div>
  
  <div class="ag-sect">▸ PREMIUM &amp; SESSION</div>
  <div class="ag-grid">
    <div class="agc" id="card-l5"><div class="ag-top"><span class="ag-id">L5</span><span class="ag-sig none" id="sig-l5">—</span></div><div class="ag-name">CE Premium</div><div class="ag-val" id="val-l5">—</div></div>
    <div class="agc" id="card-l6"><div class="ag-top"><span class="ag-id">L6</span><span class="ag-sig none" id="sig-l6">—</span></div><div class="ag-name">PE Premium</div><div class="ag-val" id="val-l6">—</div></div>
    <div class="agc" id="card-l7"><div class="ag-top"><span class="ag-id">L7</span><span class="ag-sig none" id="sig-l7">—</span></div><div class="ag-name">Session Clock</div><div class="ag-val" id="val-l7">—</div></div>
    <div class="agc" id="card-l8"><div class="ag-top"><span class="ag-id">L8</span><span class="ag-sig none" id="sig-l8">—</span></div><div class="ag-name">Expiry Watcher</div><div class="ag-val" id="val-l8">—</div></div>
  </div>
  
  <div class="ag-sect">▸ BEHAVIOUR &amp; INTELLIGENCE</div>
  <div class="ag-grid">
    <div class="agc" id="card-l9"><div class="ag-top"><span class="ag-id">L9</span><span class="ag-sig none" id="sig-l9">—</span></div><div class="ag-name">Gap Detector</div><div class="ag-val" id="val-l9">—</div></div>
    <div class="agc" id="card-l10"><div class="ag-top"><span class="ag-id">L10</span><span class="ag-sig none" id="sig-l10">—</span></div><div class="ag-name">PCR Engine</div><div class="ag-val" id="val-l10">—</div></div>
    <div class="agc" id="card-l11" style="border-color:rgba(206,147,216,.2)"><div class="ag-top"><span class="ag-id">L11</span><span class="ag-sig none" id="sig-l11">—</span></div><div class="ag-name" style="color:var(--pur)">Trap Detector</div><div class="ag-val" id="val-l11">—</div></div>
    <div class="agc" id="card-l12"><div class="ag-top"><span class="ag-id">L12</span><span class="ag-sig none" id="sig-l12">—</span></div><div class="ag-name">Risk Control</div><div class="ag-val" id="val-l12">—</div></div>
  </div>
  
  <!-- L13 MASTER -->
  <div class="agc" id="card-l13" style="grid-column:span 2;border-color:rgba(240,165,0,.3);margin-top:5px">
    <div class="ag-top"><span class="ag-id" style="color:var(--gold)">L13 — MASTER</span><span class="ag-sig none" id="sig-l13">—</span></div>
    <div class="ag-name" style="color:var(--gold)">Behaviour AI</div>
    <div class="ag-val" id="val-l13">—</div>
  </div>
  
  <!-- Confidence Bar -->
  <div class="conf-bar" style="margin-top:8px">
    <div style="display:flex;justify-content:space-between;font-family:'Share Tech Mono';font-size:8px;margin-bottom:5px;">
      <span style="color:var(--grn)">BULL <span id="bp">50%</span></span>
      <span style="color:var(--gold)" id="conf-mid">Confidence: —</span>
      <span style="color:var(--red)">BEAR <span id="brp">50%</span></span>
    </div>
    <div class="conf-track">
      <div class="conf-bull" id="conf-bull" style="width:50%"></div>
      <div class="conf-bear" id="conf-bear" style="width:50%"></div>
    </div>
  </div>
</div>

<!-- BRAIN -->
<div class="brain-box wait" id="brain-box">
  <div style="font-family:'Share Tech Mono';font-size:8px;color:var(--dim);letter-spacing:2px;margin-bottom:4px">MARKET BRAIN</div>
  <div class="brain-sig" id="brain-sig" style="color:var(--gold)">LOADING...</div>
  <div class="brain-sub" id="brain-sub">Fetching NSE data...</div>
  <div id="reasons" style="margin-top:8px;font-family:'Share Tech Mono';font-size:9px;line-height:1.8"></div>
</div>

<button class="ref-btn" onclick="doFetch()">🔄 REFRESH NOW</button>
<button class="go-btn" id="go-btn" onclick="runClaude()">⚡ CLAUDE AI — FULL STRATEGY</button>

<div class="claude-box" id="claude-box" style="display:none">
  <div style="font-family:'Orbitron';font-size:8px;color:var(--gold);margin-bottom:8px">CLAUDE AI STRATEGY</div>
  <div id="claude-text" style="font-size:13px;line-height:1.9"></div>
</div>

</div>

<div class="wsbar">
  <div class="wsdot" id="wsdot"></div>
  <span id="ws-txt">Connecting...</span>
  <span id="ws-cnt" style="margin-left:auto;color:var(--dim)"></span>
</div>

<script>
let D={}, BR={}, SY={}, j_agents={};

// ── HTTP POLLING ──────────────────────────────────────────────────
async function poll(){
  try{
    const r = await fetch('/state', {signal: AbortSignal.timeout(10000)});
    if(!r.ok) throw new Error('HTTP '+r.status);
    const j = await r.json();
    D = j.market||{}; BR = j.brain||{}; SY = j.sys||{}; j_agents = j.agents||{};
    setOnline();
    render();
  }catch(e){
    setOffline('Retrying... '+e.message);
  }
}

function setOnline(){
  q('wsdot').className='wsdot on';
  q('live-badge').className='hlive on'; q('live-badge').textContent='LIVE';
  q('ws-txt').textContent='Connected ✓ — '+D.source;
}
function setOffline(msg){
  q('wsdot').className='wsdot';
  q('live-badge').className='hlive off'; q('live-badge').textContent='OFFLINE';
  q('ws-txt').textContent=msg||'Connecting...';
}

function render(){ const j_agents_local=j_agents||{};
  // Status bar
  const ms = SY.market_status||'';
  if(ms && ms!=='MARKET OPEN'){
    sdot('wait', ms);
    q('live-badge').className='hlive on'; // still connected
  } else {
    sdot('ok','Live #'+(SY.count||0)+' — '+(D.fetch_time||ist()));
  }
  q('ws-cnt').textContent=D.source||'';

  // Index
  const idx=SY.index||'NIFTY';
  q('ib-nifty').className='ib'+(idx==='NIFTY'?' on':'');
  q('ib-sensex').className='ib'+(idx==='SENSEX'?' on':'');

  if(D.spot){
    const sv = D.spot.toFixed(0);
    const av = 'ATM: '+(D.atm||'—');
    if(idx==='NIFTY'){
      tv('nv',sv,'var(--grn)'); t('na',av); t('n-spot',sv); t('n-atm',av);
      // Also show SENSEX if available
      if(D.sensex){ tv('sv',D.sensex.toFixed(0),'var(--grn)'); t('sa','ATM: '+(D.sensex_atm||'—')); t('s-spot',D.sensex.toFixed(0)); t('s-atm','ATM: '+(D.sensex_atm||'—')); }
    } else {
      tv('sv',sv,'var(--grn)'); t('sa',av); t('s-spot',sv); t('s-atm',av);
    }
  }

  if(D.vix){
    const vc = D.vix>20?'var(--red)':D.vix>15?'var(--gold)':'var(--grn)';
    tv('vv',D.vix.toFixed(1),vc);
    t('vn',D.vix>20?'HIGH FEAR':D.vix>15?'CAUTION':'CALM');
  }

  if(D.gift){
    const gd=D.gift_diff||0;
    tv('gv',D.gift.toFixed(0),gd>=0?'var(--grn)':'var(--red)');
    tv('gc',(gd>=0?'▲+':'▼')+Math.abs(gd).toFixed(0)+' pts',gd>=0?'var(--grn)':'var(--red)');
    t('gs',gd>100?'BULLISH':gd>40?'MILD BULL':gd<-100?'BEARISH':gd<-40?'MILD BEAR':'NEUTRAL');
  }

  // OI
  if(D.call_oi){
    t('callOI',fmtOI(D.call_oi)); t('putOI',fmtOI(D.put_oi));
    const pcr=D.pcr||1;
    tv('pcrVal',pcr.toFixed(2),pcr>1.2?'var(--grn)':pcr<0.7?'var(--red)':'var(--gold)');
    q('pcrFill').style.width=Math.min(100,pcr/2*100)+'%';
    q('pcrFill').style.background=pcr>1.2?'var(--grn)':pcr<0.7?'var(--red)':'var(--gold)';
    tv('pcrSig',pcr>1.2?'📈 BULLISH — PCR above 1.2':pcr<0.7?'📉 BEARISH — PCR low':'⚖️ NEUTRAL',
       pcr>1.2?'var(--grn)':pcr<0.7?'var(--red)':'var(--gold)');
    q('oi-src').className='badge live'; q('oi-src').textContent='🟢 NSE REAL';
  }
  if(D.support) tv('support',D.support.toLocaleString('en-IN'),'var(--grn)');
  if(D.resistance) tv('resistance',D.resistance.toLocaleString('en-IN'),'var(--red)');
  if(D.ce_prem){ tv('cePrem','₹'+D.ce_prem.toFixed(0),'var(--grn)'); q('prem-src').className='badge live'; q('prem-src').textContent='🟢 REAL'; }
  if(D.pe_prem) tv('pePrem','₹'+D.pe_prem.toFixed(0),'var(--red)');

  // Agents L1-L13
  const AG=j_agents_local||{};
  let hasData=false;
  for(const [aid,a] of Object.entries(AG)){
    const card=document.getElementById('card-'+aid);
    const sigEl=document.getElementById('sig-'+aid);
    const valEl=document.getElementById('val-'+aid);
    if(!card) continue;
    const d=a.signal||'none';
    card.className='agc '+(d==='bull'||d==='bear'||d==='neut'?d:'');
    if(sigEl){ sigEl.className='ag-sig '+d; sigEl.textContent=d==='bull'?'▲ BULL':d==='bear'?'▼ BEAR':d==='neut'?'◆ HOLD':'—'; }
    if(valEl) valEl.textContent=a.detail||'—';
    if(d!=='none') hasData=true;
  }
  document.getElementById('ag-badge').className='badge '+(hasData?'live':'wait');
  document.getElementById('ag-badge').textContent=hasData?'● LIVE':'WAITING';
  // Confidence
  const bp_=BR.bull_pct||50, brp_=BR.bear_pct||50;
  document.getElementById('conf-bull').style.width=bp_+'%';
  document.getElementById('conf-bear').style.width=brp_+'%';
  t('bp',bp_+'%'); t('brp',brp_+'%');
  t('conf-mid','Confidence: '+(BR.confidence||'—'));

  // Brain
  const sig=BR.signal||'WAIT';
  const cls=sig==='BUY CE'?'bull':sig==='BUY PE'?'bear':'wait';
  const col={bull:'var(--grn)',bear:'var(--red)',wait:'var(--gold)'}[cls];
  const lbl={bull:'🟢 BUY CE — BULLISH',bear:'🔴 BUY PE — BEARISH',wait:'⏳ WAIT — HOLD'}[cls];
  q('brain-box').className='brain-box '+cls;
  tv('brain-sig',lbl,col);
  t('brain-sub',(D.source||'')+'  Bull:'+(BR.bull_pct||50)+'% Bear:'+(BR.bear_pct||50)+'%  Conf:'+(BR.confidence||'—'));
  if(BR.reasons&&BR.reasons.length)
    q('reasons').innerHTML=BR.reasons.map(r=>'▸ '+r).join('<br>');
}

// ── ACTIONS ──────────────────────────────────────────────────────
async function connectAngel(){
  const ak=q('api-key').value.trim()||'jYAKgdt3';
  const ci=q('client-id').value.trim()||'V542909';
  const pin=q('angel-pin').value.trim()||'1818';
  const ts=q('totp-secret').value.trim()||'KJ4MRMUWNTFTCUALRBH5ALKA7A';
  q('angel-btn').textContent='Connecting...';
  try{
    const r=await fetch('/connect_angel',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({api_key:ak,client_id:ci,pin:pin,totp_secret:ts})});
    const j=await r.json();
    if(j.ok){ q('angel-st').textContent='● LIVE'; q('angel-st').style.color='var(--pur)'; q('angel-btn').textContent='✅ CONNECTED'; }
    else{ q('angel-btn').textContent='CONNECT ANGEL ONE'; sdot('err',j.error||'Failed'); }
  }catch(e){ q('angel-btn').textContent='CONNECT ANGEL ONE'; sdot('err','Network error'); }
}

async function setYahoo(){
  sdot('wait','Yahoo mode...');
  await fetch('/set_yahoo',{method:'POST'}).catch(()=>{});
  setTimeout(poll,1000);
}

function setIdx(idx){
  q('ib-nifty').className='ib'+(idx==='NIFTY'?' on':'');
  q('ib-sensex').className='ib'+(idx==='SENSEX'?' on':'');
  fetch('/set_index',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({index:idx})}).then(()=>setTimeout(poll,2000)).catch(()=>{});
}

async function doFetch(){
  sdot('wait','Fetching...');
  await fetch('/do_fetch',{method:'POST'}).catch(()=>{});
  setTimeout(poll,3000);
}

async function runClaude(){
  const key=getKey();
  if(!key){ alert('CLAUDE AI KEY box\u00e0\u00ae\u00b2\u00e0\u00af\u008d sk-ant-... paste \u00e0\u00ae\u00aa\u00e0\u00ae\u00a3\u00e0\u00af\u008d\u00e0\u00ae\u00a3\u00e0\u00af\u008d\u00e0\u00ae\u0095!'); return; }
  if(!D.spot){ alert('REFRESH NOW press \u00e0\u00ae\u00aa\u00e0\u00ae\u00a3\u00e0\u00af\u008d\u00e0\u00ae\u00a3\u00e0\u00af\u008d\u00e0\u00ae\u0095!'); return; }
  const btn=q('go-btn'); btn.disabled=true; btn.innerHTML='<span class="sp"></span>Computing...';
  q('claude-box').style.display='block';
  q('claude-text').innerHTML='<span style="color:var(--gold)">Analysing...</span>';
  const prompt=`MATHAN X AI — Live Data:
NIFTY: ${D.spot?.toFixed(0)||'N/A'} | ATM: ${D.atm||'N/A'}
VIX: ${D.vix?.toFixed(1)||'N/A'} | PCR: ${D.pcr||'N/A'}
GIFT: ${D.gift?.toFixed(0)||'N/A'} (${D.gift_diff>=0?'+':''}${D.gift_diff||0} pts)
CE: ₹${D.ce_prem?.toFixed(0)||'N/A'} | PE: ₹${D.pe_prem?.toFixed(0)||'N/A'}
Support: ${D.support||'N/A'} | Resistance: ${D.resistance||'N/A'}
Signal: ${BR.signal} | Bull:${BR.bull_pct}% Bear:${BR.bear_pct}% | ${BR.confidence}
Reasons: ${(BR.reasons||[]).join(', ')}

Give Chairman Mathan Sir:
1. FINAL CALL with reason
2. Strike: ATM/OTM
3. Entry condition
4. SL exact ₹
5. T1/T2 targets
6. Risk warning

Tamil+English mixed. Bold key numbers.`;
  try{
    const r=await fetch('https://api.anthropic.com/v1/messages',{
      method:'POST',
      headers:{'Content-Type':'application/json','x-api-key':key,'anthropic-version':'2023-06-01','anthropic-dangerous-direct-browser-access':'true'},
      body:JSON.stringify({model:'claude-sonnet-4-20250514',max_tokens:700,messages:[{role:'user',content:prompt}]}),
      signal:AbortSignal.timeout(35000)
    });
    const j=await r.json();
    q('claude-text').innerHTML=(j?.content?.[0]?.text||'Error')
      .replace(/\n/g,'<br>')
      .replace(/\*\*(.*?)\*\*/g,'<strong style="color:var(--gold)">$1</strong>');
  }catch(e){
    q('claude-text').innerHTML='<span style="color:var(--red)">Error — Retry</span>';
  }
  btn.disabled=false; btn.innerHTML='⚡ CLAUDE AI — FULL STRATEGY';
  q('claude-box').scrollIntoView({behavior:'smooth'});
}

function saveKey(){ const v=q('ki').value.trim(); if(v.startsWith('sk-ant')) try{localStorage.setItem('mbk',v);}catch(e){} }
function getKey(){ const v=q('ki').value.trim(); return v.startsWith('sk-ant')?v:(localStorage.getItem('mbk')||''); }
function fmtOI(n){ if(!n)return'—'; if(n>10000000)return(n/10000000).toFixed(1)+'Cr'; if(n>100000)return(n/100000).toFixed(1)+'L'; return(n/1000).toFixed(0)+'K'; }
function sdot(s,txt){ q('sdot').className='sdot '+s; q('stxt').textContent=txt; q('stxt').style.color=s==='ok'?'var(--grn)':s==='err'?'var(--red)':'var(--gold)'; }
function q(i){ return document.getElementById(i); }
function t(i,v){ const e=q(i); if(e) e.textContent=v; }
function tv(i,v,c){ const e=q(i); if(e){ e.textContent=v; if(c) e.style.color=c; } }
function ist(){ const n=new Date(new Date().toLocaleString('en-US',{timeZone:'Asia/Kolkata'})); return [n.getHours(),n.getMinutes(),n.getSeconds()].map(x=>String(x).padStart(2,'0')).join(':'); }

setInterval(()=>{ const ts=ist(); t('clock',ts); t('rtxt','IST '+ts); },1000);

function loadSaved(){
  const k=localStorage.getItem('mbk'); if(k) q('ki').value=k;
}

window.onload=()=>{
  loadSaved();
  poll();
  setInterval(poll, 8000);
};
</script>
</body>
</html>"""

# ── REST ROUTES ──────────────────────────────────────────────────────
@app.route("/")
@app.route("/dashboard")
def dashboard():
    return Response(HTML, mimetype="text/html")

@app.route("/state")
def state_route():
    with LOCK:
        return jsonify({
            "market": dict(M),
            "brain":  dict(BRAIN),
            "agents": {k:dict(v) for k,v in AGENTS.items()},
            "sys":    {**dict(SYS), "angel_ok": ANGEL["connected"],
                       "market_status": SYS.get("market_status","CHECKING")},
        })

@app.route("/status")
def status_route():
    with LOCK:
        return jsonify({"market": dict(M), "brain": dict(BRAIN), "sys": dict(SYS)})

@app.route("/ping")
def ping():
    return jsonify({"pong": True, "time": ist(), "source": M.get("source")})

@app.route("/connect_angel", methods=["POST"])
def connect_angel():
    d = request.get_json(force=True) or {}
    ak  = d.get("api_key",  ANGEL["api_key"]).strip()
    ci  = d.get("client_id",ANGEL["client_id"]).strip()
    pin = d.get("pin",      ANGEL["pin"]).strip()
    ts  = d.get("totp_secret",ANGEL["totp_secret"]).strip()
    if not all([ak, ci, pin, ts]):
        return jsonify({"ok": False, "error": "All 4 fields required"}), 400
    try:
        from SmartApi import SmartConnect
        totp = pyotp.TOTP(ts).now()
        obj  = SmartConnect(api_key=ak)
        data = obj.generateSession(ci, pin, totp)
        if not data or data.get("status") is False:
            msg = data.get("message","Login failed") if data else "No response"
            return jsonify({"ok": False, "error": msg}), 401
        ANGEL.update({"api_key":ak,"client_id":ci,"pin":pin,"totp_secret":ts,
                      "jwt_token":data["data"]["jwtToken"],"connected":True})
        SYS["angel_ok"] = True
        print(f"[ANGEL] Login OK: {ci}")
        threading.Thread(target=full_cycle, daemon=True).start()
        return jsonify({"ok": True, "msg": "Angel One connected!"})
    except ImportError:
        return jsonify({"ok": False, "error": "SmartAPI not installed on server"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/set_yahoo", methods=["POST"])
def set_yahoo():
    with LOCK: SYS["error"] = None
    threading.Thread(target=full_cycle, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/set_index", methods=["POST"])
def set_index():
    idx = (request.get_json(force=True) or {}).get("index","NIFTY").upper()
    if idx in INDEX_CFG:
        with LOCK: SYS["index"] = idx
        threading.Thread(target=full_cycle, daemon=True).start()
    return jsonify({"ok": True, "index": idx})

@app.route("/do_fetch", methods=["POST"])
def do_fetch():
    threading.Thread(target=full_cycle, daemon=True).start()
    return jsonify({"ok": True})

# ── STARTUP ──────────────────────────────────────────────────────────
def wake_dhan():
    try:
        print("[WAKE] Pinging Dhan backend...")
        requests.get("https://mathan-backend.onrender.com/", timeout=35)
        print("[WAKE] Dhan backend awake!")
    except Exception as e:
        print(f"[WAKE ERR] {e}")

if __name__ == "__main__":
    print(f"[START] MATHAN AI — Port {PORT}")
    # Wake Dhan backend first
    threading.Thread(target=wake_dhan, daemon=True).start()
    # Initial data fetch after delay
    def delayed_start():
        time.sleep(8)
        full_cycle()
    threading.Thread(target=delayed_start, daemon=True).start()
    # Background polling
    threading.Thread(target=poll_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False, threaded=True)
