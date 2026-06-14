import { useEffect } from 'react'
import TwoColumnLayout from './components/TwoColumnLayout'
import TopBar from './components/TopBar'
import GenomicNavBar from './components/GenomicNavBar'
import { installSnapshotOrchestrator } from './snapshot'

export default function App() {
  // Wire the capture_view_snapshot orchestrator (listens for request_snapshot,
  // switches tab + captures the target panel's canvas, replies snapshot_result).
  useEffect(() => installSnapshotOrchestrator(), [])

  return (
    <div className="h-screen flex flex-col bg-bg-primary">
      <TopBar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <TwoColumnLayout />
      </div>
      <GenomicNavBar />
    </div>
  )
}
