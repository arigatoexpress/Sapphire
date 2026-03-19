import Foundation

enum PlatformClientError: LocalizedError {
    case invalidBaseURL(String)
    case missingCredentials
    case invalidResponse
    case httpError(code: Int, body: String)

    var errorDescription: String? {
        switch self {
        case let .invalidBaseURL(baseURL):
            return "Invalid platform base URL: \(baseURL)"
        case .missingCredentials:
            return "Missing platform credentials. Update Settings."
        case .invalidResponse:
            return "Invalid platform response."
        case let .httpError(code, body):
            if body.isEmpty {
                return "Platform HTTP \(code)"
            }
            return "Platform HTTP \(code): \(body)"
        }
    }
}

struct PlatformClient {
    private let baseURL: URL
    private let username: String
    private let password: String

    init(baseURL: String, username: String, password: String) throws {
        let normalized = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parsed = URL(string: normalized), parsed.scheme != nil else {
            throw PlatformClientError.invalidBaseURL(baseURL)
        }

        let user = username.trimmingCharacters(in: .whitespacesAndNewlines)
        let pass = password.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !user.isEmpty, !pass.isEmpty else {
            throw PlatformClientError.missingCredentials
        }

        self.baseURL = parsed
        self.username = user
        self.password = pass
    }

    func status() async throws -> PlatformStatusResponse {
        try await get("/api/platform/status")
    }

    func metrics() async throws -> PlatformMetricsResponse {
        try await get("/api/platform/metrics")
    }

    func readiness() async throws -> PlatformReadinessResponse {
        try await get("/api/platform/readiness")
    }

    func contracts() async throws -> PlatformContractsResponse {
        try await get("/api/platform/contracts")
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        let data = try await request(method: "GET", path: path)
        let decoder = JSONDecoder()
        return try decoder.decode(T.self, from: data)
    }

    private func request(method: String, path: String) async throws -> Data {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw PlatformClientError.invalidBaseURL(baseURL.absoluteString)
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("SapphireOperatorClient/2.0 (macOS)", forHTTPHeaderField: "User-Agent")

        let auth = "\(username):\(password)"
        if let encoded = auth.data(using: .utf8)?.base64EncodedString() {
            request.setValue("Basic \(encoded)", forHTTPHeaderField: "Authorization")
        }

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw PlatformClientError.invalidResponse
        }

        guard (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw PlatformClientError.httpError(code: http.statusCode, body: body)
        }

        return data
    }
}
