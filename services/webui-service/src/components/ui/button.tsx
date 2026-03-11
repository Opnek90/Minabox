/**
 * Minimal shim – kept so existing imports of ButtonVariant / ButtonSize
 * don’t break. ActionButton now renders MUI Button / IconButton directly.
 *
 * Do NOT use this component directly. Use ActionButton with actionType instead.
 */
export type ButtonVariant = 'default' | 'outline' | 'ghost' | 'destructive';
export type ButtonSize    = 'default' | 'sm' | 'lg' | 'icon';
