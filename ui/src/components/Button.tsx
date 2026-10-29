import type { ComponentProps } from 'react';

type ButtonProps = ComponentProps<'button'> & {
  variant?: 'default' | 'primary' | 'secondary' | 'danger';
};

/** Presentation only: callers own actions, pending state, and accessible names. */
export function Button({ variant = 'default', className = '', type = 'button', ...props }: ButtonProps) {
  const classes = ['button', variant === 'default' ? '' : variant, className].filter(Boolean).join(' ');
  return <button {...props} type={type} className={classes} />;
}
