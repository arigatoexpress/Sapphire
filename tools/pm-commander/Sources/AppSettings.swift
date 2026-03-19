import Foundation
import Security

@MainActor
final class AppSettings: ObservableObject {
    @Published var baseURL: String {
        didSet {
            UserDefaults.standard.set(baseURL, forKey: Self.baseURLKey)
        }
    }

    @Published var platformBaseURL: String {
        didSet {
            let normalized = Self.normalizePlatformBaseURL(platformBaseURL)
            if normalized != platformBaseURL {
                platformBaseURL = normalized
                return
            }
            UserDefaults.standard.set(normalized, forKey: Self.platformBaseURLKey)
        }
    }

    @Published var platformUsername: String {
        didSet {
            UserDefaults.standard.set(platformUsername, forKey: Self.platformUsernameKey)
        }
    }

    @Published var autoRefreshSeconds: Double {
        didSet {
            let normalized = max(15, min(300, autoRefreshSeconds))
            if normalized != autoRefreshSeconds {
                autoRefreshSeconds = normalized
                return
            }
            UserDefaults.standard.set(normalized, forKey: Self.refreshKey)
        }
    }

    @Published private(set) var hasToken: Bool
    @Published private(set) var hasPlatformPassword: Bool

    static let baseURLKey = "pm.commander.base_url"
    static let platformBaseURLKey = "sapphire.operator.platform_base_url"
    static let platformUsernameKey = "sapphire.operator.platform_username"
    static let refreshKey = "pm.commander.refresh_seconds"

    static let defaultBaseURL = "https://agentic-pm-hub-267358751314.us-central1.run.app"
    static let defaultPlatformBaseURL = "https://sapphirealpha.xyz"
    static let defaultPlatformUsername = "sapphire"
    static let canonicalPlatformHost = "sapphirealpha.xyz"

    private static let deprecatedPlatformHosts: Set<String> = [
        "dashboard.sapphirealpha.xyz",
        "pm.sapphirealpha.xyz",
        "gateway.sapphirealpha.xyz",
        "sapphire-unified-frontend-s77j6bxyra-uc.a.run.app",
        "sapphire-command-deck-s77j6bxyra-uc.a.run.app",
        "sapphire-dashboard-s77j6bxyra-uc.a.run.app",
        "sapphire-log-viewer-s77j6bxyra-uc.a.run.app",
    ]

    init() {
        let storedBaseURL = UserDefaults.standard.string(forKey: Self.baseURLKey) ?? Self.bootstrapBaseURL()
        baseURL = storedBaseURL

        let storedPlatformURL = UserDefaults.standard.string(forKey: Self.platformBaseURLKey) ?? Self.bootstrapPlatformBaseURL()
        let normalizedPlatformURL = Self.normalizePlatformBaseURL(storedPlatformURL)
        platformBaseURL = normalizedPlatformURL
        UserDefaults.standard.set(normalizedPlatformURL, forKey: Self.platformBaseURLKey)

        let storedPlatformUser = UserDefaults.standard.string(forKey: Self.platformUsernameKey) ?? Self.bootstrapPlatformUsername()
        platformUsername = storedPlatformUser

        let storedRefresh = UserDefaults.standard.double(forKey: Self.refreshKey)
        autoRefreshSeconds = storedRefresh == 0 ? 30 : max(15, min(300, storedRefresh))

        let keychainToken = KeychainTokenStore.shared.readControlPlaneToken() ?? ""
        let bootstrapToken = Self.bootstrapToken()
        hasToken = !(keychainToken.isEmpty ? bootstrapToken : keychainToken).isEmpty

        let keychainPassword = KeychainTokenStore.shared.readPlatformPassword() ?? ""
        let bootstrapPassword = Self.bootstrapPlatformPassword()
        hasPlatformPassword = !(keychainPassword.isEmpty ? bootstrapPassword : keychainPassword).isEmpty
    }

    func readToken() -> String {
        if let keychainToken = KeychainTokenStore.shared.readControlPlaneToken(), !keychainToken.isEmpty {
            return keychainToken
        }
        return Self.bootstrapToken()
    }

    func saveToken(_ token: String) throws {
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            try KeychainTokenStore.shared.deleteControlPlaneToken()
            hasToken = false
            return
        }
        try KeychainTokenStore.shared.writeControlPlaneToken(trimmed)
        hasToken = true
    }

    func clearToken() throws {
        try KeychainTokenStore.shared.deleteControlPlaneToken()
        hasToken = !Self.bootstrapToken().isEmpty
    }

    func readPlatformPassword() -> String {
        if let password = KeychainTokenStore.shared.readPlatformPassword(), !password.isEmpty {
            return password
        }
        return Self.bootstrapPlatformPassword()
    }

    func savePlatformPassword(_ password: String) throws {
        let trimmed = password.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            try KeychainTokenStore.shared.deletePlatformPassword()
            hasPlatformPassword = false
            return
        }
        try KeychainTokenStore.shared.writePlatformPassword(trimmed)
        hasPlatformPassword = true
    }

    func clearPlatformPassword() throws {
        try KeychainTokenStore.shared.deletePlatformPassword()
        hasPlatformPassword = !Self.bootstrapPlatformPassword().isEmpty
    }

    private static func bootstrapBaseURL() -> String {
        if let url = bootstrapEnvValue("CONTROL_PLANE_BASE_URL"), !url.isEmpty {
            return url
        }
        return defaultBaseURL
    }

    private static func bootstrapPlatformBaseURL() -> String {
        if let url = bootstrapEnvValue("PLATFORM_BASE_URL"), !url.isEmpty {
            return normalizePlatformBaseURL(url)
        }
        return normalizePlatformBaseURL(defaultPlatformBaseURL)
    }

    private static func bootstrapPlatformUsername() -> String {
        if let value = bootstrapEnvValue("PLATFORM_AUTH_USERNAME"), !value.isEmpty {
            return value
        }
        return defaultPlatformUsername
    }

    private static func bootstrapToken() -> String {
        if let token = bootstrapEnvValue("CONTROL_PLANE_TOKEN"), !token.isEmpty {
            return token
        }
        if let token = bootstrapEnvValue("CONTROL_PLANE_SHARED_TOKEN"), !token.isEmpty {
            return token
        }
        return ""
    }

    private static func bootstrapPlatformPassword() -> String {
        if let password = bootstrapEnvValue("PLATFORM_AUTH_PASSWORD"), !password.isEmpty {
            return password
        }
        return ""
    }

    private static func bootstrapEnvValue(_ key: String) -> String? {
        let env = ProcessInfo.processInfo.environment
        if let value = env[key]?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty {
            return value
        }

        for path in envSearchPaths() {
            guard let content = try? String(contentsOf: path, encoding: .utf8) else {
                continue
            }
            for line in content.split(whereSeparator: \.isNewline) {
                let raw = line.trimmingCharacters(in: .whitespaces)
                if raw.isEmpty || raw.hasPrefix("#") || !raw.contains("=") {
                    continue
                }
                let parts = raw.split(separator: "=", maxSplits: 1).map(String.init)
                if parts.count == 2, parts[0].trimmingCharacters(in: .whitespaces) == key {
                    let value = parts[1].trimmingCharacters(in: .whitespacesAndNewlines)
                    if !value.isEmpty {
                        return value
                    }
                }
            }
        }
        return nil
    }

    private static func envSearchPaths() -> [URL] {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        let candidates = [
            home.appendingPathComponent(".openclaw/.env"),
            cwd.appendingPathComponent(".env"),
            cwd.deletingLastPathComponent().appendingPathComponent(".env"),
            cwd.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent(".env"),
            cwd.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent(".env"),
        ]
        return candidates
    }

    func resetURLsToCanonicalDefaults() {
        baseURL = Self.defaultBaseURL
        platformBaseURL = Self.defaultPlatformBaseURL
    }

    var isPlatformBaseURLCanonical: Bool {
        guard let host = URL(string: platformBaseURL.trimmingCharacters(in: .whitespacesAndNewlines))?.host?.lowercased() else {
            return false
        }
        return host == Self.canonicalPlatformHost
    }

    private static func normalizePlatformBaseURL(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return defaultPlatformBaseURL
        }

        guard let parsed = URL(string: trimmed), let host = parsed.host?.lowercased() else {
            return defaultPlatformBaseURL
        }

        if host == canonicalPlatformHost || deprecatedPlatformHosts.contains(host) {
            return defaultPlatformBaseURL
        }

        // If someone points directly to any unified-frontend Cloud Run URL, pin to canonical domain.
        if host.contains("sapphire-unified-frontend") && host.hasSuffix(".run.app") {
            return defaultPlatformBaseURL
        }

        if var components = URLComponents(url: parsed, resolvingAgainstBaseURL: false), let scheme = components.scheme?.lowercased(), scheme == "http" || scheme == "https" {
            components.scheme = "https"
            components.path = ""
            components.query = nil
            components.fragment = nil
            return components.string ?? defaultPlatformBaseURL
        }

        return defaultPlatformBaseURL
    }
}

@MainActor
final class KeychainTokenStore {
    static let shared = KeychainTokenStore()

    private let service = "com.arigatoexpress.pm-commander"
    private let controlPlaneAccount = "control-plane-token"
    private let platformPasswordAccount = "platform-basic-password"

    private init() {}

    func readControlPlaneToken() -> String? {
        read(account: controlPlaneAccount)
    }

    func writeControlPlaneToken(_ token: String) throws {
        try write(token, account: controlPlaneAccount)
    }

    func deleteControlPlaneToken() throws {
        try delete(account: controlPlaneAccount)
    }

    func readPlatformPassword() -> String? {
        read(account: platformPasswordAccount)
    }

    func writePlatformPassword(_ password: String) throws {
        try write(password, account: platformPasswordAccount)
    }

    func deletePlatformPassword() throws {
        try delete(account: platformPasswordAccount)
    }

    private func read(account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess else {
            return nil
        }
        guard let data = item as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    private func write(_ value: String, account: String) throws {
        let data = Data(value.utf8)
        let baseQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]

        let update: [String: Any] = [
            kSecValueData as String: data,
        ]

        let updateStatus = SecItemUpdate(baseQuery as CFDictionary, update as CFDictionary)
        if updateStatus == errSecSuccess {
            return
        }

        var add = baseQuery
        add[kSecValueData as String] = data
        let addStatus = SecItemAdd(add as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            throw KeychainError.unhandled(status: addStatus)
        }
    }

    private func delete(account: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainError.unhandled(status: status)
        }
    }
}

enum KeychainError: LocalizedError {
    case unhandled(status: OSStatus)

    var errorDescription: String? {
        switch self {
        case let .unhandled(status):
            return "Keychain operation failed (status \(status))."
        }
    }
}
