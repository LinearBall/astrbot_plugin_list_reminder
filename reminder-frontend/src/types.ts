export interface Task {
    task_id: number
    creator: string
    umo: string
    content: string
    due_time: number
    completed: boolean
}

export interface ApiResp {
    code: number,
    payload: Record<string, any>
}
