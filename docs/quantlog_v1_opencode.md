### TAREA: QUANTLOG 1.0 — crear BD MariaDB + API FastAPI + arranque automático con systemd

#### REGLAS OBLIGATORIAS
1. PROHIBIDO instalar paquetes (nada de pip/apt). Todo está preinstalado en el venv.
2. El usuario gestiona TODO desde la GUI. Tu trabajo: dejar BD + API + autostart listos.
3. Usa SIEMPRE el intérprete `/home/daniel/mi_entorno/bin/python`.
4. Trabaja en `/home/daniel/Proyectos/apextradingjournal/quantlog-api/` (créala si no existe).
5. NO modifiques `journal-v1.html`, `quantlog_v5_schema.sql` ni `quantlog_v5_api_contract.json`.
6. Ejecuta los pasos en orden, verificando cada uno. Si algo falla, aplica TROUBLESHOOTING
   y reintenta una vez. Luego informa.
7. La ÚNICA entrada del usuario es la contraseña root de MariaDB (ya puesta en CONFIGURACIÓN).
8. Al terminar, imprime el INFORME FINAL.

#### CONFIGURACIÓN
```
DB_HOST          = 127.0.0.1
DB_PORT          = 3306
DB_NAME          = quantlog_v1
DB_ROOT_USER     = root
DB_ROOT_PASSWORD = <tu_clave_root>          ← ÚNICO dato que pone el usuario (ya sustituido)
DB_USER          = quantlog_api
DB_PASSWORD      = <tu_clave_api>
API_PORT         = 8000
API_KEY          = (vacío = sin autenticación, desarrollo local)
PROJECT_DIR      = /home/daniel/Proyectos/apextradingjournal
APP_DIR          = /home/daniel/Proyectos/apextradingjournal/quantlog-api
PYTHON           = /home/daniel/mi_entorno/bin/python
```

#### PASO 0 — Verificar intérprete y dependencias
Ejecuta:
```
/home/daniel/mi_entorno/bin/python -c "import fastapi, uvicorn, mysql.connector; print('DEPENDENCIAS OK')"
```
Si falla: DETENTE e informa:
"Faltan dependencias en el venv. Ejecuta:
 /home/daniel/mi_entorno/bin/pip install fastapi uvicorn[standard] mysql-connector-python"

#### PASO 1 — Crear estructura y archivos
Crea `/home/daniel/Proyectos/apextradingjournal/quantlog-api/` y dentro estos archivos
con EXACTAMENTE este contenido:

##### Archivo: quantlog-api/.env
```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=quantlog_v1
DB_ROOT_USER=root
DB_ROOT_PASSWORD=MI_CLAVE_ROOT
DB_USER=quantlog_api
DB_PASSWORD=<tu_clave_api>
API_PORT=8000
API_KEY=
```

##### Archivo: quantlog-api/setup_db.py
```python
#!/usr/bin/env python3
"""QUANTLOG 1.0 - Crea BD, tablas, vistas y usuario de API en MariaDB.
No requiere mysql CLI: usa mysql-connector-python. Idempotente.
Nota: usa VARCHAR(36) para los IDs (evita el relleno de espacios de CHAR)."""
import os, sys
import mysql.connector

def load_env_file(path='.env'):
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass

load_env_file()

DB_HOST   = os.getenv('DB_HOST', '127.0.0.1')
DB_PORT   = int(os.getenv('DB_PORT', '3306'))
DB_NAME   = os.getenv('DB_NAME', 'quantlog_v1')
ROOT_USER = os.getenv('DB_ROOT_USER', 'root')
ROOT_PASS = os.getenv('DB_ROOT_PASSWORD', '')
API_USER  = os.getenv('DB_USER', 'quantlog_api')
API_PASS  = os.getenv('DB_PASSWORD', '<tu_clave_api>')

assert API_USER.replace('_', '').isalnum(), 'DB_USER debe ser alfanumerico'

SCHEMA = """
CREATE DATABASE IF NOT EXISTS quantlog_v1 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE quantlog_v1;

CREATE TABLE IF NOT EXISTS accounts (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  initial_balance DECIMAL(24,8) NOT NULL DEFAULT 0,
  risk_per_trade_pct DECIMAL(9,4) NOT NULL DEFAULT 1,
  daily_loss_limit_pct DECIMAL(9,4) NOT NULL DEFAULT 3,
  weekly_loss_limit_pct DECIMAL(9,4) NOT NULL DEFAULT 6,
  max_trades_per_day INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at TIMESTAMP NULL,
  INDEX idx_accounts_updated (updated_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS instruments (
  symbol VARCHAR(48) PRIMARY KEY,
  multiplier DECIMAL(24,10) NOT NULL DEFAULT 1,
  pip_size DECIMAL(24,10) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at TIMESTAMP NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS trades (
  id VARCHAR(36) PRIMARY KEY,
  account_id VARCHAR(36) NOT NULL,
  instrument_symbol VARCHAR(48) NULL,
  `datetime` DATETIME NOT NULL,
  asset VARCHAR(64) NOT NULL,
  direction ENUM('LONG','SHORT') NOT NULL,
  status ENUM('closed','open','planned','cancelled') NOT NULL DEFAULT 'closed',
  entry_price DECIMAL(24,10) NULL,
  exit_price DECIMAL(24,10) NULL,
  stop_loss DECIMAL(24,10) NULL,
  take_profit DECIMAL(24,10) NULL,
  size DECIMAL(24,10) NOT NULL DEFAULT 1,
  commission DECIMAL(24,8) NOT NULL DEFAULT 0,
  setup VARCHAR(255) NULL,
  session VARCHAR(48) NULL,
  notes MEDIUMTEXT NULL,
  tags MEDIUMTEXT NULL,
  errors MEDIUMTEXT NULL,
  emotions VARCHAR(120) NULL,
  plan_followed TINYINT(1) NOT NULL DEFAULT 0,
  aplus TINYINT(1) NOT NULL DEFAULT 0,
  mae_price DECIMAL(24,10) NULL,
  mfe_price DECIMAL(24,10) NULL,
  screenshot_id VARCHAR(36) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at TIMESTAMP NULL,
  INDEX idx_trades_account_date (account_id, `datetime`),
  INDEX idx_trades_status (status),
  INDEX idx_trades_asset (asset),
  INDEX idx_trades_updated (updated_at),
  CONSTRAINT fk_trades_account FOREIGN KEY (account_id)
    REFERENCES accounts(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_trades_instrument FOREIGN KEY (instrument_symbol)
    REFERENCES instruments(symbol) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS reviews (
  week_key DATE PRIMARY KEY,
  grade VARCHAR(2) NULL,
  notes MEDIUMTEXT NULL,
  lessons MEDIUMTEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sync_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  direction ENUM('pull','push','import','export') NOT NULL,
  status ENUM('ok','error') NOT NULL,
  message TEXT NULL,
  payload_rows INT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS kv (
  k VARCHAR(64) PRIMARY KEY,
  v MEDIUMTEXT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE OR REPLACE VIEW v_trade_metrics AS
SELECT
  t.id, t.asset, t.direction, t.status, t.`datetime`,
  t.entry_price, t.exit_price, t.stop_loss, t.take_profit,
  t.size, t.commission, COALESCE(i.multiplier, 1) AS multiplier,
  CASE WHEN t.status='closed' AND t.entry_price IS NOT NULL AND t.exit_price IS NOT NULL
    THEN (t.exit_price - t.entry_price) * IF(t.direction='LONG',1,-1) * t.size * COALESCE(i.multiplier,1)
    ELSE NULL END AS pnl_gross,
  CASE WHEN t.status='closed' AND t.entry_price IS NOT NULL AND t.exit_price IS NOT NULL
    THEN (t.exit_price - t.entry_price) * IF(t.direction='LONG',1,-1) * t.size * COALESCE(i.multiplier,1) - t.commission
    ELSE NULL END AS pnl_net,
  CASE WHEN t.status='closed' AND t.entry_price IS NOT NULL AND t.stop_loss IS NOT NULL
    AND (t.entry_price - t.stop_loss) <> 0
    THEN (t.exit_price - t.entry_price) / (t.entry_price - t.stop_loss)
    ELSE NULL END AS r_multiple,
  ABS(t.entry_price - t.stop_loss) * t.size * COALESCE(i.multiplier,1) AS risk_usd,
  t.setup, t.session, t.plan_followed, t.aplus, t.account_id
FROM trades t
LEFT JOIN instruments i ON t.instrument_symbol = i.symbol
WHERE t.deleted_at IS NULL;

CREATE OR REPLACE VIEW v_daily_pnl AS
SELECT
  DATE(t.`datetime`) AS trade_date, t.account_id,
  COUNT(*) AS trades_count,
  SUM(CASE WHEN m.pnl_net > 0 THEN 1 ELSE 0 END) AS wins,
  SUM(CASE WHEN m.pnl_net < 0 THEN 1 ELSE 0 END) AS losses,
  SUM(m.pnl_net) AS daily_pnl, SUM(m.r_multiple) AS daily_r
FROM trades t
JOIN v_trade_metrics m ON t.id = m.id
WHERE t.status = 'closed'
GROUP BY DATE(t.`datetime`), t.account_id;

CREATE OR REPLACE VIEW v_overtrading_days AS
SELECT
  DATE(t.`datetime`) AS trade_date, t.account_id,
  COUNT(*) AS trades_count, a.max_trades_per_day,
  CASE WHEN COUNT(*) > a.max_trades_per_day AND a.max_trades_per_day > 0 THEN 1 ELSE 0 END AS is_overtrading
FROM trades t
JOIN accounts a ON t.account_id = a.id
WHERE t.status = 'closed'
GROUP BY DATE(t.`datetime`), t.account_id;

CREATE OR REPLACE VIEW v_revenge_trades AS
SELECT
  curr.id AS trade_id, curr.`datetime` AS trade_time,
  prev.`datetime` AS prev_time,
  TIMESTAMPDIFF(MINUTE, prev.`datetime`, curr.`datetime`) AS minutes_since_prev,
  prev_m.pnl_net AS prev_pnl
FROM trades curr
JOIN trades prev ON prev.account_id = curr.account_id
  AND prev.`datetime` = (
    SELECT MAX(x.`datetime`) FROM trades x
    WHERE x.account_id = curr.account_id
      AND x.`datetime` < curr.`datetime`
      AND x.status = 'closed' AND x.deleted_at IS NULL)
JOIN v_trade_metrics prev_m ON prev.id = prev_m.id
WHERE curr.status='closed' AND curr.deleted_at IS NULL AND prev.deleted_at IS NULL
  AND prev_m.pnl_net < 0
  AND TIMESTAMPDIFF(MINUTE, prev.`datetime`, curr.`datetime`) BETWEEN 0 AND 15;
"""

def run():
    print(f'→ Conectando a MariaDB {DB_HOST}:{DB_PORT} como {ROOT_USER}...')
    try:
        conn = mysql.connector.connect(host=DB_HOST, port=DB_PORT,
                                       user=ROOT_USER, password=ROOT_PASS)
    except mysql.connector.Error as e:
        print(f'❌ No se pudo conectar como root: {e}')
        print('   Verifica: 1) MariaDB esta corriendo  2) DB_ROOT_PASSWORD en .env')
        sys.exit(1)

    cur = conn.cursor()
    print('→ Creando base de datos, tablas, indices y vistas...')
    statements = [s.strip() for s in SCHEMA.split(';') if s.strip()]
    for stmt in statements:
        cur.execute(stmt)
    conn.commit()
    print(f'   ✅ {len(statements)} sentencias SQL ejecutadas')

    print(f'→ Creando usuario de API "{API_USER}" con permisos limitados...')
    for host in ('localhost', '127.0.0.1', '%'):
        cur.execute(f"CREATE USER IF NOT EXISTS '{API_USER}'@'{host}' IDENTIFIED BY %s", (API_PASS,))
        cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {DB_NAME}.* TO '{API_USER}'@'{host}'")
    cur.execute('FLUSH PRIVILEGES')
    conn.commit()

    cur.execute('SHOW TABLES')
    tables = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    print(f'✅ BD "{DB_NAME}" lista. Tablas: {", ".join(tables)}')
    print(f'✅ Usuario "{API_USER}" creado (solo SELECT/INSERT/UPDATE/DELETE).')

if __name__ == '__main__':
    run()
```

##### Archivo: quantlog-api/main.py
```python
"""QUANTLOG 1.0 - API local FastAPI + MariaDB.
Endpoints: GET /api/v1/health | GET /api/v1/state | PUT /api/v1/state"""
import os, json
from contextlib import asynccontextmanager
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

import mysql.connector
from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware

def load_env_file(path='.env'):
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass

load_env_file()

DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_PORT = int(os.getenv('DB_PORT', '3306'))
DB_USER = os.getenv('DB_USER', 'quantlog_api')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'quantlog_v1')
API_KEY = os.getenv('API_KEY', '')

def connect():
    return mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                                   password=DB_PASSWORD, database=DB_NAME)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        c = connect(); c.close()
        print('✅ MariaDB conectado')
    except Exception as e:
        print(f'❌ Error BD al arrancar: {e}')
    yield

app = FastAPI(title='quantlog-api', version=5, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'],
                   allow_methods=['*'], allow_headers=['*'])

def require_auth(authorization: Optional[str] = Header(default=None)):
    if API_KEY and authorization != f'Bearer {API_KEY}':
        raise HTTPException(status_code=401, detail='API key invalida o ausente')

ACCOUNT_MAP = {
    'id': 'id', 'name': 'name',
    'initialBalance': 'initial_balance',
    'riskPerTradePct': 'risk_per_trade_pct',
    'dailyLossLimitPct': 'daily_loss_limit_pct',
    'weeklyLossLimitPct': 'weekly_loss_limit_pct',
    'maxTradesPerDay': 'max_trades_per_day',
    'createdAt': 'created_at',
}
INSTRUMENT_MAP = {'symbol': 'symbol', 'multiplier': 'multiplier', 'pipSize': 'pip_size'}
TRADE_MAP = {
    'id': 'id', 'accountId': 'account_id', 'datetime': 'datetime',
    'asset': 'asset', 'direction': 'direction', 'status': 'status',
    'entry': 'entry_price', 'exit': 'exit_price',
    'stopLoss': 'stop_loss', 'takeProfit': 'take_profit',
    'size': 'size', 'commission': 'commission',
    'setup': 'setup', 'session': 'session', 'notes': 'notes',
    'tags': 'tags', 'errors': 'errors', 'emotions': 'emotions',
    'planFollowed': 'plan_followed', 'aplus': 'aplus',
    'maePrice': 'mae_price', 'mfePrice': 'mfe_price',
    'screenshotId': 'screenshot_id', 'createdAt': 'created_at',
}

def clean(v):
    if isinstance(v, Decimal): return float(v)
    if isinstance(v, datetime): return v.strftime('%Y-%m-%dT%H:%M:%S')
    if isinstance(v, date): return v.isoformat()
    return v

def row_to_json(row, mapping, bools=()):
    inv = {v: k for k, v in mapping.items()}
    out = {}
    for col, val in row.items():
        key = inv.get(col)
        if key is None: continue
        val = clean(val)
        if key in bools: val = bool(val)
        out[key] = val
    return out

def fix_val(v):
    if isinstance(v, bool): return 1 if v else 0
    if isinstance(v, str):
        s = v.strip()
        if s == '': return None
        t = s.replace('T', ' ').replace('Z', '')
        try:
            return datetime.strptime(t[:19], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
        try:
            return datetime.strptime(t[:16], '%Y-%m-%d %H:%M').strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
    return v

def json_to_row(obj, mapping):
    return {mapping[k]: fix_val(v) for k, v in obj.items() if k in mapping}

def insert_dict(cur, table, row):
    cols = ', '.join(f'`{k}`' for k in row)
    phs = ', '.join(['%s'] * len(row))
    cur.execute(f'INSERT INTO `{table}` ({cols}) VALUES ({phs})', list(row.values()))

@app.get('/api/v1/health', dependencies=[Depends(require_auth)])
def health():
    try:
        c = connect(); cur = c.cursor(); cur.execute('SELECT 1'); cur.fetchone(); c.close()
        return {'ok': True, 'service': 'quantlog-api', 'version': 5, 'db': 'connected'}
    except Exception:
        return {'ok': False, 'service': 'quantlog-api', 'version': 5, 'db': 'disconnected'}

@app.get('/api/v1/state', dependencies=[Depends(require_auth)])
def get_state():
    conn = connect(); cur = conn.cursor(dictionary=True)
    cur.execute('SELECT * FROM accounts WHERE deleted_at IS NULL')
    accounts = [row_to_json(r, ACCOUNT_MAP) for r in cur.fetchall()]
    cur.execute('SELECT * FROM instruments WHERE deleted_at IS NULL')
    instruments = [row_to_json(r, INSTRUMENT_MAP) for r in cur.fetchall()]
    cur.execute('SELECT * FROM trades WHERE deleted_at IS NULL')
    trades = [row_to_json(r, TRADE_MAP, bools=('planFollowed', 'aplus')) for r in cur.fetchall()]
    cur.execute('SELECT * FROM reviews')
    reviews = {clean(r['week_key']): {'grade': r['grade'], 'notes': r['notes'],
                                      'lessons': r['lessons']} for r in cur.fetchall()}
    active = accounts[0]['id'] if accounts else ''
    try:
        cur.execute("SELECT v FROM kv WHERE k='settings'")
        row = cur.fetchone()
        if row and row['v']:
            saved = json.loads(row['v'])
            if saved.get('activeAccountId'):
                active = saved['activeAccountId']
    except Exception:
        pass
    conn.close()
    return {'version': 5, 'trades': trades, 'accounts': accounts,
            'instruments': instruments, 'settings': {'activeAccountId': active},
            'reviews': reviews}

@app.put('/api/v1/state', dependencies=[Depends(require_auth)])
async def put_state(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='JSON invalido')
    if body.get('version') != 5:
        raise HTTPException(status_code=400, detail='version debe ser 5')

    conn = connect(); cur = conn.cursor()
    try:
        cur.execute('SET FOREIGN_KEY_CHECKS=0')
        for t in ('trades', 'accounts', 'instruments', 'reviews'):
            cur.execute(f'DELETE FROM `{t}`')
        cur.execute('SET FOREIGN_KEY_CHECKS=1')

        imported = {'accounts': 0, 'instruments': 0, 'trades': 0, 'reviews': 0}

        for a in body.get('accounts', []):
            insert_dict(cur, 'accounts', json_to_row(a, ACCOUNT_MAP))
            imported['accounts'] += 1

        inst_syms = set()
        for i in body.get('instruments', []):
            insert_dict(cur, 'instruments', json_to_row(i, INSTRUMENT_MAP))
            inst_syms.add(str(i.get('symbol', '')).upper())
            imported['instruments'] += 1

        for t in body.get('trades', []):
            row = json_to_row(t, TRADE_MAP)
            if not row.get('account_id'):
                raise HTTPException(status_code=400, detail='trade sin accountId')
            asset = str(row.get('asset', '')).upper()
            row['instrument_symbol'] = asset if asset in inst_syms else None
            insert_dict(cur, 'trades', row)
            imported['trades'] += 1

        for wk, r in (body.get('reviews') or {}).items():
            insert_dict(cur, 'reviews', {'week_key': wk, 'grade': r.get('grade'),
                                         'notes': r.get('notes'), 'lessons': r.get('lessons')})
            imported['reviews'] += 1

        cur.execute("INSERT INTO kv (k,v) VALUES ('settings',%s) ON DUPLICATE KEY UPDATE v=VALUES(v)",
                    (json.dumps(body.get('settings') or {}),))
        cur.execute("INSERT INTO sync_log (direction,status,payload_rows) VALUES ('push','ok',%s)",
                    (sum(imported.values()),))
        conn.commit()
        return {'ok': True, 'imported': imported}
    except HTTPException:
        conn.rollback(); raise
    except Exception as e:
        conn.rollback()
        try:
            cur.execute("INSERT INTO sync_log (direction,status,message) VALUES ('push','error',%s)",
                        (str(e)[:1000],))
            conn.commit()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
```

#### PASO 2 — Crear la base de datos
```
cd /home/daniel/Proyectos/apextradingjournal/quantlog-api
/home/daniel/mi_entorno/bin/python setup_db.py
```
Esperado: "✅ BD quantlog_v1 lista" + lista de tablas.
- "Access denied" → revisa DB_ROOT_PASSWORD en .env.
- "Can't connect" → MariaDB no está corriendo; informa y detente.

#### PASO 3 — Crear el servicio systemd (arranque automático)
Crea el archivo `~/.config/systemd/user/quantlog-api.service` (crea la carpeta si no existe)
con EXACTAMENTE este contenido:
```ini
[Unit]
Description=QUANTLOG 1.0 API local (FastAPI + MariaDB)
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/daniel/Proyectos/apextradingjournal/quantlog-api
ExecStart=/home/daniel/mi_entorno/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
```
Luego ejecuta:
```
mkdir -p ~/.config/systemd/user
systemctl --user daemon-reload
systemctl --user enable --now quantlog-api.service
```
Verifica:
```
systemctl --user is-active quantlog-api     → debe decir "active"
```
Nota: si `is-active` da "inactive", ejecuta `journalctl --user -u quantlog-api -n 30`
y adjunta la salida al informe.

#### PASO 4 — Probar health
```
curl -s http://127.0.0.1:8000/api/v1/health
```
Esperado: `{"ok":true,"service":"quantlog-api","version":5,"db":"connected"}`

#### PASO 5 — Probar push
Crea `/home/daniel/Proyectos/apextradingjournal/quantlog-api/test_state.json`:
```json
{
  "version": 5,
  "trades": [{
    "id": "t-test-0001", "accountId": "acc-test-0001",
    "datetime": "2026-08-20T10:30",
    "asset": "EURUSD", "direction": "LONG", "status": "closed",
    "entry": 1.085, "exit": 1.09, "stopLoss": 1.082, "takeProfit": 1.092,
    "size": 100000, "commission": 2,
    "setup": "Breakout", "session": "London",
    "tags": "test", "errors": "", "emotions": "Focused",
    "planFollowed": true, "aplus": false,
    "maePrice": 1.0835, "mfePrice": 1.0915, "screenshotId": "",
    "createdAt": "2026-08-20T10:35:00"
  }],
  "accounts": [{
    "id": "acc-test-0001", "name": "Cuenta Test",
    "initialBalance": 10000, "riskPerTradePct": 1,
    "dailyLossLimitPct": 3, "weeklyLossLimitPct": 6,
    "maxTradesPerDay": 5, "createdAt": "2026-01-01T00:00:00"
  }],
  "instruments": [{"symbol": "EURUSD", "multiplier": 1, "pipSize": 0.0001}],
  "settings": {"activeAccountId": "acc-test-0001"},
  "reviews": {"2026-08-17": {"grade": "A", "notes": "semana test", "lessons": ""}}
}
```
Ejecuta:
```
curl -s -X PUT http://127.0.0.1:8000/api/v1/state \
  -H "Content-Type: application/json" \
  -d @/home/daniel/Proyectos/apextradingjournal/quantlog-api/test_state.json
```
Esperado: `{"ok":true,"imported":{"accounts":1,"instruments":1,"trades":1,"reviews":1}}`

#### PASO 6 — Probar pull
```
curl -s http://127.0.0.1:8000/api/v1/state
```
Verifica que devuelve: 1 trade (asset EURUSD), 1 cuenta, 1 instrumento y la review "2026-08-17".

#### PASO 7 — Endurecimiento opcional (recomendado)
El usuario root de MariaDB ya no se necesita tras la instalación. Para mayor seguridad,
edita `/home/daniel/Proyectos/apextradingjournal/quantlog-api/.env` y deja
`DB_ROOT_PASSWORD=` vacío (la API usa quantlog_api, no root).
Guarda la clave root en un lugar seguro por si necesitas re-ejecutar setup_db.py.

#### TROUBLESHOOTING
| Error | Causa | Acción |
|---|---|---|
| ModuleNotFoundError | Falta dependencia en el venv | Informar: `/home/daniel/mi_entorno/bin/pip install fastapi uvicorn[standard] mysql-connector-python` |
| Access denied (root) | Clave root mal | Pedir corregir DB_ROOT_PASSWORD en .env y reejecutar PASO 2 |
| Can't connect | MariaDB detenido | Pedir al usuario: `sudo systemctl start mariadb` y `sudo systemctl enable mariadb` |
| is-active = inactive | Servicio falló | Adjuntar `journalctl --user -u quantlog-api -n 30` al informe |
| puerto 8000 ocupado | Otro proceso | Cambiar puerto en .service y .env, y avisar el cambio |

#### INFORME FINAL (obligatorio)
Imprime:
1. ✅/❌ DEPENDENCIAS OK (intérprete usado)
2. ✅/❌ Base de datos creada (tablas)
3. ✅/❌ Usuario quantlog_api creado
4. ✅/❌ Servicio systemd activo y habilitado (arranque automático)
5. ✅/❌ health / push / pull
6. Instrucciones de USO DIARIO:
   - "La API se inicia sola con el sistema. No tienes que hacer nada."
   - "Abre /home/daniel/Proyectos/apextradingjournal/journal-v1.html →
      pestaña Datos → Backend/API → Base URL http://127.0.0.1:8000 →
      Guardar → Probar → Pull/Push."
   - "Todo se gestiona desde la interfaz gráfica."

### FIN DEL PROMPT PARA OPENCODE  (copia hasta aquí)

---

## USO DIARIO (todo desde la interfaz gráfica)

1. Enciende el equipo. **La API arranca sola** (servicio systemd). No haces nada.
2. Abre `/home/daniel/Proyectos/apextradingjournal/journal-v1.html` en el navegador.
3. Pestaña **Datos → Backend/API** → Base URL `http://127.0.0.1:8000`
   → **Guardar** → **Probar API** → **Pull / Push**.
4. Gestiona trades, cuentas, instrumentos, demo y backups **siempre desde la GUI**.

---

## GESTIÓN DEL SERVICIO (solo si algún día lo necesitas)

```bash
systemctl --user status  quantlog-api     # ver estado
systemctl --user restart quantlog-api     # reiniciar
systemctl --user stop    quantlog-api     # detener
systemctl --user start   quantlog-api     # iniciar
journalctl --user -u quantlog-api -f       # ver logs en vivo
```

Para que arranque con el sistema incluso SIN iniciar sesión (opcional, requiere sudo una vez):
```bash
sudo loginctl enable-linger daniel

(Sin linger, el servicio arranca cuando inicias sesión, que para un escritorio es suficiente.)
