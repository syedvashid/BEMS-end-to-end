// NotFoundPage.jsx
import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return <div className="card"><h1>Page not found</h1><p><Link to="/facilities">Go to Facilities</Link></p></div>
}