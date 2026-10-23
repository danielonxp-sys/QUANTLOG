-- ============================================
-- QUANTLOG 1.0 - Schema para MariaDB (arquitectura CQRS)
-- pnl_gross, pnl_net, risk_usd, r_multiple: GENERATED ALWAYS ... STORED
-- Generado desde backend/setup_db.py
-- ============================================

CREATE DATABASE IF NOT EXISTS `quantlog_v1` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `quantlog_v1`;

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
