<script setup lang="ts">
import { ref } from 'vue'

const config = ref({
    autoTrading: true,
    maxLeverage: 5,
    riskLevel: 'moderate',
    telegramNotifications: true
})

const apiKeys = ref([
    { name: 'Drift Protocol', status: 'connected', key: '....d8a9' },
    { name: 'Symphony', status: 'connected', key: '....3f21' },
    { name: 'Hyperliquid', status: 'disconnected', key: '' },
])
</script>

<template>
    <div class="view-container">
        <h2 class="font-mono text-gradient">SYSTEM CONFIGURATION</h2>

        <div class="grid settings-grid">
            <!-- General Config -->
            <div class="panel glass">
                <div class="panel-header font-mono">TRADING PARAMETERS</div>
                <div class="panel-body">
                    <div class="setting-row">
                        <span>Autonomous Trading</span>
                        <div class="toggle" :class="{ active: config.autoTrading }" @click="config.autoTrading = !config.autoTrading">
                            <div class="knob"></div>
                        </div>
                    </div>
                     <div class="setting-row">
                        <span>Max Leverage</span>
                        <input type="number" v-model="config.maxLeverage" class="input-glass" />
                    </div>
                </div>
            </div>

            <!-- API Keys -->
            <div class="panel glass">
                <div class="panel-header font-mono">EXCHANGE CONNECTIONS</div>
                <div class="panel-body">
                    <div v-for="api in apiKeys" :key="api.name" class="key-row">
                        <div class="key-info">
                            <span class="name">{{ api.name }}</span>
                            <span class="status font-mono" :class="api.status === 'connected' ? 'text-success' : 'text-error'">
                                {{ api.status.toUpperCase() }}
                            </span>
                        </div>
                        <button class="btn-config font-mono">CONFIGURE</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
.view-container {
    display: flex;
    flex-direction: column;
    gap: 2rem;
}

.settings-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
    gap: 1.5rem;
}

.panel {
    border-radius: var(--radius-md);
    overflow: hidden;
}

.panel-header {
    padding: 1rem 1.5rem;
    background: rgba(255,255,255,0.03);
    border-bottom: var(--glass-border);
    font-size: 0.8rem;
    color: var(--text-secondary);
}

.panel-body {
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
}

.setting-row, .key-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.toggle {
    width: 40px;
    height: 20px;
    background: var(--bg-hover);
    border-radius: 10px;
    position: relative;
    cursor: pointer;
    transition: background 0.2s;
}

.toggle.active {
    background: var(--color-brand);
}

.knob {
    width: 16px;
    height: 16px;
    background: white;
    border-radius: 50%;
    position: absolute;
    top: 2px;
    left: 2px;
    transition: transform 0.2s;
}

.toggle.active .knob {
    transform: translateX(20px);
}

.input-glass {
    background: rgba(0,0,0,0.2);
    border: 1px solid var(--border-subtle);
    color: var(--text-primary);
    padding: 0.5rem;
    border-radius: 4px;
    width: 60px;
    text-align: center;
}

.text-success { color: var(--color-success); }
.text-error { color: var(--text-secondary); } /* Disconnected is gray/dim */

.btn-config {
    background: rgba(255,255,255,0.05);
    border: none;
    color: var(--text-secondary);
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
    font-size: 0.7rem;
    cursor: pointer;
}

.btn-config:hover {
    background: rgba(255,255,255,0.1);
    color: var(--text-primary);
}
</style>
