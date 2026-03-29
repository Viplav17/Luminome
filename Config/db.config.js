/**
 * MutationMap — database connection configuration.
 * Server-side only. Provides a shared PostgreSQL pool and Redis client.
 * Import as: const { pgPool, redis } = require('../Config/db.config');
 */

require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });

const { Pool } = require('pg');
const Redis = require('ioredis');

const pgPool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 10,
  idleTimeoutMillis: 30_000,
  connectionTimeoutMillis: 2_000,
});

pgPool.on('error', (err) => {
  console.error('[pgPool] Unexpected error:', err.message);
});

const redis = new Redis(process.env.REDIS_URL || 'redis://localhost:6379', {
  lazyConnect: true,
  enableOfflineQueue: false,
  // Retry 3 times with exponential back-off, then give up (don't block startup)
  retryStrategy: (times) => (times > 3 ? null : Math.min(times * 200, 1000)),
});

redis.on('error', (err) => {
  console.error('[Redis] Connection error:', err.message);
});

module.exports = { pgPool, redis };
