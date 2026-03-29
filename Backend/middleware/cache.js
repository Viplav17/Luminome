const { redis } = require('../../Config/db.config');

async function get(k) {
  try { const v = await redis.get(k); return v ? JSON.parse(v) : null; } catch { return null; }
}

async function set(k, v, ttl) {
  try { await redis.setex(k, ttl || 3600, JSON.stringify(v)); } catch {}
}

module.exports = { get, set };
