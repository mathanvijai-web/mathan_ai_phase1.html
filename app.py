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
SYS = {"count": 0, "error": None, "index": "NIFTY", "angel_ok": False}
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
    """Yahoo fallback for VIX + GIFT + spot."""
    idx = SYS.get("index", "NIFTY")
    sym = {"NIFTY": "%5ENSEI", "SENSEX": "%5EBSESN"}[idx]
    hdrs = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
            params={"interval": "1m", "range": "1d"},
            headers=hdrs, timeout=10)
        meta = r.json()["chart"]["result"][0]["meta"]
        sp = meta.get("regularMarketPrice", 0)
        pv = meta.get("previousClose", sp)
        if sp:
            cfg = INDEX_CFG[idx]
            with LOCK:
                if not M["spot"]:
                    M["spot"] = sp
                    M["atm"] = round(sp / cfg["step"]) * cfg["step"]
                    M["source"] = "Yahoo"
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
        pcr = M["pcr"]; vix = M["vix"]; spot = M["spot"]
        atm = M["atm"]; gd = M["gift_diff"]
        ce = M["ce_prem"]; pe = M["pe_prem"]
        sup = M["support"]; res = M["resistance"]
        exp = M["exp_days"]

    bull = bear = 0.0; reasons = []
    mins = ist_mins()

    # PCR
    if pcr:
        if pcr > 1.5:   bull += 1.5; reasons.append(f"PCR {pcr} STRONG BULL")
        elif pcr > 1.2: bull += 1.0; reasons.append(f"PCR {pcr} BULLISH")
        elif pcr < 0.6: bear += 1.5; reasons.append(f"PCR {pcr} STRONG BEAR")
        elif pcr < 0.8: bear += 1.0; reasons.append(f"PCR {pcr} BEARISH")

    # VIX
    if vix:
        if vix > 22:   bear += 2.0; reasons.append(f"VIX {vix:.1f} EXTREME DANGER")
        elif vix > 18: bear += 1.0; reasons.append(f"VIX {vix:.1f} HIGH FEAR")
        elif vix < 13: bull += 1.0; reasons.append(f"VIX {vix:.1f} CALM")

    # Price vs ATM
    if spot and atm:
        if spot > atm + 50:   bull += 0.5; reasons.append("Above ATM — Bullish")
        elif spot < atm - 50: bear += 0.5; reasons.append("Below ATM — Bearish")

    # GIFT
    if gd:
        if gd > 100:    bull += 0.8; reasons.append(f"GIFT +{round(gd)} Gap Up")
        elif gd < -100: bear += 0.8; reasons.append(f"GIFT {round(gd)} Gap Down")

    # Session
    if 570 <= mins <= 615:   bull += 1.0; reasons.append("OPEN HOUR — High momentum")
    elif 615 <= mins <= 780: bull += 0.5; reasons.append("Morning session")

    # Expiry
    if exp == 0: reasons.append("EXPIRY DAY — Theta max")

    # Trap
    trap = False
    if vix and vix > 20 and pcr and pcr > 1.2:
        trap = True; reasons.append(f"⚠️ VIX {vix:.1f} + PCR {pcr} — Possible trap")

    tot = bull + bear or 1
    bp = round(bull / tot * 100)
    brp = 100 - bp
    diff = abs(bull - bear)
    conf = "HIGH" if diff >= 3 else "MEDIUM" if diff >= 1.5 else "LOW"

    if trap:             sig = "WAIT"
    elif bp >= 65:       sig = "BUY CE"
    elif brp >= 65:      sig = "BUY PE"
    else:                sig = "WAIT"

    with LOCK:
        BRAIN.update({
            "signal": sig, "bull_pct": bp, "bear_pct": brp,
            "confidence": conf, "reasons": reasons[:6], "trap": trap
        })

def full_cycle():
    idx = SYS.get("index", "NIFTY")
    # Try NSE OI first
    nse_ok = fetch_nse_oi(idx)
    # Always get VIX + GIFT from Yahoo
    threading.Thread(target=fetch_yahoo, daemon=True).start()
    if not nse_ok:
        with LOCK: SYS["error"] = "NSE OI failed — using Yahoo"
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
let D={}, BR={}, SY={};

// ── HTTP POLLING ──────────────────────────────────────────────────
async function poll(){
  try{
    const r = await fetch('/state', {signal: AbortSignal.timeout(10000)});
    if(!r.ok) throw new Error('HTTP '+r.status);
    const j = await r.json();
    D = j.market||{}; BR = j.brain||{}; SY = j.sys||{};
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

function render(){
  // Status bar
  sdot('ok','Live #'+(SY.count||0)+' — '+(D.fetch_time||ist()));
  q('ws-cnt').textContent=D.source||'';

  // Index
  const idx=SY.index||'NIFTY';
  q('ib-nifty').className='ib'+(idx==='NIFTY'?' on':'');
  q('ib-sensex').className='ib'+(idx==='SENSEX'?' on':'');

  if(D.spot){
    const sv = D.spot.toFixed(0);
    const av = 'ATM: '+(D.atm||'—');
    if(idx==='NIFTY'){ tv('nv',sv,'var(--grn)'); t('na',av); t('n-spot',sv); t('n-atm',av); }
    else              { tv('sv',sv,'var(--grn)'); t('sa',av); t('s-spot',sv); t('s-atm',av); }
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
  if(!key||!D.spot){ alert('API key or data missing'); return; }
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
            "sys":    {**dict(SYS), "angel_ok": ANGEL["connected"]},
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
if __name__ == "__main__":
    print(f"[START] MATHAN AI — Port {PORT}")
    # Initial data fetch
    threading.Thread(target=full_cycle, daemon=True).start()
    # Background polling
    threading.Thread(target=poll_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False, threaded=True)
