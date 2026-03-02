import SwiftUI
import Combine

class StatusBarController: NSObject, ObservableObject {
    var statusItem: NSStatusItem
    var menu: NSMenu
    
    @Published var systemStatus: SystemStatus = SystemStatus()
    private var cancellables = Set<AnyCancellable>()
    private var timer: Timer?
    
    struct SystemStatus {
        var healthyServices: Int = 0
        var totalServices: Int = 0
        var pmProjects: Int = 0
        var activeSignals: Int = 0
        var btcPrice: Double = 0
        var lastUpdate: Date?
        
        var isHealthy: Bool {
            return totalServices > 0 && healthyServices == totalServices
        }
    }
    
    override init() {
        statusItem = NSStatusBar.shared.statusItem(withLength: NSStatusItem.variableLength)
        menu = NSMenu()
        
        super.init()
        
        setupMenuBar()
        startMonitoring()
    }
    
    func setupMenuBar() {
        // Set initial icon
        statusItem.button?.title = "💎"
        statusItem.menu = menu
        
        buildMenu()
    }
    
    func buildMenu() {
        menu.removeAllItems()
        
        // Status section
        let statusItem = NSMenuItem(title: "Status: Loading...", action: nil, keyEquivalent: "")
        statusItem.tag = 100
        menu.addItem(statusItem)
        
        let pmItem = NSMenuItem(title: "📊 PM: Loading...", action: nil, keyEquivalent: "")
        pmItem.tag = 101
        menu.addItem(pmItem)
        
        let signalsItem = NSMenuItem(title: "📡 Signals: Loading...", action: nil, keyEquivalent: "")
        signalsItem.tag = 102
        menu.addItem(signalsItem)
        
        let pricesItem = NSMenuItem(title: "💰 Prices: Loading...", action: nil, keyEquivalent: "")
        pricesItem.tag = 103
        menu.addItem(pricesItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // Quick Actions
        menu.addItem(NSMenuItem(title: "🌐 Open Dashboard", action: #selector(openDashboard), keyEquivalent: "d"))
        menu.addItem(NSMenuItem(title: "📋 Open PM Hub", action: #selector(openPMHub), keyEquivalent: "p"))
        
        menu.addItem(NSMenuItem.separator())
        
        // SSH submenu
        let sshMenu = NSMenu(title: "SSH")
        sshMenu.addItem(NSMenuItem(title: "🔧 SSH to RARI1", action: #selector(sshToRari1), keyEquivalent: ""))
        sshMenu.addItem(NSMenuItem(title: "⚡ SSH to RARI2", action: #selector(sshToRari2), keyEquivalent: ""))
        let sshItem = NSMenuItem(title: "SSH", action: nil, keyEquivalent: "")
        sshItem.submenu = sshMenu
        menu.addItem(sshItem)
        
        // Actions submenu
        let actionsMenu = NSMenu(title: "Actions")
        actionsMenu.addItem(NSMenuItem(title: "🔄 Refresh Now", action: #selector(refreshNow), keyEquivalent: "r"))
        actionsMenu.addItem(NSMenuItem(title: "📄 View Logs", action: #selector(viewLogs), keyEquivalent: "l"))
        let actionsItem = NSMenuItem(title: "Actions", action: nil, keyEquivalent: "")
        actionsItem.submenu = actionsMenu
        menu.addItem(actionsItem)
        
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
    }
    
    func startMonitoring() {
        // Initial fetch
        fetchStatus()
        
        // Set up timer for periodic updates
        timer = Timer.scheduledTimer(withTimeInterval: 30.0, repeats: true) { _ in
            self.fetchStatus()
        }
        
        // Subscribe to status changes to update UI
        $systemStatus
            .receive(on: DispatchQueue.main)
            .sink { [weak self] status in
                self?.updateUI(with: status)
            }
            .store(in: &cancellables)
    }
    
    func fetchStatus() {
        guard let url = URL(string: "https://sapphirealpha.xyz/api/status") else { return }
        
        URLSession.shared.dataTask(with: url) { [weak self] data, response, error in
            guard let self = self, let data = data else { return }
            
            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    DispatchQueue.main.async {
                        self.parseStatus(json)
                    }
                }
            } catch {
                print("Error parsing status: \(error)")
            }
        }.resume()
        
        // Also fetch PM projects
        fetchPMProjects()
        fetchTradingMetrics()
        fetchPrices()
    }
    
    func parseStatus(_ json: [String: Any]) {
        guard let byCategory = json["by_category"] as? [String: [[String: Any]]] else { return }
        
        var healthy = 0
        var total = 0
        
        for (_, services) in byCategory {
            for service in services {
                total += 1
                if service["healthy"] as? Bool == true {
                    healthy += 1
                }
            }
        }
        
        systemStatus.healthyServices = healthy
        systemStatus.totalServices = total
        systemStatus.lastUpdate = Date()
    }
    
    func fetchPMProjects() {
        guard let url = URL(string: "https://sapphirealpha.xyz/api/projects") else { return }
        
        URLSession.shared.dataTask(with: url) { [weak self] data, _, _ in
            guard let self = self, let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let count = json["count"] as? Int else { return }
            
            DispatchQueue.main.async {
                self.systemStatus.pmProjects = count
            }
        }.resume()
    }
    
    func fetchTradingMetrics() {
        guard let url = URL(string: "https://sapphirealpha.xyz/api/trading/metrics") else { return }
        
        URLSession.shared.dataTask(with: url) { [weak self] data, _, _ in
            guard let self = self, let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
            
            DispatchQueue.main.async {
                self.systemStatus.activeSignals = json["active_signals"] as? Int ?? 0
            }
        }.resume()
    }
    
    func fetchPrices() {
        guard let url = URL(string: "https://sapphirealpha.xyz/api/market/prices") else { return }
        
        URLSession.shared.dataTask(with: url) { [weak self] data, _, _ in
            guard let self = self, let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let btc = json["BTC"] as? [String: Double] else { return }
            
            DispatchQueue.main.async {
                self.systemStatus.btcPrice = btc["price"] ?? 0
            }
        }.resume()
    }
    
    func updateUI(with status: SystemStatus) {
        // Update menu bar icon based on health
        if status.isHealthy {
            statusItem.button?.title = "💎"
        } else if status.totalServices > 0 {
            let ratio = Double(status.healthyServices) / Double(status.totalServices)
            if ratio > 0.7 {
                statusItem.button?.title = "💠"
            } else {
                statusItem.button?.title = "⚠️"
            }
        } else {
            statusItem.button?.title = "❌"
        }
        
        // Update menu items
        if let item = menu.item(withTag: 100) {
            item.title = "Status: \(status.healthyServices)/\(status.totalServices) healthy"
        }
        if let item = menu.item(withTag: 101) {
            item.title = "📊 PM: \(status.pmProjects) projects"
        }
        if let item = menu.item(withTag: 102) {
            item.title = "📡 Signals: \(status.activeSignals) active"
        }
        if let item = menu.item(withTag: 103) {
            item.title = String(format: "💰 BTC: $%.0f", status.btcPrice)
        }
    }
    
    // MARK: - Actions
    
    @objc func openDashboard() {
        NSWorkspace.shared.open(URL(string: "https://sapphirealpha.xyz")!)
    }
    
    @objc func openPMHub() {
        NSWorkspace.shared.open(URL(string: "https://agentic-pm-hub-267358751314.us-central1.run.app")!)
    }
    
    @objc func sshToRari1() {
        executeAppleScript("""
        tell application "Terminal"
            activate
            do script "ssh rari@100.120.191.1"
        end tell
        """)
    }
    
    @objc func sshToRari2() {
        executeAppleScript("""
        tell application "Terminal"
            activate
            do script "ssh rari@100.87.225.89"
        end tell
        """)
    }
    
    @objc func refreshNow() {
        fetchStatus()
    }
    
    @objc func viewLogs() {
        NSWorkspace.shared.open(URL(string: "https://sapphirealpha.xyz/api/logs?limit=50")!)
    }
    
    func executeAppleScript(_ script: String) {
        var error: NSDictionary?
        if let scriptObject = NSAppleScript(source: script) {
            scriptObject.executeAndReturnError(&error)
        }
    }
}
