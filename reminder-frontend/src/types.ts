export interface Todo {
    todo_id: number
    creator: string
    umo: string
    content: string
    due_time: number
    completed: boolean
}

export interface EditTodoPayload {
    todo_id: number
    content: string
    due_time: number
    completed: boolean
}

export interface ApiResp {
    code: number,
    payload: Record<string, any>
}
