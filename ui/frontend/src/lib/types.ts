// Types mirror the Go structs in ../app.go and ../store.go.

export interface Message {
  id: string
  timestamp: string
  created_unix: number
  sender: string
  recipient: string
  priority: 'info' | 'action' | 'urgent'
  status: 'unread' | 'read' | 'approved' | 'rejected' | 'in_progress' | 'done'
  subject: string
  body: string
  parent_id?: string
}

export interface AgentInfo {
  name: string
  is_operator: boolean
  pending_mail: number
}

export interface Stats {
  total: number
  unread: number
  read: number
  approved: number
  in_progress: number
  rejected: number
  done: number
  pending_approval: number
  by_recipient: Record<string, number>
}

export interface Paths {
  briefs_dir: string
  db_path: string
  operator: string
}

export type ViewName = 'pending_approval' | 'all' | 'for_recipient'
