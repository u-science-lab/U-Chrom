import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// StrictMode is intentionally disabled: Gosling 1.x renders through HiGlass,
// which uses legacy class components and a PixiJS WebGL context whose
// mount/unmount is not idempotent. StrictMode's deliberate double-invoke of
// mount in development tears down and rebuilds that context out from under
// Gosling, crashing the renderer. Re-enable only if Gosling/HiGlass drops the
// legacy lifecycle dependency.
createRoot(document.getElementById('root')!).render(
  <App />,
)
