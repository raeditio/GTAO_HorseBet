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

    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root { 
            --bg: #11111b; 
            --surface: rgba(30, 30, 46, 0.6); 
            --surface2: rgba(49, 50, 68, 0.4); 
            --text: #cdd6f4; 
            --text-dim: #a6adc8;
            --primary: #89b4fa; 
            --danger: #f38ba8; 
            --success: #a6e3a1; 
            --warning: #f9e2af; 
        }
        body { font-family: 'Inter', sans-serif; background: radial-gradient(circle at top, #1e1e2e 0%, #11111b 100%); color: var(--text); padding: 20px; display: flex; justify-content: center; margin: 0; min-height: 100vh; }
        .container { max-width: 700px; width: 100%; display: flex; flex-direction: column; gap: 24px; margin-top: 20px; }
        .card { background: var(--surface); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); padding: 32px; border-radius: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.05); }
        
        h2 { margin-top: 0; margin-bottom: 24px; font-size: 28px; font-weight: 700; letter-spacing: -0.5px; background: linear-gradient(90deg, #cdd6f4, #a6adc8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 16px; }
        h3 { margin-top: 0; margin-bottom: 20px; color: var(--text); border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 12px; font-weight: 600; }
        
        .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; text-align: center; margin-bottom: 32px; }
        .stat-box { background: var(--surface2); padding: 24px 16px; border-radius: 16px; display: flex; flex-direction: column; justify-content: center; align-items: center; border: 1px solid rgba(255,255,255,0.03); transition: all 0.3s ease; }
        .stat-box:hover { transform: translateY(-4px); background: rgba(49, 50, 68, 0.6); border-color: rgba(255,255,255,0.08); box-shadow: 0 8px 20px rgba(0,0,0,0.2); }
        .stat-value { font-size: 28px; font-weight: 700; color: var(--primary); margin-bottom: 8px; text-shadow: 0 2px 10px rgba(137, 180, 250, 0.2); }
        .stat-label { font-size: 12px; font-weight: 600; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; }
        
        .switch-container { display: flex; justify-content: space-between; align-items: center; padding: 16px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }
        .switch-container:last-child { border-bottom: none; }
        .switch-label { font-weight: 500; color: var(--text); }
        
        .switch { position: relative; display: inline-block; width: 44px; height: 24px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(255,255,255,0.1); transition: .3s; border-radius: 24px; border: 1px solid rgba(255,255,255,0.05); }
        .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 2px; bottom: 2px; background-color: white; transition: .3s cubic-bezier(0.4, 0.0, 0.2, 1); border-radius: 50%; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
        input:checked + .slider { background-color: var(--success); border-color: var(--success); }
        input:checked + .slider:before { transform: translateX(20px); }
        
        .status-badge { display: inline-block; padding: 8px 16px; border-radius: 30px; font-size: 12px; font-weight: 700; background: rgba(88, 91, 112, 0.2); color: var(--text-dim); border: 1px solid rgba(88, 91, 112, 0.2); margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; transition: all 0.3s ease; }
        .status-paused { background: rgba(249, 226, 175, 0.1); color: var(--warning); border-color: rgba(249, 226, 175, 0.2); }
        .status-running { background: rgba(137, 180, 250, 0.1); color: var(--primary); border-color: rgba(137, 180, 250, 0.2); }
        .status-error { background: rgba(243, 139, 168, 0.1); color: var(--danger); border-color: rgba(243, 139, 168, 0.2); }
        
        .action-btn { width: 100%; padding: 18px; font-size: 16px; font-weight: 700; border-radius: 14px; transition: all 0.2s cubic-bezier(0.4, 0.0, 0.2, 1); border: none; cursor: pointer; text-transform: uppercase; letter-spacing: 1px; }
        .btn-start { background: linear-gradient(135deg, var(--success) 0%, #8bda85 100%); color: #082a06; box-shadow: 0 4px 15px rgba(166, 227, 161, 0.2); }
        .btn-start:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(166, 227, 161, 0.3); }
        .btn-stop { background: linear-gradient(135deg, var(--danger) 0%, #e86b8e 100%); color: #3a0b16; box-shadow: 0 4px 15px rgba(243, 139, 168, 0.2); }
        .btn-stop:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(243, 139, 168, 0.3); }
        .action-btn:active { transform: translateY(1px); box-shadow: none; }
        
        select { appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%23cdd6f4' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 12px center; background-size: 16px; padding-right: 40px !important; }
        .custom-select-btn { padding: 10px 24px; background: rgba(137, 180, 250, 0.1); color: var(--primary); border: 1px solid rgba(137, 180, 250, 0.2); border-radius: 8px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        .custom-select-btn:hover { background: rgba(137, 180, 250, 0.2); transform: translateY(-1px); }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h2>GTAO HorseBet</h2>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div id="status-badge" class="status-badge">Loading...</div>
                <div id="game-running-badge" class="status-badge">Game: Checking...</div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-box">
                    <div id="time_running" class="stat-value" style="font-size: 22px; color: var(--text);">0h 0m 0s</div>
                    <div class="stat-label">Time Running</div>
                </div>
                <div class="stat-box">
                    <div id="money_per_hour" class="stat-value">0</div>
                    <div class="stat-label">Earned / Hour</div>
                </div>
                <div class="stat-box">
                    <div id="winnings" class="stat-value">0</div>
                    <div class="stat-label">Earned All Time</div>
                </div>
                <div class="stat-box" style="grid-column: span 1;">
                    <div id="races_won" class="stat-value" style="color: var(--success); text-shadow: 0 2px 10px rgba(166, 227, 161, 0.2);">0</div>
                    <div class="stat-label">Wins</div>
                </div>
                <div class="stat-box" style="grid-column: span 2;">
                    <div id="win_prob" class="stat-value">0%</div>
                    <div class="stat-label">Win Probability</div>
                </div>
            </div>

            <button id="start-btn" class="action-btn btn-start" onclick="toggleBot()">Start Automation</button>
        </div>
        
        <div class="card">
            <h3>Settings</h3>
            <div class="switch-container">
                <span class="switch-label">Web Hosting (LAN Access)</span>
                <label class="switch">
                    <input type="checkbox" id="toggle-web" onchange="toggleSetting('web_hosting', this.checked)">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="switch-container" style="flex-direction: column; align-items: flex-start;">
                <span class="switch-label" style="margin-bottom: 12px;">Webserver Address</span>
                <div style="display: flex; width: 100%; gap: 10px;">
                    <select id="host-ip-select" style="flex-grow: 1; padding: 10px 14px; border-radius: 8px; background: rgba(0,0,0,0.2); color: var(--text); border: 1px solid rgba(255,255,255,0.1); font-family: 'Inter', sans-serif; font-weight: 500; font-size: 14px; outline: none;">
                    </select>
                    <button onclick="changeHostIp()" class="custom-select-btn">Save</button>
                </div>
            </div>
            <div class="switch-container">
                <span class="switch-label">Debug Mode (Save Images)</span>
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
                statusBadge.innerText = data.status;
                statusBadge.className = 'status-badge';
                if (data.status.toLowerCase().includes('failed') || data.status.toLowerCase().includes('error') || data.status.toLowerCase().includes('stopped')) statusBadge.classList.add('status-error');
                else if (data.status.toLowerCase().includes('paused') || !data.running) statusBadge.classList.add('status-paused');
                else statusBadge.classList.add('status-running');

                const gameBadge = document.getElementById('game-running-badge');
                gameBadge.innerText = data.game_running ? "Game: Running" : "Game: Not Found";
                gameBadge.style.color = data.game_running ? "var(--success)" : "var(--danger)";

                const hrs = Math.floor(data.elapsed / 3600);
                const mins = Math.floor((data.elapsed % 3600) / 60);
                const secs = data.elapsed % 60;
                document.getElementById('time_running').innerText = `${hrs}h ${mins}m ${secs}s`;

                document.getElementById('winnings').innerText = data.winnings;
                
                const hours = data.elapsed / 3600;
                document.getElementById('money_per_hour').innerText = hours > 0 ? Math.round(data.winnings / hours) : 0;

                document.getElementById('races_won').innerText = data.races_won;
                
                const total_races = data.races_won + data.races_lost;
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

def start_dashboard(bot_state, host_ip='0.0.0.0'):
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
        autobet_dir = os.path.join(os.path.expanduser('~'), 'Documents', 'autobet')
        ssl_dir = os.path.join(autobet_dir, 'ssl')
        key_path = os.path.join(ssl_dir, 'key.pem')
        cert_pem_path = os.path.join(ssl_dir, 'cert.pem')
        cert_crt_path = os.path.join(ssl_dir, 'cert.crt')

        cert_path = None
        if os.path.exists(cert_pem_path):
            cert_path = cert_pem_path
        elif os.path.exists(cert_crt_path):
            cert_path = cert_crt_path

        if cert_path and os.path.exists(key_path):
            print(f"\n[SSL INFO] Found certificates in {ssl_dir}. Starting with HTTPS.")
            ssl_context = (cert_path, key_path)
            app.run(host=host_ip, port=8027, debug=False, use_reloader=False, ssl_context=ssl_context)
        else:
            print(f"\n[SSL WARNING] No certificates found in '{ssl_dir}'.")
            print("[SSL WARNING] To enable HTTPS, place 'cert.pem' (or .crt) and 'key.pem' in that folder.")
            print("[SSL WARNING] Falling back to HTTP.\n")
            app.run(host=host_ip, port=8027, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_flask_app, daemon=True)
    server_thread.start()