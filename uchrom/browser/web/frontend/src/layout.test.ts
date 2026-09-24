import { describe, expect, it } from 'vitest'
import { groupTitle } from './components/FieldPicker'
import { useStore } from './store'

describe('colour groups', () => {
  it('names field groups for users', () => {
    expect(groupTitle('rna')).toBe('Gene')
    expect(groupTitle('cell')).toBe('Property')
    expect(groupTitle('if')).toBe('IF')
    expect(groupTitle('protein')).toBe('Protein')
  })
})

describe('embedding layout prefs', () => {
  it('switches layout and clamps the split fraction', () => {
    const st = useStore.getState()
    st.setUi({ embeddingLayout: 'split', splitFrac: 0.02 })
    expect(useStore.getState().ui).toMatchObject({ embeddingLayout: 'split', splitFrac: 0.15 })
    st.setUi({ splitFrac: 0.99 })
    expect(useStore.getState().ui.splitFrac).toBe(0.85)
    st.setUi({ embeddingLayout: 'tab', activeTab: 'embedding' })
    expect(useStore.getState().ui).toMatchObject({ embeddingLayout: 'tab', activeTab: 'embedding', splitFrac: 0.85 })
  })
})
