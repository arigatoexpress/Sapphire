import Foundation

extension KeyedDecodingContainer {
    func decodeIntLossy(forKey key: Key) -> Int {
        if let value = try? decode(Int.self, forKey: key) {
            return value
        }
        if let stringValue = try? decode(String.self, forKey: key), let value = Int(stringValue) {
            return value
        }
        return 0
    }

    func decodeDoubleLossy(forKey key: Key) -> Double {
        if let value = try? decode(Double.self, forKey: key) {
            return value
        }
        if let value = try? decode(Int.self, forKey: key) {
            return Double(value)
        }
        if let stringValue = try? decode(String.self, forKey: key), let value = Double(stringValue) {
            return value
        }
        return 0
    }

    func decodeBoolLossy(forKey key: Key) -> Bool {
        if let value = try? decode(Bool.self, forKey: key) {
            return value
        }
        if let value = try? decode(Int.self, forKey: key) {
            return value != 0
        }
        if let stringValue = try? decode(String.self, forKey: key) {
            let lowered = stringValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return ["1", "true", "yes", "y", "on"].contains(lowered)
        }
        return false
    }
}

struct TaskCounts: Decodable {
    let queued: Int
    let leased: Int
    let completed: Int
    let failed: Int
    let cancelled: Int
    let blockedReview: Int

    enum CodingKeys: String, CodingKey {
        case queued
        case leased
        case completed
        case failed
        case cancelled
        case blockedReview = "blocked_review"
    }

    init(queued: Int, leased: Int, completed: Int, failed: Int, cancelled: Int, blockedReview: Int = 0) {
        self.queued = queued
        self.leased = leased
        self.completed = completed
        self.failed = failed
        self.cancelled = cancelled
        self.blockedReview = blockedReview
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        queued = container.decodeIntLossy(forKey: .queued)
        leased = container.decodeIntLossy(forKey: .leased)
        completed = container.decodeIntLossy(forKey: .completed)
        failed = container.decodeIntLossy(forKey: .failed)
        cancelled = container.decodeIntLossy(forKey: .cancelled)
        blockedReview = container.decodeIntLossy(forKey: .blockedReview)
    }
}

struct SLOSummary: Decodable {
    let status: String
    let queueDrainTimeSeconds: Int
    let staleLeaseRate: Double
    let autocancelRate: Double
    let alerts: [String]

    enum CodingKeys: String, CodingKey {
        case status
        case queueDrainTimeSeconds = "queue_drain_time_seconds"
        case staleLeaseRate = "stale_lease_rate"
        case autocancelRate = "autocancel_rate"
        case alerts
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = (try? container.decode(String.self, forKey: .status)) ?? "unknown"
        queueDrainTimeSeconds = container.decodeIntLossy(forKey: .queueDrainTimeSeconds)
        staleLeaseRate = container.decodeDoubleLossy(forKey: .staleLeaseRate)
        autocancelRate = container.decodeDoubleLossy(forKey: .autocancelRate)
        alerts = (try? container.decode([String].self, forKey: .alerts)) ?? []
    }
}

struct ControlOverviewResponse: Decodable {
    let status: String?
    let generatedAt: String?
    let agentsTotal: Int
    let agentsOnline: Int
    let tasks: TaskCounts
    let kpiTasks: TaskCounts
    let kpiExcludedLowSignal: Int
    let slo: SLOSummary?

    enum CodingKeys: String, CodingKey {
        case status
        case generatedAt = "generated_at"
        case agentsTotal = "agents_total"
        case agentsOnline = "agents_online"
        case tasks
        case kpiTasks = "kpi_tasks"
        case kpiExcludedLowSignal = "kpi_excluded_low_signal"
        case slo
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = try container.decodeIfPresent(String.self, forKey: .status)
        generatedAt = try container.decodeIfPresent(String.self, forKey: .generatedAt)
        agentsTotal = container.decodeIntLossy(forKey: .agentsTotal)
        agentsOnline = container.decodeIntLossy(forKey: .agentsOnline)
        tasks = (try? container.decode(TaskCounts.self, forKey: .tasks))
            ?? TaskCounts(queued: 0, leased: 0, completed: 0, failed: 0, cancelled: 0)
        kpiTasks = (try? container.decode(TaskCounts.self, forKey: .kpiTasks)) ?? tasks
        kpiExcludedLowSignal = container.decodeIntLossy(forKey: .kpiExcludedLowSignal)
        slo = try? container.decodeIfPresent(SLOSummary.self, forKey: .slo)
    }

    init(
        status: String?,
        generatedAt: String?,
        agentsTotal: Int,
        agentsOnline: Int,
        tasks: TaskCounts,
        kpiTasks: TaskCounts,
        kpiExcludedLowSignal: Int,
        slo: SLOSummary?
    ) {
        self.status = status
        self.generatedAt = generatedAt
        self.agentsTotal = agentsTotal
        self.agentsOnline = agentsOnline
        self.tasks = tasks
        self.kpiTasks = kpiTasks
        self.kpiExcludedLowSignal = kpiExcludedLowSignal
        self.slo = slo
    }
}

struct ControlAgentsResponse: Decodable {
    let status: String?
    let agents: [AgentRecord]
}

struct AgentRecord: Decodable, Identifiable {
    let agentID: String
    let name: String
    let capabilities: [String]
    let status: String
    let heartbeatAgeSeconds: Int
    let isOnline: Bool
    let lastHeartbeatAt: String?

    enum CodingKeys: String, CodingKey {
        case agentID = "agent_id"
        case name
        case capabilities
        case status
        case heartbeatAgeSeconds = "heartbeat_age_seconds"
        case isOnline = "is_online"
        case lastHeartbeatAt = "last_heartbeat_at"
    }

    var id: String { agentID }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        agentID = (try? container.decode(String.self, forKey: .agentID)) ?? UUID().uuidString
        name = (try? container.decode(String.self, forKey: .name)) ?? agentID
        capabilities = (try? container.decode([String].self, forKey: .capabilities)) ?? []
        status = (try? container.decode(String.self, forKey: .status)) ?? "unknown"
        heartbeatAgeSeconds = container.decodeIntLossy(forKey: .heartbeatAgeSeconds)
        isOnline = (try? container.decode(Bool.self, forKey: .isOnline)) ?? false
        lastHeartbeatAt = try? container.decodeIfPresent(String.self, forKey: .lastHeartbeatAt)
    }
}

struct TaskListResponse: Decodable {
    let status: String?
    let tasks: [ControlTask]
}

struct ControlTask: Decodable, Identifiable {
    let taskID: String
    let title: String
    let status: String
    let priority: Int
    let attempts: Int
    let leaseOwner: String?
    let requiredCapabilities: [String]
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case taskID = "task_id"
        case title
        case status
        case priority
        case attempts
        case leaseOwner = "lease_owner"
        case requiredCapabilities = "required_capabilities"
        case updatedAt = "updated_at"
    }

    var id: String { taskID }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        taskID = (try? container.decode(String.self, forKey: .taskID)) ?? UUID().uuidString
        title = (try? container.decode(String.self, forKey: .title)) ?? "Untitled task"
        status = (try? container.decode(String.self, forKey: .status)) ?? "unknown"
        priority = container.decodeIntLossy(forKey: .priority)
        attempts = container.decodeIntLossy(forKey: .attempts)
        leaseOwner = try? container.decodeIfPresent(String.self, forKey: .leaseOwner)
        requiredCapabilities = (try? container.decode([String].self, forKey: .requiredCapabilities)) ?? []
        updatedAt = try? container.decodeIfPresent(String.self, forKey: .updatedAt)
    }
}

struct ProjectsOverviewResponse: Decodable {
    let status: String?
    let generatedAt: String?
    let runtimeMode: String?
    let board: BoardPayload?
    let trackedProjects: [TrackedProject]

    enum CodingKeys: String, CodingKey {
        case status
        case generatedAt = "generated_at"
        case runtimeMode = "runtime_mode"
        case board
        case trackedProjects = "tracked_projects"
    }
}

struct BoardPayload: Decodable {
    let counts: BoardCounts
}

struct BoardCounts: Decodable {
    let backlog: Int
    let inProgress: Int
    let blocked: Int
    let done: Int

    enum CodingKeys: String, CodingKey {
        case backlog
        case inProgress = "in_progress"
        case blocked
        case done
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        backlog = container.decodeIntLossy(forKey: .backlog)
        inProgress = container.decodeIntLossy(forKey: .inProgress)
        blocked = container.decodeIntLossy(forKey: .blocked)
        done = container.decodeIntLossy(forKey: .done)
    }
}

struct TrackedProject: Decodable, Identifiable {
    let id: String
    let name: String
    let notes: String?
    let missingLocal: Bool
    let missingGithub: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case notes
        case missingLocal = "missing_local"
        case missingGithub = "missing_github"
    }

    var healthLabel: String {
        if missingLocal && missingGithub {
            return "Missing local + GitHub"
        }
        if missingGithub {
            return "Missing GitHub"
        }
        if missingLocal {
            return "Missing local"
        }
        return "Healthy"
    }

    var healthColor: String {
        if missingLocal || missingGithub {
            return "warning"
        }
        return "ok"
    }
}

struct OpsInventoryResponse: Decodable {
    let status: String?
    let generatedAt: String?
    let summary: OpsInventorySummary?
    let policyDrift: PolicyDriftPayload?
    let queueRoutability: QueueRoutabilityPayload?

    enum CodingKeys: String, CodingKey {
        case status
        case generatedAt = "generated_at"
        case summary
        case policyDrift = "policy_drift"
        case queueRoutability = "queue_routability"
    }
}

struct OpsInventorySummary: Decodable {
    let agentsOnline: Int
    let agentsTotal: Int
    let tasksQueued: Int
    let tasksLeased: Int
    let tasksFailed: Int
    let queueRoutableCount: Int
    let queueUnroutableCount: Int
    let queueStallDetected: Bool
    let queueTopBlockerReason: String
    let policyDriftDetected: Bool
    let staleFocusCards: Int
    let sloStatus: String

    enum CodingKeys: String, CodingKey {
        case agentsOnline = "agents_online"
        case agentsTotal = "agents_total"
        case tasksQueued = "tasks_queued"
        case tasksLeased = "tasks_leased"
        case tasksFailed = "tasks_failed"
        case queueRoutableCount = "queue_routable_count"
        case queueUnroutableCount = "queue_unroutable_count"
        case queueStallDetected = "queue_stall_detected"
        case queueTopBlockerReason = "queue_top_blocker_reason"
        case policyDriftDetected = "policy_drift_detected"
        case staleFocusCards = "stale_focus_cards"
        case sloStatus = "slo_status"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        agentsOnline = container.decodeIntLossy(forKey: .agentsOnline)
        agentsTotal = container.decodeIntLossy(forKey: .agentsTotal)
        tasksQueued = container.decodeIntLossy(forKey: .tasksQueued)
        tasksLeased = container.decodeIntLossy(forKey: .tasksLeased)
        tasksFailed = container.decodeIntLossy(forKey: .tasksFailed)
        queueRoutableCount = container.decodeIntLossy(forKey: .queueRoutableCount)
        queueUnroutableCount = container.decodeIntLossy(forKey: .queueUnroutableCount)
        queueStallDetected = container.decodeBoolLossy(forKey: .queueStallDetected)
        queueTopBlockerReason = (try? container.decode(String.self, forKey: .queueTopBlockerReason)) ?? ""
        policyDriftDetected = container.decodeBoolLossy(forKey: .policyDriftDetected)
        staleFocusCards = container.decodeIntLossy(forKey: .staleFocusCards)
        sloStatus = (try? container.decode(String.self, forKey: .sloStatus)) ?? "unknown"
    }
}

struct PolicyDriftPayload: Decodable {
    let enabled: Bool
    let driftDetected: Bool
    let expected: PolicyShape?
    let observed: PolicyShape?
    let mismatches: [PolicyDriftMismatch]

    enum CodingKeys: String, CodingKey {
        case enabled
        case driftDetected = "drift_detected"
        case expected
        case observed
        case mismatches
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        enabled = container.decodeBoolLossy(forKey: .enabled)
        driftDetected = container.decodeBoolLossy(forKey: .driftDetected)
        expected = try? container.decodeIfPresent(PolicyShape.self, forKey: .expected)
        observed = try? container.decodeIfPresent(PolicyShape.self, forKey: .observed)
        mismatches = (try? container.decode([PolicyDriftMismatch].self, forKey: .mismatches)) ?? []
    }
}

struct PolicyShape: Decodable {
    let mode: String
    let allowedExecutorAgentIDs: [String]
    let allowedExecutorMembershipIDs: [String]

    enum CodingKeys: String, CodingKey {
        case mode
        case allowedExecutorAgentIDs = "allowed_executor_agent_ids"
        case allowedExecutorMembershipIDs = "allowed_executor_membership_ids"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        mode = (try? container.decode(String.self, forKey: .mode)) ?? ""
        allowedExecutorAgentIDs = (try? container.decode([String].self, forKey: .allowedExecutorAgentIDs)) ?? []
        allowedExecutorMembershipIDs = (try? container.decode([String].self, forKey: .allowedExecutorMembershipIDs)) ?? []
    }
}

struct PolicyDriftMismatch: Decodable, Identifiable {
    let field: String
    let expected: String
    let observed: String
    var id: String { field }

    enum CodingKeys: String, CodingKey {
        case field
        case expected
        case observed
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        field = (try? container.decode(String.self, forKey: .field)) ?? "unknown"
        if let expectedString = try? container.decode(String.self, forKey: .expected) {
            expected = expectedString
        } else if let expectedArray = try? container.decode([String].self, forKey: .expected) {
            expected = expectedArray.joined(separator: ", ")
        } else {
            expected = ""
        }
        if let observedString = try? container.decode(String.self, forKey: .observed) {
            observed = observedString
        } else if let observedArray = try? container.decode([String].self, forKey: .observed) {
            observed = observedArray.joined(separator: ", ")
        } else {
            observed = ""
        }
    }
}

struct ExecutorPolicyResponse: Decodable {
    let status: String?
    let policy: ExecutorPolicyDetail?
    let observedPolicy: ExecutorPolicyDetail?
    let policyDrift: PolicyDriftPayload?

    enum CodingKeys: String, CodingKey {
        case status
        case policy
        case observedPolicy = "observed_policy"
        case policyDrift = "policy_drift"
    }
}

struct ExecutorPolicyDetail: Decodable {
    let mode: String
    let updatedAt: String?
    let updatedBy: String?
    let allowedExecutorAgentIDs: [String]
    let allowedExecutorMembershipIDs: [String]
    let effectivePolicyLockApplied: Bool

    enum CodingKeys: String, CodingKey {
        case mode
        case updatedAt = "updated_at"
        case updatedBy = "updated_by"
        case allowedExecutorAgentIDs = "allowed_executor_agent_ids"
        case allowedExecutorMembershipIDs = "allowed_executor_membership_ids"
        case effectivePolicyLockApplied = "effective_policy_lock_applied"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        mode = (try? container.decode(String.self, forKey: .mode)) ?? ""
        updatedAt = try? container.decodeIfPresent(String.self, forKey: .updatedAt)
        updatedBy = try? container.decodeIfPresent(String.self, forKey: .updatedBy)
        allowedExecutorAgentIDs = (try? container.decode([String].self, forKey: .allowedExecutorAgentIDs)) ?? []
        allowedExecutorMembershipIDs = (try? container.decode([String].self, forKey: .allowedExecutorMembershipIDs)) ?? []
        effectivePolicyLockApplied = container.decodeBoolLossy(forKey: .effectivePolicyLockApplied)
    }
}

struct QueueRoutabilityPayload: Decodable {
    let summary: QueueRoutabilitySummary?
    let queuedTasks: [QueueRoutabilityTask]
    let recommendations: [QueueRecoveryRecommendation]

    enum CodingKeys: String, CodingKey {
        case summary
        case queuedTasks = "queued_tasks"
        case recommendations
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        summary = try? container.decodeIfPresent(QueueRoutabilitySummary.self, forKey: .summary)
        queuedTasks = (try? container.decode([QueueRoutabilityTask].self, forKey: .queuedTasks)) ?? []
        recommendations = (try? container.decode([QueueRecoveryRecommendation].self, forKey: .recommendations)) ?? []
    }
}

struct QueueRoutabilitySummary: Decodable {
    let queuedCount: Int
    let routableCount: Int
    let unroutableCount: Int
    let onlineAgentsTotal: Int
    let onlineExecutorAgents: Int
    let topBlockerReason: String
    let queueStallDetected: Bool
    let blockerBreakdown: [QueueBlockerBreakdown]

    enum CodingKeys: String, CodingKey {
        case queuedCount = "queued_count"
        case routableCount = "routable_count"
        case unroutableCount = "unroutable_count"
        case onlineAgentsTotal = "online_agents_total"
        case onlineExecutorAgents = "online_executor_agents"
        case topBlockerReason = "top_blocker_reason"
        case queueStallDetected = "queue_stall_detected"
        case blockerBreakdown = "blocker_breakdown"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        queuedCount = container.decodeIntLossy(forKey: .queuedCount)
        routableCount = container.decodeIntLossy(forKey: .routableCount)
        unroutableCount = container.decodeIntLossy(forKey: .unroutableCount)
        onlineAgentsTotal = container.decodeIntLossy(forKey: .onlineAgentsTotal)
        onlineExecutorAgents = container.decodeIntLossy(forKey: .onlineExecutorAgents)
        topBlockerReason = (try? container.decode(String.self, forKey: .topBlockerReason)) ?? ""
        queueStallDetected = container.decodeBoolLossy(forKey: .queueStallDetected)
        blockerBreakdown = (try? container.decode([QueueBlockerBreakdown].self, forKey: .blockerBreakdown)) ?? []
    }
}

struct QueueBlockerBreakdown: Decodable, Identifiable {
    let reason: String
    let count: Int
    var id: String { reason }

    enum CodingKeys: String, CodingKey {
        case reason
        case count
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        reason = (try? container.decode(String.self, forKey: .reason)) ?? "unknown"
        count = container.decodeIntLossy(forKey: .count)
    }
}

struct QueueRoutabilityTask: Decodable, Identifiable {
    let taskID: String
    let title: String
    let routable: Bool
    let blockerReasons: [String]
    let requiredCapabilities: [String]
    let eligibleOnlineAgents: [String]

    enum CodingKeys: String, CodingKey {
        case taskID = "task_id"
        case title
        case routable
        case blockerReasons = "blocker_reasons"
        case requiredCapabilities = "required_capabilities"
        case eligibleOnlineAgents = "eligible_online_agents"
    }

    var id: String { taskID }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        taskID = (try? container.decode(String.self, forKey: .taskID)) ?? UUID().uuidString
        title = (try? container.decode(String.self, forKey: .title)) ?? "Untitled task"
        routable = container.decodeBoolLossy(forKey: .routable)
        blockerReasons = (try? container.decode([String].self, forKey: .blockerReasons)) ?? []
        requiredCapabilities = (try? container.decode([String].self, forKey: .requiredCapabilities)) ?? []
        eligibleOnlineAgents = (try? container.decode([String].self, forKey: .eligibleOnlineAgents)) ?? []
    }
}

struct QueueRecoveryRecommendation: Decodable, Identifiable {
    let id: String
    let priority: String
    let action: String
    let reason: String?

    enum CodingKeys: String, CodingKey {
        case id
        case priority
        case action
        case reason
    }
}

struct PlatformStatusResponse: Decodable {
    let timestamp: String?
    let summary: PlatformStatusSummary
}

struct PlatformStatusSummary: Decodable {
    let serviceTotal: Int
    let serviceHealthy: Int
    let serviceUnhealthy: Int
    let nodeTotal: Int
    let nodeHealthy: Int
    let nodeUnhealthy: Int

    enum CodingKeys: String, CodingKey {
        case serviceTotal = "service_total"
        case serviceHealthy = "service_healthy"
        case serviceUnhealthy = "service_unhealthy"
        case nodeTotal = "node_total"
        case nodeHealthy = "node_healthy"
        case nodeUnhealthy = "node_unhealthy"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        serviceTotal = container.decodeIntLossy(forKey: .serviceTotal)
        serviceHealthy = container.decodeIntLossy(forKey: .serviceHealthy)
        serviceUnhealthy = container.decodeIntLossy(forKey: .serviceUnhealthy)
        nodeTotal = container.decodeIntLossy(forKey: .nodeTotal)
        nodeHealthy = container.decodeIntLossy(forKey: .nodeHealthy)
        nodeUnhealthy = container.decodeIntLossy(forKey: .nodeUnhealthy)
    }
}

struct PlatformReadinessResponse: Decodable {
    let timestamp: String?
    let overallOK: Bool
    let gates: [String: PlatformGate]
    let blockers: [PlatformReadinessBlocker]

    enum CodingKeys: String, CodingKey {
        case timestamp
        case overallOK = "overall_ok"
        case gates
        case blockers
    }
}

struct PlatformGate: Decodable {
    let ok: Bool
    let pass: Int
    let total: Int

    enum CodingKeys: String, CodingKey {
        case ok
        case pass
        case total
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        ok = container.decodeBoolLossy(forKey: .ok)
        pass = container.decodeIntLossy(forKey: .pass)
        total = container.decodeIntLossy(forKey: .total)
    }
}

struct PlatformReadinessBlocker: Decodable, Identifiable {
    let gate: String?
    let name: String
    let error: String?

    var id: String { "\(gate ?? "unknown"):\(name)" }
}

struct PlatformMetricsResponse: Decodable {
    let timestamp: String?
    let health: PlatformHealthSummary
    let trading: PlatformTradingSummary?
}

struct PlatformHealthSummary: Decodable {
    let healthy: Bool
    let healthyCount: Int
    let unhealthyCount: Int
    let nodeHealthyCount: Int
    let nodeUnhealthyCount: Int

    enum CodingKeys: String, CodingKey {
        case healthy
        case healthyCount = "healthy_count"
        case unhealthyCount = "unhealthy_count"
        case nodeHealthyCount = "node_healthy_count"
        case nodeUnhealthyCount = "node_unhealthy_count"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        healthy = container.decodeBoolLossy(forKey: .healthy)
        healthyCount = container.decodeIntLossy(forKey: .healthyCount)
        unhealthyCount = container.decodeIntLossy(forKey: .unhealthyCount)
        nodeHealthyCount = container.decodeIntLossy(forKey: .nodeHealthyCount)
        nodeUnhealthyCount = container.decodeIntLossy(forKey: .nodeUnhealthyCount)
    }
}

struct PlatformTradingSummary: Decodable {
    let trades: PlatformTradeCounts?
}

struct PlatformTradeCounts: Decodable {
    let today: Int
    let total: Int
    let successRate: Double

    enum CodingKeys: String, CodingKey {
        case today
        case total
        case successRate = "success_rate"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        today = container.decodeIntLossy(forKey: .today)
        total = container.decodeIntLossy(forKey: .total)
        successRate = container.decodeDoubleLossy(forKey: .successRate)
    }
}

struct PlatformContractsResponse: Decodable {
    let version: String
    let auth: PlatformAuthInfo?
    let counts: PlatformContractCounts?
    let endpoints: [PlatformContractEndpoint]
}

struct PlatformAuthInfo: Decodable {
    let enabled: Bool
    let mode: String
    let publicReadOnly: Bool

    enum CodingKeys: String, CodingKey {
        case enabled
        case mode
        case publicReadOnly = "public_read_only"
    }
}

struct PlatformContractCounts: Decodable {
    let total: Int
    let categories: [String]
}

struct PlatformContractEndpoint: Decodable, Identifiable {
    let name: String
    let path: String
    let method: String
    let auth: String?
    let category: String?
    let description: String?
    let authRequired: Bool?
    let publicAvailable: Bool?

    enum CodingKeys: String, CodingKey {
        case name
        case path
        case method
        case auth
        case category
        case description
        case authRequired = "auth_required"
        case publicAvailable = "public_available"
    }

    var id: String { path }
}
