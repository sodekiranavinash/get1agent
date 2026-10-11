import { useMemo } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { json } from '@codemirror/lang-json'
import { python } from '@codemirror/lang-python'
import { EditorView } from '@codemirror/view'

import { codeThemeExtensions } from './codeMirrorTheme'

/**
 * Editable CodeMirror used for the tool source and the JSON schemas. The
 * surrounding container owns the height; the editor fills it. The theme tracks
 * the app palette via `dark` (the surrounding surface shows through).
 */
export function CodeEditor({
  value,
  onChange,
  language = 'python',
  readOnly = false,
  dark = false,
  placeholder,
  className = '',
}: {
  value: string
  onChange?: (value: string) => void
  language?: 'python' | 'json'
  readOnly?: boolean
  dark?: boolean
  placeholder?: string
  className?: string
}) {
  const extensions = useMemo(
    () => [language === 'json' ? json() : python(), EditorView.lineWrapping, ...codeThemeExtensions(dark)],
    [language, dark],
  )

  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      placeholder={placeholder}
      // The wrapper defaults its theme to "light", which injects a white
      // `background-color` on `&`. CodeMirror mounts style modules in reverse,
      // so that default would override our theme. Disable it and let
      // `codeThemeExtensions()` own the surface.
      theme="none"
      extensions={extensions}
      height="100%"
      className={`h-full text-[12.5px] ${className}`}
      basicSetup={{
        lineNumbers: true,
        foldGutter: false,
        highlightActiveLine: true,
        highlightActiveLineGutter: true,
        highlightSelectionMatches: false,
        autocompletion: false,
        bracketMatching: true,
        closeBrackets: true,
        indentOnInput: true,
      }}
    />
  )
}
