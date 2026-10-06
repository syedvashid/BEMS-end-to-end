export default function FormField({ label, name, error, hint, required, as = 'input', options = [], children, className = '', ...rest }) {
  const id = `f-${name}`
  let control = children
  if (!control) {
    if (as === 'select') {
      control = (
        <select id={id} name={name} {...rest}>
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      )
    } else if (as === 'textarea') {
      control = <textarea id={id} name={name} rows={3} {...rest} />
    } else {
      control = <input id={id} name={name} {...rest} />
    }
  }
  return (
    <div className={`field ${error ? 'field-error' : ''} ${className}`.trim()}>
      <label htmlFor={id}>{label}{required && <span aria-hidden="true"> *</span>}</label>
      {control}
      {hint && !error && <small className="hint">{hint}</small>}
      {error && <small className="error-text" role="alert">{error}</small>}
    </div>
  )
}

// Standard-shape error banner (also explains stale_version).
export function FormError({ error }) {
  if (!error) return null
  const extra = error.code === 'stale_version' ? ' Close this dialog and reopen the record to get the latest version.' : ''
  return <div className="alert alert-danger" role="alert">{error.message}{extra}</div>
}