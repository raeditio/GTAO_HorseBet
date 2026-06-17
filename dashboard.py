import threading
import os
from flask import Flask, jsonify, render_template_string, request, abort

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GTAO HorseBet Control Panel</title>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg:        #07070f;
            --surface:   #0e0e1c;
            --surface2:  #13131f;
            --border:    rgba(255,255,255,0.06);
            --border-hi: rgba(99,102,241,0.35);
            --text:      #e2e4f0;
            --text-dim:  #6b6f8a;
            --primary:   #6366f1;
            --primary-glow: rgba(99,102,241,0.18);
            --cyan:      #22d3ee;
            --cyan-glow: rgba(34,211,238,0.15);
            --success:   #10b981;
            --success-glow: rgba(16,185,129,0.15);
            --danger:    #f43f5e;
            --danger-glow: rgba(244,63,94,0.15);
            --warning:   #f59e0b;
        }
 
        *, *::before, *::after { box-sizing: border-box; }
 
        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            padding: 16px 12px 56px;
            background-image:
                linear-gradient(rgba(99,102,241,0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(99,102,241,0.03) 1px, transparent 1px);
            background-size: 40px 40px;
        }
 
        .container {
            max-width: 640px;
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
 
        /* ── Header bar ── */
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            padding: 14px 16px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            flex-wrap: wrap;
        }
        .header-left { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
        .header-icon {
            width: 34px; height: 34px;
            background: var(--primary-glow);
            border: 1px solid var(--border-hi);
            border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            font-size: 17px;
            flex-shrink: 0;
        }
        .header-title {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 17px;
            font-weight: 700;
            color: var(--text);
            letter-spacing: -0.3px;
        }
        .header-sub {
            font-size: 10px;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 1.2px;
            margin-top: 1px;
        }
        .header-badges {
            display: flex;
            gap: 6px;
            align-items: center;
            flex-wrap: wrap;
        }
 
        /* ── Pulse dot + status badge ── */
        .pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 12px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            border: 1px solid var(--border);
            color: var(--text-dim);
            background: var(--surface2);
            transition: all 0.3s ease;
        }
        .pill.running  { color: var(--primary);  background: var(--primary-glow);  border-color: var(--border-hi); }
        .pill.paused   { color: var(--warning);   background: rgba(245,158,11,0.1);  border-color: rgba(245,158,11,0.25); }
        .pill.error    { color: var(--danger);    background: var(--danger-glow);    border-color: rgba(244,63,94,0.3); }
        .pill.game-ok  { color: var(--success);   background: var(--success-glow);   border-color: rgba(16,185,129,0.3); }
 
        .pulse-dot {
            width: 7px; height: 7px;
            border-radius: 50%;
            background: currentColor;
            flex-shrink: 0;
        }
        .pill.running .pulse-dot {
            animation: pulse 1.4s ease-in-out infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(99,102,241,0.5); }
            50%       { opacity: 0.6; box-shadow: 0 0 0 5px rgba(99,102,241,0); }
        }
 
        /* ── Stats grid ── */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
        }
        .stat-box {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px 12px;
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            gap: 5px;
            transition: border-color 0.2s, background 0.2s;
            min-width: 0;
        }
        .stat-box:hover {
            border-color: rgba(255,255,255,0.1);
            background: var(--surface2);
        }
        .stat-label {
            font-size: 9px;
            font-weight: 600;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 1px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 100%;
        }
        .stat-value {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 22px;
            font-weight: 700;
            color: var(--text);
            line-height: 1;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 100%;
        }
        .stat-value.accent-cyan    { color: var(--cyan); }
        .stat-value.accent-green   { color: var(--success); }
        .stat-value.accent-primary { color: var(--primary); }
        .stat-value.time-val       { font-size: 15px; color: var(--text); }
 
        /* ── Mobile responsive ── */
        @media (max-width: 480px) {
            body { padding: 12px 10px 48px; }
            .container { gap: 8px; }
            .header { padding: 12px 14px; border-radius: 14px; }
            .header-badges { width: 100%; }
            .pill { font-size: 10px; padding: 4px 10px; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
            /* Time Running spans full width on 2-col layout */
            .stats-grid .stat-box:first-child { grid-column: span 2; }
            /* Win Rate spans full width */
            .stats-grid .stat-box:last-child { grid-column: span 2; }
            .stat-value { font-size: 20px; }
            .stat-value.time-val { font-size: 16px; }
            .card { padding: 16px; border-radius: 14px; }
            .action-btn { padding: 15px; }
            .settings-row { padding: 12px 0; }
        }
 
        /* ── Main action card ── */
        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
        }
        .card-label {
            font-size: 10px;
            font-weight: 600;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 1.2px;
            margin-bottom: 16px;
        }
 
        /* ── Action button ── */
        .action-btn {
            width: 100%;
            padding: 16px;
            font-family: 'Space Grotesk', sans-serif;
            font-size: 14px;
            font-weight: 700;
            border-radius: 12px;
            border: none;
            cursor: pointer;
            letter-spacing: 0.5px;
            transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
            text-transform: uppercase;
        }
        .btn-start {
            background: var(--success);
            color: #052e16;
            box-shadow: 0 0 0 0 var(--success-glow);
        }
        .btn-start:hover {
            background: #0fca8e;
            box-shadow: 0 4px 20px rgba(16,185,129,0.35);
            transform: translateY(-1px);
        }
        .btn-stop {
            background: var(--danger);
            color: #1a0009;
            box-shadow: 0 0 0 0 var(--danger-glow);
        }
        .btn-stop:hover {
            background: #f5607a;
            box-shadow: 0 4px 20px rgba(244,63,94,0.35);
            transform: translateY(-1px);
        }
        .action-btn:active { transform: translateY(1px); box-shadow: none; }
 
        /* ── Settings ── */
        .settings-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 14px 0;
            border-bottom: 1px solid var(--border);
        }
        .settings-row:last-child { border-bottom: none; padding-bottom: 0; }
        .settings-row:first-of-type { padding-top: 0; }
        .row-label { font-size: 13px; font-weight: 500; color: var(--text); }
        .row-hint  { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
 
        /* Toggle switch */
        .switch { position: relative; display: inline-block; width: 42px; height: 23px; flex-shrink: 0; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute; inset: 0;
            background: rgba(255,255,255,0.08);
            border: 1px solid var(--border);
            border-radius: 999px;
            cursor: pointer;
            transition: 0.25s;
        }
        .slider::before {
            content: "";
            position: absolute;
            width: 17px; height: 17px;
            left: 2px; bottom: 2px;
            background: #fff;
            border-radius: 50%;
            transition: 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 1px 4px rgba(0,0,0,0.4);
        }
        input:checked + .slider { background: var(--success); border-color: var(--success); }
        input:checked + .slider::before { transform: translateX(19px); }
 
        /* IP select row */
        .ip-row { flex-direction: column; align-items: flex-start; gap: 10px; }
        .ip-controls { display: flex; width: 100%; gap: 8px; }
        select {
            flex-grow: 1;
            padding: 9px 36px 9px 12px;
            background: var(--surface2);
            color: var(--text);
            border: 1px solid var(--border);
            border-radius: 8px;
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            font-weight: 500;
            outline: none;
            appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236b6f8a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 10px center;
            cursor: pointer;
            transition: border-color 0.2s;
        }
        select:focus { border-color: var(--border-hi); }
        .save-btn {
            padding: 9px 18px;
            background: var(--primary-glow);
            color: #a5b4fc;
            border: 1px solid var(--border-hi);
            border-radius: 8px;
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
        }
        .save-btn:hover { background: rgba(99,102,241,0.28); color: #c7d2fe; }
 
        /* ── Divider ── */
        .divider {
            height: 1px;
            background: var(--border);
            margin: 4px 0;
        }
    </style>
</head>
<body>
<div class="container">
 
    <!-- Header -->
    <div class="header">
        <div class="header-left">
            <div class="header-icon">🏇</div>
            <div>
                <div class="header-title">AutoBet</div>
                <div class="header-sub">GTAO Automation</div>
            </div>
        </div>
        <div class="header-badges">
            <div id="status-badge" class="pill">
                <span class="pulse-dot"></span>
                <span id="status-text">Loading</span>
            </div>
            <div id="game-running-badge" class="pill">
                <span class="pulse-dot"></span>
                <span id="game-text">Game</span>
            </div>
        </div>
    </div>
 
    <!-- Stats -->
    <div class="stats-grid">
        <div class="stat-box">
            <div class="stat-label">Time Running</div>
            <div id="time_running" class="stat-value time-val">0h 0m 0s</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Earned / hr</div>
            <div id="money_per_hour" class="stat-value accent-cyan">$0</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">All-Time</div>
            <div id="winnings" class="stat-value accent-cyan">$0</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Wins</div>
            <div id="races_won" class="stat-value accent-green">0</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Total</div>
            <div id="races_total" class="stat-value accent-primary">0</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Win Rate</div>
            <div id="win_prob" class="stat-value accent-primary">0%</div>
        </div>
    </div>
 
    <!-- Main control -->
    <div class="card">
        <div class="card-label">Automation</div>
        <button id="start-btn" class="action-btn btn-start" onclick="toggleBot()">Start Automation</button>
    </div>
 
    <!-- Settings -->
    <div class="card">
        <div class="card-label">Settings</div>
 
        <div class="settings-row">
            <div>
                <div class="row-label">LAN Access</div>
                <div class="row-hint">Allow connections from local network</div>
            </div>
            <label class="switch">
                <input type="checkbox" id="toggle-web" onchange="toggleSetting('web_hosting', this.checked)">
                <span class="slider"></span>
            </label>
        </div>
 
        <div class="settings-row ip-row">
            <div>
                <div class="row-label">Server Address</div>
                <div class="row-hint">IP interface to bind the webserver · port <strong style="color:var(--text);font-weight:600;">8027</strong></div>
            </div>
            <div class="ip-controls">
                <select id="host-ip-select"></select>
                <button onclick="changeHostIp()" class="save-btn">Save</button>
            </div>
        </div>
 
        <div class="settings-row">
            <div>
                <div class="row-label">Debug Mode</div>
                <div class="row-hint">Save screenshots during automation</div>
            </div>
            <label class="switch">
                <input type="checkbox" id="toggle-debug" onchange="toggleSetting('debug', this.checked)">
                <span class="slider"></span>
            </label>
        </div>
    </div>
 
</div>
 
    <script>
        let isUpdating = false;
 
        async function fetchStats() {
            if(isUpdating) return;
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                
                const statusBadge = document.getElementById('status-badge');
                document.getElementById('status-text').innerText = data.status;
                statusBadge.className = 'pill';
                if (data.status.toLowerCase().includes('failed') || data.status.toLowerCase().includes('error') || data.status.toLowerCase().includes('stopped')) statusBadge.classList.add('error');
                else if (data.status.toLowerCase().includes('paused') || !data.running) statusBadge.classList.add('paused');
                else statusBadge.classList.add('running');
 
                const gameBadge = document.getElementById('game-running-badge');
                document.getElementById('game-text').innerText = data.game_running ? "Game: On" : "Game: Off";
                gameBadge.className = 'pill' + (data.game_running ? ' game-ok' : ' error');
 
                const hrs = Math.floor(data.elapsed / 3600);
                const mins = Math.floor((data.elapsed % 3600) / 60);
                const secs = data.elapsed % 60;
                document.getElementById('time_running').innerText = `${hrs}h ${mins}m ${secs}s`;
 
                document.getElementById('winnings').innerText = '$' + data.winnings.toLocaleString();
                
                const hours = data.elapsed / 3600;
                document.getElementById('money_per_hour').innerText = '$' + (hours > 0 ? Math.round(data.winnings / hours).toLocaleString() : 0);
 
                document.getElementById('races_won').innerText = data.races_won;
                
                const total_races = data.races_won + data.races_lost;
                document.getElementById('races_total').innerText = total_races;
                document.getElementById('win_prob').innerText = total_races > 0 ? ((data.races_won / total_races) * 100).toFixed(1) + '%' : '0%';
                
                const startBtn = document.getElementById('start-btn');
                startBtn.innerText = data.running ? "Stop Automation" : "Start Automation";
                startBtn.className = data.running ? "action-btn btn-stop" : "action-btn btn-start";
 
                document.getElementById('toggle-debug').checked = data.debug;
                document.getElementById('toggle-web').checked = data.web_hosting;
 
                const select = document.getElementById('host-ip-select');
                if (select.children.length === 0) {
                    data.available_ips.forEach(ip => {
                        const opt = document.createElement('option');
                        opt.value = ip;
                        opt.innerText = ip;
                        if (ip === data.host_ip) opt.selected = true;
                        select.appendChild(opt);
                    });
                }
            } catch (err) {
                const statusBadge = document.getElementById('status-badge');
                statusBadge.innerText = "Disconnected";
                statusBadge.className = 'status-badge status-error';
            }
        }
 
        async function toggleBot() {
            isUpdating = true;
            const res = await fetch('/api/stats');
            const data = await res.json();
            const payload = { running: !data.running };
            await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
            setTimeout(() => { isUpdating = false; fetchStats(); }, 200);
        }
 
        async function changeHostIp() {
            const ip = document.getElementById('host-ip-select').value;
            toggleSetting('host_ip', ip);
            alert("Webserver address updated to " + ip + ".");
        }
 
        async function toggleSetting(key, value) {
            isUpdating = true;
            const payload = {};
            payload[key] = value;
            await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
            setTimeout(() => { isUpdating = false; fetchStats(); }, 200);
        }
 
        setInterval(fetchStats, 1000);
        window.onload = fetchStats;
    </script>
</body>
</html>
"""

def start_dashboard(bot_state, host_ip='0.0.0.0', ssl_dir=None):
    app = Flask(__name__)

    @app.before_request
    def limit_remote_access():
        # Restricts remote LAN connections entirely if web hosting is disabled
        if not bot_state.web_hosting:
            if request.remote_addr != '127.0.0.1' and request.remote_addr != '::1':
                abort(403)
        # If hosting is enabled but a specific IP is chosen, optionally restrict it
        elif bot_state.host_ip != "0.0.0.0":
            if request.remote_addr != '127.0.0.1' and request.remote_addr != '::1':
                host_connected = request.host.split(':')[0]
                if host_connected != '127.0.0.1' and host_connected != bot_state.host_ip:
                    abort(403)

    @app.after_request
    def add_header(response):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    @app.route('/')
    def index(): return render_template_string(HTML_TEMPLATE)

    @app.route('/api/stats')
    def stats(): 
        elapsed = int(bot_state.stats.get_elapsed_time())
        return jsonify({
            "running": bot_state.running, 
            "status": bot_state.status, 
            "races_won": bot_state.stats.races_won, 
            "races_lost": bot_state.stats.races_lost, 
            "winnings": bot_state.stats.winnings,
            "debug": bot_state.debug,
            "web_hosting": bot_state.web_hosting,
            "game_running": bot_state.game_running,
            "elapsed": elapsed,
            "host_ip": bot_state.host_ip,
            "available_ips": bot_state.available_ips
        })

    @app.route('/api/settings', methods=['POST'])
    def settings(): 
        data = request.json
        if 'running' in data: bot_state.set_running(data['running'])
        if 'debug' in data: bot_state.debug = data['debug']
        if 'web_hosting' in data: bot_state.web_hosting = data['web_hosting']
        if 'host_ip' in data: bot_state.host_ip = data['host_ip']
        return jsonify({"success": True})

    def run_flask_app():
        local_ssl_dir = ssl_dir
        if local_ssl_dir is None:
            autobet_dir = os.path.join(os.path.expanduser('~'), 'Documents', 'autobet')
            local_ssl_dir = os.path.join(autobet_dir, 'ssl')
        
        cert_path = None
        key_path = None
        
        if os.path.exists(local_ssl_dir):
            for f in os.listdir(local_ssl_dir):
                if f.endswith('.key') or (f.endswith('.pem') and 'key' in f.lower()):
                    key_path = os.path.join(local_ssl_dir, f)
                elif f.endswith(('.crt', '.cer')) or (f.endswith('.pem') and 'key' not in f.lower()):
                    cert_path = os.path.join(local_ssl_dir, f)

        if cert_path and key_path:
            print(f"\n[SSL INFO] Found certificates in {local_ssl_dir}. Starting with HTTPS.")
            ssl_context = (cert_path, key_path)
            app.run(host=host_ip, port=8027, debug=False, use_reloader=False, ssl_context=ssl_context)
        else:
            print(f"\n[SSL WARNING] No certificates found in '{local_ssl_dir}'.")
            print("[SSL WARNING] To enable HTTPS, place 'cert.pem' (or .crt) and 'key.pem' in that folder.")
            print("[SSL WARNING] Falling back to HTTP.\n")
            app.run(host=host_ip, port=8027, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_flask_app, daemon=True)
    server_thread.start()