import os, json, time, threading, datetime, socket, requests
import pyotp
import uvicorn
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# 🚀 MATHAN AI — RENDER OPTIMIZED VERSION
app = FastAPI()

# ── DASHBOARD HTML (Dynamic WebSocket URL Added) ──────────────────────
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"/>
<title>Mathan AI — Angel One Brain</title>
<style>
/* ... (உங்கள் பழைய CSS ஸ்டைல்கள் அனைத்தும் இங்கே இருக்கும்) ... */
body { background: #070b0f; color: #cdd9e5; font-family: sans-serif; }
.hlive.on { color: #00e676; }
.hlive.off { color: #ff1744; }
</style>
</head>
<body>
<div id="status">Connecting to Mathan Brain...</div>
<div id="data-container"></div>

<script>
    // 🎯 Render-ல் தானாக URL-ஐக் கண்டறியும் மேஜிக்:
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws_url = `${protocol}//${window.location.host}/ws`;
    
    let socket = new WebSocket(ws_url);

    socket.onopen = () => {
        document.getElementById('status').innerText = "ONLINE 🟢";
        console.log("Connected to Mathan AI WebSocket");
    };

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        // உங்கள் டேட்டா டிஸ்ப்ளே லாஜிக் இங்கே...
        console.log("Data received:", data);
    };

    socket.onclose = () => {
        document.getElementById('status').innerText = "OFFLINE 🔴";
        setTimeout(() => location.reload(), 5000); // 5 செகண்டில் மீண்டும் முயற்சிக்கும்
    };
</script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(DASHBOARD_HTML)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # இங்கே உங்கள் Angel One தரவுகளை அனுப்பும் லாஜிக் வரும்
            sample_data = {"status": "connected", "msg": "Mathan AI is Live!"}
            await websocket.send_json(sample_data)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print("Client disconnected")

# 🎯 RENDER PORT FIX:
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
