const WIDTH = 760
const SIGNAL_HEIGHT = 48
const MATRIX_HEIGHT = 300

const SIGNAL_DOMAIN = { chromosome: 'chr7', interval: [77700000, 81000000] }

const BIGWIG_BASE = {
  type: 'bigwig',
  column: 'position',
  value: 'peak',
  binSize: 8,
}

const GENE_DATA = {
  type: 'beddb',
  url: 'https://server.gosling-lang.org/api/v1/tileset_info/?d=gene-annotation',
  genomicFields: [
    { index: 1, name: 'start' },
    { index: 2, name: 'end' },
  ],
  valueFields: [
    { index: 5, name: 'strand', type: 'nominal' },
    { index: 3, name: 'name', type: 'nominal' },
  ],
}

const EPILOGOS_CATEGORIES = [
  'Active TSS',
  'Flanking Active TSS',
  "Transcr at gene 5' and 3'",
  'Strong transcription',
  'Weak transcription',
  'Genic enhancers',
  'Enhancers',
  'ZNF genes & repeats',
  'Heterochromatin',
  'Bivalent/Poised TSS',
  'Flanking Bivalent TSS/Enh',
  'Bivalent Enhancer',
  'Repressed PolyComb',
  'Weak Repressed PolyComb',
  'Quiescent/Low',
]

function signalTrack(id: string, title: string, url: string, color: string, axis: 'top' | 'none' = 'none') {
  return {
    id,
    title,
    data: { ...BIGWIG_BASE, url },
    mark: 'bar',
    x: axis === 'top'
      ? { field: 'start', type: 'genomic', axis }
      : { field: 'start', type: 'genomic' },
    xe: { field: 'end', type: 'genomic' },
    y: { field: 'peak', type: 'quantitative', axis: 'none' },
    color: { value: color },
    width: WIDTH,
    height: SIGNAL_HEIGHT,
  }
}

function geneTrack(id: string, title: string, strand: '+' | '-', mark: 'triangleRight' | 'triangleLeft', color: string) {
  return {
    id,
    title,
    data: GENE_DATA,
    dataTransform: [{ type: 'filter', field: 'strand', oneOf: [strand] }],
    mark,
    x: { field: 'start', type: 'genomic' },
    xe: { field: 'end', type: 'genomic' },
    size: { value: 11 },
    stroke: { value: 'white' },
    strokeWidth: { value: 1 },
    color: { value: color },
    width: WIDTH,
    height: 28,
  }
}

function matrixTrack(id: string, title: string, tileset: string) {
  return {
    id,
    title,
    data: {
      type: 'matrix',
      url: `https://server.gosling-lang.org/api/v1/tileset_info/?d=${tileset}`,
    },
    mark: 'bar',
    x: { field: 'xs', type: 'genomic' },
    xe: { field: 'xe', type: 'genomic' },
    y: { field: 'ys', type: 'genomic' },
    ye: { field: 'ye', type: 'genomic' },
    color: {
      field: 'value',
      type: 'quantitative',
      range: 'warm',
      legend: true,
    },
    width: WIDTH,
    height: MATRIX_HEIGHT,
  }
}

export const OFFICIAL_DEMO_SPEC = {
  assembly: 'hg38',
  title: 'Official Gosling Demo',
  subtitle: 'HFFc6 Micro-C / Hi-C with signal, gene, and epilogos tracks',
  layout: 'linear',
  spacing: 2,
  xDomain: SIGNAL_DOMAIN,
  views: [
    {
      layout: 'linear',
      xDomain: SIGNAL_DOMAIN,
      tracks: [
        signalTrack(
          'official-h3k4me3',
          'HFFc6 H3K4me3',
          'https://s3.amazonaws.com/gosling-lang.org/data/HFFc6_H3K4me3.bigWig',
          'darkgreen',
          'top',
        ),
        signalTrack(
          'official-atac',
          'HFFc6 ATAC',
          'https://s3.amazonaws.com/gosling-lang.org/data/HFFc6_Atacseq.mRp.clN.bigWig',
          '#E79F00',
        ),
        signalTrack(
          'official-ctcf',
          'HFFc6 CTCF',
          'https://s3.amazonaws.com/gosling-lang.org/data/HFFC6_CTCF.mRp.clN.bigWig',
          '#0072B2',
        ),
        geneTrack('official-genes-plus', 'Genes (+ strand)', '+', 'triangleRight', '#CB7AA7'),
        geneTrack('official-genes-minus', 'Genes (- strand)', '-', 'triangleLeft', '#029F73'),
        matrixTrack('official-microc', 'HFFc6 Micro-C', 'hffc6-microc-hg38'),
        matrixTrack('official-hic', 'HFFc6 Hi-C', 'hffc6-hic-hg38'),
        {
          id: 'official-epilogos',
          title: 'Epilogos (hg38)',
          data: {
            type: 'multivec',
            url: 'https://server.gosling-lang.org/api/v1/tileset_info/?d=epilogos-hg38',
            row: 'category',
            column: 'position',
            value: 'value',
            categories: EPILOGOS_CATEGORIES,
            binSize: 8,
          },
          dataTransform: [{ type: 'filter', field: 'value', inRange: [0, 999999] }],
          mark: 'bar',
          x: { field: 'start', type: 'genomic' },
          xe: { field: 'end', type: 'genomic' },
          y: { field: 'value', type: 'quantitative', axis: 'none' },
          color: {
            field: 'category',
            type: 'nominal',
            range: [
              '#FF0000',
              '#FF4500',
              '#32CD32',
              '#008000',
              '#006400',
              '#C2E105',
              '#FFFF00',
              '#66CDAA',
              '#8A91D0',
              '#CD5C5C',
              '#E9967A',
              '#BDB76B',
              '#808080',
              '#C0C0C0',
              'gray',
            ],
          },
          width: WIDTH,
          height: SIGNAL_HEIGHT,
        },
      ],
    },
  ],
}
