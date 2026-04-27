(function () {
    function withQuery(path, params) {
        const url = new URL(path, window.location.origin);
        Object.entries(params || {}).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                url.searchParams.set(key, value);
            }
        });
        return url.pathname + url.search;
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
        return Promise.resolve({
            summary: { workspaces: 4 },
            model: {
                departments: [
                    {
                        name: 'Operations',
                        focus: 'Runtime health, routines, and deployment posture',
                        systems: ['Dashboard', 'Control plane', 'LaunchAgents'],
                    },
                    {
                        name: 'Trading Research',
                        focus: 'Paper execution, analytics, and risk controls',
                        systems: ['Signal logger', 'Strategy performance', 'Cascade'],
                    },
                    {
                        name: 'Intelligence',
                        focus: 'Threat, regional, and content pipelines',
                        systems: ['Threat refresh', 'Content engine', 'Foundry sync'],
                    },
                ],
            },
        });
    }

    function getProjects() {
        return Promise.resolve({
            projects: [
                { name: 'Sapphire OS', status: 'active', progress: 82 },
                { name: 'Routine migration', status: 'in_progress', progress: 45 },
                { name: 'Autonomy safety', status: 'active', progress: 68 },
                { name: 'Data platform', status: 'blocked', progress: 22 },
            ],
        });
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
