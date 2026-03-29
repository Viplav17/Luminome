/**
 * MutationMap — database connection configuration.
 * Server-side only. Provides a shared PostgreSQL pool and Redis client.
 * Import as: const { pgPool, redis } = require('../Config/db.config');
 */

require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });

let pgPool = null;
try {
  const { Pool } = require('pg');
  pgPool = new Pool({
    connectionString: process.env.DATABASE_URL,
    max: 10,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 2_000,
  });
  pgPool.on('error', (err) => console.error('[pgPool] Unexpected error:', err.message));
} catch (e) {
  console.warn('[pgPool] PostgreSQL not available — running without DB:', e.message);
}

let redis = null;
try {
  const Redis = require('ioredis');
  redis = new Redis(process.env.REDIS_URL || 'redis://localhost:6379', {
    lazyConnect: true,
    enableOfflineQueue: false,
    retryStrategy: (times) => (times > 3 ? null : Math.min(times * 200, 1000)),
  });
  redis.on('error', (err) => console.error('[Redis] Connection error:', err.message));
} catch (e) {
  console.warn('[Redis] Redis not available — running without cache:', e.message);
}

module.exports = { pgPool, redis };
