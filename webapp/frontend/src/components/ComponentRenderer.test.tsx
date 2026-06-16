import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve(__dirname, 'ComponentRenderer.tsx'), 'utf8')

describe('ComponentRenderer actions', () => {
  it('emits structured component_action ui_events for controls', () => {
    expect(source).toContain("event_name: 'component_action'")
    expect(source).toContain('action_id')
    expect(source).toContain("component: 'Button'")
    expect(source).toContain("emitComponentAction('Slider'")
    expect(source).toContain("emitComponentAction('Select'")
    expect(source).toContain("ws.send('ui_event'")
  })

  it('renders accessibility labels for interactive controls', () => {
    expect(source).toContain('aria-label')
    expect(source).toContain('aria_label')
    expect(source).toContain('disabled={Boolean(props.disabled)}')
  })
})
