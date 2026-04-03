import Foundation

struct DeviceInfo: Identifiable, Hashable {
    let id = UUID()
    let name: String
    let ip: String
    let online: Bool
    let role: String
}

struct RepoStatus: Identifiable, Hashable {
    let id = UUID()
    let name: String
    let branch: String
    let uncommitted: Int
    let lintErrors: Int
    let safeToCommit: Bool
}

struct TierBudget: Identifiable, Hashable {
    let id = UUID()
    let label: String
    let used: Int
    let budget: Int?  // nil = unlimited
    let calls: Int
    let pctUsed: Double
}

struct FactoryMetrics: Hashable {
    let totalIssues: Int
    let openIssues: Int
    let fixedIssues: Int
    let inBackoff: Int
}

struct SapphireEvent: Identifiable, Hashable {
    let id = UUID()
    let timestamp: String
    let type: String
    let message: String

    var shortTimestamp: String {
        String(timestamp.prefix(19)).replacingOccurrences(of: "T", with: " ")
    }
}
