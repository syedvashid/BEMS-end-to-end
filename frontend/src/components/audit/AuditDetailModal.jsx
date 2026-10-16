import { Button, Modal } from '../ui'
import { FetchError, fmtStamp, useFetch } from '../reports/shared.jsx'

const show = (v) => (v === undefined ? '' : typeof v === 'string' ? v : JSON.stringify(v, null, 1))
const isObj = (v) => v && typeof v === 'object' && !Array.isArray(v)

export default function AuditDetailModal({ id, onClose }) {
  const res = useFetch(`/audit-logs/${id}/`) // reading a detail is itself audited (AUDIT_LOG_VIEWED)
  const d = res.data
  const prev = isObj(d?.previous_value) ? d.previous_value : null
  const next = isObj(d?.new_value) ? d.new_value : null
  const keys = [...new Set([...Object.keys(prev || {}), ...Object.keys(next || {})])].sort()
  const changed = new Set(d?.changed_fields || [])

  return (
    <Modal wide title={`Audit event #${id}`} onClose={onClose} footer={<Button onClick={onClose}>Close</Button>}>
      <FetchError error={res.error} />
      {res.loading && !d && <p className="rp-note">Loading…</p>}
      {d && (
        <>
          <p className="rp-note">
            {fmtStamp(d.occurred_at)} · {d.actor_username || 'system'} · <strong>{d.action}</strong> · {d.entity_type || '—'} {d.entity_public_id || ''}
            <br />{d.http_method} {d.request_path} · request {d.request_id || '—'}
          </p>
          {d.changed_fields?.length > 0 && <p><strong>Changed fields:</strong> {d.changed_fields.join(', ')}</p>}
          {(prev || next) ? (
            <div className="rp-scroll">
              <table className="rp-diff">
                <thead><tr><th style={{ width: '22%' }}>Field</th><th>Previous</th><th>New</th></tr></thead>
                <tbody>
                  {keys.map((k) => {
                    const differs = changed.has(k) || JSON.stringify(prev?.[k]) !== JSON.stringify(next?.[k])
                    return (
                      <tr key={k} className={differs ? 'changed' : ''}>
                        <th>{k}</th>
                        <td className="prev"><pre>{show(prev?.[k])}</pre></td>
                        <td className="next"><pre>{show(next?.[k])}</pre></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <>
              <h3>Previous value</h3><pre className="json">{JSON.stringify(d.previous_value, null, 2) ?? '—'}</pre>
              <h3>New value</h3><pre className="json">{JSON.stringify(d.new_value, null, 2) ?? '—'}</pre>
            </>
          )}
        </>
      )}
    </Modal>
  )
}
