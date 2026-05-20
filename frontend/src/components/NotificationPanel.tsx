import { useState, useEffect, useRef, MutableRefObject } from 'react'
import type { WsMessage } from '../hooks/useWebSocket'

interface Notification {
  id: number
  event: string
  message: string
  timestamp: string
}

let _notifId = 0

function eventMessage(msg: WsMessage): string {
  if (msg.event === 'opportunity_added') return `New: ${msg.data.title} — ${(msg.data.score as number).toFixed(1)}`
  if (msg.event === 'scouts_done') return `${msg.data.signal_count} signals collected`
  if (msg.event === 'batch_done') return `Analyzed ${msg.data.processed}/${msg.data.total} signals`
  if (msg.event === 'cycle_done') return `Cycle complete — ${msg.data.new_opportunities} new opportunities`
  if (msg.event === 'cycle_start') return msg.data.source ? `Import started: ${msg.data.source}` : 'Discovery cycle started'
  if (msg.event === 'cycle_error') return `Error: ${msg.data.error}`
  if (msg.event === 'rerate_start') return `Re-rating ${msg.data.total} opportunities…`
  if (msg.event === 'rerate_progress') return `Re-rated: ${msg.data.title} → ${msg.data.type}`
  if (msg.event === 'rerate_done') return `Re-rating complete — ${msg.data.total} opportunities updated`
  if (msg.event === 'rerate_error') return `Re-rate error: ${msg.data.error}`
  return ''
}

interface Props {
  wsNotifyRef: MutableRefObject<((msg: WsMessage) => void) | null>
}

export function NotificationPanel({ wsNotifyRef }: Props) {
  const [notifs, setNotifs] = useState<Notification[]>([])
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)

  // Register this panel as the notification sink
  useEffect(() => {
    wsNotifyRef.current = (msg: WsMessage) => {
      const text = eventMessage(msg)
      if (!text) return
      setNotifs(prev => [
        { id: ++_notifId, event: msg.event, message: text, timestamp: new Date().toLocaleTimeString() },
        ...prev.slice(0, 49),
      ])
      if (!open) setUnread(n => n + 1)
    }
  }, [wsNotifyRef, open])

  function handleOpen() {
    setOpen(o => !o)
    setUnread(0)
  }

  return (
    <div className="relative">
      <button onClick={handleOpen} className="relative p-2 rounded-lg hover:bg-gray-800 transition-colors">
        <span className="text-lg">🔔</span>
        {unread > 0 && (
          <span className="absolute top-0 right-0 bg-violet-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center">
            {Math.min(unread, 9)}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-10 w-80 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-50 max-h-96 overflow-y-auto">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
            <span className="font-semibold text-sm">Events</span>
            <button onClick={() => { setNotifs([]); setOpen(false) }} className="text-xs text-gray-500 hover:text-white">
              Clear
            </button>
          </div>
          {notifs.length === 0 ? (
            <p className="text-center text-gray-600 py-6 text-sm">No events yet</p>
          ) : (
            notifs.map(n => (
              <div key={n.id} className="px-4 py-2 border-b border-gray-800 hover:bg-gray-800">
                <div className="flex justify-between text-xs text-gray-500 mb-0.5">
                  <span className="font-mono">{n.event}</span>
                  <span>{n.timestamp}</span>
                </div>
                <p className="text-sm text-gray-200">{n.message}</p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
