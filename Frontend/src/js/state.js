var SEV_RANK = {critical:3, moderate:2, low:1};
var SEV_COL  = {critical:'#f87171', moderate:'#fb923c', low:'#fcd34d'};

var S = {
  view:         'genome',
  selChr:       null,
  selGene:      null,
  hovChr:       null,
  hovGene:      null,
  filter:       null,
  hlDisease:    [],
  hlDrug:       [],
  aiGenes:      [],
  genes:        [],
  tick:         0,
  mutSite:      null,
  selMutation:  null,
  selChromosome: null,
  uploadChrMap: {},
  uploadSex:    null,
  sortMode:     'default',
  detailZoom:   1,
  dnaZoom:      1,
};