import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useFacility } from '../../context/FacilityContext'
import { Button, useToast } from '../ui'
import CondemnationRequestModal from './CondemnationRequestModal'

// For a verification item resolved as CONFIRMED_MISSING: opens the condemnation request pre-filled as LOST_MISSING.
// Props: item = { public_id, resolution, equipment: { public_id, asset_tag, name } }
export default function WriteOffAction({ item }) {
  const { can } = useFacility()
  const navigate = useNavigate()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  if (!item || item.resolution !== 'CONFIRMED_MISSING' || !can('condemnation.add') || !item.equipment) return null
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>Start write-off</Button>
      {open && (
        <CondemnationRequestModal equipment={item.equipment}
          initial={{ reason_category: 'LOST_MISSING', source_verification_item: item.public_id }}
          onClose={() => setOpen(false)}
          onDone={(r) => { setOpen(false); toast.success(`Request ${r.request_number} created.`); navigate(`/condemnation/${r.public_id}`) }} />
      )}
    </>
  )
}
