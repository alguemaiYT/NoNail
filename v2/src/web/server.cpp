#include "web/server.hpp"

#include <httplib.h>
#include <nlohmann/json.hpp>
#include <iostream>
#include <thread>

namespace nonail {

WebServer::WebServer(Agent& agent, const std::string& assets_dir)
    : agent_(agent)
    , assets_dir_(assets_dir)
{}

WebServer::~WebServer() {
    stop();
}

void WebServer::stop() {
    if (server_) {
        static_cast<httplib::Server*>(server_)->stop();
        running_ = false;
    }
}

void WebServer::start(const std::string& host, int port) {
    auto* svr = new httplib::Server();
    server_ = svr;

    register_routes();
    register_api_routes();

    running_ = true;
    std::cout << "🌐 Web UI: http://" << host << ":" << port << "\n";

    if (!svr->listen(host, port)) {
        std::cerr << "Failed to start web server on " << host << ":" << port << "\n";
    }
    running_ = false;
}

void WebServer::register_routes() {
    auto* svr = static_cast<httplib::Server*>(server_);

    // Serve main page
    svr->Get("/", [this](const httplib::Request&, httplib::Response& res) {
        res.set_content(get_index_html(), "text/html");
    });
}

void WebServer::register_api_routes() {
    auto* svr = static_cast<httplib::Server*>(server_);

    // GET /api/config
    svr->Get("/api/config", [this](const httplib::Request&, httplib::Response& res) {
        res.set_content(agent_.config().to_json().dump(), "application/json");
    });

    // POST /api/config
    svr->Post("/api/config", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            auto j = nlohmann::json::parse(req.body);
            // TODO: update agent config
            res.set_content(R"({"status":"ok"})", "application/json");
        } catch (const std::exception& e) {
            res.status = 400;
            res.set_content(nlohmann::json({{"error", e.what()}}).dump(), "application/json");
        }
    });

    // POST /api/chat
    svr->Post("/api/chat", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            auto j = nlohmann::json::parse(req.body);
            std::string message = j.at("message").get<std::string>();
            std::string reply = agent_.step(message);
            res.set_content(nlohmann::json({{"reply", reply}}).dump(), "application/json");
        } catch (const std::exception& e) {
            res.status = 500;
            res.set_content(nlohmann::json({{"error", e.what()}}).dump(), "application/json");
        }
    });

    // GET /api/status
    svr->Get("/api/status", [this](const httplib::Request&, httplib::Response& res) {
        nlohmann::json status = {
            {"provider", agent_.config().provider},
            {"model", agent_.config().model},
            {"history_size", agent_.history().size()},
            {"web", true}
        };
        res.set_content(status.dump(), "application/json");
    });

    // GET /api/tools
    svr->Get("/api/tools", [this](const httplib::Request&, httplib::Response& res) {
        // TODO: return tool list from agent
        res.set_content("[]", "application/json");
    });
}

void WebServer::register_ws_routes() {
    // WebSocket support would need a different library or httplib with WS
    // For now, use polling via /api/chat
}

std::string WebServer::get_index_html() const {
    return R"html(<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NoNail — AI Agent</title>
<style>
  :root { --bg: #0d1117; --fg: #c9d1d9; --accent: #58a6ff; --card: #161b22; --border: #30363d; --green: #3fb950; --red: #f85149; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--fg); min-height: 100vh; display: flex; flex-direction: column; }
  .header { background: var(--card); border-bottom: 1px solid var(--border); padding: 12px 20px; display: flex; align-items: center; gap: 12px; }
  .header h1 { font-size: 18px; color: var(--accent); }
  .header .status { font-size: 12px; color: var(--green); margin-left: auto; }
  .chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 12px; }
  .msg { max-width: 80%; padding: 10px 14px; border-radius: 12px; line-height: 1.5; word-wrap: break-word; white-space: pre-wrap; font-size: 14px; }
  .msg.user { background: var(--accent); color: #fff; align-self: flex-end; border-bottom-right-radius: 4px; }
  .msg.assistant { background: var(--card); border: 1px solid var(--border); align-self: flex-start; border-bottom-left-radius: 4px; }
  .msg.error { background: #3d1114; border: 1px solid var(--red); color: var(--red); align-self: flex-start; }
  .input-bar { background: var(--card); border-top: 1px solid var(--border); padding: 12px 20px; display: flex; gap: 8px; }
  .input-bar input { flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; color: var(--fg); font-size: 14px; outline: none; }
  .input-bar input:focus { border-color: var(--accent); }
  .input-bar button { background: var(--accent); color: #fff; border: none; border-radius: 8px; padding: 10px 20px; font-size: 14px; cursor: pointer; font-weight: 600; }
  .input-bar button:hover { opacity: 0.9; }
  .input-bar button:disabled { opacity: 0.5; cursor: not-allowed; }
  .config-panel { display: none; background: var(--card); border: 1px solid var(--border); border-radius: 12px; margin: 20px; padding: 20px; }
  .config-panel.show { display: block; }
  .config-panel label { display: block; margin-bottom: 6px; font-size: 13px; color: var(--accent); }
  .config-panel input, .config-panel select { width: 100%; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--fg); margin-bottom: 12px; font-size: 13px; }
  .toolbar { display: flex; gap: 6px; padding: 0 20px 8px; }
  .toolbar button { background: none; border: 1px solid var(--border); color: var(--fg); border-radius: 6px; padding: 4px 10px; font-size: 12px; cursor: pointer; }
  .toolbar button:hover { border-color: var(--accent); color: var(--accent); }
  @media (max-width: 600px) { .msg { max-width: 95%; } }
</style>
</head>
<body>
<div class="header">
  <h1>🔨 NoNail</h1>
  <span id="model-badge" style="font-size:12px;background:var(--border);padding:2px 8px;border-radius:4px;">loading...</span>
  <span class="status" id="status-dot">● connected</span>
</div>
<div class="toolbar">
  <button onclick="toggleConfig()">⚙ Config</button>
  <button onclick="clearChat()">🗑 Clear</button>
  <button onclick="loadStatus()">📊 Status</button>
</div>
<div class="config-panel" id="config-panel">
  <label>Provider</label>
  <select id="cfg-provider"><option>openai</option><option>anthropic</option></select>
  <label>Model</label>
  <input id="cfg-model" placeholder="gpt-4o">
  <label>API Key</label>
  <input id="cfg-apikey" type="password" placeholder="sk-...">
  <label>Temperature</label>
  <input id="cfg-temp" type="number" step="0.1" min="0" max="2" value="0.7">
  <button onclick="saveConfig()" style="background:var(--green);color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;">Save</button>
</div>
<div class="chat" id="chat"></div>
<div class="input-bar">
  <input id="input" placeholder="Type a message..." autocomplete="off">
  <button id="send-btn" onclick="sendMessage()">Send</button>
</div>
<script>
const chat = document.getElementById('chat');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send-btn');

input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });

function addMsg(role, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

async function sendMessage() {
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  addMsg('user', msg);
  sendBtn.disabled = true;
  try {
    const res = await fetch('/api/chat', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({message: msg}) });
    const data = await res.json();
    if (data.error) { addMsg('error', '❌ ' + data.error); }
    else { addMsg('assistant', data.reply); }
  } catch(e) { addMsg('error', '❌ Connection error: ' + e.message); }
  sendBtn.disabled = false;
  input.focus();
}

function clearChat() { chat.innerHTML = ''; }
function toggleConfig() { document.getElementById('config-panel').classList.toggle('show'); }

async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const s = await r.json();
    document.getElementById('model-badge').textContent = s.provider + '/' + s.model;
    addMsg('assistant', '📊 Status: ' + JSON.stringify(s, null, 2));
  } catch(e) { addMsg('error', 'Failed to load status'); }
}

async function saveConfig() {
  const cfg = {
    provider: document.getElementById('cfg-provider').value,
    model: document.getElementById('cfg-model').value,
    api_key: document.getElementById('cfg-apikey').value,
    temperature: parseFloat(document.getElementById('cfg-temp').value)
  };
  try {
    await fetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(cfg) });
    addMsg('assistant', '✅ Config saved');
    toggleConfig();
    loadStatus();
  } catch(e) { addMsg('error', 'Failed to save config'); }
}

loadStatus();
</script>
</body>
</html>)html";
}

} // namespace nonail
