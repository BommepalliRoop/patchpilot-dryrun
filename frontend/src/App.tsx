import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Compliance from './pages/Compliance'
import FindingDetail from './pages/FindingDetail'
import Integrations from './pages/Integrations'
import Overview from './pages/Overview'
import ScanLive from './pages/ScanLive'
import Styleguide from './pages/Styleguide'

// Routes per docs/UI_SPEC.md. T11 builds the design system, T12–T14 fill the pages.
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="scans/:id" element={<ScanLive />} />
        <Route path="findings/:id" element={<FindingDetail />} />
        <Route path="integrations" element={<Integrations />} />
        <Route path="compliance" element={<Compliance />} />
        <Route path="styleguide" element={<Styleguide />} />
        <Route path="*" element={<Overview />} />
      </Route>
    </Routes>
  )
}
