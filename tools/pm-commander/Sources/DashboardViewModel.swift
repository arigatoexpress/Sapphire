import Foundation

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published var controlOverview: ControlOverviewResponse?
    @Published var executorPolicy: ExecutorPolicyResponse?
    @Published var projectsOverview: ProjectsOverviewResponse?
    @Published var opsInventory: OpsInventoryResponse?
    @Published var agents: [AgentRecord] = []
    @Published var queuedTasks: [ControlTask] = []
    @Published var leasedTasks: [ControlTask] = []
    @Published var failedTasks: [ControlTask] = []
    @Published var blockedReviewTasks: [ControlTask] = []
    @Published var platformStatus: PlatformStatusResponse?
    @Published var platformMetrics: PlatformMetricsResponse?
    @Published var platformReadiness: PlatformReadinessResponse?
    @Published var platformContracts: PlatformContractsResponse?
    @Published var platformRouteNotice: String?
    @Published var lastUpdated: Date?
    @Published var isLoading = false
    @Published var actionInFlight = false
    @Published var errorMessage: String?
    @Published var actionMessage: String?
    @Published var refreshReason = "startup"

    private var refreshLoop: Task<Void, Never>?

    deinit {
        refreshLoop?.cancel()
    }

    func start(settings: AppSettings) async {
        resetRefreshTimer(settings: settings)
        await refreshNow(settings: settings, reason: "initial")
    }

    func resetRefreshTimer(settings: AppSettings) {
        refreshLoop?.cancel()
        let interval = UInt64(max(15, settings.autoRefreshSeconds) * 1_000_000_000)

        refreshLoop = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: interval)
                guard let self else {
                    return
                }
                await refreshNow(settings: settings, reason: "interval")
            }
        }
    }

    func refreshNow(settings: AppSettings, reason: String) async {
        isLoading = true
        refreshReason = reason

        do {
            let client = try PMHubClient(baseURL: settings.baseURL, token: settings.readToken())
            let platformClient = try? PlatformClient(
                baseURL: settings.platformBaseURL,
                username: settings.platformUsername,
                password: settings.readPlatformPassword()
            )

            async let overview = client.controlOverview()
            async let executorPolicy = client.executorPolicy()
            async let agentsResponse = client.controlAgents(ttlSeconds: 180)
            async let projects = client.projectsOverview(refresh: true)
            async let opsInventory: OpsInventoryResponse? = try? client.opsInventory(
                refresh: true,
                includeLogs: false,
                eventLimit: 20
            )
            async let queued = client.tasks(status: "queued", limit: 100)
            async let leased = client.tasks(status: "leased", limit: 100)
            async let failed = client.tasks(status: "failed", limit: 100)
            async let blockedReview = client.tasks(status: "blocked_review", limit: 100)

            let overviewValue = try await overview
            let executorPolicyValue = try await executorPolicy
            let agentsValue = try await agentsResponse
            let projectsValue = try await projects
            let opsInventoryValue = await opsInventory
            let queuedValue = try await queued
            let leasedValue = try await leased
            let failedValue = try await failed
            let blockedReviewValue = try await blockedReview

            controlOverview = overviewValue
            self.executorPolicy = executorPolicyValue
            agents = agentsValue.agents
            projectsOverview = projectsValue
            self.opsInventory = opsInventoryValue
            queuedTasks = queuedValue.tasks
            leasedTasks = leasedValue.tasks
            failedTasks = failedValue.tasks
            blockedReviewTasks = blockedReviewValue.tasks

            if let platformClient {
                async let platformStatus = try? platformClient.status()
                async let platformMetrics = try? platformClient.metrics()
                async let platformReadiness = try? platformClient.readiness()
                async let platformContracts = try? platformClient.contracts()
                self.platformStatus = await platformStatus
                self.platformMetrics = await platformMetrics
                self.platformReadiness = await platformReadiness
                self.platformContracts = await platformContracts
            } else {
                self.platformStatus = nil
                self.platformMetrics = nil
                self.platformReadiness = nil
                self.platformContracts = nil
            }
            platformRouteNotice = settings.isPlatformBaseURLCanonical
                ? "Platform route: canonical (\(settings.platformBaseURL))"
                : "Platform route: custom (\(settings.platformBaseURL))"
            lastUpdated = Date()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    func syncBoard(settings: AppSettings) async {
        await performAction(settings: settings, label: "sync_board") { client in
            try await client.syncBoard()
        }
    }

    func autonomyCycle(settings: AppSettings) async {
        await performAction(settings: settings, label: "autonomy_cycle") { client in
            try await client.runAutonomyCycle(limit: 2)
        }
    }

    func assistantCheckin(settings: AppSettings) async {
        await performAction(settings: settings, label: "assistant_checkin") { client in
            try await client.runAssistantCheckin(limit: 4)
        }
    }

    func refreshQuotas(settings: AppSettings) async {
        await performAction(settings: settings, label: "refresh_quotas") { client in
            try await client.refreshMembershipQuotas(force: false)
        }
    }

    func runDeepResearch(settings: AppSettings) async {
        await performAction(settings: settings, label: "deepresearch_run") { client in
            try await client.runDeepResearch()
        }
    }

    private func performAction(
        settings: AppSettings,
        label: String,
        operation: @escaping (PMHubClient) async throws -> [String: Any]
    ) async {
        actionInFlight = true
        defer { actionInFlight = false }

        do {
            let client = try PMHubClient(baseURL: settings.baseURL, token: settings.readToken())
            let response = try await operation(client)
            actionMessage = summarizeAction(label: label, response: response)
            await refreshNow(settings: settings, reason: "action:\(label)")
        } catch {
            actionMessage = "\(label) failed: \(error.localizedDescription)"
            errorMessage = error.localizedDescription
        }
    }

    private func summarizeAction(label: String, response: [String: Any]) -> String {
        let status = String(describing: response["status"] ?? "unknown")
        var bits: [String] = ["\(label): \(status)"]
        if let action = response["action"] as? String, !action.isEmpty {
            bits.append("action=\(action)")
        }
        if let task = response["task"] as? [String: Any], let taskID = task["task_id"] as? String, !taskID.isEmpty {
            bits.append("task=\(taskID)")
        }
        if let result = response["result"] as? [String: Any], let generatedAt = result["generated_at"] as? String {
            bits.append("generated_at=\(generatedAt)")
        }
        return bits.joined(separator: " | ")
    }
}
