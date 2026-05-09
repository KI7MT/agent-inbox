// Hand-rolled stub for the Wails-generated models. Wails regenerates
// these files at `wails build` / `wails dev` time. Committed so fresh
// checkouts can `npm run check` and have IDE type-resolution without
// first running wails.

export namespace main {
  export type Priority = 'info' | 'action' | 'urgent'
  export type Status = 'unread' | 'read' | 'approved' | 'rejected' | 'in_progress' | 'done'

  // Hand-rolled stub narrows priority and status to literal unions for
  // type-checking. Wails regenerates this file with plain `string` for
  // both — runtime behavior is identical because the Go side enforces
  // the same allowed values via SQLite CHECK constraints.
  export class Message {
    id: string = ''
    timestamp: string = ''
    created_unix: number = 0
    sender: string = ''
    recipient: string = ''
    priority: Priority = 'info'
    status: Status = 'unread'
    subject: string = ''
    body: string = ''
    parent_id?: string

    static createFrom(source: any = {}) { return new Message(source) }

    constructor(source: any = {}) {
      if (typeof source === 'string') source = JSON.parse(source)
      Object.assign(this, source)
    }
  }

  export class AgentInfo {
    name: string = ''
    is_operator: boolean = false
    pending_mail: number = 0

    static createFrom(source: any = {}) { return new AgentInfo(source) }

    constructor(source: any = {}) {
      if (typeof source === 'string') source = JSON.parse(source)
      Object.assign(this, source)
    }
  }

  export class Stats {
    total: number = 0
    unread: number = 0
    read: number = 0
    approved: number = 0
    in_progress: number = 0
    rejected: number = 0
    done: number = 0
    pending_approval: number = 0
    by_recipient: Record<string, number> = {}

    static createFrom(source: any = {}) { return new Stats(source) }

    constructor(source: any = {}) {
      if (typeof source === 'string') source = JSON.parse(source)
      Object.assign(this, source)
      if (!this.by_recipient) this.by_recipient = {}
    }
  }

  export class Paths {
    briefs_dir: string = ''
    db_path: string = ''
    operator: string = ''

    static createFrom(source: any = {}) { return new Paths(source) }

    constructor(source: any = {}) {
      if (typeof source === 'string') source = JSON.parse(source)
      Object.assign(this, source)
    }
  }
}
