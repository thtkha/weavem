import { useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Button } from './Button';

const sample = { customer: { name: 'Alex', email: 'alex@example.test' } };

/** Isolated design demonstration: it never reads or changes an authored flow. */
export function MotionLab() {
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [mapped, setMapped] = useState(false);
  const [enhanced, setEnhanced] = useState(false);

  const show = () => {
    setEnhanced(typeof document.startViewTransition === 'function' && !matchMedia('(prefers-reduced-motion: reduce)').matches);
    dialog.current?.showModal();
  };
  const toggle = () => {
    const update = () => flushSync(() => setMapped((current) => !current));
    if (typeof document.startViewTransition === 'function' && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      // Only the illustrative value changes; the editor never acquires a motion loop.
      void document.startViewTransition(update).finished.catch(() => undefined);
    } else update();
  };

  return <>
    <Button className="motion-lab-trigger" ref={trigger} onClick={show} aria-haspopup="dialog">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M3 12h4l3-7 4 14 3-7h4" /></svg>
      Motion lab
    </Button>
    <dialog ref={dialog} className="motion-lab" aria-labelledby="motion-lab-title" onClose={() => trigger.current?.focus()} onKeyDown={(event) => event.stopPropagation()}>
      <header className="motion-lab-header"><div><h2 id="motion-lab-title">See a field become an input</h2><p>Illustrative design experiment · no tasks execute.</p></div><Button aria-label="Close motion lab" onClick={() => dialog.current?.close()}>Close</Button></header>
      <p className="motion-lab-intro">A connection can carry a whole result or one nested value. This sample makes that change visible without changing your flow.</p>
      <div className="motion-lab-stage" data-mapped={mapped}>
        <section className="motion-lab-source" aria-label="Illustrative upstream result"><h3>Upstream result</h3><pre>{JSON.stringify(sample, null, 2)}</pre><code className="motion-lab-path">{mapped ? '["customer", "email"]' : '[]'}</code></section>
        <svg className="motion-lab-wire" viewBox="0 0 80 48" fill="none" aria-hidden="true"><path d="M0 24h68m-8-8 8 8-8 8" stroke="currentColor" strokeWidth="2" /></svg>
        <section className="motion-lab-target" aria-label="Illustrative downstream input"><h3>Target input</h3><pre className="motion-lab-value" aria-label="Illustrative target value">{mapped ? JSON.stringify(sample.customer.email) : JSON.stringify(sample, null, 2)}</pre></section>
      </div>
      <footer className="motion-lab-footer"><Button variant="primary" onClick={toggle}>{mapped ? 'Use whole result' : 'Map email field'}</Button><p role="status">{mapped ? 'customer.email becomes the target input.' : 'Whole result becomes the target input.'}</p><span className="motion-lab-support">{enhanced ? 'Native View Transition' : 'Static transition'}</span></footer>
    </dialog>
  </>;
}
