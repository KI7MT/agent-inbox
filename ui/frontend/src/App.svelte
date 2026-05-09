<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import AgentSidebar from './lib/AgentSidebar.svelte'
  import MessageList from './lib/MessageList.svelte'
  import MessageDetail from './lib/MessageDetail.svelte'
  import ComposeModal from './lib/ComposeModal.svelte'
  import type { AgentInfo, Message, Paths, Stats, ViewName } from './lib/types'

  // Wails-generated bindings (produced at build time by `wails build` / `wails dev`)
  import {
    Approve,
    GetAgents,
    GetMessage,
    GetMessages,
    GetPaths,
    GetStats,
    Ping,
    Reject,
    ReplyMessage,
    SendMessage,
    SetStatus,
  } from '../wailsjs/go/main/App.js'

  let agents: AgentInfo[] = []
  let messages: Message[] = []
  let selected: Message | null = null
  let stats: Stats | null = null
  let paths: Paths | null = null
  let connected = false
  let loading = false
  let statusMessage = ''

  let view: ViewName = 'pending_approval'
  let selectedRecipient = ''

  let showCompose = false
  let composeReplyTo: { sender: string; subject: string } | null = null
  let composeModal: ComposeModal

  let pollTimer: ReturnType<typeof setInterval> | null = null

  function startPolling() {
    if (pollTimer) return
    pollTimer = setInterval(refreshAll, 2000)
  }
  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }
  function onVisibilityChange() {
    if (document.visibilityState === 'visible') {
      refreshAll()
      startPolling()
    } else {
      stopPolling()
    }
  }

  function toast(msg: string) {
    statusMessage = msg
    setTimeout(() => { if (statusMessage === msg) statusMessage = '' }, 3500)
  }

  async function refreshAgents() {
    try { agents = (await GetAgents()) ?? [] } catch (e) { toast('agents: ' + e) }
  }
  async function refreshStats() {
    try { stats = await GetStats() } catch (e) { toast('stats: ' + e) }
  }
  async function refreshMessages() {
    loading = true
    try {
      const recipient = view === 'for_recipient' ? selectedRecipient : ''
      messages = (await GetMessages(view, recipient, '', '', 0, 200)) ?? []
    } catch (e) {
      toast('messages: ' + e)
    } finally {
      loading = false
    }
  }
  async function refreshAll() {
    await Promise.all([refreshAgents(), refreshStats(), refreshMessages()])
  }

  function selectView(e: CustomEvent<{ view: ViewName; recipient?: string }>) {
    view = e.detail.view
    selectedRecipient = e.detail.recipient ?? ''
    selected = null
    refreshMessages()
  }

  async function selectMessage(e: CustomEvent<string>) {
    try {
      selected = await GetMessage(e.detail)
      // Auto-mark unread → read when the operator opens it (info priority only;
      // action/urgent stay unread until explicitly approved/rejected so the
      // approval queue stays accurate).
      if (selected && selected.status === 'unread' && selected.priority === 'info') {
        await SetStatus(selected.id, 'read')
        selected = { ...selected, status: 'read' }
        refreshAll()
      }
    } catch (e) {
      toast('read: ' + e)
    }
  }

  async function approve(e: CustomEvent<string>) {
    try {
      await Approve(e.detail)
      toast('approved')
      if (selected?.id === e.detail) selected = { ...selected!, status: 'approved' }
      refreshAll()
    } catch (e) { toast('approve: ' + e) }
  }
  async function reject(e: CustomEvent<string>) {
    try {
      await Reject(e.detail)
      toast('rejected')
      if (selected?.id === e.detail) selected = { ...selected!, status: 'rejected' }
      refreshAll()
    } catch (e) { toast('reject: ' + e) }
  }
  async function setStatus(e: CustomEvent<{ id: string; status: string }>) {
    try {
      await SetStatus(e.detail.id, e.detail.status)
      if (selected?.id === e.detail.id) selected = { ...selected!, status: e.detail.status as Message['status'] }
      refreshAll()
    } catch (e) { toast('status: ' + e) }
  }

  function openCompose() { composeReplyTo = null; showCompose = true }
  function openReply() {
    if (!selected) return
    composeReplyTo = { sender: selected.sender, subject: selected.subject }
    showCompose = true
  }

  async function send(e: CustomEvent<{ recipient: string; priority: string; subject: string; body: string }>) {
    if (!paths) return
    try {
      if (composeReplyTo && selected) {
        await ReplyMessage(paths.operator, selected.id, e.detail.body, e.detail.priority)
      } else {
        const result = await SendMessage(paths.operator, e.detail.recipient, e.detail.priority, e.detail.subject, e.detail.body)
        if (e.detail.recipient === 'all' && result.broadcast_to && result.broadcast_to.length === 0) {
          composeModal.onError('No recipients to broadcast to (no other registered agents).')
          return
        }
      }
      composeModal.onSent()
      toast(`sent to ${e.detail.recipient}`)
      refreshAll()
    } catch (err) {
      composeModal.onError(String(err))
    }
  }

  onMount(async () => {
    try {
      await Ping()
      connected = true
      paths = await GetPaths()
      await refreshAll()
    } catch (e) {
      toast('connect: ' + e)
    }
    // Pause polling when the window is hidden / backgrounded — saves
    // ~1,800 SQLite reads per hour when the operator isn't looking.
    document.addEventListener('visibilitychange', onVisibilityChange)
    if (document.visibilityState === 'visible') startPolling()
  })
  onDestroy(() => {
    stopPolling()
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })
</script>

<div class="flex flex-col h-full">
  <header class="flex items-center justify-between px-4 py-2 bg-ink-800 border-b border-slate-700">
    <div class="flex items-center gap-3">
      <h1 class="text-base font-semibold text-slate-100">Agent Inbox</h1>
      <span class="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded
                   {connected ? 'bg-emerald-900/40 text-emerald-300' : 'bg-red-900/40 text-red-300'}">
        {connected ? 'Connected' : 'Disconnected'}
      </span>
      {#if paths}
        <span class="text-[10px] text-slate-500">operator: {paths.operator}</span>
      {/if}
    </div>
    <div class="flex items-center gap-2">
      <button on:click={openCompose}
              class="text-xs bg-amber-600 hover:bg-amber-500 text-white px-3 py-1 rounded font-medium">
        New message
      </button>
      <button on:click={refreshAll}
              class="text-xs bg-ink-700 hover:bg-ink-800 text-slate-300 px-3 py-1 rounded border border-slate-600">
        Refresh
      </button>
    </div>
  </header>

  {#if statusMessage}
    <div class="px-4 py-1 text-xs text-amber-300 bg-ink-800 border-b border-slate-700">
      {statusMessage}
    </div>
  {/if}

  <div class="flex flex-1 min-h-0">
    <AgentSidebar
      {agents}
      pendingCount={stats?.pending_approval ?? 0}
      {view}
      {selectedRecipient}
      on:select={selectView}
    />

    <div class="w-[420px] border-r border-slate-700 overflow-y-auto">
      <MessageList
        {messages}
        {loading}
        selectedId={selected?.id ?? ''}
        on:select={selectMessage}
      />
    </div>

    <div class="flex-1 overflow-y-auto">
      {#if selected}
        <MessageDetail
          message={selected}
          on:approve={approve}
          on:reject={reject}
          on:setstatus={setStatus}
          on:reply={openReply}
        />
      {:else}
        <div class="flex items-center justify-center h-full text-slate-500 text-sm">
          Select a message to view
        </div>
      {/if}
    </div>
  </div>

  <ComposeModal
    bind:this={composeModal}
    bind:show={showCompose}
    {agents}
    operator={paths?.operator ?? 'operator'}
    replyTo={composeReplyTo}
    on:send={send}
    on:close={() => { showCompose = false }}
  />
</div>
