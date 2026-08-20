export interface Todo {
    todo_id: number
    creator: string
    umo: string
    content: string
    due_time: number
    completed: boolean
    tags: string[]
}

export interface EditTodoPayload {
    todo_id: number
    content: string
    due_time: number
    completed: boolean
    owners?: string[]
    tags?: string[]
}

export interface ApiResp {
    code: number,
    payload: Record<string, any>
}

export interface TagUser {
    sender_id: string
    umo: string
    is_admin: boolean
    nickname: string
    tags: string[]
}

export interface TagCatalogue {
    is_admin: boolean
    users: TagUser[]
    tag_senders: Record<string, string[]>
}

export interface UserDetail {
    sender_id: string
    umo: string
    is_admin: boolean
    nickname: string
    tags: string[]
}

export interface UpdateUmoPayload {
    sender_id: string
    umo: string
}
