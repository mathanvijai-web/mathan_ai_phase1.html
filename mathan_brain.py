"""
MATHAN AI — BRAIN MODULE (mathan_brain.py)
==========================================
Super Power Soul — Market Analysis Engine
L1 to L14 Agent Computation
NSE Real OI + Yahoo VIX + Angel One

Used by: ccs_server.py
"""
import datetime, time, requests, threading

INDEX_CFG = {
    "NIFTY":  {"step": 50,  "lot": 65,  "expiry_dow": 1},
    "SENSEX": {"step": 100, "lot": 20,  "expiry_dow": 3},
}

NSE_HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/option-chain"
}

# ── HELPERS ──────────────────────────────────────────────────────────
def ist():
    tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(tz).strftime("%H:%M:%S")

def ist_mins():
    tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    n  = datetime.datetime.now(tz)
    return n.hour * 60 + n.minute

def calc_expiry(index="NIFTY"):
    tz  = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    t   = datetime.datetime.now(tz)
    dow = INDEX_CFG[index]["expiry_dow"]
    d2t = (dow - t.weekday()) % 7
    if d2t == 0 and t.hour >= 15 and t.minute >= 30:
        d2t = 7
    return d2t

def market_status():
    tz   = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    n    = datetime.datetime.now(tz)
    days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    day  = days[n.weekday()]
    mins = n.hour * 60 + n.minute
    if n.weekday() >= 5:
        return f"MARKET CLOSED — {day} Weekend", False
    if mins < 9*60+15:
        return f"PRE-MARKET — Opens 9:15 AM", False
    if mins > 15*60+30:
        return f"MARKET CLOSED — After 3:30 PM", False
    return "MARKET OPEN", True

# ── DATA FETCH ────────────────────────────────────────────────────────
def fetch_nse_oi(index="NIFTY"):
    """NSE Option Chain — FREE, no token, works every market day."""
    try:
        s = requests.Session()
        s.get("https://www.nseindia.com",
              headers={**NSE_HDR, "Accept": "text/html"}, timeout=7)
        time.sleep(0.3)
        r = s.get(
            f"https://www.nseindia.com/api/option-chain-indices?symbol={index}",
            headers=NSE_HDR, timeout=12)
        if r.status_code != 200:
            return None
        raw  = r.json().get("records", {})
        spot = raw.get("underlyingValue", 0)
        data = raw.get("data", [])
        exps = raw.get("expiryDates", [])
        if not spot or not data:
            return None
        target = exps[0] if exps else ""
        cfg    = INDEX_CFG[index]
        atm    = round(spot / cfg["step"]) * cfg["step"]
        tC=tP=mxC=mxP=mxCS=mxPS=ceLTP=peLTP = 0
        for row in data:
            if target and row.get("expiryDate","") != target:
                continue
            st    = row.get("strikePrice", 0)
            ce    = row.get("CE", {})
            pe    = row.get("PE", {})
            ceOI  = ce.get("openInterest", 0) or 0
            peOI  = pe.get("openInterest", 0) or 0
            ceLtp = ce.get("lastPrice", 0) or 0
            peLtp = pe.get("lastPrice", 0) or 0
            tC += ceOI; tP += peOI
            if ceOI > mxC: mxC = ceOI; mxCS = st
            if peOI > mxP: mxP = peOI; mxPS = st
            if abs(st - atm) <= cfg["step"]:
                if ceLtp: ceLTP = ceLtp
                if peLtp: peLTP = peLtp
        if tC == 0:
            return None
        return {
            "spot": spot, "atm": atm,
            "call_oi": tC, "put_oi": tP,
            "pcr": round(tP/tC, 2),
            "support": mxPS, "resistance": mxCS,
            "ce_prem": ceLTP, "pe_prem": peLTP,
            "exp_days": calc_expiry(index),
            "source": "NSE REAL OI ✓",
            "fetch_time": ist()
        }
    except Exception as e:
        print(f"[NSE ERR] {e}")
        return None

def fetch_yahoo_all():
    """Yahoo Finance — VIX + GIFT + Spot (works weekends too)."""
    hdrs = {"User-Agent": "Mozilla/5.0"}
    result = {}
    tickers = {
        "nifty":  "%5ENSEI",
        "sensex": "%5EBSESN",
        "vix":    "%5EINDIAVIX",
        "gift":   "NIFTYFUTURES.NS",
    }
    for key, sym in tickers.items():
        try:
            r = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"interval": "1d", "range": "5d"},
                headers=hdrs, timeout=10)
            meta = r.json()["chart"]["result"][0]["meta"]
            sp   = meta.get("regularMarketPrice", 0) or meta.get("previousClose", 0)
            if sp:
                result[key] = sp
        except:
            pass
    return result

def estimate_oi(spot, index="NIFTY"):
    """Estimated OI when market is closed."""
    cfg  = INDEX_CFG[index]
    atm  = round(spot / cfg["step"]) * cfg["step"]
    base = spot * 180
    return {
        "spot": spot, "atm": atm,
        "call_oi": int(base), "put_oi": int(base * 1.08),
        "pcr": 1.08,
        "support": atm - cfg["step"]*2,
        "resistance": atm + cfg["step"]*2,
        "ce_prem": round(spot * 0.004),
        "pe_prem": round(spot * 0.0037),
        "exp_days": calc_expiry(index),
        "source": "ESTIMATED (Market Closed)",
        "fetch_time": ist()
    }

# ── 14 AGENTS ─────────────────────────────────────────────────────────
def run_agents(M, angel_ok=False, poll_count=0, keep_alive=0):
    """
    Run all 14 agents and return signals.
    M = market data dict
    Returns: (agents_dict, trap_bool)
    """
    spot  = M.get("nifty") or M.get("spot")
    vix   = M.get("vix")
    pcr   = M.get("pcr")
    atm   = M.get("atm")
    gd    = M.get("gift_diff")
    ce    = M.get("ce_prem")
    pe    = M.get("pe_prem")
    ce_p  = M.get("ce_prev")
    pe_p  = M.get("pe_prev")
    sup   = M.get("support")
    res   = M.get("resistance")
    exp   = M.get("exp_days")
    gap   = M.get("gap")
    ms    = M.get("market_status", "")
    mins  = ist_mins()
    ag    = {}

    # L1 Vishnu — System Structure
    if spot and vix and pcr:
        ag["l1"] = ("bull", "System OK — All data feeds active")
    elif spot:
        ag["l1"] = ("neut", "Partial data — OI loading")
    else:
        ag["l1"] = ("neut", f"Waiting — {ms}")

    # L2 Ravi — Data Connection
    if angel_ok:
        ag["l2"] = ("bull", "Angel One CONNECTED — Real data active")
    else:
        ag["l2"] = ("neut", "Angel One not connected — Yahoo fallback")

    # L3 Pooja — Data Accuracy
    is_open = "OPEN" in ms and "CLOSED" not in ms
    if spot and vix:
        ag["l3"] = ("bull" if is_open else "neut",
                    f"{'LIVE' if is_open else 'PREV CLOSE'} | Spot={spot:.0f} VIX={vix:.1f}")
    else:
        ag["l3"] = ("neut", "Data verification pending")

    # L4 Rani — Trading Logic (PCR)
    if pcr:
        if pcr > 1.5:   ag["l4"] = ("bull", f"PCR {pcr} STRONG BULL")
        elif pcr > 1.2: ag["l4"] = ("bull", f"PCR {pcr} BULLISH")
        elif pcr < 0.6: ag["l4"] = ("bear", f"PCR {pcr} STRONG BEAR")
        elif pcr < 0.8: ag["l4"] = ("bear", f"PCR {pcr} BEARISH")
        else:           ag["l4"] = ("neut", f"PCR {pcr} NEUTRAL")
    else:
        ag["l4"] = ("neut", "PCR N/A")

    # L5 Murali — Error/VIX
    if vix:
        if vix > 22:   ag["l5"] = ("bear", f"VIX {vix:.1f} EXTREME DANGER")
        elif vix > 18: ag["l5"] = ("neut", f"VIX {vix:.1f} HIGH FEAR")
        elif vix < 13: ag["l5"] = ("bull", f"VIX {vix:.1f} CALM")
        else:          ag["l5"] = ("neut", f"VIX {vix:.1f} NORMAL")
    else:
        ag["l5"] = ("neut", "VIX N/A")

    # L6 Moorthy — Security/Trap
    trap = False; trap_det = ""
    if pcr and spot and atm:
        if pcr > 1.3 and spot < atm - 50:
            trap = True; trap_det = "PCR Bull but Price below ATM — BULL TRAP?"
        elif pcr < 0.75 and spot > atm + 50:
            trap = True; trap_det = "PCR Bear but Price above ATM — BEAR TRAP?"
    if vix and vix > 20 and pcr and pcr > 1.2:
        trap = True; trap_det = f"VIX {vix:.1f} + PCR {pcr} — Manipulation risk!"
    ag["l6"] = ("neut", f"⚠️ {trap_det}") if trap else ("bull", "No trap detected")

    # L7 Subbaraj — Network
    ag["l7"] = ("bull", f"HTTP Polling OK — {poll_count} polls") if poll_count > 0 \
               else ("neut", "Network connecting...")

    # L8 Paramasivam — Backup
    ag["l8"] = ("bull", f"Keep-alive active — {keep_alive} pings") if keep_alive > 0 \
               else ("neut", "Backup standby")

    # L9 Siluva — Session/Speed
    if mins < 555:    ag["l9"] = ("neut", "Pre-market — Standby")
    elif mins < 600:  ag["l9"] = ("bull", "OPEN HOUR 9:15 — Full speed")
    elif mins < 660:  ag["l9"] = ("bull", "PRIME WINDOW 9:15-11:00")
    elif mins < 780:  ag["l9"] = ("neut", "Mid session 11:00-1:00")
    elif mins < 870:  ag["l9"] = ("neut", "Afternoon 1:00-2:30")
    elif mins < 930:  ag["l9"] = ("neut", "EXPIRY WINDOW 2:30-3:30")
    else:             ag["l9"] = ("neut", "Post market")

    # L10 Kumar — Execution
    if spot and atm:
        if res and spot > res:       ag["l10"] = ("bull", f"BREAKOUT above {int(res)}")
        elif sup and spot < sup:     ag["l10"] = ("bear", f"BREAKDOWN below {int(sup)}")
        elif spot > atm + 50:        ag["l10"] = ("bull", f"Above ATM {atm}")
        elif spot < atm - 50:        ag["l10"] = ("bear", f"Below ATM {atm}")
        else:                        ag["l10"] = ("neut", f"At ATM {atm}")
    else:
        ag["l10"] = ("neut", "Execution standby")

    # L11 Jayalalitha — Quality/Gap
    if gap:
        if gap > 100:   ag["l11"] = ("bull", f"Gap UP +{round(gap)} STRONG")
        elif gap > 40:  ag["l11"] = ("bull", f"Gap UP +{round(gap)} mild")
        elif gap < -100:ag["l11"] = ("bear", f"Gap DOWN {round(gap)} STRONG")
        elif gap < -40: ag["l11"] = ("bear", f"Gap DOWN {round(gap)} mild")
        else:           ag["l11"] = ("neut", f"Flat ±{round(abs(gap))}")
    elif gd:
        if gd > 100:    ag["l11"] = ("bull", f"GIFT +{round(gd)} — Bull tomorrow")
        elif gd < -100: ag["l11"] = ("bear", f"GIFT {round(gd)} — Bear tomorrow")
        else:           ag["l11"] = ("neut", f"GIFT flat ±{round(abs(gd))}")
    else:
        ag["l11"] = ("neut", "Gap check pending")

    # L12 Ranjitham — Premium/Execute
    if ce and pe:
        chg_ce = (ce - ce_p) if ce_p else 0
        chg_pe = (pe - pe_p) if pe_p else 0
        if chg_ce > 5 and chg_ce > chg_pe:
            ag["l12"] = ("bull", f"CE ₹{ce:.0f} +{chg_ce:.0f} rising — BUY CE")
        elif chg_pe > 5 and chg_pe > chg_ce:
            ag["l12"] = ("bear", f"PE ₹{pe:.0f} +{chg_pe:.0f} rising — BUY PE")
        elif vix and vix > 22:
            ag["l12"] = ("neut", f"VIX HIGH — Execution HOLD")
        else:
            ag["l12"] = ("neut", f"CE ₹{ce:.0f} PE ₹{pe:.0f} monitoring")
    else:
        ag["l12"] = ("neut", "Premium monitoring standby")

    # L13 Raja — Reports/Expiry
    if exp is not None:
        if exp == 0:   ag["l13"] = ("bull", "TODAY EXPIRY ⚡ Max theta decay")
        elif exp == 1: ag["l13"] = ("neut", "TOMORROW EXPIRY — High volatility")
        elif exp <= 3: ag["l13"] = ("neut", f"{exp} days — Near expiry")
        else:          ag["l13"] = ("neut", f"{exp} days to expiry")
    else:
        ag["l13"] = ("neut", "Report standby")

    # L14 NAMBI — MASTER CONTROLLER
    b = sum(1 for v in ag.values() if v[0] == "bull")
    r = sum(1 for v in ag.values() if v[0] == "bear")
    n = sum(1 for v in ag.values() if v[0] == "neut")
    total = b + r; ratio = (b - r) / total if total > 0 else 0

    if trap:
        ag["l14"] = ("neut", f"NAMBI: WAIT — Trap! ({b}↑{r}↓{n}◆)")
    elif ratio > 0.35 and (not vix or vix < 18):
        ag["l14"] = ("bull", f"NAMBI: BUY CE — {b}/{b+r+n} BULL. Execute!")
    elif ratio < -0.35:
        ag["l14"] = ("bear", f"NAMBI: BUY PE — {r}/{b+r+n} BEAR. Execute!")
    else:
        ag["l14"] = ("neut", f"NAMBI: WAIT — Mixed signals ({b}↑{r}↓{n}◆)")

    return ag, trap

def compute_final_signal(ag, trap, M):
    """Weighted brain decision from all 14 agents."""
    WEIGHTS = {
        "l1":1.0,"l2":1.5,"l3":1.5,"l4":1.5,"l5":1.0,
        "l6":0.8,"l7":0.8,"l8":0.8,"l9":1.0,"l10":1.2,
        "l11":1.2,"l12":1.5,"l13":1.0,"l14":3.0
    }
    bw = brw = 0.0; reasons = []
    for aid, (sig, det) in ag.items():
        w = WEIGHTS.get(aid, 1.0)
        if sig == "bull":   bw  += w; reasons.append(det)
        elif sig == "bear": brw += w; reasons.append(det)

    tw   = bw + brw or 1
    bp   = round(bw / tw * 100)
    brp  = 100 - bp
    diff = abs(bw - brw)
    conf = "HIGH" if diff >= 4 else "MEDIUM" if diff >= 2 else "LOW"

    nambi = ag.get("l14", ("neut", ""))
    if trap:                              sig = "WAIT"; nv = "STANDBY — Trap detected!"
    elif nambi[0] == "bull" and bp >= 60: sig = "BUY CE"; nv = "BUY CE ✅"
    elif nambi[0] == "bear" and brp >= 60:sig = "BUY PE"; nv = "BUY PE ✅"
    else:                                 sig = "WAIT";   nv = "WAIT — No clear signal"

    return {
        "signal": sig, "bull_pct": bp, "bear_pct": brp,
        "confidence": conf, "reasons": reasons[:6],
        "trap": trap, "nambi_verdict": nv,
        "nambi_reason": nambi[1],
    }
