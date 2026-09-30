"""MC Stats — آمار زنده‌ی سرور Fabric ماینکرفت (FastAPI + SQLite + WebSocket)."""
import asyncio, json, os, sqlite3, threading, time
from contextlib import asynccontextmanager
from pathlib import Path

import nbtlib
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from mcstatus import JavaServer
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ---------- تنظیمات (با متغیر محیطی عوض میشن) ----------
SERVER_DIR = Path(os.getenv("MC_SERVER_DIR", "./server")).resolve()   # پوشه‌ی سرور ماینکرفت


def _props() -> dict:
    out = {}
    try:
        for ln in (SERVER_DIR / "server.properties").read_text("utf-8").splitlines():
            if "=" in ln and not ln.startswith("#"):
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip()
    except Exception:
        pass
    return out


PROPS = _props()  # اسم دنیا و تنظیمات RCON خودکار از server.properties خونده میشن
WORLD = SERVER_DIR / os.getenv("MC_WORLD", PROPS.get("level-name", "world"))


def _pick(new: str, old: str) -> Path:
    """نسخه‌های جدید ماینکرفت: world/players/stats و world/players/data؛ قدیمی: world/stats و world/playerdata"""
    return WORLD / new if (WORLD / new).is_dir() else WORLD / old


STATS_DIR = _pick("players/stats", "stats")
DATA_DIR = _pick("players/data", "playerdata")
ADDRESS = os.getenv("MC_ADDRESS", "127.0.0.1:25565")                  # آدرس سرور برای وضعیت آنلاین
SERVER_NAME = os.getenv("SERVER_NAME", "سرور ماینکرفت")
_rcon_on = PROPS.get("enable-rcon") == "true"
RCON_PASSWORD = os.getenv("RCON_PASSWORD", PROPS.get("rcon.password", "") if _rcon_on else "")
RCON_HOST = os.getenv("RCON_HOST", "127.0.0.1")
RCON_PORT = int(os.getenv("RCON_PORT", PROPS.get("rcon.port", "25575")))
SAVE_EVERY = int(os.getenv("SAVE_EVERY", "10"))                       # ثانیه
DB_PATH = os.getenv("DB_PATH", "stats.db")
STATIC = Path(__file__).parent / "static"

# ---------- دیتابیس ----------
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
lock = threading.Lock()
db.execute("""CREATE TABLE IF NOT EXISTS players(
  uuid TEXT PRIMARY KEY, name TEXT, level INT DEFAULT 0, max_level INT DEFAULT 0,
  deaths INT DEFAULT 0, mob_kills INT DEFAULT 0, player_kills INT DEFAULT 0,
  blocks_mined INT DEFAULT 0, play_ticks INT DEFAULT 0, first_seen REAL, updated_at REAL)""")
db.commit()

state = dict(up=False, online=0, max=0, names=[], version="", latency=0)
clients: set[WebSocket] = set()
pending: set[str] = set()
plock = threading.Lock()
loop: asyncio.AbstractEventLoop | None = None
wake: asyncio.Event | None = None


# ---------- خواندن فایل‌های ماینکرفت ----------
def usercache() -> dict:
    try:
        data = json.loads((SERVER_DIR / "usercache.json").read_text("utf-8"))
        return {e["uuid"]: e["name"] for e in data}
    except Exception:
        return {}


def read_stats(uuid: str):
    try:
        s = json.loads((STATS_DIR / f"{uuid}.json").read_text("utf-8")).get("stats", {})
    except Exception as e:
        print("stats read failed:", uuid, e)
        return None
    c = s.get("minecraft:custom", {})
    return dict(
        deaths=c.get("minecraft:deaths", 0),
        mob_kills=c.get("minecraft:mob_kills", 0),
        player_kills=c.get("minecraft:player_kills", 0),
        blocks_mined=sum(s.get("minecraft:mined", {}).values()),
        play_ticks=c.get("minecraft:play_time", c.get("minecraft:play_one_minute", 0)),
    )


def read_level(uuid: str):
    try:
        return int(nbtlib.load(DATA_DIR / f"{uuid}.dat")["XpLevel"])
    except Exception:
        return None


def refresh(uuid: str, name: str | None = None):
    """آمار یک بازیکن رو از فایل‌ها می‌خونه و تو دیتابیس ذخیره می‌کنه (بازیکن جدید = ردیف جدید)."""
    st, lv, now = read_stats(uuid), read_level(uuid), time.time()
    with lock:
        row = db.execute("SELECT * FROM players WHERE uuid=?", (uuid,)).fetchone()
        cur = dict(row) if row else dict(level=0, max_level=0, deaths=0, mob_kills=0,
                                         player_kills=0, blocks_mined=0, play_ticks=0)
        if st:
            cur.update(st)
        if lv is not None:
            cur["level"] = lv
            cur["max_level"] = max(cur["max_level"], lv)  # رکورد لول: با انچنت و مصرف پایین نمیاد
        nm = usercache().get(uuid) or name or (row["name"] if row else uuid[:8])
        db.execute(
            "INSERT OR REPLACE INTO players VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (uuid, nm, cur["level"], cur["max_level"], cur["deaths"], cur["mob_kills"],
             cur["player_kills"], cur["blocks_mined"], cur["play_ticks"],
             row["first_seen"] if row else now, now))
        db.commit()


def snapshot() -> dict:
    with lock:
        rows = [dict(r) for r in db.execute("SELECT * FROM players")]
    online = {n.lower() for n in state["names"]}
    for r in rows:
        r["online"] = r["name"].lower() in online
        r["kills"] = r["mob_kills"] + r["player_kills"]
        r["play_hours"] = round(r["play_ticks"] / 72000, 1)
    totals = dict(
        players=len(rows),
        deaths=sum(r["deaths"] for r in rows),
        kills=sum(r["kills"] for r in rows),
        blocks_mined=sum(r["blocks_mined"] for r in rows),
        top_level=max((r["max_level"] for r in rows), default=0),
    )
    server = {**state, "name": SERVER_NAME, "address": ADDRESS, "ts": time.time()}
    return dict(server=server, totals=totals, players=rows)


async def broadcast():
    msg = json.dumps(snapshot(), ensure_ascii=False)
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            clients.discard(ws)


# ---------- واچر فایل‌ها: هر تغییر => آپدیت فوری ----------
class Handler(FileSystemEventHandler):
    def _hit(self, path):
        p = Path(path)
        if p.suffix in (".json", ".dat") and len(p.stem) == 36:
            with plock:
                pending.add(p.stem)
            loop.call_soon_threadsafe(wake.set)

    def on_created(self, e): self._hit(e.src_path)
    def on_modified(self, e): self._hit(e.src_path)
    def on_moved(self, e): self._hit(e.dest_path)


async def worker():
    while True:
        await wake.wait()
        await asyncio.sleep(0.3)  # چند تغییر پشت هم رو یکی می‌کنه
        wake.clear()
        with plock:
            batch = set(pending)
            pending.clear()
        for u in batch:
            await asyncio.to_thread(refresh, u)
        await broadcast()


def rcon_save():
    from mcrcon import MCRcon
    with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as m:
        m.command("save-all flush")


async def poller():
    """هر ۵ ثانیه وضعیت آنلاین رو می‌گیره؛ ورود بازیکن جدید فوری ثبت میشه."""
    prev, last_save = set(), 0.0
    while True:
        was_up, names, ids = state["up"], [], {}
        try:
            srv = JavaServer.lookup(ADDRESS, timeout=3)
            st = await srv.async_status()
            for p in st.players.sample or []:
                names.append(p.name)
                ids[p.name] = p.id
            if len(names) < st.players.online:  # اگه سمپل ناقص بود، Query (اگه فعال باشه)
                try:
                    names = list((await srv.async_query()).players.names)
                except Exception:
                    pass
            state.update(up=True, online=st.players.online, max=st.players.max,
                         names=names, version=st.version.name, latency=round(st.latency))
        except Exception:
            state.update(up=False, online=0, names=[])
        joined = set(names) - prev
        for n in joined:
            if n in ids:  # ثبت فوری بازیکن جدید، حتی قبل از ساخته‌شدن فایل آمار
                await asyncio.to_thread(refresh, ids[n], n)
        now = time.time()
        if RCON_PASSWORD and state["online"] and (joined or now - last_save >= SAVE_EVERY):
            last_save = now
            try:
                await asyncio.to_thread(rcon_save)  # فایل‌ها رو فلاش می‌کنه، واچر بقیه‌ش رو انجام میده
            except Exception as e:
                print("RCON error:", e)
        if joined or set(names) != prev or state["up"] != was_up:
            await broadcast()
        prev = set(names)
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop, wake
    loop, wake = asyncio.get_running_loop(), asyncio.Event()
    uuids = set()
    for d, pat in ((STATS_DIR, "*.json"), (DATA_DIR, "*.dat")):
        uuids |= {f.stem for f in d.glob(pat) if len(f.stem) == 36}
    for u in uuids:
        await asyncio.to_thread(refresh, u)
    obs = Observer()
    for d in (STATS_DIR, DATA_DIR):
        if d.is_dir():
            obs.schedule(Handler(), str(d))
        else:
            print(f"هشدار: پوشه {d} پیدا نشد؛ MC_SERVER_DIR رو چک کن.")
    obs.start()
    tasks = [asyncio.create_task(worker()), asyncio.create_task(poller())]
    yield
    for t in tasks:
        t.cancel()
    obs.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/api/stats")
def api_stats():
    return snapshot()


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    clients.add(sock)
    try:
        await sock.send_text(json.dumps(snapshot(), ensure_ascii=False))
        while True:
            await sock.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(sock)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
