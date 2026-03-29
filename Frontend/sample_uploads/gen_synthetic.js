'use strict';
const fs   = require('fs');
const path = require('path');

const CHR_LEN_MB = {
  '1':249,'2':242,'3':198,'4':190,'5':181,'6':171,'7':159,'8':145,
  '9':138,'10':133,'11':135,'12':133,'13':114,'14':107,'15':102,'16':90,
  '17':83,'18':80,'19':59,'20':63,'21':47,'22':51,'X':155,'Y':59
};

// Full gene panel — all genes the lab "tested", but only a small fraction
// will have any reportable variant (the rest are tested-normal).
const GENE_DB = [
  ['1','TP73',3600000,'ts'],['1','MUTYH',45700000,'ts'],['1','NRAS',114700000,'onco'],
  ['1','LMNA',156100000,'ts'],['1','ABL2',179100000,'onco'],['1','CDC73',93500000,'ts'],
  ['1','PTPN22',114300000,'other'],['1','RUNX3',25200000,'ts'],['1','MDM4',204500000,'onco'],
  ['1','PARP1',226400000,'ts'],
  ['2','MSH2',47600000,'ts'],['2','MSH6',48000000,'ts'],['2','EPCAM',47400000,'ts'],
  ['2','ALK',29400000,'onco'],['2','MYCN',15900000,'onco'],['2','RAD51B',142500000,'ts'],
  ['2','BARD1',214800000,'ts'],['2','DNMT3A',25500000,'ts'],['2','NRXN1',51000000,'other'],
  ['3','VHL',10100000,'ts'],['3','MLH1',37000000,'ts'],['3','PIK3CA',179200000,'onco'],
  ['3','CTNNB1',41200000,'onco'],['3','RASSF1',50000000,'ts'],['3','ROBO1',79600000,'ts'],
  ['3','FHIT',60800000,'ts'],['3','RBMS3',30000000,'ts'],
  ['4','PDGFRA',55100000,'onco'],['4','KIT',55500000,'onco'],['4','FBXW7',153200000,'ts'],
  ['4','TET2',106000000,'ts'],['4','FIP1L1',38300000,'onco'],['4','WHSC1',1900000,'onco'],
  ['4','FANCA',89000000,'ts'],['4','RHOH',133500000,'ts'],
  ['5','APC',112200000,'ts'],['5','MCC',112800000,'ts'],['5','MSH3',79900000,'ts'],
  ['5','TERT',1300000,'onco'],['5','RAD50',131900000,'ts'],['5','PRDM9',23500000,'other'],
  ['5','PDGFRB',150100000,'onco'],['5','CSF1R',150500000,'onco'],
  ['6','HLA-A',29900000,'other'],['6','HLA-B',31300000,'other'],['6','TNFAIP3',138200000,'ts'],
  ['6','TCF21',161700000,'ts'],['6','ING3',33900000,'ts'],['6','CDKN1A',36700000,'ts'],
  ['6','PRDM1',106300000,'ts'],['6','EP300',41000000,'ts'],
  ['7','BRAF',140453136,'onco'],['7','EGFR',55200000,'onco'],['7','MET',116300000,'onco'],
  ['7','EZH2',148500000,'onco'],['7','CREB3L2',137500000,'ts'],['7','POT1',124400000,'ts'],
  ['7','SMO',128800000,'onco'],['7','CDK6',92200000,'onco'],
  ['8','MYC',128700000,'onco'],['8','EXT1',119000000,'ts'],['8','FGFR1',38400000,'onco'],
  ['8','PLAG1',57100000,'onco'],['8','RB1CC1',52600000,'ts'],['8','ANKRD26',37000000,'ts'],
  ['8','RUNX1T1',93500000,'onco'],
  ['9','CDKN2A',21971101,'ts'],['9','CDKN2B',22000000,'ts'],['9','TSC1',87900000,'ts'],
  ['9','ABL1',130800000,'onco'],['9','PTCH1',98200000,'ts'],['9','XPA',100500000,'other'],
  ['9','BRIP1',97000000,'ts'],['9','FANCC',98000000,'ts'],
  ['10','PTEN',89700000,'ts'],['10','RET',43600000,'onco'],['10','CDH23',73400000,'other'],
  ['10','BMPR1A',88600000,'ts'],['10','SUFU',104300000,'ts'],['10','FGFR2',123200000,'onco'],
  ['11','ATM',108236168,'ts'],['11','WT1',32400000,'ts'],['11','MEN1',64600000,'ts'],
  ['11','HRAS',533200,'onco'],['11','RNF43',87100000,'ts'],['11','CBL',119100000,'ts'],
  ['11','KMT2A',118300000,'onco'],['11','BIRC3',102200000,'ts'],
  ['12','KRAS',25245350,'onco'],['12','ETV6',12000000,'ts'],['12','CDKN1B',12800000,'ts'],
  ['12','GLI3',102100000,'ts'],['12','PAH',102800000,'other'],['12','SLX4',21700000,'ts'],
  ['12','PTPN11',112900000,'onco'],
  ['13','RB1',47800000,'ts'],['13','BRCA2',32356432,'ts'],['13','DCLRE1C',108800000,'ts'],
  ['13','GPC5',93400000,'ts'],['13','LATS2',21700000,'ts'],['13','CDX2',28500000,'ts'],
  ['14','CTCF',100800000,'ts'],['14','TRAF3',99800000,'ts'],['14','FANCM',45300000,'ts'],
  ['14','CHD8',21300000,'other'],['14','AKT1',105240000,'onco'],['14','DICER1',95600000,'ts'],
  ['15','BLM',90800000,'ts'],['15','FBN1',48400000,'other'],['15','MAN2B1',78400000,'other'],
  ['15','RECQL3',89400000,'ts'],['15','IDH2',90600000,'onco'],['15','CASC15',25900000,'ts'],
  ['16','CDH1',68800000,'ts'],['16','TSC2',2100000,'ts'],['16','CBFB',67100000,'ts'],
  ['16','CREBBP',3800000,'ts'],['16','PALB2',23600000,'ts'],
  ['17','TP53',7578221,'ts'],['17','BRCA1',43044295,'ts'],['17','NF1',31100000,'ts'],
  ['17','ERBB2',37900000,'onco'],['17','RAD51C',40500000,'ts'],['17','CHEK1',27100000,'ts'],
  ['17','MAP2K4',12000000,'ts'],['17','PIK3R1',42000000,'ts'],
  ['18','SMAD4',48600000,'ts'],['18','DCC',18300000,'ts'],['18','CCBE1',57500000,'other'],
  ['18','SMAD2',47800000,'ts'],['18','CABLES1',20500000,'ts'],
  ['19','STK11',1200000,'ts'],['19','NOTCH3',15200000,'other'],['19','KMT2B',36200000,'ts'],
  ['19','JAK3',17900000,'onco'],['19','CEBPA',33700000,'ts'],
  ['20','JAG1',10600000,'other'],['20','GATA5',61000000,'ts'],['20','SRC',36000000,'onco'],
  ['20','RUNX1T1',30700000,'onco'],['20','BCL2L1',31700000,'onco'],['20','PTPRT',40200000,'ts'],
  ['21','APP',27300000,'other'],['21','ERG',38400000,'onco'],['21','ETS2',39800000,'onco'],
  ['21','RUNX1',34900000,'ts'],['21','CLDN8',34200000,'other'],
  ['22','NF2',30000000,'ts'],['22','CHEK2',29100000,'ts'],['22','BCR',23200000,'onco'],
  ['22','EWSR1',29300000,'onco'],['22','SMARCB1',24100000,'ts'],['22','LZTR1',40700000,'ts'],
  ['X','FMR1',147912051,'other'],['X','DMD',31137654,'other'],['X','AR',67545000,'onco'],
  ['X','MECP2',154031289,'ts'],['X','KDM6A',44600000,'ts'],['X','BCOR',39800000,'ts'],
  ['X','GATA1',48600000,'ts'],['X','PHF8',54800000,'other'],
  ['Y','SRY',2787392,'other'],['Y','TSPY1',5688134,'other'],
  ['Y','RBMY1A1',24000000,'other'],['Y','DAZ1',24300000,'other'],
];

// ── Real clinical findings (1-2 per patient — most people carry 0-2) ──
const FEMALE_PATHOGENIC = {
  'BRCA1': [{v:'c.5266dupC', p:'p.Gln1756ProfsTer25', sev:'critical', zyg:'heterozygous'}],
};
const MALE_PATHOGENIC = {
  'MSH2': [{v:'c.942+3A>T', p:'p.?', sev:'critical', zyg:'heterozygous'}],
};

// Genes that commonly carry benign polymorphisms in any person
// (only these ~25 genes will show variant rows — the rest are tested-normal)
const BENIGN_GENE_POOL_INDICES_FEMALE = [
  0, 6, 27, 28, 40, 41, 54, 55, 61, 68, 73, 76, 80, 86, 89, 93, 97,
  100, 105, 110, 118, 121, 125, 128, 131,
];
const BENIGN_GENE_POOL_INDICES_MALE = [
  1, 8, 18, 25, 30, 37, 43, 50, 56, 63, 69, 74, 78, 82, 88, 92, 96,
  101, 107, 112, 119, 123, 127, 130, 134,
];

const BENIGN_TEMPLATES = [
  (base, n) => `c.${base + n * 23}A>G`,
  (base, n) => `c.${base + n * 17}T>C`,
  (base, n) => `c.${base + n * 31}G>A`,
  (base, n) => `c.${base + n * 13}C>T`,
  (base, n) => `c.*${37 + n * 3}G>A`,
  (base, n) => `c.${base + n * 7}-14T>C`,
  (base, n) => `c.${base + n * 11}+52A>G`,
];
const BENIGN_PROTEIN = [
  () => 'p.=', () => 'p.=', () => 'p.=',
  (n) => 'p.Ala' + (50 + n * 7 % 800) + 'Ala',
  (n) => 'p.Leu' + (30 + n * 11 % 900) + 'Leu',
  (n) => 'p.Ser' + (80 + n * 3 % 700) + 'Ser',
];

const VUS_TEMPLATES = [
  (base, n) => `c.${base + n * 29}G>C`,
  (base, n) => `c.${base + n * 37}A>C`,
  (base, n) => `c.${base + n * 19}T>A`,
];
const VUS_PROTEIN = [
  (n) => 'p.Arg' + (100 + n * 9 % 500) + 'Gln',
  (n) => 'p.Glu' + (200 + n * 7 % 400) + 'Lys',
  (n) => 'p.Asp' + (60 + n * 11 % 600) + 'Asn',
];

function extraFields(idx, depthBase, qualBase) {
  const depth = depthBase + (idx * 17 + 3) % 80;
  const qual  = Math.min(99, qualBase + (idx * 13) % 40);
  const tx    = 'NM_' + String(100000 + idx % 50000).padStart(6, '0') + '.' + (3 + idx % 4);
  const ref   = ['A','C','G','T'][idx % 4];
  const alt   = ['A','C','G','T'][(idx + 2) % 4];
  const af    = idx % 25 === 0 ? (1e-5).toExponential(2)
              : idx % 8  === 0 ? (1e-3).toExponential(2)
              : (0.05 + (idx * 7 % 45) / 100).toFixed(4);
  return { depth, qual, tx, ref, alt, af };
}

function buildRows(sex, pathogenic, benignPoolIndices) {
  const rows = [];
  let idx = 0;

  const allGenes = GENE_DB.filter(([chr]) => !(sex === 'female' && chr === 'Y'));

  // Pick the subset of genes that will carry benign polymorphisms
  const benignGenes = benignPoolIndices
    .filter(i => i < allGenes.length)
    .map(i => allGenes[i]);

  // 1) Pathogenic variants — the actual clinical findings (1 per patient)
  for (const [geneId, vars] of Object.entries(pathogenic)) {
    const entry = GENE_DB.find(([, g]) => g === geneId);
    if (!entry) continue;
    const [chr, gene, pos] = entry;
    for (const pv of vars) {
      const ex = extraFields(idx, 45, 60);
      rows.push({ chr, gene, variant: pv.v, sev: pv.sev, zyg: pv.zyg,
        pos: pos + idx * 50, sex, protein: pv.p, ...ex });
      idx++;
    }
  }

  // 2) VUS — 3-4 total across 3-4 genes (realistic for a panel test)
  const vusCount = 3 + Math.floor(Math.random() * 2);
  const vusIndices = new Set();
  while (vusIndices.size < Math.min(vusCount, allGenes.length)) {
    const candidate = Math.floor(Math.random() * allGenes.length);
    if (!pathogenic[allGenes[candidate][1]]) vusIndices.add(candidate);
  }
  for (const gi of vusIndices) {
    const [chr, gene, pos] = allGenes[gi];
    const ti = idx % VUS_TEMPLATES.length;
    const baseCode = Math.floor(pos / 1000) % 3000 + 100;
    const ex = extraFields(idx, 35, 45);
    rows.push({ chr, gene,
      variant: VUS_TEMPLATES[ti](baseCode, 0),
      sev: 'moderate', zyg: 'heterozygous',
      pos: pos + 200, sex,
      protein: VUS_PROTEIN[ti](idx), ...ex });
    idx++;
  }

  // 3) Benign / likely-benign — ~1550 rows, but only on ~25 genes
  //    Each gene averages ~60 benign variant rows (different positions in same gene).
  //    This is realistic: a large gene like BRCA2 can have 50+ benign SNPs reported.
  const target = 1550 + Math.floor(Math.random() * 50);
  while (rows.length < target) {
    const gi = rows.length % benignGenes.length;
    const [chr, gene, pos] = benignGenes[gi];
    const variantNum = Math.floor(rows.length / benignGenes.length);
    const ti = (idx + variantNum) % BENIGN_TEMPLATES.length;
    const baseCode = Math.floor(pos / 1000) % 4000 + 50;
    const ex = extraFields(idx, 28, 38);
    const cls = Math.random() < 0.55 ? 'likely_benign' : 'low';
    rows.push({ chr, gene,
      variant: BENIGN_TEMPLATES[ti](baseCode, variantNum),
      sev: cls,
      zyg: idx % 6 === 0 ? 'homozygous' : 'heterozygous',
      pos: pos + variantNum * 300 + (idx % 50) * 7, sex,
      protein: BENIGN_PROTEIN[ti % BENIGN_PROTEIN.length](idx), ...ex });
    idx++;
  }

  return rows;
}

function toCsv(rows) {
  return rows.map(r =>
    [r.chr, r.gene, r.variant, r.sev, r.zyg, r.pos, r.sex,
     r.depth, r.qual, r.tx, r.protein, r.ref, r.alt, r.af].join(',')
  ).join('\n');
}

function toTsv(rows) {
  return rows.map(r =>
    [r.chr, r.gene, r.variant, r.sev, r.zyg, r.pos, r.sex,
     r.depth, r.qual, r.tx, r.protein, r.ref, r.alt, r.af].join('\t')
  ).join('\n');
}

const HDR = 'chromosome,gene,variant,severity,zygosity,position,sex,read_depth,quality,transcript,protein_change,ref_allele,alt_allele,gnomad_af';

const maleRows = buildRows('male', MALE_PATHOGENIC, BENIGN_GENE_POOL_INDICES_MALE);
const malePath = path.join(__dirname, 'synthetic_male_dna_report.csv');
fs.writeFileSync(malePath, HDR + '\n' + toCsv(maleRows), 'utf8');
const mc = maleRows.filter(r => r.sev === 'critical').length;
const mm = maleRows.filter(r => r.sev === 'moderate').length;
const mGenes = new Set(maleRows.map(r => r.gene)).size;
console.log(`Male CSV:   ${maleRows.length} rows  (${mc} pathogenic, ${mm} VUS, ${maleRows.length - mc - mm} benign)  ${mGenes} unique genes  -> ${malePath}`);

const femaleRows = buildRows('female', FEMALE_PATHOGENIC, BENIGN_GENE_POOL_INDICES_FEMALE);
const femalePath = path.join(__dirname, 'synthetic_female_dna_report.tsv');
fs.writeFileSync(femalePath, HDR.replace(/,/g, '\t') + '\n' + toTsv(femaleRows), 'utf8');
const fc = femaleRows.filter(r => r.sev === 'critical').length;
const fm = femaleRows.filter(r => r.sev === 'moderate').length;
const fGenes = new Set(femaleRows.map(r => r.gene)).size;
console.log(`Female TSV: ${femaleRows.length} rows  (${fc} pathogenic, ${fm} VUS, ${femaleRows.length - fc - fm} benign)  ${fGenes} unique genes  -> ${femalePath}`);
