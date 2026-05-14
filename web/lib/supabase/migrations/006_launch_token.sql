-- One-time launch links (?k= on /activate/[deviceId]): store hash only; cleared after successful activation.

ALTER TABLE devices
ADD COLUMN IF NOT EXISTS launch_token_hash TEXT,
ADD COLUMN IF NOT EXISTS launch_token_expires_at TIMESTAMPTZ;

COMMENT ON COLUMN devices.launch_token_hash IS 'SHA-256 hex of secret k in URL; single-use, cleared after launch';
COMMENT ON COLUMN devices.launch_token_expires_at IS 'When the launch link stops working';

CREATE INDEX IF NOT EXISTS idx_devices_launch_expires ON devices (launch_token_expires_at)
WHERE launch_token_hash IS NOT NULL;
