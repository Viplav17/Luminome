var SEV_RANK = {critical:3, moderate:2, low:1};
var SEV_COL  = {critical:'#f87171', moderate:'#fb923c', low:'#fcd34d'};

var S = {
  view:         'genome',
  selChr:       null,
  selGene:      null,
  hovChr:       null,
  hovGene:      null,
  filter:       null,
  aiGenes:      [],
  genes:        [],
  tick:         0,
  mutSite:      null,
  selChromosome: null,
  uploadChrMap: {},
  sortMode:     'default',
};