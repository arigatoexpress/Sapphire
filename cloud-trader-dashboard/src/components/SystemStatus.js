import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const badgeTone = (value) => {
    const normalized = typeof value === 'string' ? value.toLowerCase() : value;
    if (normalized === true || normalized === 'online' || normalized === 'healthy' || normalized === 'connected') {
        return 'bg-emerald-100/60 text-emerald-600';
    }
    if (normalized === false || normalized === 'offline' || normalized === 'unhealthy' || normalized === 'disconnected') {
        return 'bg-rose-100/60 text-rose-600';
    }
    return 'bg-slate-200/60 text-slate-600';
};
const badgeIcon = (value) => {
    const normalized = typeof value === 'string' ? value.toLowerCase() : value;
    if (normalized === true || normalized === 'online' || normalized === 'healthy' || normalized === 'connected') {
        return '🟢';
    }
    if (normalized === false || normalized === 'offline' || normalized === 'unhealthy' || normalized === 'disconnected') {
        return '🔴';
    }
    return '🟡';
};
const SystemStatus = ({ status }) => {
    const services = status?.services ?? {};
    const models = status?.models ?? {};
    const infrastructureChecks = [
        {
            label: `Cache (${status?.cache?.backend ?? 'memory'})`,
            value: status?.cache?.connected ?? false,
        },
        {
            label: 'Storage',
            value: status?.storage_ready ?? false,
        },
        {
            label: 'Pub/Sub',
            value: status?.pubsub_connected ?? false,
        },
        {
            label: 'Feature Store',
            value: status?.feature_store_ready ?? false,
        },
        {
            label: 'BigQuery',
            value: status?.bigquery_ready ?? false,
        },
    ];
    return (_jsxs("div", { className: "sapphire-panel border border-brand-border/50 bg-brand-abyss/70 p-6", children: [_jsxs("div", { className: "flex flex-col gap-4 md:flex-row md:items-center md:justify-between", children: [_jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.32em] text-brand-muted/80", children: "System Status" }), _jsx("h2", { className: "text-xl font-semibold text-brand-ice", children: "Runtime Snapshot" })] }), _jsxs("div", { className: "flex items-center gap-2 text-xs text-brand-muted/70", children: [_jsx("span", { children: "Last updated:" }), _jsx("span", { className: "rounded-full bg-brand-border/60 px-2 py-1 text-brand-ice", children: status?.timestamp ? new Date(status.timestamp).toLocaleTimeString() : 'Never' })] })] }), _jsxs("div", { className: "mt-6 grid gap-6 lg:grid-cols-[2fr,1fr]", children: [_jsxs("div", { className: "space-y-4", children: [_jsxs("section", { children: [_jsx("h3", { className: "mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-brand-muted/70", children: "Core Services" }), _jsxs("div", { className: "grid gap-2 sm:grid-cols-2", children: [Object.entries(services).map(([service, svcStatus]) => (_jsxs("div", { className: "flex items-center justify-between rounded-lg bg-brand-midnight/70 px-3 py-2", children: [_jsxs("div", { className: "flex items-center gap-2 text-brand-ice", children: [_jsx("span", { children: badgeIcon(svcStatus) }), _jsx("span", { className: "capitalize tracking-wide", children: service.replace('_', ' ') })] }), _jsx("span", { className: `rounded-full px-2 py-0.5 text-xs font-medium ${badgeTone(svcStatus)}`, children: svcStatus })] }, service))), Object.keys(services).length === 0 && (_jsx("div", { className: "rounded-lg bg-brand-midnight/60 px-3 py-6 text-center text-sm text-brand-muted", children: "No service telemetry available" }))] })] }), _jsxs("section", { children: [_jsx("h3", { className: "mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-brand-muted/70", children: "AI Models" }), _jsxs("div", { className: "grid gap-2 sm:grid-cols-2", children: [Object.entries(models).map(([model, mdlStatus]) => (_jsxs("div", { className: "flex items-center justify-between rounded-lg bg-brand-midnight/70 px-3 py-2", children: [_jsxs("div", { className: "flex items-center gap-2 text-brand-ice", children: [_jsx("span", { children: badgeIcon(mdlStatus) }), _jsx("span", { className: "tracking-wide", children: model })] }), _jsx("span", { className: `rounded-full px-2 py-0.5 text-xs font-medium ${badgeTone(mdlStatus)}`, children: mdlStatus })] }, model))), Object.keys(models).length === 0 && (_jsx("div", { className: "rounded-lg bg-brand-midnight/60 px-3 py-6 text-center text-sm text-brand-muted", children: "No model telemetry available" }))] })] })] }), _jsxs("aside", { className: "rounded-xl border border-brand-border/60 bg-brand-midnight/70 p-4", children: [_jsx("h3", { className: "mb-4 text-sm font-semibold uppercase tracking-[0.2em] text-brand-muted/70", children: "Data Backbone" }), _jsx("div", { className: "space-y-3", children: infrastructureChecks.map(({ label, value }) => (_jsxs("div", { className: "flex items-center justify-between", children: [_jsx("span", { className: "text-sm text-brand-muted", children: label }), _jsx("span", { className: `rounded-full px-2 py-0.5 text-xs font-medium ${badgeTone(value)}`, children: value ? 'Connected' : 'Offline' })] }, label))) })] })] })] }));
};
export default SystemStatus;
