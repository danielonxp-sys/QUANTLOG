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

def require_env(name):
    v = os.getenv(name)
    if not v:
        sys.exit(f'❌ Variable de entorno obligatoria no definida: {name}')
    return v

DB_HOST   = require_env('DB_HOST')
DB_PORT   = int(require_env('DB_PORT'))
DB_NAME   = require_env('DB_NAME')
ROOT_USER = require_env('DB_ROOT_USER')
ROOT_PASS = os.getenv('DB_ROOT_PASSWORD', '')
API_USER  = require_env('DB_USER')
API_PASS  = require_env('DB_PASSWORD')

assert API_USER.replace('_', '').isalnum(), 'DB_USER debe ser alfanumerico'
assert DB_NAME.replace('_', '').isalnum(), 'DB_NAME debe ser alfanumerico'

SCHEMA = """
CREATE DATABASE IF NOT EXISTS `{DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `{DB}`;

CREATE TABLE IF NOT EXISTS accounts (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  initial_balance DECIMAL(24,8) NOT NULL DEFAULT 0,
  risk_per_trade_pct DECIMAL(9,4) NOT NULL DEFAULT 1,
  daily_loss_limit_pct DECIMAL(9,4) NOT NULL DEFAULT 3,
  weekly_loss_limit_pct DECIMAL(9,4) NOT NULL DEFAULT 6,
  max_trades_per_day INT NOT NULL DEFAULT 0,
  risk_base_mode VARCHAR(16) NOT NULL DEFAULT 'current',
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
  multiplier DECIMAL(24,10) NOT NULL DEFAULT 1,
  pnl_gross DECIMAL(36,10) GENERATED ALWAYS AS (
    CASE WHEN status='closed' AND entry_price IS NOT NULL AND exit_price IS NOT NULL
      THEN (exit_price - entry_price) * IF(direction='LONG',1,-1) * size * multiplier END) STORED,
  pnl_net DECIMAL(36,10) GENERATED ALWAYS AS (
    CASE WHEN status='closed' AND entry_price IS NOT NULL AND exit_price IS NOT NULL
      THEN (exit_price - entry_price) * IF(direction='LONG',1,-1) * size * multiplier - commission END) STORED,
  risk_usd DECIMAL(36,10) GENERATED ALWAYS AS (
    CASE WHEN entry_price IS NOT NULL AND stop_loss IS NOT NULL
      THEN ABS(entry_price - stop_loss) * size * multiplier END) STORED,
  r_multiple DECIMAL(24,10) GENERATED ALWAYS AS (
    CASE WHEN status='closed' AND entry_price IS NOT NULL AND exit_price IS NOT NULL
      AND stop_loss IS NOT NULL AND entry_price <> stop_loss
      THEN (exit_price - entry_price) / (entry_price - stop_loss) END) STORED,
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
  t.size, t.commission, t.multiplier,
  t.pnl_gross, t.pnl_net, t.r_multiple, t.risk_usd,
  t.setup, t.session, t.plan_followed, t.aplus, t.account_id
FROM trades t
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

MIGRATIONS = [
    "ALTER TABLE `{DB}`.accounts ADD COLUMN IF NOT EXISTS risk_base_mode VARCHAR(16) NOT NULL DEFAULT 'current'",
    "ALTER TABLE `{DB}`.trades ADD COLUMN IF NOT EXISTS multiplier DECIMAL(24,10) NOT NULL DEFAULT 1",
    "UPDATE `{DB}`.trades t JOIN `{DB}`.instruments i ON t.instrument_symbol=i.symbol SET t.multiplier=i.multiplier",
    "ALTER TABLE `{DB}`.trades ADD COLUMN IF NOT EXISTS pnl_gross DECIMAL(36,10) GENERATED ALWAYS AS (CASE WHEN status='closed' AND entry_price IS NOT NULL AND exit_price IS NOT NULL THEN (exit_price - entry_price) * IF(direction='LONG',1,-1) * size * multiplier END) STORED",
    "ALTER TABLE `{DB}`.trades ADD COLUMN IF NOT EXISTS pnl_net DECIMAL(36,10) GENERATED ALWAYS AS (CASE WHEN status='closed' AND entry_price IS NOT NULL AND exit_price IS NOT NULL THEN (exit_price - entry_price) * IF(direction='LONG',1,-1) * size * multiplier - commission END) STORED",
    "ALTER TABLE `{DB}`.trades ADD COLUMN IF NOT EXISTS risk_usd DECIMAL(36,10) GENERATED ALWAYS AS (CASE WHEN entry_price IS NOT NULL AND stop_loss IS NOT NULL THEN ABS(entry_price - stop_loss) * size * multiplier END) STORED",
    "ALTER TABLE `{DB}`.trades ADD COLUMN IF NOT EXISTS r_multiple DECIMAL(24,10) GENERATED ALWAYS AS (CASE WHEN status='closed' AND entry_price IS NOT NULL AND exit_price IS NOT NULL AND stop_loss IS NOT NULL AND entry_price <> stop_loss THEN (exit_price - entry_price) / (entry_price - stop_loss) END) STORED",
]

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
    statements = [x.strip() for x in SCHEMA.replace('{DB}', DB_NAME).split(';') if x.strip()]
    migrations = [m.replace('{DB}', DB_NAME) for m in MIGRATIONS]
    # Tablas primero, migraciones, y las vistas al final (dependen de columnas generadas)
    views = [x for x in statements if x.startswith('CREATE OR REPLACE VIEW')]
    base = [x for x in statements if x not in views]
    for stmt in base + migrations + views:
        cur.execute(stmt)
    conn.commit()
    print(f'   ✅ {len(statements) + len(migrations)} sentencias SQL ejecutadas')

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