export interface Task {
    task_id: number
    creator: string
    umo: string
    content: string
    due_time: number
    completed: boolean
}

export interface EditTaskPayload {
    task_id: number
    content: string
    due_time: number
}

export interface ApiResp {
    code: number,
    payload: Record<string, any>
}
