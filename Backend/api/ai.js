const router = require('express').Router();
const { GoogleGenerativeAI } = require('@google/generative-ai');

const SYS = 'You are a genomics AI assistant. Given a natural language query about genes, diseases, or drug targets, return ONLY a valid JSON object with this exact structure: {"genes":["GENE1","GENE2"],"explanation":"One sentence describing why these genes match."}. Use standard HGNC gene symbols. Include up to 20 gene symbols. No markdown, no code blocks — only the JSON object.';

router.post('/query', async (req, res) => {
  const { query } = req.body;
  if (!query) return res.status(400).json({ error: 'query required' });
  try {
    const ai    = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
    const model = ai.getGenerativeModel({ model: 'gemini-1.5-flash' });
    const result = await model.generateContent(SYS + '\n\nQuery: ' + query);
    const text   = result.response.text().trim()
      .replace(/^```json\n?/, '').replace(/\n?```$/, '');
    const parsed = JSON.parse(text);
    res.json({ genes: parsed.genes || [], explanation: parsed.explanation || '' });
  } catch (err) { res.status(500).json({ error: err.message }); }
});

module.exports = router;
