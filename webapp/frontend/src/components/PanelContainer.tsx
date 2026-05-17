import React from 'react'

interface Props {
  title: string
  children?: React.ReactNode
  onClose?: () => void
}

const actions = [
  { icon: '⛶', label: '全屏' },
  { icon: '📋', label: '复制' },
  { icon: '✎', label: '样式' },
  { icon: '✦', label: '出图' },
  { icon: '💬', label: '描述' },
]

export default function PanelContainer({ title, children, onClose }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', border: '1px solid #313244' }}>
      <div style={{ display: 'flex', alignItems: 'center', background: '#181825', padding: '0 8px', height: 32, flexShrink: 0, gap: 4 }}>
        <span style={{ flex: 1, fontSize: 12, color: '#cdd6f4' }}>{title}</span>
        {actions.map((a) => (
          <button key={a.label} title={a.label} style={btnStyle}>{a.icon}</button>
        ))}
        <button title="关闭" style={btnStyle} onClick={onClose}>✕</button>
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>{children}</div>
    </div>
  )
}

const btnStyle: React.CSSProperties = {
  background: 'none', border: 'none', cursor: 'pointer', color: '#a6adc8', fontSize: 13, padding: '0 3px',
}
