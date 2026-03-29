const router = require('express').Router();
const axios = require('axios');

const SYS = 'You are a genomics AI assistant. Given a natural language query about genes, diseases, or drug targets, return ONLY a valid JSON object with this exact structure: {"genes":["GENE1","GENE2"],"explanation":"One sentence describing why these genes match."}. Use standard HGNC gene symbols. Prioritize genes with strong real-world evidence in current clinical/literature context. If a candidate gene list is provided, only return genes from that list. Include up to 25 gene symbols. No markdown, no code blocks — only the JSON object.';

function parseModelJson(rawText) {
  const raw = String(rawText || '').trim().replace(/^```json\n?/, '').replace(/\n?```$/, '').trim();
  try {
    return JSON.parse(raw);
  } catch {
    const m = raw.match(/\{[\s\S]*\}/);
    if (!m) throw new Error('Model returned unparseable response: ' + raw.slice(0, 140));
    return JSON.parse(m[0]);
  }
}

function normalizeResponse(parsed, geneUniverse) {
  const allowed = new Set((geneUniverse || []).map(g => String(g || '').trim().toUpperCase()).filter(Boolean));
  const genes = Array.isArray(parsed && parsed.genes) ? parsed.genes : [];
  const out = [];
  genes.forEach(function(g) {
    const s = String(g || '').trim().toUpperCase();
    if (!s) return;
    if (allowed.size && !allowed.has(s)) return;
    if (out.indexOf(s) >= 0) return;
    out.push(s);
  });
  return {
    genes: out.slice(0, 25),
    explanation: String((parsed && parsed.explanation) || '').trim(),
  };
}

async function callPersonalAI(query, geneUniverse) {
  const url = process.env.PERSONAL_AI_URL;
  if (!url) throw new Error('PERSONAL_AI_URL not set');
  const headers = { 'Content-Type': 'application/json' };
  if (process.env.PERSONAL_AI_KEY) headers.Authorization = 'Bearer ' + process.env.PERSONAL_AI_KEY;
  const res = await axios.post(url, {
    query: query,
    gene_universe: geneUniverse || [],
    instructions: SYS,
  }, { timeout: 20000, headers: headers });
  return normalizeResponse(res.data || {}, geneUniverse);
}

let _genAI = null;
async function getGenAI() {
  if (_genAI) return _genAI;
  const { GoogleGenAI } = await import('@google/genai');
  _genAI = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
  return _genAI;
}

async function callGemini(query, geneUniverse) {
  const key = process.env.GEMINI_API_KEY;
  if (!key || key.trim() === '') throw new Error('GEMINI_API_KEY not set');
  const universeLine = (geneUniverse && geneUniverse.length)
    ? ('\nAllowed genes: ' + geneUniverse.join(', '))
    : '';
  const prompt = SYS + universeLine + '\n\nQuery: ' + query;
  const ai = await getGenAI();
  const models = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-flash-latest'];
  let lastErr;
  for (const modelName of models) {
    try {
      const result = await ai.models.generateContent({
        model: modelName,
        contents: prompt,
      });
      const text = result.text || '';
      if (!text.trim()) throw new Error('Empty model response');
      return normalizeResponse(parseModelJson(text), geneUniverse);
    } catch (e) {
      lastErr = e;
      console.warn('[ai] model', modelName, 'failed:', e.message?.slice(0, 120));
    }
  }
  throw lastErr || new Error('Gemini request failed');
}

router.post('/query', async (req, res) => {
  const { query, geneUniverse } = req.body;
  if (!query) return res.status(400).json({ error: 'query required' });

  const universe = Array.isArray(geneUniverse) ? geneUniverse : [];

  try {
    try {
      // Primary: user's personal model endpoint.
      const out = await callPersonalAI(query, universe);
      return res.json(out);
    } catch (personalErr) {
      console.warn('[ai] Personal model failed, falling back to Gemini:', personalErr.message || String(personalErr));
    }

    const out = await callGemini(query, universe);
    res.json(out);
  } catch (err) {
    const msg = err.message || String(err);
    console.error('[ai] model error:', msg);
    if (msg.includes('429') || msg.includes('quota') || msg.includes('RESOURCE_EXHAUSTED'))
      return res.status(503).json({ error: 'Rate limit reached — wait a minute and try again.' });
    if (msg.includes('API_KEY') || msg.includes('401') || msg.includes('403') || msg.includes('API key'))
      return res.status(503).json({ error: 'Invalid Gemini API key — check your .env file.' });
    res.status(500).json({ error: msg });
  }
});

module.exports = router;
