require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });
const express = require('express');
const cors    = require('cors');
const path    = require('path');

const app = express();
app.use(cors({ origin: '*' }));
app.use(express.json({ limit: '1mb' }));
app.use(require('./middleware/rateLimit'));

app.use(express.static(path.join(__dirname, '../Frontend')));
app.get('/Config/api.config.js', (req, res) =>
  res.sendFile(path.resolve(__dirname, '../Config/api.config.js'))
);

app.use('/api/genes',    require('./api/genes'));
app.use('/api/diseases', require('./api/diseases'));
app.use('/api/drugs',    require('./api/drugs'));
app.use('/api/trials',   require('./api/trials'));
app.use('/api/ai',       require('./api/ai'));

app.get('*', (req, res) =>
  res.sendFile(path.resolve(__dirname, '../Frontend/index.html'))
);

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => console.log(`MutationMap → http://localhost:${PORT}`));
