import { useEffect, useState, memo } from 'react';

interface AnimatedNumberProps {
    value: number;
    duration?: number;
    prefix?: string;
    suffix?: string;
    decimals?: number;
    className?: string;
    colorBySign?: boolean;
}

/**
 * AnimatedNumber - Smoothly animates between number values.
 * Used for portfolio values, PnL, percentages, etc.
 */
export const AnimatedNumber = memo<AnimatedNumberProps>(({
    value,
    duration = 800,
    prefix = '',
    suffix = '',
    decimals = 2,
    className = '',
    colorBySign = false
}) => {
    const [displayValue, setDisplayValue] = useState(value);
    const [isAnimating, setIsAnimating] = useState(false);

    useEffect(() => {
        if (displayValue === value) return;

        setIsAnimating(true);
        const startValue = displayValue;
        const endValue = value;
        const startTime = performance.now();

        const animate = (currentTime: number) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // Ease-out cubic for smooth deceleration
            const easeOut = 1 - Math.pow(1 - progress, 3);
            const current = startValue + (endValue - startValue) * easeOut;

            setDisplayValue(current);

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                setIsAnimating(false);
            }
        };

        requestAnimationFrame(animate);
    }, [value, duration]);

    // Determine color based on sign
    let colorClass = '';
    if (colorBySign) {
        if (displayValue > 0) colorClass = 'text-emerald-400';
        else if (displayValue < 0) colorClass = 'text-red-400';
        else colorClass = 'text-white';
    }

    const formattedValue = displayValue.toFixed(decimals);
    const displaySign = colorBySign && displayValue > 0 ? '+' : '';

    return (
        <span className={`${className} ${colorClass} ${isAnimating ? 'transition-colors' : ''}`}>
            {prefix}{displaySign}{formattedValue}{suffix}
        </span>
    );
});

AnimatedNumber.displayName = 'AnimatedNumber';
export default AnimatedNumber;
