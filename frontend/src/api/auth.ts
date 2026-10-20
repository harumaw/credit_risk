import { request } from "./client";

export type UserStatus = "pending_verification" | "active" | "blocked";

export interface UserProfile {
  id: string;
  email: string | null;
  last_name: string;
  first_name: string;
  middle_name: string | null;
  inn_fl: string | null;
  phone: string | null;
  status: UserStatus;
}

export interface RegisterPayload {
  email: string;
  password: string;
  last_name: string;
  first_name: string;
  middle_name: string | null;
  inn_fl: string;
  phone: string | null;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function register(payload: RegisterPayload): Promise<UserProfile> {
  return request<UserProfile>("/auth/register", { method: "POST", body: payload });
}

export async function login(email: string, password: string): Promise<string> {
  const res = await request<TokenResponse>("/auth/login", { method: "POST", body: { email, password } });
  return res.access_token;
}

export function fetchMe(token: string): Promise<UserProfile> {
  return request<UserProfile>("/auth/me", { token });
}
