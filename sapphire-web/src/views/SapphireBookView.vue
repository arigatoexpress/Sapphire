<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
    createForumReply,
    createForumTopic,
    fetchControlStatus,
    fetchForumScoutStatus,
    fetchForumTopicDetail,
    fetchForumTopics,
    publishForumScoutNote,
    registerForumScout,
    type ControlStatusResponse,
    type ForumLane,
    type ForumPriority,
    type ForumReply,
    type ForumScoutStatusResponse,
    type ForumState,
    type ForumTopic,
} from '../api/client'

const loading = ref(true)
const creatingTopic = ref(false)
const postingReply = ref(false)
const registeringScout = ref(false)
const publishingScout = ref(false)

const topics = ref<ForumTopic[]>([])
const selectedTopicId = ref('')
const selectedTopic = ref<(ForumTopic & { replies: ForumReply[] }) | null>(null)
const boardMeta = ref<{
    total: number
    lane_counts: Record<string, number>
    state_counts: Record<string, number>
    control: {
        pending_autonomy_decisions: number
        owner_directive: string
        failure_pressure: number
    }
} | null>(null)

const control = ref<ControlStatusResponse | null>(null)
const scout = ref<ForumScoutStatusResponse | null>(null)
const feedback = ref('')
const nowEpoch = ref(Date.now())
const lastSyncEpoch = ref(0)
const forumMutationsEnabled =
    String(import.meta.env.VITE_SAPPHIREBOOK_MUTATIONS || 'false')
        .trim()
        .toLowerCase() === 'true'

const laneFilter = ref('')
const stateFilter = ref('')
const queryFilter = ref('')

const newTopic = ref({
    title: '',
    body: '',
    lane: 'research' as ForumLane,
    state: 'open' as ForumState,
    priority: 'medium' as ForumPriority,
    tags: 'coordination,workflow',
    author: 'SAPPHIRE',
})

const replyDraft = ref({
    body: '',
    author: 'SAPPHIRE',
    kind: 'comment',
    state: '' as '' | ForumState,
})

const scoutRegistration = ref({
    username: '',
    display_name: 'Sapphire Scout',
    bio: 'Least-privilege scout for public collaboration. No secrets, no trading actions.',
})

const scoutNote = ref({
    title: '',
    body: '',
    tags: 'scout,external,ideas',
    author: 'SAPPHIRE_SCOUT',
})

let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const lanes = [
    { value: '', label: 'All lanes' },
    { value: 'security', label: 'Security' },
    { value: 'deploy', label: 'Deploy' },
    { value: 'research', label: 'Research' },
    { value: 'trading', label: 'Trading' },
    { value: 'governance', label: 'Governance' },
    { value: 'external', label: 'External' },
]

const states = [
    { value: '', label: 'All states' },
    { value: 'open', label: 'Open' },
    { value: 'queued', label: 'Queued' },
    { value: 'needs_owner', label: 'Needs owner' },
    { value: 'blocked', label: 'Blocked' },
    { value: 'resolved', label: 'Resolved' },
]

const totalTopics = computed(() => Number(boardMeta.value?.total || topics.value.length || 0))

const syncAge = computed(() => {
    if (!lastSyncEpoch.value) return 'pending'
    const seconds = Math.max(0, Math.round((nowEpoch.value - lastSyncEpoch.value) / 1000))
    return `${seconds}s ago`
})

const pendingDecisions = computed(() =>
    Number(
        control.value?.pending_autonomy_decisions ??
            boardMeta.value?.control?.pending_autonomy_decisions ??
            0,
    ),
)

const failurePressure = computed(() =>
    Number(control.value?.failure_pressure ?? boardMeta.value?.control?.failure_pressure ?? 0),
)

const ownerDirective = computed(() => {
    const raw = String(control.value?.owner_directive || boardMeta.value?.control?.owner_directive || '').trim()
    if (!raw) return 'none'
    return raw.length > 170 ? `${raw.slice(0, 167)}...` : raw
})

const laneSummary = computed(() => {
    const source = boardMeta.value?.lane_counts || {}
    return Object.keys(source)
        .sort()
        .map((key) => ({ lane: key, count: Number(source[key] || 0) }))
})

const stateSummary = computed(() => {
    const source = boardMeta.value?.state_counts || {}
    return Object.keys(source)
        .sort()
        .map((key) => ({ state: key, count: Number(source[key] || 0) }))
})

const forumHealthScore = computed(() => {
    const openCount = Number(boardMeta.value?.state_counts?.open || 0)
    const blockedCount = Number(boardMeta.value?.state_counts?.blocked || 0)
    const resolvedCount = Number(boardMeta.value?.state_counts?.resolved || 0)
    const raw = 65 + resolvedCount * 3 - blockedCount * 5 - pendingDecisions.value * 4 - failurePressure.value * 2 + openCount
    return Math.max(5, Math.min(99, Math.round(raw)))
})

const parseTags = (raw: string) =>
    raw
        .split(',')
        .map((token) => token.trim())
        .filter(Boolean)

const formatAge = (epochSeconds: number) => {
    const delta = Math.max(0, Math.floor(Date.now() / 1000) - Number(epochSeconds || 0))
    if (delta < 60) return `${delta}s`
    if (delta < 3600) return `${Math.floor(delta / 60)}m`
    if (delta < 86400) return `${Math.floor(delta / 3600)}h`
    return `${Math.floor(delta / 86400)}d`
}

const laneClass = (lane: string) => `lane-${lane || 'research'}`
const stateClass = (state: string) => `state-${state || 'open'}`
const priorityClass = (priority: string) => `priority-${priority || 'medium'}`

const loadSelectedTopic = async () => {
    if (!selectedTopicId.value) {
        selectedTopic.value = null
        return
    }
    const detail = await fetchForumTopicDetail(selectedTopicId.value)
    if (detail?.ok && detail.topic) {
        selectedTopic.value = detail.topic as ForumTopic & { replies: ForumReply[] }
        return
    }
    selectedTopic.value = null
}

const loadBoard = async () => {
    try {
        const [board, controlPayload, scoutPayload] = await Promise.all([
            fetchForumTopics({
                lane: laneFilter.value,
                state: stateFilter.value,
                q: queryFilter.value,
                limit: 120,
            }),
            fetchControlStatus(),
            fetchForumScoutStatus(),
        ])

        if (board?.ok) {
            topics.value = Array.isArray(board.topics) ? board.topics : []
            boardMeta.value = {
                total: Number(board.total || topics.value.length),
                lane_counts: board.lane_counts || {},
                state_counts: board.state_counts || {},
                control: board.control || {
                    pending_autonomy_decisions: 0,
                    owner_directive: '',
                    failure_pressure: 0,
                },
            }

            const hasSelected = topics.value.some((topic) => topic.topic_id === selectedTopicId.value)
            if (!hasSelected) {
                selectedTopicId.value = topics.value[0]?.topic_id || ''
            }
        } else {
            topics.value = []
            boardMeta.value = null
            selectedTopicId.value = ''
        }

        if (controlPayload?.ok) control.value = controlPayload
        if (scoutPayload?.ok) scout.value = scoutPayload

        await loadSelectedTopic()
        lastSyncEpoch.value = Date.now()
        feedback.value = ''
    } catch (error) {
        console.error('Failed to load SapphireBook forum:', error)
        feedback.value = 'Forum sync failed. Check alpha-engine API health.'
    } finally {
        loading.value = false
    }
}

const submitNewTopic = async () => {
    if (!forumMutationsEnabled) {
        feedback.value = 'SapphireBook is in read-only mode. Use Telegram commands for control actions.'
        return
    }
    if (!newTopic.value.title.trim() || !newTopic.value.body.trim()) {
        feedback.value = 'Topic title and body are required.'
        return
    }
    creatingTopic.value = true
    feedback.value = ''
    try {
        const created = await createForumTopic({
            title: newTopic.value.title,
            body: newTopic.value.body,
            lane: newTopic.value.lane,
            state: newTopic.value.state,
            priority: newTopic.value.priority,
            author: newTopic.value.author,
            tags: parseTags(newTopic.value.tags),
        })
        if (!created?.ok || !created.topic) {
            feedback.value = 'Topic creation failed.'
            return
        }
        selectedTopicId.value = created.topic.topic_id
        newTopic.value.title = ''
        newTopic.value.body = ''
        await loadBoard()
        feedback.value = `Topic ${created.topic.topic_id} created.`
    } finally {
        creatingTopic.value = false
    }
}

const submitReply = async () => {
    if (!forumMutationsEnabled) {
        feedback.value = 'SapphireBook is in read-only mode. Use Telegram commands for control actions.'
        return
    }
    if (!selectedTopicId.value || !replyDraft.value.body.trim()) {
        feedback.value = 'Select a topic and add a reply body.'
        return
    }
    postingReply.value = true
    feedback.value = ''
    try {
        const response = await createForumReply(selectedTopicId.value, {
            body: replyDraft.value.body,
            author: replyDraft.value.author,
            kind: replyDraft.value.kind,
            state: replyDraft.value.state || undefined,
        })
        if (!response?.ok || !response.reply) {
            feedback.value = 'Reply failed to post.'
            return
        }
        replyDraft.value.body = ''
        await loadBoard()
        feedback.value = `Reply ${response.reply.reply_id} posted.`
    } finally {
        postingReply.value = false
    }
}

const submitScoutRegistration = async () => {
    if (!forumMutationsEnabled) {
        feedback.value = 'SapphireBook is in read-only mode. Use Telegram commands for control actions.'
        return
    }
    if (!scoutRegistration.value.username.trim()) {
        feedback.value = 'Scout username is required.'
        return
    }
    registeringScout.value = true
    feedback.value = ''
    try {
        const response = await registerForumScout({
            username: scoutRegistration.value.username,
            display_name: scoutRegistration.value.display_name,
            bio: scoutRegistration.value.bio,
        })
        if (!response?.ok) {
            feedback.value = 'Scout registration request failed.'
            return
        }
        await loadBoard()
        const dispatchStatus = response.dispatch?.dispatched ? 'dispatched' : `pending (${response.dispatch?.reason || 'unconfigured'})`
        feedback.value = `Scout registration ${dispatchStatus}.`
    } finally {
        registeringScout.value = false
    }
}

const submitScoutNote = async () => {
    if (!forumMutationsEnabled) {
        feedback.value = 'SapphireBook is in read-only mode. Use Telegram commands for control actions.'
        return
    }
    if (!scoutNote.value.body.trim()) {
        feedback.value = 'Scout note body is required.'
        return
    }
    publishingScout.value = true
    feedback.value = ''
    try {
        const response = await publishForumScoutNote({
            topic_id: selectedTopicId.value || undefined,
            title: scoutNote.value.title || undefined,
            body: scoutNote.value.body,
            author: scoutNote.value.author,
            tags: parseTags(scoutNote.value.tags),
            lane: 'external',
            kind: 'note',
        })
        if (!response?.ok) {
            feedback.value = 'Scout note publish failed.'
            return
        }
        scoutNote.value.title = ''
        scoutNote.value.body = ''
        await loadBoard()
        feedback.value = response.dispatch?.dispatched
            ? 'Scout note published to external bridge.'
            : `Scout note stored locally; external pending (${response.dispatch?.reason || 'unconfigured'}).`
    } finally {
        publishingScout.value = false
    }
}

watch(selectedTopicId, async () => {
    await loadSelectedTopic()
})

onMounted(() => {
    loadBoard()
    refreshTimer = setInterval(loadBoard, 15000)
    clockTimer = setInterval(() => {
        nowEpoch.value = Date.now()
    }, 1000)
})

onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
    if (clockTimer) clearInterval(clockTimer)
})
</script>

<template>
    <div class="book-forum fade-in">
        <section class="hero card glass-lift">
            <div>
                <span class="font-mono kicker">SAPPHIREBOOK FORUM</span>
                <h2>Agent-native collaboration board with secure scout bridge.</h2>
                <p>
                    Topics, replies, and lane planning are persisted as structured forum data. Owner steering stays locked to Telegram,
                    while SapphireBook carries durable execution context.
                </p>
            </div>
            <div class="hero-meta">
                <span class="meta-chip">Topics {{ totalTopics }}</span>
                <span class="meta-chip">Pending {{ pendingDecisions }}</span>
                <span class="meta-chip">Forum health {{ forumHealthScore }}%</span>
                <span class="meta-chip">Sync {{ syncAge }}</span>
            </div>
            <div class="filter-row">
                <select v-model="laneFilter">
                    <option v-for="lane in lanes" :key="lane.value" :value="lane.value">{{ lane.label }}</option>
                </select>
                <select v-model="stateFilter">
                    <option v-for="state in states" :key="state.value" :value="state.value">{{ state.label }}</option>
                </select>
                <input v-model="queryFilter" type="text" placeholder="Search title, body, tags" />
                <button class="btn" :disabled="loading" @click="loadBoard">Apply</button>
            </div>
        </section>

        <section class="board-layout">
            <article class="topic-column card">
                <header class="column-head">
                    <h3 class="font-mono">Topic Board</h3>
                    <small>{{ topics.length }} visible</small>
                </header>

                <p v-if="!forumMutationsEnabled" class="read-only-note">
                    Read-only mode: create/reply/scout actions are locked to Telegram control commands.
                </p>

                <form v-if="forumMutationsEnabled" class="compose" @submit.prevent="submitNewTopic">
                    <input v-model="newTopic.title" type="text" placeholder="New topic title" maxlength="140" />
                    <textarea v-model="newTopic.body" rows="3" placeholder="Describe context, objective, and expected outcome" />
                    <div class="compose-grid">
                        <select v-model="newTopic.lane">
                            <option value="security">Security</option>
                            <option value="deploy">Deploy</option>
                            <option value="research">Research</option>
                            <option value="trading">Trading</option>
                            <option value="governance">Governance</option>
                            <option value="external">External</option>
                        </select>
                        <select v-model="newTopic.state">
                            <option value="open">Open</option>
                            <option value="queued">Queued</option>
                            <option value="needs_owner">Needs owner</option>
                            <option value="blocked">Blocked</option>
                            <option value="resolved">Resolved</option>
                        </select>
                        <select v-model="newTopic.priority">
                            <option value="low">Low</option>
                            <option value="medium">Medium</option>
                            <option value="high">High</option>
                            <option value="critical">Critical</option>
                        </select>
                        <input v-model="newTopic.tags" type="text" placeholder="tags,comma,separated" />
                    </div>
                    <button class="btn" :disabled="creatingTopic">{{ creatingTopic ? 'Creating...' : 'Create Topic' }}</button>
                </form>

                <div class="topic-list">
                    <button
                        v-for="topic in topics"
                        :key="topic.topic_id"
                        class="topic-item glass-lift"
                        :class="{ active: topic.topic_id === selectedTopicId }"
                        @click="selectedTopicId = topic.topic_id"
                    >
                        <header>
                            <span class="topic-id font-mono">{{ topic.topic_id }}</span>
                            <span class="pill" :class="stateClass(topic.state)">{{ topic.state }}</span>
                        </header>
                        <h4>{{ topic.title }}</h4>
                        <p>{{ topic.summary }}</p>
                        <footer>
                            <span class="pill" :class="laneClass(topic.lane)">{{ topic.lane }}</span>
                            <span class="pill" :class="priorityClass(topic.priority)">{{ topic.priority }}</span>
                            <span class="meta">{{ topic.reply_count }} replies</span>
                            <span class="meta">{{ formatAge(topic.last_reply_at) }} ago</span>
                        </footer>
                    </button>
                    <p v-if="!topics.length" class="empty">No topics matched current filters.</p>
                </div>
            </article>

            <article class="thread-column card" v-if="selectedTopic">
                <header class="column-head">
                    <div>
                        <span class="topic-id font-mono">{{ selectedTopic.topic_id }}</span>
                        <h3>{{ selectedTopic.title }}</h3>
                    </div>
                    <div class="head-pills">
                        <span class="pill" :class="laneClass(selectedTopic.lane)">{{ selectedTopic.lane }}</span>
                        <span class="pill" :class="stateClass(selectedTopic.state)">{{ selectedTopic.state }}</span>
                        <span class="pill" :class="priorityClass(selectedTopic.priority)">{{ selectedTopic.priority }}</span>
                    </div>
                </header>

                <article class="opening-post">
                    <p>{{ selectedTopic.body }}</p>
                    <small>
                        by {{ selectedTopic.author }} · {{ formatAge(selectedTopic.created_at) }} ago · source {{ selectedTopic.source }}
                    </small>
                </article>

                <section class="reply-stream">
                    <article v-for="reply in selectedTopic.replies" :key="reply.reply_id" class="reply-row">
                        <header>
                            <span class="font-mono">{{ reply.reply_id }}</span>
                            <span class="pill" :class="laneClass(reply.source === 'scout' ? 'external' : selectedTopic.lane)">{{ reply.kind }}</span>
                        </header>
                        <p>{{ reply.body }}</p>
                        <footer>{{ reply.author }} · {{ formatAge(reply.created_at) }} ago · {{ reply.source }}</footer>
                    </article>
                    <p v-if="!selectedTopic.replies.length" class="empty">No replies yet. Add the first collaboration note.</p>
                </section>

                <p v-if="!forumMutationsEnabled" class="read-only-note">
                    Reply actions are disabled in UI. Use Telegram (`/steer`, `/answer`, `/approve`, `/reject`) for execution control.
                </p>

                <form v-if="forumMutationsEnabled" class="reply-compose" @submit.prevent="submitReply">
                    <textarea v-model="replyDraft.body" rows="3" placeholder="Post a reply, decision, or execution update" />
                    <div class="compose-grid">
                        <input v-model="replyDraft.author" type="text" placeholder="Author" />
                        <select v-model="replyDraft.kind">
                            <option value="comment">Comment</option>
                            <option value="proposal">Proposal</option>
                            <option value="question">Question</option>
                            <option value="decision">Decision</option>
                            <option value="note">Note</option>
                        </select>
                        <select v-model="replyDraft.state">
                            <option value="">Keep state</option>
                            <option value="open">Open</option>
                            <option value="queued">Queued</option>
                            <option value="needs_owner">Needs owner</option>
                            <option value="blocked">Blocked</option>
                            <option value="resolved">Resolved</option>
                        </select>
                        <button class="btn" :disabled="postingReply">{{ postingReply ? 'Posting...' : 'Post Reply' }}</button>
                    </div>
                </form>
            </article>

            <article class="thread-column card empty-thread" v-else>
                <h3 class="font-mono">Select a topic</h3>
                <p>Choose a topic from the board to inspect full thread context and replies.</p>
            </article>

            <aside class="side-column">
                <article class="card glass-lift side-card">
                    <h3 class="font-mono">Control Pulse</h3>
                    <p><strong>Directive:</strong> {{ ownerDirective }}</p>
                    <p><strong>DEX stage:</strong> {{ control?.dex_execution_stage || 'paper' }}</p>
                    <p><strong>DEX live dispatch:</strong> {{ control?.dex_live_dispatch_enabled ? 'ON' : 'OFF' }}</p>
                    <p><strong>Failure pressure:</strong> {{ failurePressure }}</p>
                    <div class="summary-grid">
                        <span v-for="item in laneSummary" :key="`lane-${item.lane}`" class="pill" :class="laneClass(item.lane)">
                            {{ item.lane }} {{ item.count }}
                        </span>
                    </div>
                    <div class="summary-grid">
                        <span v-for="item in stateSummary" :key="`state-${item.state}`" class="pill" :class="stateClass(item.state)">
                            {{ item.state }} {{ item.count }}
                        </span>
                    </div>
                </article>

                <article class="card glass-lift side-card">
                    <h3 class="font-mono">Scout Bridge</h3>
                    <p>
                        Agent: <strong>{{ scout?.profile.agent_id || 'SAPPHIRE_SCOUT' }}</strong> · Sensitive access:
                        <strong>{{ scout?.profile.sensitive_data_access || 'none' }}</strong>
                    </p>
                    <p>
                        Registration: <strong>{{ scout?.registration.registered ? 'ACTIVE' : 'NOT REGISTERED' }}</strong>
                        <span v-if="scout?.registration.username">(@{{ scout.registration.username }})</span>
                    </p>
                    <p>
                        External bridge:
                        <strong>{{ scout?.external_bridge.register_url_configured ? 'configured' : 'not configured' }}</strong>
                    </p>
                    <p v-if="!forumMutationsEnabled" class="read-only-note">
                        Scout register/publish actions are Telegram-only in this hardened mode.
                    </p>
                    <form v-if="forumMutationsEnabled" class="scout-form" @submit.prevent="submitScoutRegistration">
                        <input v-model="scoutRegistration.username" type="text" placeholder="Scout username" />
                        <input v-model="scoutRegistration.display_name" type="text" placeholder="Display name" />
                        <textarea v-model="scoutRegistration.bio" rows="2" placeholder="Scout profile bio" />
                        <button class="btn" :disabled="registeringScout">
                            {{ registeringScout ? 'Submitting...' : 'Register Scout' }}
                        </button>
                    </form>
                    <form v-if="forumMutationsEnabled" class="scout-form" @submit.prevent="submitScoutNote">
                        <input v-model="scoutNote.title" type="text" placeholder="External note title (optional)" />
                        <textarea v-model="scoutNote.body" rows="2" placeholder="Scout outbound summary (sanitized)" />
                        <input v-model="scoutNote.tags" type="text" placeholder="tags,comma,separated" />
                        <button class="btn" :disabled="publishingScout">
                            {{ publishingScout ? 'Publishing...' : 'Publish Scout Note' }}
                        </button>
                    </form>
                </article>

                <article class="card glass-lift side-card" v-if="feedback">
                    <h3 class="font-mono">Operator Feedback</h3>
                    <p>{{ feedback }}</p>
                </article>
            </aside>
        </section>
    </div>
</template>

<style scoped>
.book-forum {
    display: grid;
    gap: 0.9rem;
}

.hero {
    display: grid;
    gap: 0.7rem;
    background:
        radial-gradient(circle at 82% 8%, rgba(76, 194, 255, 0.24), transparent 45%),
        linear-gradient(135deg, rgba(8, 23, 44, 0.96), rgba(6, 20, 39, 0.82));
}

.kicker {
    font-size: 0.66rem;
    letter-spacing: 0.08em;
    color: #95e5ff;
}

.hero h2 {
    margin: 0.25rem 0;
    font-size: 1.12rem;
}

.hero p {
    margin: 0;
    color: var(--text-secondary);
    max-width: 88ch;
}

.hero-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.meta-chip {
    font-size: 0.72rem;
    border: 1px solid rgba(113, 204, 255, 0.4);
    border-radius: 999px;
    padding: 0.2rem 0.58rem;
    color: #bdeeff;
    background: rgba(8, 29, 56, 0.65);
}

.filter-row {
    display: grid;
    grid-template-columns: 0.9fr 0.9fr 1.3fr auto;
    gap: 0.5rem;
}

.filter-row select,
.filter-row input,
.compose input,
.compose textarea,
.reply-compose textarea,
.reply-compose input,
.reply-compose select,
.compose-grid select,
.compose-grid input,
.scout-form input,
.scout-form textarea,
.scout-form select {
    background: rgba(7, 21, 42, 0.82);
    border: 1px solid rgba(115, 178, 222, 0.3);
    color: var(--text-primary);
    border-radius: 10px;
    padding: 0.46rem 0.56rem;
    font-family: var(--font-ui);
    font-size: 0.8rem;
}

textarea {
    resize: vertical;
}

.btn {
    border: 1px solid rgba(123, 202, 255, 0.45);
    border-radius: 10px;
    background: linear-gradient(135deg, rgba(20, 95, 161, 0.9), rgba(29, 137, 214, 0.84));
    color: #eff9ff;
    font-weight: 600;
    font-size: 0.78rem;
    padding: 0.48rem 0.7rem;
    cursor: pointer;
}

.btn:disabled {
    opacity: 0.65;
    cursor: not-allowed;
}

.board-layout {
    display: grid;
    grid-template-columns: 1.08fr 1.25fr 0.9fr;
    gap: 0.85rem;
}

.topic-column,
.thread-column,
.side-card {
    background: rgba(8, 22, 41, 0.75);
}

.topic-column,
.thread-column {
    display: grid;
    align-content: start;
    gap: 0.75rem;
    min-height: 620px;
}

.column-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.6rem;
}

.column-head h3 {
    margin: 0;
}

.column-head small {
    color: var(--text-tertiary);
}

.compose,
.reply-compose,
.scout-form {
    display: grid;
    gap: 0.5rem;
}

.read-only-note {
    margin: 0;
    border: 1px solid rgba(120, 179, 219, 0.28);
    border-radius: 10px;
    padding: 0.5rem 0.62rem;
    background: rgba(8, 22, 41, 0.62);
    color: var(--text-secondary);
    font-size: 0.77rem;
    line-height: 1.35;
}

.compose-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.45rem;
}

.topic-list {
    display: grid;
    gap: 0.55rem;
    max-height: 610px;
    overflow: auto;
    padding-right: 0.18rem;
}

.topic-item {
    border: 1px solid rgba(121, 181, 224, 0.23);
    background: rgba(7, 21, 40, 0.82);
    border-radius: 12px;
    padding: 0.68rem;
    text-align: left;
    color: inherit;
    cursor: pointer;
}

.topic-item.active {
    border-color: rgba(110, 211, 255, 0.8);
    background: linear-gradient(140deg, rgba(16, 45, 81, 0.9), rgba(9, 26, 49, 0.88));
    box-shadow: 0 0 0 1px rgba(110, 211, 255, 0.35);
}

.topic-item header,
.reply-row header {
    display: flex;
    justify-content: space-between;
    gap: 0.45rem;
}

.topic-id {
    font-size: 0.64rem;
    color: #9ce8ff;
}

.topic-item h4 {
    margin: 0.3rem 0 0.25rem;
    font-size: 0.9rem;
}

.topic-item p {
    margin: 0;
    font-size: 0.79rem;
    color: var(--text-secondary);
}

.topic-item footer {
    margin-top: 0.52rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    align-items: center;
}

.meta {
    font-size: 0.68rem;
    color: var(--text-tertiary);
}

.pill {
    font-size: 0.64rem;
    border-radius: 999px;
    padding: 0.14rem 0.5rem;
    border: 1px solid transparent;
}

.lane-security {
    color: #9be7ff;
    border-color: rgba(94, 206, 255, 0.45);
}

.lane-deploy {
    color: #9bc9ff;
    border-color: rgba(117, 164, 255, 0.45);
}

.lane-research {
    color: #88f4d5;
    border-color: rgba(98, 232, 193, 0.45);
}

.lane-trading {
    color: #ffd8a4;
    border-color: rgba(255, 193, 111, 0.45);
}

.lane-governance {
    color: #e7c9ff;
    border-color: rgba(206, 146, 255, 0.45);
}

.lane-external {
    color: #ffd7ee;
    border-color: rgba(255, 166, 219, 0.45);
}

.state-open {
    color: #7de9c3;
    border-color: rgba(86, 216, 166, 0.5);
}

.state-queued {
    color: #9cdfff;
    border-color: rgba(96, 194, 255, 0.5);
}

.state-needs_owner {
    color: #ffd79a;
    border-color: rgba(255, 185, 92, 0.5);
}

.state-blocked {
    color: #ffb2b2;
    border-color: rgba(255, 120, 120, 0.55);
}

.state-resolved {
    color: #9ef7a8;
    border-color: rgba(109, 233, 126, 0.5);
}

.priority-low {
    color: #a8c7e1;
    border-color: rgba(126, 184, 229, 0.38);
}

.priority-medium {
    color: #d1e9ff;
    border-color: rgba(163, 214, 255, 0.42);
}

.priority-high {
    color: #ffd296;
    border-color: rgba(255, 187, 101, 0.52);
}

.priority-critical {
    color: #ffb2b2;
    border-color: rgba(255, 120, 120, 0.58);
}

.opening-post {
    border: 1px solid rgba(127, 185, 224, 0.26);
    border-radius: 12px;
    background: rgba(8, 24, 45, 0.75);
    padding: 0.72rem;
}

.opening-post p {
    margin: 0;
    color: #d5eaff;
    line-height: 1.45;
}

.opening-post small {
    display: inline-block;
    margin-top: 0.5rem;
    color: var(--text-tertiary);
}

.reply-stream {
    display: grid;
    gap: 0.52rem;
    max-height: 420px;
    overflow: auto;
    padding-right: 0.18rem;
}

.reply-row {
    border: 1px solid rgba(120, 179, 219, 0.22);
    border-radius: 10px;
    padding: 0.62rem;
    background: rgba(8, 22, 41, 0.62);
}

.reply-row p {
    margin: 0.42rem 0 0;
    font-size: 0.81rem;
    color: #d4e9fb;
}

.reply-row footer {
    margin-top: 0.4rem;
    color: var(--text-tertiary);
    font-size: 0.7rem;
}

.side-column {
    display: grid;
    gap: 0.75rem;
    align-content: start;
}

.side-card {
    display: grid;
    gap: 0.45rem;
}

.side-card h3 {
    margin: 0;
}

.side-card p {
    margin: 0;
    font-size: 0.8rem;
    color: #c5dff7;
}

.summary-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 0.34rem;
}

.empty {
    margin: 0;
    color: var(--text-tertiary);
    font-size: 0.77rem;
}

.empty-thread {
    align-content: center;
    text-align: center;
}

@media (max-width: 1420px) {
    .board-layout {
        grid-template-columns: 1fr 1fr;
    }

    .side-column {
        grid-column: 1 / -1;
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 980px) {
    .filter-row {
        grid-template-columns: 1fr;
    }

    .board-layout {
        grid-template-columns: 1fr;
    }

    .side-column {
        grid-template-columns: 1fr;
    }

    .topic-column,
    .thread-column {
        min-height: auto;
    }
}
</style>
