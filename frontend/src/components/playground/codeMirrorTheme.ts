import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { EditorView } from '@codemirror/view'
import { tags as t } from '@lezer/highlight'

/**
 * CodeMirror theme wired to the app's CSS variables so it tracks the app
 * surface in both palettes. The syntax palette is chosen per app theme because
 * a single set of token colors does not read well on both backgrounds.
 */
function baseTheme(dark: boolean) {
  return EditorView.theme(
    {
      '&': {
        color: 'var(--app-foreground)',
        backgroundColor: 'transparent',
        fontSize: '12.5px',
        height: '100%',
      },
      '.cm-scroller': {
        fontFamily: 'var(--font-mono)',
        lineHeight: '1.6',
      },
      '.cm-content': {
        caretColor: 'var(--app-accent)',
        padding: '8px 0',
      },
      '.cm-gutters': {
        backgroundColor: 'transparent',
        color: 'var(--app-subtle)',
        border: 'none',
        paddingLeft: '4px',
      },
      '.cm-activeLine': {
        backgroundColor: dark
          ? 'color-mix(in srgb, var(--app-raised) 60%, transparent)'
          : 'color-mix(in srgb, var(--app-raised) 70%, transparent)',
      },
      '.cm-activeLineGutter': { backgroundColor: 'transparent', color: 'var(--app-muted)' },
      '&.cm-focused': { outline: 'none' },
      '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--app-accent)' },
      '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': {
        backgroundColor: 'color-mix(in srgb, var(--app-accent) 28%, transparent)',
      },
      '.cm-placeholder': { color: 'var(--app-subtle)' },
      '.cm-lineNumbers .cm-gutterElement': { padding: '0 6px 0 4px' },
      // Merge / diff decorations (@codemirror/merge).
      '.cm-changedLine': {
        backgroundColor: 'color-mix(in srgb, var(--app-success) 15%, transparent)',
      },
      '.cm-changedText': {
        backgroundColor: 'color-mix(in srgb, var(--app-success) 32%, transparent)',
        borderRadius: '2px',
      },
      '.cm-changedLineGutter': { backgroundColor: 'var(--app-success-soft)' },
      '.cm-deletedChunk': {
        backgroundColor: 'color-mix(in srgb, var(--app-rose) 12%, transparent)',
      },
      '.cm-deletedText': {
        backgroundColor: 'color-mix(in srgb, var(--app-rose) 26%, transparent)',
      },
      '.cm-mergeControls': { padding: '0 4px' },
      '.cm-mergeControls button': {
        color: 'var(--app-muted)',
        backgroundColor: 'var(--app-raised)',
        border: '1px solid var(--app-border)',
        borderRadius: '4px',
        marginRight: '3px',
        padding: '0 4px',
      },
    },
    { dark },
  )
}

const DARK_TOKENS = HighlightStyle.define([
  { tag: [t.comment, t.lineComment, t.blockComment], color: '#6b7280', fontStyle: 'italic' },
  { tag: [t.keyword, t.operatorKeyword, t.modifier, t.controlKeyword], color: '#c792ea' },
  { tag: [t.string, t.special(t.string)], color: '#c3e88d' },
  { tag: [t.number, t.bool, t.null, t.atom], color: '#f78c6c' },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: '#82aaff' },
  { tag: [t.className, t.typeName, t.namespace, t.definition(t.variableName)], color: '#ffcb6b' },
  { tag: [t.propertyName], color: '#b2ccd6' },
  { tag: [t.variableName], color: '#e8eaed' },
  { tag: [t.operator], color: '#89ddff' },
  { tag: [t.punctuation, t.separator, t.bracket, t.derefOperator], color: '#9aa2ad' },
  { tag: [t.self, t.constant(t.name)], color: '#f78c6c' },
])

const LIGHT_TOKENS = HighlightStyle.define([
  { tag: [t.comment, t.lineComment, t.blockComment], color: '#8a8f98', fontStyle: 'italic' },
  { tag: [t.keyword, t.operatorKeyword, t.modifier, t.controlKeyword], color: '#a626a4' },
  { tag: [t.string, t.special(t.string)], color: '#50a14f' },
  { tag: [t.number, t.bool, t.null, t.atom], color: '#986801' },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: '#4078f2' },
  { tag: [t.className, t.typeName, t.namespace, t.definition(t.variableName)], color: '#c18401' },
  { tag: [t.propertyName], color: '#383a42' },
  { tag: [t.variableName], color: '#383a42' },
  { tag: [t.operator], color: '#0184bc' },
  { tag: [t.punctuation, t.separator, t.bracket, t.derefOperator], color: '#696c77' },
  { tag: [t.self, t.constant(t.name)], color: '#986801' },
])

export function codeThemeExtensions(dark: boolean) {
  return [baseTheme(dark), syntaxHighlighting(dark ? DARK_TOKENS : LIGHT_TOKENS)]
}
