const STEPS = ['Upload', 'Review', 'Export'] as const

export function Stepper({ at }: { at: 1 | 2 | 3 }) {
  return (
    <ol className="stepper" aria-label="Progress">
      {STEPS.map((label, i) => {
        const n = i + 1
        const state = n < at ? 'done' : n === at ? 'now' : ''
        return (
          <li key={label} className={`step ${state}`} style={{ listStyle: 'none', display: 'contents' }}>
            {i > 0 && <span className="step-line" aria-hidden />}
            <span className={`step ${state}`} aria-current={n === at ? 'step' : undefined}>
              <i>{n < at ? '✓' : n}</i>
              {label}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
