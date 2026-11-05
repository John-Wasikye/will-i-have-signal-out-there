import { Route, Routes } from 'react-router-dom'
import { DevelopmentBanner } from './components/DevelopmentBanner'
import { NavBar } from './components/NavBar'
import { About } from './pages/About'
import { Lookup } from './pages/Lookup'
import { Status } from './pages/Status'
import { Trails } from './pages/Trails'

export default function App() {
  return (
    <>
      <DevelopmentBanner />
      <NavBar />
      <main className="page">
        <Routes>
          <Route path="/" element={<Trails />} />
          <Route path="/trails" element={<Trails />} />
          <Route path="/about" element={<About />} />
          <Route path="/lookup" element={<Lookup />} />
          <Route path="/status" element={<Status />} />
          <Route path="*" element={<h1>Page not found</h1>} />
        </Routes>
      </main>
    </>
  )
}
