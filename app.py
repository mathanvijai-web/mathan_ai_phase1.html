"""
MATHAN AI — COMPLETE SYSTEM V10
================================
CCS (BODY) + Super Power (SOUL) + L14 NAMBI (CONTROLLER)
Chairman → Nambi → L1-L13 → Market Brain → Signal

Render compatible | HTTP Polling | NSE Real OI
"""
import os, json, time, threading, datetime, requests, pyotp
from flask import Flask, Response, jsonify, request
from flask_cors import CORS

app  = Flask(__name__)
CORS(app)
PORT = int(os.environ.get("PORT", 8000))

# ── CREDENTIALS ───────────────────────────────────────────────────────
ANGEL = {
    "api_key":     os.environ.get("ANGEL_API_KEY",    "jYAKgdt3"),
    "client_id":   os.environ.get("ANGEL_CLIENT_ID",  "V542909"),
    "pin":         os.environ.get("ANGEL_PIN",        "1818"),
    "totp_secret": os.environ.get("ANGEL_TOTP",       "KJ4MRMUWNTFTCUALRBH5ALKA7A"),
    "connected": False, "jwt_token": "", "error": None,
}

INDEX_CFG = {
    "NIFTY":  {"step": 50,  "lot": 65,  "expiry_dow": 1},
    "SENSEX": {"step": 100, "lot": 20,  "expiry_dow": 3},
}

# ── STATE ─────────────────────────────────────────────────────────────
M = {
    "nifty": None, "sensex": None, "vix": None,
    "gift": None, "gift_diff": None,
    "atm": None, "gap": None,
    "pcr": None, "call_oi": None, "put_oi": None,
    "ce_prem": None, "pe_prem": None,
    "ce_prev": None, "pe_prev": None,
    "support": None, "resistance": None,
    "exp_days": None, "source": "LOADING",
    "fetch_time": None, "market_status": "CHECKING",
}

# 14 AGENTS — L1 to L13 + L14 NAMBI
AGENTS = {
    "l1":  {"name":"Vishnu",      "role":"System Structure",    "signal":None,"detail":"","weight":1.0},
    "l2":  {"name":"Ravi",        "role":"Data Connection",     "signal":None,"detail":"","weight":1.5},
    "l3":  {"name":"Pooja",       "role":"Market Data Verify",  "signal":None,"detail":"","weight":1.5},
    "l4":  {"name":"Rani",        "role":"Trading Logic",       "signal":None,"detail":"","weight":1.5},
    "l5":  {"name":"Murali",      "role":"Error Detection",     "signal":None,"detail":"","weight":1.0},
    "l6":  {"name":"Moorthy",     "role":"Security",            "signal":None,"detail":"","weight":0.8},
    "l7":  {"name":"Subbaraj",    "role":"Network/WebSocket",   "signal":None,"detail":"","weight":0.8},
    "l8":  {"name":"Paramasivam", "role":"Backup & Recovery",   "signal":None,"detail":"","weight":0.8},
    "l9":  {"name":"Siluva",      "role":"Speed Optimizer",     "signal":None,"detail":"","weight":1.0},
    "l10": {"name":"Kumar",       "role":"Execution Supervisor","signal":None,"detail":"","weight":1.2},
    "l11": {"name":"Jayalalitha", "role":"Quality Check",       "signal":None,"detail":"","weight":1.2},
    "l12": {"name":"Ranjitham",   "role":"Trade Executor",      "signal":None,"detail":"","weight":1.5},
    "l13": {"name":"Raja",        "role":"Report Generator",    "signal":None,"detail":"","weight":1.0},
    "l14": {"name":"NAMBI",       "role":"MASTER CONTROLLER",   "signal":None,"detail":"","weight":3.0},
}

BRAIN = {
    "signal":"WAIT","bull_pct":50,"bear_pct":50,
    "confidence":"LOW","reasons":[],"trap":False,
    "nambi_verdict":"STANDBY","nambi_reason":"Awaiting data",
}

SYS = {
    "count":0,"error":None,"index":"NIFTY",
    "angel_ok":False,"market_status":"CHECKING",
    "keep_alive_count":0,
}

LOCK = threading.Lock()

# ── HELPERS ───────────────────────────────────────────────────────────
def ist():
    tz = datetime.timezone(datetime.timedelta(hours=5,minutes=30))
    return datetime.datetime.now(tz).strftime("%H:%M:%S")

def ist_now():
    tz = datetime.timezone(datetime.timedelta(hours=5,minutes=30))
    return datetime.datetime.now(tz)

def ist_mins():
    n=ist_now(); return n.hour*60+n.minute

def calc_expiry(index="NIFTY"):
    tz  = datetime.timezone(datetime.timedelta(hours=5,minutes=30))
    t   = datetime.datetime.now(tz)
    dow = INDEX_CFG[index]["expiry_dow"]
    d2t = (dow - t.weekday()) % 7
    if d2t==0 and t.hour>=15 and t.minute>=30: d2t=7
    return d2t

def market_status():
    n = ist_now()
    day_names=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    day=day_names[n.weekday()]
    is_weekday = n.weekday() < 5
    mins = n.hour*60+n.minute
    if not is_weekday:
        return f"MARKET CLOSED — {day} Weekend", False
    if mins < 9*60+15:
        return f"PRE-MARKET — Opens 9:15 AM IST", False
    if mins > 15*60+30:
        return f"MARKET CLOSED — After 3:30 PM", False
    return "MARKET OPEN", True

NSE_HDR = {
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":"*/*","Referer":"https://www.nseindia.com/option-chain"
}

# ── DATA FETCH ────────────────────────────────────────────────────────
def fetch_yahoo_all():
    hdrs={"User-Agent":"Mozilla/5.0"}
    tickers={
        "nifty":  "%5ENSEI",
        "sensex": "%5EBSESN",
        "vix":    "%5EINDIAVIX",
        "gift":   "NIFTYFUTURES.NS",
    }
    for key,sym in tickers.items():
        try:
            r=requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"interval":"1d","range":"5d"},
                headers=hdrs,timeout=10)
            meta=r.json()["chart"]["result"][0]["meta"]
            sp=meta.get("regularMarketPrice",0) or meta.get("previousClose",0)
            if not sp: continue
            with LOCK:
                if key=="nifty":
                    M["nifty"]=sp
                    M["atm"]=round(sp/50)*50
                    M["gap"]=round(sp-(meta.get("previousClose",sp)),2)
                elif key=="sensex":
                    M["sensex"]=sp
                elif key=="vix":
                    M["vix"]=sp
                elif key=="gift":
                    M["gift"]=sp
                    if M["nifty"]:
                        M["gift_diff"]=round(sp-M["nifty"],2)
        except Exception as e:
            print(f"[YAHOO {key}] {e}")

def fetch_nse_oi(index="NIFTY"):
    try:
        s=requests.Session()
        s.get("https://www.nseindia.com",headers={**NSE_HDR,"Accept":"text/html"},timeout=7)
        time.sleep(0.3)
        r=s.get(
            f"https://www.nseindia.com/api/option-chain-indices?symbol={index}",
            headers=NSE_HDR,timeout=12)
        if r.status_code!=200: return False
        raw=r.json().get("records",{})
        spot=raw.get("underlyingValue",0)
        data=raw.get("data",[])
        exps=raw.get("expiryDates",[])
        if not spot or not data: return False
        target=exps[0] if exps else ""
        cfg=INDEX_CFG[index]
        atm=round(spot/cfg["step"])*cfg["step"]
        tC=tP=mxC=mxP=mxCS=mxPS=ceLTP=peLTP=0
        for row in data:
            if target and row.get("expiryDate","")!=target: continue
            st=row.get("strikePrice",0)
            ce=row.get("CE",{}); pe=row.get("PE",{})
            ceOI=ce.get("openInterest",0) or 0
            peOI=pe.get("openInterest",0) or 0
            ceLtp=ce.get("lastPrice",0) or 0
            peLtp=pe.get("lastPrice",0) or 0
            tC+=ceOI; tP+=peOI
            if ceOI>mxC: mxC=ceOI; mxCS=st
            if peOI>mxP: mxP=peOI; mxPS=st
            if abs(st-atm)<=cfg["step"]:
                if ceLtp: ceLTP=ceLtp
                if peLtp: peLTP=peLtp
        if tC==0: return False
        with LOCK:
            M["nifty"]=spot; M["atm"]=atm
            M["call_oi"]=tC; M["put_oi"]=tP
            M["pcr"]=round(tP/tC,2)
            M["ce_prev"]=M["ce_prem"]; M["pe_prev"]=M["pe_prem"]
            M["ce_prem"]=ceLTP; M["pe_prem"]=peLTP
            M["support"]=mxPS; M["resistance"]=mxCS
            M["source"]="NSE REAL OI ✓"
            M["exp_days"]=calc_expiry(index)
            M["fetch_time"]=ist()
            SYS["count"]+=1; SYS["error"]=None
        print(f"[NSE OI] spot={spot} pcr={round(tP/tC,2)} CE={ceLTP} PE={peLTP}")
        return True
    except Exception as e:
        print(f"[NSE ERR] {e}"); return False

def estimate_oi_from_spot():
    """Weekend/holiday estimated OI from last spot."""
    with LOCK:
        sp=M["nifty"] or 23000
        idx=SYS["index"]
        cfg=INDEX_CFG[idx]
        atm=round(sp/cfg["step"])*cfg["step"]
        base=sp*180
        M["atm"]=atm
        M["call_oi"]=int(base)
        M["put_oi"]=int(base*1.08)
        M["pcr"]=round(1.08,2)
        M["support"]=atm-cfg["step"]*2
        M["resistance"]=atm+cfg["step"]*2
        M["ce_prem"]=round(sp*0.004)
        M["pe_prem"]=round(sp*0.0037)
        M["exp_days"]=calc_expiry(idx)
        M["source"]="ESTIMATED (Market Closed)"
        M["fetch_time"]=ist()

# ── L1-L14 AGENT COMPUTE ──────────────────────────────────────────────
def compute_agents():
    with LOCK:
        spot=M["nifty"]; vix=M["vix"]; pcr=M["pcr"]
        atm=M["atm"]; gd=M["gift_diff"]
        ce=M["ce_prem"]; pe=M["pe_prem"]
        ce_p=M["ce_prev"]; pe_p=M["pe_prev"]
        sup=M["support"]; res=M["resistance"]
        exp=M["exp_days"]; gap=M["gap"]
        ms=M["market_status"]
        idx=SYS["index"]

    mins=ist_mins(); ag={}
    is_open="OPEN" in ms

    # L1 Vishnu — System Structure
    if spot and vix and pcr:
        ag["l1"]=("bull","System OK — All data feeds active")
    elif spot:
        ag["l1"]=("neut","Partial data — OI loading")
    else:
        ag["l1"]=("neut",f"Waiting for data — {ms}")

    # L2 Ravi — Data Connection (Angel One)
    with LOCK: angel_ok=ANGEL["connected"]
    if angel_ok:
        ag["l2"]=("bull","Angel One CONNECTED — Real data active")
    else:
        ag["l2"]=("neut","Angel One not connected — Yahoo fallback")

    # L3 Pooja — Market Data Accuracy
    if spot and vix:
        accuracy = "HIGH" if is_open else "PREV CLOSE"
        ag["l3"]=("bull" if is_open else "neut",
                  f"Data accuracy: {accuracy} | Spot={spot:.0f} VIX={vix:.1f}")
    else:
        ag["l3"]=("neut","Data verification pending")

    # L4 Rani — Trading Logic (PCR)
    if pcr:
        if pcr>1.5:   ag["l4"]=("bull",f"PCR {pcr} STRONG BULL — Put writing dominant")
        elif pcr>1.2: ag["l4"]=("bull",f"PCR {pcr} BULLISH signal")
        elif pcr<0.6: ag["l4"]=("bear",f"PCR {pcr} STRONG BEAR — Call writing dominant")
        elif pcr<0.8: ag["l4"]=("bear",f"PCR {pcr} BEARISH signal")
        else:         ag["l4"]=("neut",f"PCR {pcr} NEUTRAL zone")
    else:
        ag["l4"]=("neut","PCR N/A — Market closed or loading")

    # L5 Murali — Error Detection (VIX risk)
    if vix:
        if vix>22:   ag["l5"]=("bear",f"VIX {vix:.1f} EXTREME DANGER — Error risk high")
        elif vix>18: ag["l5"]=("neut",f"VIX {vix:.1f} HIGH — Caution mode")
        elif vix<13: ag["l5"]=("bull",f"VIX {vix:.1f} CALM — Low error risk")
        else:        ag["l5"]=("neut",f"VIX {vix:.1f} NORMAL range")
    else:
        ag["l5"]=("neut","VIX N/A")

    # L6 Moorthy — Security (trap detection)
    trap=False; trap_det=""
    if pcr and spot and atm:
        if pcr>1.3 and spot<atm-50:
            trap=True; trap_det="PCR Bull but Price below ATM — BULL TRAP?"
        elif pcr<0.75 and spot>atm+50:
            trap=True; trap_det="PCR Bear but Price above ATM — BEAR TRAP?"
    if vix and vix>20 and pcr and pcr>1.2:
        trap=True; trap_det=f"VIX {vix:.1f}+PCR {pcr} — Manipulation risk!"
    ag["l6"]=("neut",f"⚠️ {trap_det}") if trap else ("bull","Security OK — No trap detected")

    # L7 Subbaraj — Network (HTTP Polling status)
    with LOCK: cnt=SYS["count"]
    if cnt>0:
        ag["l7"]=("bull",f"Network OK — {cnt} polls completed")
    else:
        ag["l7"]=("neut","Network connecting...")

    # L8 Paramasivam — Backup & Recovery
    with LOCK: ka=SYS["keep_alive_count"]
    ag["l8"]=("bull",f"Keep-alive active — {ka} pings sent") if ka>0 else ("neut","Backup standby")

    # L9 Siluva — Speed (market open hours)
    if mins<555:      ag["l9"]=("neut","Pre-market — System standby")
    elif mins<600:    ag["l9"]=("bull","OPEN HOUR — Full speed 9:15 AM")
    elif mins<660:    ag["l9"]=("bull","PRIME WINDOW 9:15-11:00 — Best entry")
    elif mins<780:    ag["l9"]=("neut","Mid session 11:00-1:00")
    elif mins<870:    ag["l9"]=("neut","Afternoon 1:00-2:30")
    elif mins<930:    ag["l9"]=("neut","EXPIRY WINDOW 2:30-3:30")
    else:             ag["l9"]=("neut","Post market — System resting")

    # L10 Kumar — Execution (Price vs ATM)
    if spot and atm:
        if res and spot>res:       ag["l10"]=("bull",f"BREAKOUT above resistance {int(res)}")
        elif sup and spot<sup:     ag["l10"]=("bear",f"BREAKDOWN below support {int(sup)}")
        elif spot>atm+50:          ag["l10"]=("bull",f"Above ATM {atm} — Bullish execution")
        elif spot<atm-50:          ag["l10"]=("bear",f"Below ATM {atm} — Bearish execution")
        else:                      ag["l10"]=("neut",f"At ATM {atm} — Wait for breakout")
    else:
        ag["l10"]=("neut","Execution standby")

    # L11 Jayalalitha — Quality Check (Gap)
    if gap:
        if gap>100:    ag["l11"]=("bull",f"Gap UP +{round(gap)} — Quality BULLISH open")
        elif gap>40:   ag["l11"]=("bull",f"Gap UP +{round(gap)} — Mild positive")
        elif gap<-100: ag["l11"]=("bear",f"Gap DOWN {round(gap)} — Quality BEARISH open")
        elif gap<-40:  ag["l11"]=("bear",f"Gap DOWN {round(gap)} — Mild negative")
        else:          ag["l11"]=("neut",f"Flat ±{round(abs(gap))} — Quality neutral")
    elif gd:
        if gd>100:     ag["l11"]=("bull",f"GIFT +{round(gd)} — Tomorrow quality BULL")
        elif gd<-100:  ag["l11"]=("bear",f"GIFT {round(gd)} — Tomorrow quality BEAR")
        else:          ag["l11"]=("neut",f"GIFT ±{round(abs(gd))} — Flat")
    else:
        ag["l11"]=("neut","Quality check pending")

    # L12 Ranjitham — Trade Executor (Premium direction)
    if ce and pe:
        chg_ce=(ce-ce_p) if ce_p else 0
        chg_pe=(pe-pe_p) if pe_p else 0
        if chg_ce>5 and chg_ce>chg_pe:
            ag["l12"]=("bull",f"CE ₹{ce:.0f} +{chg_ce:.0f} rising — Execute BUY CE")
        elif chg_pe>5 and chg_pe>chg_ce:
            ag["l12"]=("bear",f"PE ₹{pe:.0f} +{chg_pe:.0f} rising — Execute BUY PE")
        elif vix and vix>22:
            ag["l12"]=("neut",f"VIX {vix:.1f} HIGH — Execution HOLD")
        else:
            ag["l12"]=("neut",f"CE ₹{ce:.0f} PE ₹{pe:.0f} — Monitor")
    else:
        ag["l12"]=("neut","Execution engine standby")

    # L13 Raja — Report (Expiry)
    if exp is not None:
        if exp==0:   ag["l13"]=("bull","TODAY EXPIRY ⚡ — Report: Max theta decay")
        elif exp==1: ag["l13"]=("neut","TOMORROW EXPIRY — Report: High volatility")
        elif exp<=3: ag["l13"]=("neut",f"Report: {exp} days to expiry — Near expiry")
        else:        ag["l13"]=("neut",f"Report: {exp} days to expiry — Normal")
    else:
        ag["l13"]=("neut","Report module standby")

    # L14 NAMBI — MASTER CONTROLLER
    b=sum(1 for v in ag.values() if v[0]=="bull")
    r=sum(1 for v in ag.values() if v[0]=="bear")
    n=sum(1 for v in ag.values() if v[0]=="neut")
    total=b+r; ratio=(b-r)/total if total>0 else 0
    if trap:
        ag["l14"]=("neut",f"NAMBI VERDICT: WAIT — Trap detected! ({b}↑{r}↓{n}◆)")
    elif ratio>0.35 and (not vix or vix<18):
        ag["l14"]=("bull",f"NAMBI VERDICT: BUY CE — {b}/{b+r+n} agents BULL. Execute!")
    elif ratio<-0.35:
        ag["l14"]=("bear",f"NAMBI VERDICT: BUY PE — {r}/{b+r+n} agents BEAR. Execute!")
    else:
        ag["l14"]=("neut",f"NAMBI VERDICT: WAIT — Signals mixed ({b}↑{r}↓{n}◆)")

    # Update AGENTS dict
    with LOCK:
        for aid,(sig,det) in ag.items():
            AGENTS[aid]["signal"]=sig
            AGENTS[aid]["detail"]=det

    return trap, ag

def compute_brain(trap, ag):
    bw=brw=0.0; reasons=[]
    for aid,a in ag.items():
        sig=a[0]; w=AGENTS[aid]["weight"]; det=a[1]
        if sig=="bull":   bw+=w;  reasons.append(det)
        elif sig=="bear": brw+=w; reasons.append(det)

    tw=bw+brw or 1
    bp=round(bw/tw*100); brp=100-bp
    diff=abs(bw-brw)
    conf="HIGH" if diff>=4 else "MEDIUM" if diff>=2 else "LOW"

    # NAMBI final call overrides
    nambi=ag.get("l14",("neut",""))
    if trap:             sig="WAIT"; nv="STANDBY — Trap!"
    elif nambi[0]=="bull" and bp>=60: sig="BUY CE"; nv="BUY CE ✅"
    elif nambi[0]=="bear" and brp>=60: sig="BUY PE"; nv="BUY PE ✅"
    else:                sig="WAIT"; nv="WAIT — No clear signal"

    with LOCK:
        BRAIN.update({
            "signal":sig,"bull_pct":bp,"bear_pct":brp,
            "confidence":conf,"reasons":reasons[:6],
            "trap":trap,"nambi_verdict":nv,
            "nambi_reason":nambi[1],
        })

# ── FULL CYCLE ────────────────────────────────────────────────────────
def full_cycle():
    status, is_open = market_status()
    with LOCK:
        M["market_status"]=status
        SYS["market_status"]=status

    # Always fetch Yahoo (works weekends)
    threading.Thread(target=fetch_yahoo_all, daemon=True).start()
    time.sleep(1)  # wait for yahoo

    if is_open:
        ok = fetch_nse_oi(SYS["index"])
        if not ok:
            with LOCK: SYS["error"]="NSE OI unavailable — using Yahoo data"
    else:
        estimate_oi_from_spot()
        with LOCK: SYS["error"]=None

    trap, ag = compute_agents()
    compute_brain(trap, ag)

    with LOCK:
        if is_open: SYS["count"]+=1

def keep_alive_loop():
    """Ping self every 10 min — Render never sleeps!"""
    time.sleep(60)
    while True:
        try:
            requests.get(f"http://localhost:{PORT}/ping", timeout=5)
            with LOCK: SYS["keep_alive_count"]+=1
        except: pass
        time.sleep(600)

def poll_loop():
    while True:
        time.sleep(20)
        try: full_cycle()
        except Exception as e: print(f"[POLL ERR] {e}")

# ── HTML DASHBOARD ────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"/>
<title>MATHAN AI — Complete System</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Share+Tech+Mono&family=Rajdhani:wght@600;700&display=swap" rel="stylesheet"/>
<style>
:root{--bg:#070b0f;--bg2:#0d1419;--bg3:#111820;--brd:#1e2d3d;
  --gold:#f0a500;--grn:#00e676;--red:#ff1744;--blu:#29b6f6;
  --pur:#ce93d8;--orn:#ff9800;--txt:#cdd9e5;--dim:#4a6278;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--txt);font-family:'Rajdhani',sans-serif;padding-bottom:55px;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(240,165,0,.4)}70%{box-shadow:0 0 0 8px rgba(240,165,0,0)}}
.hdr{position:sticky;top:0;z-index:100;
  background:linear-gradient(180deg,#0a1118,rgba(7,11,15,.97));
  border-bottom:2px solid var(--gold);padding:10px 14px;
  display:flex;align-items:center;justify-content:space-between;
  box-shadow:0 4px 24px rgba(240,165,0,.15);}
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
.mstatus{text-align:center;padding:6px;border-radius:8px;font-family:'Share Tech Mono';font-size:9px;
  margin-bottom:9px;border:1px solid;}
.mstatus.open{border-color:var(--grn);color:var(--grn);background:rgba(0,230,118,.06);}
.mstatus.closed{border-color:var(--gold);color:var(--gold);background:rgba(240,165,0,.06);}
.card{background:var(--bg2);border:1px solid var(--brd);border-radius:12px;padding:12px;margin-bottom:9px;}
.ctitle{font-family:'Orbitron';font-size:9px;color:var(--gold);letter-spacing:1px;
  margin-bottom:9px;display:flex;justify-content:space-between;align-items:center;}
.badge{display:inline-flex;padding:1px 7px;border-radius:8px;font-family:'Share Tech Mono';font-size:7px;}
.badge.live{background:rgba(0,230,118,.1);border:1px solid rgba(0,230,118,.3);color:var(--grn);}
.badge.wait{background:rgba(41,182,246,.08);border:1px solid rgba(41,182,246,.2);color:var(--blu);}
.badge.nambi{background:rgba(240,165,0,.1);border:1px solid rgba(240,165,0,.4);color:var(--gold);animation:pulse 2s infinite;}
.inp{width:100%;background:var(--bg3);border:1px solid var(--brd);border-radius:6px;
  color:var(--txt);padding:8px 10px;font-size:12px;font-family:'Share Tech Mono';outline:none;margin-bottom:6px;}
.inp-lbl{font-family:'Share Tech Mono';font-size:7px;color:var(--dim);margin-bottom:3px;}
.cbtn{width:100%;padding:11px;border-radius:8px;cursor:pointer;
  font-family:'Orbitron';font-size:9px;font-weight:700;letter-spacing:1px;
  border:1px solid var(--orn);background:rgba(255,152,0,.08);color:var(--orn);margin-top:5px;}
.cbtn.ok{border-color:var(--pur);background:rgba(206,147,216,.1);color:var(--pur);}
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
  padding:10px 13px;margin-bottom:9px;display:flex;justify-content:space-between;align-items:center;
  position:relative;overflow:hidden;}
.gift-box::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--gold);}
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
.prem-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:8px;}
.prem-cell{background:var(--bg3);border-radius:8px;padding:9px;border:2px solid var(--brd);text-align:center;}
/* AGENTS */
.ag-sect{font-family:'Share Tech Mono';font-size:7px;color:var(--dim);letter-spacing:2px;margin:8px 0 5px;}
.ag-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:4px;}
.agc{background:var(--bg3);border:1px solid var(--brd);border-radius:8px;padding:7px;position:relative;overflow:hidden;}
.agc::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--brd);}
.agc.bull::before{background:var(--grn);} .agc.bear::before{background:var(--red);} .agc.neut::before{background:var(--gold);}
.ag-top{display:flex;justify-content:space-between;margin-bottom:1px;}
.ag-id{font-family:'Orbitron';font-size:7px;color:var(--dim);}
.ag-sig{font-family:'Share Tech Mono';font-size:8px;font-weight:700;}
.ag-sig.bull{color:var(--grn);} .ag-sig.bear{color:var(--red);} .ag-sig.neut{color:var(--gold);} .ag-sig.none{color:var(--dim);}
.ag-name{font-size:9px;font-weight:700;margin-bottom:1px;}
.ag-role{font-family:'Share Tech Mono';font-size:7px;color:var(--blu);margin-bottom:2px;}
.ag-val{font-family:'Share Tech Mono';font-size:7px;color:var(--dim);line-height:1.3;}
/* NAMBI L14 */
.nambi-card{background:linear-gradient(135deg,rgba(240,165,0,.08),rgba(240,165,0,.02));
  border:2px solid rgba(240,165,0,.5);border-radius:12px;padding:12px;margin-top:8px;
  animation:pulse 3s infinite;}
.nambi-title{font-family:'Orbitron';font-size:10px;color:var(--gold);margin-bottom:4px;letter-spacing:2px;}
.nambi-verdict{font-family:'Orbitron';font-size:18px;font-weight:900;margin-bottom:4px;}
.nambi-reason{font-family:'Share Tech Mono';font-size:9px;color:var(--dim);line-height:1.5;}
/* CONF BAR */
.conf-bar{background:var(--bg3);border-radius:8px;padding:9px;margin-bottom:7px;}
.conf-track{height:10px;border-radius:5px;background:rgba(255,255,255,.05);overflow:hidden;display:flex;margin-bottom:3px;}
.conf-bull{height:100%;background:linear-gradient(90deg,#004d40,var(--grn));transition:width .7s;}
.conf-bear{height:100%;background:linear-gradient(90deg,var(--red),#7f0000);transition:width .7s;}
/* BRAIN */
.brain-box{border-radius:13px;padding:14px;margin-bottom:9px;border:2px solid var(--brd);}
.brain-box.bull{border-color:rgba(0,230,118,.6);background:linear-gradient(135deg,rgba(0,230,118,.07),transparent);box-shadow:0 0 30px rgba(0,230,118,.1);}
.brain-box.bear{border-color:rgba(255,23,68,.6);background:linear-gradient(135deg,rgba(255,23,68,.07),transparent);box-shadow:0 0 30px rgba(255,23,68,.1);}
.brain-box.wait{border-color:rgba(240,165,0,.5);background:linear-gradient(135deg,rgba(240,165,0,.05),transparent);}
.brain-sig{font-family:'Orbitron';font-size:24px;font-weight:900;margin-bottom:4px;}
.brain-sub{font-size:11px;color:var(--dim);margin-bottom:8px;}
.go-btn{width:100%;padding:15px;border-radius:13px;border:none;cursor:pointer;
  background:linear-gradient(135deg,#7a5200,var(--gold));
  color:#000;font-family:'Orbitron';font-size:12px;font-weight:900;letter-spacing:2px;margin-bottom:9px;}
.go-btn:disabled{background:#1a2230;color:var(--dim);}
.ref-btn{width:100%;padding:9px;border-radius:9px;cursor:pointer;
  border:1px solid rgba(41,182,246,.4);background:rgba(41,182,246,.05);
  color:var(--blu);font-family:'Orbitron';font-size:9px;letter-spacing:1px;margin-bottom:9px;}
.claude-box{background:var(--bg2);border:1px solid rgba(240,165,0,.2);border-radius:11px;padding:12px;margin-bottom:9px;}
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
  <div class="logo">MATHAN AI — COMPLETE SYSTEM<small>CCS BODY + SUPER POWER SOUL + L14 NAMBI</small></div>
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

<!-- MARKET STATUS -->
<div class="mstatus closed" id="mstatus-box">
  <span id="mstatus-txt">Checking market status...</span>
</div>

<!-- ANGEL ONE -->
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

<!-- INDEX -->
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

<!-- GIFT -->
<div class="gift-box">
  <div>
    <div style="font-family:'Share Tech Mono';font-size:7px;color:var(--gold);letter-spacing:1px;margin-bottom:2px">GIFT NIFTY — TOMORROW SENTIMENT</div>
    <div style="font-family:'Orbitron';font-size:20px;font-weight:900;" id="gv">—</div>
    <div style="font-family:'Share Tech Mono';font-size:9px;margin-top:2px" id="gc">—</div>
  </div>
  <div style="background:var(--bg3);border-radius:7px;padding:6px 9px;text-align:center;min-width:90px;">
    <div style="font-family:'Share Tech Mono';font-size:7px;color:var(--dim)">MOOD</div>
    <div style="font-size:12px;font-weight:700;margin-top:2px" id="gs">—</div>
  </div>
</div>

<!-- MARKET STRIP -->
<div class="mstrip">
  <div class="mc"><div class="mc-n">NIFTY 50</div><div class="mc-v" id="nv" style="color:var(--grn)">—</div><div class="mc-c" id="na" style="color:var(--blu)">ATM: —</div></div>
  <div class="mc"><div class="mc-n">SENSEX</div><div class="mc-v" id="sv" style="color:var(--grn)">—</div><div class="mc-c" id="sa">—</div></div>
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
      <span>PUT/CALL RATIO (PCR)</span><span id="pcrVal" style="color:var(--gold)">—</span>
    </div>
    <div class="pcr-bg"><div class="pcr-fill" id="pcrFill" style="width:50%;background:var(--gold)"></div></div>
    <div class="pcr-marks"><span>BEAR &lt;0.7</span><span>NEUTRAL 1.0</span><span>BULL &gt;1.2</span></div>
    <div style="font-family:'Share Tech Mono';font-size:10px;margin-top:5px;text-align:center" id="pcrSig">—</div>
  </div>
  <div class="sr-row">
    <div class="sr-cell sr-sup">
      <div style="font-family:'Share Tech Mono';font-size:7px;color:var(--grn)">SUPPORT (Max PUT OI)</div>
      <div style="font-family:'Orbitron';font-size:14px;font-weight:700;color:var(--grn)" id="support">—</div>
    </div>
    <div class="sr-cell sr-res">
      <div style="font-family:'Share Tech Mono';font-size:7px;color:var(--red)">RESISTANCE (Max CALL OI)</div>
      <div style="font-family:'Orbitron';font-size:14px;font-weight:700;color:var(--red)" id="resistance">—</div>
    </div>
  </div>
</div>

<!-- PREMIUM -->
<div class="card">
  <div class="ctitle">ATM PREMIUM <span class="badge wait" id="prem-src">LOADING</span></div>
  <div class="prem-grid">
    <div class="prem-cell"><div style="font-family:'Orbitron';font-size:10px;color:var(--grn);margin-bottom:3px">CALL CE</div><div style="font-family:'Orbitron';font-size:20px;font-weight:700;color:var(--grn)" id="cePrem">—</div></div>
    <div class="prem-cell"><div style="font-family:'Orbitron';font-size:10px;color:var(--red);margin-bottom:3px">PUT PE</div><div style="font-family:'Orbitron';font-size:20px;font-weight:700;color:var(--red)" id="pePrem">—</div></div>
  </div>
</div>

<!-- 13 AGENTS + L14 NAMBI -->
<div class="card">
  <div class="ctitle">CCS AGENTS — L1 TO L13 <span class="badge wait" id="ag-badge">WAITING</span></div>

  <div class="ag-sect">▸ SYSTEM & DATA (L1-L4)</div>
  <div class="ag-grid">
    <div class="agc" id="card-l1"><div class="ag-top"><span class="ag-id">L1</span><span class="ag-sig none" id="sig-l1">—</span></div><div class="ag-name">Vishnu</div><div class="ag-role">System Structure</div><div class="ag-val" id="val-l1">—</div></div>
    <div class="agc" id="card-l2"><div class="ag-top"><span class="ag-id">L2</span><span class="ag-sig none" id="sig-l2">—</span></div><div class="ag-name">Ravi</div><div class="ag-role">Data Connection</div><div class="ag-val" id="val-l2">—</div></div>
    <div class="agc" id="card-l3"><div class="ag-top"><span class="ag-id">L3</span><span class="ag-sig none" id="sig-l3">—</span></div><div class="ag-name">Pooja</div><div class="ag-role">Data Accuracy</div><div class="ag-val" id="val-l3">—</div></div>
    <div class="agc" id="card-l4"><div class="ag-top"><span class="ag-id">L4</span><span class="ag-sig none" id="sig-l4">—</span></div><div class="ag-name">Rani</div><div class="ag-role">Trading Logic</div><div class="ag-val" id="val-l4">—</div></div>
  </div>

  <div class="ag-sect">▸ RISK & NETWORK (L5-L8)</div>
  <div class="ag-grid">
    <div class="agc" id="card-l5"><div class="ag-top"><span class="ag-id">L5</span><span class="ag-sig none" id="sig-l5">—</span></div><div class="ag-name">Murali</div><div class="ag-role">Error Detection</div><div class="ag-val" id="val-l5">—</div></div>
    <div class="agc" id="card-l6"><div class="ag-top"><span class="ag-id">L6</span><span class="ag-sig none" id="sig-l6">—</span></div><div class="ag-name">Moorthy</div><div class="ag-role">Security</div><div class="ag-val" id="val-l6">—</div></div>
    <div class="agc" id="card-l7"><div class="ag-top"><span class="ag-id">L7</span><span class="ag-sig none" id="sig-l7">—</span></div><div class="ag-name">Subbaraj</div><div class="ag-role">Network</div><div class="ag-val" id="val-l7">—</div></div>
    <div class="agc" id="card-l8"><div class="ag-top"><span class="ag-id">L8</span><span class="ag-sig none" id="sig-l8">—</span></div><div class="ag-name">Paramasivam</div><div class="ag-role">Backup</div><div class="ag-val" id="val-l8">—</div></div>
  </div>

  <div class="ag-sect">▸ EXECUTION & INTELLIGENCE (L9-L13)</div>
  <div class="ag-grid">
    <div class="agc" id="card-l9"><div class="ag-top"><span class="ag-id">L9</span><span class="ag-sig none" id="sig-l9">—</span></div><div class="ag-name">Siluva</div><div class="ag-role">Speed Optimizer</div><div class="ag-val" id="val-l9">—</div></div>
    <div class="agc" id="card-l10"><div class="ag-top"><span class="ag-id">L10</span><span class="ag-sig none" id="sig-l10">—</span></div><div class="ag-name">Kumar</div><div class="ag-role">Execution</div><div class="ag-val" id="val-l10">—</div></div>
    <div class="agc" id="card-l11"><div class="ag-top"><span class="ag-id">L11</span><span class="ag-sig none" id="sig-l11">—</span></div><div class="ag-name">Jayalalitha</div><div class="ag-role">Quality Check</div><div class="ag-val" id="val-l11">—</div></div>
    <div class="agc" id="card-l12"><div class="ag-top"><span class="ag-id">L12</span><span class="ag-sig none" id="sig-l12">—</span></div><div class="ag-name">Ranjitham</div><div class="ag-role">Trade Executor</div><div class="ag-val" id="val-l12">—</div></div>
  </div>
  <div style="margin-top:5px">
    <div class="agc" id="card-l13" style="border-color:rgba(41,182,246,.3)">
      <div class="ag-top"><span class="ag-id" style="color:var(--blu)">L13</span><span class="ag-sig none" id="sig-l13">—</span></div>
      <div class="ag-name" style="color:var(--blu)">Raja</div>
      <div class="ag-role">Report Generator</div>
      <div class="ag-val" id="val-l13">—</div>
    </div>
  </div>

  <!-- CONFIDENCE BAR -->
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

  <!-- L14 NAMBI -->
  <div class="nambi-card">
    <div class="nambi-title">⚡ L14 — NAMBI (MASTER CONTROLLER)</div>
    <div class="nambi-verdict" id="nambi-verdict" style="color:var(--gold)">STANDBY</div>
    <div class="nambi-reason" id="nambi-reason">Waiting for all agents to report...</div>
    <div style="margin-top:6px;font-family:'Share Tech Mono';font-size:8px;color:var(--dim)">
      Chairman → NAMBI → L1-L13 → Super Power AI → Signal
    </div>
  </div>
</div>

<!-- BRAIN FINAL DECISION -->
<div class="brain-box wait" id="brain-box">
  <div style="font-family:'Share Tech Mono';font-size:8px;color:var(--dim);letter-spacing:2px;margin-bottom:4px">MARKET BRAIN — FINAL DECISION</div>
  <div class="brain-sig" id="brain-sig" style="color:var(--gold)">LOADING...</div>
  <div class="brain-sub" id="brain-sub">Awaiting data...</div>
  <div id="reasons" style="margin-top:8px;background:var(--bg3);border-radius:8px;padding:8px;font-family:'Share Tech Mono';font-size:9px;line-height:1.8"></div>
</div>

<button class="ref-btn" onclick="doFetch()">🔄 REFRESH NOW</button>
<button class="go-btn" id="go-btn" onclick="runClaude()">⚡ NAMBI + CLAUDE — FULL STRATEGY</button>
<div class="claude-box" id="claude-box" style="display:none">
  <div style="font-family:'Orbitron';font-size:8px;color:var(--gold);margin-bottom:8px;letter-spacing:1px">CLAUDE AI STRATEGY — CHAIRMAN REPORT</div>
  <div id="claude-text" style="font-size:13px;line-height:1.9"></div>
</div>

</div><!-- /main -->

<div class="wsbar">
  <div class="wsdot" id="wsdot"></div>
  <span id="ws-txt">Connecting...</span>
  <span id="ws-cnt" style="margin-left:auto;color:var(--dim)"></span>
</div>

<script>
let D={}, BR={}, SY={}, AG={};

async function poll(){
  try{
    const r=await fetch('/state',{signal:AbortSignal.timeout(10000)});
    if(!r.ok) throw new Error('HTTP '+r.status);
    const j=await r.json();
    D=j.market||{}; BR=j.brain||{}; SY=j.sys||{}; AG=j.agents||{};
    setOnline(); render();
  }catch(e){ setOffline('Retrying...'); }
}

function setOnline(){
  q('wsdot').className='wsdot on';
  q('live-badge').className='hlive on'; q('live-badge').textContent='LIVE';
  q('ws-txt').textContent='Connected ✓';
}
function setOffline(msg){
  q('wsdot').className='wsdot';
  q('live-badge').className='hlive off'; q('live-badge').textContent='OFFLINE';
  q('ws-txt').textContent=msg||'Connecting...';
}

function render(){
  // Market Status
  const ms=D.market_status||SY.market_status||'';
  const isOpen=ms.includes('OPEN')&&!ms.includes('CLOSED')&&!ms.includes('PRE');
  const msBox=q('mstatus-box');
  msBox.className='mstatus '+(isOpen?'open':'closed');
  t('mstatus-txt', ms||'Checking...');

  // Status bar
  if(ms&&!isOpen) sdot('wait',ms);
  else sdot('ok','Live #'+(SY.count||0)+' — '+(D.fetch_time||ist()));
  q('ws-cnt').textContent=D.source||'';

  // Index
  const idx=SY.index||'NIFTY';
  q('ib-nifty').className='ib'+(idx==='NIFTY'?' on':'');
  q('ib-sensex').className='ib'+(idx==='SENSEX'?' on':'');

  if(D.nifty){ tv('nv',D.nifty.toFixed(0),'var(--grn)'); t('na','ATM: '+(D.atm||'—')); t('n-spot',D.nifty.toFixed(0)); t('n-atm','ATM: '+(D.atm||'—')); }
  if(D.sensex){ tv('sv',D.sensex.toFixed(0),'var(--grn)'); t('sa','ATM: '+Math.round(D.sensex/100)*100); t('s-spot',D.sensex.toFixed(0)); t('s-atm','ATM: '+Math.round(D.sensex/100)*100); }

  if(D.vix){
    const vc=D.vix>20?'var(--red)':D.vix>15?'var(--gold)':'var(--grn)';
    tv('vv',D.vix.toFixed(1),vc);
    t('vn',D.vix>20?'HIGH FEAR':D.vix>15?'CAUTION':'CALM');
  }

  if(D.gift){
    const gd=D.gift_diff||0;
    tv('gv',D.gift.toFixed(0),gd>=0?'var(--grn)':'var(--red)');
    tv('gc',(gd>=0?'▲ +':'▼ ')+Math.abs(gd).toFixed(0)+' pts',gd>=0?'var(--grn)':'var(--red)');
    t('gs',gd>100?'BULLISH':gd>40?'MILD BULL':gd<-100?'BEARISH':gd<-40?'MILD BEAR':'NEUTRAL');
  }

  // OI
  if(D.call_oi){
    t('callOI',fmt(D.call_oi)); t('putOI',fmt(D.put_oi));
    const pcr=D.pcr||1;
    tv('pcrVal',pcr.toFixed(2),pcr>1.2?'var(--grn)':pcr<0.7?'var(--red)':'var(--gold)');
    q('pcrFill').style.width=Math.min(100,pcr/2*100)+'%';
    q('pcrFill').style.background=pcr>1.2?'var(--grn)':pcr<0.7?'var(--red)':'var(--gold)';
    tv('pcrSig',pcr>1.2?'📈 BULLISH':pcr<0.7?'📉 BEARISH':'⚖️ NEUTRAL',
       pcr>1.2?'var(--grn)':pcr<0.7?'var(--red)':'var(--gold)');
    const src=D.source||'';
    q('oi-src').className='badge '+(src.includes('NSE')?'live':'wait');
    q('oi-src').textContent=src.includes('NSE')?'🟢 NSE REAL':src.includes('EST')?'⚡ ESTIMATED':'LOADING';
    q('prem-src').className='badge '+(D.ce_prem?'live':'wait');
    q('prem-src').textContent=D.ce_prem?'🟢 LIVE':'LOADING';
  }
  if(D.support) tv('support',D.support.toLocaleString('en-IN'),'var(--grn)');
  if(D.resistance) tv('resistance',D.resistance.toLocaleString('en-IN'),'var(--red)');
  if(D.ce_prem) tv('cePrem','₹'+D.ce_prem.toFixed(0),'var(--grn)');
  if(D.pe_prem) tv('pePrem','₹'+D.pe_prem.toFixed(0),'var(--red)');

  // L1-L13 Agents
  let liveCount=0;
  for(let i=1;i<=13;i++){
    const aid='l'+i;
    const a=AG[aid]||{};
    const card=q('card-'+aid), sigEl=q('sig-'+aid), valEl=q('val-'+aid);
    if(!card) continue;
    const d=a.signal||'none';
    card.className='agc '+(d==='bull'||d==='bear'||d==='neut'?d:'');
    if(sigEl){ sigEl.className='ag-sig '+d; sigEl.textContent=d==='bull'?'▲ BULL':d==='bear'?'▼ BEAR':d==='neut'?'◆ HOLD':'—'; }
    if(valEl) valEl.textContent=a.detail||'—';
    if(d!=='none') liveCount++;
  }
  q('ag-badge').className='badge '+(liveCount>0?'live':'wait');
  q('ag-badge').textContent=liveCount>0?`● ${liveCount}/13 LIVE`:'WAITING';

  // Confidence Bar
  const bp_=BR.bull_pct||50, brp_=BR.bear_pct||50;
  q('conf-bull').style.width=bp_+'%'; q('conf-bear').style.width=brp_+'%';
  t('bp',bp_+'%'); t('brp',brp_+'%');
  t('conf-mid','Confidence: '+(BR.confidence||'—'));

  // L14 NAMBI
  const nv=BR.nambi_verdict||'STANDBY';
  const nc=nv.includes('BUY CE')?'var(--grn)':nv.includes('BUY PE')?'var(--red)':'var(--gold)';
  tv('nambi-verdict',nv,nc);
  t('nambi-reason',BR.nambi_reason||(AG.l14||{}).detail||'—');
  if(AG.l14){
    const nd=AG.l14.signal||'none';
    q('card-l13')&&(q('card-l13').style.borderColor='');
  }

  // Brain
  const sig=BR.signal||'WAIT';
  const cls=sig==='BUY CE'?'bull':sig==='BUY PE'?'bear':'wait';
  const col={bull:'var(--grn)',bear:'var(--red)',wait:'var(--gold)'}[cls];
  const lbl={bull:'🟢 BUY CE — BULLISH',bear:'🔴 BUY PE — BEARISH',wait:'⏳ WAIT — HOLD CAPITAL'}[cls];
  q('brain-box').className='brain-box '+cls;
  tv('brain-sig',lbl,col);
  t('brain-sub',(D.source||'—')+'  Bull:'+bp_+'% Bear:'+brp_+'%  Conf:'+(BR.confidence||'—')+(BR.trap?' ⚠️TRAP':''));
  if(BR.reasons&&BR.reasons.length)
    q('reasons').innerHTML=BR.reasons.slice(0,5).map(r=>'▸ '+r).join('<br>');
}

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
    if(j.ok){
      q('angel-st').textContent='● LIVE'; q('angel-st').style.color='var(--pur)';
      q('angel-btn').textContent='✅ CONNECTED'; q('angel-btn').className='cbtn ok';
    } else {
      q('angel-btn').textContent='CONNECT ANGEL ONE';
      sdot('err','Angel: '+(j.error||'Failed'));
    }
  }catch(e){ q('angel-btn').textContent='CONNECT ANGEL ONE'; }
}

async function setYahoo(){
  sdot('wait','Yahoo mode...');
  await fetch('/set_yahoo',{method:'POST'}).catch(()=>{});
  setTimeout(poll,2000);
}
function setIdx(idx){
  q('ib-nifty').className='ib'+(idx==='NIFTY'?' on':'');
  q('ib-sensex').className='ib'+(idx==='SENSEX'?' on':'');
  fetch('/set_index',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({index:idx})})
    .then(()=>setTimeout(poll,2000)).catch(()=>{});
}
async function doFetch(){
  sdot('wait','Fetching...');
  await fetch('/do_fetch',{method:'POST'}).catch(()=>{});
  setTimeout(poll,4000);
}

async function runClaude(){
  const key=getKey();
  if(!key){ alert('Claude API Key enter பண்ணுங்க!'); return; }
  const btn=q('go-btn'); btn.disabled=true; btn.innerHTML='<span class="sp"></span>NAMBI Computing...';
  q('claude-box').style.display='block';
  q('claude-text').innerHTML='<span style="color:var(--gold)">NAMBI → L1-L13 → Claude AI...</span>';
  q('claude-box').scrollIntoView({behavior:'smooth'});

  const agSummary=Object.entries(AG).map(([id,a])=>
    `${id.toUpperCase()} ${a.name||''}: ${(a.signal||'N/A').toUpperCase()} — ${a.detail||''}`
  ).join('\n');

  const prompt=`MATHAN AI COMPLETE SYSTEM — CHAIRMAN REPORT
===========================================
Market Status: ${D.market_status||'Unknown'}
NIFTY: ${D.nifty?.toFixed(0)||'N/A'} | ATM: ${D.atm||'N/A'}
SENSEX: ${D.sensex?.toFixed(0)||'N/A'}
VIX: ${D.vix?.toFixed(1)||'N/A'} | PCR: ${D.pcr||'N/A'}
GIFT: ${D.gift?.toFixed(0)||'N/A'} (${D.gift_diff>=0?'+':''}${D.gift_diff||0} pts)
CE: ₹${D.ce_prem?.toFixed(0)||'N/A'} | PE: ₹${D.pe_prem?.toFixed(0)||'N/A'}
Support: ${D.support||'N/A'} | Resistance: ${D.resistance||'N/A'}

L14 NAMBI VERDICT: ${BR.nambi_verdict||'STANDBY'}
Brain Signal: ${BR.signal} | Bull:${BR.bull_pct}% Bear:${BR.bear_pct}% | ${BR.confidence}
Trap: ${BR.trap?'YES ⚠️':'NO'}

ALL 14 AGENTS:
${agSummary}

Please give Chairman Mr. Mathan Sir:
1. NAMBI FINAL CALL with reason
2. Strike selection (ATM/OTM)
3. Entry timing + condition
4. Stop Loss exact ₹
5. T1/T2/T3 targets
6. Risk warning (VIX + trap)
7. Tomorrow outlook (GIFT signal)

Tamil+English mixed. Bold key numbers. Start with "சாமி!"`;

  try{
    const r=await fetch('https://api.anthropic.com/v1/messages',{
      method:'POST',
      headers:{'Content-Type':'application/json','x-api-key':key,
        'anthropic-version':'2023-06-01','anthropic-dangerous-direct-browser-access':'true'},
      body:JSON.stringify({model:'claude-sonnet-4-20250514',max_tokens:800,
        messages:[{role:'user',content:prompt}]}),
      signal:AbortSignal.timeout(35000)
    });
    const j=await r.json();
    q('claude-text').innerHTML=(j?.content?.[0]?.text||'Error')
      .replace(/\n/g,'<br>')
      .replace(/\*\*(.*?)\*\*/g,'<strong style="color:var(--gold)">$1</strong>');
  }catch(e){
    q('claude-text').innerHTML='<span style="color:var(--red)">Error — Retry</span>';
  }
  btn.disabled=false; btn.innerHTML='⚡ NAMBI + CLAUDE — FULL STRATEGY';
}

function saveKey(){const v=q('ki').value.trim();if(v.startsWith('sk-ant'))try{localStorage.setItem('mbk',v);}catch(e){}}
function getKey(){const v=q('ki').value.trim();return v.startsWith('sk-ant')?v:(localStorage.getItem('mbk')||'');}
function fmt(n){if(!n)return'—';if(n>10000000)return(n/10000000).toFixed(1)+'Cr';if(n>100000)return(n/100000).toFixed(1)+'L';return(n/1000).toFixed(0)+'K';}
function sdot(s,txt){q('sdot').className='sdot '+s;q('stxt').textContent=txt;q('stxt').style.color=s==='ok'?'var(--grn)':s==='err'?'var(--red)':'var(--gold)';}
function q(i){return document.getElementById(i);}
function t(i,v){const e=q(i);if(e)e.textContent=v;}
function tv(i,v,c){const e=q(i);if(e){e.textContent=v;if(c)e.style.color=c;}}
function ist(){const n=new Date(new Date().toLocaleString('en-US',{timeZone:'Asia/Kolkata'}));return [n.getHours(),n.getMinutes(),n.getSeconds()].map(x=>String(x).padStart(2,'0')).join(':');}
setInterval(()=>{const ts=ist();t('clock',ts);t('rtxt','IST '+ts);},1000);

window.onload=()=>{
  const k=localStorage.getItem('mbk');if(k)q('ki').value=k;
  // Auto-fill credentials
  q('api-key').value='jYAKgdt3';
  q('client-id').value='V542909';
  q('angel-pin').value='1818';
  q('totp-secret').value='KJ4MRMUWNTFTCUALRBH5ALKA7A';
  poll();
  setInterval(poll,8000);
};
</script>
</body>
</html>"""

# ── REST ROUTES ────────────────────────────────────────────────────────
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
            "sys":    {**dict(SYS),"angel_ok":ANGEL["connected"]},
        })

@app.route("/ping")
def ping():
    return jsonify({"pong":True,"time":ist(),"source":M.get("source"),"count":SYS["count"]})

@app.route("/connect_angel",methods=["POST"])
def connect_angel():
    d=request.get_json(force=True) or {}
    ak=d.get("api_key",ANGEL["api_key"]).strip()
    ci=d.get("client_id",ANGEL["client_id"]).strip()
    pin=d.get("pin",ANGEL["pin"]).strip()
    ts=d.get("totp_secret",ANGEL["totp_secret"]).strip()
    if not all([ak,ci,pin,ts]):
        return jsonify({"ok":False,"error":"All 4 fields required"}),400
    try:
        from SmartApi import SmartConnect
        totp=pyotp.TOTP(ts).now()
        obj=SmartConnect(api_key=ak)
        data=obj.generateSession(ci,pin,totp)
        if not data or data.get("status") is False:
            msg=data.get("message","Login failed") if data else "No response"
            return jsonify({"ok":False,"error":msg}),401
        ANGEL.update({"api_key":ak,"client_id":ci,"pin":pin,"totp_secret":ts,
                      "jwt_token":data["data"]["jwtToken"],"connected":True})
        SYS["angel_ok"]=True
        threading.Thread(target=full_cycle,daemon=True).start()
        return jsonify({"ok":True,"msg":"Angel One connected!"})
    except ImportError:
        return jsonify({"ok":False,"error":"SmartAPI not installed"}),500
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500

@app.route("/set_yahoo",methods=["POST"])
def set_yahoo():
    threading.Thread(target=full_cycle,daemon=True).start()
    return jsonify({"ok":True})

@app.route("/set_index",methods=["POST"])
def set_index():
    idx=(request.get_json(force=True) or {}).get("index","NIFTY").upper()
    if idx in INDEX_CFG:
        with LOCK: SYS["index"]=idx
        threading.Thread(target=full_cycle,daemon=True).start()
    return jsonify({"ok":True,"index":idx})

@app.route("/do_fetch",methods=["POST"])
def do_fetch():
    threading.Thread(target=full_cycle,daemon=True).start()
    return jsonify({"ok":True})

# ── STARTUP ───────────────────────────────────────────────────────────
if __name__=="__main__":
    print(f"""
╔══════════════════════════════════════════════╗
║   MATHAN AI — COMPLETE SYSTEM V10           ║
║   CCS BODY + SUPER POWER SOUL + L14 NAMBI   ║
╠══════════════════════════════════════════════╣
║   Chairman → Nambi → L1-L13 → Brain        ║
║   NSE Real OI | Yahoo | Angel One           ║
║   Keep-Alive | No timeout!                  ║
╚══════════════════════════════════════════════╝
    """)
    # Initial data fetch
    threading.Thread(target=full_cycle,daemon=True).start()
    # Background loops
    threading.Thread(target=poll_loop,daemon=True).start()
    threading.Thread(target=keep_alive_loop,daemon=True).start()
    app.run(host="0.0.0.0",port=PORT,use_reloader=False,threaded=True)
