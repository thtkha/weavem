import type { ComponentProps, ReactNode } from 'react';

type FieldProps = ComponentProps<'label'> & { label: ReactNode };

/** Retains native label/control association without owning the input's state. */
export function Field({ label, className = '', children, ...props }: FieldProps) {
  return (
    <label {...props} className={['field', className].filter(Boolean).join(' ')}>
      <span>{label}</span>
      {children}
    </label>
  );
}
