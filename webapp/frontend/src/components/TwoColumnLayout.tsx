import ChatPanel from './ChatPanel'
import TabContainer from './TabContainer'

export default function TwoColumnLayout() {
  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Left: Chat Panel (fixed 300px) */}
      <div className="w-[300px] flex-shrink-0 border-r border-border-primary">
        <ChatPanel />
      </div>

      {/* Right: Tab Container (flexible) */}
      <div className="flex-1 overflow-hidden">
        <TabContainer />
      </div>
    </div>
  )
}
