import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const MetricCard = ({ label, value, delta, icon, accent = 'teal', footer }) => {
    const deltaColor = delta && delta.value >= 0 ? 'text-accent-emerald' : 'text-error';
    const accentMap = {
        emerald: 'border-accent-emerald/40 before:from-accent-emerald/25',
        teal: 'border-accent-teal/40 before:from-accent-teal/25',
        amber: 'border-warning-amber/40 before:from-warning-amber/25',
        slate: 'border-brand-border/60 before:from-brand-border/40',
    };
    return (_jsxs("div", { className: `group sapphire-panel p-6 before:absolute before:inset-0 before:bg-gradient-to-br before:opacity-60 before:transition-opacity before:duration-200 ${accentMap[accent]}`, children: [_jsx("div", { className: "absolute inset-0 bg-gradient-to-br from-white/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200" }), _jsxs("div", { className: "relative flex items-start justify-between", children: [_jsxs("div", { className: "transition-transform duration-200 group-hover:translate-y-[-1px]", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-brand-muted/80 transition-colors duration-200 group-hover:text-brand-muted", children: label }), _jsx("div", { className: "mt-2 text-3xl font-semibold text-brand-ice transition-transform duration-200 group-hover:scale-105", children: value }), delta && (_jsxs("div", { className: "mt-2 flex items-center gap-2 text-xs font-medium text-brand-muted", children: [_jsxs("span", { className: `${deltaColor} transition-all duration-200 group-hover:scale-110`, children: [delta.value >= 0 ? '+' : '', delta.value.toFixed(2), "%"] }), _jsx("span", { className: "transition-colors duration-200 group-hover:text-brand-muted/90", children: delta.label ?? 'vs previous' })] }))] }), icon && _jsx("span", { className: "text-3xl text-brand-muted/70 transition-transform duration-200 group-hover:scale-110 group-hover:rotate-3", children: icon })] }), footer && _jsx("div", { className: "relative mt-4 text-xs text-brand-muted transition-colors duration-200 group-hover:text-brand-muted/80", children: footer })] }));
};
export default MetricCard;
