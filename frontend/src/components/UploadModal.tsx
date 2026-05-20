import { useState, useRef, DragEvent, useEffect } from 'react'
import { api } from '../api'

interface Props {
  onClose: () => void
}

export function UploadModal({ onClose }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [status, setStatus] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [imports, setImports] = useState<Array<{ id: string; filename: string; imported_at: string; signals_extracted: number; opportunities_added: number }>>([])
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.getImports().then(setImports).catch(() => {})
  }, [])

  function accept(f: File) {
    const ext = f.name.split('.').pop()?.toLowerCase()
    if (!['pdf', 'md', 'txt'].includes(ext ?? '')) {
      setMessage('Only .pdf, .md, and .txt files are supported')
      setStatus('error')
      return
    }
    setFile(f)
    setMessage('')
    setStatus('idle')
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) accept(f)
  }

  async function handleUpload() {
    if (!file) return
    setStatus('uploading')
    setMessage('Uploading and extracting signals…')
    const result = await api.uploadFile(file)
    if (result.ok) {
      setStatus('done')
      setMessage('Pipeline started — watch the banner for live progress.')
      setTimeout(onClose, 2000)
    } else {
      setStatus('error')
      setMessage(result.message || 'Upload failed')
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="font-semibold text-white text-sm">Import Opportunities</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-lg leading-none">✕</button>
        </div>

        <div className="p-5 space-y-4">
          <p className="text-xs text-gray-400">
            Upload a PDF or Markdown file containing opportunities, pain points, or market gaps.
            Each signal will be fully researched and scored by the same pipeline as auto-discovered opportunities.
          </p>

          <div
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
              ${dragging ? 'border-violet-400 bg-violet-900/20' : 'border-gray-600 hover:border-violet-500'}`}
          >
            {file ? (
              <div>
                <p className="text-sm text-white font-medium">{file.name}</p>
                <p className="text-xs text-gray-400 mt-1">{(file.size / 1024).toFixed(0)} KB</p>
              </div>
            ) : (
              <div>
                <p className="text-2xl mb-2">📄</p>
                <p className="text-sm text-gray-300">Drag & drop or click to select</p>
                <p className="text-xs text-gray-500 mt-1">.pdf · .md · .txt</p>
              </div>
            )}
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.md,.txt"
              className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) accept(f) }}
            />
          </div>

          {message && (
            <p className={`text-xs ${status === 'error' ? 'text-red-400' : status === 'done' ? 'text-green-400' : 'text-gray-300'}`}>
              {message}
            </p>
          )}

          <div className="flex gap-2 pt-1">
            <button
              onClick={onClose}
              className="flex-1 text-sm border border-gray-600 text-gray-300 hover:border-gray-400 px-4 py-2 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleUpload}
              disabled={!file || status === 'uploading' || status === 'done'}
              className="flex-1 text-sm bg-violet-700 hover:bg-violet-600 disabled:opacity-40 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg font-semibold transition-colors"
            >
              {status === 'uploading' ? '⏳ Processing…' : status === 'done' ? '✓ Started' : 'Run Analysis'}
            </button>
          </div>

          {imports.length > 0 && (
            <div className="pt-2 border-t border-gray-800">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Import History</h3>
              <div className="space-y-1 max-h-36 overflow-y-auto">
                {[...imports].reverse().map(imp => (
                  <div key={imp.id} className="flex items-center justify-between text-xs py-1">
                    <div className="min-w-0">
                      <span className="text-gray-300 truncate block">{imp.filename}</span>
                      <span className="text-gray-600">{new Date(imp.imported_at).toLocaleString()}</span>
                    </div>
                    <div className="text-gray-500 text-right shrink-0 ml-3">
                      <div>{imp.signals_extracted} signals</div>
                      <div>{imp.opportunities_added} added</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
