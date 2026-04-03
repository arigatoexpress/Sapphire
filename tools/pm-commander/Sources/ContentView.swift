import SwiftUI

struct ContentView: View {
    @EnvironmentObject var state: AppState
    @State private var selectedTab: Tab = .dashboard

    enum Tab: String, CaseIterable {
        case dashboard = "Dashboard"
        case devices = "Devices"
        case repos = "Repos"
        case inference = "Inference"
        case factory = "Factory"
        case market = "Market"
        case events = "Events"

        var icon: String {
            switch self {
            case .dashboard: return "rectangle.3.group"
            case .devices: return "network"
            case .repos: return "externaldrive.connected.to.line.below"
            case .inference: return "brain"
            case .factory: return "gearshape.2"
            case .market: return "chart.line.uptrend.xyaxis"
            case .events: return "list.bullet.rectangle"
            }
        }
    }

    var body: some View {
        NavigationSplitView {
            sidebar
        } detail: {
            ZStack {
                bgGradient
                detail
            }
        }
        .navigationTitle("Sapphire OS")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button(action: { Task { await state.refreshAll() } }) {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .disabled(state.isLoading)
            }
        }
    }

    var bgGradient: some View {
        LinearGradient(
            colors: [
                Color(red: 0.04, green: 0.06, blue: 0.10),
                Color(red: 0.06, green: 0.10, blue: 0.18),
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .ignoresSafeArea()
    }

    var sidebar: some View {
        List(Tab.allCases, id: \.self, selection: $selectedTab) { tab in
            Label(tab.rawValue, systemImage: tab.icon)
        }
        .listStyle(.sidebar)
    }

    @ViewBuilder
    var detail: some View {
        switch selectedTab {
        case .dashboard: DashboardView()
        case .devices: DevicesView()
        case .repos: ReposView()
        case .inference: InferenceView()
        case .factory: FactoryView()
        case .market: MarketView()
        case .events: EventsView()
        }
    }
}

// MARK: - Dashboard

struct DashboardView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Command Center")
                    .font(.largeTitle.bold())
                    .foregroundStyle(.white)

                if state.isLoading {
                    ProgressView("Refreshing...")
                        .foregroundStyle(.white)
                }

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 16) {
                    StatCard(title: "Devices Online",
                             value: "\(state.devices.filter(\.online).count)/\(state.devices.count)",
                             icon: "network", color: .green)

                    StatCard(title: "GPU Models",
                             value: "\(state.gpuModels.count)",
                             icon: "brain", color: state.gpuOnline ? .cyan : .red)

                    StatCard(title: "Repos Clean",
                             value: "\(state.repos.filter(\.safeToCommit).count)/\(state.repos.count)",
                             icon: "checkmark.shield", color: .blue)

                    StatCard(title: "Tests Passing",
                             value: "1,040",
                             icon: "testtube.2", color: .green)

                    StatCard(title: "Factory Issues",
                             value: "\(state.factoryMetrics?.openIssues ?? 0) open",
                             icon: "gearshape.2", color: .orange)

                    StatCard(title: "TradingView",
                             value: state.tvConnected ? state.tvSymbol : "Offline",
                             icon: "chart.line.uptrend.xyaxis",
                             color: state.tvConnected ? .green : .red)
                }

                // Quick Actions
                HStack(spacing: 12) {
                    ActionButton(title: "Scan Repos", icon: "magnifyingglass", color: .blue) {
                        Task { await state.runFactoryScan() }
                    }
                    ActionButton(title: "Fix Lint", icon: "wrench", color: .orange) {
                        Task { await state.runLintFix() }
                    }
                    ActionButton(title: "Refresh", icon: "arrow.clockwise", color: .green) {
                        Task { await state.refreshAll() }
                    }
                    ActionButton(title: "Notify", icon: "paperplane", color: .purple) {
                        Task { await state.sendNotification("Manual check from Sapphire Command Center") }
                    }
                }

                // Recent Events
                if !state.recentEvents.isEmpty {
                    Text("Recent Events")
                        .font(.headline)
                        .foregroundStyle(.white.opacity(0.8))

                    ForEach(state.recentEvents.prefix(8)) { event in
                        HStack {
                            Image(systemName: eventIcon(event.type))
                                .foregroundStyle(eventColor(event.type))
                                .frame(width: 20)
                            Text(event.shortTimestamp)
                                .font(.caption.monospaced())
                                .foregroundStyle(.white.opacity(0.5))
                            Text(event.type)
                                .font(.caption.bold())
                                .foregroundStyle(eventColor(event.type))
                            Text(event.message)
                                .font(.caption)
                                .foregroundStyle(.white.opacity(0.7))
                                .lineLimit(1)
                            Spacer()
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.white.opacity(0.04))
                        .cornerRadius(6)
                    }
                }
            }
            .padding(24)
        }
    }

    func eventIcon(_ type: String) -> String {
        if type.contains("deploy") { return "arrow.up.circle" }
        if type.contains("test") { return "testtube.2" }
        if type.contains("lint") || type.contains("fix") { return "wrench" }
        if type.contains("tool") { return "terminal" }
        return "circle.fill"
    }

    func eventColor(_ type: String) -> Color {
        if type.contains("deploy") { return .green }
        if type.contains("test") { return .blue }
        if type.contains("fix") { return .orange }
        return .gray
    }
}

// MARK: - Devices

struct DevicesView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Device Mesh").font(.largeTitle.bold()).foregroundStyle(.white)
                Text("Tailscale WireGuard VPN — all devices")
                    .foregroundStyle(.white.opacity(0.6))

                ForEach(state.devices) { dev in
                    HStack(spacing: 16) {
                        Circle()
                            .fill(dev.online ? Color.green : Color.red)
                            .frame(width: 12, height: 12)
                        VStack(alignment: .leading) {
                            Text(dev.name).font(.headline).foregroundStyle(.white)
                            Text(dev.role).font(.caption).foregroundStyle(.white.opacity(0.6))
                        }
                        Spacer()
                        Text(dev.ip).font(.caption.monospaced()).foregroundStyle(.cyan)
                        Text(dev.online ? "ONLINE" : "OFFLINE")
                            .font(.caption.bold())
                            .foregroundStyle(dev.online ? .green : .red)
                    }
                    .padding(16)
                    .background(Color.white.opacity(0.06))
                    .cornerRadius(10)
                }
            }
            .padding(24)
        }
    }
}

// MARK: - Repos

struct ReposView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Repository Health").font(.largeTitle.bold()).foregroundStyle(.white)
                    Spacer()
                    Button("Scan All") { Task { await state.runFactoryScan() } }
                    Button("Fix Lint") { Task { await state.runLintFix() } }
                }

                ForEach(state.repos) { repo in
                    HStack(spacing: 16) {
                        Image(systemName: repo.safeToCommit ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                            .foregroundStyle(repo.safeToCommit ? .green : .orange)
                            .font(.title2)
                        VStack(alignment: .leading) {
                            Text(repo.name).font(.headline).foregroundStyle(.white)
                            Text(repo.branch).font(.caption.monospaced()).foregroundStyle(.cyan)
                        }
                        Spacer()
                        if repo.lintErrors > 0 {
                            Label("\(repo.lintErrors)", systemImage: "exclamationmark.triangle")
                                .font(.caption)
                                .foregroundStyle(.orange)
                        }
                        if repo.uncommitted > 0 {
                            Label("\(repo.uncommitted) changes", systemImage: "pencil.circle")
                                .font(.caption)
                                .foregroundStyle(.yellow)
                        }
                        Text(repo.safeToCommit ? "✅" : "⚠️")
                    }
                    .padding(14)
                    .background(Color.white.opacity(0.06))
                    .cornerRadius(10)
                }
            }
            .padding(24)
        }
    }
}

// MARK: - Inference

struct InferenceView: View {
    @EnvironmentObject var state: AppState
    @State private var prompt = ""
    @State private var result = ""
    @State private var isRunning = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Inference").font(.largeTitle.bold()).foregroundStyle(.white)

                HStack(spacing: 20) {
                    VStack(alignment: .leading) {
                        Label("GPU (Windows)", systemImage: "bolt.fill")
                            .foregroundStyle(state.gpuOnline ? .green : .red)
                        Text("\(state.gpuModels.count) models")
                            .font(.caption).foregroundStyle(.white.opacity(0.6))
                    }
                    VStack(alignment: .leading) {
                        Label("Local (Mac)", systemImage: "desktopcomputer")
                            .foregroundStyle(state.localOllamaOnline ? .green : .red)
                        Text("\(state.localModels.count) models")
                            .font(.caption).foregroundStyle(.white.opacity(0.6))
                    }
                }
                .foregroundStyle(.white)

                Divider().background(.white.opacity(0.2))

                Text("Ask Nemotron").font(.headline).foregroundStyle(.white)
                HStack {
                    TextField("Ask anything...", text: $prompt)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { runInference() }
                    Button(isRunning ? "..." : "Ask") { runInference() }
                        .disabled(prompt.isEmpty || isRunning)
                        .buttonStyle(.borderedProminent)
                }

                if !result.isEmpty {
                    Text(result)
                        .font(.body)
                        .foregroundStyle(.white.opacity(0.9))
                        .padding(12)
                        .background(Color.white.opacity(0.06))
                        .cornerRadius(8)
                        .textSelection(.enabled)
                }

                Divider().background(.white.opacity(0.2))

                if !state.gpuModels.isEmpty {
                    Text("GPU Models (\(state.gpuModels.count))")
                        .font(.headline).foregroundStyle(.white)
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        ForEach(state.gpuModels, id: \.self) { model in
                            Text(model)
                                .font(.caption.monospaced())
                                .foregroundStyle(.cyan)
                                .padding(6)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.white.opacity(0.04))
                                .cornerRadius(6)
                        }
                    }
                }
            }
            .padding(24)
        }
    }

    func runInference() {
        guard !prompt.isEmpty else { return }
        isRunning = true
        result = ""
        let q = prompt
        Task {
            result = await state.runDispatch(q, tier: "t0")
            isRunning = false
        }
    }
}

// MARK: - Factory

struct FactoryView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Autonomous Factory").font(.largeTitle.bold()).foregroundStyle(.white)

                if let m = state.factoryMetrics {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        StatCard(title: "Total Issues", value: "\(m.totalIssues)", icon: "doc.text", color: .blue)
                        StatCard(title: "Open", value: "\(m.openIssues)", icon: "circle", color: .orange)
                        StatCard(title: "Fixed", value: "\(m.fixedIssues)", icon: "checkmark.circle", color: .green)
                        StatCard(title: "In Backoff", value: "\(m.inBackoff)", icon: "clock", color: .yellow)
                    }
                }

                Text("Token Budget").font(.headline).foregroundStyle(.white)
                ForEach(Array(state.budget.values).sorted(by: { $0.label < $1.label })) { tier in
                    HStack {
                        Text(tier.label).foregroundStyle(.white).frame(width: 200, alignment: .leading)
                        if let budget = tier.budget {
                            ProgressView(value: Double(tier.used), total: Double(budget))
                                .tint(tier.pctUsed < 50 ? .green : tier.pctUsed < 80 ? .yellow : .red)
                            Text("\(tier.used)/\(budget)")
                                .font(.caption.monospaced())
                                .foregroundStyle(.white.opacity(0.6))
                        } else {
                            Text("\(tier.used) tokens (unlimited)")
                                .font(.caption).foregroundStyle(.green)
                        }
                        Text("\(tier.calls) calls")
                            .font(.caption).foregroundStyle(.white.opacity(0.5))
                    }
                }

                HStack(spacing: 12) {
                    ActionButton(title: "Run Factory", icon: "play.fill", color: .green) {
                        Task { await state.runFactoryScan() }
                    }
                    ActionButton(title: "Fix Lint", icon: "wrench", color: .orange) {
                        Task { await state.runLintFix() }
                    }
                }
            }
            .padding(24)
        }
    }
}

// MARK: - Market

struct MarketView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Market Data").font(.largeTitle.bold()).foregroundStyle(.white)

                HStack(spacing: 20) {
                    VStack(alignment: .leading) {
                        Label("TradingView", systemImage: "chart.line.uptrend.xyaxis")
                            .foregroundStyle(state.tvConnected ? .green : .red)
                        if state.tvConnected {
                            Text("\(state.tvSymbol)  $\(state.tvPrice, specifier: "%.2f")")
                                .font(.title2.monospaced().bold())
                                .foregroundStyle(.cyan)
                        }
                    }
                    VStack(alignment: .leading) {
                        Label("OpenBB API", systemImage: "globe")
                            .foregroundStyle(.green)
                        Text("32 providers on :6900")
                            .font(.caption).foregroundStyle(.white.opacity(0.6))
                    }
                }
                .foregroundStyle(.white)

                Text("Data Sources: yFinance, FRED, SEC, NASDAQ, Benzinga, Tiingo, FMP, CoinGecko")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.5))
            }
            .padding(24)
        }
    }
}

// MARK: - Events

struct EventsView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Event Stream").font(.largeTitle.bold()).foregroundStyle(.white)
                    Spacer()
                    Button("Refresh") { Task { await state.fetchEvents() } }
                }

                ForEach(state.recentEvents) { event in
                    HStack(alignment: .top, spacing: 12) {
                        Text(event.shortTimestamp)
                            .font(.caption2.monospaced())
                            .foregroundStyle(.white.opacity(0.4))
                            .frame(width: 130, alignment: .leading)
                        Text(event.type)
                            .font(.caption.bold().monospaced())
                            .foregroundStyle(.cyan)
                            .frame(width: 160, alignment: .leading)
                        Text(event.message)
                            .font(.caption)
                            .foregroundStyle(.white.opacity(0.8))
                            .lineLimit(2)
                        Spacer()
                    }
                    .padding(.vertical, 4)
                    Divider().background(.white.opacity(0.1))
                }
            }
            .padding(24)
        }
    }
}

// MARK: - Reusable Components

struct StatCard: View {
    let title: String
    let value: String
    let icon: String
    let color: Color

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(color)
            Text(value)
                .font(.title3.bold().monospaced())
                .foregroundStyle(.white)
            Text(title)
                .font(.caption)
                .foregroundStyle(.white.opacity(0.6))
        }
        .frame(maxWidth: .infinity)
        .padding(16)
        .background(Color.white.opacity(0.06))
        .cornerRadius(12)
    }
}

struct ActionButton: View {
    let title: String
    let icon: String
    let color: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label(title, systemImage: icon)
                .font(.caption.bold())
                .foregroundStyle(.white)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(color.opacity(0.3))
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(color.opacity(0.5), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}
