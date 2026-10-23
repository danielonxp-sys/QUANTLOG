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

def require_env(name):
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f'Variable de entorno obligatoria no definida: {name}')
    return v

DB_HOST = require_env('DB_HOST')
DB_PORT = int(require_env('DB_PORT'))
DB_USER = require_env('DB_USER')
DB_PASSWORD = require_env('DB_PASSWORD')
DB_NAME = require_env('DB_NAME')
API_KEY = os.getenv('API_KEY', '')
CORS_ORIGINS = [o.strip() for o in os.getenv('CORS_ORIGINS', '').split(',') if o.strip()]

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

app = FastAPI(title='quantlog-api', version=6, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
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
    'riskBaseMode': 'risk_base_mode',
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

# Columnas calculadas por la BD (GENERATED ALWAYS): solo lectura, nunca se insertan.
TRADE_READ_MAP = {**TRADE_MAP, 'multiplier': 'multiplier', 'pnlGross': 'pnl_gross',
                  'pnlNet': 'pnl_net', 'riskUsd': 'risk_usd', 'rMultiple': 'r_multiple'}

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
    trades = [row_to_json(r, TRADE_READ_MAP, bools=('planFollowed', 'aplus')) for r in cur.fetchall()]
    cur.execute('SELECT * FROM reviews')
    reviews = {clean(r['week_key']): {'grade': r['grade'], 'notes': r['notes'],
                                      'lessons': r['lessons']} for r in cur.fetchall()}
    active = accounts[0]['id'] if accounts else ''
    saved_settings = {'activeAccountId': active}
    try:
        cur.execute("SELECT v FROM kv WHERE k='settings'")
        row = cur.fetchone()
        if row and row['v']:
            saved = json.loads(row['v'])
            if isinstance(saved, dict):
                saved_settings.update(saved)
                if not saved_settings.get('activeAccountId'):
                    saved_settings['activeAccountId'] = active
    except Exception:
        pass
    conn.close()
    return {'version': 5, 'trades': trades, 'accounts': accounts,
            'instruments': instruments, 'settings': saved_settings,
            'reviews': reviews}

@app.put('/api/v1/state', dependencies=[Depends(require_auth)])
async def put_state(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='JSON invalido')
    if body.get('version') not in (5, 6):
        raise HTTPException(status_code=400, detail='version debe ser 5 o 6')

    conn = connect(); cur = conn.cursor()
    try:
        cur.execute('SET FOREIGN_KEY_CHECKS=0')
        for t in ('trades', 'accounts', 'instruments', 'reviews'):
            cur.execute(f'DELETE FROM `{t}`')
        cur.execute('SET FOREIGN_KEY_CHECKS=1')

        imported = {'accounts': 0, 'instruments': 0, 'trades': 0, 'reviews': 0}

        for a in body.get('accounts', []):
            row = json_to_row(a, ACCOUNT_MAP)
            if not row.get('risk_base_mode'):
                row['risk_base_mode'] = 'current'
            insert_dict(cur, 'accounts', row)
            imported['accounts'] += 1

        inst_mult = {}
        for i in body.get('instruments', []):
            irow = json_to_row(i, INSTRUMENT_MAP)
            insert_dict(cur, 'instruments', irow)
            inst_mult[str(i.get('symbol', '')).upper()] = irow.get('multiplier') or 1
            imported['instruments'] += 1

        for t in body.get('trades', []):
            row = json_to_row(t, TRADE_MAP)
            if not row.get('account_id'):
                raise HTTPException(status_code=400, detail='trade sin accountId')
            asset = str(row.get('asset', '')).upper()
            row['instrument_symbol'] = asset if asset in inst_mult else None
            row['multiplier'] = inst_mult.get(asset, 1)
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
