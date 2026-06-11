/**
 * Default Gosling spec for local contact map (chr21).
 * Uses our HiGlass-compatible tileset API at /api/tileset_info.
 */

export const LOCAL_CONTACT_MAP_SPEC = {
  assembly: [['chr21', 46709983]], // chr21 length for hg38
  spacing: 0,
  style: { outlineWidth: 0 },
  views: [
    {
      layout: 'linear',
      xDomain: { chromosome: 'chr21', interval: [0, 46709983] },
      tracks: [
        {
          id: 'contact-heatmap',
          title: 'Contact Map (chr21)',
          data: {
            type: 'matrix',
            url: `${window.location.origin}/api/tileset_info?d=contact-chr21`,
            server: window.location.origin,
            tilesetUid: 'contact-chr21',
          },
          mark: 'rect',
          x: { field: 'start', type: 'genomic', axis: 'top' },
          xe: { field: 'end', type: 'genomic' },
          color: {
            field: 'value',
            type: 'quantitative',
            range: 'warm',
            legend: true,
          },
          width: 800,
          height: 400,
        },
        {
          // TAD boundaries overlaid on the heatmap
          id: 'tad-boundaries',
          alignment: 'overlay',
          title: 'TAD Boundaries',
          data: {
            type: 'json',
            url: `${window.location.origin}/api/tads/chr21?format=gosling`,
            genomicFields: [
              { index: 'start', name: 'start' },
              { index: 'end', name: 'end' },
            ],
            chromosomeField: 'chrom',
          },
          dataTransform: [
            // Create boundary positions (start and end of each TAD)
            { type: 'filter', field: 'start', oneOf: ['!', null] },
          ],
          mark: 'rule',
          x: { field: 'start', type: 'genomic' },
          strokeWidth: { value: 2 },
          stroke: { value: '#ff1493' },
          opacity: { value: 0.7 },
          style: { linePattern: { type: 'triangleRight', size: 5 } },
          width: 800,
          height: 400,
        },
        {
          // Right boundaries (end positions)
          id: 'tad-boundaries-end',
          alignment: 'overlay',
          data: {
            type: 'json',
            url: `${window.location.origin}/api/tads/chr21?format=gosling`,
            genomicFields: [
              { index: 'end', name: 'end' },
            ],
            chromosomeField: 'chrom',
          },
          mark: 'rule',
          x: { field: 'end', type: 'genomic' },
          strokeWidth: { value: 2 },
          stroke: { value: '#ff1493' },
          opacity: { value: 0.7 },
          width: 800,
          height: 400,
        },
        {
          // Axis track below the heatmap
          id: 'axis',
          alignment: 'overlay',
          data: {
            type: 'csv',
            url: 'https://raw.githubusercontent.com/sehilyi/gemini-datasets/master/data/cytogenetic_band.csv',
            chromosomeField: 'Chr.',
            genomicFields: ['ISCN_start', 'ISCN_stop', 'Basepair_start', 'Basepair_stop'],
            quantitativeFields: ['Band', 'Density'],
          },
          mark: 'rect',
          dataTransform: [{ type: 'filter', field: 'Chr.', oneOf: ['chr21'] }],
          x: {
            field: 'Basepair_start',
            type: 'genomic',
            domain: { chromosome: 'chr21', interval: [0, 46709983] },
            axis: 'top',
          },
          xe: { field: 'Basepair_stop', type: 'genomic' },
          color: {
            field: 'Density',
            type: 'nominal',
            domain: ['', '25', '50', '75', '100'],
            range: ['white', '#D9D9D9', '#979797', '#636363', 'black'],
          },
          width: 800,
          height: 30,
        },
      ],
    },
  ],
}
