module.exports = (req, res, next) => {
  const k = process.env.INTERNAL_API_KEY;
  if (k && req.headers['x-api-key'] !== k) return res.status(401).json({ error: 'Unauthorized' });
  next();
};
