import { Route, Routes } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { ScrollOnNavigate } from './components/ScrollOnNavigate'
import { SiteFooter } from './components/SiteFooter'
import { About } from './pages/About'
import { Lookup } from './pages/Lookup'
import { NotFound } from './pages/NotFound'
import { Status } from './pages/Status'
import { Trails } from './pages/Trails'

export default function App() {
  return (
    <>
      <ScrollOnNavigate />
      <NavBar />
      <main className="page">
        <Routes>
          <Route path="/" element={<Trails />} />
          <Route path="/trails" element={<Trails />} />
          <Route path="/about" element={<About />} />
          <Route path="/lookup" element={<Lookup />} />
          <Route path="/status" element={<Status />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <SiteFooter />
    </>
  )
}
