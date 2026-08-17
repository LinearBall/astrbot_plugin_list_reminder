import type { ApiResp, EditTaskPayload, Task } from "@/types.ts";
import axios from "axios";

/**
 * 让axios不管返回HTTP状态码是啥都认为是成功，
 * 这样可以避免因为状态码问题导致执行流被打断
 */
const http = axios.create({
    validateStatus: _ => true
});

/**
 * 通过访问`/api/me`接口，检查用户是否已登录
 * 
 * @returns 已登录的用户ID(后端的sender_id)，若未登录则返回null
 */
async function checkIfAlreadyLoggedIn(): Promise<string | null> {
    let resp = await http.get<ApiResp>("/api/me");
    let data = resp.data as ApiResp;
    return data.code === 200 ? data["payload"]["sender_id"] as string : null;
}

/**
 * 通过访问`/api/login`接口，检查密钥是否正确
 * 
 * @param key 密钥
 * @returns 密钥是否正确
 */
async function checkKey(key: string): Promise<boolean> {
    let resp = await http.post<ApiResp>("/api/login", {
        key: key
    });
    let data = resp.data as ApiResp;
    return Promise.resolve(data.code === 200);
}

/**
 * 通过访问`/api/logout`接口，注销当前登录用户
 */
async function logout(): Promise<void> {
    await http.post<ApiResp>("/api/logout");
}

/**
 * 取得当前用户创建的所有任务
 */
async function getTasks(): Promise<Task[]> {
    let resp = await http.get<ApiResp>("/api/tasks");
    let data = resp.data as ApiResp;
    return data.code === 200 ? data["payload"]["tasks"] as Task[] : [];
}

async function delTaskById(taskId: number) {
    let resp = await http.delete(`/api/tasks/${taskId}`);
    let data = resp.data as ApiResp;
    return data;
}

async function updateTaskById(taskId: number, payload: Pick<EditTaskPayload, "content" | "due_time">) {
    let resp = await http.put<ApiResp>(`/api/tasks/${taskId}`, payload);
    let data = resp.data as ApiResp;
    return data;
}

export { checkIfAlreadyLoggedIn, checkKey, logout, getTasks, delTaskById, updateTaskById }
