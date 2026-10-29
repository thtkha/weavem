import { describe, expect, it } from 'vitest';
import { DEFAULT_LAYOUT, EDITOR_LAYOUT_STORAGE_KEY, constrainedLayout, loadEditorLayout, saveEditorLayout } from './layout';

function storage(raw: string | null = null): Pick<Storage, 'getItem' | 'setItem'> {
  let value = raw;
  return {
    getItem: () => value,
    setItem: (_key, next) => { value = next; },
  };
}

describe('editor layout preferences', () => {
  it('keeps panel widths within their bounds and leaves a usable canvas', () => {
    expect(constrainedLayout({ libraryWidth: 900, inspectorWidth: 900 }, 1100)).toEqual({ libraryWidth: 220, inspectorWidth: 434 });
    expect(constrainedLayout({ libraryWidth: 10, inspectorWidth: 10 })).toEqual({ libraryWidth: 220, inspectorWidth: 260 });
  });

  it('only restores a valid versioned preference', () => {
    expect(loadEditorLayout(storage(JSON.stringify({ version: 1, libraryWidth: 333, inspectorWidth: 444 })))).toEqual({ libraryWidth: 333, inspectorWidth: 444 });
    expect(loadEditorLayout(storage('{bad json'))).toEqual(DEFAULT_LAYOUT);
    expect(loadEditorLayout(storage(JSON.stringify({ version: 2, libraryWidth: 333, inspectorWidth: 444 })))).toEqual(DEFAULT_LAYOUT);
  });

  it('writes a separate versioned preference without touching drafts', () => {
    const target = storage();
    saveEditorLayout(target, { libraryWidth: 333, inspectorWidth: 444 });
    expect(JSON.parse(target.getItem(EDITOR_LAYOUT_STORAGE_KEY)!)).toEqual({ version: 1, libraryWidth: 333, inspectorWidth: 444 });
  });
});
