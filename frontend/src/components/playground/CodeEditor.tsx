import { useMemo } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { json } from '@codemirror/lang-json'
import { python } from '@codemirror/lang-python'
import { EditorView } from '@codemirror/view'

import { codeThemeExtensions } from './codeMirrorTheme'

/**
 * Editable CodeMirror used for the tool source and the JSON schemas. The
 * surrounding container owns the height; the editor fills it.
 */
export function CodeEditor({
  value,
  onChange,
  language = 'python',
  readOnly = false,
  dark = true,
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
    () => [
      language === 'json' ? json() : python(),
      EditorView.lineWrapping,
      ...codeThemeExtensions(dark),
    ],
    [language, dark],
  )

  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      placeholder={placeholder}
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
