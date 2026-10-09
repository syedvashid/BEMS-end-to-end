import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useFacility } from '../context/FacilityContext'

const CODE_RE = /^[A-Za-z0-9_-]{1,100}$/

export default function ScanBox() {
  const { can } = useFacility()
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [msg, setMsg] = useState('')
  if (!can('equipment.view')) return null

  const flash = (m) => { setMsg(m); setTimeout(() => setMsg(''), 3000) }
  const go = async () => {
    const c = code.trim()
    if (!c) return
    if (!CODE_RE.test(c)) { flash('Not found'); return }
    try {
      const { data } = await api.get(`/equipment/scan/${encodeURIComponent(c)}/`)
      setCode('')
      navigate(`/equipment/${data.public_id}`)
    } catch (e) {
      flash(e?.response?.status === 404 ? 'Not found' : 'Scan failed')
    }
  }

  return (
    <span className="eq-scan">
      <input aria-label="Scan or type equipment code" placeholder="Scan / type code" value={code}
        onChange={(e) => setCode(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') go() }} maxLength={100} />
      {msg && <span className="muted">{msg}</span>}
    </span>
  )
}
