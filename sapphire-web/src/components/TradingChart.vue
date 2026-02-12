<script setup lang="ts">
import {
    createChart,
    CandlestickSeries,
    HistogramSeries,
    type IChartApi,
    ColorType,
    type UTCTimestamp,
} from 'lightweight-charts'
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

const props = withDefaults(
    defineProps<{
        basePrice?: number
        height?: number
    }>(),
    {
        basePrice: 80,
        height: 280,
    },
)

const chartContainer = ref<HTMLElement | null>(null)
let chart: IChartApi | null = null
let candleSeries: any = null
let volumeSeries: any = null
let resizeHandler: (() => void) | null = null

const seedCandles = (base: number) => {
    const data: Array<{
        time: UTCTimestamp
        open: number
        high: number
        low: number
        close: number
    }> = []
    const now = Math.floor(Date.now() / 1000)
    let prior = base

    for (let i = 120; i >= 1; i -= 1) {
        const delta = (Math.random() - 0.5) * 0.8
        const open = prior
        const close = Math.max(0.001, open + delta)
        const high = Math.max(open, close) + Math.random() * 0.5
        const low = Math.min(open, close) - Math.random() * 0.5
        const time = (now - i * 60) as UTCTimestamp
        data.push({
            time,
            open: Number(open.toFixed(3)),
            high: Number(high.toFixed(3)),
            low: Number(low.toFixed(3)),
            close: Number(close.toFixed(3)),
        })
        prior = close
    }
    return data
}

const seedVolume = (candles: Array<{ time: UTCTimestamp; open: number; close: number }>) =>
    candles.map((item) => ({
        time: item.time,
        value: Math.round(120 + Math.random() * 360),
        color: item.close >= item.open ? 'rgba(23,200,136,0.45)' : 'rgba(255,116,116,0.45)',
    }))

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

    const candles = seedCandles(props.basePrice)
    if (candleSeries) candleSeries.setData(candles)
    if (volumeSeries) volumeSeries.setData(seedVolume(candles))

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
    () => props.basePrice,
    () => {
        renderChart()
    },
)
</script>

<template>
    <div ref="chartContainer" class="chart-wrapper"></div>
</template>

<style scoped>
.chart-wrapper {
    width: 100%;
    border-radius: 12px;
    overflow: hidden;
}
</style>
