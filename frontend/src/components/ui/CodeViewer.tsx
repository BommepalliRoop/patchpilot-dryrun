import { useEffect, useState } from 'react'
import { codeToHtml } from 'shiki'
import { langFor } from '../../lib/ui'

/**
 * Shiki (github-dark) with one highlighted line. The Shiki HTML is the only `dangerouslySetInnerHTML` in the app
 * (RISKS S11): Shiki escapes the code itself. While loading or on failure the code shows as plain text (React-escaped).
 */
export default function CodeViewer({ code, file, line, startLine = 1, inRoute }: {
  code?: string | null
  file?: string
  line?: number
  startLine?: number
  inRoute?: boolean
}) {
  const text = code ?? ''
  const [html, setHtml] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    setHtml(null)
    codeToHtml(text, {
      lang: langFor(file),
      theme: 'github-dark',
      transformers: [
        {
          line(node, n) {
            this.addClassToHast(node, 'pp-line')
            if (line != null && n + startLine - 1 === line) this.addClassToHast(node, 'pp-hl')
          },
        },
      ],
    })
      .then((h) => live && setHtml(h))
      .catch(() => live && setHtml(null))
    return () => {
      live = false
    }
  }, [text, file, line, startLine])

  return (
    <figure className="m-0 overflow-hidden rounded-xl border border-border bg-[#0d1117]">
      {(file || inRoute) && (
        <figcaption className="flex items-center justify-between border-b border-border px-3 py-2 font-mono text-xs text-muted">
          <span>
            {file}
            {line != null ? `:${line}` : ''}
          </span>
          {inRoute && <span className="rounded-full border border-danger/50 bg-danger/15 px-2 py-0.5 text-danger">in route</span>}
        </figcaption>
      )}
      <div className="pp-code overflow-x-auto font-mono text-[13px]" style={{ ['--pp-start' as string]: startLine - 1 }}>
        {html ? <div dangerouslySetInnerHTML={{ __html: html }} /> : <pre className="m-0 p-3 text-fg">{text}</pre>}
      </div>
    </figure>
  )
}
