import Foundation

enum PMHubClientError: LocalizedError {
    case invalidBaseURL(String)
    case missingToken
    case invalidResponse
    case httpError(code: Int, body: String)

    var errorDescription: String? {
        switch self {
        case let .invalidBaseURL(baseURL):
            return "Invalid base URL: \(baseURL)"
        case .missingToken:
            return "Missing control-plane token. Add it in Settings."
        case .invalidResponse:
            return "Invalid server response."
        case let .httpError(code, body):
            if body.isEmpty {
                return "HTTP \(code)"
            }
            return "HTTP \(code): \(body)"
        }
    }
}

struct PMHubClient {
    private let baseURL: URL
    private let token: String

    init(baseURL: String, token: String) throws {
        let normalized = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parsed = URL(string: normalized), parsed.scheme != nil else {
            throw PMHubClientError.invalidBaseURL(baseURL)
        }

        let tokenValue = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !tokenValue.isEmpty else {
            throw PMHubClientError.missingToken
        }

        self.baseURL = parsed
        self.token = tokenValue
    }

    func controlOverview() async throws -> ControlOverviewResponse {
        try await get("/api/control/overview")
    }

    func executorPolicy() async throws -> ExecutorPolicyResponse {
        try await get("/api/control/executor-policy")
    }

    func controlAgents(ttlSeconds: Int = 180) async throws -> ControlAgentsResponse {
        try await get("/api/control/agents?heartbeat_ttl_seconds=\(ttlSeconds)")
    }

    func projectsOverview(refresh: Bool = true) async throws -> ProjectsOverviewResponse {
        try await get("/api/projects/overview?refresh=\(refresh ? "true" : "false")")
    }

    func opsInventory(refresh: Bool = true, includeLogs: Bool = false, eventLimit: Int = 20) async throws -> OpsInventoryResponse {
        try await get(
            "/api/ops/inventory?refresh=\(refresh ? "true" : "false")&include_logs=\(includeLogs ? "true" : "false")&event_limit=\(max(1, min(eventLimit, 100)))"
        )
    }

    func tasks(status: String, limit: Int = 100) async throws -> TaskListResponse {
        let safeStatus = status.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? status
        return try await get("/api/control/tasks?status=\(safeStatus)&limit=\(max(1, limit))")
    }

    func syncBoard() async throws -> [String: Any] {
        try await integrationAction(payload: [
            "action": "sync_board",
            "actor": "pm-commander-macos",
        ])
    }

    func runAutonomyCycle(limit: Int = 2) async throws -> [String: Any] {
        try await integrationAction(payload: [
            "action": "autonomy_cycle",
            "actor": "pm-commander-macos",
            "limit": max(1, min(limit, 6)),
            "force": true,
        ])
    }

    func runAssistantCheckin(limit: Int = 4) async throws -> [String: Any] {
        try await integrationAction(payload: [
            "action": "assistant_checkin",
            "actor": "pm-commander-macos",
            "limit": max(1, min(limit, 12)),
            "force": true,
        ])
    }

    func runDeepResearch(topic: String = "highest-impact project blocker", force: Bool = true) async throws -> [String: Any] {
        try await integrationAction(payload: [
            "action": "deepresearch_run",
            "actor": "pm-commander-macos",
            "topic": topic,
            "force": force,
            "payload": [
                "force": force,
            ],
        ])
    }

    func refreshMembershipQuotas(force: Bool = false) async throws -> [String: Any] {
        try await postJSON(
            "/api/router/quotas/refresh",
            payload: [
                "force": force,
            ]
        )
    }

    private func integrationAction(payload: [String: Any]) async throws -> [String: Any] {
        try await postJSON("/api/integrations/kimi-claw/pm", payload: payload)
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        let data = try await request(method: "GET", path: path, body: nil)
        let decoder = JSONDecoder()
        return try decoder.decode(T.self, from: data)
    }

    private func postJSON(_ path: String, payload: [String: Any]) async throws -> [String: Any] {
        let body = try JSONSerialization.data(withJSONObject: payload, options: [])
        let data = try await request(method: "POST", path: path, body: body)
        guard !data.isEmpty else {
            return [:]
        }
        let object = try JSONSerialization.jsonObject(with: data, options: [])
        if let dictionary = object as? [String: Any] {
            return dictionary
        }
        return ["status": "ok", "raw": String(data: data, encoding: .utf8) ?? ""]
    }

    private func request(method: String, path: String, body: Data?) async throws -> Data {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw PMHubClientError.invalidBaseURL(baseURL.absoluteString)
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 30
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(token, forHTTPHeaderField: "X-Control-Token")
        request.setValue(token, forHTTPHeaderField: "X-Job-Token")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw PMHubClientError.invalidResponse
        }

        guard (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw PMHubClientError.httpError(code: http.statusCode, body: body)
        }
        return data
    }
}
