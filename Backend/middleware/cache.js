const { redis } = require('../../Config/db.config');

async function get(k) {
  if (!redis) return null;
  try { const v = await redis.get(k); return v ? JSON.parse(v) : null; } catch { return null; }
}

async function set(k, v, ttl) {
  if (!redis) return;
  try { await redis.setex(k, ttl || 3600, JSON.stringify(v)); } catch {}
}

module.exports = { get, set };
