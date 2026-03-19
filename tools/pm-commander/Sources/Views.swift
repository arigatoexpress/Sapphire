import SwiftUI
import AppKit
import WebKit
import Foundation

private enum PMCommanderTab: Hashable {
    case overview
    case agents
    case queue
    case projects
    case organizationWeb
    case intelligenceWeb
    case platformWeb
    case activityWeb
    case sapphireBookWeb
}

struct ContentView: View {
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var dashboard: DashboardViewModel

    @State private var showingSettings = false
    @State private var selectedTab: PMCommanderTab = .overview

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.05, green: 0.08, blue: 0.13),
                    Color(red: 0.07, green: 0.12, blue: 0.20),
                    Color(red: 0.08, green: 0.16, blue: 0.28),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            Circle()
                .fill(Color.cyan.opacity(0.16))
                .frame(width: 520, height: 520)
                .blur(radius: 70)
                .offset(x: -280, y: -260)
                .allowsHitTesting(false)

            Circle()
                .fill(Color.blue.opacity(0.12))
                .frame(width: 420, height: 420)
                .blur(radius: 60)
                .offset(x: 300, y: -220)
                .allowsHitTesting(false)

            VStack(spacing: 0) {
                topBar
                TabView(selection: $selectedTab) {
                    overviewTab
                        .tag(PMCommanderTab.overview)
                        .tabItem { Label("Overview", systemImage: "rectangle.3.group.bubble") }

                    agentsTab
                        .tag(PMCommanderTab.agents)
                        .tabItem { Label("Agents", systemImage: "person.3.fill") }

                    queueTab
                        .tag(PMCommanderTab.queue)
                        .tabItem { Label("Queue", systemImage: "list.bullet.clipboard") }

                    projectsTab
                        .tag(PMCommanderTab.projects)
                        .tabItem { Label("Projects", systemImage: "folder.fill") }

                    webDashboardTab(
                        title: "Organization & Programs",
                        subtitle: "Unified operating model and client program portfolio.",
                        path: "/organization"
                    )
                    .tag(PMCommanderTab.organizationWeb)
                    .tabItem { Label("Organization", systemImage: "building.2.crop.circle") }

                    webDashboardTab(
                        title: "Market & Intelligence",
                        subtitle: "Consolidated market telemetry and research intelligence stream.",
                        path: "/intelligence"
                    )
                    .tag(PMCommanderTab.intelligenceWeb)
                    .tabItem { Label("Intelligence", systemImage: "chart.line.uptrend.xyaxis") }

                    webDashboardTab(
                        title: "Platform Reliability",
                        subtitle: "Cloud, edge, readiness, and contract reliability in one view.",
                        path: "/platform"
                    )
                    .tag(PMCommanderTab.platformWeb)
                    .tabItem { Label("Platform", systemImage: "heart.text.square") }

                    webDashboardTab(
                        title: "Activity Stream",
                        subtitle: "Unified timeline of system events, signals, and verified trades.",
                        path: "/activity"
                    )
                    .tag(PMCommanderTab.activityWeb)
                    .tabItem { Label("Activity", systemImage: "list.bullet.rectangle.portrait") }

                    webDashboardTab(
                        title: "Sapphire Book",
                        subtitle: "Operator strategy, playbooks, and roadmap surfaces.",
                        path: "/sapphire-book"
                    )
                    .tag(PMCommanderTab.sapphireBookWeb)
                    .tabItem { Label("Book", systemImage: "book.closed") }
                }
            }
            .padding(12)
        }
        .preferredColorScheme(.dark)
        .sheet(isPresented: $showingSettings) {
            SettingsSheet(isPresented: $showingSettings)
                .environmentObject(settings)
                .environmentObject(dashboard)
        }
    }

    private var topBar: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Sapphire Operator")
                    .font(.headline)
                    .fontWeight(.semibold)
                Text("Canonical platform: \(settings.platformBaseURL)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Group {
                if let platform = dashboard.platformStatus {
                    statusBadge(
                        label: "Cloud",
                        value: "\\(platform.summary.serviceHealthy)/\\(platform.summary.serviceTotal)",
                        color: platform.summary.serviceUnhealthy > 0 ? .orange : .green
                    )
                    statusBadge(
                        label: "Nodes",
                        value: "\\(platform.summary.nodeHealthy)/\\(platform.summary.nodeTotal)",
                        color: platform.summary.nodeUnhealthy > 0 ? .orange : .green
                    )
                }
                if let readiness = dashboard.platformReadiness {
                    statusBadge(
                        label: "Readiness",
                        value: readiness.overallOK ? "PASS" : "HOLD",
                        color: readiness.overallOK ? .green : .orange
                    )
                }
                if let contracts = dashboard.platformContracts {
                    let total = contracts.counts?.total ?? contracts.endpoints.count
                    statusBadge(
                        label: "Contracts",
                        value: "\(total) · \(contracts.version.uppercased())",
                        color: .mint
                    )
                }
                if let overview = dashboard.controlOverview {
                    let counts = overview.kpiTasks
                    statusBadge(
                        label: "Agents",
                        value: "\(overview.agentsOnline)/\(overview.agentsTotal)",
                        color: overview.agentsOnline > 0 ? .green : .red
                    )
                    statusBadge(label: "Queued", value: "\(counts.queued)", color: counts.queued > 0 ? .orange : .green)
                    statusBadge(label: "Leased", value: "\(counts.leased)", color: .blue)
                    statusBadge(label: "Failed", value: "\(counts.failed)", color: counts.failed > 0 ? .red : .green)
                    statusBadge(
                        label: "Review",
                        value: "\(counts.blockedReview)",
                        color: counts.blockedReview > 0 ? .orange : .green
                    )
                    if let slo = overview.slo {
                        statusBadge(
                            label: "SLO",
                            value: slo.status.uppercased(),
                            color: slo.status.lowercased() == "healthy" ? .green : .orange
                        )
                    }
                } else {
                    statusBadge(label: "Status", value: "Loading", color: .gray)
                }
            }

            Spacer()

            if let updated = dashboard.lastUpdated {
                Text("Updated \(updated.formatted(date: .omitted, time: .standard))")
                    .foregroundStyle(.secondary)
                    .font(.caption)
            }

            Menu {
                Button("Sync Board") {
                    Task { await dashboard.syncBoard(settings: settings) }
                }
                Button("Autonomy Cycle") {
                    Task { await dashboard.autonomyCycle(settings: settings) }
                }
                Button("Assistant Check-In") {
                    Task { await dashboard.assistantCheckin(settings: settings) }
                }
                Button("Refresh Quotas") {
                    Task { await dashboard.refreshQuotas(settings: settings) }
                }
                Button("Run Deep Research") {
                    Task { await dashboard.runDeepResearch(settings: settings) }
                }
            } label: {
                Label(dashboard.actionInFlight ? "Actions Running" : "Actions", systemImage: "bolt.circle")
            }
            .disabled(dashboard.actionInFlight)

            Button {
                Task {
                    await dashboard.refreshNow(settings: settings, reason: "manual")
                }
            } label: {
                Label(dashboard.isLoading ? "Refreshing" : "Refresh", systemImage: "arrow.clockwise")
            }
            .keyboardShortcut("r", modifiers: [.command])

            Button {
                showingSettings = true
            } label: {
                Label("Settings", systemImage: "gearshape")
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(Color.white.opacity(0.18), lineWidth: 1)
                )
        )
        .shadow(color: .black.opacity(0.25), radius: 20, x: 0, y: 10)
    }

    private var overviewTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                overviewNoticeSection
                overviewMetricsGrid
                overviewModeSection
                overviewSLOSection
                overviewQueueDiagnosticsSection
                overviewTaskSummarySection(title: "Failed Tasks", tasks: dashboard.failedTasks, empty: "No failed tasks.")
                overviewTaskSummarySection(title: "Blocked Review Tasks", tasks: dashboard.blockedReviewTasks, empty: "No blocked-review tasks.")
            }
            .padding(16)
        }
    }

    @ViewBuilder
    private var overviewNoticeSection: some View {
        if let error = dashboard.errorMessage {
            Text(error)
                .font(.callout)
                .foregroundStyle(.red)
                .padding(10)
                .glassSurface(tint: Color.red.opacity(0.08), stroke: Color.red.opacity(0.24), radius: 8)
        }

        if let action = dashboard.actionMessage, !action.isEmpty {
            Text(action)
                .font(.callout)
                .foregroundStyle(.blue)
                .padding(10)
                .glassSurface(tint: Color.blue.opacity(0.08), stroke: Color.blue.opacity(0.24), radius: 8)
        }

        if let routeNotice = dashboard.platformRouteNotice, !routeNotice.isEmpty {
            Text(routeNotice)
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(10)
                .glassSurface(radius: 8)
        }
    }

    private var overviewMetricsGrid: some View {
        let counts = dashboard.projectsOverview?.board?.counts
        let control = dashboard.controlOverview

        return LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 12)], spacing: 12) {
            metricCard(title: "Backlog", value: "\(counts?.backlog ?? 0)", tint: .orange)
            metricCard(title: "In Progress", value: "\(counts?.inProgress ?? 0)", tint: .blue)
            metricCard(title: "Blocked", value: "\(counts?.blocked ?? 0)", tint: .red)
            metricCard(title: "Done", value: "\(counts?.done ?? 0)", tint: .green)
            metricCard(title: "Tracked Projects", value: "\(dashboard.projectsOverview?.trackedProjects.count ?? 0)", tint: .purple)
            metricCard(title: "Queue (KPI)", value: "\(control?.kpiTasks.queued ?? 0)", tint: .orange)
            metricCard(title: "Failed (KPI)", value: "\(control?.kpiTasks.failed ?? 0)", tint: .red)
            metricCard(title: "Blocked Review", value: "\(control?.kpiTasks.blockedReview ?? 0)", tint: .yellow)
            metricCard(title: "Refresh Interval", value: "\(Int(settings.autoRefreshSeconds))s", tint: .gray)
        }
    }

    private var overviewModeSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Current Mode")
                .font(.headline)
            Text(dashboard.projectsOverview?.runtimeMode ?? "unknown")
                .font(.title3)
            Text("Last refresh reason: \(dashboard.refreshReason)")
                .foregroundStyle(.secondary)
                .font(.caption)
            if let control = dashboard.controlOverview {
                Text("Low-signal excluded from KPI: \(control.kpiExcludedLowSignal)")
                    .foregroundStyle(.secondary)
                    .font(.caption)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .glassSurface()
    }

    @ViewBuilder
    private var overviewSLOSection: some View {
        if let slo = dashboard.controlOverview?.slo {
            VStack(alignment: .leading, spacing: 8) {
                Text("SLO Telemetry")
                    .font(.headline)
                Text("status: \(slo.status)")
                    .font(.subheadline)
                Text("queue drain: \(slo.queueDrainTimeSeconds)s · stale lease rate: \(String(format: "%.2f", slo.staleLeaseRate)) · autocancel rate: \(String(format: "%.2f", slo.autocancelRate))")
                    .foregroundStyle(.secondary)
                    .font(.caption)
                if !slo.alerts.isEmpty {
                    ForEach(slo.alerts, id: \.self) { alert in
                        Text("• \(alert)")
                            .font(.caption)
                            .foregroundStyle(.orange)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .glassSurface(stroke: Color.orange.opacity(0.28))
        }
    }

    @ViewBuilder
    private var overviewQueueDiagnosticsSection: some View {
        if let ops = dashboard.opsInventory {
            let summary = ops.summary
            let queue = ops.queueRoutability
            let drift = ops.policyDrift

            VStack(alignment: .leading, spacing: 10) {
                Text("Queue Stall Diagnosis")
                    .font(.headline)
                if let summary {
                    Text(
                        "stall=\(summary.queueStallDetected ? "true" : "false") · top=\(summary.queueTopBlockerReason.isEmpty ? "none" : summary.queueTopBlockerReason)"
                    )
                    .font(.subheadline)
                    Text(
                        "queued=\(summary.tasksQueued) leased=\(summary.tasksLeased) failed=\(summary.tasksFailed) · routable=\(summary.queueRoutableCount) unroutable=\(summary.queueUnroutableCount)"
                    )
                    .foregroundStyle(.secondary)
                    .font(.caption)
                } else {
                    Text("Ops inventory summary unavailable.")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                }

                if let drift, drift.enabled {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Executor Policy Lock")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("drift=\(drift.driftDetected ? "true" : "false") · mismatches=\(drift.mismatches.count)")
                            .font(.caption)
                            .foregroundStyle(drift.driftDetected ? .orange : .green)
                        if let expected = drift.expected, !expected.mode.isEmpty {
                            Text("expected mode: \(expected.mode)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        if let observed = drift.observed, !observed.mode.isEmpty {
                            Text("observed mode: \(observed.mode)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                if let blockerRows = queue?.summary?.blockerBreakdown, !blockerRows.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Blocker Breakdown")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        ForEach(blockerRows.prefix(4)) { row in
                            Text("• \(row.reason): \(row.count)")
                                .font(.caption)
                        }
                    }
                }

                if let recommendations = queue?.recommendations, !recommendations.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Recovery Recommendations")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        ForEach(Array(recommendations.prefix(4).enumerated()), id: \.offset) { _, row in
                            Text("• [\(row.priority)] \(row.action)")
                                .font(.caption)
                        }
                    }
                }

                if let queuedRows = queue?.queuedTasks, !queuedRows.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Top Queued Tasks")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        ForEach(Array(queuedRows.prefix(3).enumerated()), id: \.element.id) { _, row in
                            let blockerText = row.blockerReasons.isEmpty ? "routable" : row.blockerReasons.joined(separator: ", ")
                            Text("• \(row.title) → \(blockerText)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .glassSurface(
                tint: (summary?.queueStallDetected ?? false)
                    ? Color.red.opacity(0.10)
                    : ((drift?.driftDetected ?? false) ? Color.orange.opacity(0.10) : Color.green.opacity(0.08)),
                stroke: (summary?.queueStallDetected ?? false)
                    ? Color.red.opacity(0.28)
                    : ((drift?.driftDetected ?? false) ? Color.orange.opacity(0.28) : Color.green.opacity(0.28))
            )
        }
    }

    private func overviewTaskSummarySection(title: String, tasks: [ControlTask], empty: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            if tasks.isEmpty {
                Text(empty)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(tasks.prefix(10)) { task in
                    taskRow(task)
                }
            }
        }
    }

    private var agentsTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Agent Fleet")
                    .font(.headline)

                if dashboard.agents.isEmpty {
                    Text("No agent telemetry available.")
                        .foregroundStyle(.secondary)
                        .padding(.top, 4)
                }

                ForEach(dashboard.agents) { agent in
                    HStack(alignment: .top, spacing: 10) {
                        Circle()
                            .fill(agent.isOnline ? Color.green : Color.gray)
                            .frame(width: 10, height: 10)
                            .padding(.top, 5)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(agent.name)
                                .font(.headline)
                            Text(agent.capabilities.joined(separator: ", "))
                                .foregroundStyle(.secondary)
                                .font(.caption)
                            Text("heartbeat age: \(agent.heartbeatAgeSeconds)s")
                                .foregroundStyle(.secondary)
                                .font(.caption)
                        }
                        Spacer()
                        Text(agent.status.uppercased())
                            .font(.caption)
                            .foregroundStyle(agent.isOnline ? .green : .secondary)
                    }
                    .padding(.vertical, 4)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 8)
                    .glassSurface()
                }
            }
            .padding(16)
        }
    }

    private var queueTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                taskSection(title: "Queued", tasks: dashboard.queuedTasks, emptyLabel: "No queued tasks.")
                taskSection(title: "Leased", tasks: dashboard.leasedTasks, emptyLabel: "No leased tasks.")
                taskSection(title: "Failed", tasks: dashboard.failedTasks, emptyLabel: "No failed tasks.")
                taskSection(title: "Blocked Review", tasks: dashboard.blockedReviewTasks, emptyLabel: "No blocked review tasks.")
            }
            .padding(16)
        }
    }

    private var projectsTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Tracked Projects")
                    .font(.headline)

                let projects = dashboard.projectsOverview?.trackedProjects ?? []
                if projects.isEmpty {
                    Text("No tracked projects found.")
                        .foregroundStyle(.secondary)
                        .padding(.top, 4)
                }

                ForEach(projects) { project in
                    HStack(alignment: .top, spacing: 12) {
                        Circle()
                            .fill(project.healthColor == "ok" ? Color.green : Color.orange)
                            .frame(width: 10, height: 10)
                            .padding(.top, 5)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(project.name)
                                .font(.headline)
                            Text(project.healthLabel)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            if let notes = project.notes, !notes.isEmpty {
                                Text(notes)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                    }
                    .padding(.vertical, 4)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 8)
                    .glassSurface(stroke: project.healthColor == "ok" ? Color.green.opacity(0.25) : Color.orange.opacity(0.25))
                }
            }
            .padding(16)
        }
    }

    private func webDashboardTab(title: String, subtitle: String, path: String) -> some View {
        PMWebDashboardTab(
            title: title,
            subtitle: subtitle,
            baseURL: settings.platformBaseURL,
            username: settings.platformUsername,
            password: settings.readPlatformPassword(),
            path: path
        )
    }

    private func statusBadge(label: String, value: String, color: Color) -> some View {
        HStack(spacing: 6) {
            Circle()
                .fill(color)
                .frame(width: 8, height: 8)
            Text("\(label): \(value)")
                .font(.caption)
                .fontWeight(.medium)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .stroke(color.opacity(0.35), lineWidth: 1)
                )
        )
    }

    private func metricCard(title: String, value: String, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .foregroundStyle(.secondary)
                .font(.caption)
            Text(value)
                .font(.title2)
                .fontWeight(.bold)
                .foregroundStyle(tint)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .glassSurface(stroke: tint.opacity(0.35))
    }

    private func taskSection(title: String, tasks: [ControlTask], emptyLabel: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            if tasks.isEmpty {
                Text(emptyLabel)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(tasks.prefix(20)) { task in
                    taskRow(task)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .glassSurface()
    }

    private func taskRow(_ task: ControlTask) -> some View {
        let statusColor: Color
        switch task.status {
        case "failed":
            statusColor = .red
        case "leased":
            statusColor = .blue
        case "blocked_review":
            statusColor = .orange
        default:
            statusColor = .orange
        }
        return HStack(alignment: .top, spacing: 10) {
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
                .padding(.top, 6)
            VStack(alignment: .leading, spacing: 4) {
                Text(task.title)
                    .font(.subheadline)
                Text(task.taskID)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if !task.requiredCapabilities.isEmpty {
                    Text(task.requiredCapabilities.joined(separator: ", "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 3) {
                Text(task.status)
                    .font(.caption)
                Text("p\(task.priority)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if let owner = task.leaseOwner, !owner.isEmpty {
                    Text(owner)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 2)
    }
}

private extension View {
    func glassSurface(
        tint: Color = Color.white.opacity(0.07),
        stroke: Color = Color.white.opacity(0.16),
        radius: CGFloat = 14
    ) -> some View {
        self.background(
            RoundedRectangle(cornerRadius: radius, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: radius, style: .continuous)
                        .fill(tint)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: radius, style: .continuous)
                        .stroke(stroke, lineWidth: 1)
                )
                .shadow(color: .black.opacity(0.20), radius: 16, x: 0, y: 8)
        )
    }
}

struct SettingsSheet: View {
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var dashboard: DashboardViewModel

    @Binding var isPresented: Bool
    @State private var tokenInput = ""
    @State private var localBaseURL = ""
    @State private var localPlatformBaseURL = ""
    @State private var localPlatformUsername = ""
    @State private var localPlatformPassword = ""
    @State private var localRefresh: Double = 30
    @State private var feedbackMessage = ""
    @State private var pendingClearTarget: ClearTarget?

    private enum ClearTarget {
        case controlToken
        case platformPassword
        case both

        var title: String {
            switch self {
            case .controlToken:
                return "Clear control token?"
            case .platformPassword:
                return "Clear platform password?"
            case .both:
                return "Clear both credentials?"
            }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Sapphire Operator Settings")
                .font(.title3)
                .fontWeight(.semibold)

            VStack(alignment: .leading, spacing: 10) {
                Text("Control Plane")
                    .font(.headline)
                TextField("Control plane URL (PM Hub APIs)", text: $localBaseURL)
                    .textFieldStyle(.roundedBorder)
                SecureField("Control plane token", text: $tokenInput)
                    .textFieldStyle(.roundedBorder)
                Text(settings.hasToken ? "Control token is stored in Keychain." : "No control token stored.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding(12)
            .glassSurface(radius: 12)

            Divider()

            VStack(alignment: .leading, spacing: 10) {
                Text("Platform")
                    .font(.headline)
                TextField("Platform URL (Unified Frontend)", text: $localPlatformBaseURL)
                    .textFieldStyle(.roundedBorder)
                Text("Canonical platform is https://sapphirealpha.xyz. Deprecated hosts auto-migrate.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                TextField("Platform username", text: $localPlatformUsername)
                    .textFieldStyle(.roundedBorder)
                SecureField("Platform password", text: $localPlatformPassword)
                    .textFieldStyle(.roundedBorder)
                Text(settings.hasPlatformPassword ? "Platform password is stored in Keychain." : "No platform password stored.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding(12)
            .glassSurface(radius: 12)

            HStack(spacing: 10) {
                Label(settings.isPlatformBaseURLCanonical ? "Canonical route active" : "Custom route active", systemImage: settings.isPlatformBaseURLCanonical ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                    .foregroundStyle(settings.isPlatformBaseURLCanonical ? Color.green : Color.orange)
                    .font(.caption)
                Spacer()
                Text("Refresh every \(Int(localRefresh))s")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 4)

            HStack {
                Text("Auto refresh")
                Slider(value: $localRefresh, in: 15...300, step: 5)
                Text("\(Int(localRefresh))s")
                    .frame(width: 52, alignment: .trailing)
            }

            if !feedbackMessage.isEmpty {
                Text(feedbackMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            HStack {
                Button("Clear Control Token", role: .destructive) {
                    pendingClearTarget = .controlToken
                }

                Button("Clear Platform Password", role: .destructive) {
                    pendingClearTarget = .platformPassword
                }

                Button("Clear Both", role: .destructive) {
                    pendingClearTarget = .both
                }

                Button("Use Canonical URLs") {
                    settings.resetURLsToCanonicalDefaults()
                    localBaseURL = settings.baseURL
                    localPlatformBaseURL = settings.platformBaseURL
                    feedbackMessage = "Reset to canonical platform URLs."
                }

                Button("Test Connection") {
                    Task {
                        await dashboard.refreshNow(settings: settings, reason: "settings_test_connection")
                    }
                    feedbackMessage = "Connection test triggered."
                }

                Spacer()

                Button("Cancel") {
                    isPresented = false
                }

                Button("Save") {
                    settings.baseURL = localBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
                    settings.platformBaseURL = localPlatformBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
                    settings.platformUsername = localPlatformUsername.trimmingCharacters(in: .whitespacesAndNewlines)
                    settings.autoRefreshSeconds = localRefresh
                    do {
                        try settings.saveToken(tokenInput)
                        try settings.savePlatformPassword(localPlatformPassword)
                        dashboard.resetRefreshTimer(settings: settings)
                        Task {
                            await dashboard.refreshNow(settings: settings, reason: "settings_saved")
                        }
                        isPresented = false
                    } catch {
                        feedbackMessage = error.localizedDescription
                    }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(18)
        .frame(minWidth: 620, minHeight: 360)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(Color.white.opacity(0.18), lineWidth: 1)
                )
        )
        .onAppear {
            localBaseURL = settings.baseURL
            localPlatformBaseURL = settings.platformBaseURL
            localPlatformUsername = settings.platformUsername
            localPlatformPassword = settings.readPlatformPassword()
            localRefresh = settings.autoRefreshSeconds
            tokenInput = settings.readToken()
            feedbackMessage = settings.hasToken ? "Control token loaded from Keychain." : "No control token stored yet."
        }
        .confirmationDialog(
            pendingClearTarget?.title ?? "Clear credentials?",
            isPresented: Binding(
                get: { pendingClearTarget != nil },
                set: { if !$0 { pendingClearTarget = nil } }
            )
        ) {
            Button("Confirm Clear", role: .destructive) {
                clearPendingCredential()
            }
            Button("Cancel", role: .cancel) {
                pendingClearTarget = nil
            }
        } message: {
            Text("This removes saved credentials from macOS Keychain.")
        }
    }

    private func clearPendingCredential() {
        guard let target = pendingClearTarget else { return }
        do {
            switch target {
            case .controlToken:
                try settings.clearToken()
                tokenInput = ""
                feedbackMessage = "Control token cleared."
            case .platformPassword:
                try settings.clearPlatformPassword()
                localPlatformPassword = ""
                feedbackMessage = "Platform password cleared."
            case .both:
                try settings.clearToken()
                try settings.clearPlatformPassword()
                tokenInput = ""
                localPlatformPassword = ""
                feedbackMessage = "Both credentials cleared."
            }
        } catch {
            feedbackMessage = error.localizedDescription
        }
        pendingClearTarget = nil
    }
}

private struct PMWebDashboardTab: View {
    let title: String
    let subtitle: String
    let baseURL: String
    let username: String
    let password: String
    let path: String

    @State private var reloadToken = UUID()

    private static let deprecatedPathMap: [String: String] = [
        "/trading": "/intelligence",
        "/feed": "/intelligence",
        "/autonomy": "/platform",
        "/command-deck": "/platform",
        "/system-health": "/platform",
        "/infrastructure": "/platform",
        "/production-readiness": "/platform",
        "/logs": "/activity",
        "/projects": "/organization#programs",
        "/api/status": "/api/platform/status",
        "/api/logs": "/api/platform/logs",
        "/api/trades": "/api/platform/trades",
    ]

    private var canonicalPath: String {
        PMWebDashboardTab.deprecatedPathMap[path, default: path]
    }

    private var resolvedURL: URL? {
        let trimmed = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let base = URL(string: trimmed), base.scheme != nil else {
            return nil
        }
        guard let url = URL(string: canonicalPath, relativeTo: base)?.absoluteURL else {
            return nil
        }
        return url
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.headline)
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if let url = resolvedURL {
                    Button("Open in Browser") {
                        NSWorkspace.shared.open(url)
                    }
                    Button {
                        reloadToken = UUID()
                    } label: {
                        Label("Reload", systemImage: "arrow.clockwise")
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .stroke(Color.white.opacity(0.18), lineWidth: 1)
                    )
            )

            if let url = resolvedURL {
                PMWebView(url: url, username: username, password: password)
                    .id(reloadToken)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.largeTitle)
                        .foregroundStyle(.orange)
                    Text("Invalid platform URL")
                        .font(.headline)
                    Text("Open Settings and set a valid HTTPS platform URL.")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color.white.opacity(0.04))
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(Color.white.opacity(0.14), lineWidth: 1)
                )
        )
    }
}

private struct PMWebView: NSViewRepresentable {
    let url: URL
    let username: String
    let password: String

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.preferredContentMode = .desktop
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.setValue(false, forKey: "drawsBackground")
        webView.customUserAgent = "SapphireOperatorClient/1.0 (macOS)"
        context.coordinator.username = username
        context.coordinator.password = password
        webView.navigationDelegate = context.coordinator
        webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30))
        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {
        context.coordinator.username = username
        context.coordinator.password = password
        if nsView.url?.absoluteString != url.absoluteString {
            nsView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30))
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var username: String = ""
        var password: String = ""

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            print("PMWebView navigation failed: \(error.localizedDescription)")
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            print("PMWebView provisional navigation failed: \(error.localizedDescription)")
        }

        func webView(
            _ webView: WKWebView,
            didReceive challenge: URLAuthenticationChallenge,
            completionHandler: @escaping @MainActor @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
        ) {
            guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodHTTPBasic else {
                completionHandler(.performDefaultHandling, nil)
                return
            }
            guard !username.isEmpty, !password.isEmpty else {
                completionHandler(.performDefaultHandling, nil)
                return
            }
            let credential = URLCredential(user: username, password: password, persistence: .forSession)
            completionHandler(.useCredential, credential)
        }
    }
}
