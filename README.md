MC Stats

A live web dashboard for monitoring Minecraft Java server player statistics.

MC Stats reads player data directly from a Minecraft server and displays statistics through a web dashboard. The dashboard updates in real time using WebSocket.

Features

- Live online player count
- Online player list
- Player levels
- Highest level record
- Mob kills
- Player kills
- Deaths
- Blocks mined
- Play time
- Player ranking
- Player search
- Live updates without refreshing the page
- Minecraft server status and latency
- SQLite database for storing player statistics
- Optional RCON support for forcing Minecraft to save player data

---

Requirements

Before installing MC Stats, make sure you have:

- Python 3.10+
- A Minecraft Java server
- Access to the Minecraft server files
- A Fabric/compatible Minecraft server that stores player statistics in the standard Minecraft format

---

Installation

Clone the repository:

git clone https://github.com/YOUR_USERNAME/mc-stats.git
cd mc-stats

Create a virtual environment:

python -m venv .venv

Activate it.

Linux

source .venv/bin/activate

Windows

.venv\Scripts\activate

Install the required packages:

pip install fastapi uvicorn mcstatus nbtlib watchdog mcrcon

---

Project Structure

Your project should look similar to this:

mc-stats/
├── app.py
├── static/
│   └── index.html
├── stats.db
└── .venv/

The "stats.db" file is created automatically when the application starts.

---

Connecting MC Stats to Your Minecraft Server

MC Stats needs to know where your Minecraft server is located.

By default, it looks for the server inside:

./server

You can change this using the "MC_SERVER_DIR" environment variable.

For example, if your Minecraft server is located at:

/home/minecraft/server

run:

export MC_SERVER_DIR="/home/minecraft/server"

Then start MC Stats.

The application automatically reads:

server.properties

from the Minecraft server directory.

It also detects the Minecraft world and reads player statistics from the appropriate directories.

---

Start the Dashboard

Run:

uvicorn app:app --host 0.0.0.0 --port 8000

You should see something similar to:

Uvicorn running on http://0.0.0.0:8000

Open the dashboard in your browser:

http://YOUR_SERVER_IP:8000

For example:

http://192.168.1.100:8000

If MC Stats is running on the same machine:

http://127.0.0.1:8000

---

Running MC Stats With a Minecraft Server

MC Stats does not replace your Minecraft server.

You should run your Minecraft server normally and run MC Stats separately.

Example:

Minecraft Server
       │
       ├── server.properties
       ├── world/
       │   ├── stats/
       │   └── playerdata/
       │
       ▼
    MC Stats
       │
       ▼
   Web Dashboard

MC Stats watches the Minecraft player data files and updates its database when player statistics change.

---

How It Works

MC Stats uses several components to collect and display data.

1. Minecraft Player Statistics

Minecraft stores player statistics in JSON files.

MC Stats reads statistics such as:

Deaths
Mob Kills
Player Kills
Blocks Mined
Play Time

The application also reads the player's Minecraft level from the player data files.

2. SQLite Database

MC Stats stores the collected information in:

stats.db

The database keeps information such as:

UUID
Player Name
Current Level
Maximum Level
Deaths
Mob Kills
Player Kills
Blocks Mined
Play Time
First Seen
Last Updated

3. Minecraft Server Status

MC Stats periodically connects to the Minecraft server using its address.

The default address is:

127.0.0.1:25565

You can change it with:

export MC_ADDRESS="127.0.0.1:25565"

For example:

export MC_ADDRESS="play.example.com:25565"

The dashboard can then display:

- Server status
- Online players
- Maximum players
- Server version
- Latency

4. File Watcher

MC Stats monitors Minecraft player data files.

When a player's statistics change, MC Stats detects the change and refreshes the player's information.

This is handled using "watchdog".

5. WebSocket

The dashboard uses WebSocket for live updates.

Instead of refreshing the browser manually, the server sends updated data to connected browsers automatically.

The WebSocket endpoint is:

/ws

The normal API endpoint is:

/api/stats

---

Environment Variables

You can configure MC Stats using environment variables.

Minecraft Server Directory

export MC_SERVER_DIR="/path/to/minecraft/server"

Minecraft Server Address

export MC_ADDRESS="127.0.0.1:25565"

Dashboard Server Name

export SERVER_NAME="My Minecraft Server"

World Name

Normally the world name is detected automatically from "server.properties".

You can override it with:

export MC_WORLD="world"

Database Location

By default:

stats.db

You can change it:

export DB_PATH="/path/to/stats.db"

---

RCON Support

MC Stats can optionally use Minecraft RCON to force the server to save player data.

Enable RCON in:

server.properties

Example:

enable-rcon=true
rcon.port=25575
rcon.password=YOUR_PASSWORD

Then configure MC Stats:

export RCON_HOST="127.0.0.1"
export RCON_PORT="25575"
export RCON_PASSWORD="YOUR_PASSWORD"

Restart MC Stats after changing these settings.

«Never publish your RCON password on GitHub.»

---

Running in the Background

For a temporary/background process on Linux:

nohup uvicorn app:app --host 0.0.0.0 --port 8000 > mc-stats.log 2>&1 &

Check the log:

tail -f mc-stats.log

---

Running With systemd

For a permanent installation, you can create a systemd service.

Create:

sudo nano /etc/systemd/system/mc-stats.service

Add:

[Unit]
Description=MC Stats Dashboard
After=network.target

[Service]
Type=simple
User=minecraft
WorkingDirectory=/opt/mc-stats
Environment="MC_SERVER_DIR=/opt/minecraft/server"
Environment="MC_ADDRESS=127.0.0.1:25565"
Environment="SERVER_NAME=My Minecraft Server"
ExecStart=/opt/mc-stats/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

Then run:

sudo systemctl daemon-reload
sudo systemctl enable --now mc-stats

Check the service:

systemctl status mc-stats

View logs:

journalctl -u mc-stats -f

---

Updating MC Stats

Stop the application if it is running:

sudo systemctl stop mc-stats

Update the repository:

cd /opt/mc-stats
git pull

Update dependencies:

source .venv/bin/activate
pip install -r requirements.txt

Start it again:

sudo systemctl start mc-stats

---

Security

If the dashboard is exposed to the internet, do not expose Minecraft RCON to the public internet.

Keep RCON bound to localhost when possible:

127.0.0.1

Also consider placing MC Stats behind a reverse proxy such as Nginx or Caddy and using HTTPS.

---

Troubleshooting

The dashboard cannot find the Minecraft server

Check:

echo $MC_SERVER_DIR

Make sure the directory contains:

server.properties
world/

Then check:

ls "$MC_SERVER_DIR"

---

Player statistics are not updating

Make sure the application can read the Minecraft server files:

ls "$MC_SERVER_DIR/world"

Also check the statistics directory:

ls "$MC_SERVER_DIR/world/stats"

For newer Minecraft versions, the application can also detect the newer player data directory structure.

---

Server status shows offline

Check the Minecraft server address:

echo $MC_ADDRESS

Test the Minecraft server separately and make sure the server is running.

---

Port 8000 is not accessible

Make sure MC Stats is listening on all interfaces:

uvicorn app:app --host 0.0.0.0 --port 8000

If a firewall is enabled, allow port "8000".

For UFW:

sudo ufw allow 8000/tcp

---

API

MC Stats provides a statistics API:

GET /api/stats

Example:

curl http://127.0.0.1:8000/api/stats

The API returns server information, totals and player statistics.

WebSocket:

/ws

The WebSocket sends the latest dashboard data whenever the statistics are updated.

---

License

Add your preferred license here.

For example:

MIT License

---

Credits

Built with:

- FastAPI
- SQLite
- WebSocket
- mcstatus
- nbtlib
- watchdog
- mcrcon
- Vanilla JavaScript
- Minecraft Java Edition

Created by Agravix 
