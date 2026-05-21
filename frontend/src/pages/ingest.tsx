import { useState, useCallback, DragEvent } from 'react'

export default function Ingest() {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState('')

  const uploadFile = async (file: File) => {
    setUploading(true)
    setError('')
    setResult(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/v1/ingest', { method: 'POST', body: form })
      const data = await res.json()
      if (res.ok) setResult(data)
      else setError(data.detail || 'Upload failed')
    } catch (e) {
      setError(String(e))
    }
    setUploading(false)
  }

  const onDrop = useCallback((e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }, [])

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-2">Document Upload</h1>
      <p className="text-slate-400 mb-6">Upload PDFs, text files, or images for session-scoped analysis</p>

      <div
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
          dragging ? 'border-indigo-500 bg-indigo-500/10' : 'border-slate-700 hover:border-slate-500'
        }`}
      >
        <svg className="mx-auto h-12 w-12 text-slate-500 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
        <p className="text-slate-300 mb-2">Drag and drop a file here</p>
        <p className="text-slate-500 text-sm">or click to browse</p>
        <input
          type="file"
          onChange={e => { const f = e.target.files?.[0]; if (f) uploadFile(f) }}
          className="mt-4 text-sm text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-indigo-600 file:text-white hover:file:bg-indigo-700"
          disabled={uploading}
        />
      </div>

      {uploading && (
        <div className="mt-4 text-center text-indigo-400 animate-pulse">Uploading and indexing...</div>
      )}

      {error && (
        <div className="mt-4 bg-red-900/30 border border-red-800 rounded-lg p-3 text-red-300 text-sm">{error}</div>
      )}

      {result && (
        <div className="mt-6 bg-slate-800 border border-slate-700 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-3">Upload Complete</h3>
          <div className="space-y-2 text-sm text-slate-300">
            <div><span className="text-slate-500">File:</span> {String(result.filename)}</div>
            <div><span className="text-slate-500">Document ID:</span> {String(result.document_id)}</div>
            <div><span className="text-slate-500">Chunks:</span> {String(result.chunks)}</div>
            <div><span className="text-slate-500">Session:</span> {String(result.session_id)}</div>
          </div>
          <a
            href={`/reason?session=${result.session_id}`}
            className="mt-4 inline-block px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm transition-colors"
          >
            Query this document
          </a>
        </div>
      )}
    </div>
  )
}
