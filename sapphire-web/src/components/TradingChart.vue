<script setup lang="ts">
import {
    createChart,
    CandlestickSeries,
    HistogramSeries,
    type IChartApi,
    ColorType,
    type UTCTimestamp,
} from 'lightweight-charts'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { OhlcCandle } from '../api/client'

const props = withDefaults(
    defineProps<{
        candles?: OhlcCandle[]
        height?: number
    }>(),
    {
        candles: () => [],
        height: 280,
    },
)

const chartContainer = ref<HTMLElement | null>(null)
let chart: IChartApi | null = null
let candleSeries: any = null
let volumeSeries: any = null
let resizeHandler: (() => void) | null = null

const normalizedCandles = computed(() =>
    (props.candles || [])
        .filter(
            (item) =>
                Number.isFinite(Number(item.time)) &&
                Number.isFinite(Number(item.open)) &&
                Number.isFinite(Number(item.high)) &&
                Number.isFinite(Number(item.low)) &&
                Number.isFinite(Number(item.close)),
        )
        .map((item) => ({
            time: Math.floor(Number(item.time)) as UTCTimestamp,
            open: Number(item.open),
            high: Number(item.high),
            low: Number(item.low),
            close: Number(item.close),
            volume: Number.isFinite(Number(item.volume)) ? Number(item.volume) : 0,
        }))
        .sort((a, b) => Number(a.time) - Number(b.time)),
)

const hasData = computed(() => normalizedCandles.value.length > 0)

const renderChart = async () => {
    if (!chartContainer.value) return

    await nextTick()
    if (!chartContainer.value) return

    chart?.remove()
    chart = createChart(chartContainer.value, {
        width: chartContainer.value.clientWidth,
        height: props.height,
        layout: {
            background: { type: ColorType.Solid, color: 'transparent' },
            textColor: 'rgba(184, 214, 245, 0.82)',
            attributionLogo: false,
        },
        grid: {
            vertLines: { color: 'rgba(110, 164, 212, 0.12)' },
            horzLines: { color: 'rgba(110, 164, 212, 0.12)' },
        },
        rightPriceScale: {
            borderColor: 'rgba(110, 164, 212, 0.2)',
        },
        timeScale: {
            borderColor: 'rgba(110, 164, 212, 0.2)',
            timeVisible: true,
            secondsVisible: false,
        },
        crosshair: {
            horzLine: { color: 'rgba(120, 199, 255, 0.4)' },
            vertLine: { color: 'rgba(120, 199, 255, 0.4)' },
        },
    })

    candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#17c888',
        downColor: '#ff7474',
        borderVisible: false,
        wickUpColor: '#17c888',
        wickDownColor: '#ff7474',
    })

    volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' },
        priceScaleId: '',
    })

    if (candleSeries) candleSeries.setData(normalizedCandles.value)
    if (volumeSeries) {
        volumeSeries.setData(
            normalizedCandles.value.map((item) => ({
                time: item.time,
                value: Math.max(item.volume || 0, 0),
                color: item.close >= item.open ? 'rgba(23,200,136,0.45)' : 'rgba(255,116,116,0.45)',
            })),
        )
    }

    chart.timeScale().fitContent()
}

onMounted(() => {
    renderChart()
    resizeHandler = () => {
        if (!chartContainer.value || !chart) return
        chart.applyOptions({ width: chartContainer.value.clientWidth })
    }
    window.addEventListener('resize', resizeHandler)
})

onUnmounted(() => {
    if (resizeHandler) window.removeEventListener('resize', resizeHandler)
    chart?.remove()
})

watch(
    () => props.height,
    () => {
        renderChart()
    },
)

watch(
    normalizedCandles,
    () => {
        renderChart()
    },
    { deep: true },
)
</script>

<template>
    <div class="chart-wrapper">
        <div ref="chartContainer" class="chart-canvas"></div>
        <div v-if="!hasData" class="empty-state">Waiting for live OHLC feed...</div>
    </div>
</template>

<style scoped>
.chart-wrapper {
    position: relative;
    width: 100%;
    min-height: 200px;
}

.chart-canvas {
    width: 100%;
    height: 100%;
    border-radius: 12px;
    overflow: hidden;
}

.empty-state {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    color: rgba(184, 214, 245, 0.78);
    font-size: 0.8rem;
    letter-spacing: 0.02em;
    pointer-events: none;
    background: linear-gradient(180deg, rgba(8, 22, 40, 0.22), rgba(8, 22, 40, 0.4));
}
</style>
