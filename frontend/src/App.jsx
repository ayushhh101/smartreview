import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Planned from './pages/Planned.jsx'
import MLLab from './pages/MLLab.jsx'
import Products from './pages/Products.jsx'
import NLPExplorer from './pages/NLPExplorer.jsx'
import BDALab from './pages/BDALab.jsx'
import Streaming from './pages/Streaming.jsx'
import ProductDetail from './pages/ProductDetail.jsx'

const P = (title, subject, phase, text) => (
  <Planned title={title} subject={subject} phase={phase}><p>{text}</p></Planned>
)

export default function App() {
  return (
    <div className="flex">
      <Sidebar />
      <main className="flex-1 min-w-0 p-8 max-w-[1400px]">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/products" element={<Products />} />
          <Route path="/products/:id" element={<ProductDetail />} />
          <Route path="/reviews" element={P('Reviews', 'NLP', 6, 'Browse and search reviews with TF-IDF cosine similarity.')} />
          <Route path="/nlp" element={<NLPExplorer />} />
          <Route path="/ml" element={<MLLab />} />
          <Route path="/bda" element={<BDALab />} />
          <Route path="/streaming" element={<Streaming />} />
          <Route path="/recommendations" element={P('Recommendations', 'BDA', 6, 'Content-based similar-product recommendations.')} />
          <Route path="/ask" element={P('Ask SmartReview', 'NLP + BDA', 6, 'Questions answered from database statistics, no LLM.')} />
          <Route path="/mapping" element={P('Academic Mapping', 'All', 7, 'Concept, subject, where used, purpose.')} />
          <Route path="/about" element={P('About', 'All', 7, 'Scope, limitations and the educational-simulation disclosures.')} />
        </Routes>
      </main>
    </div>
  )
}
