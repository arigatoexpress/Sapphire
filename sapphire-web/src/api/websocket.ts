import { ref } from 'vue'

export type WebSocketStatus = 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'ERROR'

export class WebSocketClient {
    private ws: WebSocket | null = null
    private url: string
    private reconnectAttempts = 0
    private maxReconnectAttempts = 5
    private reconnectDelay = 2000
    private listeners: ((data: any) => void)[] = []

    public status = ref<WebSocketStatus>('DISCONNECTED')

    constructor(endpoint: string) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const host = window.location.host
        // If dev mode, use the known backend URL (optional fallback)
        const baseUrl = import.meta.env.PROD
            ? `${protocol}//${host}`
            : 'wss://sapphire-v2-s77j6bxyra-uc.a.run.app'

        this.url = `${baseUrl}${endpoint}`
    }

    connect() {
        if (this.ws?.readyState === WebSocket.OPEN) return

        this.status.value = 'CONNECTING'
        console.log(`🔌 [WS] Connecting to ${this.url}`)

        try {
            this.ws = new WebSocket(this.url)

            this.ws.onopen = () => {
                console.log('✅ [WS] Connected')
                this.status.value = 'CONNECTED'
                this.reconnectAttempts = 0
            }

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data)
                    this.notifyListeners(data)
                } catch (e) {
                    console.error('❌ [WS] Parse error:', e)
                }
            }

            this.ws.onclose = () => {
                console.log('⚠️ [WS] Disconnected')
                this.status.value = 'DISCONNECTED'
                this.handleReconnect()
            }

            this.ws.onerror = (error) => {
                console.error('❌ [WS] Error:', error)
                this.status.value = 'ERROR'
            }

        } catch (e) {
            console.error('❌ [WS] Connection failed:', e)
            this.handleReconnect()
        }
    }

    private handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++
            console.log(`Checking reconnect... Attempt ${this.reconnectAttempts}`)
            setTimeout(() => this.connect(), this.reconnectDelay * this.reconnectAttempts)
        }
    }

    subscribe(callback: (data: any) => void) {
        this.listeners.push(callback)
        return () => {
            this.listeners = this.listeners.filter(l => l !== callback)
        }
    }

    private notifyListeners(data: any) {
        this.listeners.forEach(l => l(data))
    }

    disconnect() {
        if (this.ws) {
            this.ws.close()
            this.ws = null
        }
    }
}
