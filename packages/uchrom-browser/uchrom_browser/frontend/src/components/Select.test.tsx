import { describe, expect, it } from 'vitest'
import { filterItems, selectItems } from './Select'

describe('Select', () => {
  it('reads <option> / <optgroup> children like a native select', () => {
    const items = selectItems(
      <>
        <option value="overview">same as overview</option>
        <optgroup label="RNA">
          {['umap', 'pca'].map((k) => (
            <option key={k} value={`rna_${k}`} title={k}>
              RNA · {k}
            </option>
          ))}
        </optgroup>
        <option disabled>no value</option>
        {false && <option value="x">hidden</option>}
      </>,
    )
    expect(items.map((i) => [i.value, i.text, i.group, i.disabled])).toEqual([
      ['overview', 'same as overview', null, false],
      ['rna_umap', 'RNA · umap', 'RNA', false],
      ['rna_pca', 'RNA · pca', 'RNA', false],
      ['no value', 'no value', null, true],
    ])
    expect(items[1].title).toBe('umap')
  })
  it('filters by every word, in text, group or value', () => {
    const items = selectItems(
      <>
        <optgroup label="Hi-C">
          <option value="hic_umap.E13_HiC_R1">E13_HiC_R1 · umap</option>
        </optgroup>
        <option value="chr1">chr1</option>
        <option value="chr10">chr10</option>
      </>,
    )
    expect(filterItems(items, 'chr1').map((i) => i.value)).toEqual(['chr1', 'chr10'])
    expect(filterItems(items, 'hi-c umap').map((i) => i.value)).toEqual(['hic_umap.E13_HiC_R1'])
    expect(filterItems(items, '  ')).toHaveLength(3)
  })
})
