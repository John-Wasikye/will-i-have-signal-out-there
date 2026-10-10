import { Route, Routes } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { Home } from './pages/Home'
import { Lookup } from './pages/Lookup'
import { Status } from './pages/Status'

export default function App() {
  return (
    <>
      <NavBar />
      <main className="page">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/lookup" element={<Lookup />} />
          <Route path="/status" element={<Status />} />
          <Route path="*" element={<h1>Page not found</h1>} />
        </Routes>
      </main>
    </>
  )
}
