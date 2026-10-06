import { Children, isValidElement, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Popover } from './Popover'

/** One entry of a Select: an <option> of the children (group = the <optgroup> label). */
export interface SelectItem {
  value: string
  label: ReactNode
  text: string
  disabled: boolean
  title?: string
  group: string | null
}

const textOf = (n: ReactNode): string => {
  if (n === null || n === undefined || typeof n === 'boolean') return ''
  if (typeof n === 'string' || typeof n === 'number') return String(n)
  if (Array.isArray(n)) return n.map(textOf).join('')
  if (isValidElement<{ children?: ReactNode }>(n)) return textOf(n.props.children)
  return ''
}

/**
 * The <option> / <optgroup> children of a Select as a flat list (fragments
 * and arrays flattened), like a native <select> reads them.  Pure — tested.
 */
export function selectItems(children: ReactNode, group: string | null = null): SelectItem[] {
  const out: SelectItem[] = []
  Children.forEach(children, (c) => {
    if (!isValidElement<Record<string, unknown>>(c)) return
    const p = c.props
    if (c.type === 'optgroup') out.push(...selectItems(p.children as ReactNode, String(p.label ?? '')))
    else if (c.type === 'option') {
      const text = textOf(p.children as ReactNode)
      out.push({
        value: p.value !== undefined ? String(p.value) : text,
        label: p.children as ReactNode,
        text,
        disabled: !!p.disabled,
        title: typeof p.title === 'string' ? p.title : undefined,
        group,
      })
    } else out.push(...selectItems(p.children as ReactNode, group)) // fragments
  })
  return out
}

/** Items whose text (or group) contains every word of `query`, case-insensitive. */
export function filterItems(items: SelectItem[], query: string): SelectItem[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return items
  return items.filter((it) => {
    const t = `${it.text} ${it.group ?? ''} ${it.value}`.toLowerCase()
    return words.every((w) => t.includes(w))
  })
}

/** Lists this long get a search box. */
export const SEARCH_MIN = 12

/**
 * Drop-in for a native <select>: the same <option> / <optgroup> children and
 * `onChange(e)` with `e.target.value`, drawn in the app's style — a button
 * with the chosen label and a caret, and a themed menu (current entry
 * checked, groups as headings, a search box for long lists).  Keyboard: ↑/↓
 * (or Space / Enter) open, ↑/↓ move, Enter picks, Esc closes, typing jumps
 * to (or, with the search box, filters) entries.
 */
export function Select({
  value,
  onChange,
  children,
  className = '',
  title,
  disabled = false,
  style,
  placeholder = '—',
  'aria-label': ariaLabel,
}: {
  value: string | number | undefined | null
  onChange(e: { target: { value: string } }): void
  children: ReactNode
  className?: string
  title?: string
  disabled?: boolean
  style?: React.CSSProperties
  placeholder?: string
  'aria-label'?: string
}) {
  const items = useMemo(() => selectItems(children), [children])
  const current = value === undefined || value === null ? null : String(value)
  const chosen = items.find((it) => it.value === current) ?? null
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(-1)
  const btn = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const typed = useRef<{ s: string; t: number }>({ s: '', t: 0 })
  const searchable = items.length >= SEARCH_MIN
  const shown = useMemo(() => (searchable ? filterItems(items, query) : items), [items, query, searchable])
  const close = useCallback(() => {
    setOpen(false)
    setQuery('')
  }, [])
  const pick = (it: SelectItem) => {
    if (it.disabled) return
    close()
    btn.current?.focus()
    if (it.value !== current) onChange({ target: { value: it.value } })
  }
  // opening: highlight the current entry and bring it into view
  useEffect(() => {
    if (!open) return
    setActive(Math.max(0, shown.findIndex((it) => it.value === current)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
  useEffect(() => {
    if (open && query) setActive(shown.findIndex((it) => !it.disabled))
  }, [query, open, shown])
  useEffect(() => {
    if (!open || active < 0) return
    list.current?.querySelector<HTMLElement>(`[data-i="${active}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [active, open])
  const step = (d: number) => {
    if (!shown.length) return
    let i = active
    for (let k = 0; k < shown.length; k++) {
      i = (i + d + shown.length) % shown.length
      if (!shown[i].disabled) break
    }
    setActive(i)
  }
  const onKey = (e: React.KeyboardEvent) => {
    if (disabled) return
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        setOpen(true)
      } else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey) {
        // closed: type to select the next entry starting with the typed text (native behaviour)
        const now = Date.now()
        const s = (now - typed.current.t < 700 ? typed.current.s : '') + e.key.toLowerCase()
        typed.current = { s, t: now }
        const hit = items.find((it) => !it.disabled && it.text.toLowerCase().startsWith(s))
        if (hit && hit.value !== current) onChange({ target: { value: hit.value } })
      }
      return
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      step(e.key === 'ArrowDown' ? 1 : -1)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (shown[active]) pick(shown[active])
    } else if (e.key === 'Tab') close()
  }
  let lastGroup: string | null = null
  return (
    <>
      <button
        ref={btn}
        type="button"
        className={`select${open ? ' open' : ''}${className ? ` ${className}` : ''}`}
        style={style}
        title={title ?? chosen?.title}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => (open ? close() : setOpen(true))}
        onKeyDown={onKey}
      >
        <span className="select-label">{chosen ? chosen.label : <span className="muted">{placeholder}</span>}</span>
        <svg className="select-caret" viewBox="0 0 10 6" width="9" height="6" aria-hidden>
          <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <Popover anchor={btn} open={open} onClose={close} className="menu-popup select-popup">
        <div className="select-menu" style={{ minWidth: btn.current?.offsetWidth }} onKeyDown={onKey}>
          {searchable && (
            <input
              className="select-search"
              autoFocus
              placeholder={`search ${items.length} entries…`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          )}
          <ul ref={list} role="listbox">
            {shown.map((it, i) => {
              const head = it.group !== lastGroup && it.group !== null ? it.group : null
              lastGroup = it.group
              return (
                <li key={`${it.group ?? ''}\u0000${it.value}`} className="select-li">
                  {head !== null && <div className="select-group">{head}</div>}
                  <div
                    role="option"
                    aria-selected={it.value === current}
                    aria-disabled={it.disabled || undefined}
                    data-i={i}
                    title={it.title}
                    className={`select-item${it.value === current ? ' current' : ''}${i === active ? ' active' : ''}${it.disabled ? ' disabled' : ''}${it.group !== null ? ' grouped' : ''}`}
                    onMouseEnter={() => setActive(i)}
                    onClick={() => pick(it)}
                  >
                    <span className="select-check" aria-hidden>
                      {it.value === current ? '✓' : ''}
                    </span>
                    <span className="select-text">{it.label}</span>
                  </div>
                </li>
              )
            })}
            {!shown.length && <li className="select-empty muted">no match</li>}
          </ul>
        </div>
      </Popover>
    </>
  )
}
