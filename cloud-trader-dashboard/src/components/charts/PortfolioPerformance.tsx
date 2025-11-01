import React, { useEffect, useMemo, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';

interface PerformanceDatum {
    timestamp: string | number;
    balance?: number;
    price?: number;
}

interface PortfolioPerformanceProps {
    balanceSeries: PerformanceDatum[];
    priceSeries: PerformanceDatum[];
}

const toUnix = (input: string | number) => {
    const date = typeof input === 'number' ? new Date(input) : new Date(input);
    return Math.floor(date.getTime() / 1000);
};

const PortfolioPerformance: React.FC<PortfolioPerformanceProps> = ({ balanceSeries, priceSeries }) => {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
    const areaSeriesRef = useRef<any>(null);
    const lineSeriesRef = useRef<any>(null);

    const balanceData = useMemo(
        () =>
            balanceSeries
                .filter((point) => typeof point.balance === 'number')
                .map((point) => ({
                    time: toUnix(point.timestamp),
                    value: point.balance ?? 0,
                })),
        [balanceSeries]
    );

    const priceData = useMemo(
        () =>
            priceSeries
                .filter((point) => typeof point.price === 'number')
                .map((point) => ({
                    time: toUnix(point.timestamp),
                    value: point.price ?? 0,
                })),
        [priceSeries]
    );

    useEffect(() => {
        if (!containerRef.current) return;

        const chart = createChart(containerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: '#cbd5f5',
                fontFamily: 'Inter',
            },
            grid: {
                horzLines: { color: 'rgba(148, 163, 184, 0.08)' },
                vertLines: { color: 'rgba(148, 163, 184, 0.08)' },
            },
            localization: {
                timeFormatter: (time: number) => new Date(time * 1000).toLocaleTimeString(),
            },
            rightPriceScale: {
                borderVisible: false,
                textColor: '#cbd5f5',
            },
            timeScale: {
                borderVisible: false,
                timeVisible: true,
                secondsVisible: false,
            },
        }) as any;

        chartRef.current = chart;

        // Temporarily disable chart creation to prevent crash
        const areaSeries = null;
        const lineSeries = null;

        areaSeriesRef.current = areaSeries;
        lineSeriesRef.current = lineSeries;

        const observer = new ResizeObserver(() => {
            if (containerRef.current) {
                chart.applyOptions({
                    width: containerRef.current.clientWidth,
                    height: containerRef.current.clientHeight,
                });
            }
        });

        observer.observe(containerRef.current);

        return () => {
            observer.disconnect();
            chart.remove();
            chartRef.current = null;
            areaSeriesRef.current = null;
            lineSeriesRef.current = null;
        };
    }, []);

    useEffect(() => {
        // Temporarily disabled to prevent crash
        // if (areaSeriesRef.current && balanceData.length > 0) {
        //     areaSeriesRef.current.setData(balanceData);
        // }
        // if (lineSeriesRef.current && priceData.length > 0) {
        //     lineSeriesRef.current.setData(priceData);
        // }
        // if (chartRef.current) {
        //     chartRef.current.timeScale().fitContent();
        // }
    }, [balanceData, priceData]);

    return <div ref={containerRef} className="h-64 w-full" />;
};

export default PortfolioPerformance;

