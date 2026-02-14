/**
 * useWebSocket — reactive WebSocket composable for Sapphire dashboard.
 *
 * Connects to the Alpha Engine `/ws` endpoint and provides:
 *  - Automatic reconnect with exponential backoff (3s → 6s → 12s → …60s cap)
 *  - Ping/pong keep-alive matching backend's 30s heartbeat
 *  - Message dispatch to registered callbacks by message type
 *  - Graceful fallback: stores continue REST polling as backup
 *
 * Usage:
 *   const ws = useWebSocket()
 *   ws.onMessage('snapshot', (data) => { ... })
 *   ws.connect()   // in onMounted
 *   ws.disconnect() // in onUnmounted
 */

import { ref, readonly } from 'vue'

const API_BASE = (
    import.meta.env.VITE_API_URL || 'https://sapphire-alpha-s77j6bxyra-uc.a.run.app'
).trim()

/** Convert HTTP(S) base URL to WS(S) URL */
function toWsUrl(base: string): string {
    return base.replace(/^http/, 'ws') + '/ws'
}

export type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

export interface WsMessage {
    type: string
    [key: string]: unknown
}

type MessageHandler = (data: WsMessage) => void

// ── Singleton state (shared across all composable calls) ──

let _socket: WebSocket | null = null
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null
let _pingTimer: ReturnType<typeof setInterval> | null = null
let _reconnectAttempts = 0
let _intentionalClose = false

const _status = ref<WsStatus>('disconnected')
const _lastMessageAt = ref(0)

const MAX_RECONNECT_DELAY = 60_000    // 60s cap
const BASE_RECONNECT_DELAY = 3_000    // 3s initial
const PING_INTERVAL = 25_000          // 25s (server timeout is 30s)
const MAX_RECONNECT_ATTEMPTS = 50

/** Per-type listener registry */
const _listeners = new Map<string, Set<MessageHandler>>()

function _dispatch(msg: WsMessage): void {
    _lastMessageAt.value = Date.now()

    // Dispatch to type-specific listeners
    const handlers = _listeners.get(msg.type)
    if (handlers) {
        for (const fn of handlers) {
            try {
                fn(msg)
            } catch (err) {
                console.error(`[WS] Handler error for type '${msg.type}':`, err)
            }
        }
    }

    // Dispatch to wildcard listeners
    const wildcards = _listeners.get('*')
    if (wildcards) {
        for (const fn of wildcards) {
            try {
                fn(msg)
            } catch (err) {
                console.error('[WS] Wildcard handler error:', err)
            }
        }
    }
}

function _startPing(): void {
    _stopPing()
    _pingTimer = setInterval(() => {
        if (_socket?.readyState === WebSocket.OPEN) {
            _socket.send('ping')
        }
    }, PING_INTERVAL)
}

function _stopPing(): void {
    if (_pingTimer) {
        clearInterval(_pingTimer)
        _pingTimer = null
    }
}

function _scheduleReconnect(): void {
    if (_intentionalClose) return
    if (_reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        console.warn('[WS] Max reconnect attempts reached. Giving up — REST polling remains active.')
        _status.value = 'disconnected'
        return
    }

    const delay = Math.min(
        BASE_RECONNECT_DELAY * Math.pow(2, _reconnectAttempts),
        MAX_RECONNECT_DELAY,
    )
    _reconnectAttempts++
    _status.value = 'reconnecting'
    console.info(`[WS] Reconnecting in ${(delay / 1000).toFixed(1)}s (attempt ${_reconnectAttempts})`)

    _reconnectTimer = setTimeout(() => {
        _reconnectTimer = null
        _connect()
    }, delay)
}

function _connect(): void {
    if (_socket?.readyState === WebSocket.OPEN || _socket?.readyState === WebSocket.CONNECTING) {
        return
    }

    _status.value = 'connecting'
    const url = toWsUrl(API_BASE)

    try {
        _socket = new WebSocket(url)
    } catch {
        _scheduleReconnect()
        return
    }

    _socket.onopen = () => {
        _status.value = 'connected'
        _reconnectAttempts = 0
        _startPing()
        console.info('[WS] Connected to', url)
    }

    _socket.onmessage = (event) => {
        if (event.data === 'pong') return // ping response, ignore

        try {
            const msg = JSON.parse(event.data) as WsMessage
            _dispatch(msg)
        } catch {
            // Non-JSON message (e.g. plain text pong)
        }
    }

    _socket.onclose = (event) => {
        _stopPing()
        _socket = null

        if (_intentionalClose) {
            _status.value = 'disconnected'
        } else {
            console.info(`[WS] Connection closed (code=${event.code}). Scheduling reconnect.`)
            _scheduleReconnect()
        }
    }

    _socket.onerror = () => {
        // onclose will fire after onerror — reconnect handled there
    }
}

function _disconnect(): void {
    _intentionalClose = true
    _stopPing()

    if (_reconnectTimer) {
        clearTimeout(_reconnectTimer)
        _reconnectTimer = null
    }

    if (_socket) {
        _socket.close(1000)
        _socket = null
    }

    _status.value = 'disconnected'
    _reconnectAttempts = 0
}

// ── Public composable ──

let _refCount = 0

export function useWebSocket() {
    /** Register a handler for a specific message type (or '*' for all). */
    function onMessage(type: string, handler: MessageHandler): void {
        if (!_listeners.has(type)) {
            _listeners.set(type, new Set())
        }
        _listeners.get(type)!.add(handler)
    }

    /** Remove a previously registered handler. */
    function offMessage(type: string, handler: MessageHandler): void {
        const set = _listeners.get(type)
        if (set) {
            set.delete(handler)
            if (set.size === 0) _listeners.delete(type)
        }
    }

    /** Connect (ref-counted — first caller opens, subsequent callers are no-ops). */
    function connect(): void {
        _refCount++
        if (_refCount === 1) {
            _intentionalClose = false
            _connect()
        }
    }

    /** Disconnect (ref-counted — last caller closes). */
    function disconnect(): void {
        _refCount = Math.max(0, _refCount - 1)
        if (_refCount === 0) {
            _disconnect()
        }
    }

    return {
        status: readonly(_status),
        lastMessageAt: readonly(_lastMessageAt),
        connect,
        disconnect,
        onMessage,
        offMessage,
    }
}
