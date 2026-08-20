import type { ApiResp, EditTodoPayload, TagCatalogue, Todo, UserDetail } from "@/types.ts";
import axios from "axios";

/**
 * 让axios不管返回HTTP状态码是啥都认为是成功，
 * 这样可以避免因为状态码问题导致执行流被打断
 */
const http = axios.create({
    validateStatus: _ => true
});

/**
 * 方案A：每个标签页从自己的 URL 查询参数里取登录密钥，
 * 并在后续每个请求头里携带 `X-Auth-Key`，从而同一台电脑上能同时打开多个账号的后台。
 */
let authKey: string | null = new URLSearchParams(window.location.search).get("key");

http.interceptors.request.use((config) => {
    if (authKey) {
        config.headers.set("X-Auth-Key", authKey);
    }
    return config;
});

export function setAuthKey(key: string | null): void {
    authKey = key;
}

export function getAuthKey(): string | null {
    return authKey;
}

interface Me {
    sender_id: string;
    is_admin: boolean;
}

/**
 * 通过访问`/api/me`接口，检查用户是否已登录
 *
 * @returns 已登录的用户信息，若未登录则返回null
 */
async function checkIfAlreadyLoggedIn(): Promise<Me | null> {
    let resp = await http.get<ApiResp>("/api/me");
    let data = resp.data as ApiResp;
    return data.code === 200
        ? { sender_id: data["payload"]["sender_id"] as string, is_admin: !!data["payload"]["is_admin"] }
        : null;
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
    return data.code === 200;
}

/**
 * 通过访问`/api/logout`接口，注销当前登录用户
 */
async function logout(): Promise<void> {
    await http.post<ApiResp>("/api/logout");
    setAuthKey(null);
}

/**
 * 取得当前用户可见的所有待办
 */
async function getTodos(): Promise<Todo[]> {
    let resp = await http.get<ApiResp>("/api/todos");
    let data = resp.data as ApiResp;
    return data.code === 200 ? data["payload"]["todos"] as Todo[] : [];
}

async function delTodoById(todoId: number) {
    let resp = await http.delete(`/api/todos/${todoId}`);
    return resp.data as ApiResp;
}

/**
 * 更新指定待办的内容和截止时间，若待办Id为-1，则创建新待办
 */
async function updateTodoById(payload: EditTodoPayload) {
    let todoId = payload.todo_id;
    return http({
        method: todoId < 0 ? "POST" : "PUT",
        url: todoId < 0 ? "/api/todos" : `/api/todos/${todoId}`,
        data: payload,
    }).then(res => res.data as ApiResp);
}

/**
 * 切换当前用户的管理员权限（开启 / 关闭）
 */
async function toggleAdmin(): Promise<ApiResp> {
    let resp = await http.post<ApiResp>("/api/admin/toggle");
    return resp.data as ApiResp;
}

/**
 * 获取当前用户可见的标签目录（管理员看到全部用户，普通用户只看到自己）
 */
async function getTagCatalogue(): Promise<TagCatalogue> {
    let resp = await http.get<ApiResp>("/api/tags");
    let data = resp.data as ApiResp;
    return data.code === 200 ? data["payload"] as TagCatalogue : { is_admin: false, users: [], tag_senders: {} };
}

/**
 * 给指定用户添加一个标签（普通用户只能操作自己，管理员可操作任意用户）
 * @param senderId 目标用户 sender_id
 * @param tag 要添加的标签名
 */
async function addUserTag(senderId: string, tag: string): Promise<ApiResp> {
    let resp = await http.post<ApiResp>("/api/tags", { tag: tag, sender_id: senderId });
    return resp.data as ApiResp;
}

/**
 * 给指定用户移除一个标签
 * @param senderId 目标用户 sender_id
 * @param tag 要移除的标签名
 */
async function removeUserTag(senderId: string, tag: string): Promise<ApiResp> {
    let resp = await http.delete<ApiResp>("/api/tags", { data: { tag: tag, sender_id: senderId } });
    return resp.data as ApiResp;
}

/**
 * 修改当前用户自己的昵称
 * @param nickname 新昵称
 */
async function updateOwnNickname(nickname: string): Promise<ApiResp> {
    let resp = await http.post<ApiResp>("/api/users/nickname", { nickname: nickname });
    return resp.data as ApiResp;
}

/**
 * 查询某用户的完整信息（userDB 所有字段 + 关联标签）
 * @param senderId 目标用户 sender_id
 */
async function getUserDetail(senderId: string): Promise<UserDetail | null> {
    let resp = await http.get<ApiResp>(`/api/users/${senderId}`);
    let data = resp.data as ApiResp;
    return data.code === 200 ? data["payload"] as UserDetail : null;
}

export { checkIfAlreadyLoggedIn, checkKey, logout, getTodos, delTodoById, updateTodoById, toggleAdmin, getTagCatalogue, addUserTag, removeUserTag, updateOwnNickname, getUserDetail }
