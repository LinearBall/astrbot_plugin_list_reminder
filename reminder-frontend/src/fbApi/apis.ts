import type { ApiResp } from "@/types.ts";
import axios from "axios";

const http = axios.create({
    validateStatus: _ => true
});

async function checkIfAlreadyLoggedIn(): Promise<string | null> {
    let resp = await http.get<ApiResp>("/api/me");
    let data = resp.data as ApiResp;
    return data.code === 200 ? data["payload"]["sender_id"] as string : null;
}

async function checkKey(key: string): Promise<boolean> {
    let resp = await http.post<ApiResp>("/api/login", {
        key: key
    });
    let data = resp.data as ApiResp;
    console.log(data);
    return Promise.resolve(data.code === 200);
}

async function logout(): Promise<void> {
    await http.post<ApiResp>("/api/logout");
}

export { checkIfAlreadyLoggedIn, checkKey, logout }