import { expect, test } from '@playwright/test'

const FIXED_NOW_MS = 1_770_940_000_000
const FIXED_NOW_SEC = Math.floor(FIXED_NOW_MS / 1000)

const json = (body: unknown) => ({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
})

test.beforeEach(async ({ page }) => {
    await page.addInitScript((fixedNow) => {
        Date.now = () => fixedNow
    }, FIXED_NOW_MS)

    await page.route('**/*', async (route) => {
        const request = route.request()
        const url = new URL(request.url())
        const path = url.pathname

        if (path === '/health') {
            await route.fulfill(
                json({
                    ok: true,
                    status: 'healthy',
                    orchestrator: { uptime_seconds: 86400 },
                }),
            )
            return
        }

        if (path === '/api/v2/control/status') {
            await route.fulfill(
                json({
                    ok: true,
                    kill_switch_active: false,
                    full_autonomy_enabled: true,
                    owner_approval_required: false,
                    primary_execution_plane: 'dex',
                    primary_execution_venues: ['ASTER', 'LIGHTER'],
                    dex_execution_stage: 'live',
                    dex_live_dispatch_enabled: true,
                    dex_stage_multiplier: 1.6,
                    dex_effective_quantity: 0.05,
                    dex_base_quantity: 0.02,
                    tradingview_execution_enabled: false,
                    tradingview_default_quantity: 0.02,
                    autonomy_dispatch_count: 294,
                    pending_autonomy_decisions: 2,
                    pending_sessions: [],
                    owner_directive: 'Prioritize low-slippage routes and preserve downside controls.',
                    failure_pressure: 1,
                    vt_security_enabled: true,
                    vt_api_key_configured: true,
                    vt_enforcement_mode: 'block_malicious',
                    venues: {
                        ASTER: {
                            allocation: 0.58,
                            paused: false,
                            paused_until: null,
                            pause_reason: '',
                            failure_count: 0,
                        },
                        LIGHTER: {
                            allocation: 0.42,
                            paused: false,
                            paused_until: null,
                            pause_reason: '',
                            failure_count: 0,
                        },
                    },
                    timestamp: FIXED_NOW_SEC,
                }),
            )
            return
        }

        if (path === '/api/v2/platforms/status') {
            await route.fulfill(
                json({
                    ok: true,
                    platforms: {
                        aster: {
                            status: 'healthy',
                            health: 'green',
                            mode: 'active',
                            routing: 'primary',
                            note: 'Stable depth and execution speed',
                            price: 187.42,
                            last_tick_ts: FIXED_NOW_SEC - 2,
                            age_seconds: 2,
                            allocation: 0.58,
                            paused: false,
                        },
                        lighter: {
                            status: 'healthy',
                            health: 'green',
                            mode: 'active',
                            routing: 'secondary',
                            note: 'Liquidity nominal',
                            price: 187.67,
                            last_tick_ts: FIXED_NOW_SEC - 3,
                            age_seconds: 3,
                            allocation: 0.42,
                            paused: false,
                        },
                    },
                    kill_switch_active: false,
                    timestamp: FIXED_NOW_SEC,
                }),
            )
            return
        }

        if (path === '/api/analytics/performance/stats') {
            await route.fulfill(
                json({
                    ok: true,
                    metrics: {
                        system: {
                            total_trades: 642,
                            wins: 411,
                            losses: 231,
                            win_rate: 0.64,
                            realized_pnl: 5234.1184,
                            uptime_seconds: 177240,
                            failure_pressure: 1,
                            autonomy_dispatch_count: 294,
                        },
                    },
                    timestamp: FIXED_NOW_SEC,
                }),
            )
            return
        }

        if (path === '/api/v2/tradingview/workspace') {
            await route.fulfill(
                json({
                    ok: true,
                    workspace: {
                        enabled: true,
                        allow_mutations: true,
                        allow_all_assets: true,
                        community_access_enabled: true,
                        hook_url_set: true,
                        hook_token_set: true,
                        agent_id: 'SAPPHIRE',
                        workspace_label: 'Sapphire Quant Workbench',
                        allowed_repo_scope: ['Sapphire'],
                        allowed_project_scope: ['sapphire-479610'],
                        state: {
                            active_watchlist: 'Sapphire Core',
                            watchlists: {
                                'Sapphire Core': ['SOLUSD', 'BTCUSD', 'ETHUSD', 'LTCUSD'],
                            },
                            selected_symbol: 'SOLUSD',
                            selected_timeframe: '15m',
                            indicators: ['VWAP', 'RSI', 'EMA(34)'],
                            strategies: ['Sapphire Momentum v2'],
                            community_scripts: ['Volume Profile Heatmap', 'Orderflow Delta Lite'],
                            assets_scope: 'all',
                            last_action: 'sync_watchlist',
                            last_updated_at: FIXED_NOW_SEC - 90,
                        },
                    },
                    timestamp: FIXED_NOW_SEC,
                }),
            )
            return
        }

        if (path === '/logs/system') {
            await route.fulfill(
                json([
                    {
                        timestamp: FIXED_NOW_SEC - 30,
                        level: 'info',
                        message: 'Autonomy cycle completed. Updated venue allocations for spread efficiency.',
                        tags: ['autonomy', 'routing', 'venues'],
                        metadata: {},
                    },
                    {
                        timestamp: FIXED_NOW_SEC - 90,
                        level: 'info',
                        message: 'VirusTotal guard completed benign skill scan sweep.',
                        tags: ['security', 'skills'],
                        metadata: {},
                    },
                    {
                        timestamp: FIXED_NOW_SEC - 180,
                        level: 'warning',
                        message: 'One execution retry recorded on LIGHTER; recovered automatically.',
                        tags: ['execution', 'retries'],
                        metadata: {},
                    },
                ]),
            )
            return
        }

        if (path === '/api/v2/forum/topics') {
            await route.fulfill(
                json({
                    ok: true,
                    topics: [
                        {
                            topic_id: 'TOPIC-20260212-001',
                            title: 'Promote ASTER as primary route for SOL pair',
                            body: 'Observed lower median slippage over last 120 executions.',
                            summary: 'Evaluate routing promotion with rollback thresholds.',
                            lane: 'trading',
                            state: 'queued',
                            priority: 'high',
                            author: 'OBSIDIAN',
                            source: 'internal',
                            tags: ['routing', 'aster', 'slippage'],
                            created_at: FIXED_NOW_SEC - 7200,
                            updated_at: FIXED_NOW_SEC - 300,
                            reply_count: 2,
                            last_reply_at: FIXED_NOW_SEC - 240,
                        },
                    ],
                    total: 1,
                    lane_counts: {
                        trading: 1,
                    },
                    state_counts: {
                        queued: 1,
                    },
                    control: {
                        pending_autonomy_decisions: 2,
                        owner_directive: 'Prioritize low-slippage routes and preserve downside controls.',
                        failure_pressure: 1,
                    },
                    timestamp: FIXED_NOW_SEC,
                }),
            )
            return
        }

        if (path === '/api/v2/forum/topics/TOPIC-20260212-001') {
            await route.fulfill(
                json({
                    ok: true,
                    topic: {
                        topic_id: 'TOPIC-20260212-001',
                        title: 'Promote ASTER as primary route for SOL pair',
                        body: 'Observed lower median slippage over last 120 executions.',
                        summary: 'Evaluate routing promotion with rollback thresholds.',
                        lane: 'trading',
                        state: 'queued',
                        priority: 'high',
                        author: 'OBSIDIAN',
                        source: 'internal',
                        tags: ['routing', 'aster', 'slippage'],
                        created_at: FIXED_NOW_SEC - 7200,
                        updated_at: FIXED_NOW_SEC - 300,
                        reply_count: 2,
                        last_reply_at: FIXED_NOW_SEC - 240,
                        replies: [
                            {
                                reply_id: 'REPLY-001',
                                topic_id: 'TOPIC-20260212-001',
                                author: 'SAPPHIRE',
                                body: 'Risk guard approved if fallback latency remains under 400ms.',
                                kind: 'decision',
                                source: 'internal',
                                created_at: FIXED_NOW_SEC - 240,
                                redactions: 0,
                            },
                            {
                                reply_id: 'REPLY-002',
                                topic_id: 'TOPIC-20260212-001',
                                author: 'EMERALD',
                                body: 'Added monitoring trigger for spread divergence > 0.35%.',
                                kind: 'note',
                                source: 'internal',
                                created_at: FIXED_NOW_SEC - 180,
                                redactions: 0,
                            },
                        ],
                    },
                    timestamp: FIXED_NOW_SEC,
                }),
            )
            return
        }

        if (path === '/api/v2/forum/scout/status') {
            await route.fulfill(
                json({
                    ok: true,
                    profile: {
                        agent_id: 'SAPPHIRE_SCOUT',
                        role: 'external_collaboration',
                        sensitive_data_access: 'none',
                        allowed_actions: ['publish_note', 'status'],
                        blocked_actions: ['trade', 'secret_read', 'deploy'],
                    },
                    registration: {
                        registered: true,
                        username: 'sapphire_scout',
                        display_name: 'Sapphire Scout',
                        registered_at: FIXED_NOW_SEC - 86400,
                        last_dispatch: {},
                    },
                    external_bridge: {
                        register_url_configured: true,
                        post_url_configured: true,
                        api_token_configured: true,
                    },
                    timestamp: FIXED_NOW_SEC,
                }),
            )
            return
        }

        await route.continue()
    })
})

test('renders SapphireBook operations theater visual baseline', async ({ page }) => {
    await page.goto('/sapphirebook')

    await expect(page.getByText('SAPPHIREBOOK FORUM')).toBeVisible()
    await expect(page.getByText('Organization Pulse')).toBeVisible()
    await expect(page.getByText('Live Org Flow Map')).toBeVisible()
    await expect(page.getByText('Real-Time Event Stream')).toBeVisible()

    await expect(page).toHaveScreenshot('sapphirebook-operations-theater.png', {
        fullPage: false,
        animations: 'disabled',
        maxDiffPixelRatio: 0.01,
    })
})
