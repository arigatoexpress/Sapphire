(function () {
    function cleanOrigin() {
        const currentUrl = new URL(window.location.href);
        currentUrl.username = '';
        currentUrl.password = '';
        return currentUrl.origin;
    }

    function withQuery(path, params) {
        const url = new URL(path, cleanOrigin());
        Object.entries(params || {}).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                url.searchParams.set(key, value);
            }
        });
        return url.href;
    }

    async function request(path, params) {
        const response = await fetch(withQuery(path, params), { credentials: 'same-origin' });
        if (!response.ok) {
            throw new Error(`${path} ${response.status}`);
        }
        return response.json();
    }

    async function getStatus() {
        const data = await request('/api/health/summary');
        const healthy = Number(data.healthy_count || 0);
        const unhealthy = Number(data.unhealthy_count || 0);
        return {
            ...data,
            summary: {
                ...(data.summary || {}),
                service_healthy: healthy,
                service_total: healthy + unhealthy,
            },
        };
    }

    function getOrganization() {
        return request('/api/autonomy/org-coverage');
    }

    async function getProjects() {
        const org = await getOrganization();
        return { projects: org.programs || [] };
    }

    window.platformApi = {
        request,
        getStatus,
        getReadiness: () => request('/api/production/readiness'),
        getLogs: (params) => request('/api/logs', params),
        getMetrics: () => request('/api/metrics/history'),
        getIntelFeed: (params) => request('/api/intel', params),
        getWindowsLab: async () => {
            const status = await getStatus();
            return { windows: status.by_category?.windows || [] };
        },
        getAutonomy: () => request('/api/events/world-state'),
        getTrades: (params) => request('/api/signals', params),
        getOrganization,
        getProjects,
    };
})();
