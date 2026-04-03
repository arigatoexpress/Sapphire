import SwiftUI
import Foundation

/// Central state for the Sapphire Command Center.
/// All data is fetched from local services (Ollama, OpenBB, tv CLI, plugin tools).
@MainActor
final class AppState: ObservableObject {
    // Device mesh
    @Published var devices: [DeviceInfo] = []
    @Published var meshLastUpdate: Date?

    // Inference
    @Published var gpuModels: [String] = []
    @Published var localModels: [String] = []
    @Published var gpuOnline = false
    @Published var localOllamaOnline = false

    // Repos
    @Published var repos: [RepoStatus] = []

    // Token budget
    @Published var budget: [String: TierBudget] = [:]

    // Factory state
    @Published var factoryMetrics: FactoryMetrics?

    // Market data
    @Published var tvSymbol: String = ""
    @Published var tvPrice: Double = 0
    @Published var tvConnected = false

    // Events
    @Published var recentEvents: [SapphireEvent] = []

    // Loading
    @Published var isLoading = false
    @Published var lastError: String?

    // Paths
    private let sapphireDir = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Code/Sapphire")
    private let pluginTools: URL

    init() {
        pluginTools = sapphireDir.appendingPathComponent("plugins/claw-sapphire/tools")
        Task { await refreshAll() }
    }

    func refreshAll() async {
        isLoading = true
        defer { isLoading = false }

        await withTaskGroup(of: Void.self) { group in
            group.addTask { await self.fetchDevices() }
            group.addTask { await self.fetchModels() }
            group.addTask { await self.fetchRepos() }
            group.addTask { await self.fetchBudget() }
            group.addTask { await self.fetchFactory() }
            group.addTask { await self.fetchTradingView() }
            group.addTask { await self.fetchEvents() }
        }
        meshLastUpdate = Date()
    }

    // MARK: - Shell execution

    private func shell(_ command: String, timeout: TimeInterval = 15) async -> String {
        await withCheckedContinuation { cont in
            let task = Process()
            let pipe = Pipe()
            task.standardOutput = pipe
            task.standardError = pipe
            task.executableURL = URL(fileURLWithPath: "/bin/zsh")
            task.arguments = ["-c", "source ~/.zshenv 2>/dev/null; \(command)"]
            task.environment = [
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/sbin",
                "HOME": FileManager.default.homeDirectoryForCurrentUser.path,
            ]

            do {
                try task.run()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                task.waitUntilExit()
                cont.resume(returning: String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "")
            } catch {
                cont.resume(returning: "ERROR: \(error.localizedDescription)")
            }
        }
    }

    private func runTool(_ tool: String, input: [String: Any] = [:]) async -> [String: Any] {
        let inputJSON = (try? JSONSerialization.data(withJSONObject: input)) ?? Data()
        let inputStr = String(data: inputJSON, encoding: .utf8) ?? "{}"
        let output = await shell("echo '\(inputStr)' | python3 \(pluginTools.appendingPathComponent(tool).path)")

        if let data = output.data(using: .utf8),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            return json
        }
        return ["raw": output]
    }

    // MARK: - Fetchers

    func fetchDevices() async {
        let output = await shell("tailscale status --json 2>/dev/null")
        guard let data = output.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }

        var devs: [DeviceInfo] = []

        if let selfNode = json["Self"] as? [String: Any] {
            let ips = selfNode["TailscaleIPs"] as? [String] ?? []
            devs.append(DeviceInfo(
                name: selfNode["HostName"] as? String ?? "mac",
                ip: ips.first ?? "",
                online: true,
                role: "Commander"
            ))
        }

        if let peers = json["Peer"] as? [String: [String: Any]] {
            for (_, peer) in peers {
                let ips = peer["TailscaleIPs"] as? [String] ?? []
                devs.append(DeviceInfo(
                    name: peer["HostName"] as? String ?? "unknown",
                    ip: ips.first ?? "",
                    online: peer["Online"] as? Bool ?? false,
                    role: guessRole(peer["HostName"] as? String ?? "")
                ))
            }
        }

        devices = devs.sorted { $0.name < $1.name }
    }

    func fetchModels() async {
        // GPU
        let gpuOut = await shell("curl -s --connect-timeout 3 http://100.71.10.48:11434/api/tags 2>/dev/null")
        if let data = gpuOut.data(using: .utf8),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let models = json["models"] as? [[String: Any]] {
            gpuModels = models.compactMap { $0["name"] as? String }.sorted()
            gpuOnline = true
        } else {
            gpuModels = []
            gpuOnline = false
        }

        // Local
        let localOut = await shell("curl -s --connect-timeout 3 http://localhost:11434/api/tags 2>/dev/null")
        if let data = localOut.data(using: .utf8),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let models = json["models"] as? [[String: Any]] {
            localModels = models.compactMap { $0["name"] as? String }.sorted()
            localOllamaOnline = true
        } else {
            localModels = []
            localOllamaOnline = false
        }
    }

    func fetchRepos() async {
        let result = await runTool("verify.py", input: ["all": true])
        var repoList: [RepoStatus] = []
        for (name, info) in result {
            guard let info = info as? [String: Any] else { continue }
            let lint = (info["lint"] as? [String: Any])?["errors"] as? Int ?? -1
            let git = info["git"] as? [String: Any] ?? [:]
            repoList.append(RepoStatus(
                name: name,
                branch: git["branch"] as? String ?? "?",
                uncommitted: git["uncommitted"] as? Int ?? 0,
                lintErrors: lint,
                safeToCommit: info["safe_to_commit"] as? Bool ?? false
            ))
        }
        repos = repoList.sorted { $0.name < $1.name }
    }

    func fetchBudget() async {
        let result = await runTool("budget.py", input: ["json": true])
        var budgets: [String: TierBudget] = [:]
        for (tier, info) in result {
            guard let info = info as? [String: Any] else { continue }
            budgets[tier] = TierBudget(
                label: info["label"] as? String ?? tier,
                used: info["used"] as? Int ?? 0,
                budget: info["budget"] as? Int,
                calls: info["calls"] as? Int ?? 0,
                pctUsed: info["pct_used"] as? Double ?? 0
            )
        }
        budget = budgets
    }

    func fetchFactory() async {
        let result = await runTool("state.py", input: ["action": "metrics"])
        factoryMetrics = FactoryMetrics(
            totalIssues: result["total_issues"] as? Int ?? 0,
            openIssues: result["open"] as? Int ?? 0,
            fixedIssues: result["fixed"] as? Int ?? 0,
            inBackoff: result["in_backoff"] as? Int ?? 0
        )
    }

    func fetchTradingView() async {
        let output = await shell("tv status 2>/dev/null")
        guard let data = output.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            tvConnected = false
            return
        }
        tvConnected = json["cdp_connected"] as? Bool ?? false
        tvSymbol = json["chart_symbol"] as? String ?? ""
        if let quote = await shell("tv quote 2>/dev/null").data(using: .utf8),
           let qj = try? JSONSerialization.jsonObject(with: quote) as? [String: Any] {
            tvPrice = qj["last"] as? Double ?? qj["close"] as? Double ?? 0
        }
    }

    func fetchEvents() async {
        let eventsPath = sapphireDir.appendingPathComponent("data/system_events.jsonl")
        guard let content = try? String(contentsOf: eventsPath, encoding: .utf8) else { return }
        let lines = content.components(separatedBy: "\n").filter { !$0.isEmpty }.suffix(20)
        var events: [SapphireEvent] = []
        for line in lines {
            if let data = line.data(using: .utf8),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                events.append(SapphireEvent(
                    timestamp: json["timestamp"] as? String ?? "",
                    type: json["type"] as? String ?? "",
                    message: json["message"] as? String ?? ""
                ))
            }
        }
        recentEvents = events.reversed()
    }

    // MARK: - Actions

    func runFactoryScan() async {
        _ = await shell("python3 \(pluginTools.appendingPathComponent("verify.py").path) <<< '{\"all\": true}'")
        await fetchRepos()
    }

    func runLintFix() async {
        _ = await shell("cd \(sapphireDir.path) && python3 -m ruff check --fix --select E,F,I . 2>&1")
        await fetchRepos()
    }

    func sendNotification(_ message: String) async {
        _ = await runTool("notify.py", input: ["message": message, "priority": "p1"])
    }

    func runDispatch(_ task: String, tier: String? = nil) async -> String {
        var input: [String: Any] = ["task": task]
        if let tier = tier { input["tier"] = tier }
        let result = await runTool("dispatch.py", input: input)
        return result["output"] as? String ?? (result["error"] as? String ?? "No output")
    }

    // MARK: - Helpers

    private func guessRole(_ hostname: String) -> String {
        let h = hostname.lowercased()
        if h.contains("desktop") || h.contains("hfck") { return "GPU Workbench" }
        if h.contains("rari1") { return "Controller" }
        if h.contains("rari2") { return "Trader" }
        return "Unknown"
    }
}
