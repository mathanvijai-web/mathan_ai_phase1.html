"""
MATHAN AI — CCS SERVER (ccs_server.py)
=======================================
CCS Body — Command Control System Backend
Imports brain logic from mathan_brain.py
Serves dashboard + REST API

Run: python ccs_server.py
URL: https://your-render-url.onrender.com
"""
import os, json, time, threading, requests, pyotp
from flask import Flask, Response, jsonify, request
from flask_cors import CORS

# Import brain module
try:
    from mathan_brain import (
        fetch_nse_oi, fetch_yahoo_all, estimate_oi,
        market_status, run_agents, compute_final_signal,
        ist, INDEX_CFG
    )
    print("[CCS] Brain module loaded ✓")
except ImportError as e:
    print(f"[CCS] Brain import error: {e}")

app  = Flask(__name__)
CORS(app)
PORT = int(os.environ.get("PORT", 8000))

# ── ANGEL ONE CREDENTIALS ─────────────────────────────────────────────
ANGEL = {
    "api_key":     os.environ.get("ANGEL_API_KEY",    "jYAKgdt3"),
    "client_id":   os.environ.get("ANGEL_CLIENT_ID",  "V542909"),
    "pin":         os.environ.get("ANGEL_PIN",        "1818"),
    "totp_secret": os.environ.get("ANGEL_TOTP",       "KJ4MRMUWNTFTCUALRBH5ALKA7A"),
    "connected":   False,
    "jwt_token":   "",
    "error":       None,
}

# ── SYSTEM STATE ──────────────────────────────────────────────────────
M = {
    "nifty": None, "sensex": None, "vix": None,
    "gift": None,  "gift_diff": None,
    "atm": None,   "gap": None,
    "pcr": None,   "call_oi": None, "put_oi": None,
    "ce_prem": None, "pe_prem": None,
    "ce_prev": None, "pe_prev": None,
    "support": None, "resistance": None,
    "exp_days": None, "source": "LOADING",
    "fetch_time": None, "market_status": "CHECKING",
}

AGENTS_STATE = {}
BRAIN_STATE  = {
    "signal": "WAIT", "bull_pct": 50, "bear_pct": 50,
    "confidence": "LOW", "reasons": [],
    "trap": False, "nambi_verdict": "STANDBY",
    "nambi_reason": "Awaiting data...",
}

SYS = {
    "count": 0, "error": None,
    "index": "NIFTY", "angel_ok": False,
    "market_status": "CHECKING",
    "keep_alive_count": 0,
}

LOCK = threading.Lock()

# ── FULL CYCLE ────────────────────────────────────────────────────────
def full_cycle():
    """Main data fetch + agent run cycle."""
    status, is_open = market_status()

    with LOCK:
        M["market_status"] = status
        SYS["market_status"] = status

    # Step 1: Yahoo data (works 24/7)
    yahoo = fetch_yahoo_all()
    with LOCK:
        if yahoo.get("nifty"):
            M["nifty"] = yahoo["nifty"]
            from mathan_brain import INDEX_CFG
            M["atm"]   = round(yahoo["nifty"] / INDEX_CFG[SYS["index"]]["step"]) * INDEX_CFG[SYS["index"]]["step"]
        if yahoo.get("sensex"): M["sensex"] = yahoo["sensex"]
        if yahoo.get("vix"):    M["vix"]    = yahoo["vix"]
        if yahoo.get("gift"):
            M["gift"]      = yahoo["gift"]
            M["gift_diff"] = round(yahoo["gift"] - (M["nifty"] or 23000), 2)

    # Step 2: OI data
    if is_open:
        oi = fetch_nse_oi(SYS["index"])
        if oi:
            with LOCK:
                M["ce_prev"] = M["ce_prem"]
                M["pe_prev"] = M["pe_prem"]
                M.update(oi)
                SYS["count"] += 1
                SYS["error"]  = None
        else:
            with LOCK: SYS["error"] = "NSE OI unavailable"
    else:
        with LOCK:
            spot = M["nifty"] or 23000
            oi   = estimate_oi(spot, SYS["index"])
            M.update(oi)

    # Step 3: Run 14 agents
    with LOCK: m_snap = dict(M); sys_snap = dict(SYS)
    ag, trap = run_agents(
        m_snap,
        angel_ok=ANGEL["connected"],
        poll_count=SYS["count"],
        keep_alive=SYS["keep_alive_count"]
    )

    brain = compute_final_signal(ag, trap, m_snap)

    with LOCK:
        global AGENTS_STATE, BRAIN_STATE
        AGENTS_STATE = {
            k: {"name": _agent_names().get(k,""), "signal": v[0], "detail": v[1],
                "weight": _agent_weights().get(k, 1.0)}
            for k, v in ag.items()
        }
        BRAIN_STATE = brain

def _agent_names():
    return {
        "l1":"Vishnu","l2":"Ravi","l3":"Pooja","l4":"Rani",
        "l5":"Murali","l6":"Moorthy","l7":"Subbaraj","l8":"Paramasivam",
        "l9":"Siluva","l10":"Kumar","l11":"Jayalalitha","l12":"Ranjitham",
        "l13":"Raja","l14":"NAMBI"
    }

def _agent_weights():
    return {
        "l1":1.0,"l2":1.5,"l3":1.5,"l4":1.5,"l5":1.0,
        "l6":0.8,"l7":0.8,"l8":0.8,"l9":1.0,"l10":1.2,
        "l11":1.2,"l12":1.5,"l13":1.0,"l14":3.0
    }

def poll_loop():
    while True:
        time.sleep(20)
        try: full_cycle()
        except Exception as e: print(f"[POLL ERR] {e}")

def keep_alive_loop():
    """Ping self every 10 min — Render never sleeps!"""
    time.sleep(60)
    while True:
        try:
            requests.get(f"http://localhost:{PORT}/ping", timeout=5)
            with LOCK: SYS["keep_alive_count"] += 1
            print(f"[ALIVE] Ping #{SYS['keep_alive_count']}")
        except: pass
        time.sleep(600)

# ── REST API ──────────────────────────────────────────────────────────
@app.route("/state")
def state_route():
    with LOCK:
        return jsonify({
            "market": dict(M),
            "brain":  dict(BRAIN_STATE),
            "agents": dict(AGENTS_STATE),
            "sys":    {**dict(SYS), "angel_ok": ANGEL["connected"]},
        })

@app.route("/ping")
def ping():
    return jsonify({"pong": True, "time": ist(),
                    "source": M.get("source"), "count": SYS["count"]})

@app.route("/connect_angel", methods=["POST"])
def connect_angel():
    d   = request.get_json(force=True) or {}
    ak  = d.get("api_key",  ANGEL["api_key"]).strip()
    ci  = d.get("client_id",ANGEL["client_id"]).strip()
    pin = d.get("pin",      ANGEL["pin"]).strip()
    ts  = d.get("totp_secret",ANGEL["totp_secret"]).strip()
    if not all([ak, ci, pin, ts]):
        return jsonify({"ok":False,"error":"All 4 fields required"}),400
    try:
        from SmartApi import SmartConnect
        totp = pyotp.TOTP(ts).now()
        obj  = SmartConnect(api_key=ak)
        data = obj.generateSession(ci, pin, totp)
        if not data or data.get("status") is False:
            msg = data.get("message","Login failed") if data else "No response"
            return jsonify({"ok":False,"error":msg}),401
        ANGEL.update({"api_key":ak,"client_id":ci,"pin":pin,"totp_secret":ts,
                      "jwt_token":data["data"]["jwtToken"],"connected":True})
        SYS["angel_ok"] = True
        threading.Thread(target=full_cycle, daemon=True).start()
        return jsonify({"ok":True,"msg":"Angel One connected!"})
    except ImportError:
        return jsonify({"ok":False,"error":"SmartAPI not installed"}),500
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500

@app.route("/set_yahoo",  methods=["POST"])
def set_yahoo():
    threading.Thread(target=full_cycle, daemon=True).start()
    return jsonify({"ok":True})

@app.route("/set_index",  methods=["POST"])
def set_index():
    idx = (request.get_json(force=True) or {}).get("index","NIFTY").upper()
    if idx in INDEX_CFG:
        with LOCK: SYS["index"] = idx
        threading.Thread(target=full_cycle, daemon=True).start()
    return jsonify({"ok":True,"index":idx})

@app.route("/do_fetch", methods=["POST"])
def do_fetch():
    threading.Thread(target=full_cycle, daemon=True).start()
    return jsonify({"ok":True})

@app.route("/")
@app.route("/dashboard")
def dashboard():
    try:
        with open("ccs_dashboard.html") as f:
            return Response(f.read(), mimetype="text/html")
    except:
        return jsonify({"status":"CCS Server running","url":"/dashboard"})

# ── STARTUP ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════╗
║   MATHAN AI — CCS SERVER                     ║
║   CCS Body + Super Power Soul + L14 Nambi    ║
╠═══════════════════════════════════════════════╣
║   Chairman → Nambi → L1-L13 → Brain         ║
║   NSE Real OI | Yahoo | Angel One            ║
╚═══════════════════════════════════════════════╝
    """)
    threading.Thread(target=full_cycle,    daemon=True).start()
    threading.Thread(target=poll_loop,     daemon=True).start()
    threading.Thread(target=keep_alive_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False, threaded=True)
