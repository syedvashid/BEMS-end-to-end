export default function Button({ variant = 'secondary', size, loading = false, disabled, type = 'button', className = '', children, ...rest }) {
  const cls = `btn btn-${variant} ${size === 'sm' ? 'btn-sm' : ''} ${className}`.trim()
  return (
    <button type={type} className={cls} disabled={disabled || loading} {...rest}>
      {loading ? 'Please wait…' : children}
    </button>
  )
}