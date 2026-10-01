import { useEffect, useRef } from 'react'
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { unifiedMergeView } from '@codemirror/merge'
import { python } from '@codemirror/lang-python'

import { codeThemeExtensions } from './codeMirrorTheme'

/**
 * Inline "changes" view: a VS Code-style unified diff where the editor's
 * document is the proposed code and `original` is the accepted code. Deleted
 * lines are shown as read-only widgets and changed lines are highlighted; the
 * single accept/reject pair lives in the toolbar above (no per-chunk controls).
 * The parent remounts this component with a `key` whenever a new proposal
 * arrives, so it is created once per mount.
 */
export function CodeDiff({
  original,
  value,
  dark = true,
  onChange,
}: {
  original: string
  value: string
  dark?: boolean
  onChange?: (value: string) => void
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const valueRef = useRef(value)
  const originalRef = useRef(original)
  const darkRef = useRef(dark)
  const changeRef = useRef(onChange)

  // Keep the latest props in refs without touching them during render.
  useEffect(() => {
    valueRef.current = value
    originalRef.current = original
    darkRef.current = dark
    changeRef.current = onChange
  })

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const view = new EditorView({
      state: EditorState.create({
        doc: valueRef.current,
        extensions: [
          python(),
          EditorView.lineWrapping,
          ...codeThemeExtensions(darkRef.current),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) changeRef.current?.(update.state.doc.toString())
          }),
          unifiedMergeView({
            original: originalRef.current,
            highlightChanges: true,
            gutter: true,
            // Accept/reject is a single action in the toolbar above, so no
            // per-chunk controls here.
            mergeControls: false,
            allowInlineDiffs: true,
            collapseUnchanged: { margin: 3, minSize: 4 },
          }),
        ],
      }),
      parent: host,
    })
    return () => view.destroy()
  }, [])

  return <div ref={hostRef} className="scrollbar-thin h-full min-h-0 overflow-auto" />
}
