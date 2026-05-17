import { useState } from 'react'

interface FigurePreviewProps {
  preview: string  // base64
  path: string
  format: string
  params?: any
}

export default function FigurePreview({ preview, path, format, params }: FigurePreviewProps) {
  const [expanded, setExpanded] = useState(false)

  function downloadPDF() {
    // Request backend to serve the file
    const filename = path.split('/').pop() || 'figure.pdf'
    const link = document.createElement('a')
    link.href = `/api/download?path=${encodeURIComponent(path)}`
    link.download = filename
    link.click()
  }

  function downloadPNG() {
    // Download the preview as PNG
    const link = document.createElement('a')
    link.href = `data:image/png;base64,${preview}`
    link.download = path.replace('.pdf', '.png').split('/').pop() || 'figure.png'
    link.click()
  }

  function downloadParams() {
    // Download parameters as JSON
    const json = JSON.stringify(params, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = path.replace('.pdf', '_params.json').split('/').pop() || 'params.json'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{
      background: '#313244',
      borderRadius: 8,
      padding: 8,
      marginTop: 6,
      maxWidth: '90%',
    }}>
      {/* Preview image */}
      <div style={{
        position: 'relative',
        cursor: 'pointer',
        borderRadius: 6,
        overflow: 'hidden',
        background: '#1e1e2e',
      }}
        onClick={() => setExpanded(!expanded)}
      >
        <img
          src={`data:image/png;base64,${preview}`}
          alt="Figure preview"
          style={{
            width: '100%',
            display: 'block',
            maxHeight: expanded ? 'none' : 200,
            objectFit: expanded ? 'contain' : 'cover',
          }}
        />
        {!expanded && (
          <div style={{
            position: 'absolute',
            bottom: 4,
            right: 4,
            background: 'rgba(0,0,0,0.7)',
            color: '#cdd6f4',
            padding: '2px 6px',
            borderRadius: 4,
            fontSize: 10,
          }}>
            Click to expand
          </div>
        )}
      </div>

      {/* Download buttons */}
      <div style={{
        display: 'flex',
        gap: 6,
        marginTop: 6,
        flexWrap: 'wrap',
      }}>
        <button
          onClick={downloadPDF}
          style={{
            background: '#f38ba8',
            border: 'none',
            borderRadius: 4,
            padding: '4px 8px',
            color: '#1e1e2e',
            fontSize: 11,
            cursor: 'pointer',
            fontWeight: 500,
          }}
        >
          📄 PDF
        </button>
        <button
          onClick={downloadPNG}
          style={{
            background: '#a6e3a1',
            border: 'none',
            borderRadius: 4,
            padding: '4px 8px',
            color: '#1e1e2e',
            fontSize: 11,
            cursor: 'pointer',
            fontWeight: 500,
          }}
        >
          🖼️ PNG
        </button>
        {params && (
          <button
            onClick={downloadParams}
            style={{
              background: '#89b4fa',
              border: 'none',
              borderRadius: 4,
              padding: '4px 8px',
              color: '#1e1e2e',
              fontSize: 11,
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            ⚙️ Params
          </button>
        )}
      </div>

      {/* Metadata */}
      <div style={{
        marginTop: 6,
        fontSize: 10,
        color: '#a6adc8',
      }}>
        Format: {format.toUpperCase()} • Style: {params?.style || 'default'}
      </div>
    </div>
  )
}
