import SwiftUI
import Combine

class StatusBarController: NSObject, ObservableObject {
    private var statusItem: NSStatusItem
    private var menu: NSMenu
    private var timer: Timer?
    private var cancellables = Set<AnyCancellable>()

    struct SystemSnapshot {
        var healthyServices: Int = 0
        var totalServices: Int = 0
        var readinessOk: Bool = false
        var projects: Int = 0
        var workspaces: Int = 0
        var agentsOnline: Int = 0
        var agentsTotal: Int = 0
        var signals: Int = 0
        var trades: Int = 0
        var pnl: Double = 0
        var btcPrice: Double = 0
        var latestActivity: String = "No activity yet"
        var updatedAt: Date? = nil
        var errorMessage: String = ""

        var isHealthy: Bool {
            return totalServices > 0 && healthyServices == totalServices && readinessOk
        }

        var serviceRatio: Double {
            guard totalServices > 0 else { return 0 }
            return Double(healthyServices) / Double(totalServices)
        }
    }

    @Published var snapshot = SystemSnapshot()

    private let baseURL = "https://sapphirealpha.xyz"
    private let publicPaths: [String: String] = [
        "dashboard": "/",
        "organization": "/organization",
        "intelligence": "/intelligence",
        "activity": "/activity",
        "readiness": "/production-readiness",
        "statusJSON": "/api/platform/status",
        "contractsJSON": "/api/platform/contracts",
    ]
    private let internalURLs: [String: String] = [
        "pmHubOrganization": "https://agentic-pm-hub-267358751314.us-central1.run.app/organization",
        "pmManager": "https://agentic-pm-hub-267358751314.us-central1.run.app/organization",
    ]
    private let operatorUserDefaultsKey = "SapphireOperatorUser"
    private let operatorPasswordDefaultsKey = "SapphireOperatorPassword"

    override init() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        menu = NSMenu()
        super.init()

        setupMenuBar()
        startMonitoring()
    }

    private func setupMenuBar() {
        statusItem.button?.title = "💎"
        statusItem.menu = menu
        buildMenu()
    }

    private func buildMenu() {
        menu.removeAllItems()

        let status = NSMenuItem(title: "Status: loading...", action: nil, keyEquivalent: "")
        status.tag = 100
        menu.addItem(status)

        let pm = NSMenuItem(title: "PM: loading...", action: nil, keyEquivalent: "")
        pm.tag = 101
        menu.addItem(pm)

        let trading = NSMenuItem(title: "Trading: loading...", action: nil, keyEquivalent: "")
        trading.tag = 102
        menu.addItem(trading)

        let activity = NSMenuItem(title: "Activity: loading...", action: nil, keyEquivalent: "")
        activity.tag = 103
        menu.addItem(activity)

        let updated = NSMenuItem(title: "Updated: never", action: nil, keyEquivalent: "")
        updated.tag = 104
        menu.addItem(updated)

        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "🌐 Open Platform (Public)", action: #selector(openDashboard), keyEquivalent: "d"))
        menu.addItem(NSMenuItem(title: "🏢 Open Organization (Public)", action: #selector(openOrganization), keyEquivalent: "o"))
        menu.addItem(NSMenuItem(title: "🧠 Open Intelligence (Public)", action: #selector(openIntelligence), keyEquivalent: "i"))
        menu.addItem(NSMenuItem(title: "📡 Open Activity (Public)", action: #selector(openActivity), keyEquivalent: "a"))
        menu.addItem(NSMenuItem(title: "✅ Open Readiness (Public)", action: #selector(openReadiness), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "📋 Open PM Hub (Internal)", action: #selector(openPMHub), keyEquivalent: "p"))
        menu.addItem(NSMenuItem(title: "🗂️ Open AI PM Manager (Internal)", action: #selector(openAIProjectManager), keyEquivalent: "m"))

        menu.addItem(NSMenuItem.separator())

        let infraMenu = NSMenu(title: "Infra")
        infraMenu.addItem(NSMenuItem(title: "SSH RARI1", action: #selector(sshToRari1), keyEquivalent: ""))
        infraMenu.addItem(NSMenuItem(title: "SSH RARI2", action: #selector(sshToRari2), keyEquivalent: ""))
        infraMenu.addItem(NSMenuItem(title: "SSH Windows", action: #selector(sshToWindows), keyEquivalent: ""))
        let infraItem = NSMenuItem(title: "Infra", action: nil, keyEquivalent: "")
        infraItem.submenu = infraMenu
        menu.addItem(infraItem)

        let actionsMenu = NSMenu(title: "Actions")
        actionsMenu.addItem(NSMenuItem(title: "🔄 Refresh now", action: #selector(refreshNow), keyEquivalent: ""))
        actionsMenu.addItem(NSMenuItem(title: "🧾 Open Status JSON", action: #selector(openStatusJSON), keyEquivalent: ""))
        actionsMenu.addItem(NSMenuItem(title: "📜 Open Contracts JSON", action: #selector(openContractsJSON), keyEquivalent: ""))
        let actionsItem = NSMenuItem(title: "Actions", action: nil, keyEquivalent: "")
        actionsItem.submenu = actionsMenu
        menu.addItem(actionsItem)

        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
    }

    private func startMonitoring() {
        fetchStatus()

        timer = Timer.scheduledTimer(withTimeInterval: 30.0, repeats: true) { _ in
            self.fetchStatus()
        }

        $snapshot
            .receive(on: DispatchQueue.main)
            .sink { [weak self] snap in
                self?.updateUI(with: snap)
            }
            .store(in: &cancellables)
    }

    private func fetchStatus() {
        guard let url = URL(string: "\(baseURL)/api/platform/home-snapshot") else { return }
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let authHeader = basicAuthHeader() {
            request.setValue(authHeader, forHTTPHeaderField: "Authorization")
        }

        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard let self = self else { return }
            if let error {
                self.fetchStatusFallback(reason: error.localizedDescription)
                return
            }
            if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
                let reason = http.statusCode == 401
                    ? "Unauthorized (set SapphireOperatorUser/SapphireOperatorPassword)"
                    : "HTTP \(http.statusCode)"
                self.fetchStatusFallback(reason: reason)
                return
            }
            guard let data else { return }

            do {
                guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
                DispatchQueue.main.async {
                    self.parseSnapshot(json)
                }
            } catch {
                self.fetchStatusFallback(reason: error.localizedDescription)
            }
        }.resume()
    }

    private func fetchStatusFallback(reason: String) {
        let group = DispatchGroup()
        var statusJSON: [String: Any] = [:]
        var organizationJSON: [String: Any] = [:]
        var metricsJSON: [String: Any] = [:]

        func fetch(path: String, assign: @escaping ([String: Any]) -> Void) {
            guard let url = URL(string: "\(baseURL)\(path)") else { return }
            var request = URLRequest(url: url)
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            if let authHeader = basicAuthHeader() {
                request.setValue(authHeader, forHTTPHeaderField: "Authorization")
            }
            group.enter()
            URLSession.shared.dataTask(with: request) { data, response, _ in
                defer { group.leave() }
                guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),
                      let data,
                      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                else { return }
                assign(json)
            }.resume()
        }

        fetch(path: "/api/platform/status") { statusJSON = $0 }
        fetch(path: "/api/platform/organization") { organizationJSON = $0 }
        fetch(path: "/api/platform/metrics") { metricsJSON = $0 }

        group.notify(queue: .main) {
            if statusJSON.isEmpty && organizationJSON.isEmpty && metricsJSON.isEmpty {
                self.snapshot.errorMessage = reason
                self.snapshot.updatedAt = Date()
                return
            }

            var next = SystemSnapshot()
            let summary = statusJSON["summary"] as? [String: Any] ?? [:]
            let readiness = statusJSON["readiness"] as? [String: Any] ?? [:]
            let orgSummary = organizationJSON["summary"] as? [String: Any] ?? [:]
            let trading = metricsJSON["trading"] as? [String: Any] ?? [:]
            let market = metricsJSON["market"] as? [String: Any] ?? [:]

            next.healthyServices = self.intValue(summary["service_healthy"])
            next.totalServices = self.intValue(summary["service_total"])
            next.readinessOk = self.boolValue(readiness["overall_ok"])
            next.projects = self.intValue(orgSummary["tracked_projects"])
            next.workspaces = self.intValue(orgSummary["workspaces"])
            next.agentsOnline = self.intValue(orgSummary["agents_online"])
            next.agentsTotal = self.intValue(orgSummary["agents_total"])
            next.signals = self.intValue(trading["signals_total"])
            next.trades = self.intValue(trading["trades_count"])
            if let pnl = trading["pnl"] as? [String: Any] {
                next.pnl = self.doubleValue(pnl["total"])
            }
            if let btc = market["BTC"] as? [String: Any] {
                next.btcPrice = self.doubleValue(btc["price"])
            }
            next.latestActivity = "Snapshot fallback active"
            next.updatedAt = Date()
            next.errorMessage = ""
            self.snapshot = next
        }
    }

    private func parseSnapshot(_ json: [String: Any]) {
        let statusSummary = ((json["status"] as? [String: Any])?["summary"] as? [String: Any]) ?? [:]
        let readiness = json["readiness"] as? [String: Any] ?? [:]
        let orgSummary = ((json["organization"] as? [String: Any])?["summary"] as? [String: Any]) ?? [:]
        let metrics = json["metrics"] as? [String: Any] ?? [:]
        let trading = metrics["trading"] as? [String: Any] ?? [:]
        let market = metrics["market"] as? [String: Any] ?? [:]
        let projects = json["projects"] as? [String: Any] ?? [:]
        let logs = (json["logs"] as? [String: Any])?["logs"] as? [[String: Any]] ?? []

        var next = SystemSnapshot()
        next.healthyServices = intValue(statusSummary["service_healthy"])
        next.totalServices = intValue(statusSummary["service_total"])
        next.readinessOk = boolValue(readiness["overall_ok"])
        next.projects = intValue(projects["count"])
        next.workspaces = intValue(orgSummary["workspaces"])
        next.agentsOnline = intValue(orgSummary["agents_online"])
        next.agentsTotal = intValue(orgSummary["agents_total"])
        next.signals = intValue(trading["signals_total"])
        next.trades = intValue(trading["trades_count"])

        if let pnl = trading["pnl"] as? [String: Any] {
            next.pnl = doubleValue(pnl["total"])
        }
        if let btc = market["BTC"] as? [String: Any] {
            next.btcPrice = doubleValue(btc["price"])
        }

        if let log = logs.first {
            let msg = stringValue(log["message"])
            let symbol = stringValue(log["symbol"])
            let eventType = stringValue(log["event_type"])
            var line = msg.isEmpty ? "No activity yet" : msg
            if !symbol.isEmpty { line += " [\(symbol)]" }
            if !eventType.isEmpty { line += " (\(eventType))" }
            next.latestActivity = String(line.prefix(88))
        }

        next.updatedAt = Date()
        next.errorMessage = ""
        snapshot = next
    }

    private func updateUI(with snapshot: SystemSnapshot) {
        if !snapshot.errorMessage.isEmpty {
            statusItem.button?.title = "❌"
            (menu.item(withTag: 100))?.title = "Status: offline"
            (menu.item(withTag: 101))?.title = "PM: unavailable"
            (menu.item(withTag: 102))?.title = "Trading: unavailable"
            (menu.item(withTag: 103))?.title = "Activity: \(snapshot.errorMessage)"
            (menu.item(withTag: 104))?.title = "Updated: \(formattedTime(snapshot.updatedAt))"
            return
        }

        if snapshot.isHealthy {
            statusItem.button?.title = "💎"
        } else if snapshot.serviceRatio >= 0.7 {
            statusItem.button?.title = "💠"
        } else {
            statusItem.button?.title = "⚠️"
        }

        let readinessLabel = snapshot.readinessOk ? "GREEN" : "WATCH"
        (menu.item(withTag: 100))?.title = "Status: \(snapshot.healthyServices)/\(snapshot.totalServices) services | Readiness: \(readinessLabel)"
        (menu.item(withTag: 101))?.title = "PM: \(snapshot.projects) projects | \(snapshot.workspaces) workspaces | agents \(snapshot.agentsOnline)/\(snapshot.agentsTotal)"
        (menu.item(withTag: 102))?.title = String(format: "Trading: signals %d | trades %d | PnL $%.2f | BTC $%.0f", snapshot.signals, snapshot.trades, snapshot.pnl, snapshot.btcPrice)
        (menu.item(withTag: 103))?.title = "Activity: \(snapshot.latestActivity)"
        (menu.item(withTag: 104))?.title = "Updated: \(formattedTime(snapshot.updatedAt))"
    }

    private func intValue(_ value: Any?) -> Int {
        if let i = value as? Int { return i }
        if let d = value as? Double { return Int(d) }
        if let s = value as? String { return Int(s) ?? 0 }
        return 0
    }

    private func doubleValue(_ value: Any?) -> Double {
        if let d = value as? Double { return d }
        if let i = value as? Int { return Double(i) }
        if let s = value as? String { return Double(s) ?? 0 }
        return 0
    }

    private func boolValue(_ value: Any?) -> Bool {
        if let b = value as? Bool { return b }
        if let i = value as? Int { return i != 0 }
        if let s = value as? String { return ["1","true","yes","on"].contains(s.lowercased()) }
        return false
    }

    private func stringValue(_ value: Any?) -> String {
        if let s = value as? String { return s }
        return ""
    }

    private func formattedTime(_ date: Date?) -> String {
        guard let date else { return "never" }
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f.string(from: date)
    }

    // MARK: - Links

    @objc private func openDashboard() {
        openPublicPath("dashboard")
    }

    @objc private func openOrganization() {
        openPublicPath("organization")
    }

    @objc private func openIntelligence() {
        openPublicPath("intelligence")
    }

    @objc private func openActivity() {
        openPublicPath("activity")
    }

    @objc private func openReadiness() {
        openPublicPath("readiness")
    }

    @objc private func openPMHub() {
        openInternalURL("pmHubOrganization")
    }

    @objc private func openAIProjectManager() {
        openInternalURL("pmManager")
    }

    @objc private func openStatusJSON() {
        openPublicPath("statusJSON")
    }

    @objc private func openContractsJSON() {
        openPublicPath("contractsJSON")
    }

    private func openPublicPath(_ key: String) {
        guard let path = publicPaths[key] else { return }
        openURL("\(baseURL)\(path)")
    }

    private func openInternalURL(_ key: String) {
        guard let url = internalURLs[key] else { return }
        openURL(url)
    }

    private func openURL(_ urlString: String) {
        guard let url = URL(string: urlString) else { return }
        NSWorkspace.shared.open(url)
    }

    // MARK: - Infra

    @objc private func sshToRari1() {
        executeAppleScript("""
        tell application "Terminal"
            activate
            do script "ssh rari@100.120.191.1"
        end tell
        """)
    }

    @objc private func sshToRari2() {
        executeAppleScript("""
        tell application "Terminal"
            activate
            do script "ssh rari@100.87.225.89"
        end tell
        """)
    }

    @objc private func sshToWindows() {
        executeAppleScript("""
        tell application "Terminal"
            activate
            do script "ssh rari@100.71.10.48"
        end tell
        """)
    }

    @objc private func refreshNow() {
        fetchStatus()
    }

    private func executeAppleScript(_ script: String) {
        var error: NSDictionary?
        if let scriptObject = NSAppleScript(source: script) {
            scriptObject.executeAndReturnError(&error)
        }
    }

    private func basicAuthHeader() -> String? {
        let defaults = UserDefaults.standard
        let env = ProcessInfo.processInfo.environment
        let user =
            defaults.string(forKey: operatorUserDefaultsKey)
            ?? env["SAPPHIRE_OPERATOR_USER"]
            ?? ""
        let password =
            defaults.string(forKey: operatorPasswordDefaultsKey)
            ?? env["SAPPHIRE_OPERATOR_PASSWORD"]
            ?? ""
        if user.isEmpty || password.isEmpty {
            return nil
        }
        let token = Data("\(user):\(password)".utf8).base64EncodedString()
        return "Basic \(token)"
    }
}
