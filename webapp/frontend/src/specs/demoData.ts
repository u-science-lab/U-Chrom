export type DemoOptionId = 'uchrom-demo' | 'official-demo'

export const UCHROM_DEMO_DATA_PATH = 'example-data/rich_multicell.h5cd'

export const DEMO_OPTIONS: Array<{ id: DemoOptionId; label: string }> = [
  { id: 'uchrom-demo', label: 'U-Chrom Demo' },
  { id: 'official-demo', label: 'Official Demo' },
]
