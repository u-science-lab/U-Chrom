import { describe, expect, it } from 'vitest'
import { esc, num, paint, serialize, svgDocument } from './svg'
import { parseFont, SvgContext2D, type ImageEncoder } from './svgctx'
import { teeContext } from './vectorcapture'
import { cssGradient, captureFilename, pdfText } from './capture'

const enc: ImageEncoder = { imageData: (d) => `data:image/png;base64,${d.width}x${d.height}`, source: () => 'data:image/png;base64,src' }
const ctx = (dpr = 1) => new SvgContext2D(dpr, enc)
const svg = (c: SvgContext2D) => serialize(c.elements)

describe('svg helpers', () => {
  it('formats numbers with at most 2 decimals', () => {
    expect(num(1.23456)).toBe('1.23')
    expect(num(-0.001)).toBe('0')
    expect(num(NaN)).toBe('0')
  })
  it('escapes markup', () => {
    expect(esc(`a<b & "c"`)).toBe('a&lt;b &amp; &quot;c&quot;')
  })
  it('splits colours into an opaque colour and an opacity', () => {
    expect(paint('rgba(255, 0, 10, 0.5)')).toEqual({ color: '#ff000a', opacity: 0.5 })
    expect(paint('rgb(1,2,3)', 0.5)).toEqual({ color: '#010203', opacity: 0.5 })
    expect(paint('#abc')).toEqual({ color: '#aabbcc', opacity: 1 })
    expect(paint('#11223380').opacity).toBeCloseTo(0.502, 3)
    expect(paint('transparent').color).toBe('none')
    expect(paint('steelblue')).toEqual({ color: 'steelblue', opacity: 1 })
  })
  it('groups runs of elements with the same style', () => {
    const els = [0, 1, 2].map((i) => ({ tag: 'circle', geom: `cx="${i}" cy="0" r="1"`, style: { fill: '#ff0000' } }))
    const out = serialize([...els, { tag: 'rect', geom: 'x="0" y="0" width="1" height="1"', style: { fill: '#00ff00' } }])
    expect(out).toBe(
      '<g fill="#ff0000">\n<circle cx="0" cy="0" r="1"/>\n<circle cx="1" cy="0" r="1"/>\n<circle cx="2" cy="0" r="1"/>\n</g>\n<rect x="0" y="0" width="1" height="1" fill="#00ff00"/>',
    )
  })
  it('writes a standalone document', () => {
    const doc = svgDocument(100, 50, '<rect/>', { title: 'a & b', desc: 'note' })
    expect(doc).toContain('viewBox="0 0 100 50"')
    expect(doc).toContain('<title>a &amp; b</title>')
    expect(doc).toContain('xmlns="http://www.w3.org/2000/svg"')
  })
})

describe('SvgContext2D', () => {
  it('divides the device-pixel transform out (CSS pixels)', () => {
    const c = ctx(2)
    c.setTransform(2, 0, 0, 2, 0, 0)
    c.fillStyle = '#ff0000'
    c.fillRect(10, 20, 30, 40)
    expect(svg(c)).toBe('<rect x="10" y="20" width="30" height="40" fill="#ff0000"/>')
  })
  it('a full arc is a circle; fill + stroke of the same path is one element', () => {
    const c = ctx()
    c.fillStyle = 'rgba(0, 0, 255, 0.5)'
    c.strokeStyle = '#000000'
    c.lineWidth = 0.5
    c.globalAlpha = 0.5
    c.beginPath()
    c.arc(5, 6, 3, 0, 2 * Math.PI)
    c.fill()
    c.stroke()
    expect(svg(c)).toBe('<circle cx="5" cy="6" r="3" fill="#0000ff" fill-opacity="0.25" stroke="#000000" stroke-opacity="0.5" stroke-width="0.5"/>')
  })
  it('records polylines, dashes and closed paths', () => {
    const c = ctx()
    c.strokeStyle = '#123456'
    c.setLineDash([5, 4])
    c.beginPath()
    c.moveTo(0, 0)
    c.lineTo(10, 0)
    c.lineTo(10, 10)
    c.closePath()
    c.stroke()
    expect(svg(c)).toBe('<path d="M0 0L10 0L10 10Z" fill="none" stroke="#123456" stroke-width="1" stroke-dasharray="5 4"/>')
  })
  it('partial arcs become SVG arc commands', () => {
    const c = ctx()
    c.beginPath()
    c.arc(0, 0, 10, 0, Math.PI / 2)
    c.stroke()
    expect(svg(c)).toBe('<path d="M10 0A10 10 0 0 1 0 10" fill="none" stroke="#000000" stroke-width="1"/>')
  })
  it('keeps text as text, with the baseline and alignment of the canvas', () => {
    const c = ctx()
    c.font = 'bold 11px -apple-system, "Segoe UI", sans-serif'
    c.fillStyle = '#333333'
    c.textAlign = 'center'
    c.textBaseline = 'middle'
    c.fillText('chr1 <x>', 50, 20)
    expect(svg(c)).toBe(
      '<text x="50" y="23.85" fill="#333333" font-family="-apple-system, &quot;Segoe UI&quot;, sans-serif" font-size="11" font-weight="bold" text-anchor="middle">chr1 &lt;x&gt;</text>',
    )
  })
  it('rotated text keeps the transform', () => {
    const c = ctx()
    c.translate(10, 50)
    c.rotate(-Math.PI / 2)
    c.fillText('y', 0, 0)
    expect(svg(c)).toMatch(/<text x="0" y="0" transform="matrix\(0 -1 1 0 10 50\)"/)
  })
  it('save / restore and globalAlpha', () => {
    const c = ctx()
    c.save()
    c.globalAlpha = 0.5
    c.translate(5, 5)
    c.restore()
    c.fillRect(0, 0, 1, 1)
    expect(svg(c)).toBe('<rect x="0" y="0" width="1" height="1" fill="#000000"/>')
  })
  it('putImageData is placed in CSS pixels, ignoring the transform', () => {
    const c = ctx(2)
    c.setTransform(2, 0, 0, 2, 0, 0)
    c.putImageData({ width: 200, height: 100, data: new Uint8ClampedArray(0), colorSpace: 'srgb' } as ImageData, 0, 0)
    expect(svg(c)).toContain('<image x="0" y="0" width="100" height="50"')
    expect(svg(c)).toContain('data:image/png;base64,200x100')
  })
  it('square dots: a strokeRect over the same fillRect joins it', () => {
    const c = ctx()
    c.fillStyle = '#ff0000'
    c.strokeStyle = '#000000'
    c.fillRect(0, 0, 2, 2)
    c.strokeRect(0, 0, 2, 2)
    expect(svg(c)).toBe('<rect x="0" y="0" width="2" height="2" fill="#ff0000" stroke="#000000" stroke-width="1"/>')
  })
  it('parses canvas fonts', () => {
    expect(parseFont('11px -apple-system, sans-serif')).toEqual({ style: 'normal', weight: 'normal', size: 11, family: '-apple-system, sans-serif' })
    expect(parseFont('italic 600 12.5px Arial')).toEqual({ style: 'italic', weight: '600', size: 12.5, family: 'Arial' })
  })
})

describe('tee context', () => {
  it('draws on the canvas and records the same calls; unknown drawing calls are reported', () => {
    const calls: string[] = []
    const target = {
      fillStyle: '#000000',
      fillRect: (...a: number[]) => calls.push(`fillRect ${a.join(',')}`),
      measureText: (t: string) => ({ width: t.length * 7 }),
      createLinearGradient: () => ({}),
    } as unknown as CanvasRenderingContext2D
    const rec = ctx()
    const g = teeContext(target, rec)
    g.fillStyle = '#00ff00'
    g.fillRect(1, 2, 3, 4)
    expect(g.measureText('abc').width).toBe(21)
    g.createLinearGradient(0, 0, 1, 1)
    expect(calls).toEqual(['fillRect 1,2,3,4'])
    expect(target.fillStyle).toBe('#00ff00')
    expect(svg(rec)).toBe('<rect x="1" y="2" width="3" height="4" fill="#00ff00"/>')
    expect([...rec.unsupported]).toEqual(['createLinearGradient'])
  })
})

describe('CSS gradients', () => {
  it('become SVG linear gradients', () => {
    expect(cssGradient('linear-gradient(to right, rgb(255, 0, 0), rgba(0, 0, 255, 0.5) 100%)', 'g')).toBe(
      '<linearGradient id="g" x1="0" y1="0.5" x2="1" y2="0.5"><stop offset="0" stop-color="#ff0000"/><stop offset="1" stop-color="#0000ff" stop-opacity="0.5"/></linearGradient>',
    )
    expect(cssGradient('linear-gradient(rgb(0, 0, 0), rgb(255, 255, 255))', 'v')).toContain('x1="0.5" y1="0" x2="0.5" y2="1"')
    expect(cssGradient('none', 'n')).toBeNull()
  })
})

describe('capture filenames by format', () => {
  const date = new Date(2026, 8, 24, 15, 30, 7)
  it('end in the format', () => {
    expect(captureFilename({ dataset: 'd', type: '3d', date, ext: 'svg' })).toBe('uchrom_d_3d_all_20260924-153007.svg')
    expect(captureFilename({ dataset: 'd', type: 'stats', date, ext: 'pdf' })).toBe('uchrom_d_stats_all_20260924-153007.pdf')
    expect(captureFilename({ dataset: 'd', type: 'stats', date })).toBe('uchrom_d_stats_all_20260924-153007.png')
  })
})

describe('PDF text', () => {
  it('spells common symbols with Latin-1', () => {
    expect(pdfText('≥6.52k · -1.88 … 1.88 – x')).toBe('>=6.52k · -1.88 ... 1.88 - x')
  })
})
