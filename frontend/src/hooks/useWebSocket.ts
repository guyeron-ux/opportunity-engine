import { useEffect, useRef, useState } from 'react'

export interface WsMessage {
  event: string
  data: Record<string, unknown>
}

export function useWebSocket(onMessage: (msg: WsMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    // In production, VITE_WS_URL must point directly to the backend (e.g. wss://your-app.railway.app/ws)
    // because Netlify cannot proxy WebSockets.
    const envWs = import.meta.env.VITE_WS_URL as string | undefined
    const url = envWs || (() => {
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      return `${protocol}://${window.location.host}/ws`
    })()

    function connect() {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        // Reconnect after 3s
        setTimeout(connect, 3000)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data) as WsMessage
          onMessage(msg)
        } catch {
          // ignore malformed
        }
      }
    }

    connect()
    return () => {
      wsRef.current?.close()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return connected
}
