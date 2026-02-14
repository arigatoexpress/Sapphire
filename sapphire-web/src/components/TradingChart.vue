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

let lastCandleCount = 0

const initChart = async () => {
    if (!chartContainer.value) return

    await nextTick()
    if (!chartContainer.value) return

    chart?.remove()
    chart = createChart(chartContainer.value, {
        width: chartContainer.value.clientWidth,
        height: props.height,
        layout: {
            background: { type: ColorType.Solid, color: 'transparent' },
            textColor: 'rgba(32, 194, 14, 0.7)',
            attributionLogo: false,
        },
        grid: {
            vertLines: { color: 'rgba(32, 194, 14, 0.08)' },
            horzLines: { color: 'rgba(32, 194, 14, 0.08)' },
        },
        rightPriceScale: {
            borderColor: 'rgba(32, 194, 14, 0.15)',
        },
        timeScale: {
            borderColor: 'rgba(32, 194, 14, 0.15)',
            timeVisible: true,
            secondsVisible: false,
        },
        crosshair: {
            horzLine: { color: 'rgba(32, 194, 14, 0.3)' },
            vertLine: { color: 'rgba(32, 194, 14, 0.3)' },
        },
    })

    candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#20C20E',
        downColor: '#ff4444',
        borderVisible: false,
        wickUpColor: '#20C20E',
        wickDownColor: '#ff4444',
    })

    volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' },
        priceScaleId: '',
    })

    setFullData()
    chart.timeScale().fitContent()
}

const setFullData = () => {
    const candles = normalizedCandles.value
    lastCandleCount = candles.length
    if (candleSeries) candleSeries.setData(candles)
    if (volumeSeries) {
        volumeSeries.setData(
            candles.map((item) => ({
                time: item.time,
                value: Math.max(item.volume || 0, 0),
                color: item.close >= item.open ? 'rgba(32,194,14,0.4)' : 'rgba(255,68,68,0.4)',
            })),
        )
    }
}

const updateChart = () => {
    if (!chart || !candleSeries || !volumeSeries) {
        initChart()
        return
    }

    const candles = normalizedCandles.value
    if (candles.length === 0) return

    // Full re-render if candle count changed significantly (symbol switch or large gap)
    if (Math.abs(candles.length - lastCandleCount) > 5) {
        setFullData()
        return
    }

    // Incremental update: update only the last candle (tip)
    const last = candles[candles.length - 1]
    if (!last) return
    candleSeries.update(last)
    volumeSeries.update({
        time: last.time,
        value: Math.max(last.volume || 0, 0),
        color: last.close >= last.open ? 'rgba(32,194,14,0.4)' : 'rgba(255,68,68,0.4)',
    })
    lastCandleCount = candles.length
}

onMounted(() => {
    initChart()
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
        initChart()
    },
)

watch(
    normalizedCandles,
    () => {
        updateChart()
    },
    { deep: true },
)
</script>

<template>
    <div class="chart-wrapper" role="img" :aria-label="hasData ? `Candlestick chart with ${normalizedCandles.length} candles` : 'Chart awaiting data'">
        <div ref="chartContainer" class="chart-canvas" aria-hidden="true"></div>
        <div v-if="!hasData" class="empty-state" role="status">Waiting for live OHLC feed...</div>
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
    color: rgba(32, 194, 14, 0.6);
    font-size: 0.8rem;
    letter-spacing: 0.02em;
    pointer-events: none;
    background: linear-gradient(180deg, rgba(10, 20, 10, 0.2), rgba(5, 10, 5, 0.4));
}
</style>
