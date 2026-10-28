export const EDITOR_LAYOUT_STORAGE_KEY = 'weavem.editor.layout.v1';
export const DEFAULT_LAYOUT = { libraryWidth: 272, inspectorWidth: 308 } as const;
export const LAYOUT_BOUNDS = {
  library: { min: 220, max: 480 },
  inspector: { min: 260, max: 560 },
  canvasMin: 430,
  dividerWidth: 8,
} as const;

type LayoutStorage = Pick<Storage, 'getItem' | 'setItem'>;

export type EditorLayout = { libraryWidth: number; inspectorWidth: number };

function asFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function constrainedLayout(layout: EditorLayout, availableWidth = Number.POSITIVE_INFINITY): EditorLayout {
  const dividerSpace = LAYOUT_BOUNDS.dividerWidth * 2;
  const panelsMax = Math.max(
    LAYOUT_BOUNDS.library.min + LAYOUT_BOUNDS.inspector.min,
    availableWidth - LAYOUT_BOUNDS.canvasMin - dividerSpace,
  );
  let libraryWidth = clamp(layout.libraryWidth, LAYOUT_BOUNDS.library.min, LAYOUT_BOUNDS.library.max);
  let inspectorWidth = clamp(layout.inspectorWidth, LAYOUT_BOUNDS.inspector.min, LAYOUT_BOUNDS.inspector.max);
  const overflow = libraryWidth + inspectorWidth - panelsMax;
  if (overflow > 0) {
    const libraryReduction = Math.min(overflow, libraryWidth - LAYOUT_BOUNDS.library.min);
    libraryWidth -= libraryReduction;
    inspectorWidth = Math.max(LAYOUT_BOUNDS.inspector.min, inspectorWidth - (overflow - libraryReduction));
  }
  return { libraryWidth, inspectorWidth };
}

export function loadEditorLayout(storage: LayoutStorage): EditorLayout {
  try {
    const raw = storage.getItem(EDITOR_LAYOUT_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_LAYOUT };
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { ...DEFAULT_LAYOUT };
    const record = parsed as Record<string, unknown>;
    if (record.version !== 1) return { ...DEFAULT_LAYOUT };
    const libraryWidth = asFiniteNumber(record.libraryWidth);
    const inspectorWidth = asFiniteNumber(record.inspectorWidth);
    if (libraryWidth === null || inspectorWidth === null) return { ...DEFAULT_LAYOUT };
    return constrainedLayout({ libraryWidth, inspectorWidth });
  } catch {
    return { ...DEFAULT_LAYOUT };
  }
}

export function saveEditorLayout(storage: LayoutStorage, layout: EditorLayout): void {
  try {
    storage.setItem(EDITOR_LAYOUT_STORAGE_KEY, JSON.stringify({ version: 1, ...constrainedLayout(layout) }));
  } catch {
    // Layout preference is optional. Draft persistence reports its own errors.
  }
}
