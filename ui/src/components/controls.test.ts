import { createElement, createRef } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { Button } from './Button';
import { Field } from './Field';

describe('shared native controls', () => {
  it('keeps native button props, refs and handlers while centralizing variant classes', () => {
    const ref = createRef<HTMLButtonElement>();
    const onClick = vi.fn();
    const button = Button({ variant: 'secondary', className: 'wide', disabled: true, ref, onClick, 'aria-label': 'Apply', children: 'Apply parameters' });
    expect(button.type).toBe('button');
    expect(button.props).toMatchObject({ type: 'button', className: 'button secondary wide', disabled: true, ref, onClick, 'aria-label': 'Apply' });
    expect(renderToStaticMarkup(button)).toContain('disabled=""');
    expect(onClick).not.toHaveBeenCalled();
  });

  it('allows explicit form semantics and does not add an empty variant class', () => {
    expect(Button({ type: 'submit', form: 'project', children: 'Save' }).props).toMatchObject({ type: 'submit', form: 'project', className: 'button' });
  });

  it('preserves label association, child state, and native label props', () => {
    const ref = createRef<HTMLLabelElement>();
    const child = createElement('input', { id: 'task-name', defaultValue: 'normalize', disabled: true });
    const field = Field({ label: 'Task name', htmlFor: 'task-name', className: 'extra', ref, children: child });
    expect(field.props).toMatchObject({ htmlFor: 'task-name', className: 'field extra', ref });
    const html = renderToStaticMarkup(field);
    expect(html).toContain('<label for="task-name" class="field extra"><span>Task name</span>');
    expect(html).toContain('id="task-name"');
    expect(html).toContain('value="normalize"');
    expect(html).toContain('disabled=""');
  });
});
