import TwoColumnLayout from './components/TwoColumnLayout'
import TopBar from './components/TopBar'
import GenomicNavBar from './components/GenomicNavBar'

export default function App() {
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
