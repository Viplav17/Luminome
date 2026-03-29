const router = require('express').Router();
const { GoogleGenAI } = require('@google/genai');

const SYS = 'You are a genomics AI assistant. Given a natural language query about genes, diseases, or drug targets, return ONLY a valid JSON object with this exact structure: {"genes":["GENE1","GENE2"],"explanation":"One sentence describing why these genes match."}. Use standard HGNC gene symbols. Include up to 20 gene symbols. No markdown, no code blocks — only the JSON object.';

router.post('/query', async (req, res) => {
  const { query } = req.body;
  if (!query) return res.status(400).json({ error: 'query required' });

  const key = process.env.GEMINI_API_KEY;
  if (!key || key.trim() === '') {
    return res.status(503).json({ error: 'GEMINI_API_KEY not set — add it to your .env file.' });
  }

  try {
    const ai = new GoogleGenAI({ apiKey: key });
    const result = await ai.models.generateContent({
      model: 'gemini-2.0-flash',
      contents: [{ role: 'user', parts: [{ text: SYS + '\n\nQuery: ' + query }] }]
    });
    const raw = result.text.trim()
      .replace(/^```json\n?/, '').replace(/\n?```$/, '').trim();

    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      const m = raw.match(/\{[\s\S]*\}/);
      if (!m) throw new Error('Gemini returned unparseable response: ' + raw.slice(0, 120));
      parsed = JSON.parse(m[0]);
    }

    res.json({ genes: parsed.genes || [], explanation: parsed.explanation || '' });
  } catch (err) {
    const msg = err.message || String(err);
    console.error('[ai] Gemini error:', msg);
    if (msg.includes('429') || msg.includes('quota') || msg.includes('RESOURCE_EXHAUSTED'))
      return res.status(503).json({ error: 'Rate limit reached — wait a minute and try again.' });
    if (msg.includes('API_KEY') || msg.includes('401') || msg.includes('403') || msg.includes('API key'))
      return res.status(503).json({ error: 'Invalid Gemini API key — check your .env file.' });
    res.status(500).json({ error: msg });
  }
});

module.exports = router;
