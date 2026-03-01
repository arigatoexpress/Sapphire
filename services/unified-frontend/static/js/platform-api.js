(function () {
  async function request(path, options) {
    const response = await fetch(path, {
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
      },
      ...(options || {}),
    });

    let payload = {};
    try {
      payload = await response.json();
    } catch (_) {
      payload = {};
    }

    if (!response.ok) {
      const message = payload.error || payload.message || `HTTP ${response.status}`;
      const error = new Error(message);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }

    return payload;
  }

  function withParams(path, params) {
    const search = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return;
      search.set(key, String(value));
    });
    const qs = search.toString();
    return qs ? `${path}?${qs}` : path;
  }

  window.platformApi = {
    request,
    getStatus() {
      return request('/api/platform/status');
    },
    getMetrics() {
      return request('/api/platform/metrics');
    },
    getLogs(params) {
      return request(withParams('/api/platform/logs', params));
    },
    getOrganization(refresh = false) {
      return request(withParams('/api/platform/organization', refresh ? { refresh: true } : {}));
    },
    getReadiness() {
      return request('/api/platform/readiness');
    },
    getProjects() {
      return request('/api/platform/projects');
    },
    getWindowsLab() {
      return request('/api/platform/windows-lab');
    },
    getIntelFeed(params) {
      return request(withParams('/api/platform/intel-feed', params));
    },
  };
})();
